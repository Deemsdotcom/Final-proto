"""Candidate-facing post-submission screen.

Shows the candidate their results: overall + per-layer metrics, a bar
chart of the three layers, a competency radar, and AI-generated
developmental feedback. Top Fit classification and per-question / per-
week / per-transcript drill-downs are hidden - those are recruiter-only.

Performance: base numeric scores (overall, layers, competencies) are
computed and saved synchronously in well under a second, so the
candidate sees their scores and charts immediately. The AI-generated
feedback runs after the page has already rendered, displayed below
the charts with a small spinner while it loads. The candidate is
NOT blocked waiting for the LLM call.
"""

from __future__ import annotations

import streamlit as st
import plotly.graph_objects as go

from assessment_logic.layer1_logic import aggregate_layer1
from assessment_logic.layer2_logic import aggregate_layer2
from assessment_logic.layer3_logic import aggregate_layer3
from assessment_logic.scoring_matrix import assemble_final_scores
from database import db

from . import _design as ui


def render() -> None:
    candidate_id = st.session_state.candidate_id

    # Fast path: compute and save the numeric scores synchronously.
    # Sub-second, no LLM calls. This is what makes the candidate's
    # scores + charts available right away below.
    existing = db.get_final_score(candidate_id)
    if not existing and not st.session_state.get("final_result_computed"):
        with st.spinner("Saving your responses..."):
            _save_base_scores_fast(candidate_id)
        st.session_state.final_result_computed = True
        existing = db.get_final_score(candidate_id)

    if not existing:
        ui.inject_global_styles()
        ui.header()
        st.error(
            "We couldn't load your results. Please reach out to the "
            "recruitment team - your responses are still safely stored."
        )
        return

    _render_candidate_view(existing)

    # Deferred LLM summary (recruiter-facing). Runs AFTER the candidate
    # view has rendered so it never blocks the candidate.
    if not st.session_state.get("l3_llm_summaries_attempted"):
        st.session_state.l3_llm_summaries_attempted = True
        _generate_llm_summaries_lazy(candidate_id)


# ============================================================
# Fast scoring + persistence
# ============================================================

def _save_base_scores_fast(candidate_id: str) -> None:
    """Compute base scores from the persisted DB rows and save them. Fast.

    No LLM calls. The recruiter_summary and candidate_feedback fields are
    seeded with empty strings here so the row exists and the recruiter
    dashboard can read it immediately. The feedback strings get
    backfilled later by _generate_llm_summaries_lazy and (on the
    candidate side) by _render_developmental_feedback.
    """
    import sys

    # Layer 1: recompute from DB.
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

    # AI-use flags from session state.
    ai_flags = {
        "ai_flag_logical":   int(bool(st.session_state.get("l1_ai_flag_logical", False))),
        "ai_flag_numerical": int(bool(st.session_state.get("l1_ai_flag_numerical", False))),
        "ai_flag_verbal":    int(bool(st.session_state.get("l1_ai_flag_verbal", False))),
        "ai_flag_layer2":    int(bool(st.session_state.get("l2_ai_flag", False))),
    }

    # Tech-issue skip on Layer 3.
    skip_reason = st.session_state.get("l3_skip_reason") or ""

    # ---- DIAGNOSTIC LOGGING ----
    # If a candidate ends up with 0 on every layer despite their
    # current_stage having advanced, something silently dropped data
    # (typical causes: a redeploy mid-flow that wiped session state,
    # an aggressive resume_from_db that nuked layer rows, the nav
    # bar being used to jump past layers). Log loudly to stderr so
    # we can spot the next occurrence.
    print(
        "[final_scores] candidate=" + str(candidate_id)[:8]
        + " l1_rows=" + str(len(l1_rows))
        + " l2_sim=" + ("yes" if l2_sim else "no")
        + " l3_rows=" + str(len(l3_rows))
        + " -> layer1=" + str(round(layer1, 1))
        + " layer2=" + str(round(layer2, 1))
        + " layer3=" + str(round(layer3, 1))
        + " skip=" + ("yes" if skip_reason else "no"),
        file=sys.stderr,
    )
    if layer1 == 0 and layer2 == 0 and layer3 == 0 and not skip_reason:
        print(
            "[final_scores] WARNING: candidate=" + str(candidate_id)[:8]
            + " saved with zero on every layer. Likely cause: data "
            + "wiped by mid-flow redeploy or resume_from_db. Investigate.",
            file=sys.stderr,
        )

    draft = assemble_final_scores(
        candidate_id=candidate_id,
        layer1=layer1, layer2=layer2, layer3=layer3,
        l1_comp=l1_comp, l2_comp=l2_comp, l3_comp=l3_comp,
        candidate_feedback="",
        recruiter_summary="",
        ai_flags=ai_flags,
        layer3_skipped=bool(skip_reason),
        layer3_skip_reason=skip_reason,
    )
    db.save_final_score(draft)
    db.mark_complete(candidate_id)


