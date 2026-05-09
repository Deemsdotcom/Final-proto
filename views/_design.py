"""Design system: shared CSS injection + reusable Streamlit components.

Implements the Capgemini Invent visual language derived from the official
2026 deck template (Bright / Blue / Dark themes).

Source-of-truth tokens:
  Primary blue  #0058AB   Deep navy  #121A38   Bright cyan  #1DB8F2

Public surface:
  inject_global_styles()  – call once at the top of every page render
  header(meta)            – full-bleed top bar with Capgemini Invent logo
  eyebrow(text)           – small all-caps cyan label above headings
  page_title(title, sub)  – bold heading + optional muted subtitle
  metric(value, label)    – KPI card (big number + short descriptor)
  card(eyebrow_text)      – context manager: rounded surface card
  numbered_rule(n, text)  – one item in a rules card
  info_banner(text, icon) – left-accented cyan notice above CTAs
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

import streamlit as st

# ── Capgemini Invent official palette (Dark 2026 theme) ─────────────────────
# Sourced from theme1/2/3.xml of 20260414_Agentic_AI_in_Action_Swiss_Stories.pptx

NAVY_DEEP    = "#121A38"   # page background (official deep navy)
NAVY_CARD    = "#1A2548"   # card surface   (derived +lighter)
NAVY_CARD_2  = "#1E2D55"   # nested rows
NAVY_BORDER  = "#28387A"   # 1 px borders

BLUE_PRIMARY = "#0058AB"   # Capgemini primary blue
BLUE_CYAN    = "#1DB8F2"   # bright cyan accent
TEAL         = "#00828E"   # teal (secondary accent)
AMBER        = "#FEB100"   # amber warning
RED          = "#FF816E"   # red/error
ORANGE       = "#BE4D00"   # burnt orange (severity)
GREEN        = "#00D5D0"   # teal-green success

TEXT_PRIMARY   = "#FFFFFF"
TEXT_SECONDARY = "#A0AECB"   # muted on dark surface
TEXT_MUTED     = "#6B7A9E"


# ── Capgemini Invent logo (inline SVG) ──────────────────────────────────────
# Two overlapping angled stripes → Capgemini mark  +  Ubuntu-style wordmark
_LOGO_SVG = (
    '<svg viewBox="0 0 220 44" height="36" xmlns="http://www.w3.org/2000/svg">'
    # mark: left stripe (primary blue)
    '<path d="M2,38 L14,6 L21,6 L9,38 Z" fill="#0058AB"/>'
    # mark: right stripe (bright cyan, slightly offset)
    '<path d="M11,38 L23,6 L30,6 L18,38 Z" fill="#1DB8F2"/>'
    # wordmark
    '<text x="40" y="27"'
    ' font-family="Ubuntu,Arial,sans-serif"'
    ' font-weight="700" font-size="20" fill="#FFFFFF"'
    '>Capgemini</text>'
    '<text x="41" y="41"'
    ' font-family="Ubuntu,Arial,sans-serif"'
    ' font-weight="500" font-size="11" fill="#1DB8F2"'
    ' letter-spacing="4">INVENT</text>'
    '</svg>'
)

# Horizontal padding shared by the block-container and the header bleed
_PAD = "3.5rem"

# ── Global CSS ───────────────────────────────────────────────────────────────

_GLOBAL_CSS = f"""
<style>
/* Ubuntu from Google Fonts */
@import url('https://fonts.googleapis.com/css2?family=Ubuntu:wght@400;500;700&display=swap');

/* ── Base ──────────────────────────────────────────────────────────────── */
.stApp {{
    background: {NAVY_DEEP};
    font-family: 'Ubuntu', Arial, sans-serif;
    color: {TEXT_PRIMARY};
}}

/* Remove Streamlit's outer padding so we control every pixel */
.stApp > section[data-testid="stMain"] {{
    padding: 0 !important;
}}

/* Full-width block container */
.stApp [data-testid="stMain"] .block-container {{
    padding-top: 0 !important;
    padding-bottom: 5rem !important;
    padding-left: {_PAD} !important;
    padding-right: {_PAD} !important;
    max-width: 100% !important;
    width: 100% !important;
}}

