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

    ui.eyebrow("Consulting recruitment assessment")
    ui.page_title(
        "A focused, modern hiring experience.",
        "Cognitive reasoning, a firm-management simulation, and an AI-led interview — "
        "completed in one session.",
    )

    col1, col2 = st.columns(2, gap="large")

    with col1:
        with ui.card("For Candidates"):
            st.markdown(
                "<p>Begin a new assessment, or resume one that's already in progress. "
                "The full session takes about 60 minutes end to end.</p>",
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
        with ui.card("For Recruiters"):
            st.markdown(
                "<p>Access the dashboard to review completed assessments, "
                "filter candidates, and export results.</p>",
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
    st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)
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

    # check for an in-progress session
    existing = db.find_candidate_by_email(email.strip().lower())
    if existing and existing["current_stage"] not in ("done",):
        st.info(
            f"Found an in-progress session from {existing['started_at'][:10]}. "
            f"Resuming at stage: **{existing['current_stage']}**."
        )
        resume_from_db(existing)
        st.rerun()
        return

    # new candidate
    candidate_id = str(uuid.uuid4())
    db.create_candidate(candidate_id, name.strip(), email.strip().lower())

    st.session_state.mode = "candidate"
    st.session_state.candidate_id = candidate_id
    st.session_state.candidate_name = name.strip()
    st.session_state.candidate_email = email.strip().lower()
    st.session_state.stage = "intro"
    st.rerun()


def _recruiter_form() -> None:
    st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)
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
