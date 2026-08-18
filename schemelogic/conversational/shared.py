"""Shared cached resources + visual system for the conversational app's multi-page Streamlit
setup. Both app.py (the chat entry point) and pages/1_Browse_all_schemes.py import from here so
st.cache_resource/st.cache_data-decorated functions are defined exactly ONCE (Streamlit caches by
function identity -- defining the same logic twice in two files would build the embedding index
twice).

Conversation STATE and the scheme-selection funnel live in chat_engine.py, not here (continuous-
chat redesign) -- this module only ever provides read-only/cached data (the discovery index,
silver records, gold match report) and pure rendering helpers (seals, cards, nav, next-steps).
"""

from __future__ import annotations

import html
import json
from pathlib import Path

import streamlit as st

from schemelogic.conversational import i18n
from schemelogic.conversational.chat_engine import ChatDeps
from schemelogic.discovery.indexer import (
    DescriptionMatch,
    NextSteps,
    build_discovery_index,
    next_steps_for_silver,
    resolve_next_steps,
)
from schemelogic.ingestion.silver_scraper import clean_record_text

ROOT = Path(__file__).resolve().parents[2]
GOLD_DIR = ROOT / "data" / "gold"
SILVER_PATH = ROOT / "data" / "silver" / "schemes.jsonl"
RAW_DOCS_DIR = ROOT / "data" / "raw_documents"


# --- visual system (light theme, matching the Figma reference) ---------------------------------
# Color/type plan: white/light-gray base (#F5F6F8 bg / #FFFFFF surface / #E4E7EC hairline / #1A1A2E
# body text), dark-navy header/wordmark (#0F1B3D), amber/orange brand accent (#C9791A -- nav
# links, category pills, card accent bars, matching the Figma reference exactly). Verdict colors
# stay reserved for their meaning (verified-green ELIGIBLE-only, brick-red INELIGIBLE-only); the
# amber accent is now also the general brand color (nav/pills/cards), which is a deliberate
# departure from the previous dark theme's "semantic colors, never decorative" rule -- the Figma
# design calls for one consistent amber throughout, and Unverified's warrant-amber already lived
# in the same family, so this reads as one coherent choice rather than two colliding systems.
# Clean sans throughout (IBM Plex Sans) instead of the previous serif display face -- the
# reference has no serif characteristics anywhere. IBM Plex Mono kept only for the technical
# rule-trace JSON (inside a collapsed expander, never part of the primary visual language).

# NOTE: this whole string is deliberately ONE unbroken <style> block with no other HTML tags
# ahead of it. A leading <link> tag (or any other CommonMark "type 6" html-block tag) before
# <style> makes the markdown parser end the raw-html block at the first blank LINE it hits --
# which is inside our CSS -- dumping the rest of the stylesheet as literal visible text. <style>
# itself is a "type 1" block (ends only at a literal </style>, blank lines don't count), so fonts
# are loaded via @import from inside it instead of a separate <link> tag.
_CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');
:root {
  --sl-bg: #F5F6F8;
  --sl-surface: #FFFFFF;
  --sl-hairline: #E4E7EC;
  --sl-text: #1A1A2E;
  --sl-muted: #6B7280;
  --sl-navy: #0F1B3D;
  --sl-accent: #C9791A;
  --sl-accent-soft: rgba(201,121,26,0.10);
  --sl-verified: #2F9E67;
  --sl-warrant: #C9791A;
  --sl-ineligible: #C0524B;
  --sl-ai-checked: #4C6FCB;
  --sl-shadow: 0 1px 3px rgba(16,24,40,0.07), 0 1px 2px rgba(16,24,40,0.05);
}

.stApp, .stApp [class*="css"] { font-family: "IBM Plex Sans", -apple-system, sans-serif; color: var(--sl-text); }
h1, h2, h3, .sl-serif { font-family: "IBM Plex Sans", -apple-system, sans-serif !important; font-weight: 700; color: var(--sl-navy); }
code, pre, .stJson, .sl-mono { font-family: "IBM Plex Mono", monospace !important; }

.stApp { background-color: var(--sl-bg); }
section[data-testid="stSidebar"] { background-color: var(--sl-surface); border-right: 1px solid var(--sl-hairline); }

