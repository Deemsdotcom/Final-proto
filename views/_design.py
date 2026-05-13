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
_LOGO_SVG = """<!-- Created with Inkscape (http://www.inkscape.org/) by Marsupilami -->
<svg
   xmlns:svg="http://www.w3.org/2000/svg"
   xmlns="http://www.w3.org/2000/svg"
   version="1.1"
   id="svg3709"
   width="180"
   height="42"
   viewBox="-1.06668594 -1.06668594 161.58207188 37.68956988">
  <defs
     id="defs3711" />
  <path
     id="path3676"
     style="fill:#12abdb;fill-opacity:1;fill-rule:evenodd;stroke:none"
     d="m 153.2175,21.2782 c 3.4962,0 6.1962,-2.8462 6.2312,-6.225 -0.245,-1.475 -0.7625,-4.2037 -4.585,-4.2037 -4.19,0 -5.5762,5.8487 -8.985,9.6237 -0.2737,2.1438 -2.305,4.0625 -4.8387,4.385 0.62,0.6488 2.0025,1.0013 3.6525,1.0013 3.0175,0 6.67,-0.9088 8.5837,-2.7988 -2.5537,0.035 -4.1937,-1.6062 -4.355,-3.8762 1.245,1.5087 2.6513,2.0937 4.2963,2.0937" />
  <path
     id="path3678"
     style="fill:#0070ad;fill-opacity:1;fill-rule:evenodd;stroke:none"
     d="m 126.3725,11.972 c 0,-1.86 -0.1125,-3.1 -1.3288,-3.1 -0.5562,0 -0.825,0.1125 -1.3087,0.2725 0.43,6.28 -0.9913,11.8125 -2.7238,11.8125 -2.2712,0 -1.1387,-13.4625 -5.9475,-13.4625 -4.4387,0 -5.0787,10.7475 -5.5812,10.7475 -0.3425,0 -0.395,-2.8225 -0.3763,-4.9763 0.1863,-1.03 0.2888,-1.9575 0.2888,-2.6612 0,-1 -0.41,-2.7288 -2.6813,-1.865 0.079,7.6862 -1.46,12.3287 -3.1937,12.3287 -2.5388,0 -2.5675,-6.9675 -2.5675,-8.8862 0,-1.875 0.1362,-4.38 -2.6513,-3.4913 -0.415,6.7038 -2.1737,11.7625 -3.2812,11.7625 -1.6513,0 -1.3188,-11.5812 -4.8888,-11.5812 -3.2125,0 -4.2037,10.9712 -4.8725,10.9712 -1.1962,0 0.3763,-12.3487 -4.2625,-12.3487 -2.4312,0 -3.3987,4.1212 -4.3512,8.735 -0.185,0.8937 -0.375,0.9237 -0.41,-0.087 -0.024,-0.8588 -0.029,-1.7238 -0.019,-2.5825 1.1663,-4.6388 -0.2587,-6.3525 -2.4075,-5.1175 0.6938,8.56 -3.2375,12.7437 -6.25,12.7437 -1.0887,0 -1.9487,-0.4637 -2.5875,-1.1962 3.6125,-2.2163 5.2188,-4.76 5.2188,-7.2463 0,-2.69 -1.5475,-4.2425 -4.1163,-4.2425 -3.5837,0 -5.59,3.6913 -5.59,6.8313 0,1.6887 0.3175,3.125 0.835,4.3062 -1.2312,0.5863 -2.3925,1.0938 -3.4725,1.5863 -0.098,-3.2275 -0.4587,-6.615 -0.7362,-9.745 -1.91,-0.5275 -2.4663,0.39 -2.6125,2.0887 -0.3425,3.8775 -1.7775,6.285 -3.0475,6.285 -0.9525,0 -1.5375,-1.1625 -1.6063,-2.3975 -0.3562,-6.2162 4.6875,-7.945 7.3288,-7.0412 0.5475,-1.3725 -0.054,-2.3588 -2.4363,-2.3588 -2.8862,0 -5.0437,1.7538 -6.6262,4.0038 -1.0538,1.5 -2.275,2.5637 -3.8963,3.8487 0.044,-0.3662 0.064,-0.7375 0.064,-1.1037 0,-4.38 -2.3738,-6.3038 -4.6388,-6.3038 -1.875,0 -3.0562,1.1225 -3.74,2.8513 -0.1662,-1.7338 -0.5125,-2.48 -1.5187,-2.48 -0.43,0 -1.03,0.1212 -1.67,0.4337 0.2925,0.9675 0.405,3.1113 0.405,4.5175 0,5.2675 -1.5088,7.6313 -2.9588,7.6313 -1.66,0 -1.9237,-6.25 -2.065,-8.6813 -0.2587,-0.098 -0.5325,-0.1512 -0.8112,-0.1512 -1.5038,0 -1.6988,2.0162 -2.07,3.8712 -0.41,2.0563 -1.5913,4.6388 -3.345,4.6388 -1.0588,0 -1.7238,-1.02 -1.8063,-2.8563 -0.1712,-3.725 2.93,-8.14 7.7788,-6.7675 0.6337,-1.4837 -0.3625,-2.6125 -2.3738,-2.6125 -3.545,0 -6.475,2.6513 -7.7537,5.7913 -1.2988,2.8812 -3.57,7.11 -8.1888,7.11 C 6.26,21.7975 3.76,18.95 3.76,12.9787 c 0,-5.1462 3.2462,-10.035 6.7087,-10.035 2.4213,0 2.9838,2.3838 2.7688,4.62 1.255,1.005 3.31,0.067 3.31,-2.4462 0,-1.7338 -1.4063,-4.6738 -5.9513,-4.6738 C 4.9712,0.4437 0,6.055 0,13.4225 0,20.5612 3.6225,24.78 8.75,24.78 c 3.2375,0 6.2887,-1.845 8.3937,-5.2538 0.5325,2.9838 2.5638,4.2388 4.0863,4.2388 2.4662,0 4.0775,-1.5975 4.9562,-3.755 0.5475,2.1625 1.7038,3.765 3.6288,3.765 1.3525,0 2.4112,-0.6888 3.2075,-1.7875 -0.3175,7.5187 -0.7125,12.3137 3.73,11.3725 -0.6875,-2.1388 -0.9075,-6.0313 -0.9075,-9.5275 0,-9.565 1.5775,-12.7138 3.555,-12.7138 1.435,0 1.8987,1.825 1.8987,3.7738 0,1.045 -0.1025,2.2462 -0.3662,3.325 -2.4313,1.5337 -4.37,2.745 -4.37,4.2825 0,1.2162 0.9037,1.3275 1.685,1.3275 1.865,0 4.1112,-1.83 5.3512,-5.2825 1.0838,-0.6588 2.1725,-1.4113 3.2125,-2.4363 -0.034,0.3513 -0.054,0.7025 -0.054,1.0638 0,3.4275 1.4987,5.5037 3.8962,5.5037 1.88,0 3.2863,-1.3337 4.2825,-3.33 0.064,1.1513 0.1025,2.2113 0.1175,3.1825 -3.8087,1.7638 -8.0225,3.55 -8.0225,8.5213 0,2.5725 1.855,4.5062 4.2725,4.5062 5.3075,0 6.5188,-5.6 6.5675,-12.1087 1.7288,-0.7475 3.0125,-1.3238 4.4975,-2.0613 1.2688,1.5925 2.9975,2.3888 4.58,2.3888 2.9925,0 5.2438,-1.5875 7.05,-4.805 0.3175,2.4462 0.9525,4.805 2.2563,4.805 2.3725,0 2.8562,-12.4125 4.6187,-12.4125 1.3525,0 0.245,13.4275 3.8138,13.4275 3.0562,0 3.6275,-11.8163 5.1175,-11.8163 1.055,0 1.1325,10.8013 4.4625,10.8013 1.6362,0 3.4137,-1.9688 4.3012,-6.09 0.42,2.745 1.8025,6.09 4.5075,6.09 1.5775,0 2.935,-1.5975 3.9838,-3.7163 0.2887,2.1825 0.9037,3.7163 2.1,3.7163 3.11,0 3.0075,-12.3838 5.4687,-12.3838 1.9188,0 1.3288,12.3838 5.8988,12.3838 2.1725,0 3.2025,-1.8513 3.8187,-4.18 0.8388,3.4225 2.2013,4.18 3.315,4.18 0.7075,0 1.245,-0.25 1.9488,-1.085 -3.5363,-1.5325 -3.2375,-7.1138 -3.2375,-10.7175 m -74.8438,21.27 c -1.0987,0 -1.68,-1.045 -1.68,-2.2225 0,-3.1788 2.3338,-4.8625 5.205,-6.3125 -0.1275,6.9425 -1.7437,8.535 -3.525,8.535 m 14.2775,-22.51 c 1.0688,0 1.6788,0.9812 1.5713,2.3925 -0.1213,1.655 -1.3275,3.555 -3.4275,5.0437 -1.0938,-3.115 -0.2775,-7.4362 1.8562,-7.4362 M 99.6722,6.035 c 1.0162,-0.034 1.7287,-0.9075 1.7337,-1.9475 0.01,-1.04 -0.6987,-1.8613 -1.7187,-1.8225 -1.02,0.035 -1.85,0.9087 -1.855,1.9487 -0.01,1.04 0.82,1.855 1.84,1.8213 m 25.3325,0.5275 c 0.9275,-0.034 1.685,-0.8638 1.685,-1.855 0,-0.9913 -0.7425,-1.7675 -1.67,-1.7388 -0.9288,0.034 -1.685,0.8688 -1.69,1.86 -0.01,0.9913 0.7475,1.7675 1.675,1.7338 m 34.4387,8.2425 c -0.079,-3.9263 -1.9437,-7.2363 -4.825,-9.8788 -2.1875,-1.9962 -4.785,-3.515 -7.5087,-4.6575 -0.215,-0.092 -0.44,-0.1812 -0.66,-0.2687 -3.3538,4.0187 -14.965,7.0162 -14.965,15.44 0,3.29 2.08,6.3712 5.1312,7.6075 1.7725,0.6687 3.54,0.7025 5.3125,0.1062 1.5775,-0.5175 2.8713,-1.4937 3.95,-2.68 3.4088,-3.775 4.795,-9.6187 8.98,-9.6187 3.8275,0 4.345,2.7237 4.59,4.1987 0,-0.01 0,-0.1075 -0.01,-0.2487" />
</svg>
<!-- version: 20171223, original size: 159.4487 35.556198, border: 3% -->"""


