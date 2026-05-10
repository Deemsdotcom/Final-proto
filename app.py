"""Streamlit entry point.

Routes to the right view based on st.session_state.stage and mode.
Everything kicks off from here.

Run with:
    streamlit run app.py

Dev mode: append ?dev=1 to the URL to reveal a sidebar with one-click
stage navigation. Useful for testing UI changes without going through
the full assessment each time.
"""

from __future__ import annotations

import time
import uuid

import streamlit as st

from database import db
from views import (
    candidate_intro,
    candidate_results,
    landing,
    layer1,
    layer2,
    layer3,
    recruiter_dashboard,
)
from views.state import init_session_state, reset_candidate_state


# ── Dev sidebar ──────────────────────────────────────────────────────────
# Visible only when ?dev=1 is in the URL. Lets the developer set up a
# test candidate in one click and jump straight to any stage of the
# assessment, including specific Layer 1 theme intros and question
# screens. Candidates never see this because they don't add the param.

THEMES = ["logical", "numerical", "verbal"]


def _dev_sidebar() -> None:
    if st.query_params.get("dev") != "1":
        return

    # Override the global CSS that hides the toolbar (and therefore the
    # sidebar-toggle button) so the sidebar is always reachable here.
    # Also render a small fixed "DEV MODE" badge so it is obvious the
    # param took effect.
    st.markdown(
        """
        <style>
        .stApp [data-testid="stToolbar"] {
            visibility: visible !important;
            height: auto !important;
        }
        .stApp [data-testid="stSidebar"] {
            display: block !important;
        }
        .cap-dev-badge {
            position: fixed;
            top: 0.6rem;
            right: 1rem;
            background: #1DB8F2;
            color: #121A38;
            font-family: Ubuntu, sans-serif;
            font-weight: 700;
            font-size: 0.78rem;
            letter-spacing: 0.18em;
            padding: 0.3rem 0.7rem;
            border-radius: 999px;
            z-index: 9999;
            box-shadow: 0 4px 16px rgba(29,184,242,0.4);
        }
        </style>
        <div class="cap-dev-badge">DEV MODE</div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.markdown("### Dev navigation")
        st.caption("Visible because URL has ?dev=1. Append/remove the param to toggle.")

        # ── Test candidate setup ─────────────────────────────────────────
        if not st.session_state.get("candidate_id"):
            if st.button(
                "Create test candidate", use_container_width=True,
                key="dev_make_candidate",
            ):
                cid = str(uuid.uuid4())
                db.create_candidate(cid, "Dev Tester", f"dev+{cid[:8]}@test.local")
                st.session_state.mode = "candidate"
                st.session_state.candidate_id = cid
                st.session_state.candidate_name = "Dev Tester"
                st.session_state.candidate_email = f"dev+{cid[:8]}@test.local"
                st.session_state.stage = "intro"
                st.rerun()
        else:
            st.caption(
                f"Candidate: **{st.session_state.candidate_name}** · "
                f"`{(st.session_state.candidate_id or '')[:8]}...`"
            )
            if st.button(
                "Reset to landing", use_container_width=True,
                key="dev_reset",
            ):
                reset_candidate_state()
                st.rerun()

        st.divider()
        st.markdown("**Jump to stage**")

        # Generic stage jumps
        for label, stage in [
            ("Candidate intro", "intro"),
            ("Layer 1 — overview", "layer1"),
            ("Layer 2 — simulation", "layer2"),
            ("Layer 3 — interview", "layer3"),
            ("Results", "results"),
        ]:
            if st.button(
                label, key=f"dev_jump_{stage}", use_container_width=True,
                disabled=not st.session_state.get("candidate_id"),
            ):
                st.session_state.stage = stage
                if stage == "layer1":
                    # Show the overview, not skip past it.
                    st.session_state.l1_overview_seen = False
                if st.session_state.candidate_id:
                    db.set_stage(st.session_state.candidate_id, stage)
                st.rerun()

        # Recruiter dashboard — special, doesn't need a candidate
        st.divider()
        if st.button(
            "Recruiter dashboard", use_container_width=True,
            key="dev_jump_recruiter",
        ):
            st.session_state.mode = "recruiter"
            st.session_state.recruiter_authed = True
            st.session_state.stage = "recruiter_dashboard"
            st.rerun()

        # ── Layer 1 sub-navigation ──────────────────────────────────────
        st.divider()
        st.markdown("**Layer 1 sub-pages**")

        if st.button(
            "Skip overview → first theme intro",
            use_container_width=True, key="dev_l1_skip_overview",
            disabled=not st.session_state.get("candidate_id"),
        ):
            st.session_state.stage = "layer1"
            st.session_state.l1_overview_seen = True
            st.session_state.l1_theme_idx = 0
            st.session_state.l1_question_idx = 0
            for t in THEMES:
                st.session_state.pop(f"l1_{t}_started", None)
            st.rerun()

        for idx, theme in enumerate(THEMES):
            cols = st.sidebar.columns(2)
            with cols[0]:
                if st.button(
                    f"{theme.title()} intro",
                    key=f"dev_l1_intro_{theme}",
                    use_container_width=True,
                    disabled=not st.session_state.get("candidate_id"),
                ):
                    st.session_state.stage = "layer1"
                    st.session_state.l1_overview_seen = True
                    st.session_state.l1_theme_idx = idx
                    st.session_state.l1_question_idx = 0
                    for t in THEMES:
                        st.session_state.pop(f"l1_{t}_started", None)
                    st.rerun()
            with cols[1]:
                if st.button(
                    f"{theme.title()} Q1",
                    key=f"dev_l1_q1_{theme}",
                    use_container_width=True,
                    disabled=not st.session_state.get("candidate_id"),
                ):
                    st.session_state.stage = "layer1"
                    st.session_state.l1_overview_seen = True
                    st.session_state.l1_theme_idx = idx
                    st.session_state.l1_question_idx = 0
                    st.session_state[f"l1_{theme}_started"] = True
                    st.session_state.l1_question_started_at = time.time()
                    st.rerun()


# ── Main ─────────────────────────────────────────────────────────────────


def main() -> None:
    st.set_page_config(
        page_title="Capgemini Invent — Consulting Assessment",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state=(
            "expanded" if st.query_params.get("dev") == "1" else "collapsed"
        ),
    )

    # Initialize DB once per process
    if "db_initialized" not in st.session_state:
        freshly_seeded = db.init_db()
        st.session_state.db_initialized = True
        if freshly_seeded:
            print("=" * 60)
            print("First-time setup complete.")
            print(f"Default recruiter login: {db.DEFAULT_RECRUITER_USERNAME} / {db.get_recruiter_password()}")
            print("=" * 60)

    init_session_state()

    # Dev navigation sidebar (no-op when ?dev=1 is not in the URL)
    _dev_sidebar()

    mode = st.session_state.mode
    stage = st.session_state.stage

    # Recruiter flow
    if mode == "recruiter" and st.session_state.recruiter_authed:
        recruiter_dashboard.render()
        return

    # Candidate flow (only once they've been created in DB)
    if mode == "candidate" and st.session_state.candidate_id:
        if stage == "intro":
            candidate_intro.render()
        elif stage == "layer1":
            layer1.render()
        elif stage == "layer2":
            layer2.render()
        elif stage == "layer3":
            layer3.render()
        elif stage in ("results", "done"):
            candidate_results.render()
        else:
            # unknown stage, fall back to landing
            candidate_intro.render()
        return

    # Default: landing page
    landing.render()


if __name__ == "__main__":
    main()