/* ── Typography ────────────────────────────────────────────────────────── */
.stApp h1, .stApp h2, .stApp h3, .stApp h4 {{
    color: {TEXT_PRIMARY};
    font-family: 'Ubuntu', Arial, sans-serif;
    font-weight: 700;
    letter-spacing: -0.01em;
}}
.stApp h1 {{ font-size: 2.75rem; line-height: 1.1; margin-bottom: 0.5rem; }}
.stApp h2 {{ font-size: 2rem;    line-height: 1.15; }}
.stApp h3 {{ font-size: 1.25rem; line-height: 1.3; }}

.stApp p, .stApp li, .stApp label {{
    color: {TEXT_PRIMARY};
    line-height: 1.6;
    font-family: 'Ubuntu', Arial, sans-serif;
}}

.stApp .cap-subtitle {{
    color: {TEXT_SECONDARY};
    font-size: 1.05rem;
    margin-top: 0.25rem;
    margin-bottom: 0;
    max-width: 680px;
    line-height: 1.55;
}}

.stApp .cap-eyebrow {{
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    color: {BLUE_CYAN};
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    margin-bottom: 0.6rem;
}}
.stApp .cap-eyebrow .dot {{
    width: 0.4rem;
    height: 0.4rem;
    border-radius: 50%;
    background: {BLUE_CYAN};
    box-shadow: 0 0 0 3px rgba(29,184,242,0.2);
    flex-shrink: 0;
}}

/* ── Full-bleed header bar ─────────────────────────────────────────────── */
.cap-header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem {_PAD};
    margin-left: -{_PAD};
    margin-right: -{_PAD};
    margin-bottom: 3rem;
    border-bottom: 1px solid {NAVY_BORDER};
    background: {NAVY_DEEP};
}}
.cap-header .meta {{
    color: {TEXT_SECONDARY};
    font-size: 0.83rem;
    font-weight: 500;
    letter-spacing: 0.03em;
}}

/* ── KPI metric cards ──────────────────────────────────────────────────── */
.cap-metric {{
    background: {NAVY_CARD};
    border: 1px solid {NAVY_BORDER};
    border-top: 3px solid {BLUE_PRIMARY};
    border-radius: 6px;
    padding: 1.1rem 1.25rem;
    text-align: left;
}}
.cap-metric .val {{
    display: block;
    font-size: 2rem;
    font-weight: 700;
    color: {TEXT_PRIMARY};
    line-height: 1;
    margin-bottom: 0.35rem;
}}
.cap-metric .lbl {{
    display: block;
    font-size: 0.8rem;
    font-weight: 500;
    color: {TEXT_SECONDARY};
    letter-spacing: 0.08em;
    text-transform: uppercase;
}}

/* ── Cards (styled via Streamlit's bordered container) ─────────────────── */
/* st.container(border=True) renders as stVerticalBlockBorderWrapper        */
.stApp [data-testid="stVerticalBlockBorderWrapper"] {{
    background: {NAVY_CARD} !important;
    border: 1px solid {NAVY_BORDER} !important;
    border-radius: 8px !important;
    box-shadow: 0 2px 16px rgba(0,0,0,0.25) !important;
    display: flex !important;
    flex-direction: column !important;
    flex: 1 !important;
}}
/* Inner block — also flex so button can be pushed down */
.stApp [data-testid="stVerticalBlockBorderWrapper"] > div[data-testid="stVerticalBlock"] {{
    display: flex !important;
    flex-direction: column !important;
    flex: 1 !important;
    padding: 1.5rem !important;
}}
/* Push the last child of a card body (typically the button) to the
   bottom. We target the stElementContainer (the actual flex item) rather
   than .stButton (which is the inner element and not part of the flex
   layout). The selector also handles cases where the last child is a
   form or another widget container — anything that ends up last in the
   card gets aligned to the bottom of the card body. */
