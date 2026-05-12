"""Candidate-facing post-submission screen.

The candidate sees a minimal "Thanks for the submission" page - no scores,
no radar, no LLM-generated feedback. All those things are still computed
and saved to the database for the recruiter dashboard; they're just not
surfaced to the candidate.

We split the persistence work in two:

1. _save_base_scores_fast: pure number-crunching off the existing DB
   rows. No LLM calls. Runs synchronously while the candidate is shown
   a one-line spinner. Takes well under a second on any normal load.

2. _generate_llm_summaries_lazy: the two LLM calls
   (generate_candidate_feedback + generate_recruiter_summary) needed for
   the recruiter dashboard. They run AFTER the thank-you screen has
   rendered, so the candidate isn't blocked. If they fail or are slow,
   the candidate has already moved on. The recruiter dashboard handles
   missing summaries gracefully and can also regenerate them on demand.
"""

from __future__ import annotations

import streamlit as st

from assessment_logic.layer1_logic import aggregate_layer1
from assessment_logic.layer2_logic import aggregate_layer2
from assessment_logic.layer3_logic import aggregate_layer3
from assessment_logic.scoring_matrix import assemble_final_scores
from database import db

from . import _design as ui


def render() -> None:
    candidate_id = st.session_state.candidate_id

    # Fast path: compute and save the numeric scores synchronously. This
    # is what unblocks the recruiter dashboard right away. No LLM calls
    # here, so we're talking sub-second.
    existing = db.get_final_score(candidate_id)
    if not existing and not st.session_state.get("final_result_computed"):
        with st.spinner("Saving your responses..."):
            _save_base_scores_fast(candidate_id)
        st.session_state.final_result_computed = True

    # Render the thank-you screen right now so the candidate isn't waiting.
    _render_thank_you()

    # Deferred LLM summaries. Runs AFTER the thank-you screen has
    # appeared. Wrapped in try/except so a slow or failed call never
    # bubbles up into the candidate UI. Caches via session_state so we
    # only attempt it once per session.
    if not st.session_state.get("l3_llm_summaries_attempted"):
        st.session_state.l3_llm_summaries_attempted = True
        _generate_llm_summaries_lazy(candidate_id)


def _save_base_scores_fast(candidate_id: str) -> None:
    """Compute base scores from the persisted DB rows and save them. Fast.

    No LLM calls. The recruiter_summary and candidate_feedback fields are
    seeded with empty strings here so the row exists and the recruiter
    dashboard can read it immediately. The feedback strings get
    backfilled later by _generate_llm_summaries_lazy (or by the
    recruiter dashboard on demand if that backfill fails).
    """
    # Layer 1: recompute from DB in case session state is stale.
    l1_rows = db.get_layer1_results(candidate_id)
    theme_totals = {"logical": [0, 0], "numerical": [0, 0], "verbal": [0, 0]}
    for r in l1_rows:
        theme_totals[r["theme"]][0] += 1
        theme_totals[r["theme"]][1] += int(r["is_correct"])
    theme_scores = {
        t: (correct / total * 100) if total > 0 else 0
        for t, (total, correct) in theme_totals.items()
    }
    layer1, l1_comp = aggregate_layer1(theme_scores)

    # Layer 2: rehydrate the simulation final state to compute competencies.
    l2_sim = db.get_layer2_simulation(candidate_id)
    if l2_sim:
        import json
        from assessment_logic.layer2_logic import load_scenario
        final_state = json.loads(l2_sim["final_state_json"])
        scenario = load_scenario()
        layer2, l2_comp = aggregate_layer2(final_state, scenario)
    else:
        layer2 = 0.0
        l2_comp = {"competency_strategic": 0.0, "competency_adaptability": 0.0}

    # Layer 3
    l3_rows = db.get_layer3_results(candidate_id)
    competency_scores = [
        {
            "competency_key": r["competency_key"],
            "competency_id": r["competency_id"],
            "score": r["competency_score"] if r["competency_score"] is not None else 0,
        } for r in l3_rows
    ]
    layer3, l3_comp = aggregate_layer3(competency_scores)

    # AI-use flags from session state (set by Layer 1 finish and Layer 2 finalize).
    ai_flags = {
        "ai_flag_logical":   int(bool(st.session_state.get("l1_ai_flag_logical", False))),
        "ai_flag_numerical": int(bool(st.session_state.get("l1_ai_flag_numerical", False))),
        "ai_flag_verbal":    int(bool(st.session_state.get("l1_ai_flag_verbal", False))),
        "ai_flag_layer2":    int(bool(st.session_state.get("l2_ai_flag", False))),
    }

    # Forward the "I have technical issues" skip from session_state if the
    # candidate hit the escape on the Layer 3 in-call screen. The reason
    # text is shown verbatim in the recruiter dashboard.
    skip_reason = st.session_state.get("l3_skip_reason") or ""

    draft = assemble_final_scores(
        candidate_id=candidate_id,
        layer1=layer1, layer2=layer2, layer3=layer3,
        l1_comp=l1_comp, l2_comp=l2_comp, l3_comp=l3_comp,
        candidate_feedback="",  # filled later by lazy LLM path
        recruiter_summary="",   # filled later by lazy LLM path
        ai_flags=ai_flags,
        layer3_skipped=bool(skip_reason),
        layer3_skip_reason=skip_reason,
    )
    db.save_final_score(draft)
    db.mark_complete(candidate_id)