# Capgemini Invent brand logo (transparent PNG) embedded as base64 so
# Streamlit doesn't need a static-file route. Loaded once at module
# import time. The PNG lives at data/branding/capgemini_invent_logo.png
# inside the repo and is the official Invent_Logo_2COL_RGB asset.
import base64 as _b64
import os.path as _osp
_LOGO_PNG_PATH = _osp.join(
    _osp.dirname(_osp.dirname(_osp.abspath(__file__))),
    "data", "branding", "capgemini_invent_logo.png",
)
try:
    with open(_LOGO_PNG_PATH, "rb") as _f:
        _LOGO_DATA_URI = "data:image/png;base64," + _b64.b64encode(_f.read()).decode("ascii")
except Exception:
    _LOGO_DATA_URI = ""


# Horizontal padding shared by the block-container and the header bleed
_PAD = "3.5rem"

# ── Global CSS ───────────────────────────────────────────────────────────────

_GLOBAL_CSS = f"""
<style>
/* Ubuntu from Google Fonts */
@import url('https://fonts.googleapis.com/css2?family=Ubuntu:ital,wght@0,400;0,500;0,700;1,400;1,500;1,700&family=Comfortaa:wght@600;700&display=swap');

/* ── Base ──────────────────────────────────────────────────────────────── */
.stApp {{
    background: {NAVY_DEEP};
    font-family: 'Ubuntu', Arial, sans-serif;
    color: {TEXT_PRIMARY};

    /* Typography scale · single source of truth for every page.
       Bump any size here and it cascades to every helper that uses it. */
    --cap-text-display:  3.2rem;
    --cap-text-h2:       2.25rem;
    --cap-text-h3:       1.75rem;
    --cap-text-lead:     1.4rem;
    --cap-text-body:     1.2rem;
    --cap-text-body-sm:  1.05rem;
    --cap-text-meta:     1.0rem;
    --cap-text-eyebrow:  0.88rem;
    --cap-text-caption:  0.82rem;
}}

/* Remove Streamlit's outer padding so we control every pixel */
.stApp > section[data-testid="stMain"] {{
    padding: 0 !important;
}}

/* Full-width block container · restore breathing room at the top so
   the page eyebrow / title is not clipped against the viewport edge.
   2rem leaves enough room for a comfortable hero start without
   wasting screen space. */
.stApp [data-testid="stMain"] .block-container {{
    padding-top: 2rem !important;
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
.stApp h1 {{ font-size: var(--cap-text-display); line-height: 1.15; margin-bottom: 0.5rem; }}
.stApp h2 {{ font-size: var(--cap-text-h2); line-height: 1.2; }}
.stApp h3 {{ font-size: var(--cap-text-h3); line-height: 1.3; }}

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
.cap-logo-img {{
    height: 38px;
    width: auto;
    display: block;
}}
.cap-logo-wrap {{
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    line-height: 1;
}}
.cap-invent-word {{
    /* "invent" wordmark next to the Capgemini SVG. The brand uses a
       custom italic typeface; Ubuntu Italic is the closest match in
       the fonts already loaded by this page. */
    font-family: 'Ubuntu', 'Segoe UI', sans-serif;
    font-style: italic;
    font-size: 1.65rem;
    font-weight: 500;
    color: #0070ad;
    line-height: 1;
    letter-spacing: -0.01em;
    /* Baseline tweak so 'invent' sits visually centred with
       the Capgemini wordmark next to it. */
    transform: translateY(1px);
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


/* ── Layer 2 staffing row (project label above each multiselect) ───────── */
.l2-staff-row {{
    margin: 0.9rem 0 0 0;
}}
.l2-staff-row:first-of-type {{ margin-top: 0.4rem; }}
.l2-staff-label {{
    background: {NAVY_CARD_2};
    border: 1px solid {NAVY_BORDER};
    border-left: 3px solid {BLUE_CYAN};
    border-radius: 6px 6px 0 0;
    padding: 0.55rem 0.95rem 0.55rem 1rem;
    color: {TEXT_PRIMARY};
    font-size: 0.98rem;
    line-height: 1.3;
    margin-bottom: -1px;
}}
.l2-staff-label strong {{
    color: {BLUE_CYAN};
    font-weight: 700;
}}
.l2-staff-label .l2-staff-id {{
    color: {TEXT_SECONDARY};
    margin-left: 0.25rem;
    font-weight: 500;
}}

/* ── Layer 2 mini cards (consultants + projects) ───────────────────────── */
.l2-mini {{
    background: {NAVY_CARD_2};
    border: 1px solid {NAVY_BORDER};
    border-left: 3px solid {BLUE_CYAN};
    border-radius: 8px;
    padding: 0.85rem 1.05rem;
    margin-bottom: 0.65rem;
    position: relative;
}}
.l2-mini:last-child {{ margin-bottom: 0.2rem; }}
.l2-mini-senior     {{ border-left-color: {BLUE_CYAN}; }}
.l2-mini-manager    {{ border-left-color: {AMBER}; }}
.l2-mini-consultant {{ border-left-color: rgba(160,174,203,0.45); }}
.l2-mini-tier-a     {{ border-left-color: {RED}; }}
.l2-mini-tier-b     {{ border-left-color: {AMBER}; }}
.l2-mini-tier-c     {{ border-left-color: rgba(160,174,203,0.45); }}
.l2-mini-title {{
    color: {TEXT_PRIMARY};
    font-size: var(--cap-text-body);
    line-height: 1.35;
    margin-bottom: 0.45rem;
    font-weight: 500;
}}
.l2-mini-title strong {{
    color: {BLUE_CYAN};
    font-weight: 700;
}}
.l2-mini-title em {{
    color: {TEXT_SECONDARY};
    font-style: italic;
    font-weight: 500;
}}
.l2-mini-line {{
    color: {TEXT_PRIMARY};
    font-size: var(--cap-text-body-sm);
    line-height: 1.45;
    margin-bottom: 0.25rem;
}}
.l2-mini-line:last-child {{ margin-bottom: 0; }}
.l2-mini-bar {{
    height: 5px;
    background: rgba(0,0,0,0.32);
    border-radius: 999px;
    overflow: hidden;
    margin-top: 0.55rem;
}}
.l2-mini-bar-fill {{
    height: 100%;
    border-radius: 999px;
    transition: width 0.4s ease;
}}

/* ── Cards (styled via Streamlit's bordered container) ─────────────────── */
/* st.container(border=True) renders as stVerticalBlockBorderWrapper        */
.stApp [data-testid="stVerticalBlockBorderWrapper"] {{
    background: {NAVY_CARD} !important;
    border: 1px solid {NAVY_BORDER} !important;
    border-top: 3px solid {BLUE_CYAN} !important;
    border-radius: 8px !important;
    box-shadow: 0 2px 16px rgba(0,0,0,0.25) !important;
    display: flex !important;
    flex-direction: column !important;
    flex: 1 !important;
}}
/* Inner block · also flex so button can be pushed down */
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
   form or another widget container · anything that ends up last in the
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

.cap-banner.cap-banner-warn {{
    background: rgba(254,177,0,0.10);
    border: 1px solid rgba(254,177,0,0.35);
    border-left: 3px solid {AMBER};
}}
.cap-banner.cap-banner-warn .icon {{ color: {AMBER}; }}
.cap-banner.cap-banner-crit {{
    background: rgba(255,129,110,0.10);
    border: 1px solid rgba(255,129,110,0.4);
    border-left: 3px solid {RED};
}}
.cap-banner.cap-banner-crit .icon {{ color: {RED}; }}

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

/* ── Radio / Checkbox ──────────────────────────────────────────────────────
   Style each radio option inside a stRadio widget as a clickable choice
   card. The native input + label structure stays intact (Streamlit keeps
   driving selection), only the visual container around each label changes.
   Applies to the Layer 1 questions, the Layer 1 verbal example preview,
   and the Layer 2 decision + trade-off modals.                              */
.stApp [data-testid="stRadio"] > label {{ color: {TEXT_PRIMARY}; }}

.stApp [data-testid="stRadio"] [role="radiogroup"] {{
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
}}
.stApp [data-testid="stRadio"] [role="radiogroup"] > label {{
    background: rgba(0,0,0,0.22);
    border: 1px solid {NAVY_BORDER};
    border-radius: 6px;
    padding: 0.65rem 1rem 0.65rem 0.85rem;
    margin: 0 !important;
    transition: background 0.15s ease, border-color 0.15s ease;
    cursor: pointer;
    align-items: flex-start;
}}
.stApp [data-testid="stRadio"] [role="radiogroup"] > label:hover {{
    background: rgba(29,184,242,0.08);
    border-color: rgba(29,184,242,0.42);
}}
.stApp [data-testid="stRadio"] [role="radiogroup"] > label[data-checked="true"],
.stApp [data-testid="stRadio"] [role="radiogroup"] > label:has(input:checked) {{
    background: rgba(29,184,242,0.14);
    border-color: {BLUE_CYAN};
    box-shadow: 0 0 0 1px rgba(29,184,242,0.35);
}}
.stApp [data-testid="stRadio"] [role="radiogroup"] > label > div:first-child {{
    margin-top: 0.18rem;
}}
.stApp [data-testid="stRadio"] [role="radiogroup"] > label p {{
    color: {TEXT_PRIMARY};
    font-size: 0.96rem;
    line-height: 1.4;
}}
.stApp [data-testid="stRadio"] [role="radiogroup"] > label p strong {{
    color: {BLUE_CYAN};
    font-weight: 700;
}}

/* ── Card paragraph · equalise heights across sibling cards ─────────────── */
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

/* ── Equal-height columns · full flex cascade to pin button at bottom ──────── */
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
/* (No per-markdown flex rule needed · the last-child margin-top:auto
   above takes care of bottom-aligning the CTA in action cards.) */

/* ── Vertical journey timeline ─────────────────────────────────────────────
   Used by ui.journey_timeline() - a column of "stations" (numbered
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
    font-size: 1.65rem;
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
   Used by ui.theme_card() - a tall card with an inline SVG illustration
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
    font-size: 1.85rem;
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

/* ── Theme demo (visual mock-up of a sample question) ──────────────────────
   A framed canvas inside a card showing what the candidate will actually
   see during the test. Sits inside an existing card body.            */
.cap-theme-demo {{
    background: linear-gradient(180deg, rgba(29,184,242,0.04) 0%, rgba(0,88,171,0.06) 100%);
    border: 1px solid {NAVY_BORDER};
    border-radius: 10px;
    padding: 1.25rem;
    margin-top: 0.5rem;
    text-align: center;
}}
.cap-theme-demo svg {{
    width: 100%;
    max-width: 32rem;
    height: auto;
    display: block;
    margin: 0 auto;
}}
.cap-theme-demo-caption {{
    color: {TEXT_MUTED};
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    margin-top: 0.85rem;
}}

/* ── Chip rows (pill-shaped tags inside cards) ────────────────────────── */
.cap-chips {{
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin: 0.4rem 0;
}}
.cap-chip {{
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    background: rgba(29,184,242,0.10);
    border: 1px solid rgba(29,184,242,0.35);
    color: {TEXT_PRIMARY};
    border-radius: 999px;
    padding: 0.32rem 0.85rem 0.32rem 0.7rem;
    font-size: 0.85rem;
    font-weight: 600;
    line-height: 1.2;
}}
.cap-chip-glyph {{
    color: {BLUE_CYAN};
    font-weight: 800;
    font-size: 0.95rem;
    line-height: 1;
}}
.cap-chip-list {{
    margin: 0.5rem 0;
}}
.cap-chip-list .cap-chip-item {{
    display: flex;
    align-items: flex-start;
    gap: 0.7rem;
    padding: 0.55rem 0;
    border-bottom: 1px solid {NAVY_BORDER};
}}
.cap-chip-list .cap-chip-item:last-child {{ border-bottom: none; }}
.cap-chip-list .cap-chip-item .cap-chip-bullet {{
    color: {BLUE_CYAN};
    flex-shrink: 0;
    width: 0.55rem;
    height: 0.55rem;
    border-radius: 50%;
    background: {BLUE_CYAN};
    margin-top: 0.45rem;
    box-shadow: 0 0 0 3px rgba(29,184,242,0.18);
}}
.cap-chip-list .cap-chip-item .cap-chip-text strong {{
    color: {TEXT_PRIMARY};
    font-weight: 700;
}}
.cap-chip-list .cap-chip-item .cap-chip-text {{
    color: {TEXT_SECONDARY};
    line-height: 1.45;
    font-size: 0.95rem;
}}

/* ── Editorial card ────────────────────────────────────────────────────────
   A single wide card with a left cyan accent stripe and several stacked
   sections separated by thin dividers. Each section starts with a small
   all-caps cyan eyebrow followed by body content. Matches the slide-deck
   visual language for the in-app long-form pages.                       */
.cap-edit-card {{
    background: {NAVY_CARD};
    border: 1px solid {NAVY_BORDER};
    border-left: 3px solid {BLUE_CYAN};
    border-radius: 8px;
    padding: 2.1rem 2.4rem 1.8rem 2.4rem;
    margin: 0.5rem 0 1rem 0;
    box-shadow: 0 4px 24px rgba(0,0,0,0.25);
}}
.cap-edit-section {{ padding: 0.2rem 0; }}
.cap-edit-section + .cap-edit-section {{ padding-top: 1.6rem; }}
.cap-edit-section h4.cap-edit-eyebrow {{
    color: {BLUE_CYAN};
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.20em;
    text-transform: uppercase;
    margin: 0 0 0.85rem 0;
    font-family: 'Ubuntu', sans-serif;
}}
.cap-edit-section .cap-edit-lead {{
    color: {TEXT_PRIMARY};
    font-size: 1.05rem;
    line-height: 1.65;
    margin: 0 0 0.5rem 0;
}}
.cap-edit-section .cap-edit-note {{
    color: {TEXT_SECONDARY};
    font-size: 0.95rem;
    line-height: 1.55;
    margin: 0.6rem 0 0 0;
}}
.cap-edit-divider {{
    border: none;
    border-top: 1px solid {NAVY_BORDER};
    margin: 1.6rem 0 0 0;
    height: 0;
}}
/* Inline pattern-type tags: a horizontal row of plain text separated by
   small bullets. Keeps the "tags" feel without being chip pills. */
.cap-edit-tags {{
    display: flex;
    flex-wrap: wrap;
    gap: 0 0.35rem;
    color: {TEXT_PRIMARY};
    font-size: 1.05rem;
    line-height: 1.7;
    font-weight: 600;
}}
.cap-edit-tags .tag-sep {{
    color: {BLUE_CYAN};
    opacity: 0.7;
    margin: 0 0.25rem;
}}
/* Numbered list with cyan numerals · used for the "how to approach" tips */
ol.cap-edit-steps {{
    counter-reset: capstep;
    list-style: none;
    padding-left: 0;
    margin: 0;
}}
ol.cap-edit-steps li {{
    counter-increment: capstep;
    color: {TEXT_PRIMARY};
    font-size: 1rem;
    line-height: 1.55;
    padding: 0.45rem 0 0.45rem 2.4rem;
    position: relative;
    border-bottom: 1px solid {NAVY_BORDER};
}}
ol.cap-edit-steps li:first-child {{ padding-top: 0.2rem; }}
ol.cap-edit-steps li:last-child {{ border-bottom: none; padding-bottom: 0.2rem; }}
ol.cap-edit-steps li::before {{
    content: counter(capstep, decimal-leading-zero);
    position: absolute;
    left: 0;
    top: 0.35rem;
    color: {BLUE_CYAN};
    font-weight: 700;
    font-size: 0.92rem;
    letter-spacing: 0.05em;
    width: 2rem;
    font-variant-numeric: tabular-nums;
}}
ol.cap-edit-steps li strong {{
    color: {TEXT_PRIMARY};
    font-weight: 700;
    margin-right: 0.4rem;
}}

/* ── Theme-intro magazine spread ───────────────────────────────────────────
   Asymmetric two-panel layout used by Layer 1 theme intros. Left panel
   is a narrow editorial column with a HUGE theme number and stacked
   stat rows; right panel carries the title, subtitle, and editorial
   sections. Designed to feel like a print magazine spread.            */
.cap-spread {{
    display: grid;
    grid-template-columns: 1fr 2.4fr;
    gap: 1.5rem;
    align-items: stretch;
    margin: 0.4rem 0 1.2rem 0;
}}
.cap-spread-left {{
    background: linear-gradient(180deg, {NAVY_CARD_2} 0%, {NAVY_CARD} 100%);
    border: 1px solid {NAVY_BORDER};
    border-left: 4px solid {BLUE_CYAN};
    border-radius: 8px;
    padding: 2rem 1.6rem;
    display: flex;
    flex-direction: column;
}}
.cap-spread-left .side-eyebrow {{
    color: {BLUE_CYAN};
    font-size: var(--cap-text-eyebrow);
    font-weight: 700;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    margin: 0 0 0.5rem 0;
}}
.cap-spread-left .side-num {{
    color: {TEXT_PRIMARY};
    font-family: 'Ubuntu', sans-serif;
    font-weight: 700;
    font-size: 7rem;
    line-height: 0.95;
    letter-spacing: -0.04em;
    margin: 0.2rem 0 1.5rem 0;
    background: linear-gradient(135deg, {TEXT_PRIMARY} 0%, {BLUE_CYAN} 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}}
.cap-spread-left .side-stats {{
    margin-top: auto;
    border-top: 1px solid {NAVY_BORDER};
    padding-top: 1rem;
}}
.cap-spread-left .stat-row {{
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    padding: 0.55rem 0;
    border-bottom: 1px solid {NAVY_BORDER};
}}
.cap-spread-left .stat-row:last-child {{ border-bottom: none; }}
.cap-spread-left .stat-num {{
    color: {TEXT_PRIMARY};
    font-size: 1.5rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
}}
.cap-spread-left .stat-num .unit {{
    color: {BLUE_CYAN};
    font-size: 0.95rem;
    font-weight: 600;
    margin-left: 0.15rem;
}}
.cap-spread-left .stat-label {{
    color: {TEXT_SECONDARY};
    font-size: var(--cap-text-eyebrow);
    font-weight: 700;
    letter-spacing: 0.16em;
    text-transform: uppercase;
}}
.cap-spread-right {{
    /* Hosts the title block + a 2x2 grid of mini feature cards */
    display: flex;
    flex-direction: column;
    gap: 1.4rem;
}}
.cap-spread-right .right-head {{
    background: {NAVY_CARD};
    border: 1px solid {NAVY_BORDER};
    border-radius: 8px;
    padding: 1.7rem 2rem;
}}
.cap-spread-right .right-eyebrow {{
    color: {BLUE_CYAN};
    font-size: var(--cap-text-eyebrow);
    font-weight: 700;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    margin: 0 0 0.4rem 0;
}}
.cap-spread-right .right-title {{
    color: {TEXT_PRIMARY};
    font-family: 'Ubuntu', sans-serif;
    font-weight: 700;
    font-size: 2.4rem;
    line-height: 1.1;
    letter-spacing: -0.02em;
    margin: 0 0 0.5rem 0;
}}
.cap-spread-right .right-sub {{
    color: {TEXT_SECONDARY};
    font-size: var(--cap-text-lead);
    line-height: 1.5;
    margin: 0;
}}

/* 2x2 grid of mini feature cards */
.cap-feat-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1rem;
}}
.cap-feat {{
    background: {NAVY_CARD};
    border: 1px solid {NAVY_BORDER};
    border-top: 3px solid {BLUE_CYAN};
    border-radius: 8px;
    padding: 1.3rem 1.4rem;
    display: flex;
    flex-direction: column;
}}
.cap-feat-eyebrow {{
    color: {BLUE_CYAN};
    font-size: var(--cap-text-eyebrow);
    font-weight: 700;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    margin: 0 0 0.85rem 0;
}}
.cap-feat-body {{
    color: {TEXT_PRIMARY};
    font-size: var(--cap-text-body);
    line-height: 1.5;
    margin: 0;
}}
.cap-feat-body strong {{
    color: {BLUE_CYAN};
    font-weight: 700;
}}
.cap-feat-stats {{
    display: flex;
    flex-direction: column;
    gap: 0.55rem;
    margin-top: 0.2rem;
}}
.cap-feat-stat-line {{
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    padding: 0.25rem 0;
    border-bottom: 1px solid {NAVY_BORDER};
}}
.cap-feat-stat-line:last-child {{ border-bottom: none; }}
.cap-feat-stat-num {{
    color: {TEXT_PRIMARY};
    font-weight: 700;
    font-size: 1.15rem;
    font-variant-numeric: tabular-nums;
}}
.cap-feat-stat-label {{
    color: {TEXT_SECONDARY};
    font-size: var(--cap-text-eyebrow);
    font-weight: 600;
    letter-spacing: 0.14em;
    text-transform: uppercase;
}}
.cap-feat-pills {{
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin-top: 0.2rem;
}}
.cap-feat-pill {{
    background: rgba(29,184,242,0.10);
    border: 1px solid rgba(29,184,242,0.35);
    color: {TEXT_PRIMARY};
    font-size: var(--cap-text-body-sm);
    font-weight: 600;
    padding: 0.28rem 0.7rem;
    border-radius: 999px;
}}
.cap-feat-tips {{
    list-style: none;
    padding: 0;
    margin: 0;
    counter-reset: feattip;
}}
.cap-feat-tips li {{
    counter-increment: feattip;
    color: {TEXT_PRIMARY};
    font-size: var(--cap-text-body-sm);
    line-height: 1.5;
    padding: 0.4rem 0 0.4rem 1.7rem;
    position: relative;
    border-bottom: 1px solid {NAVY_BORDER};
}}
.cap-feat-tips li:last-child {{ border-bottom: none; padding-bottom: 0.2rem; }}
.cap-feat-tips li:first-child {{ padding-top: 0.1rem; }}
.cap-feat-tips li::before {{
    content: counter(feattip);
    position: absolute;
    left: 0;
    top: 0.5rem;
    color: {BLUE_CYAN};
    font-weight: 700;
    font-size: 0.85rem;
    width: 1.4rem;
    font-variant-numeric: tabular-nums;
}}
.cap-feat-tips li strong {{
    color: {TEXT_PRIMARY};
    font-weight: 700;
    margin-right: 0.3rem;
}}

@media (max-width: 700px) {{
    .cap-feat-grid {{ grid-template-columns: 1fr; }}
}}

/* Mobile-ish stacking when the viewport gets narrow */
@media (max-width: 900px) {{
    .cap-spread {{
        grid-template-columns: 1fr;
    }}
    .cap-spread-left .side-num {{ font-size: 5rem; }}
}}

/* ── Question screen (Layer 1) ─────────────────────────────────────────────
   Header eyebrow + horizontal progress rail + countdown timer pill,
   then a styled question card with bigger stem text. Replaces the
   default Streamlit chrome.                                            */
.cap-q-eyebrow {{
    color: {BLUE_CYAN};
    font-size: var(--cap-text-eyebrow);
    font-weight: 700;
    letter-spacing: 0.20em;
    text-transform: uppercase;
    margin: 0 0 0.85rem 0;
}}
.cap-q-bar {{
    display: flex;
    align-items: center;
    gap: 1.2rem;
    margin: 0 0 1.5rem 0;
}}
.cap-q-progress {{
    flex: 1;
    height: 10px;
    background: {NAVY_CARD_2};
    border: 1px solid {NAVY_BORDER};
    border-radius: 5px;
    overflow: hidden;
}}
.cap-q-progress-fill {{
    height: 100%;
    background: linear-gradient(90deg, {BLUE_PRIMARY} 0%, {BLUE_CYAN} 100%);
    transition: width 0.3s ease;
    border-radius: 4px;
}}
.cap-q-timer {{
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1.1rem;
    border-radius: 999px;
    font-weight: 700;
    font-size: var(--cap-text-meta);
    letter-spacing: 0.04em;
    font-variant-numeric: tabular-nums;
    border: 1.5px solid;
    flex-shrink: 0;
    font-family: 'Ubuntu', sans-serif;
}}
.cap-q-timer.tone-ok {{ color: {BLUE_CYAN}; background: rgba(29,184,242,0.10); border-color: {BLUE_CYAN}; }}
.cap-q-timer.tone-warn {{ color: {AMBER}; background: rgba(254,177,0,0.12); border-color: {AMBER}; }}
.cap-q-timer.tone-crit {{ color: {RED}; background: rgba(255,129,110,0.15); border-color: {RED}; }}
.cap-q-timer .dot {{
    width: 0.55rem;
    height: 0.55rem;
    border-radius: 50%;
    background: currentColor;
    box-shadow: 0 0 0 3px rgba(255,255,255,0.05);
}}
.cap-q-stem {{
    color: {TEXT_PRIMARY};
    font-size: 1.95rem;
    font-weight: 600;
    line-height: 1.35;
    margin: 0.5rem 0 1.5rem 0;
    letter-spacing: -0.005em;
    font-family: 'Ubuntu', sans-serif;
}}
.cap-q-submit-spacer {{
    height: 0.6rem;
}}
</style>
"""


