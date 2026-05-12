"""Layer 1 view: cognitive assessment.

Theme-level timer (one budget per theme block, not per question). The
candidate sees a continuous countdown over the whole theme. When the
theme runs out, any unanswered questions are auto-marked wrong and the
candidate skips to the next theme intro.

Renders three theme hero cards on the layer overview, a magazine-spread
intro per theme (left: huge theme number + stats; right: editorial
features and pattern chips), then a question screen with the eyebrow +
horizontal progress rail + countdown timer pill above a card-mounted
question stem.

Visual layer uses views/_design.py helpers (ui.theme_card, ui.theme_spread,
ui.question_progress_bar, ui.question_stem, ui.numbered_rule, ui.card,
ui.info_banner). Question logic, theme timer, AI-flag scoring, example
questions, save/advance, and force-finish-on-timeout are all from team
v9 and unchanged.
"""

from __future__ import annotations

import time

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from assessment_logic.layer1_logic import (
    QUESTIONS_PER_THEME,
    THEMES,
    select_questions,
    theme_score,
    theme_time_limit_for,
)
from database import db

from . import _design as ui
from .state import advance_stage


# AI-use flagging thresholds: per-theme score >= 80% AND theme total time
# spent <= 25% of the theme block triggers a "possible AI use" flag.
AI_FLAG_SCORE_THRESHOLD_PCT = 80.0
AI_FLAG_TIME_RATIO = 0.25


# ---------------------------------------------------------------------------
# Hardcoded example questions, one per theme. Shown on the theme intro page
# as "Example question (not graded)" so the candidate knows what to expect.
# These are static and do not go through the seeded random pool.
# ---------------------------------------------------------------------------
EXAMPLE_QUESTIONS = {
    "logical": {
        "stem": (
            "Which of the five figures (A-E) continues the sequence shown above?"
        ),
        "sequence_image": "data/charts/example_logical_sequence.png",
        "options_image": "data/charts/example_logical_options.png",
        "options": ["A", "B", "C", "D", "E"],
        "correct": "A",
        "explanation": (
            "Each frame adds one dot following a consistent diagonal pattern "
            "from the top-left corner. Option A continues that progression."
        ),
    },
    "numerical": {
        "stem": (
            "It was estimated that it took editing companies approximately 3 "
            "minutes per minute of final movie time. If 87% of each thriller "
            "movie was looked into by editing companies, how many minutes on "
            "average did they spend on it in 2004?"
        ),
        "chart_image": "data/charts/example_numerical.png",
        "options": [
            "A) 425 minutes",
            "B) 260 minutes",
            "C) 140 minutes",
            "D) 47 minutes",
            "E) 3 minutes",
        ],
        "correct": "A",
        "explanation": (
            "Thriller 2004 average length is 163 minutes. 87% of 163 = 141.81 "
            "minutes of footage reviewed. At 3 editing minutes per movie "
            "minute, that's 141.81 x 3 = 425 minutes."
        ),
    },
    "verbal": {
        "stem": (
            "Passage: The decision must be notified in writing within "
            "fourteen days of the hearing.\n\n"
            "Statement: A notification given orally would not satisfy the "
            "requirement."
        ),
        "options": ["A) True", "B) False", "C) Cannot Say"],
        "correct": "A",
        "explanation": (
            "The passage explicitly requires the decision to be notified *in "
            "writing*. An oral notification therefore fails to meet the stated "
            "requirement, so the statement is True."
        ),
    },
}