.stApp [data-testid="stVerticalBlockBorderWrapper"]
  > div[data-testid="stVerticalBlock"]
  > [data-testid="stElementContainer"]:last-child {{
    margin-top: auto !important;
}}
/* Eyebrow label inside the card */
.cap-card-eyebrow {{
    color: {TEXT_SECONDARY};
    font-size: 0.73rem;
    font-weight: 700;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    padding-bottom: 0.75rem;
    margin-bottom: 1rem;
    border-bottom: 1px solid {NAVY_BORDER};
    display: block;
}}

/* ── Numbered rule list ─────────────────────────────────────────────────── */
.cap-rule {{
    display: flex;
    align-items: flex-start;
    gap: 0.9rem;
    background: {NAVY_CARD_2};
    border: 1px solid {NAVY_BORDER};
    border-radius: 6px;
    padding: 0.8rem 1rem;
    margin-bottom: 0.5rem;
}}
.cap-rule:last-child {{ margin-bottom: 0; }}
.cap-rule .num {{
    flex-shrink: 0;
    width: 1.65rem;
    height: 1.65rem;
    border-radius: 4px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 0.82rem;
    border: 1px solid currentColor;
    background: rgba(255,255,255,0.03);
    margin-top: 0.05rem;
}}
.cap-rule.sev-info .num {{ color: {BLUE_CYAN}; }}
.cap-rule.sev-warn .num {{ color: {AMBER}; }}
.cap-rule.sev-crit .num {{ color: {RED}; }}
.cap-rule .text {{
    color: {TEXT_PRIMARY};
    font-size: 0.95rem;
    line-height: 1.45;
}}

/* ── Info banner ───────────────────────────────────────────────────────── */
.cap-banner {{
    background: rgba(0,88,171,0.12);
    border: 1px solid rgba(29,184,242,0.28);
    border-left: 3px solid {BLUE_CYAN};
    color: {TEXT_PRIMARY};
    border-radius: 6px;
    padding: 0.8rem 1.1rem;
    margin: 1rem 0;
    display: flex;
    align-items: center;
    gap: 0.7rem;
    font-size: 0.93rem;
}}
.cap-banner .icon {{ color: {BLUE_CYAN}; flex-shrink: 0; }}

/* ── Primary buttons ────────────────────────────────────────────────────── */
.stApp .stButton > button[kind="primary"],
.stApp .stFormSubmitButton > button[kind="primary"] {{
    background: {BLUE_PRIMARY};
    color: #FFFFFF;
    font-weight: 700;
    font-family: 'Ubuntu', Arial, sans-serif;
    border: none;
    border-radius: 6px;
    padding: 0.75rem 1.5rem;
    font-size: 0.95rem;
    letter-spacing: 0.02em;
    transition: background 0.15s ease, box-shadow 0.15s ease;
    box-shadow: 0 2px 10px rgba(0,88,171,0.35);
}}
.stApp .stButton > button[kind="primary"]:hover,
.stApp .stFormSubmitButton > button[kind="primary"]:hover {{
    background: #0068CC;
    box-shadow: 0 4px 18px rgba(0,88,171,0.5);
}}
.stApp .stButton > button[kind="primary"]:active {{ transform: translateY(1px); }}

/* ── Secondary buttons ─────────────────────────────────────────────────── */
.stApp .stButton > button[kind="secondary"],
.stApp .stFormSubmitButton > button[kind="secondary"] {{
    background: transparent;
    color: {TEXT_PRIMARY};
    border: 1px solid {NAVY_BORDER};
    border-radius: 6px;
    padding: 0.75rem 1.5rem;
    font-weight: 600;
    font-family: 'Ubuntu', Arial, sans-serif;
    font-size: 0.95rem;
    transition: border-color 0.15s ease, background 0.15s ease;
}}
.stApp .stButton > button[kind="secondary"]:hover,
.stApp .stFormSubmitButton > button[kind="secondary"]:hover {{
    border-color: {BLUE_PRIMARY};
    background: rgba(0,88,171,0.1);
}}

