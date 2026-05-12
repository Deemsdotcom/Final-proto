"""Shared helpers for Streamlit session state and routing.

We use DB-backed stage tracking so refreshes don't lose progress.
Session state is rebuilt from the DB on resume.

Layer 2 resume note: the firm simulation is continuous and intra-layer
state isn't checkpointed to DB. If a candidate refreshes mid-Layer-2
they'll restart Layer 2 from Week 1. Once they finish Layer 2, the
final state is persisted and they can resume into Layer 3.
"""

from __future__ import annotations

import streamlit as st

from database import db

STAGES = ["intro", "layer1", "layer2", "layer3", "results", "done"]


def init_session_state() -> None:
    defaults = {
        "mode": None,                # 'candidate' or 'recruiter'
        "candidate_id": None,
        "candidate_name": None,
        "candidate_email": None,
        "stage": "landing",
        "recruiter_authed": False,

        # Layer 1 progress
        "l1_theme_idx": 0,
        "l1_question_idx": 0,
        "l1_questions_cache": {},       # theme -> list[Question]
        "l1_theme_scores": {},          # theme -> score (used for final results)
        "l1_question_started_at": None,

        # Layer 2 progress (simulation)
        "l2_started": False,
        "l2_started_at": None,
        "l2_state": None,                # the firm simulation state dict

        # Layer 3 progress (per-question two-step flow with main + followup)
        "l3_started": False,
        "l3_main_questions": [],
        "l3_question_idx": 0,
        "l3_phase": "main",              # 'main' or 'followup'
        "l3_current_followup": None,
        "l3_answer_scores": [],
        "l3_question_started_at": None,
        "l3_last_transcript": None,

        # Layer 3 voice-call state (hands-free single-page call)
        "l3_call_phase": "intro",        # intro / active / closing / scoring / done
        "l3_turn_idx": 0,
        "l3_main_transcripts": {},
        "l3_followups": {},
        "l3_followup_transcripts": {},
        "l3_mic_nonce": 0,
        "l3_consumed_fingerprint": None,
        "l3_closer_spoken": False,
        "l3_closing_started_at": None,

        # Results cache
        "final_result_computed": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def reset_candidate_state() -> None:
    """Wipe all candidate-specific session state."""
    keys = [
        "mode", "candidate_id", "candidate_name", "candidate_email", "stage",
        "l1_theme_idx", "l1_question_idx", "l1_questions_cache", "l1_theme_scores",
        "l1_question_started_at",
        "l2_started", "l2_started_at", "l2_state",
        "l3_started", "l3_main_questions", "l3_question_idx", "l3_phase",
        "l3_current_followup", "l3_answer_scores", "l3_question_started_at",
        "l3_last_transcript",
        "l3_call_phase", "l3_turn_idx", "l3_main_transcripts", "l3_followups",
        "l3_followup_transcripts", "l3_mic_nonce", "l3_consumed_fingerprint",
        "l3_closer_spoken", "l3_closing_started_at",
        "final_result_computed",
    ]
    # Also strip any per-turn / per-theme dynamic keys.
    dynamic_prefixes = [
        "l3_transcript_", "l3_audio_", "l3_transcript_shown_",
        "l3_transcribed_id_", "l3_main_transcript_",
        "l3_spoken_", "l3_speak_started_", "l3_deadline_", "l3_spoken_turn_",
        "l3_autoadvanced_", "l3_recording_", "l3_ttsdone_",
        "l3_typed_mode_", "l3_typed_fallback_comp_",
        "l1_theme_started_at_", "l1_ai_flag_",
        "l2_ai_flag",
    ]
    for k in list(st.session_state.keys()):
        if any(k.startswith(p) or k == p for p in dynamic_prefixes):
            del st.session_state[k]
    for k in keys:
        if k in st.session_state:
            del st.session_state[k]
    init_session_state()


def _wipe_layer1_state() -> None:
    """Reset every Layer 1 session_state key + dynamic per-theme flags."""
    st.session_state.l1_theme_idx = 0
    st.session_state.l1_question_idx = 0
    st.session_state.l1_questions_cache = {}
    st.session_state.l1_theme_scores = {}
    st.session_state.l1_question_started_at = None
    st.session_state.l1_overview_seen = False
    for k in list(st.session_state.keys()):
        if not isinstance(k, str):
            continue
        for prefix in (
            "l1_logical_started", "l1_numerical_started", "l1_verbal_started",
            "l1_theme_started_at_", "l1_ai_flag_",
        ):
            if k == prefix or k.startswith(prefix):
                del st.session_state[k]
                break


def _wipe_layer2_state() -> None:
    """Reset every Layer 2 session_state key."""
    st.session_state.l2_started = False
    st.session_state.l2_started_at = None
    st.session_state.l2_state = None
    st.session_state.pop("l2_ai_flag", None)


def _wipe_layer3_state() -> None:
    """Reset every Layer 3 session_state key + per-turn dynamic flags."""
    fixed = {
        "l3_started": False,
        "l3_main_questions": [],
        "l3_question_idx": 0,
        "l3_phase": "main",
        "l3_current_followup": None,
        "l3_answer_scores": [],
        "l3_question_started_at": None,
        "l3_last_transcript": None,
        "l3_call_phase": "intro",
        "l3_turn_idx": 0,
        "l3_main_transcripts": {},
        "l3_followups": {},
        "l3_followup_transcripts": {},
        "l3_mic_nonce": 0,
        "l3_consumed_fingerprint": None,
        "l3_closer_spoken": False,
        "l3_closing_started_at": None,
    }
    for k, v in fixed.items():
        st.session_state[k] = v
    for k in list(st.session_state.keys()):
        if isinstance(k, str) and k.startswith("l3_spoken_turn_"):
            del st.session_state[k]


def resume_from_db(candidate: dict) -> None:
    """Resume the candidate at the START of their current layer.

    Earlier-layer data is kept (so candidates who already finished
    Layer 1 don't have to redo it). The CURRENT in-progress layer
    is wiped both in the DB and in session_state so the candidate
    restarts that layer cleanly.

    Coarse rather than question-level resume because real candidates
    lose context mid-layer (especially in the timed Layer 1 and the
    voice-call Layer 3) and prefer a clean restart of the whole
    layer. The 2-hour TTL on incomplete attempts (in app.py) is the
    outer bound: outside that window the entire candidate row is
    purged and the email starts from scratch.
    """
    from assessment_logic.layer1_logic import THEMES

    cid = candidate["candidate_id"]
    st.session_state.mode = "candidate"
    st.session_state.candidate_id = cid
    st.session_state.candidate_name = candidate["full_name"]
    st.session_state.candidate_email = candidate["email"]

    stage = candidate["current_stage"]
    st.session_state.stage = stage

    # ---- Rehydrate earlier-layer scores ----
    if stage in ("layer2", "layer3", "results", "done"):
        # Layer 1 was completed. Pull theme_scores from saved rows so the
        # final-results aggregation works.
        l1_rows = db.get_layer1_results(cid)
        theme_correct = {"logical": 0, "numerical": 0, "verbal": 0}
        theme_total   = {"logical": 0, "numerical": 0, "verbal": 0}
        for r in l1_rows:
            theme_total[r["theme"]]   += 1
            theme_correct[r["theme"]] += int(r["is_correct"])
        st.session_state.l1_theme_scores = {
            t: (theme_correct[t] / theme_total[t] * 100) if theme_total[t] > 0 else 0.0
            for t in ("logical", "numerical", "verbal")
        }
        # Mark Layer 1 as fully done so its router doesn't show again.
        st.session_state.l1_theme_idx = len(THEMES)
        st.session_state.l1_question_idx = 0
        st.session_state.l1_overview_seen = True
        for t in THEMES:
            st.session_state[f"l1_{t}_started"] = True

    if stage in ("layer3", "results", "done"):
        # Layer 2 row already in DB; just flag it as started so the
        # router doesn't re-run the sim.
        st.session_state.l2_started = True

    if stage in ("results", "done"):
        # Layer 3 was completed. Rehydrate competency scores.
        l3_rows = db.get_layer3_results(cid)
        st.session_state.l3_answer_scores = [
            {
                "competency_key": r["competency_key"],
                "competency_id": r["competency_id"],
                "score": r["competency_score"] if r["competency_score"] is not None else 0,
                "scripted_flag": bool(r.get("scripted_flag")) if isinstance(r, dict) else bool(r["scripted_flag"]),
            } for r in l3_rows
        ]
        st.session_state.l3_started = True
        st.session_state.l3_call_phase = "done"

    # ---- Wipe the CURRENT in-progress layer ----
    if stage == "intro":
        # Nothing to wipe; they just signed up.
        _wipe_layer1_state()
        _wipe_layer2_state()
        _wipe_layer3_state()
    elif stage == "layer1":
        db.clear_layer1_results(cid)
        _wipe_layer1_state()
        _wipe_layer2_state()
        _wipe_layer3_state()
    elif stage == "layer2":
        db.clear_layer2_simulation(cid)
        _wipe_layer2_state()
        _wipe_layer3_state()
    elif stage == "layer3":
        db.clear_layer3_results(cid)
        _wipe_layer3_state()
    # stage == "results" or "done": leave everything alone.


def advance_stage(new_stage: str) -> None:
    st.session_state.stage = new_stage
    if st.session_state.candidate_id:
        db.set_stage(st.session_state.candidate_id, new_stage)
    st.rerun()