# ---------------------------------------------------------------------------
# Per-theme content for the magazine-spread theme intro. Module-level so the
# render function stays a clean layout pipeline and the copy can be edited
# without touching layout code.
# ---------------------------------------------------------------------------
THEME_LABELS = {
    "logical": {
        "short": "Logical",
        "title": "Logical Reasoning",
        "subtitle": "Find the pattern in the sequence and pick the figure that comes next.",
        "options": "A-E",
        "setup_html": (
            "Each question shows a <strong>row of figures</strong>. The "
            "figures change from left to right according to a hidden rule. "
            "Your job is to work out the rule and pick the option (A-E) "
            "that comes next in the sequence."
        ),
        "pattern_tags": [
            "Shape changes", "Rotation", "Add or subtract",
            "Counting", "Color &amp; shading",
        ],
        "look_for_note": (
            "Patterns can combine multiple rules. Track how each figure changes "
            "from one step to the next, then project that change forward."
        ),
        "tips": [
            ("Look at the change between adjacent figures first.",
             " The step-by-step rule is usually easier to spot than the whole pattern at once."),
            ("Eliminate impossible options.",
             " Even if you can't see the full pattern, you can usually rule out 2-3 options quickly."),
        ],
    },
    "numerical": {
        "short": "Numerical",
        "title": "Numerical Reasoning",
        "subtitle": "Read a chart or table, then answer a multiple-choice question about the data.",
        "options": "A-D",
        "setup_html": (
            "Each question shows a <strong>chart or table</strong> followed by a "
            "multiple-choice question about the data. You will work with percentages, "
            "ratios, growth rates, and multi-step calculations. Use a calculator."
        ),
        "pattern_tags": [
            "Percentages", "Ratios", "Growth rates",
            "Table reading", "Multi-step sums",
        ],
        "look_for_note": (
            "Wrong answers are usually plausible-looking traps based on misreading "
            "axes, units, or which row of the table the question refers to."
        ),
        "tips": [
            ("Read carefully.", "Check axes, units, and which row or column the question refers to."),
            ("Use the calculator.", "Don't try to do percentages or ratios in your head under time pressure."),
            ("Estimate first.", "A rough estimate helps you spot when an answer choice is way off."),
            ("Skip and return.", "If a calculation is taking too long, guess and move on."),
        ],
    },
    "verbal": {
        "short": "Verbal",
        "title": "Verbal Reasoning",
        "subtitle": "Read the passage, then judge the statement: True, False, or Cannot Say.",
        "options": "3 choices",
        "setup_html": (
            "Each question shows a <strong>short passage</strong> followed by a "
            "<strong>statement</strong>. You decide whether the statement is True, "
            "False, or Cannot Say based only on what the passage says. Outside "
            "knowledge does not count."
        ),
        "pattern_tags": ["True", "False", "Cannot Say"],
        "look_for_note": (
            "If the passage doesn't address the statement directly, the answer "
            "is almost always Cannot Say. Don't read in what isn't there."
        ),
        "tips": [
            ("Stick to the passage.",
             " Use only what's written. No assumptions about what 'should' be true."),
            ("Default to Cannot Say.",
             " When the passage is silent on a point, the answer is most often Cannot Say."),
        ],
    },
}


# ============================================================
# Top-level router
# ============================================================

def render() -> None:
    candidate_id = st.session_state.candidate_id
    theme_idx = st.session_state.l1_theme_idx
    question_idx = st.session_state.l1_question_idx

    if theme_idx >= len(THEMES):
        _finish_layer(candidate_id)
        return

    # One-time Layer 1 overview, shown before the first theme intro.
    if theme_idx == 0 and not st.session_state.get("l1_overview_seen", False):
        _layer_overview()
        return

    theme = THEMES[theme_idx]

    # Theme intro screen (only before the first question of a theme)
    if question_idx == 0 and not st.session_state.get(f"l1_{theme}_started", False):
        _theme_intro(theme, theme_idx)
        return

    # Lazy-load questions for this theme
    if theme not in st.session_state.l1_questions_cache:
        st.session_state.l1_questions_cache[theme] = select_questions(candidate_id, theme)

    questions = st.session_state.l1_questions_cache[theme]

    if question_idx >= len(questions):
        _finish_theme(candidate_id, theme)
        return

    question = questions[question_idx]
    _render_question(candidate_id, theme, theme_idx, question_idx, question, len(questions))


# ============================================================
# Layer overview (three theme hero cards)
# ============================================================

