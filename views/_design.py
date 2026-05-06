"""Design system: shared CSS injection + reusable Streamlit components.

Implements the Capgemini Invent dark visual language used across all pages.
Anything style-related that can't be expressed via Streamlit's built-in
theme (.streamlit/config.toml) lives here.

The public surface is a small set of helpers:

- inject_global_styles(): CSS for the whole app. Call once near the top of
  every page render() — it is idempotent (re-injecting is harmless because
  the CSS is wrapped in a <style> tag and overwrites itself).
- header(): the top brand bar (Capgemini Invent wordmark + tagline).
- eyebrow(): the small all-caps label above a heading
  ("STAGE 2 OF 3").
- page_title(): the bold heading + optional subtitle pattern.
- card(): context manager that wraps content in a rounded surface card.
- numbered_rule(): one entry in a "rules to follow" card list.
- info_banner(): the soft cyan banner with an icon and a sentence
  (used above CTAs).

Color tokens are kept as Python constants so view code can reference them
without sprinkling hex values around.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

import streamlit as st

# ----- Capgemini Invent palette -----------------------------------------
# These mirror the brand reference: deep navy + a ladder of Capgemini
# blues + the standard semantic colors for warnings/errors.

NAVY_DEEP = "#0B1729"      # page background
NAVY_CARD = "#15233E"      # card surface
NAVY_CARD_2 = "#1E2E4A"    # nested item surface (darker than card)
NAVY_BORDER = "#26365A"    # 1px borders on cards / inputs

BLUE_PRIMARY = "#1493D4"   # primary CTA — "Begin Game"
BLUE_CYAN = "#1EB4FF"      # eyebrow text + small accents
BLUE_ACCENT = "#5BC0EB"    # info banner background tint
BLUE_DEEP = "#0070AD"      # Capgemini classic blue (secondary)

TEXT_PRIMARY = "#FFFFFF"
TEXT_SECONDARY = "#94A3B8"  # muted gray-blue for subtitles / help text
TEXT_MUTED = "#64748B"

AMBER = "#F59E0B"          # rule severity: caution
RED = "#EF4444"            # rule severity: critical
GREEN = "#10B981"          # success states


# ----- Global CSS -------------------------------------------------------

# Loaded once per page render. Targets Streamlit's generated DOM via
# stable data-testid attributes where possible, and falls back to
# class-based selectors with high specificity. Everything is scoped to
# .stApp so it cannot leak outside the app surface.

_GLOBAL_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

/* ----- Base ------------------------------------------------------- */
.stApp {{
    background: {NAVY_DEEP};
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    color: {TEXT_PRIMARY};
}}

/* Tighten up the default Streamlit page padding so content has more room. */
.stApp [data-testid="stMain"] .block-container {{
    padding-top: 2rem;
    padding-bottom: 4rem;
    max-width: 880px;
}}

/* ----- Typography ------------------------------------------------- */
.stApp h1, .stApp h2, .stApp h3, .stApp h4 {{
    color: {TEXT_PRIMARY};
    font-family: 'Inter', sans-serif;
    font-weight: 700;
    letter-spacing: -0.02em;
}}
.stApp h1 {{ font-size: 2.5rem; line-height: 1.15; }}
.stApp h2 {{ font-size: 1.75rem; line-height: 1.2; }}
.stApp h3 {{ font-size: 1.25rem; line-height: 1.3; }}

.stApp p, .stApp li, .stApp label {{
    color: {TEXT_PRIMARY};
    line-height: 1.6;
}}

.stApp .cap-subtitle {{
    color: {TEXT_SECONDARY};
    font-size: 1.05rem;
    margin-top: -0.25rem;
    margin-bottom: 1.5rem;
}}

.stApp .cap-eyebrow {{
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    color: {BLUE_CYAN};
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    margin-bottom: 0.6rem;
}}
.stApp .cap-eyebrow .dot {{
    width: 0.5rem;
    height: 0.5rem;
    border-radius: 50%;
    background: {BLUE_CYAN};
    box-shadow: 0 0 0 4px rgba(30, 180, 255, 0.18);
}}

/* ----- Header bar ------------------------------------------------- */
.cap-header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.5rem 0 1.75rem 0;
    border-bottom: 1px solid {NAVY_BORDER};
    margin-bottom: 2rem;
}}
.cap-header .brand {{
    display: flex;
    align-items: center;
    gap: 0.65rem;
    font-weight: 700;
    font-size: 1.1rem;
    letter-spacing: -0.01em;
    color: {TEXT_PRIMARY};
}}
.cap-header .brand .mark {{
    width: 1.6rem;
    height: 1.6rem;
    border-radius: 6px;
    background: linear-gradient(135deg, {BLUE_PRIMARY} 0%, {BLUE_CYAN} 100%);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-weight: 800;
    font-size: 0.95rem;
    color: {NAVY_DEEP};
    flex-shrink: 0;
}}
.cap-header .brand .invent {{
    color: {BLUE_CYAN};
    font-weight: 600;
    margin-left: 0.1rem;
}}
.cap-header .meta {{
    color: {TEXT_SECONDARY};
    font-size: 0.85rem;
}}

/* ----- Cards ------------------------------------------------------ */
.cap-card {{
    background: {NAVY_CARD};
    border: 1px solid {NAVY_BORDER};
    border-radius: 16px;
    padding: 1.75rem;
    margin: 1rem 0;
    box-shadow: 0 1px 0 rgba(255, 255, 255, 0.03) inset,
                0 8px 32px rgba(0, 0, 0, 0.25);
}}
.cap-card .cap-card-eyebrow {{
    color: {TEXT_SECONDARY};
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    margin-bottom: 1rem;
}}

/* ----- Numbered rule list ---------------------------------------- */
.cap-rule {{
    display: flex;
    align-items: center;
    gap: 1rem;
    background: {NAVY_CARD_2};
    border: 1px solid {NAVY_BORDER};
    border-radius: 12px;
    padding: 0.95rem 1.1rem;
    margin-bottom: 0.7rem;
}}
.cap-rule:last-child {{ margin-bottom: 0; }}
.cap-rule .num {{
    flex-shrink: 0;
    width: 2rem;
    height: 2rem;
    border-radius: 50%;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 0.9rem;
    border: 1.5px solid currentColor;
    background: rgba(255, 255, 255, 0.02);
}}
.cap-rule.sev-info .num   {{ color: {BLUE_CYAN}; }}
.cap-rule.sev-warn .num   {{ color: {AMBER}; }}
.cap-rule.sev-crit .num   {{ color: {RED}; }}
.cap-rule .text {{ color: {TEXT_PRIMARY}; font-size: 0.98rem; }}

/* ----- Info banner ------------------------------------------------ */
.cap-banner {{
    background: linear-gradient(135deg,
        rgba(30, 180, 255, 0.15) 0%,
        rgba(91, 192, 235, 0.10) 100%);
    border: 1px solid rgba(30, 180, 255, 0.35);
    color: {TEXT_PRIMARY};
    border-radius: 12px;
    padding: 0.85rem 1.15rem;
    margin: 1rem 0;
    display: flex;
    align-items: center;
    gap: 0.6rem;
    font-size: 0.95rem;
}}
.cap-banner .icon {{ color: {BLUE_CYAN}; }}

/* ----- Buttons ---------------------------------------------------- */
/* Primary buttons (type="primary") — bright Capgemini blue. */
.stApp .stButton > button[kind="primary"],
.stApp .stFormSubmitButton > button[kind="primary"] {{
    background: {BLUE_PRIMARY};
    color: {NAVY_DEEP};
    font-weight: 700;
    border: none;
    border-radius: 12px;
    padding: 0.85rem 1.5rem;
    font-size: 1rem;
    letter-spacing: 0.01em;
    transition: transform 0.05s ease, box-shadow 0.15s ease, background 0.15s ease;
    box-shadow: 0 4px 16px rgba(20, 147, 212, 0.35);
}}
.stApp .stButton > button[kind="primary"]:hover,
.stApp .stFormSubmitButton > button[kind="primary"]:hover {{
    background: {BLUE_CYAN};
    box-shadow: 0 6px 24px rgba(30, 180, 255, 0.45);
    color: {NAVY_DEEP};
}}
.stApp .stButton > button[kind="primary"]:active {{ transform: translateY(1px); }}

/* Secondary buttons — outlined navy with white text. */
.stApp .stButton > button[kind="secondary"],
.stApp .stFormSubmitButton > button[kind="secondary"] {{
    background: transparent;
    color: {TEXT_PRIMARY};
    border: 1.5px solid {NAVY_BORDER};
    border-radius: 12px;
    padding: 0.8rem 1.5rem;
    font-weight: 600;
    transition: border-color 0.15s ease, background 0.15s ease;
}}
.stApp .stButton > button[kind="secondary"]:hover,
.stApp .stFormSubmitButton > button[kind="secondary"]:hover {{
    border-color: {BLUE_CYAN};
    background: rgba(30, 180, 255, 0.08);
    color: {TEXT_PRIMARY};
}}

/* ----- Form inputs ----------------------------------------------- */
.stApp [data-baseweb="input"],
.stApp [data-baseweb="textarea"] {{
    background: {NAVY_CARD_2} !important;
    border-radius: 10px !important;
}}
.stApp [data-baseweb="input"] input,
.stApp [data-baseweb="textarea"] textarea {{
    background: {NAVY_CARD_2} !important;
    color: {TEXT_PRIMARY} !important;
    border: 1px solid {NAVY_BORDER} !important;
    border-radius: 10px !important;
}}
.stApp [data-baseweb="input"] input:focus,
.stApp [data-baseweb="textarea"] textarea:focus {{
    border-color: {BLUE_CYAN} !important;
    box-shadow: 0 0 0 3px rgba(30, 180, 255, 0.18) !important;
}}

/* ----- Radio / Checkbox ------------------------------------------ */
.stApp [data-testid="stRadio"] label {{ color: {TEXT_PRIMARY}; }}

/* ----- Progress bar ---------------------------------------------- */
.stApp [data-testid="stProgress"] > div > div > div > div {{
    background: linear-gradient(90deg, {BLUE_PRIMARY}, {BLUE_CYAN});
}}

/* ----- Alerts (st.error / st.success / st.info / st.warning) ----- */
.stApp [data-testid="stAlert"] {{
    border-radius: 12px;
    border: 1px solid {NAVY_BORDER};
}}

/* ----- Divider ---------------------------------------------------- */
.stApp hr {{ border-color: {NAVY_BORDER}; opacity: 1; }}

/* ----- Hide default Streamlit chrome ----------------------------- */
.stApp [data-testid="stToolbar"] {{ visibility: hidden; height: 0; }}
.stApp footer {{ visibility: hidden; }}
.stApp #MainMenu {{ visibility: hidden; }}
</style>
"""


