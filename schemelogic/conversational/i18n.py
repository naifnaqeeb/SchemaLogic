"""Language toggle (English/Hindi), scoped realistically to what's actually translatable tonight.

Three separate tiers, deliberately NOT conflated:
1. Static UI chrome (this module) -- headers, button labels, nav, disclaimer, category pill
   names, seal-tier labels. A plain lookup dict, swapped by st.session_state["language"].
2. LLM-generated content (router responses, phrased verdicts, extracted-question phrasing) --
   NOT handled here. Those call sites pass a `language` parameter through to the existing
   provider abstraction, which adds a system-prompt instruction to respond in Hindi -- see
   router.py/phrasing.py/answer_parser.py's own `language` parameters.
3. chat_engine.py's own template strings ("Checking the rules for this scheme now...", "Which
   one did you mean?", etc.) -- explicitly OUT OF SCOPE tonight. chat_engine.py is deliberately
   Streamlit-agnostic and business-logic-only (see its own module docstring); threading a
   presentation-layer language toggle through its entire call graph is not a presentation-only
   change. These stay English regardless of toggle state -- flagged here rather than silently
   half-translating.
4. Scraped/silver scheme description text (benefits_text, eligibility_text, ...) -- explicitly
   OUT OF SCOPE, stays in its original (scraped) language regardless of toggle, per explicit
   instruction not to produce partial/inconsistent translations of source data.
"""

from __future__ import annotations

import streamlit as st

Language = str  # "en" | "hi"

_STRINGS: dict[str, dict[Language, str]] = {
    "nav_browse": {"en": "Browse All Schemes", "hi": "सभी योजनाएं देखें"},
    "nav_back_to_chat": {"en": "Back to chat", "hi": "चैट पर वापस जाएं"},
    "lang_toggle_label": {"en": "English/हिंदी", "hi": "हिंदी/English"},
    "hero_thesis": {
        "en": "Real government scheme rules, checked the same way every time — no guessing, no ads, a clear reason for every answer.",
        "hi": "असली सरकारी योजना नियम, हर बार एक ही तरीके से जांचे गए — कोई अंदाजा नहीं, कोई विज्ञापन नहीं, हर जवाब का एक स्पष्ट कारण।",
    },
    "step_1": {"en": "Ask, in your own words", "hi": "अपने शब्दों में पूछें"},
    "step_2": {"en": "We check the real rules", "hi": "हम असली नियम जांचते हैं"},
    "step_3": {"en": 'A verified answer, or an honest "not sure yet"', "hi": "एक सत्यापित जवाब, या ईमानदारी से \"अभी पक्का नहीं\""},
    "greeting": {
        "en": "Namaste! 🙏 How can I help you find government schemes today? You can tell me a bit about yourself or ask about specific welfare programs.",
        "hi": "नमस्ते! 🙏 आज मैं सरकारी योजनाएं खोजने में आपकी कैसे मदद कर सकता हूं? आप अपने बारे में थोड़ा बता सकते हैं या किसी खास योजना के बारे में पूछ सकते हैं।",
    },
    "try_one_of_these": {"en": "Or try one of these:", "hi": "या इनमें से एक आज़माएं:"},
    "browse_hint": {
        "en": "Looking for something specific? Use **Browse all schemes** above to look through the full list directly.",
        "hi": "कुछ खास ढूंढ रहे हैं? पूरी सूची देखने के लिए ऊपर **सभी योजनाएं देखें** का उपयोग करें।",
    },
    "chat_input_placeholder": {"en": "Message SchemeLogic...", "hi": "SchemeLogic को संदेश भेजें..."},
    "disclaimer": {
        "en": "SchemeLogic can make mistakes. Consider verifying important scheme details on official government portals.",
        "hi": "SchemeLogic गलतियां कर सकता है। महत्वपूर्ण योजना विवरण आधिकारिक सरकारी पोर्टल पर सत्यापित करें।",
    },
    "start_over": {"en": "Start over", "hi": "फिर से शुरू करें"},
    "browse_title": {"en": "All Schemes", "hi": "सभी योजनाएं"},
    "browse_subtitle": {
        "en": "Discover and apply for government welfare schemes tailored to your needs. Browse all available programs below.",
        "hi": "अपनी जरूरतों के अनुसार सरकारी कल्याण योजनाएं खोजें और आवेदन करें। नीचे सभी उपलब्ध कार्यक्रम देखें।",
    },
    "search_placeholder": {"en": "Search schemes by name or keyword...", "hi": "योजना का नाम या कीवर्ड खोजें..."},
    "view_details": {"en": "View Details", "hi": "विवरण देखें"},
    "select": {"en": "Select", "hi": "चुनें"},
    "ask_ai_sahayak": {"en": "Ask AI Sahayak", "hi": "AI सहायक से पूछें"},
    "seal_verified": {"en": "Verified", "hi": "सत्यापित"},
    "seal_ai_checked": {"en": "AI-Checked", "hi": "एआई-जांचित"},
    "seal_unverified": {"en": "Unverified", "hi": "असत्यापित"},
    "category_all": {"en": "All Schemes", "hi": "सभी योजनाएं"},
    "category_farmers": {"en": "Farmers", "hi": "किसान"},
    "category_students": {"en": "Students", "hi": "छात्र"},
    "category_women": {"en": "Women", "hi": "महिलाएं"},
    "category_health": {"en": "Health", "hi": "स्वास्थ्य"},
    "category_housing": {"en": "Housing", "hi": "आवास"},
    "schemes_shown_suffix": {"en": "shown", "hi": "दिखाए गए"},
}


def current_language() -> Language:
    return st.session_state.get("language", "en")


def toggle_language() -> None:
    st.session_state["language"] = "hi" if current_language() == "en" else "en"


def t(key: str) -> str:
    """Looks up `key` in the current language, falling back to English, then to the key itself
    -- never raises on a typo'd/missing key, just degrades to something visible."""
    entry = _STRINGS.get(key)
    if entry is None:
        return key
    return entry.get(current_language()) or entry.get("en") or key
