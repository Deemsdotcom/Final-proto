"""Recruiter dashboard: overview table, filters, stats, and per-candidate deep-dive."""

from __future__ import annotations

import json
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from database import db


# Filter widget keys (explicit so the Reset button can clear them).
FILTER_KEYS = [
    "recruiter_min_overall",
    "recruiter_min_l1",
    "recruiter_min_l2",
    "recruiter_min_l3",
    "recruiter_name_search",
    "recruiter_top_fit_only",
    "recruiter_date_range",
]


def _compute_ai_risk(row: dict) -> dict:
    """Count AI risk signals and classify the overall tier.

    Five signal sources are watched:
      - L1 logical theme flag (fast + accurate)
      - L1 numerical theme flag (fast + accurate)
      - L1 verbal theme flag (fast + accurate)
      - L2 simulation flag (fast + accurate)
      - L3 tech-issue skip (candidate flagged a tech issue mid-call)

    Tier rules:
      - 0 signals → tier "none"
      - 1 signal → tier "single" (informational only)
      - 2 signals → tier "probable" (amber banner)
      - 3+ signals → tier "definite" (red banner)
    """
    l1_themes = []
    if int(row.get("ai_flag_logical") or 0):
        l1_themes.append("logical")
    if int(row.get("ai_flag_numerical") or 0):
        l1_themes.append("numerical")
    if int(row.get("ai_flag_verbal") or 0):
        l1_themes.append("verbal")
    l2_flag = bool(int(row.get("ai_flag_layer2") or 0))
    l3_skip = bool(int(row.get("layer3_skipped") or 0))

    count = len(l1_themes) + (1 if l2_flag else 0) + (1 if l3_skip else 0)

    if count >= 3:
        tier = "definite"
        label = "Definite AI usage"
    elif count == 2:
        tier = "probable"
        label = "Probable AI usage"
    elif count == 1:
        tier = "single"
        label = "Possible AI use"
    else:
        tier = "none"
        label = ""

    # Compact breakdown string used in the table cell and detail banner.
    parts = []
    if l1_themes:
        parts.append("L1 " + "+".join(l1_themes))
    if l2_flag:
        parts.append("L2")
    if l3_skip:
        parts.append("L3 tech-issue skip")
    breakdown = ", ".join(parts)

    return {
        "count": count,
        "tier": tier,
        "label": label,
        "breakdown": breakdown,
    }


def _format_ai_flags(row: dict) -> str:
    """Build the 'Possible AI use' cell string for the candidate table.

    Empty (\"-\") when no signals. One signal renders the breakdown
    only. Two signals renders \"Probable · <breakdown>\". Three or
    more renders \"Definite · <breakdown>\". The L3 tech-issue skip
    counts as a signal alongside the four classic AI flags.
    """
    risk = _compute_ai_risk(row)
    if risk["count"] == 0:
        return "-"
    if risk["tier"] in ("probable", "definite"):
        return f"{risk['label']} · {risk['breakdown']}"
    return risk["breakdown"]