def _generate_llm_summaries_lazy(candidate_id: str) -> None:
    """Best-effort LLM generation that runs after the thank-you screen.

    Runs synchronously but only AFTER the thank-you UI has rendered, so
    the candidate sees the confirmation immediately. If it fails or is
    slow, the candidate is already done. The recruiter dashboard reads
    these fields and degrades gracefully if they're empty.
    """
    try:
        existing = db.get_final_score(candidate_id)
        if not existing:
            return
        if existing.get("candidate_feedback") and existing.get("recruiter_summary"):
            # Already generated (likely a re-render of the results page).
            return
        # Import lazily so the candidate page isn't held back by import
        # cost on the fast path.
        from assessment_logic.feedback_generator import (
            generate_candidate_feedback,
            generate_recruiter_summary,
        )
        cf = existing.get("candidate_feedback") or ""
        rs = existing.get("recruiter_summary") or ""
        if not cf:
            try:
                cf = generate_candidate_feedback(dict(existing))
            except Exception:
                cf = ""
        if not rs:
            try:
                rs = generate_recruiter_summary(dict(existing))
            except Exception:
                rs = ""
        if cf or rs:
            row = dict(existing)
            row["candidate_feedback"] = cf or row.get("candidate_feedback") or ""
            row["recruiter_summary"] = rs or row.get("recruiter_summary") or ""
            db.save_final_score(row)
    except Exception:
        # Never let this path bubble up into the candidate UI.
        pass


def _render_thank_you() -> None:
    """The only thing the candidate ever sees on this screen."""
    ui.inject_global_styles()
    ui.header(meta=f"Candidate {st.session_state.candidate_name}")

    first_name = (st.session_state.candidate_name or "").split()[0] if st.session_state.candidate_name else ""
    subtitle = (
        f"Thanks for completing the assessment, {first_name}. "
        "A member of the recruitment team will be in touch with next steps."
    ) if first_name else (
        "Thanks for completing the assessment. "
        "A member of the recruitment team will be in touch with next steps."
    )

    ui.eyebrow("Submission received")
    ui.page_title("You're done.", subtitle)

    with ui.card("What happens next"):
        st.markdown(
            "Your responses have been recorded across all three layers - cognitive, "
            "simulation, and interview. A recruiter will review them and contact you "
            "directly about the next steps. You can close this page now."
        )