def _generate_llm_summaries_lazy(candidate_id: str) -> None:
    """Best-effort LLM generation that runs after the candidate page renders."""
    try:
        existing = db.get_final_score(candidate_id)
        if not existing:
            return
        if existing.get("candidate_feedback") and existing.get("recruiter_summary"):
            return
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
        pass


# ============================================================
# Candidate-facing UI (per the slide spec)
# ============================================================

def _render_candidate_view(scores: dict) -> None:
    ui.inject_global_styles()
    ui.header(meta=f"Candidate {st.session_state.candidate_name}")

    first_name = (st.session_state.candidate_name or "").split()[0] if st.session_state.candidate_name else ""
    subtitle = (
        f"Thanks for completing the assessment, {first_name}. Here is how it went."
    ) if first_name else "Thanks for completing the assessment. Here is how it went."

    ui.eyebrow("Assessment complete")
    ui.page_title("Your assessment results", subtitle)

    # ── Score metrics ────────────────────────────────────────────────
    # Layer 3 display:
    #   • full skip (0 of 4 answered) → SKIPPED + "tech issues"
    #   • partial skip (1-3 of 4 answered) → score + "partly skipped (N)"
    #   • no skip flag → score as normal
    skipped = bool(scores.get("layer3_skipped"))
    l3_answered = db.count_layer3_main_answers(scores["candidate_id"]) if skipped else 4
    l3_unanswered = 4 - l3_answered
    partial_skip = skipped and l3_answered > 0
    full_skip = skipped and l3_answered == 0

    cols = st.columns(4)
    cols[0].metric("Overall", f"{(scores.get('overall_score') or 0):.0f}")
    cols[1].metric("Layer 1 (Cognitive)", f"{(scores.get('layer1_score') or 0):.0f}")
    cols[2].metric("Layer 2 (Simulation)", f"{(scores.get('layer2_score') or 0):.0f}")
    if full_skip:
        cols[3].metric(
            "Layer 3 (Interview)", "SKIPPED",
            delta="tech issues", delta_color="off",
        )
    elif partial_skip:
        cols[3].metric(
            "Layer 3 (Interview)", f"{(scores.get('layer3_score') or 0):.0f}",
            delta=f"partly skipped ({l3_unanswered} unanswered)",
            delta_color="off",
        )
    else:
        cols[3].metric(
            "Layer 3 (Interview)",
            f"{(scores.get('layer3_score') or 0):.0f}",
        )

    if full_skip:
        ui.info_banner(
            "Layer 3 was skipped at your request due to technical issues. "
            "A member of the recruitment team will follow up.",
            icon="i",
        )
    elif partial_skip:
        ui.info_banner(
            f"Layer 3 was partly skipped at your request due to "
            f"technical issues. {l3_answered} of 4 competencies were "
            f"completed; the remaining {l3_unanswered} were not "
            f"answered and counted as 0.",
            icon="i",
        )

    st.markdown("<div style='height:0.6rem'></div>", unsafe_allow_html=True)

    # ── Bar chart: three layer scores ────────────────────────────────
    with ui.card("Layer breakdown"):
        bar = go.Figure()
        bar_x = ["Layer 1 (Cognitive)", "Layer 2 (Simulation)", "Layer 3 (Interview)"]
        l3_val = 0 if skipped else float(scores.get("layer3_score") or 0)
        bar_y = [
            float(scores.get("layer1_score") or 0),
            float(scores.get("layer2_score") or 0),
            l3_val,
        ]
        bar.add_trace(go.Bar(
            x=bar_x,
            y=bar_y,
            marker_color=["#0058AB", "#1DB8F2", "#00D5D0"],
            text=[f"{v:.0f}" for v in bar_y],
            textposition="auto",
        ))
        bar.update_layout(
            yaxis_range=[0, 100],
            yaxis_title="Score (0-100)",
            height=320,
            margin=dict(t=20, b=20, l=20, r=20),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#cbd5e1"),
        )
        st.plotly_chart(bar, use_container_width=True)

    # ── Competency radar ─────────────────────────────────────────────
    with ui.card("Competency profile"):
        # Mirror the recruiter dashboard's dimensions so the candidate
        # sees the same competency space (just without the Top Fit flag
        # and the drill-downs).
        comp_labels = [
            "Analytical", "Numerical", "Verbal",
            "Strategic", "Adaptability (sim)",
            "Growth mindset", "Adaptability (interview)",
            "Collaboration", "Self-reflection",
        ]
        legacy_growth = (
            scores.get("competency_l3_proactivity")
            or scores.get("competency_l3_learning_mindset")
            or 0
        )
        growth_val = (
            scores.get("competency_l3_growth_mindset")
            or scores.get("competency_l3_growth_driven_mindset")
            or legacy_growth
            or 0
        )
        comp_values = [
            float(scores.get("competency_analytical") or 0),
            float(scores.get("competency_numerical") or 0),
            float(scores.get("competency_verbal") or 0),
            float(scores.get("competency_strategic") or 0),
            float(scores.get("competency_adaptability") or 0),
            float(growth_val),
            float(scores.get("competency_l3_adaptability") or 0),
            float(scores.get("competency_l3_collaboration") or 0),
            float(scores.get("competency_l3_self_reflection") or 0),
        ]
        radar = go.Figure()
        radar.add_trace(go.Scatterpolar(
            r=comp_values + [comp_values[0]],
            theta=comp_labels + [comp_labels[0]],
            fill="toself",
            line_color="#1DB8F2",
            fillcolor="rgba(29,184,242,0.25)",
            name="You",
        ))
        radar.update_layout(
            polar=dict(
                bgcolor="rgba(0,0,0,0)",
                radialaxis=dict(range=[0, 100], visible=True, gridcolor="#28387A"),
                angularaxis=dict(gridcolor="#28387A"),
            ),
            showlegend=False,
            height=420,
            margin=dict(t=30, b=20, l=40, r=40),
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#cbd5e1"),
        )
        st.plotly_chart(radar, use_container_width=True)

    # ── Developmental feedback ───────────────────────────────────────
    _render_developmental_feedback(scores)

    # ── Footer ───────────────────────────────────────────────────────
    st.markdown("<div style='height:0.8rem'></div>", unsafe_allow_html=True)
    ui.info_banner(
        "Your results have been recorded. A member of the recruitment team "
        "will be in touch about next steps.",
        icon="i",
    )


