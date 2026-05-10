"""Layer 1 view: cognitive assessment.

Per-question timer (theme-specific). Uses streamlit_autorefresh to tick
the clock every second. On expiry, submission is forced server-side
(comparing start_time to now).

Renders dynamic option counts (3-5 options) and an optional answer-grid
image for abstract reasoning questions.
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
    time_limit_for,
)
from database import db

from . import _design as ui
from .state import advance_stage

# Per-theme content for _theme_intro. Keeping it module-level so the
# render function reads as a clean layout pipeline, and so the copy can
# be edited without touching layout code.
THEME_LABELS = {
    "logical": {
        "short": "Logical",
        "title": "Logical Reasoning",
        "subtitle": "Spot the pattern across rows and columns. Pick the figure that completes the matrix.",
        "options": "A · E",
        "setup_html": (
            "Each question shows a <strong>3×3 grid of figures</strong> with the "
            "bottom-right cell missing. The figures change across rows and columns "
            "according to a hidden rule. Your job is to work out the rule and pick "
            "the option (A · E) that completes the grid."
        ),
        "pattern_tags": [
            "Shape changes", "Rotation", "Add or subtract",
            "Counting", "Color &amp; shading",
        ],
        "look_for_note": (
            "Patterns can combine multiple rules. Most matrices have one dominant "
            "rule running along rows and a second along columns."
        ),
        "tips": [
            ("Rows first.", "The pattern often runs more obviously along rows than columns."),
            ("Eliminate options.", "If you can\'t see the full pattern, you can usually rule out 2 · 3 options quickly."),
            ("Don\'t overthink.", "After about 30 seconds of being stuck, pick your best guess and move on."),
            ("Watch the timer.", "75 seconds is plenty if you don\'t get stuck on one cell."),
        ],
    },
    "numerical": {
        "short": "Numerical",
        "title": "Numerical Reasoning",
        "subtitle": "Read a chart or table, then answer a multiple-choice question about the data.",
        "options": "A · D",
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
            ("Use the calculator.", "Don\'t try to do percentages or ratios in your head under time pressure."),
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
            "statement. You choose <strong>True</strong> if the statement follows "
            "from the passage, <strong>False</strong> if it contradicts the passage, "
            "or <strong>Cannot Say</strong> if the passage does not give you enough "
            "information to decide."
        ),
        "pattern_tags": [
            "True", "False", "Cannot Say",
        ],
        "look_for_note": (
            "Use only what the passage says. If outside knowledge or common sense "
            "would be required to decide, the answer is almost always Cannot Say."
        ),
        "tips": [
            ("Stay literal.", "Don\'t bring outside knowledge or assumptions into the passage."),
            ("Watch qualifiers.", "Words like &lsquo;all&rsquo;, &lsquo;always&rsquo;, &lsquo;never&rsquo;, &lsquo;most&rsquo; often determine the answer."),
            ("Default to Cannot Say.", "If the passage does not directly address the statement, that is your answer."),
            ("Re-read the relevant sentence.", "Faster than re-reading the whole passage."),
        ],
    },
}




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


def _layer_overview() -> None:
    """Layer 1 overview shown once before the first theme intro.

    Three theme hero cards across the top (Logical · Numerical · Verbal),
    each with its own inline SVG illustration and stat strip. A compact
    "Before you begin" prep card below, then info banner + CTA.
    """
    ui.inject_global_styles()
    ui.header(meta=f"Candidate · {st.session_state.candidate_name}")

    ui.eyebrow("Stage 1 of 3 · Cognitive Assessment")
    ui.page_title(
        "Three reasoning themes, one timed sprint",
        "About 30 minutes total. Each theme has its own time limit per question.",
    )

    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

    # Three theme hero cards
    c1, c2, c3 = st.columns(3, gap="medium")
    with c1:
        ui.theme_card(
            icon_svg=ui.THEME_ICON_LOGICAL,
            meta="Theme 1",
            title="Logical Reasoning",
            desc=(
                "Abstract 3×3 matrix puzzles. Spot the pattern across rows "
                "and columns, then pick the figure that completes the grid."
            ),
            stats=[(f"{QUESTIONS_PER_THEME}", "Questions"), ("75 s", "Per question")],
        )
    with c2:
        ui.theme_card(
            icon_svg=ui.THEME_ICON_NUMERICAL,
            meta="Theme 2",
            title="Numerical Reasoning",
            desc=(
                "Short charts and tables followed by a multiple-choice "
                "question. Percentages, ratios, growth rates · calculator "
                "is recommended."
            ),
            stats=[(f"{QUESTIONS_PER_THEME}", "Questions"), ("90 s", "Per question")],
        )
    with c3:
        ui.theme_card(
            icon_svg=ui.THEME_ICON_VERBAL,
            meta="Theme 3",
            title="Verbal Reasoning",
            desc=(
                "Read a short passage, then judge a statement: True, False, "
                "or Cannot Say. Use only what the passage says · no outside "
                "knowledge."
            ),
            stats=[(f"{QUESTIONS_PER_THEME}", "Questions"), ("60 s", "Per question")],
        )

    st.markdown("<div style='height:1.25rem'></div>", unsafe_allow_html=True)

    # Compact prep checklist · single full-width card
    with ui.card("Before you begin"):
        ui.numbered_rule(
            1, "Pen and paper for working through problems.",
            severity="info",
        )
        ui.numbered_rule(
            2, "A calculator · the numerical theme uses percentages, ratios, and multi-step figures.",
            severity="info",
        )
        ui.numbered_rule(
            3, "A quiet, uninterrupted environment for the next ~30 minutes.",
            severity="info",
        )
        ui.numbered_rule(
            4, "A stable internet connection · your answers save automatically as you go.",
            severity="info",
        )
        ui.numbered_rule(
            5, "Time-outs count as incorrect, and answered questions cannot be revisited.",
            severity="info",
        )

    st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
    ui.info_banner(
        "Pick the best answer for each question · you will not see whether you got each one right.",
        icon="ℹ",
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


def _theme_intro(theme: str, theme_idx: int) -> None:
    """Per-theme intro shown before the first question of each theme.

    Asymmetric magazine-spread layout: a narrow editorial column on the
    left with the theme number set in huge typography and a stack of
    stats; a wider right column with the title, subtitle, and three
    editorial sections (Task / Patterns / Approach). Info banner + CTA
    close the page.
    """
    ui.inject_global_styles()
    ui.header(meta=f"Candidate {st.session_state.candidate_name}")

    seconds = time_limit_for(theme)
    label = THEME_LABELS[theme]

    # Build the editorial sections
    tags_html = (
        '<div class="cap-edit-tags">'
        + '<span class="tag-sep">·</span>'.join(
            f'<span>{t}</span>' for t in label["pattern_tags"]
        )
        + '</div>'
        + '<p class="cap-edit-note">' + label["look_for_note"] + '</p>'
    )
    steps_html = '<ol class="cap-edit-steps">' + "".join(
        f'<li><strong>{head}</strong> {body}</li>' for head, body in label["tips"]
    ) + '</ol>'

    section_2_eyebrow = (
        "Pattern types to look for" if theme == "logical" else
        ("What the data looks like" if theme == "numerical" else
         "How to read the answer choices")
    )

    ui.theme_spread(
        eyebrow=f"Stage 1 of 3 · Theme {theme_idx + 1} of 3",
        title=label["title"],
        subtitle=label["subtitle"],
        side_num=f"0{theme_idx + 1}",
        side_eyebrow=f"Theme {theme_idx + 1} of 3",
        stats=[
            (str(QUESTIONS_PER_THEME), "",  "Questions"),
            (str(seconds),              "s", "Per question"),
            (label["options"],          "",  "Options"),
        ],
        sections=[
            {
                "eyebrow": "The task",
                "body_html": '<p class="cap-edit-lead">' + label["setup_html"] + '</p>',
            },
            {
                "eyebrow": section_2_eyebrow,
                "body_html": tags_html,
            },
            {
                "eyebrow": "How to approach it",
                "body_html": steps_html,
            },
        ],
    )

    ui.info_banner(
        f"{seconds} seconds per question. Time-outs count as incorrect, "
        f"and you cannot revisit a question once it's answered.",
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
        st.session_state.l1_question_started_at = time.time()
        st.rerun()

def _render_question(
    candidate_id: str, theme: str, theme_idx: int, question_idx: int,
    question, total: int,
) -> None:
    """Render one Layer 1 question with the standardised typography +
    a sharp header bar (eyebrow + progress rail + countdown timer pill)
    and a properly-sized question stem.
    """
    seconds = time_limit_for(theme)

    # Tick every second
    st_autorefresh(interval=1000, key=f"l1_tick_{theme}_{question_idx}")

    started_at = st.session_state.l1_question_started_at or time.time()
    if st.session_state.l1_question_started_at is None:
        st.session_state.l1_question_started_at = started_at

    elapsed = time.time() - started_at
    remaining = max(0, int(seconds - elapsed))

    # ── Page chrome + header bar ─────────────────────────────────────────
    ui.inject_global_styles()
    ui.header(meta=f"Candidate · {st.session_state.candidate_name}")

    label = THEME_LABELS[theme]
    ui.question_progress_bar(
        idx=question_idx,
        total=total,
        remaining=remaining,
        seconds=seconds,
        eyebrow_text=(
            f"Stage 1 of 3 · {label['title']} · Question {question_idx + 1} of {total}"
        ),
    )

    # ── Question card ────────────────────────────────────────────────────
    with ui.card(None):
        # Optional question image (chart/figure/sequence)
        if question.chart_path:
            try:
                st.image(question.chart_path)
            except Exception:
                pass

        # Big bold question stem
        ui.question_stem(question.question_text)

        # Optional second image (abstract: A · E option grid)
        if question.answer_image_path:
            try:
                st.image(question.answer_image_path)
            except Exception:
                pass

        # Options · dynamic count, support 3 / 4 / 5
        n_opts = len(question.options)
        letters = ["A", "B", "C", "D", "E"][:n_opts]
        selection_key = f"l1_{theme}_{question_idx}_selection"

        # Letter-only rendering is reserved for abstract-reasoning items
        # where the letters are baked into the answer-grid image.
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

        # Auto-submit on timeout OR manual submit
        submit_clicked = st.button(
            "Submit answer",
            type="primary",
            disabled=(chosen_letter is None),
            key=f"submit_{theme}_{question_idx}",
            use_container_width=True,
        )
        timed_out = remaining <= 0

    if submit_clicked or timed_out:
        _save_and_advance(
            candidate_id, theme, theme_idx, question_idx, question,
            chosen_letter, int(elapsed), timed_out, seconds,
        )

def _save_and_advance(
    candidate_id: str, theme: str, theme_idx: int, question_idx: int,
    question, chosen_letter: str | None, elapsed: int, timed_out: bool,
    seconds: int,
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
        time_taken_seconds=min(elapsed, seconds),
    )

    # reset timer for next question
    st.session_state.l1_question_started_at = time.time()
    st.session_state.l1_question_idx = question_idx + 1
    st.rerun()


def _finish_theme(candidate_id: str, theme: str) -> None:
    rows = [r for r in db.get_layer1_results(candidate_id) if r["theme"] == theme]
    correct = sum(1 for r in rows if r["is_correct"])
    st.session_state.l1_theme_scores[theme] = theme_score(correct, QUESTIONS_PER_THEME)
    st.session_state.l1_theme_idx += 1
    st.session_state.l1_question_idx = 0
    st.session_state.l1_question_started_at = None
    st.rerun()


def _finish_layer(candidate_id: str) -> None:
    """All three themes done. Move on to Layer 2 with no score reveal."""
    st.title("Layer 1 Complete")
    st.success(
        "Nice work · you've finished the cognitive assessment. Your full results "
        "will be shown after you complete all three layers."
    )

    st.markdown(
        """
        ---
        **Next · Layer 2: Firm Simulation**

        You'll run a consulting firm for 8 simulated weeks. Assign consultants to
        projects, manage cash and reputation, and respond to events as they
        happen. **20 minutes** in one continuous timer.
        """
    )

    if st.button("Begin Layer 2", type="primary", use_container_width=True):
        advance_stage("layer2")
