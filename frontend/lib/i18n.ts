// Duplicated from schemelogic/conversational/i18n.py's _STRINGS dict -- kept byte-for-byte
// identical on purpose (same keys, same en/hi values) so the two frontends (this one and the
// Streamlit fallback) never visibly disagree. If you add/change a key, update BOTH files.
//
// Same three-tier scope as the Python version:
// 1. This file: static UI chrome only.
// 2. LLM-generated content (router/phrase_verdict/answer_parser): language is sent as part of
//    every /chat request body and threaded server-side into those system prompts -- see lib/api.ts.
// 3. chat_engine.py's own template strings and scraped scheme text: NOT translated, same as before.

import generated from "./ui_strings.generated.json";
import languageStatus from "./ui_language_status.generated.json";

// Multilingual stage 3 (2026-10-05): Urdu, Marathi and Tamil join English and Hindi. Their strings are
// machine translations generated from data/i18n/<lang>.json by scripts/export_ui_strings.py
// (reviewed or not -- see docs/i18n/REVIEW_<lang>.md); a key without one falls back to English.
export type Language = "en" | "hi" | "ur" | "mr" | "ta";

export const LANGUAGES: { code: Language; nativeName: string; dir: "ltr" | "rtl"; speech: string }[] = [
  { code: "en", nativeName: "English", dir: "ltr", speech: "en-IN" },
  { code: "hi", nativeName: "हिंदी", dir: "ltr", speech: "hi-IN" },
  { code: "ur", nativeName: "اردو", dir: "rtl", speech: "ur-IN" },
  { code: "mr", nativeName: "मराठी", dir: "ltr", speech: "mr-IN" },
  { code: "ta", nativeName: "தமிழ்", dir: "ltr", speech: "ta-IN" },
];

export function isLanguage(value: string | null): value is Language {
  return LANGUAGES.some((l) => l.code === value);
}

const GENERATED = generated as Record<string, Record<string, string>>;

type StringEntry = { en: string; hi: string };