/* ── Form inputs ────────────────────────────────────────────────────────── */
.stApp [data-baseweb="input"],
.stApp [data-baseweb="textarea"] {{
    background: {NAVY_CARD_2} !important;
    border-radius: 6px !important;
}}
.stApp [data-baseweb="input"] input,
.stApp [data-baseweb="textarea"] textarea {{
    background: {NAVY_CARD_2} !important;
    color: {TEXT_PRIMARY} !important;
    border: 1px solid {NAVY_BORDER} !important;
    border-radius: 6px !important;
    font-family: 'Ubuntu', Arial, sans-serif !important;
}}
.stApp [data-baseweb="input"] input:focus,
.stApp [data-baseweb="textarea"] textarea:focus {{
    border-color: {BLUE_CYAN} !important;
    box-shadow: 0 0 0 2px rgba(29,184,242,0.18) !important;
}}

/* ── Progress bar ────────────────────────────────────────────────────────── */
.stApp [data-testid="stProgress"] > div > div > div > div {{
    background: linear-gradient(90deg, {BLUE_PRIMARY}, {BLUE_CYAN});
    border-radius: 2px;
}}

/* ── Radio / Checkbox ────────────────────────────────────────────────────── */
.stApp [data-testid="stRadio"] label {{ color: {TEXT_PRIMARY}; }}

/* ── Card paragraph — equalise heights across sibling cards ─────────────── */
.cap-card p {{
    min-height: 3.8rem;
    margin: 0 0 1.25rem 0;
}}

/* ── Alerts ──────────────────────────────────────────────────────────────── */
.stApp [data-testid="stAlert"] {{ border-radius: 6px; }}

/* ── Divider ─────────────────────────────────────────────────────────────── */
.stApp hr {{ border-color: {NAVY_BORDER}; opacity: 1; }}

/* ── Hide Streamlit chrome ───────────────────────────────────────────────── */
.stApp [data-testid="stToolbar"] {{ visibility: hidden; height: 0; }}
.stApp footer {{ visibility: hidden; }}
.stApp #MainMenu {{ visibility: hidden; }}

/* ── Equal-height columns — full flex cascade to pin button at bottom ──────── */
/* Row: stretch all columns to the tallest one's height */
.stApp [data-testid="stHorizontalBlock"] {{
    align-items: stretch !important;
    gap: 1.5rem;
}}
/* Column: flex column, full height */
.stApp [data-testid="stColumn"] {{
    display: flex !important;
    flex-direction: column !important;
}}
/* Outer stVerticalBlock inside column */
.stApp [data-testid="stColumn"] > div[data-testid="stVerticalBlock"] {{
    flex: 1 !important;
    display: flex !important;
    flex-direction: column !important;
}}
/* Border wrapper fills its column */
.stApp [data-testid="stVerticalBlockBorderWrapper"] {{
    flex: 1 !important;
}}
/* Inner stVerticalBlock: flex column so children can be distributed */
.stApp [data-testid="stVerticalBlockBorderWrapper"] > [data-testid="stVerticalBlock"] {{
    flex: 1 !important;
    display: flex !important;
    flex-direction: column !important;
}}
/* (No per-markdown flex rule needed — the last-child margin-top:auto
   above takes care of bottom-aligning the CTA in action cards.) */

/* ── Vertical journey timeline ─────────────────────────────────────────────
   Used by ui.journey_timeline() — a column of "stations" (numbered
   circles) connected by a glowing cyan rail, with each station's content
   to the right of its circle. */
.cap-journey {{
    position: relative;
    padding-left: 4.5rem;
    margin: 1.75rem 0 1.5rem 0;
}}
/* The continuous rail running through every station. The top/bottom
   insets keep the rail from extending past the first and last circles. */