/* -- nav bar (st.container(key="sl_navbar") -- Streamlit stamps this class on its wrapper) -- */
.st-key-sl_navbar {
  padding: 0.9rem 1.25rem; margin: -1rem -1rem 1.5rem -1rem;
  background: var(--sl-surface); border-bottom: 1px solid var(--sl-hairline);
}
.st-key-sl_navbar [data-testid="stHorizontalBlock"] { align-items: center; }
.sl-wordmark {
  font-family: "IBM Plex Sans", -apple-system, sans-serif; font-size: 1.4rem; font-weight: 700;
  color: var(--sl-navy); display: flex; align-items: center; justify-content: center; gap: 0.5rem;
}
.sl-wordmark .sl-mark {
  display: inline-flex; align-items: center; justify-content: center;
  width: 1.6rem; height: 1.6rem; border-radius: 50%; border: 1.5px solid var(--sl-verified);
  color: var(--sl-verified); font-size: 0.85rem; font-family: "IBM Plex Mono", monospace;
}
.sl-nav-link {
  color: var(--sl-accent) !important; font-weight: 600; font-size: 0.95rem;
  display: inline-flex; align-items: center; gap: 0.4rem;
}
.st-key-sl_navbar a[data-testid="stPageLink-NavLink"] {
  border: none !important; background: transparent !important; padding: 0 !important;
}
.st-key-sl_navbar a[data-testid="stPageLink-NavLink"] p { color: var(--sl-accent) !important; font-weight: 600 !important; }
.st-key-sl_navbar a[data-testid="stPageLink-NavLink"]:hover p { text-decoration: underline; }
.st-key-sl_lang_toggle .stButton > button {
  border-radius: 999px !important; border: 1px solid var(--sl-hairline) !important;
  background: var(--sl-surface) !important; color: var(--sl-navy) !important;
  font-size: 0.8rem !important; padding: 0.3rem 0.9rem !important; box-shadow: var(--sl-shadow);
}
.st-key-sl_lang_toggle .stButton > button:hover { border-color: var(--sl-accent) !important; }

/* -- seal badge: the signature verification motif -- */
.sl-seal { display: inline-flex; align-items: center; gap: 0.4rem; font-size: 0.8rem; font-weight: 500; }
.sl-seal .sl-ring {
  display: inline-flex; align-items: center; justify-content: center;
  width: 1.5rem; height: 1.5rem; border-radius: 50%; flex-shrink: 0;
  border: 2px solid currentColor; font-size: 0.75rem; font-family: "IBM Plex Mono", monospace;
}
.sl-seal-verified { color: var(--sl-verified); }
.sl-seal-ai-checked { color: var(--sl-ai-checked); }
.sl-seal-unverified { color: var(--sl-warrant); }

/* -- cards: every scheme/result card uses st.container(border=True, key=f"card_...") so this
   attribute selector catches all of them without depending on Streamlit's internal (and
   version-fragile) testid for bordered containers -- st.container(key=...) always stamps a
   stable "st-key-<key>" class on the wrapper regardless of Streamlit version. -- */
div[class*="st-key-card_"] {
  background: var(--sl-surface); border: 1px solid var(--sl-hairline) !important; border-radius: 12px !important;
  box-shadow: var(--sl-shadow); transition: transform 0.15s ease, box-shadow 0.15s ease;
  border-left: 4px solid var(--sl-accent) !important;
}
div[class*="st-key-card_"]:hover { transform: translateY(-2px); box-shadow: 0 4px 10px rgba(16,24,40,0.10); }
.sl-card-title { font-weight: 600; margin-bottom: 0.15rem; font-size: 1rem; color: var(--sl-navy); }
.sl-card-snippet { color: var(--sl-muted); font-size: 0.85rem; }

/* -- hero / greeting -- */
.sl-hero-thesis {
  font-size: 1.15rem; font-weight: 500; color: var(--sl-text); line-height: 1.5; margin-bottom: 0.5rem;
}
.sl-steps { display: flex; gap: 0; align-items: center; margin-bottom: 1.75rem; flex-wrap: wrap; }
.sl-step { display: flex; align-items: center; gap: 0.5rem; color: var(--sl-muted); font-size: 0.9rem; }
.sl-step-num {
  display: inline-flex; align-items: center; justify-content: center;
  width: 1.6rem; height: 1.6rem; border-radius: 50%; border: 1.5px solid var(--sl-hairline);
  font-family: "IBM Plex Mono", monospace; font-size: 0.75rem; color: var(--sl-navy); flex-shrink: 0;
}
.sl-step-arrow { color: var(--sl-hairline); margin: 0 0.75rem; font-size: 1rem; }

/* Assistant chat bubbles as soft-shadowed white cards with a navy avatar -- matches the Figma
   greeting-bubble look for every assistant turn, not just the first. */