def _layer_overview() -> None:
    """Layer 1 overview shown once before the first theme intro.

    The visual layer is our 3 theme hero cards + prep card, but every
    obligatory sentence from the team v9 spec is rendered alongside so
    the candidate gets the exact rule wording the team agreed on.
    """
    ui.inject_global_styles()
    ui.header(meta=f"Candidate {st.session_state.candidate_name}")

    ui.eyebrow("Stage 1 of 3 · Cognitive Assessment")
    ui.page_title("Layer 1: Cognitive Assessment")

    # The three theme descriptions live inside the hero cards below
    # (not duplicated here). The rule paragraph stays, since it covers
    # behaviour the cards don't repeat.
    st.markdown(
        "Each theme has **10 questions** and its own **time block, not a "
        "per-question timer**. The clock runs continuously over the whole "
        "theme. When the theme block ends, any unanswered questions are "
        "marked wrong and you move on to the next theme. **You cannot "
        "revisit questions once answered.**"
    )

    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

    # Three theme hero cards
    c1, c2, c3 = st.columns(3, gap="medium")
    def _theme_time_label(theme: str) -> str:
        """Format a theme time-budget as 'M min' or 'M min S sec' when
        there are leftover seconds. Logical is 750s = 12 min 30 sec,
        verbal is 450s = 7 min 30 sec, numerical is 900s = 15 min.
        """
        secs = theme_time_limit_for(theme)
        mins, leftover = divmod(secs, 60)
        if leftover == 0:
            return f"{mins} min"
        return f"{mins} min {leftover} sec"

    with c1:
        ui.theme_card(
            icon_svg=ui.THEME_ICON_LOGICAL,
            meta="Theme 1",
            title="Logical Reasoning",
            desc=(
                "Abstract sequence puzzles. You'll see a row of figures "
                "and pick the one that comes next in the pattern."
            ),
            stats=[
                (f"{QUESTIONS_PER_THEME}", "Questions"),
                (_theme_time_label("logical"), "Theme time"),
            ],
        )
    with c2:
        ui.theme_card(
            icon_svg=ui.THEME_ICON_NUMERICAL,
            meta="Theme 2",
            title="Numerical Reasoning",
            desc=(
                "Short charts and tables, followed by a multiple-choice "
                "question about the data."
            ),
            stats=[
                (f"{QUESTIONS_PER_THEME}", "Questions"),
                (_theme_time_label("numerical"), "Theme time"),
            ],
        )
    with c3:
        ui.theme_card(
            icon_svg=ui.THEME_ICON_VERBAL,
            meta="Theme 3",
            title="Verbal Reasoning",
            desc=(
                "A short passage followed by a statement. You decide "
                "whether the statement is True, False, or Cannot Say "
                "based only on the passage."
            ),
            stats=[
                (f"{QUESTIONS_PER_THEME}", "Questions"),
                (_theme_time_label("verbal"), "Theme time"),
            ],
        )

    st.markdown("<div style='height:1.25rem'></div>", unsafe_allow_html=True)

    # Compact prep checklist (single full-width card). Three items only,
    # matching the team v9 obligatory list.
    with ui.card("Before you begin, please make sure you have"):
        ui.numbered_rule(
            1, "Pen and paper for working through problems.",
            severity="info",
        )
        ui.numbered_rule(
            2, "A calculator (the numerical theme requires arithmetic on percentages, ratios, and multi-step figures).",
            severity="info",
        )
        ui.numbered_rule(
            3, "A quiet, uninterrupted environment for the next ~35 minutes.",
            severity="info",
        )

    st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
    ui.info_banner(
        "Pick the best answer; you will not see whether you got each question right.",
        icon="i",
    )
    # Team v9 obligatory tip - rendered as plain markdown so the full
    # paragraph is preserved verbatim.
    st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)
    st.markdown(
        "**Don't overthink it.** If you've stared for 30 seconds and "
        "nothing clicks, pick your best guess and move on. Wrong answers "
        "cost the same as no answer, and no answer is guaranteed wrong."
    )
    st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)

    if st.button(
        "Continue to Logical Reasoning",
        type="primary",
        use_container_width=True,
        key="l1_overview_continue",
    ):
        st.session_state.l1_overview_seen = True
        st.rerun()


# ============================================================
# Theme intro (magazine spread + example)
# ============================================================