def _render_developmental_feedback(scores: dict) -> None:
    """Render the AI-generated developmental feedback section.

    If feedback is already cached on the row, render it immediately.
    If not, generate it now with a small spinner so the candidate sees
    a clear loading state for just this section (other sections above
    have already rendered, so there's no global wait).
    """
    with ui.card("Your developmental feedback"):
        cf = (scores.get("candidate_feedback") or "").strip()
        if not cf:
            with st.spinner("Preparing your personalised feedback..."):
                try:
                    from assessment_logic.feedback_generator import (
                        _strip_code_fences,
                        generate_candidate_feedback,
                    )
                    cf = generate_candidate_feedback(dict(scores))
                    # Cache it back so a refresh doesn't regenerate.
                    if cf:
                        row = dict(scores)
                        row["candidate_feedback"] = cf
                        try:
                            db.save_final_score(row)
                        except Exception:
                            pass
                except Exception:
                    cf = (
                        "We couldn't generate your developmental feedback "
                        "right now. Your scores above are still your full "
                        "result; a member of the recruitment team will "
                        "follow up directly."
                    )
        # Strip any leading/trailing ```markdown ... ``` the LLM may have
        # wrapped the answer in.
        try:
            from assessment_logic.feedback_generator import _strip_code_fences
            cf = _strip_code_fences(cf)
        except Exception:
            pass
        st.markdown(cf or "_(feedback unavailable)_")
