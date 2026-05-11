"""Layer 3 view: AI-led interview rebuilt as a hands-free voice call.

Flow:
  1. Pre-call intro. Candidate clicks Begin call.
  2. In-call: the AI speaks one utterance via Web Speech, the recorder
     auto-arms, in-browser VAD watches the mic and auto-stops on ~1.5s of
     silence. Candidate never clicks anything during the conversation, never
     sees a transcript, never sees the question text on screen.
  3. Closer: the AI says goodbye, then we run all five competency-level
     scoring passes (existing rubric, untouched).
  4. Complete confirmation screen.

Turn machine: ten listen turns per call (5 main questions + 5 AI follow-ups).
  comp_idx = turn_idx // 2
  phase    = "main" if turn_idx % 2 == 0 else "followup"

State keys (declared in views/state.py):
  l3_call_phase           : intro / active / closing / scoring / done
  l3_main_questions       : list[dict] from load_main_questions(candidate_id)
  l3_turn_idx             : 0..9
  l3_main_transcripts     : {comp_idx: transcript}
  l3_followups            : {comp_idx: {"bucket": str, "question": str}}
  l3_followup_transcripts : {comp_idx: transcript}
  l3_mic_nonce            : per-turn fresh-widget key
  l3_consumed_fingerprint : last consumed (file_id, size) - prevents
                            double-consumption on Streamlit reruns
"""

from __future__ import annotations

import time

import streamlit as st

from assessment_logic.layer3_logic import (
    COMPETENCY_COUNT,
    RECRUITER_OPENER,
    RECRUITER_CLOSER,
    acknowledge_line,
    generate_followup,
    load_main_questions,
    score_competency,
    transition_line,
)
from assessment_logic.llm_client import transcribe_audio
from assessment_logic.voice_call import prewarm_tts, release_call_mic, render_silent_turn, render_voice_turn
from database import db

from . import _design as ui
from .state import advance_stage

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:  # pragma: no cover - autorefresh is in requirements.txt
    st_autorefresh = None


MIC_AVAILABLE = hasattr(st, "audio_input")


# ---------- public entry ----------

def render() -> None:
    ui.inject_global_styles()
    ui.header(meta="Layer 3 of 3")

    _ensure_state_defaults()
    phase = st.session_state.l3_call_phase

    if phase == "intro":
        _render_intro()
    elif phase == "active":
        _render_active()
    elif phase == "closing":
        _render_closing()
    elif phase == "scoring":
        _render_scoring()
    else:  # "done"
        _render_done()


# ---------- state ----------

