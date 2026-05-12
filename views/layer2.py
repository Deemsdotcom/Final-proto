"""Layer 2 view: 8-week firm simulation.

Single big 20-minute timer. Each week, the candidate sees the firm dashboard
(cash, reputation, fatigue, project board), assigns consultants to projects,
and clicks 'Advance to next week.' At Week 6, a trade-off modal interrupts.

No scoring is shown to the candidate during play. Only at the very end
(after Layer 3) are full results revealed.
"""

from __future__ import annotations

import time

import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh

from assessment_logic.layer2_logic import (
    LAYER_TIME_LIMIT_SECONDS,
    advance_week,
    aggregate_layer2,
    consultants_available_in_week,
    events_for_week,
    final_layer2_score,
    initial_state,
    is_simulation_complete,
    load_scenario,
    pending_decision_for_week,
    projects_visible_in_week,
    validate_weekly_assignments,
)
from database import db

from . import _design as ui
from .state import advance_stage


def render() -> None:
    if not st.session_state.get("l2_started", False):
        _intro()
        return

    scenario = load_scenario()

    if "l2_state" not in st.session_state or st.session_state.l2_state is None:
        st.session_state.l2_state = initial_state(scenario)
        st.session_state.l2_started_at = time.time()

    state = st.session_state.l2_state

    # Time check (single big timer)
    elapsed = time.time() - (st.session_state.l2_started_at or time.time())
    remaining = max(0, int(LAYER_TIME_LIMIT_SECONDS - elapsed))
    timed_out = remaining <= 0

    # End-of-game conditions: simulation complete OR time up
    if is_simulation_complete(state):
        _finalize_and_advance(scenario, state, int(elapsed))
        return

    if timed_out:
        st.warning("⏰ Time's up. Auto-advancing remaining weeks with no new staffing.")
        # auto-advance through remaining weeks with empty assignments
        while not is_simulation_complete(state):
            state = advance_week(scenario, state, weekly_assignments={}, tradeoff_choice=None)
        st.session_state.l2_state = state
        _finalize_and_advance(scenario, state, int(elapsed))
        return

    # Otherwise render the current week
    _render_week(scenario, state, remaining, elapsed)