.cap-journey::before {{
    content: "";
    position: absolute;
    left: 1.85rem;
    top: 1.5rem;
    bottom: 2.0rem;
    width: 2px;
    background: linear-gradient(180deg, {BLUE_CYAN} 0%, {BLUE_PRIMARY} 100%);
    opacity: 0.55;
}}
.cap-station {{
    position: relative;
    margin-bottom: 1.6rem;
    min-height: 3rem;
}}
.cap-station:last-child {{ margin-bottom: 0; }}
.cap-station .cap-station-circle {{
    position: absolute;
    left: -3.65rem;
    top: 0;
    width: 2.7rem;
    height: 2.7rem;
    border-radius: 50%;
    background: linear-gradient(135deg, {BLUE_PRIMARY} 0%, {BLUE_CYAN} 100%);
    color: {NAVY_DEEP};
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.15rem;
    font-weight: 800;
    box-shadow: 0 0 0 4px rgba(30, 180, 255, 0.18),
                0 4px 18px rgba(30, 180, 255, 0.35);
    z-index: 1;
}}
.cap-station .cap-station-meta {{
    color: {BLUE_CYAN};
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    margin-bottom: 0.25rem;
}}
.cap-station .cap-station-title {{
    color: {TEXT_PRIMARY};
    font-size: 1.35rem;
    font-weight: 700;
    line-height: 1.2;
    margin-bottom: 0.35rem;
    letter-spacing: -0.01em;
}}
.cap-station .cap-station-desc {{
    color: {TEXT_SECONDARY};
    font-size: 1rem;
    line-height: 1.55;
    max-width: 56rem;
}}

/* ── Theme hero cards ──────────────────────────────────────────────────────
   Used by ui.theme_card() — a tall card with an inline SVG illustration
   at the top, a meta pill, big theme name, and a short description. Used
   on the Layer 1 overview to give each reasoning theme its own visual
   identity. */