def render() -> None:
    st.title("Recruiter Dashboard")
    st.caption("Review completed candidate assessments, filter by score, and export.")

    # --- Load data ---
    rows = db.get_all_completed_candidates()
    if not rows:
        st.info("No completed assessments yet. Candidates will appear here once they finish.")
        return

    df = pd.DataFrame(rows)
    df["completed_at_dt"] = pd.to_datetime(df["completed_at"])

    # --- Sidebar filters ---
    with st.sidebar:
        st.header("Filters")
        min_overall = st.slider(
            "Min overall score", 0, 100, 0, key="recruiter_min_overall",
        )
        min_l1 = st.slider(
            "Min Layer 1 score", 0, 100, 0, key="recruiter_min_l1",
        )
        min_l2 = st.slider(
            "Min Layer 2 score", 0, 100, 0, key="recruiter_min_l2",
        )
        min_l3 = st.slider(
            "Min Layer 3 score", 0, 100, 0, key="recruiter_min_l3",
        )

        if not df.empty:
            date_min = df["completed_at_dt"].min().date()
            date_max = df["completed_at_dt"].max().date()
            date_range = st.date_input(
                "Completed between",
                value=(date_min, date_max),
                min_value=date_min, max_value=date_max,
                key="recruiter_date_range",
            )
        else:
            date_range = None

        name_search = st.text_input(
            "Name contains", "", key="recruiter_name_search",
        )
        top_fit_only = st.checkbox(
            "Top Fit only", key="recruiter_top_fit_only",
        )

        if st.button("Reset filters"):
            for k in FILTER_KEYS:
                if k in st.session_state:
                    del st.session_state[k]
            st.rerun()

    # --- Apply filters ---
    filtered = df.copy()
    filtered = filtered[filtered["overall_score"] >= min_overall]
    filtered = filtered[filtered["layer1_score"] >= min_l1]
    filtered = filtered[filtered["layer2_score"] >= min_l2]
    filtered = filtered[filtered["layer3_score"] >= min_l3]
    if name_search:
        filtered = filtered[filtered["full_name"].str.contains(name_search, case=False, na=False)]
    if top_fit_only:
        filtered = filtered[filtered["top_fit"] == 1]
    if date_range and isinstance(date_range, tuple) and len(date_range) == 2:
        start, end = date_range
        filtered = filtered[
            (filtered["completed_at_dt"].dt.date >= start)
            & (filtered["completed_at_dt"].dt.date <= end)
        ]

    # --- Summary stats ---
    st.subheader("At a glance")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Candidates assessed", len(df))
    c2.metric("In current view", len(filtered))
    c3.metric("Top Fit (in view)", int(filtered["top_fit"].sum()))
    avg_score = filtered["overall_score"].mean() if len(filtered) > 0 else 0
    c4.metric("Avg overall (in view)", f"{avg_score:.1f}")

    # Score distribution histogram
    if len(filtered) > 0:
        hist = px.histogram(
            filtered, x="overall_score", nbins=20,
            title="Overall score distribution",
            labels={"overall_score": "Overall score"},
        )
        hist.update_layout(height=280, margin=dict(t=40, b=20))
        st.plotly_chart(hist, use_container_width=True)

    st.divider()

    # --- Overview table ---
    st.subheader("Candidates")
    table_rows = []
    for _, row in filtered.iterrows():
        typed_fallback_count = db.count_layer3_typed_fallback(row["candidate_id"])
        if typed_fallback_count > 0:
            typed_fallback_cell = f"🛠 {typed_fallback_count}/4"
        else:
            typed_fallback_cell = "-"
        table_rows.append({
            "Name": row["full_name"],
            "Email": row["email"],
            "Completed": pd.to_datetime(row["completed_at"]).strftime("%Y-%m-%d %H:%M"),
            "Layer 1": round(float(row["layer1_score"] or 0), 1),
            "Layer 2": round(float(row["layer2_score"] or 0), 1),
            "Layer 3": round(float(row["layer3_score"] or 0), 1),
            "Overall": round(float(row["overall_score"] or 0), 1),
            "Possible AI use": _format_ai_flags(row.to_dict()),
            "L3 typed fallback": typed_fallback_cell,
            "Top Fit": "✓" if row["top_fit"] == 1 else "-",
        })
    display_df = pd.DataFrame(table_rows, columns=[
        "Name", "Email", "Completed", "Layer 1", "Layer 2", "Layer 3",
        "Overall", "Possible AI use", "L3 typed fallback", "Top Fit",
    ])

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        height=350,
    )

    # --- Export ---
    if len(filtered) > 0:
        csv = filtered.drop(columns=["completed_at_dt"]).to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 Export filtered candidates to CSV",
            data=csv,
            file_name=f"candidates_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
        )

    st.divider()

    # --- Individual deep-dive ---
    st.subheader("Individual deep-dive")
    if len(filtered) == 0:
        st.info("No candidates match the current filters.")
        return

    options = {
        f"{row['full_name']} ({row['email']}): Overall {row['overall_score']:.0f}": row["candidate_id"]
        for _, row in filtered.iterrows()
    }
    chosen_label = st.selectbox("Select a candidate", options=list(options.keys()))
    chosen_id = options[chosen_label]

    _render_deep_dive(chosen_id)


