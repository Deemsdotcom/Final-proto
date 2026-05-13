"""Landing page: candidate entry or recruiter login."""

from __future__ import annotations

import re
import uuid

import streamlit as st

from database import db

from . import _design as ui
from .state import resume_from_db

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def render() -> None:
    ui.inject_global_styles()
    ui.header()

    # ── Hero ──────────────────────────────────────────────────────────────
    # Team v9 verbatim title and caption.
    ui.eyebrow("Welcome")
    ui.page_title(
        "Capgemini Invent Consulting Assessment",
        "Cognitive reasoning, staffing simulation, and voice-led interview in one session.",
    )

    # ── KPI stat bar ──────────────────────────────────────────────────────
    # CSS grid (not st.columns) so the three tiles stay on one line at
    # all viewport widths.
    st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div style="display:grid;grid-template-columns:repeat(3,1fr);'
        'gap:0.6rem;margin:0.2rem 0 0.4rem 0;">'
        '<div class="cap-metric"><span class="val">3</span>'
        '<span class="lbl">Assessment Layers</span></div>'
        '<div class="cap-metric"><span class="val">~70 min</span>'
        '<span class="lbl">Total Duration</span></div>'
        '<div class="cap-metric"><span class="val">AI</span>'
        '<span class="lbl">Powered Interview</span></div>'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height:2rem'></div>", unsafe_allow_html=True)

    # ── Action cards ──────────────────────────────────────────────────────
    col1, col2 = st.columns(2, gap="large")

    with col1:
        with ui.card("I'm a Candidate"):
            st.markdown(
                "<p>Start or resume your assessment. Takes roughly "
                "70 minutes end to end.</p>",
                unsafe_allow_html=True,
            )
            if st.button(
                "Begin as Candidate",
                type="primary",
                use_container_width=True,
                key="btn_candidate",
            ):
                st.session_state.mode = "candidate_form"
                st.rerun()

    with col2:
        with ui.card("Recruiter Login"):
            st.markdown(
                "<p>Access the dashboard to review completed assessments.</p>",
                unsafe_allow_html=True,
            )
            if st.button(
                "Recruiter Login",
                type="secondary",
                use_container_width=True,
                key="btn_recruiter",
            ):
                st.session_state.mode = "recruiter_form"
                st.rerun()

    if st.session_state.mode == "candidate_form":
        _candidate_form()
    elif st.session_state.mode == "recruiter_form":
        _recruiter_form()


def _candidate_form() -> None:
    st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)
    with ui.card("Start your assessment"):
        with st.form("candidate_form"):
            name = st.text_input("Full name", max_chars=100)
            email = st.text_input("Email address", max_chars=100)
            submitted = st.form_submit_button("Continue", type="primary")

    if not submitted:
        return

    if not name or len(name.strip()) < 2:
        st.error("Please enter your full name.")
        return
    if not EMAIL_RE.match(email.strip()):
        st.error("Please enter a valid email address.")
        return

    existing = db.find_candidate_by_email(email.strip().lower())
    if existing and existing["current_stage"] not in ("done",):
        # Coarse resume: the candidate goes back to the START of whichever
        # layer they were in. Earlier completed layers are preserved.
        # Outside the 2-hour TTL window the row would have been purged
        # entirely, so a same-email login here always lands inside a
        # warm session.
        nice = {
            "intro": "the welcome screen",
            "layer1": "the start of Layer 1",
            "layer2": "the start of Layer 2",
            "layer3": "the start of Layer 3",
            "results": "your results",
            "done": "your completed assessment",
        }.get(existing['current_stage'], existing['current_stage'])
        st.info(
            f"Welcome back. Picking up where you left off: **{nice}**."
        )
        resume_from_db(existing)
        st.rerun()
        return

    candidate_id = str(uuid.uuid4())
    db.create_candidate(candidate_id, name.strip(), email.strip().lower())

    st.session_state.mode = "candidate"
    st.session_state.candidate_id = candidate_id
    st.session_state.candidate_name = name.strip()
    st.session_state.candidate_email = email.strip().lower()
    st.session_state.stage = "intro"
    st.rerun()


def _recruiter_form() -> None:
    st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)
    with ui.card("Recruiter login"):
        with st.form("recruiter_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log in", type="primary")

    if not submitted:
        return

    if db.verify_recruiter(username, password):
        st.session_state.mode = "recruiter"
        st.session_state.recruiter_authed = True
        st.session_state.stage = "recruiter_dashboard"
        st.rerun()
    else:
        st.error("Invalid credentials.")
