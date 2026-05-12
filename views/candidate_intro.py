"""Candidate intro page: personalised welcome + 3-layer journey overview."""

from __future__ import annotations

import streamlit as st

from . import _design as ui
from .state import advance_stage


# The three layers presented as a vertical journey timeline. Edit here if
# durations or descriptions change · the welcome page picks this up
# automatically.
JOURNEY = [
    {
        "num": "1",
        "meta": "Layer 1 · ~35 minutes",
        "title": "Cognitive Assessment",
        "desc": (
            "30 timed reasoning questions across logical, numerical, "
            "and verbal themes."
        ),
    },
    {
        "num": "2",
        "meta": "Layer 2 · ~20 minutes",
        "title": "Staffing Simulation",
        "desc": (
            "An 8-week firm simulation where you act as a resource manager "
            "assigning consultants to projects under real-world constraints."
        ),
    },
    {
        "num": "3",
        "meta": "Layer 3 · ~16 minutes",
        "title": "AI-Led Interview",
        "desc": (
            "Four voice-recorded questions with a live follow-up for each."
        ),
    },
]


def render() -> None:
    ui.inject_global_styles()
    ui.header(meta=f"Candidate · {st.session_state.candidate_name}")

    first_name = st.session_state.candidate_name.split()[0]

    ui.eyebrow("Welcome · let's begin")
    ui.page_title(
        f"Welcome, {first_name}",
        "Over the next ~70 minutes, you'll complete three short exercises "
        "that help us understand how you think, solve problems, and "
        "communicate.",
    )

    # ── KPI strip · at-a-glance facts before the journey ─────────────────
    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
    k1, k2, k3, k4 = st.columns(4, gap="small")
    with k1:
        ui.metric("3", "Layers")
    with k2:
        ui.metric("~70 min", "Total time")
    with k3:
        ui.metric("Sign in to your current layer", "within 2 hours")
    with k4:
        ui.metric("End-of-session", "Personalised feedback")

    # ── Vertical journey ─────────────────────────────────────────────────
    ui.journey_timeline(JOURNEY)

    # ── Quiet reassurance + setup banner ─────────────────────────────────
    # Team v9 obligatory copy on autosave + closing line, plus our
    # 2-hour resume window phrasing as the practical detail.
    ui.info_banner(
        "Your answers are saved as you go. If you accidentally close the "
        "tab, you can return and resume by entering the same email "
        "(within two hours, you will pick up at the start of the last "
        "layer you fully went through). When you finish, you will receive "
        "personalised feedback on your performance.",
        icon="ℹ",
    )
    ui.info_banner(
        "Find a quiet spot, make sure your microphone works, and give "
        "yourself uninterrupted time. Good luck.",
        icon="ℹ",
    )

    st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)

    if st.button(
        "Begin Layer 1",
        type="primary",
        use_container_width=True,
        key="candidate_intro_begin",
    ):
        advance_stage("layer1")