def _render_deep_dive(candidate_id: str) -> None:
    candidate = db.get_candidate(candidate_id)
    scores = db.get_final_score(candidate_id)
    if not candidate or not scores:
        st.error("Candidate data not found.")
        return

    st.markdown(f"### {candidate['full_name']}")
    st.caption(
        f"{candidate['email']} · Started {candidate['started_at'][:10]} · "
        f"Completed {candidate['completed_at'][:10] if candidate['completed_at'] else '-'}"
    )

    # Top Fit badge (v7: single rule, overall >= 70)
    if scores["top_fit"]:
        st.success("✓ **Top Fit**: Overall score ≥ 70")
    else:
        st.warning("Not flagged as Top Fit")

    # Score summary
    cols = st.columns(4)
    cols[0].metric("Overall", f"{scores['overall_score']:.1f}")
    cols[1].metric("Layer 1", f"{scores['layer1_score']:.1f}")
    cols[2].metric("Layer 2", f"{scores['layer2_score']:.1f}")
    # Layer 3 metric carries a tech-issue badge if the candidate skipped
    # the interview via the in-call "I'm having technical issues" escape.
    if scores.get("layer3_skipped"):
        cols[3].metric("Layer 3", "SKIPPED", delta="tech issues", delta_color="off")
    else:
        cols[3].metric("Layer 3", f"{scores['layer3_score']:.1f}")

    # AI-risk banner. Tiered by signal count (see _compute_ai_risk):
    # 1 signal renders an amber "Possible" note, 2 an amber "Probable",
    # 3+ a red "Definite". The L3 tech-issue skip is counted as a
    # signal alongside the four classic AI flags.
    risk = _compute_ai_risk(scores)
    if risk["tier"] == "definite":
        st.error(
            f"🚩 **Definite AI usage** · {risk['count']} signals tripped · "
            f"{risk['breakdown']}"
        )
    elif risk["tier"] == "probable":
        st.warning(
            f"⚠️ **Probable AI usage** · {risk['count']} signals tripped · "
            f"{risk['breakdown']}"
        )
    elif risk["tier"] == "single":
        st.warning(
            f"⚠️ Possible AI use flagged: **{risk['breakdown']}** "
            f"(informational only)"
        )

    # Competency radar (v7: 4 L3 axes)
    comp_labels = [
        "Analytical", "Numerical", "Verbal",
        "Strategic", "Adaptability (sim)",
        "Growth Mindset", "Adaptability (interview)",
        "Collaboration", "Self-Reflection",
    ]
    comp_values = [
        scores.get("competency_analytical") or 0,
        scores.get("competency_numerical") or 0,
        scores.get("competency_verbal") or 0,
        scores.get("competency_strategic") or 0,
        scores.get("competency_adaptability") or 0,
        scores.get("competency_l3_growth_mindset") or 0,
        scores.get("competency_l3_adaptability") or 0,
        scores.get("competency_l3_collaboration") or 0,
        scores.get("competency_l3_self_reflection") or 0,
    ]
    radar = go.Figure()
    radar.add_trace(go.Scatterpolar(
        r=comp_values + [comp_values[0]],
        theta=comp_labels + [comp_labels[0]],
        fill="toself",
        line_color="#6366F1",
    ))
    radar.update_layout(
        polar=dict(radialaxis=dict(range=[0, 100], visible=True)),
        showlegend=False, height=380, margin=dict(t=20, b=20),
    )
    st.plotly_chart(radar, use_container_width=True)

    # Recruiter summary (LLM-generated)
    st.markdown("#### Recruiter summary")
    if scores.get("recruiter_summary"):
        st.markdown(scores["recruiter_summary"])
    else:
        st.info("No recruiter summary generated yet.")

    # Layer 1 detail
    with st.expander("Layer 1: Question-by-question detail"):
        l1_rows = db.get_layer1_results(candidate_id)
        if l1_rows:
            df1 = pd.DataFrame([{
                "Theme": r["theme"],
                "Question ID": r["question_id"],
                "Question": (r["question_text"] or "")[:80] + "...",
                "Candidate's Answer": r["candidate_answer"] or "-",
                "Correct": r["correct_option"],
                "✓": "✓" if r["is_correct"] else "✗",
                "Time (s)": r["time_taken_seconds"],
            } for r in l1_rows])
            st.dataframe(df1, use_container_width=True, hide_index=True)
        else:
            st.write("No Layer 1 data.")

    # Layer 2 detail
    with st.expander("Layer 2: Firm simulation detail"):
        l2_sim = db.get_layer2_simulation(candidate_id)
        if not l2_sim:
            st.write("No Layer 2 data.")
        else:
            sc1, sc2, sc3, sc4 = st.columns(4)
            sc1.metric("Outcome score", f"{l2_sim['outcome_score']:.0f}")
            sc2.metric("Process score", f"{l2_sim['process_score']:.0f}")
            sc3.metric("Layer 2 total", f"{l2_sim['layer2_total']:.0f}")
            sc4.metric("Weeks played", l2_sim['weeks_played'])

            kc1, kc2, kc3, kc4 = st.columns(4)
            kc1.metric("Final cash", f"€{l2_sim['final_cash']:,.0f}")
            kc2.metric("Final reputation", f"{l2_sim['final_reputation']:.0f}/100")
            kc3.metric("Projects completed", l2_sim["projects_completed"])
            kc4.metric("Projects failed", l2_sim["projects_cancelled"])

            if l2_sim.get("tradeoff_choice"):
                st.markdown(f"**Week 6 trade-off:** Option **{l2_sim['tradeoff_choice']}**")
            else:
                st.markdown("*No trade-off decision recorded (didn't reach Week 6 or didn't choose).*")

            try:
                final_state = json.loads(l2_sim["final_state_json"])
                decisions = final_state.get("decision_choices", {})
                for did, choice in decisions.items():
                    st.markdown(f"**Week 2 decision ({did}):** chose **{choice}**")
            except (json.JSONDecodeError, TypeError, KeyError):
                pass

            st.markdown("**Week-by-week log:**")
            try:
                weekly_log = json.loads(l2_sim["weekly_log_json"])
            except (json.JSONDecodeError, TypeError):
                weekly_log = []

            for log in weekly_log:
                st.markdown(f"---\n**Week {log.get('week', '?')}**")
                cc1, cc2 = st.columns(2)
                cc1.markdown(f"*Cash change:* €{log.get('cash_change', 0):,.0f}")
                cc2.markdown(f"*Reputation change:* {log.get('reputation_change', 0):+d}")

                if log.get("events_fired"):
                    for ev in log["events_fired"]:
                        st.markdown(f"- 📢 {ev}")
                if log.get("tradeoff_choice"):
                    st.markdown(f"- 🎯 Trade-off chosen: **{log['tradeoff_choice']}**")
                if log.get("decision"):
                    decision_info = log["decision"]
                    st.markdown(
                        f"- 📋 Decision: **{decision_info.get('decision_id')}** -> "
                        f"option **{decision_info.get('choice_id')}**"
                    )
                if log.get("actions"):
                    for a in log["actions"]:
                        issues = f" ⚠️ {' / '.join(a['issues'])}" if a.get("issues") else ""
                        st.markdown(
                            f"- **{a['project_id']}** <- {', '.join(a['consultant_ids']) or '-'} "
                            f"(burn €{a['burn']:,}, quality {a['quality_mult_this_week']:.2f}){issues}"
                        )
                if log.get("completions"):
                    st.markdown(f"- ✅ Completed: {', '.join(log['completions'])}")
                if log.get("quality_failures"):
                    st.markdown(f"- ⚠️ Quality failure: {', '.join(log['quality_failures'])}")
                if log.get("cancellations"):
                    st.markdown(f"- ❌ Cancelled: {', '.join(log['cancellations'])}")
                if log.get("missed_deadlines"):
                    st.markdown(f"- ⏰ Missed deadline: {', '.join(log['missed_deadlines'])}")

    # Layer 3 detail
    with st.expander("Layer 3: Interview transcripts"):
        l3_rows = db.get_layer3_results(candidate_id)
        # Tech-issue escape: if the candidate hit "I'm having technical
        # issues" during the call, show their reason verbatim at the top.
        # Any answers they gave BEFORE pressing the escape are scored
        # normally and rendered below this banner.
        if scores.get("layer3_skipped"):
            reason = scores.get("layer3_skip_reason") or "(no reason provided)"
            partial = any(
                (r.get("main_transcript") or "").strip()
                or (r.get("followup_transcript") or "").strip()
                for r in l3_rows
            )
            if partial:
                trailing = (
                    "Partial transcripts were captured before the candidate "
                    "flagged the issue - they're shown below and were scored "
                    "as normal (unanswered competencies count as 0)."
                )
            else:
                trailing = (
                    "No interview transcripts were captured. The candidate's "
                    "Layer 1 and Layer 2 results are still valid."
                )
            st.error(
                "**Layer 3 skipped by candidate (technical issues)**\n\n"
                f"Candidate's note:\n\n> {reason}\n\n" + trailing
            )
        if not l3_rows and not scores.get("layer3_skipped"):
            st.write("No Layer 3 data.")
        bucket_names = {
            "A": "GET SPECIFIC", "B": "GET EVIDENCE",
            "C": "GET REASONING", "D": "GET REFLECTION",
        }
        # Threshold (seconds) above which a pre-record pause is flagged
        # as a possible AI signal. Kept conservative; 15s is "I'm thinking
        # hard" territory, longer than that and the candidate may be
        # typing into another tool.
        PAUSE_FLAG_THRESHOLD_SECONDS = 15.0

        def _format_pause(seconds: float | None) -> str:
            """Render the time-to-record cell, flagging suspicious pauses."""
            if seconds is None:
                return "-"
            if seconds >= PAUSE_FLAG_THRESHOLD_SECONDS:
                return f"🚩 {seconds:.1f}s (long pause — possible AI)"
            return f"{seconds:.1f}s"

        # Top-level typed-fallback callout: if the candidate hit the
        # "technical issues with recording" button on one or more
        # competencies, surface it once at the top of the L3 section
        # so the recruiter doesn't have to scan every competency row
        # to spot it. Per-competency detail still shows in the headers
        # below.
        typed_rows = [r for r in l3_rows if int(r.get("typed_fallback_used") or 0)]
        if typed_rows:
            comp_labels = ", ".join(
                f"Q{r['competency_order']} ({r['competency_name']})"
                for r in typed_rows
            )
            st.warning(
                f"🛠 **Typed-answer fallback used on {len(typed_rows)} of "
                f"{len(l3_rows)} questions** — the candidate reported "
                f"technical issues with recording and typed their answer "
                f"on: {comp_labels}."
            )

        for r in l3_rows:
            header = (
                f"**Competency {r['competency_order']}: "
                f"{r['competency_id']}: {r['competency_name']}**"
            )
            if r.get("scripted_flag"):
                header += "  🚩 *flagged: possibly scripted*"
            if int(r.get("typed_fallback_used") or 0):
                header += "  🛠 *typed-answer fallback used*"
            st.markdown(header)

            score = r.get("competency_score")
            if score is not None:
                st.metric("Score (0-25)", f"{score}")
            if r.get("rationale"):
                st.caption(f"Scoring rationale: {r['rationale']}")

            st.markdown(f"*Main question:* {r['main_question']}")
            st.markdown(f"*Main answer:* > {r['main_transcript'] or '(no answer)'}")
            st.markdown(
                f"*Pause before recording (main):* "
                f"{_format_pause(r.get('main_time_to_record_seconds'))}"
            )

            if r.get("followup_question"):
                bucket = r.get("followup_bucket")
                bucket_label = f" [{bucket_names.get(bucket, bucket)}]" if bucket else ""
                st.markdown(f"*Follow-up{bucket_label}:* {r['followup_question']}")
                st.markdown(f"*Follow-up answer:* > {r.get('followup_transcript') or '(no answer)'}")
                st.markdown(
                    f"*Pause before recording (follow-up):* "
                    f"{_format_pause(r.get('followup_time_to_record_seconds'))}"
                )

            st.markdown("---")

    # Logout
    st.divider()
    if st.button("Log out"):
        st.session_state.mode = None
        st.session_state.recruiter_authed = False
        st.session_state.stage = "landing"
        st.rerun()