def _intro() -> None:
    """Layer 2 intro - cap-feat block style.

    Each section becomes a `cap-feat` block (cyan top stripe, dark navy
    fill, cyan eyebrow, cyan bold accents) - the same visual element
    used inside the Layer 1 theme-intro magazine spread. Bullets use
    the cap-feat-tips numbered counter list. Two-column CSS grid inside
    'How you're judged' so Outcomes and Process sit side by side.

    Every word, sentence, percentage, currency symbol, bold marker and
    em-dash is byte-for-byte from the team's original copy. This is
    purely a visual restructure.
    """
    ui.inject_global_styles()
    ui.header(meta=f"Candidate {st.session_state.candidate_name}")

    ui.page_title("Layer 2: Firm Simulation")

    # The setup
    st.markdown(
        '''
<div class="cap-feat" style="margin-bottom:1rem;">
  <div class="cap-feat-eyebrow">The setup</div>
  <p class="cap-feat-body">You\'re the resource lead at a consulting firm with <strong>6 consultants</strong> and a starting cash balance of <strong>\u20ac500,000</strong>. Over the next <strong>8 simulated weeks</strong>, you\'ll decide who works on which project, respond to events, and try to keep the firm in good shape, both financially and reputationally.</p>
  <p class="cap-feat-body" style="margin-top:0.85rem;">Each week you\'ll see your firm dashboard, the active project board, and your consultants\' current state. You assign people to projects, then click <strong>Advance to next week</strong>. Time, cash, fatigue, and reputation all carry forward.</p>
</div>
''',
        unsafe_allow_html=True,
    )

    # How you\'re judged
    st.markdown(
        '''
<div class="cap-feat" style="margin-bottom:1rem;">
  <div class="cap-feat-eyebrow">How you\'re judged</div>
  <p class="cap-feat-body">Your performance is scored on two things: outcomes (70%) and process (30%).</p>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:1.8rem;margin-top:1.1rem;">
    <div>
      <div style="font-weight:700;color:#cbd5e1;margin-bottom:0.5rem;font-size:1.02rem;">Outcomes (what you actually achieved):</div>
      <ul class="cap-feat-tips">
        <li><strong>Cash management:</strong> did you protect the firm\'s money or burn through it? Holding cash flat earns partial credit; growing it earns full marks.</li>
        <li><strong>Reputation:</strong> starts at 60. Holding it steady is solid; gaining reputation is excellent. Losing it through cancellations and missed deadlines will cost you.</li>
        <li><strong>Project completions:</strong> projects only count if they finish properly. Quality failures and missed deadlines don\'t count.</li>
        <li><strong>Consultant fatigue:</strong> keeping the team from burning out matters.</li>
      </ul>
    </div>
    <div>
      <div style="font-weight:700;color:#cbd5e1;margin-bottom:0.5rem;font-size:1.02rem;">Process (how well you ran it):</div>
      <ul class="cap-feat-tips">
        <li><strong>Constraint compliance:</strong> did you respect skill and seniority requirements?</li>
        <li><strong>Skill match quality:</strong> staffing the wrong people on a project lowers its quality multiplier and shrinks the revenue when it completes.</li>
      </ul>
    </div>
  </div>
</div>
''',
        unsafe_allow_html=True,
    )

    # What to prioritize
    st.markdown(
        '''
<div class="cap-feat" style="margin-bottom:1rem;">
  <div class="cap-feat-eyebrow">What to prioritize</div>
  <ul class="cap-feat-tips">
    <li><strong>Match skills and seniority before anything else.</strong> A skill mismatch cuts that project\'s quality to 55%. A seniority mismatch cuts it to 65%. These stack. A badly-staffed project pays a fraction of its revenue.</li>
    <li><strong>Use the smallest viable team.</strong> Adding more people doesn\'t speed projects up or improve quality past 100%. Extra bodies just leave other projects unstaffed.</li>
    <li><strong>Don\'t let projects sit idle.</strong> Two consecutive unstaffed weeks and the project gets cancelled with a -15 reputation hit.</li>
    <li><strong>Watch deadlines.</strong> Missing one costs -8 reputation and the project pays nothing.</li>
    <li><strong>Plan around fatigue.</strong> A consultant staffed every week hits high fatigue (\u226570) and starts dragging quality down. Rotate the bench.</li>
  </ul>
</div>
''',
        unsafe_allow_html=True,
    )

    # What to look out for
    st.markdown(
        '''
<div class="cap-feat" style="margin-bottom:1rem;">
  <div class="cap-feat-eyebrow">What to look out for</div>
  <ul class="cap-feat-tips">
    <li><strong>Two binding decisions</strong> will interrupt the game. You can\'t advance until you choose. Read the options carefully because they have lasting effects on cash, reputation, and your team.</li>
    <li><strong>Sick leave, budget cuts, and new project arrivals</strong> will happen mid-game. You\'ll need to adapt your staffing on the fly.</li>
    <li><strong>New projects arrive in later weeks.</strong> Some have very short windows (a 2-week project arriving in week 7, for example). You may need to free people up to chase them.</li>
  </ul>
</div>
''',
        unsafe_allow_html=True,
    )

    # The clock
    st.markdown(
        '''
<div class="cap-feat" style="margin-bottom:1rem;">
  <div class="cap-feat-eyebrow">The clock</div>
  <p class="cap-feat-body">You have <strong>20 minutes total</strong> to play through all 8 weeks. The timer runs continuously. There\'s no per-week limit. If time runs out, remaining weeks auto-advance with no new staffing, which usually goes badly.</p>
</div>
''',
        unsafe_allow_html=True,
    )

    ui.info_banner(
        "Think long. A decision in Week 2 will shape what\'s possible in Week 6.",
        icon="\u2139",
    )
    st.markdown("<div style=\'height:0.4rem\'></div>", unsafe_allow_html=True)

    if st.button("Begin Layer 2", type="primary", use_container_width=True):
        st.session_state.l2_started = True
        st.session_state.l2_state = None
        st.session_state.l2_started_at = time.time()
        st.rerun()