def inject_global_styles() -> None:
    """Inject the app-wide CSS.

    Idempotent — safe to call at the top of every page render. The browser
    discards the previous <style> block and applies the new one.
    """
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)


# ----- Components -------------------------------------------------------

def header(meta: Optional[str] = None) -> None:
    """Render the top brand bar.

    `meta` is a small right-aligned label (e.g. "Candidate · Layer 2 of 3"
    or the candidate's name on the dashboard).
    """
    meta_html = f'<div class="meta">{_escape(meta)}</div>' if meta else ""
    st.markdown(
        f"""
        <div class="cap-header">
            <div class="brand">
                <span class="mark">C</span>
                <span>Capgemini <span class="invent">Invent</span></span>
            </div>
            {meta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def eyebrow(text: str) -> None:
    """Small all-caps label with a glowing dot, used above page titles."""
    st.markdown(
        f'<div class="cap-eyebrow"><span class="dot"></span>{_escape(text)}</div>',
        unsafe_allow_html=True,
    )


def page_title(title: str, subtitle: Optional[str] = None) -> None:
    """Bold heading + optional muted subtitle."""
    st.markdown(f"<h1>{_escape(title)}</h1>", unsafe_allow_html=True)
    if subtitle:
        st.markdown(
            f'<div class="cap-subtitle">{_escape(subtitle)}</div>',
            unsafe_allow_html=True,
        )


@contextmanager
def card(eyebrow_text: Optional[str] = None) -> Iterator[None]:
    """Context manager that wraps following Streamlit calls in a styled card.

    Usage:
        with card("Rules to follow"):
            numbered_rule(1, "...", severity="info")
            ...

    Implementation note: Streamlit doesn't let us wrap arbitrary widgets
    in custom HTML, so we open the card div, render the widgets inside
    a st.container(), then close the div. The container ensures DOM order.
    """
    eyebrow_html = (
        f'<div class="cap-card-eyebrow">{_escape(eyebrow_text)}</div>'
        if eyebrow_text
        else ""
    )
    st.markdown(f'<div class="cap-card">{eyebrow_html}', unsafe_allow_html=True)
    try:
        yield
    finally:
        st.markdown("</div>", unsafe_allow_html=True)


def numbered_rule(num: int, text: str, severity: str = "info") -> None:
    """One numbered item in a rules card.

    severity: "info" (blue), "warn" (amber), "crit" (red).
    """
    sev_class = {"info": "sev-info", "warn": "sev-warn", "crit": "sev-crit"}.get(
        severity, "sev-info"
    )
    st.markdown(
        f"""
        <div class="cap-rule {sev_class}">
            <span class="num">{num}</span>
            <span class="text">{_escape(text)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def info_banner(text: str, icon: str = "ℹ") -> None:
    """Soft cyan banner for inline contextual notes (above CTAs)."""
    st.markdown(
        f"""
        <div class="cap-banner">
            <span class="icon">{icon}</span>
            <span>{_escape(text)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ----- Internal ---------------------------------------------------------

def _escape(text: object) -> str:
    """Minimal HTML escape for the small set of helpers above.

    The components only accept short strings (titles, labels, single
    sentences), so we don't need a full HTML sanitizer — just enough to
    keep stray angle brackets from breaking layout.
    """
    s = str(text) if text is not None else ""
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
    )
