"""Streamlit entry point.

Routes to the right view based on st.session_state.stage and mode.
Everything kicks off from here.

Run with:
    streamlit run app.py
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


THEMES = ["logical", "numerical", "verbal"]


# ── Top nav bar (prototype-mode) ──────────────────────────────────────────
# Always-visible navigation strip rendered at the very top of every page.
# Each button jumps directly to that stage. Designed for prototype testing
# so the team can hop around without clicking through the full flow each
# time. Strip this function (or wrap it back in a ?dev=1 gate) before
# shipping the assessment to real candidates.

def _nav_bar() -> None:
    # Brand-aligned styling: dark navy strip with cyan accents matching
    # the rest of the app. Sits ABOVE the page header that each view
    # renders, so it's always the first thing on screen.
    st.markdown(
        """
        <style>
        .cap-nav-bar {
            background: #15233E;
            border: 1px solid #28387A;
            border-radius: 8px;
            padding: 0.4rem 0.6rem;
            margin: 0 0 1rem 0;
            display: flex;
            align-items: center;
            gap: 0.4rem;
            font-family: Ubuntu, sans-serif;
        }
        .cap-nav-label {
            color: #1DB8F2;
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.18em;
            text-transform: uppercase;
            margin-right: 0.5rem;
            white-space: nowrap;
        }
        /* Make the nav buttons themselves compact */
        .cap-nav-row .stButton > button {
            width: 100%;
            padding: 0.4rem 0.5rem !important;
            font-size: 0.85rem !important;
            font-weight: 600 !important;
            min-height: auto !important;
            border-radius: 6px !important;
        }
        </style>
        <div class="cap-nav-bar">
            <span class="cap-nav-label">Quick nav</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Test candidate setup row (only when no candidate yet) ────────────
    if not st.session_state.get("candidate_id"):
        c1, c2 = st.columns([3, 1])
        with c1:
            st.caption(
                "No candidate yet — create a test one to enable stage jumps."
            )
        with c2:
            if st.button(
                "Create test candidate",
                use_container_width=True, key="nav_make_candidate",
                type="primary",
            ):
                cid = str(uuid.uuid4())
                db.create_candidate(
                    cid, "Dev Tester", f"dev+{cid[:8]}@test.local"
                )
                st.session_state.mode = "candidate"
                st.session_state.candidate_id = cid
                st.session_state.candidate_name = "Dev Tester"
                st.session_state.candidate_email = f"dev+{cid[:8]}@test.local"
                st.session_state.stage = "intro"
                st.rerun()
        st.markdown("---")
        return  # no point rendering the rest until a candidate exists

    # ── Main page-jump row ───────────────────────────────────────────────
    st.markdown('<div class="cap-nav-row">', unsafe_allow_html=True)
    cols = st.columns(8)
    pages = [
        ("Landing",         "landing"),
        ("Intro",           "intro"),
        ("Layer 1",         "layer1"),
        ("Layer 2",         "layer2"),
        ("Layer 3",         "layer3"),
        ("Results",         "results"),
        ("Recruiter",       "recruiter"),
        ("Reset",           "reset"),
    ]
    for i, (label, target) in enumerate(pages):
        with cols[i]:
            if st.button(label, key=f"nav_{target}", use_container_width=True):
                _jump_to(target)
    st.markdown("</div>", unsafe_allow_html=True)

    # ── Layer 1 sub-jumps (themes) ───────────────────────────────────────
    st.caption("Layer 1 themes")
    cols = st.columns(6)
    sub_pages = []
    for theme in THEMES:
        sub_pages.append((f"{theme.title()} intro", theme, "intro"))
        sub_pages.append((f"{theme.title()} Q1",    theme, "q1"))
    for i, (label, theme, kind) in enumerate(sub_pages):
        with cols[i]:
            if st.button(
                label, key=f"nav_l1_{theme}_{kind}", use_container_width=True,
            ):
                _jump_layer1(theme, kind)
    st.markdown("---")


def _jump_to(target: str) -> None:
    if target == "landing":
        reset_candidate_state()
    elif target == "recruiter":
        st.session_state.mode = "recruiter"
        st.session_state.recruiter_authed = True
        st.session_state.stage = "recruiter_dashboard"
    elif target == "reset":
        reset_candidate_state()
    else:
        st.session_state.stage = target
        if target == "layer1":
            st.session_state.l1_overview_seen = False
        if st.session_state.candidate_id:
            db.set_stage(st.session_state.candidate_id, target)
    st.rerun()


def _jump_layer1(theme: str, kind: str) -> None:
    idx = THEMES.index(theme)
    st.session_state.stage = "layer1"
    st.session_state.l1_overview_seen = True
    st.session_state.l1_theme_idx = idx
    st.session_state.l1_question_idx = 0
    for t in THEMES:
        st.session_state.pop(f"l1_{t}_started", None)
    if kind == "q1":
        st.session_state[f"l1_{theme}_started"] = True
        st.session_state.l1_question_started_at = time.time()
    st.rerun()


# ── Main ─────────────────────────────────────────────────────────────────


def main() -> None:
    st.set_page_config(
        page_title="Capgemini Invent — Consulting Assessment",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="collapsed",
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

    # ALWAYS-VISIBLE quick-nav strip. Remove this call before shipping
    # the assessment to real candidates.
    _nav_bar()

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