def _theme_intro(theme: str, theme_idx: int) -> None:
    """Per-theme intro: magazine spread on top, example question card below."""
    ui.inject_global_styles()
    ui.header(meta=f"Candidate {st.session_state.candidate_name}")

    label = THEME_LABELS[theme]
    total_seconds = theme_time_limit_for(theme)
    mins = total_seconds // 60
    leftover = total_seconds % 60
    if leftover == 0:
        time_label = f"{mins} min"
    else:
        time_label = f"{mins} min {leftover} sec"

    pills_html = (
        '<div class="cap-feat-pills">'
        + "".join(
            f'<span class="cap-feat-pill">{t}</span>'
            for t in label["pattern_tags"]
        )
        + "</div>"
    )

    tips_short_html = (
        '<ol class="cap-feat-tips">'
        + "".join(
            f'<li><strong>{head}</strong>{body}</li>'
            for head, body in label["tips"][:3]
        )
        + "</ol>"
    )

    format_stats_html = (
        '<p class="cap-feat-body">'
        f'<strong>{time_label}</strong> is given for the entire theme '
        f'block. The clock runs continuously across all {QUESTIONS_PER_THEME} '
        'questions; the timer does not reset between questions, so '
        'manage your time as you go.'
        '</p>'
    )

    watch_eyebrow = (
        "Pattern types to look for" if theme == "logical" else
        ("What the data looks like" if theme == "numerical" else
         "Possible answers")
    )

    ui.theme_spread(
        eyebrow=f"Theme {theme_idx + 1} of 3",
        title=f"Layer 1: {label['title']}",
        subtitle=label["subtitle"],
        side_num=f"0{theme_idx + 1}",
        side_eyebrow=f"Theme {theme_idx + 1} of 3",
        stats=[
            (str(QUESTIONS_PER_THEME), "",  "Questions"),
            (time_label,                "",  "Theme time"),
            (label["options"],          "",  "Options"),
        ],
        features=[
            {
                "eyebrow": "The task",
                "body_html": '<p class="cap-feat-body">' + label["setup_html"] + '</p>',
            },
            {
                "eyebrow": "The format",
                "body_html": format_stats_html,
            },
            {
                "eyebrow": watch_eyebrow,
                "body_html": pills_html + '<p class="cap-feat-body" style="margin-top:0.7rem;color:var(--cap-text-secondary,#A0AECB);font-size:var(--cap-text-body-sm);">' + label["look_for_note"] + '</p>',
            },
            {
                "eyebrow": "Tips before you start",
                "body_html": tips_short_html,
            },
        ],
    )

    # Example question card (still a box - stays per user request).
    st.markdown("<div style='height:0.6rem'></div>", unsafe_allow_html=True)
    with ui.card("Example question (not graded)"):
        _render_example(theme)

    # Auto-marked-wrong info banner is also a boxed UI element, kept.
    st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)
    ui.info_banner(
        f"Theme clock runs continuously for {time_label}. When it hits zero, any unanswered "
        f"questions are marked wrong and you move on.",
        icon="i",
    )
    st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)

    if st.button(
        f"Begin {label['short']} Theme",
        type="primary",
        use_container_width=True,
        key=f"l1_theme_{theme}_begin",
    ):
        st.session_state[f"l1_{theme}_started"] = True
        # Theme-level clock starts now.
        st.session_state[f"l1_theme_started_at_{theme}"] = time.time()
        # Per-question wall clock starts here for the first question.
        st.session_state.l1_question_started_at = time.time()
        st.rerun()


def _render_example(theme: str) -> None:
    """Render the example question card body. Called inside ui.card()."""
    ex = EXAMPLE_QUESTIONS.get(theme)
    if not ex:
        return

    # Verbal example: render in the same visual register as a real
    # verbal question screen. Big bold stem via ui.question_stem,
    # answer choices as a disabled radio with the correct one
    # pre-selected, then a small caption confirming the correct
    # answer + the explanation.
    if theme == "verbal":
        # Split passage and statement so they display on separate
        # paragraphs (mirrors how the real question renders).
        parts = [p.strip() for p in str(ex["stem"]).split("\n\n") if p.strip()]
        for part in parts:
            st.markdown(
                '<div class="cap-q-stem" style="font-size:1.2rem;margin:0.4rem 0;">'
                + part.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                + '</div>',
                unsafe_allow_html=True,
            )

        # Strip the 'A) ' / 'B) ' prefix so the radio shows clean labels.
        clean_opts = []
        for opt in ex["options"]:
            if ") " in opt:
                clean_opts.append(opt.split(") ", 1)[1])
            else:
                clean_opts.append(opt)
        letters = ["A", "B", "C", "D", "E"][:len(clean_opts)]
        correct_idx = letters.index(ex["correct"]) if ex["correct"] in letters else 0

        st.radio(
            "Answer",
            options=clean_opts,
            index=correct_idx,
            disabled=True,
            label_visibility="collapsed",
            key="l1_verbal_example_preview",
        )
        st.markdown(
            f"<div style='margin-top:0.5rem;color:#94a3b8;font-size:0.92rem;'>"
            f"<strong style='color:#00D5D0;'>Correct answer: "
            f"{clean_opts[correct_idx]}</strong> &mdash; {ex['explanation']}"
            f"</div>",
            unsafe_allow_html=True,
        )
        return

    # Logical: sequence image, then stem, then A-E options image.
    if theme == "logical":
        seq_path = ex.get("sequence_image")
        if seq_path:
            try:
                st.image(seq_path)
            except Exception:
                pass
        st.markdown(ex["stem"])
        opts_path = ex.get("options_image")
        if opts_path:
            try:
                st.image(opts_path)
            except Exception:
                pass
    # Numerical: chart image first, then stem.
    elif theme == "numerical":
        chart_path = ex.get("chart_image")
        if chart_path:
            try:
                st.image(chart_path)
            except Exception:
                pass
        st.markdown(ex["stem"])

    # Logical / numerical: keep the original markdown-bullet option list.
    for opt in ex["options"]:
        letter = opt.split(")", 1)[0].strip() if ")" in opt else opt.strip()
        if letter == ex["correct"]:
            st.markdown(f"- **{opt}** *(correct)*")
        else:
            st.markdown(f"- {opt}")
    st.markdown(f"*Why: {ex['explanation']}*")