def _md_inline_to_html(text: str) -> str:
    """Tiny markdown-bold + markdown-italic to HTML converter, used inside
    the Layer 2 mini-card titles so the existing **Anna** / *sick this week*
    text still renders correctly when we drop out of st.markdown into
    raw-HTML containers."""
    import re
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", text)
    return text


def _render_consultant_card(c, fatigue, sick, departed) -> None:
    """Render one consultant as a styled mini-card.

    Every word, number, emoji and the *italic* status marker from the
    original markdown line is preserved verbatim inside the card. The
    visual additions are: a left border colour-coded by seniority, and
    a thin fatigue progress bar at the bottom (colour mirrors the
    existing emoji indicator).
    """
    # Left border kept uniform (default cyan) - the user doesn't want
    # the border colour to leak seniority info, since seniority is
    # already shown in plain text inside the card.
    tag = ""
    if departed:
        tag = " \u274C *no longer with the firm*"
    elif sick:
        tag = " \U0001F912 *sick this week*"

    fatigue_emoji = "\U0001F7E2" if fatigue < 40 else ("\U0001F7E1" if fatigue < 70 else "\U0001F534")
    fatigue_color = "#00D5D0" if fatigue < 40 else ("#FEB100" if fatigue < 70 else "#FF816E")

    title = _md_inline_to_html(
        f"<strong>{c['name']}</strong> ({c['id']}), {c['seniority']}{tag}"
    )
    skills_line = f"Skills: {', '.join(c['skills'])}"
    fatigue_line = f"Fatigue: {fatigue_emoji} {fatigue}/100"

    st.markdown(
        f'<div class="l2-mini">'
        f'<div class="l2-mini-title">{title}</div>'
        f'<div class="l2-mini-line">{skills_line}</div>'
        f'<div class="l2-mini-line">{fatigue_line}</div>'
        f'<div class="l2-mini-bar"><div class="l2-mini-bar-fill" '
        f'style="width:{max(0, min(100, fatigue))}%;background:{fatigue_color};"></div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_project_card(p, ps, total: int) -> None:
    """Render one project as a styled mini-card.

    Every word, number, currency value, emoji and dot separator from
    the original markdown line is preserved verbatim. The visual
    additions are: a left border colour-coded by priority tier, and a
    thin progress bar at the bottom (only when the project is active),
    showing weeks staffed vs total duration.
    """
    # Tier hint removed per user request: no coloured priority bubble
    # in the title and no tier-coloured border. The priority_tier is
    # still used inside the scoring logic, just not surfaced visually.
    urgent_tag = " \U0001F6A8 URGENT" if p.get("urgent") else ""
    progress = ps["weeks_staffed_correctly"]
    duration = p["duration_weeks"]
    revenue = p.get("revenue", 0)
    revenue_str = f"\u20AC{revenue:,}" if revenue else "Strategic (no revenue)"

    status_str = ""
    if ps["status"] == "active":
        status_str = f" \u00B7 \u25B6\uFE0F {progress}/{duration} weeks done"
    elif ps["status"] == "available":
        status_str = " \u00B7 \U0001F195 Not started"

    title = _md_inline_to_html(
        f"<strong>{p['name']}</strong> ({p['id']}){urgent_tag}{status_str}"
    )
    skills_line = (
        f"Skills: {', '.join(p.get('required_skills', []))} \u00B7 "
        f"Min. seniority: {p.get('min_seniority')}"
    )
    nums_line = (
        f"Burn: \u20AC{p['weekly_burn']:,}/wk \u00B7 "
        f"Revenue: {revenue_str} \u00B7 "
        f"Deadline: Week {p.get('deadline_week', total)}"
    )

    bar_html = ""
    if ps["status"] == "active" and duration > 0:
        pct = max(0, min(100, int(progress / duration * 100)))
        bar_html = (
            f'<div class="l2-mini-bar"><div class="l2-mini-bar-fill" '
            f'style="width:{pct}%;background:#1DB8F2;"></div></div>'
        )

    st.markdown(
        f'<div class="l2-mini">'
        f'<div class="l2-mini-title">{title}</div>'
        f'<div class="l2-mini-line">{skills_line}</div>'
        f'<div class="l2-mini-line">{nums_line}</div>'
        f'{bar_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_week(scenario: dict, state: dict, remaining: int, elapsed: float) -> None:
    """Render one week of the simulation - redesigned with our design system.

    Content (every word, value, emoji, formula) is preserved exactly. Only
    the visual container changes: ui.question_progress_bar header with
    cyan timer pill, ui.metric KPI strip, ui.card-wrapped panels for team
    / projects / staffing / log. Cards across the app already render
    with a cyan top stripe via the global CSS update in _design.py.
    """
    # Anchor at the very top of the week content, used by the scroll script.
    st.markdown('<div id="week-top"></div>', unsafe_allow_html=True)

    # Tick down the timer every second
    st_autorefresh(interval=1000, key=f"l2_tick_{state['current_week']}")

    week = state["current_week"]
    total = state["total_weeks"]

    # ── Header chrome: eyebrow + progress rail + countdown timer pill ──
    ui.inject_global_styles()
    ui.header(meta=f"Candidate {st.session_state.candidate_name}")
    ui.question_progress_bar(
        idx=week - 1,
        total=total,
        remaining=remaining,
        seconds=LAYER_TIME_LIMIT_SECONDS,
        eyebrow_text=f"Week {week} of {total}",
    )

    # ── Firm KPI strip ────────────────────────────────────────────────
    # 4-up grid in a single st.markdown call. Using a CSS grid here
    # rather than st.columns(4) because Streamlit's column layout was
    # wrapping the 4th tile onto a new row at certain viewport widths.
    completed = sum(1 for ps in state["projects"].values() if ps["status"] == "completed")
    failed = sum(
        1 for ps in state["projects"].values()
        if ps["status"] in ("cancelled", "quality_failure", "missed_deadline")
    )
    st.markdown(
        '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:0.6rem;margin:0.2rem 0 0.4rem 0;">'
        + f'<div class="cap-metric"><span class="val">\u20ac{state["cash"]:,.0f}</span><span class="lbl">Cash</span></div>'
        + f'<div class="cap-metric"><span class="val">{state["reputation"]:.0f}/100</span><span class="lbl">Reputation</span></div>'
        + f'<div class="cap-metric"><span class="val">{completed}</span><span class="lbl">Projects done</span></div>'
        + f'<div class="cap-metric"><span class="val">{failed}</span><span class="lbl">Projects failed</span></div>'
        + '</div>',
        unsafe_allow_html=True,
    )

    # ── Events firing this week ───────────────────────────────────────
    events = events_for_week(scenario, week)
    for ev in events:
        if ev["type"] == "sick_leave":
            st.warning(f"\U0001F912 {ev['message']}")
        elif ev["type"] == "budget_cut":
            st.warning(f"\U0001F4B8 {ev['message']}")
        elif ev["type"] == "new_project_alert":
            st.info(f"\U0001F4E8 {ev['message']}")
        elif ev["type"] == "tradeoff":
            st.error(f"\u26A0\uFE0F {ev['message']}")

    st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)

    # ── Week 2 decision modal (must be made before advancing) ─────────
    decision_choice_tuple = None
    pending = pending_decision_for_week(scenario, state, week)
    if pending is not None:
        decision_choice_tuple = _render_decision(pending, scenario)
        if decision_choice_tuple is None:
            st.stop()

    # ── Trade-off modal in Week 6 ─────────────────────────────────────
    tradeoff_choice = None
    is_tradeoff_week = any(ev["type"] == "tradeoff" for ev in events)
    if is_tradeoff_week:
        tradeoff_choice = _render_tradeoff(scenario)
        if tradeoff_choice is None:
            st.stop()

    # ── Two-column main view: consultants + projects ─────────────────
    left, right = st.columns([1, 1], gap="medium")

    with left:
        with ui.card("Your team"):
            available = consultants_available_in_week(scenario, state, week)
            available_ids = {c["id"] for c in available}
            departed_ids = set(state.get("consultants_departed_at_week", {}).keys())
            for c in scenario["consultants"]:
                fatigue = state["fatigue"].get(c["id"], 0)
                sick = c["id"] not in available_ids and c["id"] not in departed_ids
                departed = c["id"] in departed_ids and c["id"] not in available_ids
                _render_consultant_card(c, fatigue, sick, departed)

    with right:
        with ui.card("Active projects"):
            visible_projects = projects_visible_in_week(scenario, state, week)
            if not visible_projects:
                st.info("No active projects this week.")
            for p in visible_projects:
                ps = state["projects"][p["id"]]
                _render_project_card(p, ps, total)

    st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)

    # ── Staffing widget (multiselect per visible project) ─────────────
    with ui.card("Staff projects this week"):
        st.caption("Each consultant can be on at most one project per week.")

        consultant_label = {c["id"]: f"{c['name']} ({c['id']}, {c['seniority']})"
                            for c in available}

        assignments_key = f"l2_week_{week}_assignments"
        if assignments_key not in st.session_state:
            prev_week = week - 1
            prev_assignments = state["weekly_assignments_history"].get(str(prev_week), {})
            visible_pids = {p["id"] for p in visible_projects}
            carried = {
                pid: [cid for cid in cids if cid in consultant_label]
                for pid, cids in prev_assignments.items()
                if pid in visible_pids
            }
            for pid in visible_pids:
                if pid not in carried:
                    carried[pid] = []
            st.session_state[assignments_key] = carried

        assignments = st.session_state[assignments_key]
        new_assignments = {}
        for project in visible_projects:
            pid = project["id"]
            current = [cid for cid in assignments.get(pid, []) if cid in consultant_label]
            # Styled label row above the multiselect. The same label text
            # is still passed into st.multiselect for accessibility, just
            # collapsed visually so we don't show it twice.
            st.markdown(
                f'<div class="l2-staff-row"><div class="l2-staff-label">'
                f'<strong>{project["name"]}</strong>'
                f'<span class="l2-staff-id">({pid})</span>'
                f'</div></div>',
                unsafe_allow_html=True,
            )
            chosen = st.multiselect(
                f"**{project['name']}** ({pid})",
                options=list(consultant_label.keys()),
                default=current,
                format_func=lambda cid: consultant_label[cid],
                key=f"l2_assign_w{week}_{pid}",
                label_visibility="collapsed",
            )
            new_assignments[pid] = chosen
        st.session_state[assignments_key] = new_assignments

        # Validation warnings (live, doesn't block)
        warnings = validate_weekly_assignments(scenario, state, week, new_assignments)
        for w in warnings:
            st.warning(f"\u26A0\uFE0F {w}")

    st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)

    # ── Recent activity log ──────────────────────────────────────────
    if state.get("weekly_log"):
        with st.expander("\U0001F4DC Recent weeks log", expanded=False):
            for log in state["weekly_log"][-3:]:
                _render_log_entry(log, scenario)

    # ── Advance button ───────────────────────────────────────────────
    advance_label = (
        f"Advance to Week {week + 1}" if week < total else "Finish Layer 2"
    )
    if st.button(advance_label, type="primary", use_container_width=True):
        new_state = advance_week(
            scenario, state, new_assignments,
            tradeoff_choice=tradeoff_choice,
            decision_choice=decision_choice_tuple,
        )
        st.session_state.l2_state = new_state
        if assignments_key in st.session_state:
            del st.session_state[assignments_key]
        st.session_state["_scroll_top_needed"] = True
        st.rerun()


