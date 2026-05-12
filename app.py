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
# Compact dev/QA nav strip rendered above every page. Designed for
# prototype testing so the team can hop between stages without clicking
# through the full candidate flow. Strip this function (or wrap it back
# in a ?dev=1 gate) before shipping the assessment to real candidates.

def _inject_dev_nav_styles() -> None:
    """Inject scoped CSS for the dev nav popover. Selectors target
    Streamlit's stPopover / stPopoverBody data-testids so the rest of
    the app's button styling is untouched."""
    st.markdown(
        """
        <style>
        /* Popover trigger: small, dev-tool styled, cyan accent */
        .stApp div[data-testid="stPopover"] > div > button {
            padding: 0.28rem 0.65rem !important;
            font-size: 0.72rem !important;
            font-weight: 700 !important;
            letter-spacing: 0.18em !important;
            text-transform: uppercase !important;
            font-family: Ubuntu, sans-serif !important;
            background: rgba(29,184,242,0.06) !important;
            border: 1px solid rgba(29,184,242,0.35) !important;
            color: #1DB8F2 !important;
            border-radius: 4px !important;
            min-height: 0 !important;
            line-height: 1.4 !important;
            box-shadow: none !important;
        }
        .stApp div[data-testid="stPopover"] > div > button:hover {
            background: rgba(29,184,242,0.14) !important;
            border-color: #1DB8F2 !important;
            color: #1DB8F2 !important;
        }
        /* Popover panel surface */
        .stApp div[data-testid="stPopoverBody"] {
            background: #15233E !important;
            border: 1px solid #28387A !important;
            border-radius: 6px !important;
            min-width: 580px !important;
            box-shadow: 0 12px 32px rgba(0,0,0,0.45) !important;
        }
        /* Compact secondary buttons inside the popover */
        .stApp div[data-testid="stPopoverBody"] .stButton > button[kind="secondary"] {
            padding: 0.3rem 0.4rem !important;
            font-size: 0.74rem !important;
            font-weight: 600 !important;
            font-family: Ubuntu, sans-serif !important;
            min-height: 0 !important;
            line-height: 1.25 !important;
            border-radius: 4px !important;
            background: #1A2548 !important;
            border: 1px solid #28387A !important;
            color: #C5D1E8 !important;
            box-shadow: none !important;
            letter-spacing: 0.02em !important;
        }
        .stApp div[data-testid="stPopoverBody"] .stButton > button[kind="secondary"]:hover {
            background: #1E2D55 !important;
            border-color: #1DB8F2 !important;
            color: #FFFFFF !important;
        }
        /* Primary button (e.g. Create test candidate) inside popover */
        .stApp div[data-testid="stPopoverBody"] .stButton > button[kind="primary"] {
            padding: 0.4rem 0.7rem !important;
            font-size: 0.78rem !important;
            min-height: 0 !important;
            border-radius: 4px !important;
            box-shadow: none !important;
        }
        /* Tiny eyebrow rows inside the popover */
        .cap-dev-section {
            color: #1DB8F2;
            font-size: 0.62rem;
            font-weight: 700;
            letter-spacing: 0.22em;
            text-transform: uppercase;
            margin: 0.55rem 0 0.3rem 0;
        }
        /* Status pill at the top of the popover */
        .cap-dev-stage-pill {
            display: inline-block;
            padding: 0.2rem 0.55rem;
            border: 1px solid #28387A;
            border-radius: 4px;
            background: #1A2548;
            color: #C5D1E8;
            font-size: 0.72rem;
            letter-spacing: 0.02em;
            font-family: ui-monospace, Menlo, monospace;
            margin: 0.1rem 0 0.4rem 0;
        }
        .cap-dev-stage-pill strong {
            color: #1DB8F2;
            font-weight: 700;
            letter-spacing: 0.04em;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _nav_bar() -> None:
    _inject_dev_nav_styles()

    has_candidate = bool(st.session_state.get("candidate_id"))
    stage = st.session_state.get("stage", "-") if has_candidate else "no candidate"
    trigger = f"⚙ Dev nav · {stage}"

    with st.popover(trigger, use_container_width=False):
        # No candidate yet: setup affordance only.
        if not has_candidate:
            st.markdown(
                '<div class="cap-dev-section">Test candidate</div>',
                unsafe_allow_html=True,
            )
            st.caption(
                "No candidate yet · create a test one to enable stage jumps."
            )
            if st.button(
                "Create test candidate",
                use_container_width=True,
                key="nav_make_candidate",
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
            return

        # Active candidate: status pill + page jumps + Layer 1 sub-jumps.
        cname = st.session_state.get("candidate_name", "")
        st.markdown(
            f'<div class="cap-dev-stage-pill">'
            f'candidate · {cname} · stage: <strong>{stage}</strong>'
            f'</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div class="cap-dev-section">Page jumps</div>',
            unsafe_allow_html=True,
        )
        pages = [
            ("Landing",   "landing"),
            ("Intro",     "intro"),
            ("Layer 1",   "layer1"),
            ("Layer 2",   "layer2"),
            ("Layer 3",   "layer3"),
            ("Results",   "results"),
            ("Recruiter", "recruiter"),
            ("Reset",     "reset"),
        ]
        cols = st.columns(len(pages))
        for i, (label, target) in enumerate(pages):
            with cols[i]:
                if st.button(
                    label, key=f"nav_{target}", use_container_width=True,
                ):
                    _jump_to(target)

        st.markdown(
            '<div class="cap-dev-section">Layer 1 themes</div>',
            unsafe_allow_html=True,
        )
        sub_pages = []
        for theme in THEMES:
            sub_pages.append((f"{theme.title()} intro", theme, "intro"))
            sub_pages.append((f"{theme.title()} Q1",    theme, "q1"))
        cols = st.columns(len(sub_pages))
        for i, (label, theme, kind) in enumerate(sub_pages):
            with cols[i]:
                if st.button(
                    label,
                    key=f"nav_l1_{theme}_{kind}",
                    use_container_width=True,
                ):
                    _jump_layer1(theme, kind)


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




# Two-hour TTL for candidate attempts. Throttled per-session so the
# cleanup query doesn't fire on every Streamlit rerun (which can happen
# on every keystroke). One minute is plenty - the user-visible behavior
# is "your data is gone after roughly 2 hours" and a 60s slack window
# on top of that doesn't matter.
_PURGE_TTL_SECONDS = 2 * 60 * 60
_PURGE_THROTTLE_SECONDS = 60


def _maybe_purge_expired_candidates() -> None:
    try:
        now = time.time()
        last = st.session_state.get("_last_purge_at", 0.0)
        if now - last < _PURGE_THROTTLE_SECONDS:
            return
        st.session_state["_last_purge_at"] = now
        db.purge_expired_candidates(ttl_seconds=_PURGE_TTL_SECONDS)
    except Exception:
        # A failed purge should never take the app down.
        pass


def main() -> None:
    st.set_page_config(
        page_title="Capgemini Invent · Consulting Assessment",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    # Initialize DB once per process. Wrapped in try/except so a freshly
    # seeded container (Streamlit Cloud recycles containers after sleep,
    # which gives us a fresh filesystem and a brand-new DB) can never
    # take the whole app down on its first request. Inside the success
    # path we use DEFAULT_RECRUITER_PASSWORD directly because that's the
    # constant the merged team-v9 db.py exposes; the old wrapper function
    # get_recruiter_password() was removed in the merge.
    if "db_initialized" not in st.session_state:
        try:
            freshly_seeded = db.init_db()
            st.session_state.db_initialized = True
            if freshly_seeded:
                print("=" * 60)
                print("First-time setup complete.")
                pw = getattr(db, "DEFAULT_RECRUITER_PASSWORD", "(see secrets)")
                print(f"Default recruiter login: {db.DEFAULT_RECRUITER_USERNAME} / {pw}")
                print("=" * 60)
        except Exception as exc:
            st.session_state.db_initialized = True
            print(f"[init_db] non-fatal: {type(exc).__name__}: {exc}")

    init_session_state()

    # 2-hour TTL on incomplete candidate attempts.
    # Throttled so we hit the DB at most once per minute per session,
    # not once per Streamlit rerun (which can fire every keystroke).
    # Completed assessments are NOT purged, so the recruiter dashboard
    # keeps full history.
    _maybe_purge_expired_candidates()

    # Safety net: if the candidate's session points at a candidate_id
    # that no longer exists in the DB (their attempt was purged after
    # 2 hours OR their teammate cleared the DB), wipe the session and
    # send them back to landing with a friendly message instead of
    # crashing on the next DB call.
    if st.session_state.get("candidate_id"):
        if db.get_candidate(st.session_state.candidate_id) is None:
            reset_candidate_state()
            st.info(
                "Your session has expired. Sessions are kept for two hours - "
                "please enter your details again to start a fresh attempt."
            )
            st.rerun()
            return

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