[data-testid="stChatMessage"] { background: transparent !important; }
[data-testid="stChatMessageContent"] {
  background: var(--sl-surface) !important; border-radius: 16px !important; box-shadow: var(--sl-shadow);
  padding: 0.9rem 1.1rem !important;
}
[data-testid="stChatMessageAvatarAssistant"] {
  background: var(--sl-navy) !important; border: none !important;
}
[data-testid="stChatMessageAvatarAssistant"] svg { fill: #FFFFFF !important; }
[data-testid="stChatMessageAvatarUser"] { background: var(--sl-accent-soft) !important; border: none !important; }

/* -- verdict banner -- */
.sl-verdict { padding: 0.9rem 1.1rem; border-radius: 10px; border: 1px solid; font-weight: 600; margin: 0.75rem 0; }
.sl-verdict-eligible { border-color: var(--sl-verified); background: rgba(47,158,103,0.08); color: var(--sl-verified); }
.sl-verdict-ineligible { border-color: var(--sl-ineligible); background: rgba(192,82,75,0.08); color: var(--sl-ineligible); }
.sl-verdict-undetermined { border-color: var(--sl-warrant); background: rgba(201,121,26,0.08); color: var(--sl-warrant); }

/* -- buttons: hover lift, no scale/bounce -- */
.stButton > button, .stTextInput input, .stChatInput textarea {
  transition: transform 0.15s ease, border-color 0.15s ease !important;
}
.stButton > button:hover { transform: translateY(-1px); }
.stButton > button:focus:not(:active) { border-color: var(--sl-accent) !important; color: var(--sl-accent) !important; }

/* -- suggestion cards (2-col grid replacing the old pill-chip row) -- */
.st-key-sl_chip_row .stButton > button {
  border-radius: 14px !important; border: 1px solid var(--sl-hairline) !important;
  background: var(--sl-surface) !important; color: var(--sl-text) !important;
  font-size: 0.9rem !important; font-weight: 400 !important; text-align: left !important;
  padding: 1rem 1.1rem !important; min-height: 4.5rem !important; height: auto !important;
  white-space: normal !important; line-height: 1.4 !important; box-shadow: var(--sl-shadow);
}
.st-key-sl_chip_row .stButton > button:hover { border-color: var(--sl-accent) !important; }
.st-key-sl_chip_row .stButton > button p { white-space: normal !important; text-align: left !important; }

/* -- category filter pills (browse page) -- */
.st-key-sl_category_pills .stButton > button {
  border-radius: 999px !important; border: 1px solid var(--sl-hairline) !important;
  background: var(--sl-surface) !important; color: var(--sl-text) !important;
  font-size: 0.85rem !important; font-weight: 500 !important; padding: 0.4rem 1.1rem !important;
  min-height: 0 !important;
}
.st-key-sl_category_pills .stButton > button:hover { border-color: var(--sl-accent) !important; }
/* the ACTIVE pill is a primary-type button (see Python side) -- Streamlit's own primary styling
   is overridden here to use the brand navy fill instead of its default red/orange. */
.st-key-sl_category_pills .stButton > button[kind="primary"] {
  background: var(--sl-navy) !important; border-color: var(--sl-navy) !important; color: #FFFFFF !important;
}

/* -- expanders: smooth, no gratuitous motion -- */
[data-testid="stExpander"] { border: 1px solid var(--sl-hairline) !important; border-radius: 10px !important; transition: border-color 0.15s ease; background: var(--sl-surface) !important; }

/* -- alerts: mapped onto the semantic palette instead of Streamlit's default red/orange/blue -- */
[data-testid="stAlert"] { border-radius: 10px !important; }
[data-testid="stAlert"]:has([data-testid="stAlertContentWarning"]) { background: rgba(201,121,26,0.08) !important; border: 1px solid var(--sl-warrant) !important; }
[data-testid="stAlertContentWarning"] { color: var(--sl-warrant) !important; }
[data-testid="stAlert"]:has([data-testid="stAlertContentError"]) { background: rgba(192,82,75,0.08) !important; border: 1px solid var(--sl-ineligible) !important; }
[data-testid="stAlertContentError"] { color: var(--sl-ineligible) !important; }
[data-testid="stAlert"]:has([data-testid="stAlertContentInfo"]) { background: var(--sl-surface) !important; border: 1px solid var(--sl-hairline) !important; }
[data-testid="stAlertContentInfo"] { color: var(--sl-text) !important; }

/* -- chat input: pill-shaped bar + disclaimer line, matching the Figma bottom bar -- */
[data-testid="stChatInput"] {
  border-radius: 999px !important; border: 1px solid var(--sl-hairline) !important;
  box-shadow: var(--sl-shadow); background: var(--sl-surface) !important;
}
[data-testid="stBottomBlockContainer"] { background: var(--sl-bg) !important; }
.sl-input-disclaimer { text-align: center; color: var(--sl-muted); font-size: 0.75rem; margin-top: 0.4rem; }

/* -- floating "Ask AI Sahayak" button (browse page -> back to chat) -- */
.st-key-sl_floating_chat { position: fixed; right: 1.5rem; bottom: 1.5rem; z-index: 999; width: auto !important; }
.st-key-sl_floating_chat .stButton > button {
  border-radius: 999px !important; border: none !important; background: var(--sl-navy) !important;
  color: #FFFFFF !important; padding: 0.75rem 1.3rem !important; box-shadow: 0 4px 14px rgba(15,27,61,0.35);
  font-weight: 600 !important;
}
.st-key-sl_floating_chat .stButton > button:hover { transform: translateY(-2px); }

@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; animation: none !important; }
}
</style>
"""


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def esc(text: str) -> str:
    """HTML-escapes scraped/generated text before it goes into any unsafe_allow_html=True
    markdown -- scheme names/descriptions come from government source docs and myScheme scrapes,
    not from us, so they can contain '&', '<', etc that would otherwise break the layout."""
    return html.escape(text)


def _render_language_toggle() -> None:
    with st.container(key="sl_lang_toggle"):
        if st.button("\U0001F310 " + i18n.t("lang_toggle_label"), key="lang_toggle_btn"):
            i18n.toggle_language()
            st.rerun()


def render_nav_bar(active: str = "chat") -> None:
    """Styled horizontal nav bar at the top of main content, not a bare sidebar link.
    Streamlit's built-in multipage nav lives in the sidebar only -- this uses st.page_link inside
    a styled flex container (st.container(key=...) so CSS can target the whole row as one band).
    Layout differs slightly by page, matching the Figma reference exactly: the home/chat page has
    a 3-part bar (Browse-all-schemes link left, centered wordmark, language toggle right); the
    browse page has just the wordmark left + toggle right -- no redundant "browse" link (already
    on that page) and no text "back to chat" link (the floating Ask-AI-Sahayak button covers
    that, see render_floating_chat_button())."""
    with st.container(key="sl_navbar"):
        if active == "chat":
            cols = st.columns([2.5, 3, 1.5])
            with cols[0]:
                st.page_link("pages/1_Browse_all_schemes.py", label=i18n.t("nav_browse"), icon="\U0001F517")
            with cols[1]:
                st.markdown(
                    '<div style="text-align:center;"><span class="sl-wordmark">SchemeLogic</span></div>',
                    unsafe_allow_html=True,
                )
            with cols[2]:
                _render_language_toggle()
        else:
            cols = st.columns([4, 1.5])
            with cols[0]:
                st.markdown('<span class="sl-wordmark">SchemeLogic</span>', unsafe_allow_html=True)
            with cols[1]:
                _render_language_toggle()


def render_floating_chat_button() -> None:
    """The floating bottom-right "Ask AI Sahayak" button on the browse page, routing back to the
    chat page -- this is a NAVIGATION button (st.switch_page), not a chat action; it never touches
    chat_engine state."""
    with st.container(key="sl_floating_chat"):
        if st.button("\U0001F4AC " + i18n.t("ask_ai_sahayak"), key="floating_chat_btn"):
            st.switch_page("app.py")


def render_verdict_banner(verdict_value: str, headline: str) -> None:
    """The eligible/ineligible/undetermined banner -- brick-red is used HERE and only here,
    reserved strictly for the ineligible verdict per the design brief (never decorative)."""
    css_class = {
        "eligible": "sl-verdict-eligible",
        "ineligible": "sl-verdict-ineligible",
    }.get(verdict_value, "sl-verdict-undetermined")
    st.markdown(f'<div class="sl-verdict {css_class}">{esc(headline)}</div>', unsafe_allow_html=True)


_SEAL_TIERS = {
    "gold": ("sl-seal-verified", "&#10003;", "seal_verified"),
    "ai_checked": ("sl-seal-ai-checked", "AI", "seal_ai_checked"),
    # anything else (e.g. "silver", "silver_unverified", the historical `source_type` values from
    # before the three-tier redesign) falls through to the same Unverified styling as before --
    # backward compatible with every existing call site.
}
_SEAL_DEFAULT = ("sl-seal-unverified", "!", "seal_unverified")


def render_seal(tier: str, label: str | None = None) -> str:
    """Circular seal/stamp badge markup -- the one signature visual element, used identically in
    the chat shortlist, browse-all-schemes rows, and scheme detail/Q&A headers. `tier` is one of
    "gold" (Verified, green), "ai_checked" (AI-Checked, muted blue -- rules extracted live and
    validated, but not human-verified), or anything else (Unverified, gold ring -- description
    only, no rule extraction attempted or it failed). Label text follows the language toggle."""
    css_class, glyph, label_key = _SEAL_TIERS.get(tier, _SEAL_DEFAULT)
    text = label or i18n.t(label_key)
    return (
        f'<span class="sl-seal {css_class}">'
        f'<span class="sl-ring">{glyph}</span>{text}</span>'
    )


# --- cached, expensive, local-only setup (no LLM) -------------------------------------------


@st.cache_resource(show_spinner="Building local search index (one-time, no internet cost after model download)...")
def get_discovery_index() -> tuple:
    return build_discovery_index(gold_dir=GOLD_DIR, silver_jsonl_path=SILVER_PATH, raw_documents_dir=RAW_DOCS_DIR)


@st.cache_data
def get_silver_records() -> list[dict]:
    """The ONE place raw schemes.jsonl gets parsed for the whole conversational app -- every
    consumer (silver_by_slug, browse-page rows, AI-Checked extraction input, scheme_detail
    rendering, next-steps text) reads through this, so cleaning mojibake HERE (Bug 3 fix) covers
    all of them at once instead of needing a separate fix at each individual render call site."""
    if not SILVER_PATH.exists():
        return []
    records = [json.loads(line) for line in SILVER_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [clean_record_text(r) for r in records]


@st.cache_data
def get_silver_by_slug() -> dict:
    return {r["slug"]: r for r in get_silver_records()}


def gold_match_report() -> dict[str, DescriptionMatch]:
    _index, match_report = get_discovery_index()
    return match_report


def build_deps() -> ChatDeps:
    """Wires this module's cached resources into a chat_engine.ChatDeps -- shared by both app.py
    and the browse-all-schemes page so neither has to import from the other (importing app.py as
    a module would re-run its own top-level st.set_page_config() call, which Streamlit rejects if
    a page already called its own)."""
    index, match_report = get_discovery_index()
    return ChatDeps(
        discovery_index=index,
        gold_match_report=match_report,
        silver_by_slug=get_silver_by_slug(),
        raw_docs_dir=RAW_DOCS_DIR,
        gold_dir=GOLD_DIR,
        language=i18n.current_language(),
    )


# --- "what to do next" -- benefits/application/link, from data already scraped ---------------


def _resolve_next_steps_for(scheme_id: str, source_type: str) -> NextSteps | None:
    if source_type == "gold":
        match = gold_match_report().get(scheme_id)
        if match is None:
            return None
        return resolve_next_steps(scheme_id, match, get_silver_by_slug(), RAW_DOCS_DIR)
    record = get_silver_by_slug().get(scheme_id)
    if record is None:
        return None
    return next_steps_for_silver(record)


def official_link_for(scheme_id: str, source_type: str) -> str | None:
    """Lightweight lookup for shortlist cards -- a candidate the citizen never selects should
    still leave them with a link, not nothing."""
    ns = _resolve_next_steps_for(scheme_id, source_type)
    return ns.official_link if ns else None


def render_next_steps_data(ns: NextSteps, is_gold_source_doc_fallback: bool = False) -> None:
    """The one 'What to do next' section, rendered directly from an already-resolved NextSteps --
    chat_engine.py resolves this once per verdict/scheme_detail message and embeds it, so
    rendering never needs to re-look-up data mid-chat-history-replay."""
    if not (ns.benefits_text or ns.application_process_text or ns.official_link):
        return
    st.markdown("### What to do next")
    if ns.benefits_text:
        st.markdown(f"**Benefits:** {ns.benefits_text}")
    if ns.application_process_text:
        st.markdown(f"**How to apply:** {ns.application_process_text}")
    if ns.official_link:
        st.markdown(f"[Official scheme page]({ns.official_link})")
    if is_gold_source_doc_fallback and ns.source == "source_doc":
        st.caption(
            "Sourced from the scheme's official notification document — no separate verified "
            "listing was found to cross-check against."
        )


def render_next_steps(scheme_id: str, source_type: str) -> None:
    """Convenience wrapper: resolves then renders. Prefer render_next_steps_data() with an
    already-resolved NextSteps when one is available (chat_engine.py embeds one on every
    verdict/scheme_detail message) -- this wrapper re-resolves live, for any caller that only has
    a scheme_id/source_type on hand."""
    ns = _resolve_next_steps_for(scheme_id, source_type)
    if ns is not None:
        render_next_steps_data(ns, is_gold_source_doc_fallback=(source_type == "gold"))