def inject_global_styles() -> None:
    """Inject the app-wide CSS. Idempotent · safe to call on every render."""
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)


# ── Components ────────────────────────────────────────────────────────────────

def header(meta: Optional[str] = None) -> None:
    """Full-bleed top bar with the Capgemini Invent logo + optional right label.

    Renders the official Capgemini Invent PNG (loaded once into
    _LOGO_DATA_URI at module import). If the PNG isn't available for
    some reason, falls back to the embedded SVG wordmark.
    """
    meta_html = f'<div class="meta">{_esc(meta)}</div>' if meta else ""
    if _LOGO_DATA_URI:
        logo_html = (
            f'<img class="cap-logo-img" src="{_LOGO_DATA_URI}" '
            f'alt="Capgemini Invent" />'
        )
    else:
        logo_html = _LOGO_SVG
    st.markdown(
        f'<div class="cap-header">{logo_html}{meta_html}</div>',
        unsafe_allow_html=True,
    )


def eyebrow(text: str) -> None:
    """Small all-caps cyan label with glowing dot · used above page titles."""
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
    """KPI card · big value + short uppercase descriptor."""
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
    """Context manager · wraps Streamlit widgets in a styled bordered card.

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


def layer_complete_hero(eyebrow: str, title: str, subtitle: str) -> None:
    """Centered celebration hero for layer-complete screens.

    Renders the teal checkmark badge, the eyebrow ('STAGE N OF 3
    COMPLETE'), the big page title ('Layer N Complete'), and the
    subtitle paragraph - all stacked, centred, on a single visual
    block. Replaces calling completion_badge + eyebrow + page_title
    separately, which produced an awkward mix of centred badge above
    left-aligned text.
    """
    st.markdown(
        '''
<div style="text-align:center;margin:1.5rem 0 1.6rem 0;">
  <div style="display:inline-flex;align-items:center;justify-content:center;width:68px;height:68px;border-radius:50%;background:rgba(0,213,208,0.14);border:2px solid #00D5D0;box-shadow:0 0 0 6px rgba(0,213,208,0.07);margin-bottom:1.1rem;">
    <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="#00D5D0" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  </div>
  <div style="font-size:0.82rem;font-weight:700;letter-spacing:0.18em;text-transform:uppercase;color:#1DB8F2;margin-bottom:0.55rem;">EYEBROW_HERE</div>
  <h1 style="margin:0 0 0.7rem 0;font-size:2.9rem;font-weight:700;line-height:1.1;color:#FFFFFF;">TITLE_HERE</h1>
  <p style="color:#A0AECB;font-size:1.12rem;line-height:1.55;margin:0 auto;max-width:680px;">SUBTITLE_HERE</p>
</div>
'''
        .replace("EYEBROW_HERE", _esc(eyebrow))
        .replace("TITLE_HERE", _esc(title))
        .replace("SUBTITLE_HERE", _esc(subtitle)),
        unsafe_allow_html=True,
    )


def completion_badge() -> None:
    """Centred 'all done' checkmark in a teal circle.

    Used at the top of each layer-complete screen so the candidate gets
    a moment of visual celebration before the next-step copy. No text -
    pure visual flourish.
    """
    st.markdown(
        '<div style="display:flex;justify-content:center;'
        'margin:1.5rem 0 0.75rem 0;">'
        '<div style="width:68px;height:68px;border-radius:50%;'
        'background:rgba(0,213,208,0.14);'
        'border:2px solid #00D5D0;display:flex;align-items:center;'
        'justify-content:center;box-shadow:0 0 0 6px rgba(0,213,208,0.07);">'
        '<svg width="34" height="34" viewBox="0 0 24 24" fill="none" '
        'stroke="#00D5D0" stroke-width="2.5" stroke-linecap="round" '
        'stroke-linejoin="round">'
        '<polyline points="20 6 9 17 4 12"/>'
        '</svg></div></div>',
        unsafe_allow_html=True,
    )


def info_banner(text: str, icon: str = "ℹ", tone: str = "info") -> None:
    """Left-accented banner for contextual notes.

    tone:
      'info' (default) - cyan accent, for neutral hints / next-step prompts
      'warn'           - amber accent, for cautions like a decision the
                         candidate must make before continuing
      'crit'           - red accent, for harder warnings (trade-off modal)
    """
    tone_class = {
        "info": "",
        "warn": " cap-banner-warn",
        "crit": " cap-banner-crit",
    }.get(tone, "")
    st.markdown(
        f"""
        <div class="cap-banner{tone_class}">
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
    bordered strip across the bottom of the card · ideal for showing
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


# ── Theme demo SVGs ────────────────────────────────────────────────────────
# Larger illustrative SVGs that mock up what the candidate will see during
# the test. Used by the Layer 1 theme intros via ui.theme_demo().

THEME_DEMO_LOGICAL = (
    '<svg viewBox="0 0 360 360" xmlns="http://www.w3.org/2000/svg" fill="none">'
    # Subtle 3x3 grid lines
    '<line x1="120" y1="10" x2="120" y2="350" stroke="#28387A" stroke-dasharray="3 4" opacity="0.5"/>'
    '<line x1="240" y1="10" x2="240" y2="350" stroke="#28387A" stroke-dasharray="3 4" opacity="0.5"/>'
    '<line x1="10" y1="120" x2="350" y2="120" stroke="#28387A" stroke-dasharray="3 4" opacity="0.5"/>'
    '<line x1="10" y1="240" x2="350" y2="240" stroke="#28387A" stroke-dasharray="3 4" opacity="0.5"/>'
    # Row 1 · open shapes
    '<polygon points="60,40 90,90 30,90" stroke="#1DB8F2" stroke-width="2.5"/>'
    '<rect x="150" y="40" width="60" height="50" stroke="#1DB8F2" stroke-width="2.5"/>'
    '<circle cx="300" cy="65" r="28" stroke="#1DB8F2" stroke-width="2.5"/>'
    # Row 2 · filled shapes
    '<polygon points="60,160 90,210 30,210" fill="#1DB8F2"/>'
    '<rect x="150" y="160" width="60" height="50" fill="#1DB8F2"/>'
    '<circle cx="300" cy="185" r="28" fill="#1DB8F2"/>'
    # Row 3 · half-filled
    '<polygon points="60,280 90,330 30,330" stroke="#1DB8F2" stroke-width="2.5" fill="#1DB8F2" fill-opacity="0.45"/>'
    '<rect x="150" y="280" width="60" height="50" stroke="#1DB8F2" stroke-width="2.5" fill="#1DB8F2" fill-opacity="0.45"/>'
    # Missing cell with question mark
    '<rect x="262" y="262" width="76" height="76" rx="8" stroke="#1DB8F2" stroke-width="2.5" stroke-dasharray="6 5"/>'
    '<text x="300" y="318" text-anchor="middle" font-size="48" font-family="Ubuntu, sans-serif" font-weight="700" fill="#1DB8F2">?</text>'
    '</svg>'
)

THEME_DEMO_NUMERICAL = (
    '<svg viewBox="0 0 400 240" xmlns="http://www.w3.org/2000/svg" fill="none">'
    # Y-axis label
    '<text x="14" y="22" font-size="11" font-family="Ubuntu, sans-serif" font-weight="700" letter-spacing="2" fill="#1DB8F2">REVENUE · CHF M</text>'
    # Y axis grid lines
    '<line x1="40" y1="50" x2="380" y2="50" stroke="#28387A" stroke-dasharray="2 4" opacity="0.4"/>'
    '<line x1="40" y1="100" x2="380" y2="100" stroke="#28387A" stroke-dasharray="2 4" opacity="0.4"/>'
    '<line x1="40" y1="150" x2="380" y2="150" stroke="#28387A" stroke-dasharray="2 4" opacity="0.4"/>'
    # Bars (Q1-Q4)
    '<rect x="60"  y="120" width="50" height="80"  rx="2" fill="#1DB8F2" fill-opacity="0.55"/>'
    '<rect x="140" y="80"  width="50" height="120" rx="2" fill="#1DB8F2" fill-opacity="0.7"/>'
    '<rect x="220" y="100" width="50" height="100" rx="2" fill="#1DB8F2" fill-opacity="0.7"/>'
    '<rect x="300" y="40"  width="50" height="160" rx="2" fill="#1DB8F2"/>'
    # X axis
    '<line x1="40" y1="200" x2="380" y2="200" stroke="#A0AECB" stroke-width="1.5"/>'
    # X axis labels
    '<text x="85"  y="218" font-size="11" font-family="Ubuntu, sans-serif" fill="#A0AECB" text-anchor="middle">Q1</text>'
    '<text x="165" y="218" font-size="11" font-family="Ubuntu, sans-serif" fill="#A0AECB" text-anchor="middle">Q2</text>'
    '<text x="245" y="218" font-size="11" font-family="Ubuntu, sans-serif" fill="#A0AECB" text-anchor="middle">Q3</text>'
    '<text x="325" y="218" font-size="11" font-family="Ubuntu, sans-serif" fill="#A0AECB" text-anchor="middle">Q4</text>'
    # Question pill
    '<rect x="40" y="232" width="320" height="0" stroke="#28387A"/>'
    '</svg>'
)

THEME_DEMO_VERBAL = (
    '<svg viewBox="0 0 400 240" xmlns="http://www.w3.org/2000/svg" fill="none">'
    # Passage box (mock document)
    '<rect x="10" y="10" width="380" height="115" rx="8" fill="#1F2D52" stroke="#28387A"/>'
    # Passage label
    '<text x="22" y="32" font-size="10" font-family="Ubuntu, sans-serif" font-weight="700" letter-spacing="2" fill="#A0AECB">PASSAGE</text>'
    # Text lines
    '<rect x="22" y="44" width="356" height="4" rx="2" fill="#A0AECB" opacity="0.55"/>'
    '<rect x="22" y="56" width="338" height="4" rx="2" fill="#A0AECB" opacity="0.55"/>'
    '<rect x="22" y="68" width="356" height="4" rx="2" fill="#A0AECB" opacity="0.55"/>'
    '<rect x="22" y="80" width="280" height="4" rx="2" fill="#A0AECB" opacity="0.55"/>'
    '<rect x="22" y="92" width="356" height="4" rx="2" fill="#A0AECB" opacity="0.55"/>'
    '<rect x="22" y="104" width="220" height="4" rx="2" fill="#A0AECB" opacity="0.55"/>'
    # Statement label
    '<text x="10" y="148" font-size="10" font-family="Ubuntu, sans-serif" font-weight="700" letter-spacing="2" fill="#1DB8F2">STATEMENT</text>'
    # Statement text (brighter)
    '<rect x="10" y="158" width="360" height="5" rx="2" fill="#FFFFFF" opacity="0.85"/>'
    '<rect x="10" y="170" width="240" height="5" rx="2" fill="#FFFFFF" opacity="0.85"/>'
    # Answer pills
    '<rect x="10" y="200" width="78" height="32" rx="16" fill="rgba(29,184,242,0.08)" stroke="#1DB8F2" stroke-width="1.5"/>'
    '<text x="49" y="220" font-size="11" font-family="Ubuntu, sans-serif" font-weight="700" letter-spacing="1.5" fill="#1DB8F2" text-anchor="middle">TRUE</text>'
    '<rect x="98" y="200" width="78" height="32" rx="16" fill="rgba(29,184,242,0.08)" stroke="#1DB8F2" stroke-width="1.5"/>'
    '<text x="137" y="220" font-size="11" font-family="Ubuntu, sans-serif" font-weight="700" letter-spacing="1.5" fill="#1DB8F2" text-anchor="middle">FALSE</text>'
    '<rect x="186" y="200" width="138" height="32" rx="16" fill="rgba(29,184,242,0.08)" stroke="#1DB8F2" stroke-width="1.5"/>'
    '<text x="255" y="220" font-size="11" font-family="Ubuntu, sans-serif" font-weight="700" letter-spacing="1.5" fill="#1DB8F2" text-anchor="middle">CANNOT SAY</text>'
    '</svg>'
)


def theme_demo(svg: str, caption: Optional[str] = None) -> None:
    """Render a framed visual demo (SVG mock-up) inside a card body.
    Used on Layer 1 theme intros to show candidates an example of the
    question type they're about to see.
    """
    parts = [
        '<div class="cap-theme-demo">',
        svg,
    ]
    if caption:
        parts.append('<div class="cap-theme-demo-caption">' + _esc(caption) + '</div>')
    parts.append('</div>')
    st.markdown("".join(parts), unsafe_allow_html=True)


def chip_row(items: list) -> None:
    """Render a row of pill-shaped tags. items: list of (glyph, label).
    The glyph is a small cyan symbol (e.g. arrow, ↻, 1·2·3) shown to the
    left of the label inside each chip.
    """
    parts = ['<div class="cap-chips">']
    for glyph, label in items:
        parts.append(
            '<span class="cap-chip">'
            '<span class="cap-chip-glyph">' + _esc(glyph) + '</span>'
            '<span>' + _esc(label) + '</span>'
            '</span>'
        )
    parts.append('</div>')
    st.markdown("".join(parts), unsafe_allow_html=True)


def chip_list(items: list) -> None:
    """Vertical bullet-style list with strong-tagged head + body.
    items: list of (head, body) tuples · head appears bold, body in
    muted text body. Use for short tip lists where each tip has a
    one-word strategy verb followed by a sentence of detail.
    """
    parts = ['<div class="cap-chip-list">']
    for head, body in items:
        parts.append(
            '<div class="cap-chip-item">'
            '<span class="cap-chip-bullet"></span>'
            '<span class="cap-chip-text"><strong>' + _esc(head) + '</strong> ' + _esc(body) + '</span>'
            '</div>'
        )
    parts.append('</div>')
    st.markdown("".join(parts), unsafe_allow_html=True)


def editorial_card(sections: list) -> None:
    """Render a wide editorial card with stacked, divider-separated sections.

    `sections` is a list of dicts with keys:
        eyebrow  (str)        small all-caps section label
        body_html (str)       inner HTML (rendered as-is, must be safe)
    Sections render in order, separated by a thin border line. The card
    has a cyan left accent stripe and matches the slide-deck visual
    language. Use for in-app long-form pages where the content reads as
    a short editorial article (theme intros, results explanations, etc.).
    """
    parts = ['<div class="cap-edit-card">']
    for i, sec in enumerate(sections):
        if i > 0:
            parts.append('<hr class="cap-edit-divider"/>')
        parts.append('<div class="cap-edit-section">')
        parts.append('<h4 class="cap-edit-eyebrow">' + _esc(sec.get("eyebrow", "")) + '</h4>')
        parts.append(sec.get("body_html", ""))
        parts.append('</div>')
    parts.append('</div>')
    st.markdown("".join(parts), unsafe_allow_html=True)


def question_progress_bar(idx: int, total: int, remaining: int, seconds: int,
                          eyebrow_text: str) -> None:
    """Render the Layer 1 question screen header: eyebrow + horizontal
    progress rail + countdown timer pill.

    The timer pill changes tone (cyan / amber / red) based on how much
    time is left vs the per-question budget.
    """
    pct = max(0, min(100, int(((idx) / max(total, 1)) * 100)))
    # Tone thresholds scale with the time limit.
    if seconds > 0 and remaining > max(20, seconds // 3):
        tone = "tone-ok"
    elif remaining > max(10, seconds // 6):
        tone = "tone-warn"
    else:
        tone = "tone-crit"

    # Format the countdown: MM:SS when remaining >= 60, otherwise 'Ns'.
    # This keeps the visual compact when theme-level timers run up to
    # 20+ minutes and still reads naturally in the last minute.
    if remaining >= 60:
        mins, secs = divmod(int(remaining), 60)
        time_str = f"{mins}:{secs:02d} left"
    else:
        time_str = f"{int(remaining)}s left"

    html = (
        '<div class="cap-q-eyebrow">' + _esc(eyebrow_text) + '</div>'
        '<div class="cap-q-bar">'
        '<div class="cap-q-progress"><div class="cap-q-progress-fill" '
        'style="width:' + str(pct) + '%"></div></div>'
        '<span class="cap-q-timer ' + tone + '">'
        '<span class="dot"></span>'
        + time_str +
        '</span>'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def question_stem(text: str) -> None:
    """Render the question stem in large bold text · the primary content
    on the question screen.
    """
    st.markdown(
        '<div class="cap-q-stem">' + _esc(text) + '</div>',
        unsafe_allow_html=True,
    )


def theme_spread(
    eyebrow: str,
    title: str,
    subtitle: str,
    side_num: str,
    side_eyebrow: str,
    stats: list,
    features: list,
) -> None:
    """Asymmetric magazine-spread layout for Layer 1 theme intros.

    Left panel (1fr): small eyebrow, a huge theme number with cyan-to-
    white gradient text, and a vertical stat ladder at the bottom.
    Right panel (2.4fr): a head card carrying the title + subtitle,
    then a 2x2 grid of mini feature cards (The task / The format /
    Watch for / Strategy).

    `stats`    : list of (number, unit, label) tuples for the left side
    `features` : list of dicts with keys 'eyebrow' and 'body_html' —
                 each becomes one mini card in the 2x2 grid.
    """
    stat_rows = []
    for num, unit, label in stats:
        unit_html = (
            '<span class="unit">' + _esc(unit) + '</span>' if unit else ""
        )
        stat_rows.append(
            '<div class="stat-row">'
            '<span class="stat-num">' + _esc(num) + unit_html + '</span>'
            '<span class="stat-label">' + _esc(label) + '</span>'
            '</div>'
        )

    feat_blocks = []
    for feat in features:
        feat_blocks.append(
            '<div class="cap-feat">'
            '<div class="cap-feat-eyebrow">' + _esc(feat.get("eyebrow", "")) + '</div>'
            + feat.get("body_html", "")
            + '</div>'
        )

    html = (
        '<div class="cap-spread">'
        '<div class="cap-spread-left">'
        '<div class="side-eyebrow">' + _esc(side_eyebrow) + '</div>'
        '<div class="side-num">' + _esc(side_num) + '</div>'
        '<div class="side-stats">' + "".join(stat_rows) + '</div>'
        '</div>'
        '<div class="cap-spread-right">'
        '<div class="right-head">'
        '<div class="right-eyebrow">' + _esc(eyebrow) + '</div>'
        '<div class="right-title">' + _esc(title) + '</div>'
        '<div class="right-sub">' + _esc(subtitle) + '</div>'
        '</div>'
        '<div class="cap-feat-grid">' + "".join(feat_blocks) + '</div>'
        '</div>'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)