def _ensure_state_defaults() -> None:
    """Initialise the new-style state keys on first render.

    The legacy l3_started flag is still recognised so a candidate who was
    mid-flow on the previous version doesn't get stuck.
    """
    defaults = {
        "l3_call_phase": "intro",
        "l3_main_transcripts": {},
        "l3_followups": {},
        "l3_followup_transcripts": {},
        "l3_mic_nonce": 0,
        "l3_consumed_fingerprint": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # Bridge: if the older l3_started flag was set by a stale session, treat
    # it as "intro" so the candidate sees the new pre-call screen.
    if st.session_state.get("l3_started") and st.session_state.l3_call_phase == "intro":
        st.session_state.l3_started = False


# ---------- screens ----------

def _render_intro() -> None:
    ui.eyebrow("Layer 3 · AI-led interview")
    ui.page_title(
        "Voice call with an AI recruiter",
        subtitle="Four short questions, around sixteen minutes. Speak openly - there are no right or wrong answers.",
    )

    # Quietly warm the browser's TTS engine while the candidate reads the
    # prep copy below. Saves ~400ms on the first turn (the opener) where
    # otherwise we'd be waiting on the voices-loaded fallback timer.
    prewarm_tts()

    with ui.card(eyebrow_text="Before you begin"):
        st.markdown(
            "- Put on headphones if you can - it stops the AI's voice from feeding into your microphone.  \n"
            "- When the browser asks for microphone access, click Allow. You only need to grant it once.  \n"
            "- The AI will read each question out loud, then listen. Just speak naturally - "
            "the call will move on by itself when you stop talking.  \n"
            "- You won't see the questions or your transcript on the screen. Treat it like a real phone interview."
        )

    if not MIC_AVAILABLE:
        ui.info_banner(
            "Voice recording isn't available in this browser. Please open the link in Chrome, Edge, or Safari.",
            icon="!",
        )
        return

    if st.button("Begin call", type="primary", use_container_width=True):
        # Clear any leftover rows from a previous attempt so a re-take
        # doesn't double-write into layer3_results.
        db.clear_layer3_results(st.session_state.candidate_id)
        # Build the question list now so we can reference it deterministically
        # for the rest of the call.
        if not st.session_state.l3_main_questions:
            st.session_state.l3_main_questions = load_main_questions(
                st.session_state.candidate_id
            )
        # Reset per-call state (in case the candidate is restarting).
        st.session_state.l3_main_transcripts = {}
        st.session_state.l3_followups = {}
        st.session_state.l3_followup_transcripts = {}
        st.session_state.l3_answer_scores = []
        st.session_state.l3_closer_spoken = False
        # Clear any stale per-turn spoken flags from a previous attempt.
        for k in list(st.session_state.keys()):
            if isinstance(k, str) and k.startswith("l3_spoken_turn_"):
                del st.session_state[k]
        st.session_state.l3_call_phase = "active"
        st.session_state.l3_started = True  # legacy flag, kept for resume_from_db
        st.session_state.l3_turn_idx = 0
        st.session_state.l3_mic_nonce = 0
        st.session_state.l3_consumed_fingerprint = None
        st.session_state.l3_question_started_at = time.time()
        st.rerun()


def _render_active() -> None:
    turn_idx = st.session_state.l3_turn_idx

    # End-of-call sentinel: we've collected all ten listen turns.
    total_turns = COMPETENCY_COUNT * 2
    if turn_idx >= total_turns:
        st.session_state.l3_call_phase = "closing"
        st.session_state.l3_closing_started_at = time.time()
        release_call_mic()
        st.rerun()
        return

    comp_idx = turn_idx // 2
    phase = "main" if turn_idx % 2 == 0 else "followup"
    questions = st.session_state.l3_main_questions
    comp = questions[comp_idx]

    ai_text = _compose_ai_line(comp, comp_idx, phase)

    # Visual header. Deliberately spare - no question text, no progress
    # rail, no transcript echo. Looks like a phone call status line.
    ui.eyebrow("Call in progress")
    ui.page_title(
        "AI Interview",
        subtitle="The interviewer is on the line. Speak when you hear them finish.",
    )

    # Reserve a slot for the status pulse. We fill it later once we know
    # whether this render is the FIRST render of a turn (live call) or
    # the consuming render where transcription + follow-up generation is
    # about to run (in which case we show 'Reviewing your answer...' so
    # the candidate sees something happening instead of silent waiting).
    status_slot = st.empty()

    # The voice turn helper: renders st.audio_input + a components.html JS
    # block that speaks ai_text, auto-arms the recorder, and stops on
    # silence. The returned audio_file is the UploadedFile from audio_input.
    mic_key = f"l3_mic_{st.session_state.l3_mic_nonce}"

    # The TTS+VAD script should only run on the FIRST render of a turn.
    # Subsequent renders of the same turn (most importantly the rerun that
    # delivers the candidate's audio for transcription) must NOT re-speak
    # the AI line - otherwise the previous turn's text starts replaying
    # during the transcription window and gets cut off when the next
    # turn finally renders. We track "did I already speak this turn?" by
    # turn_idx because mic_nonce advances together with turn_idx.
    turn_spoken_key = f"l3_spoken_turn_{turn_idx}"
    should_speak_now = not st.session_state.get(turn_spoken_key, False)
    # Per-turn ID for the JS dedupe. mic_nonce is unique across turns
    # AND across re-takes (it's reset on Begin call), so it makes a solid
    # idempotency key for window.parent.__capLastTurn.
    turn_id = f"l3_t{turn_idx}_n{st.session_state.l3_mic_nonce}"
    audio_file = render_voice_turn(
        ai_text=ai_text,
        mic_key=mic_key,
        speak=should_speak_now,
        turn_id=turn_id,
    )
    if should_speak_now:
        st.session_state[turn_spoken_key] = True

    st.markdown(
        '<div style="margin-top:18px;font-size:0.85rem;color:#94a3b8;">'
        "If anything goes wrong, you can press End call at any time. "
        "Your answers so far will still be assessed."
        "</div>",
        unsafe_allow_html=True,
    )
    if st.button("End call", key="l3_end_call"):
        st.session_state.l3_call_phase = "scoring"
        release_call_mic()
        st.rerun()
        return

    # Consume the recording (if any) exactly once. st.audio_input returns
    # the same UploadedFile on every rerun until the widget is rekeyed, so
    # we fingerprint by (file_id, size) and skip if we've seen this one.
    # Determine whether this render is the consuming pass: audio was
    # delivered and we haven't processed this fingerprint yet.
    is_consuming = False
    audio_bytes = None
    fingerprint = None
    if audio_file is not None:
        audio_bytes = audio_file.getvalue()
        fingerprint = (
            getattr(audio_file, "file_id", id(audio_file)),
            len(audio_bytes),
        )
        if st.session_state.l3_consumed_fingerprint != fingerprint:
            is_consuming = True

    # Fill the reserved status slot at the top with a pulse that matches
    # the actual state of the call right now.
    _render_status_pulse(status_slot, is_consuming=is_consuming)

    if not is_consuming:
        return

    st.session_state.l3_consumed_fingerprint = fingerprint
    _consume_turn_audio(comp_idx, phase, audio_bytes)


def _render_closing() -> None:
    ui.eyebrow("Call wrapping up")
    ui.page_title(
        "Thanks - that's the call",
        subtitle="The interviewer is signing off. Your answers are being scored now.",
    )

    # Speak the closer once.
    if not st.session_state.get("l3_closer_spoken"):
        render_silent_turn(RECRUITER_CLOSER)
        st.session_state.l3_closer_spoken = True

    # Auto-advance to scoring after ~7s so the closer has time to finish.
    if st_autorefresh is not None:
        st_autorefresh(interval=1000, key="l3_closing_tick")

    started_at = st.session_state.get("l3_closing_started_at") or time.time()
    if time.time() - started_at > 7.0:
        st.session_state.l3_call_phase = "scoring"
        release_call_mic()
        st.rerun()
        return

    with st.spinner("Wrapping up the call..."):
        time.sleep(0.5)  # small visual settle; the autorefresh drives advance


def _render_scoring() -> None:
    ui.eyebrow("Finalising")
    ui.page_title("Scoring your interview", subtitle="One moment - we are reviewing each competency against the rubric.")

    candidate_id = st.session_state.candidate_id
    questions = st.session_state.l3_main_questions or []
    if not questions:
        # Defensive: if the candidate ended the call before any questions
        # loaded, jump straight to done with zero score.
        st.session_state.l3_call_phase = "done"
        st.rerun()
        return

    with st.spinner("Scoring your responses..."):
        st.session_state.l3_answer_scores = []
        for comp_idx, comp in enumerate(questions):
            main_t = st.session_state.l3_main_transcripts.get(comp_idx, "")
            fu_obj = st.session_state.l3_followups.get(comp_idx) or {}
            fu_t = st.session_state.l3_followup_transcripts.get(comp_idx, "")

            result = score_competency(
                main_question=comp["question"],
                main_transcript=main_t,
                followup_question=fu_obj.get("question", ""),
                followup_transcript=fu_t,
                competency_name=comp["competency_name"],
                followup_goal=comp["followup_goal"],
            )

            main_dur = min(120.0, len(main_t.split()) / 2.5) if main_t else 0.0
            fu_dur = min(120.0, len(fu_t.split()) / 2.5) if fu_t else 0.0

            db.save_layer3_result(
                candidate_id=candidate_id,
                competency_order=comp_idx + 1,
                competency_id=comp["competency_id"],
                competency_key=comp["competency_key"],
                competency_name=comp["competency_name"],
                main_question=comp["question"],
                main_transcript=main_t,
                main_audio_duration_seconds=main_dur,
                followup_bucket=fu_obj.get("bucket"),
                followup_question=fu_obj.get("question"),
                followup_transcript=fu_t,
                followup_audio_duration_seconds=fu_dur,
                competency_score=result["score"],
                scripted_flag=result["scripted_flag"],
                rationale=result["rationale"],
            )

            st.session_state.l3_answer_scores.append({
                "competency_key": comp["competency_key"],
                "competency_id": comp["competency_id"],
                "score": result["score"],
                "scripted_flag": result["scripted_flag"],
            })

    st.session_state.l3_call_phase = "done"
    st.rerun()


def _render_done() -> None:
    ui.eyebrow("Interview complete")
    ui.page_title(
        "Thank you",
        subtitle="Your call has been recorded and assessed. On the next screen you'll see your full results.",
    )
    with ui.card(eyebrow_text="What happens next"):
        st.markdown(
            "Your responses are stored in your candidate record. Your full assessment "
            "across the three layers - cognitive, simulation, and this interview - "
            "is shown on the results screen."
        )
    if st.button("See my results", type="primary", use_container_width=True):
        advance_stage("results")


# ---------- helpers ----------

def _compose_ai_line(comp: dict, comp_idx: int, phase: str) -> str:
    """Build the exact string the AI speaks for a given turn.

    Main turn: opener (Q1 only) or transition (Q2..Q4) + the verbatim
    question from interview_questions.json.

    Follow-up turn: a short acknowledgement + the LLM-generated follow-up
    question already stashed for this competency. If the LLM tagged the
    follow-up as bucket "E" (RE-ASK), the candidate clearly didn't engage
    with the question (greeting, asked the AI a question back, off-topic
    response), and we swap the normal acknowledgement for a short
    reassurance and the verbatim original question.
    """
    if phase == "main":
        if comp_idx == 0:
            return RECRUITER_OPENER + " " + comp["question"]
        return transition_line(comp_idx) + " " + comp["question"]
    fu_obj = st.session_state.l3_followups.get(comp_idx) or {}
    fu_text = fu_obj.get("question") or "Can you tell me a bit more about that?"
    if str(fu_obj.get("bucket", "")).upper() == "E":
        return "Yes, I can hear you. Let me ask that again. " + fu_text
    return acknowledge_line(comp_idx) + " " + fu_text


def _consume_turn_audio(comp_idx: int, phase: str, audio_bytes: bytes) -> None:
    """Transcribe the audio, stash it in the right slot, advance the turn."""
    # The visible spinner text + the amber status pulse together make
    # the otherwise-silent 8-15s wait feel intentional.
    try:
        with st.spinner("Reviewing your answer..."):
            transcript = transcribe_audio(audio_bytes, filename="turn.wav")
    except Exception as exc:
        # Transcription failure: stash a placeholder so scoring can still run
        # against the rest of the call. Log via st.toast (non-intrusive).
        transcript = ""
        try:
            st.toast(f"Couldn't transcribe one of your answers ({type(exc).__name__}). Continuing.", icon="!")
        except Exception:
            pass

    transcript = (transcript or "").strip()

    if phase == "main":
        st.session_state.l3_main_transcripts[comp_idx] = transcript
        # Generate the follow-up question now, in time for the next turn.
        comp = st.session_state.l3_main_questions[comp_idx]
        with st.spinner("Thinking about a follow-up..."):
            try:
                fu = generate_followup(
                    main_question=comp["question"],
                    transcript=transcript,
                    competency_name=comp["competency_name"],
                    followup_goal=comp["followup_goal"],
                )
            except Exception:
                fu = {"bucket": "A", "question": "Can you walk me through exactly what you personally did?"}
        st.session_state.l3_followups[comp_idx] = fu
    else:
        st.session_state.l3_followup_transcripts[comp_idx] = transcript

    st.session_state.l3_turn_idx = st.session_state.l3_turn_idx + 1
    st.session_state.l3_mic_nonce = st.session_state.l3_mic_nonce + 1
    st.session_state.l3_consumed_fingerprint = None
    st.session_state.l3_question_started_at = time.time()
    st.rerun()


def _render_status_pulse(slot, *, is_consuming: bool) -> None:
    """Fill the status slot with the right pulse for the current state.

    is_consuming=False -> red 'Live call' pulse, candidate's turn to talk
                          or the AI is speaking.
    is_consuming=True  -> amber 'Reviewing your answer' pulse, system is
                          transcribing + asking the LLM for the next line.
                          Keeps the candidate from staring at a silent
                          page during the 8-15s wait.
    """
    if is_consuming:
        color = "#FEB100"  # amber from the design tokens
        rgba = "rgba(254,177,0,0.7)"
        rgba_zero = "rgba(254,177,0,0)"
        text = "Reviewing your answer - one moment"
    else:
        color = "#FF816E"
        rgba = "rgba(255,129,110,0.7)"
        rgba_zero = "rgba(255,129,110,0)"
        text = "Live call - microphone hands-free"

    html = (
        '<div style="display:flex;align-items:center;gap:12px;margin:18px 0 8px 0;">'
        f'<span style="width:10px;height:10px;border-radius:50%;background:{color};'
        f'box-shadow:0 0 0 0 {rgba};animation:cap-pulse 1.6s infinite ease-out;"></span>'
        '<span style="font-size:0.95rem;letter-spacing:0.04em;text-transform:uppercase;color:#94a3b8;">'
        f'{text}</span></div>'
        f"<style>@keyframes cap-pulse{{0%{{box-shadow:0 0 0 0 {rgba};}}"
        f"70%{{box-shadow:0 0 0 14px {rgba_zero};}}"
        f"100%{{box-shadow:0 0 0 0 {rgba_zero};}}}}</style>"
    )
    slot.markdown(html, unsafe_allow_html=True)