export const STRINGS: Record<string, StringEntry> = {
  nav_browse: { en: "Browse All Schemes", hi: "सभी योजनाएं देखें" },
  nav_back_to_chat: { en: "Back to chat", hi: "चैट पर वापस जाएं" },
  lang_toggle_label: { en: "English/हिंदी", hi: "हिंदी/English" },
  hero_thesis: {
    en: "Real government scheme rules, checked the same way every time — no guessing, no ads, a clear reason for every answer.",
    hi: "असली सरकारी योजना नियम, हर बार एक ही तरीके से जांचे गए — कोई अंदाजा नहीं, कोई विज्ञापन नहीं, हर जवाब का एक स्पष्ट कारण।",
  },
  step_1: { en: "Ask, in your own words", hi: "अपने शब्दों में पूछें" },
  step_2: { en: "We check the real rules", hi: "हम असली नियम जांचते हैं" },
  step_3: { en: 'A verified answer, or an honest "not sure yet"', hi: 'एक सत्यापित जवाब, या ईमानदारी से "अभी पक्का नहीं"' },
  greeting: {
    en: "Namaste! 🙏 How can I help you find government schemes today? You can tell me a bit about yourself or ask about specific welfare programs.",
    hi: "नमस्ते! 🙏 आज मैं सरकारी योजनाएं खोजने में आपकी कैसे मदद कर सकता हूं? आप अपने बारे में थोड़ा बता सकते हैं या किसी खास योजना के बारे में पूछ सकते हैं।",
  },
  try_one_of_these: { en: "Or try one of these:", hi: "या इनमें से एक आज़माएं:" },
  browse_hint: {
    en: "Looking for something specific? Use **Browse all schemes** above to look through the full list directly.",
    hi: "कुछ खास ढूंढ रहे हैं? पूरी सूची देखने के लिए ऊपर **सभी योजनाएं देखें** का उपयोग करें।",
  },
  chat_input_placeholder: { en: "Message SchemeLogic...", hi: "SchemeLogic को संदेश भेजें..." },
  disclaimer: {
    en: "SchemeLogic can make mistakes. Consider verifying important scheme details on official government portals.",
    hi: "SchemeLogic गलतियां कर सकता है। महत्वपूर्ण योजना विवरण आधिकारिक सरकारी पोर्टल पर सत्यापित करें।",
  },
  start_over: { en: "Start over", hi: "फिर से शुरू करें" },
  browse_title: { en: "All Schemes", hi: "सभी योजनाएं" },
  browse_subtitle: {
    en: "Discover and apply for government welfare schemes tailored to your needs. Browse all available programs below.",
    hi: "अपनी जरूरतों के अनुसार सरकारी कल्याण योजनाएं खोजें और आवेदन करें। नीचे सभी उपलब्ध कार्यक्रम देखें।",
  },
  search_placeholder: { en: "Search schemes by name or keyword...", hi: "योजना का नाम या कीवर्ड खोजें..." },
  view_details: { en: "View Details", hi: "विवरण देखें" },
  select: { en: "Select", hi: "चुनें" },
  ask_ai_sahayak: { en: "Ask AI Sahayak", hi: "AI सहायक से पूछें" },
  seal_verified: { en: "Verified", hi: "सत्यापित" },
  seal_ai_checked: { en: "AI-Checked", hi: "एआई-जांचित" },
  seal_unverified: { en: "Unverified", hi: "असत्यापित" },
  // Mirrors schemelogic/conversational/i18n.py's key of the same name -- shown on every
  // AI-Checked verdict. The Q&A and evaluator are identical to a Verified scheme's, so the seal
  // badge alone is too quiet at the moment a verdict is read. Honest-labelling requirement; do
  // not drop or soften.
  ai_checked_verdict_disclaimer: {
    en: "These rules were extracted automatically by AI from this scheme's published text and have NOT been checked by a human reviewer. The verdict above was computed by the same deterministic rules engine used for Verified schemes, but the rules it applied may be incomplete or wrong — confirm with the official source before acting on this.",
    hi: "ये नियम इस योजना के प्रकाशित पाठ से AI द्वारा स्वचालित रूप से निकाले गए हैं और किसी व्यक्ति द्वारा जांचे नहीं गए हैं। ऊपर का निर्णय उसी नियम-इंजन से निकला है जो सत्यापित योजनाओं के लिए उपयोग होता है, लेकिन जिन नियमों पर वह लागू हुआ वे अधूरे या गलत हो सकते हैं — इस पर कार्य करने से पहले आधिकारिक स्रोत से पुष्टि करें।",
  },
  category_all: { en: "All Schemes", hi: "सभी योजनाएं" },
  category_farmers: { en: "Farmers", hi: "किसान" },
  category_students: { en: "Students", hi: "छात्र" },
  category_women: { en: "Women", hi: "महिलाएं" },
  category_health: { en: "Health", hi: "स्वास्थ्य" },
  category_housing: { en: "Housing", hi: "आवास" },
  schemes_shown_suffix: { en: "shown", hi: "दिखाए गए" },
  // Shown under the nav bar for any language not yet fully reviewed by a person (2026-10-05).
  translation_notice_machine: {
    en: "Machine-translated and not yet reviewed by a person. If anything is unclear, the English version is the authoritative one.",
    hi: "यह अनुवाद मशीन से किया गया है और अभी किसी व्यक्ति ने इसकी समीक्षा नहीं की है। कुछ भी अस्पष्ट हो तो अंग्रेज़ी संस्करण ही मान्य है।",
  },
  translation_notice_none: {
    en: "This language is not translated yet, so most text is shown in English. Any text in this language is machine-generated and not reviewed.",
    hi: "यह भाषा अभी अनूदित नहीं है, इसलिए ज़्यादातर पाठ अंग्रेज़ी में दिखाया गया है। इस भाषा का कोई भी पाठ मशीन से बना है और उसकी समीक्षा नहीं हुई है।",
  },
};

// Each language's review state, from data/i18n/<lang>.json (scripts/export_ui_strings.py). Anything but
// "reviewed" -- every catalogue entry confirmed by a person -- is marked in the interface.
export type TranslationState = "reviewed" | "machine" | "none";
const STATUS = languageStatus as Record<string, { state: TranslationState }>;

export function translationState(language: Language): TranslationState {
  if (language === "en") return "reviewed";
  return STATUS[language]?.state ?? "none";
}

export function translate(key: string, language: Language): string {
  const entry = STRINGS[key];
  if (!entry) return key;
  if (language === "en") return entry.en || key;
  // Hindi: a reviewer's correction (exported from data/i18n/hi.json) wins over the hand-written text.
  if (language === "hi") return GENERATED.hi?.[key] || entry.hi || entry.en || key;
  return GENERATED[language]?.[key] || entry.en || key;
}