# ============================================================
# Question screen
# ============================================================

def _theme_remaining_seconds(theme: str) -> int:
    """Seconds left in the current theme's time block."""
    started_at = st.session_state.get(f"l1_theme_started_at_{theme}")
    if started_at is None:
        return theme_time_limit_for(theme)
    elapsed = time.time() - started_at
    return max(0, int(theme_time_limit_for(theme) - elapsed))


def _render_question(
    candidate_id: str, theme: str, theme_idx: int, question_idx: int,
    question, total: int,
) -> None:
    """Question screen with eyebrow + progress rail + theme-time pill on top,
    question stem + image + options inside a card.
    """
    theme_total = theme_time_limit_for(theme)

    # Tick every second.
    st_autorefresh(interval=1000, key=f"l1_tick_{theme}_{question_idx}")

    # Per-question wall clock (used for DB time_taken_seconds; not surfaced).
    if st.session_state.l1_question_started_at is None:
        st.session_state.l1_question_started_at = time.time()
    q_started_at = st.session_state.l1_question_started_at

    # Theme-level remaining time (the visible timer).
    remaining = _theme_remaining_seconds(theme)

    # If the theme already ran out, auto-mark all remaining wrong and move on.
    if remaining <= 0:
        _force_finish_theme_on_timeout(candidate_id, theme, question_idx)
        return

    # ── Page chrome + header bar ─────────────────────────────────────────
    ui.inject_global_styles()
    ui.header(meta=f"Candidate {st.session_state.candidate_name}")

    label = THEME_LABELS[theme]
    ui.question_progress_bar(
        idx=question_idx,
        total=total,
        remaining=remaining,
        seconds=theme_total,
        eyebrow_text=f"{label['title']} · Question {question_idx + 1} of {total}",
    )

    # ── Question card ────────────────────────────────────────────────────
    with ui.card(None):
        # Optional main image (chart, sequence, etc).
        if question.chart_path:
            try:
                st.image(question.chart_path)
            except Exception:
                pass

        # Large question stem.
        ui.question_stem(question.question_text)

        # Optional second image (abstract: A-E option grid).
        if question.answer_image_path:
            try:
                st.image(question.answer_image_path)
            except Exception:
                pass

        # Options - dynamic count, support 3 / 4 / 5.
        n_opts = len(question.options)
        letters = ["A", "B", "C", "D", "E"][:n_opts]
        selection_key = f"l1_{theme}_{question_idx}_selection"

        # Letter-only rendering is reserved for abstract-reasoning items where
        # the letters are baked into the answer-grid image.
        use_letter_only = question.locked and question.answer_image_path is not None

        if use_letter_only:
            display = [f"**{letters[i]}**" for i in range(n_opts)]
        else:
            display = [opt for opt in question.options]

        choice_display = st.radio(
            "Select one:",
            options=display,
            key=selection_key,
            index=None,
            horizontal=use_letter_only,
            label_visibility="collapsed",
        )
        chosen_letter = None
        if choice_display is not None:
            chosen_letter = letters[display.index(choice_display)]

        st.markdown(
            '<div class="cap-q-submit-spacer"></div>',
            unsafe_allow_html=True,
        )

        submit_clicked = st.button(
            "Submit answer",
            type="primary",
            disabled=(chosen_letter is None),
            key=f"submit_{theme}_{question_idx}",
            use_container_width=True,
        )

    if submit_clicked:
        elapsed_on_q = int(time.time() - q_started_at)
        _save_and_advance(
            candidate_id, theme, theme_idx, question_idx, question,
            chosen_letter, elapsed_on_q, timed_out=False,
        )