def _render_decision(decision: dict, scenario: dict) -> tuple[str, str] | None:
    """Render a one-off decision modal. Returns (decision_id, choice_id) or None."""
    with ui.card("\U0001F4CB Decision required"):
        st.warning(decision["description"])

        option_labels = [f"**{opt['id'].replace('_', ' ').title()}**, {opt['label']}"
                         for opt in decision["options"]]
        choice_display = st.radio(
            "Pick one:",
            options=option_labels,
            key=f"l2_decision_{decision.get('id', 'x')}",
            index=None,
        )
        if choice_display is None:
            st.info("You must make this decision before continuing the week.")
            return None
        chosen = decision["options"][option_labels.index(choice_display)]
    # find the decision_id by looking it up in scenario['decisions']
    decision_id = None
    for did, d in scenario.get("decisions", {}).items():
        if d == decision:
            decision_id = did
            break
    if decision_id is None:
        decision_id = next(iter(scenario.get("decisions", {})), None)
    return (decision_id, chosen["id"])


def _render_tradeoff(scenario: dict) -> str | None:
    """Render the Week 6 trade-off modal. Returns the choice id or None if not chosen yet."""
    tradeoff = scenario["tradeoff"]
    with ui.card("\u26A0\uFE0F Trade-off decision"):
        st.error(tradeoff["description"])

        option_labels = [f"**{opt['id']}**, {opt['label']}" for opt in tradeoff["options"]]
        choice_display = st.radio(
            "Choose one option:",
            options=option_labels,
            key="l2_tradeoff_radio",
            index=None,
        )
        if choice_display is None:
            st.info("You must make this decision before continuing the week.")
            return None
        return tradeoff["options"][option_labels.index(choice_display)]["id"]


