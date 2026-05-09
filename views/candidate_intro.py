"""Candidate intro page: personalised welcome + 3-layer journey overview."""

from __future__ import annotations

import streamlit as st

from . import _design as ui
from .state import advance_stage


# The three layers presented as a vertical journey timeline. Edit here if
# durations or descriptions change — the welcome page picks this up
# automatically.
JOURNEY = [
    {
        "num": "1",
        "meta": "~30 min · 30 questions",
        "title": "Cognitive Assessment",
        "desc": (
            "Three timed themes — logical, numerical, and verbal reasoning. "
            "Each question has its own time limit, and you cannot revisit "
            "an answer once it's submitted."
        ),
    },
    {
        "num": "2",
        "meta": "~20 min · 8 simulated weeks",
        "title": "Staffing Simulation",
        "desc": (
            "Step into the shoes of a resource manager. Assign consultants "
            "to projects under realistic constraints — a continuous "
            "20-minute timer, with a Week 6 trade-off decision."
        ),
    },
    {
        "num": "3",
        "meta": "~15 min · 5 voice questions",
        "title": "AI-Led Interview",
        "desc": (
            "Five behavioural questions, each with a live AI follow-up. "
            "Speak naturally; you can re-record any answer once. A typed "
            "fallback is always available."
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
        "Three short exercises across roughly 60 minutes. Take your time, "
        "and we'll share personalised feedback at the end.",
    )

    # ── KPI strip — at-a-glance facts before the journey ─────────────────
    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
    k1, k2, k3, k4 = st.columns(4, gap="small")
    with k1:
        ui.metric("3", "Layers")
    with k2:
        ui.metric("~60 min", "Total time")
    with k3:
        ui.metric("Auto-save", "Resume any time")
    with k4:
        ui.metric("End-of-session", "Personalised feedback")

    # ── Vertical journey ─────────────────────────────────────────────────
    ui.journey_timeline(JOURNEY)

    # ── Quiet reassurance + setup banner ─────────────────────────────────
    ui.info_banner(
        "Find a quiet spot, make sure your microphone works, and give "
        "yourself uninterrupted time. Your progress saves automatically — "
        "if you close the tab, sign back in with the same email to resume.",
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