.cap-theme-card {{
    background: {NAVY_CARD};
    border: 1px solid {NAVY_BORDER};
    border-top: 3px solid {BLUE_CYAN};
    border-radius: 8px;
    padding: 1.6rem 1.4rem 1.4rem 1.4rem;
    margin: 0.5rem 0;
    box-shadow: 0 4px 24px rgba(0,0,0,0.25);
    height: 100%;
    display: flex;
    flex-direction: column;
}}
.cap-theme-card .cap-theme-icon {{
    width: 4.5rem;
    height: 4.5rem;
    border-radius: 14px;
    background: linear-gradient(135deg, rgba(29,184,242,0.12) 0%, rgba(0,88,171,0.18) 100%);
    border: 1px solid rgba(29,184,242,0.25);
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 1.2rem;
}}
.cap-theme-card .cap-theme-icon svg {{
    width: 2.6rem;
    height: 2.6rem;
}}
.cap-theme-card .cap-theme-icon svg .stroke {{ stroke: {BLUE_CYAN}; }}
.cap-theme-card .cap-theme-icon svg .fill   {{ fill:   {BLUE_CYAN}; }}
.cap-theme-card .cap-theme-meta {{
    display: inline-block;
    align-self: flex-start;
    color: {BLUE_CYAN};
    background: rgba(29,184,242,0.10);
    border: 1px solid rgba(29,184,242,0.30);
    padding: 0.20rem 0.65rem;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    margin-bottom: 0.55rem;
}}
.cap-theme-card .cap-theme-title {{
    color: {TEXT_PRIMARY};
    font-size: 1.55rem;
    font-weight: 700;
    line-height: 1.15;
    margin-bottom: 0.55rem;
    letter-spacing: -0.01em;
}}
.cap-theme-card .cap-theme-desc {{
    color: {TEXT_SECONDARY};
    font-size: 0.95rem;
    line-height: 1.5;
    flex: 1;
}}
.cap-theme-card .cap-theme-stat {{
    display: flex;
    gap: 1.5rem;
    margin-top: 1rem;
    padding-top: 0.9rem;
    border-top: 1px solid {NAVY_BORDER};
}}
.cap-theme-card .cap-theme-stat-item {{
    display: flex;
    flex-direction: column;
}}
.cap-theme-card .cap-theme-stat-value {{
    color: {TEXT_PRIMARY};
    font-size: 1.05rem;
    font-weight: 700;
    line-height: 1.1;
}}
.cap-theme-card .cap-theme-stat-label {{
    color: {TEXT_MUTED};
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    margin-top: 0.15rem;
}}
</style>
"""


def inject_global_styles() -> None:
    """Inject the app-wide CSS. Idempotent — safe to call on every render."""
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)


# ── Components ────────────────────────────────────────────────────────────────

def header(meta: Optional[str] = None) -> None:
    """Full-bleed top bar with the Capgemini Invent logo + optional right label."""
    meta_html = f'<div class="meta">{_esc(meta)}</div>' if meta else ""
    st.markdown(
        f'<div class="cap-header">{_LOGO_SVG}{meta_html}</div>',
        unsafe_allow_html=True,
    )


def eyebrow(text: str) -> None:
    """Small all-caps cyan label with glowing dot — used above page titles."""
    st.markdown(
        f'<div class="cap-eyebrow"><span class="dot"></span>{_esc(text)}</div>',
        unsafe_allow_html=True,
    )


def page_title(title: str, subtitle: Optional[str] = None) -> None:
    """Bold Ubuntu heading + optional muted subtitle."""
    st.markdown(f"<h1>{_esc(title)}</h1>", unsafe_allow_html=True)
    if subtitle:
        st.markdown(
            f'<p class="cap-subtitle">{_esc(subtitle)}</p>',
            unsafe_allow_html=True,
        )


def metric(value: str, label: str) -> None:
    """KPI card — big value + short uppercase descriptor."""
    st.markdown(
        f"""
        <div class="cap-metric">
            <span class="val">{_esc(value)}</span>
            <span class="lbl">{_esc(label)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


@contextmanager
def card(eyebrow_text: Optional[str] = None) -> Iterator[None]:
    """Context manager — wraps Streamlit widgets in a styled bordered card.

    Uses st.container(border=True) so Streamlit properly wraps all yielded
    widgets. The border/background/radius are applied via CSS targeting
    [data-testid="stVerticalBlockBorderWrapper"].
    """
    with st.container(border=True):
        if eyebrow_text:
            st.markdown(
                f'<span class="cap-card-eyebrow">{_esc(eyebrow_text)}</span>',
                unsafe_allow_html=True,
            )
        yield


def numbered_rule(num: int, text: str, severity: str = "info") -> None:
    """One numbered item in a rules card. severity: info / warn / crit."""
    sev_class = {"info": "sev-info", "warn": "sev-warn", "crit": "sev-crit"}.get(
        severity, "sev-info"
    )
    st.markdown(
        f"""
        <div class="cap-rule {sev_class}">
            <span class="num">{num}</span>
            <span class="text">{_esc(text)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def info_banner(text: str, icon: str = "ℹ") -> None:
    """Left-accented cyan banner for contextual notes above CTAs."""
    st.markdown(
        f"""
        <div class="cap-banner">
            <span class="icon">{icon}</span>
            <span>{_esc(text)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Internal ──────────────────────────────────────────────────────────────────

def _esc(text: object) -> str:
    s = str(text) if text is not None else ""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def journey_timeline(items: list) -> None:
    """Render a vertical timeline of "stations" connected by a cyan rail.

    `items` is a list of dicts with keys: num, meta, title, desc.
    Each station shows a numbered circle on the rail, with the meta tag,
    bold title, and description rendered to the right. Use for the
    welcome page (3 layers) or anywhere else a sequenced journey is
    clearer than a horizontal stat strip or card grid.

    Implementation note: the inner HTML is emitted as a single line with
    no leading whitespace. Indented multi-line HTML inside a triple-quoted
    f-string makes Streamlit's markdown parser treat blocks after the
    first as 4-space-indented code blocks, which renders the raw HTML as
    text instead of styled elements.
    """
    parts = []
    for item in items:
        parts.append(
            '<div class="cap-station">'
            '<div class="cap-station-circle">' + _esc(item.get("num", "")) + '</div>'
            '<div class="cap-station-meta">' + _esc(item.get("meta", "")) + '</div>'
            '<div class="cap-station-title">' + _esc(item.get("title", "")) + '</div>'
            '<div class="cap-station-desc">' + _esc(item.get("desc", "")) + '</div>'
            '</div>'
        )
    html = '<div class="cap-journey">' + "".join(parts) + '</div>'
    st.markdown(html, unsafe_allow_html=True)


# ── SVG icons for the three Layer 1 themes ─────────────────────────────────
# Each icon is a 60×60 viewBox using the .stroke / .fill classes so the
# theme card CSS can colour them via class selectors. Logical: a 3×3 grid
# with the bottom-right cell missing (the matrix puzzle). Numerical: a
# four-bar bar chart. Verbal: stacked horizontal text lines.

THEME_ICON_LOGICAL = (
    '<svg viewBox="0 0 60 60" xmlns="http://www.w3.org/2000/svg" fill="none">'
    '<rect class="fill" x="3"  y="3"  width="14" height="14" rx="2"/>'
    '<rect class="fill" x="23" y="3"  width="14" height="14" rx="2"/>'
    '<rect class="fill" x="43" y="3"  width="14" height="14" rx="2"/>'
    '<rect class="fill" x="3"  y="23" width="14" height="14" rx="2"/>'
    '<rect class="fill" x="23" y="23" width="14" height="14" rx="2"/>'
    '<rect class="fill" x="43" y="23" width="14" height="14" rx="2"/>'
    '<rect class="fill" x="3"  y="43" width="14" height="14" rx="2"/>'
    '<rect class="fill" x="23" y="43" width="14" height="14" rx="2"/>'
    '<rect class="stroke" x="43" y="43" width="14" height="14" rx="2" '
    'stroke-width="2" stroke-dasharray="3 2"/>'
    '</svg>'
)
THEME_ICON_NUMERICAL = (
    '<svg viewBox="0 0 60 60" xmlns="http://www.w3.org/2000/svg" fill="none">'
    '<rect class="fill" x="6"  y="35" width="8" height="20" rx="1"/>'
    '<rect class="fill" x="20" y="20" width="8" height="35" rx="1"/>'
    '<rect class="fill" x="34" y="28" width="8" height="27" rx="1"/>'
    '<rect class="fill" x="48" y="12" width="8" height="43" rx="1"/>'
    '<line class="stroke" x1="3" y1="56" x2="58" y2="56" stroke-width="1.5"/>'
    '</svg>'
)
THEME_ICON_VERBAL = (
    '<svg viewBox="0 0 60 60" xmlns="http://www.w3.org/2000/svg" fill="none">'
    '<rect class="fill" x="6"  y="12" width="48" height="3" rx="1.5"/>'
    '<rect class="fill" x="6"  y="22" width="48" height="3" rx="1.5"/>'
    '<rect class="fill" x="6"  y="32" width="32" height="3" rx="1.5"/>'
    '<line class="stroke" x1="6" y1="42" x2="54" y2="42" '
    'stroke-width="1" stroke-dasharray="3 2"/>'
    '<rect class="fill" x="6"  y="48" width="40" height="3" rx="1.5"/>'
    '</svg>'
)


def theme_card(
    icon_svg: str,
    meta: str,
    title: str,
    desc: str,
    stats: Optional[list] = None,
) -> None:
    """Render a tall theme hero card with an SVG icon, meta pill, title,
    description, and an optional row of small stat boxes at the bottom.

    `stats` is a list of (value, label) tuples. They render as a thin
    bordered strip across the bottom of the card — ideal for showing
    things like "10 questions" + "75 sec / question".

    HTML is emitted as a single line to avoid Streamlit's markdown parser
    treating indented blocks as code (same gotcha as journey_timeline).
    """
    stats_html = ""
    if stats:
        items = []
        for value, label in stats:
            items.append(
                '<div class="cap-theme-stat-item">'
                '<div class="cap-theme-stat-value">' + _esc(value) + '</div>'
                '<div class="cap-theme-stat-label">' + _esc(label) + '</div>'
                '</div>'
            )
        stats_html = '<div class="cap-theme-stat">' + "".join(items) + '</div>'

    html = (
        '<div class="cap-theme-card">'
        '<div class="cap-theme-icon">' + icon_svg + '</div>'
        '<div class="cap-theme-meta">' + _esc(meta) + '</div>'
        '<div class="cap-theme-title">' + _esc(title) + '</div>'
        '<div class="cap-theme-desc">' + _esc(desc) + '</div>'
        + stats_html +
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)