# ============================================================
# Persistence + transitions
# ============================================================

def _save_and_advance(
    candidate_id: str, theme: str, theme_idx: int, question_idx: int,
    question, chosen_letter: str | None, elapsed: int, timed_out: bool,
) -> None:
    is_correct = (chosen_letter == question.correct_option)
    db.save_layer1_result(
        candidate_id=candidate_id,
        theme=theme,
        question_id=question.question_id,
        question_text=question.question_text,
        options_shown=question.options,
        correct_option=question.correct_option,
        candidate_answer=chosen_letter,
        is_correct=is_correct,
        time_taken_seconds=max(0, int(elapsed)),
    )

    # Reset per-question wall clock for the next question.
    st.session_state.l1_question_started_at = time.time()
    st.session_state.l1_question_idx = question_idx + 1
    st.rerun()


def _force_finish_theme_on_timeout(
    candidate_id: str, theme: str, current_question_idx: int,
) -> None:
    """Theme timer hit zero. Mark every remaining unanswered question wrong
    and advance straight to the next theme intro.
    """
    questions = st.session_state.l1_questions_cache.get(theme, [])

    existing = {
        r["question_id"]
        for r in db.get_layer1_results(candidate_id)
        if r["theme"] == theme
    }

    for idx in range(current_question_idx, len(questions)):
        q = questions[idx]
        if q.question_id in existing:
            continue
        db.save_layer1_result(
            candidate_id=candidate_id,
            theme=theme,
            question_id=q.question_id,
            question_text=q.question_text,
            options_shown=q.options,
            correct_option=q.correct_option,
            candidate_answer=None,
            is_correct=False,
            time_taken_seconds=theme_time_limit_for(theme),
        )

    ui.info_banner(
        f"Time's up on the {theme.capitalize()} theme. Moving on to the next theme.",
        icon="!",
    )
    _finish_theme(candidate_id, theme)


def _finish_theme(candidate_id: str, theme: str) -> None:
    rows = [r for r in db.get_layer1_results(candidate_id) if r["theme"] == theme]
    correct = sum(1 for r in rows if r["is_correct"])
    score_pct = theme_score(correct, QUESTIONS_PER_THEME)
    st.session_state.l1_theme_scores[theme] = score_pct

    # AI-use flag: high score plus very fast finish on this theme.
    theme_total_time = sum(int(r.get("time_taken_seconds") or 0) for r in rows)
    flag = (
        score_pct >= AI_FLAG_SCORE_THRESHOLD_PCT
        and theme_total_time <= int(theme_time_limit_for(theme) * AI_FLAG_TIME_RATIO)
    )
    st.session_state[f"l1_ai_flag_{theme}"] = bool(flag)

    st.session_state.l1_theme_idx += 1
    st.session_state.l1_question_idx = 0
    st.session_state.l1_question_started_at = None
    st.rerun()


def _finish_layer(candidate_id: str) -> None:
    """All three themes done. Move on to Layer 2 with no score reveal."""
    ui.inject_global_styles()
    ui.header(meta=f"Candidate {st.session_state.candidate_name}")

    # Team v9 verbatim title.
    ui.eyebrow("Stage 1 of 3 complete")
    ui.page_title(
        "Layer 1 Complete",
        "Nice work, you've finished the cognitive assessment. Your full results will be shown after you complete all three layers.",
    )

    with ui.card("Up next"):
        # Team v9 obligatory verbatim copy for the Layer 2 teaser.
        st.markdown(
            "**Next: Layer 2 (Firm Simulation)**\n\n"
            "You'll run a consulting firm for 8 simulated weeks. Assign "
            "consultants to projects, manage cash and reputation, and "
            "respond to events as they happen. **20 minutes** in one "
            "continuous timer."
        )

    if st.button(
        "Begin Layer 2",
        type="primary",
        use_container_width=True,
        key="l1_finish_to_l2",
    ):
        advance_stage("layer2")