def _render_log_entry(log: dict, scenario: dict) -> None:
    """Render one week's log entry."""
    project_names = {p["id"]: p["name"] for p in scenario["projects"]}
    st.markdown(f"**Week {log['week']}**")
    if log.get("events_fired"):
        for ev in log["events_fired"]:
            st.markdown(f"- 📢 {ev}")
    if log.get("tradeoff_choice"):
        st.markdown(f"- 🎯 Trade-off: chose option **{log['tradeoff_choice']}**")
    if log.get("completions"):
        names = [project_names.get(pid, pid) for pid in log["completions"]]
        st.markdown(f"- ✅ Completed: {', '.join(names)}")
    if log.get("quality_failures"):
        names = [project_names.get(pid, pid) for pid in log["quality_failures"]]
        st.markdown(f"- ⚠️ Quality failure: {', '.join(names)}")
    if log.get("cancellations"):
        names = [project_names.get(pid, pid) for pid in log["cancellations"]]
        st.markdown(f"- ❌ Cancelled (unstaffed too long): {', '.join(names)}")
    if log.get("missed_deadlines"):
        names = [project_names.get(pid, pid) for pid in log["missed_deadlines"]]
        st.markdown(f"- ⏰ Missed deadline: {', '.join(names)}")


def _finalize_and_advance(scenario: dict, state: dict, elapsed: int) -> None:
    """Persist the simulation result and move to Layer 3 with no score reveal."""
    if db.has_layer2_simulation(st.session_state.candidate_id):
        # already saved (resume case); just move on
        advance_stage("layer3")
        return

    result = final_layer2_score(state, scenario)
    completed = sum(1 for ps in state["projects"].values() if ps["status"] == "completed")
    cancelled = sum(1 for ps in state["projects"].values()
                    if ps["status"] in ("cancelled", "quality_failure", "missed_deadline"))

    # AI-use flag: high score on Layer 2 AND finished in <= 35% of the time
    # limit (i.e. <= 7 minutes of the 20). Informational only.
    layer2_total = result["layer2_total"]
    fast_threshold = int(LAYER_TIME_LIMIT_SECONDS * 0.35)
    ai_flag_layer2 = (layer2_total >= 80) and (elapsed <= fast_threshold)
    st.session_state["l2_ai_flag"] = bool(ai_flag_layer2)

    db.save_layer2_simulation(
        candidate_id=st.session_state.candidate_id,
        final_state=state,
        weekly_log=state.get("weekly_log", []),
        weeks_played=min(state["current_week"] - 1, state["total_weeks"]),
        final_cash=state["cash"],
        final_reputation=state["reputation"],
        projects_completed=completed,
        projects_cancelled=cancelled,
        tradeoff_choice=state.get("tradeoff_choice"),
        outcome_score=result["outcome_score"],
        process_score=result["process_score"],
        layer2_total=result["layer2_total"],
        time_taken_seconds=elapsed,
    )

    ui.eyebrow("Stage 2 of 3 complete")
    ui.page_title(
        "Layer 2 Complete",
        "You've finished the firm simulation.",
    )

    with ui.card("Next: Layer 3 (AI-Led Interview)"):
        st.markdown(
            "Four questions, each with a follow-up. Each answer is voice-recorded, "
            "transcribed, and scored on clarity, structure, relevance, and depth."
        )
        st.markdown(
            "Make sure your microphone is working and that you're in a quiet space. "
            "Your full results will be shown after this final layer."
        )

    if st.button("Begin Layer 3", type="primary", use_container_width=True):
        advance_stage("layer3")
