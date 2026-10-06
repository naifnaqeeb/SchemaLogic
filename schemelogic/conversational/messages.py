"""Every fixed string the citizen sees, under a stable key, in English and in translation (multilingual
stage 2, 2026-10-05). No LLM at run time: translations are made once (scripts/translate_catalogue.py),
stored as files, and reviewed by a person.

- `MESSAGES`: chat replies, verdict templates, explanation labels, quick replies. The English text is
  exactly what the code said before this module existed -- English output is unchanged by construction.
- `catalogue()`: MESSAGES plus every live ontology field's question (applicant form, family-member form,
  household form) and display label, generated from the ontology so they can't drift from it.
- `text(key, language, **fields)`: the translation when one exists, is current, and has the same
  {placeholders} as the English; otherwise the English. A missing or stale translation never breaks a
  reply -- it falls back.
- Translation files: data/i18n/<lang>.json -> {key: {"source": English, "text": translation,
  "status": "unreviewed" | "reviewed", ...}}. A translation whose English source has since changed is
  stale and not used. "unreviewed" ones ARE used (that's what review sheets are for) but are labelled as
  such in docs/i18n/REVIEW_<lang>.md until a person marks them reviewed.
- Domain terms (BPL, APL, SC/ST, OBC, Group D, MTS, Class IV, Aadhaar, kutcha, pucca, NRI, e-Shram,
  MGNREGA, scheme names) keep their exact form in every language -- GLOSSARY, enforced by the translator.
"""

from __future__ import annotations

import json
import re
import string
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
I18N_DIR = ROOT / "data" / "i18n"
LANGUAGES = ("hi", "ur", "mr", "ta")  # English is the source

GLOSSARY = ("BPL", "APL", "SC/ST", "SC", "ST", "OBC", "Group D", "Class IV", "MTS", "Aadhaar", "kutcha", "pucca",
            "NRI", "e-Shram", "MGNREGA", "NFSA", "AAY", "PM-KISAN", "AB-PMJAY", "PMAY-G", "PMMVY", "IGNOAPS",
            "SECC", "RSBY", "Kisan Credit Card", "HIV", "AIDS")

# Glossary terms that are ordinary words in a language, so a translation into it may use the native
# word (2026-10-06: Hindi and Marathi पक्का / कच्चा, Urdu پکا / کچا; Tamil keeps the English terms).
# Every other glossary term still stays exactly as written.
NATIVE_TERMS: dict[str, dict[str, str]] = {
    "hi": {"pucca": "पक्का", "kutcha": "कच्चा"},
    "mr": {"pucca": "पक्का", "kutcha": "कच्चा"},
    "ur": {"pucca": "پکا", "kutcha": "کچا"},
}


def glossary_for(language: str | None) -> tuple[str, ...]:
    """The glossary terms a translation into `language` must keep unchanged."""
    native = NATIVE_TERMS.get(language or "", {})
    return tuple(t for t in GLOSSARY if t not in native)


MESSAGES: dict[str, str] = {
    # --- chat replies (chat_engine) ---
    "chat.greeting": "Hey! Tell me a bit about your situation or what kind of help you're looking for, and I'll check real scheme rules for you.",
    "chat.greeting_pending": "No rush! Whenever you're ready: {question}",
    "chat.which_scheme": "Which scheme did you mean? Search for one first, or pick one from Browse all schemes.",
    "chat.finish_first": "Let's finish checking {scheme_id} first — {question}",
    "chat.already_checked": "I already checked {scheme_id} for you above — scroll up to see the result, or search again to check a different scheme.",
    "chat.scheme_gone": "Sorry, I couldn't find that scheme anymore.",
    "chat.nothing_matched": "Nothing matched closely. Try describing it differently, or a different situation.",
    "chat.found": "Here's what I found",
    "chat.found_followup": "Want more detail on any of these, or should I check your eligibility for one? Just tell me, or click Select.",
    "chat.checking_rules": "Checking the rules for this scheme now...",
    "chat.ai_checked_ok": ("I ran automatic rule extraction on **{scheme_name}** and it validated, so I can check your "
                           "eligibility the same way as a verified scheme — just know this is AI-Checked (rules extracted "
                           "automatically), not human-verified."),
    "chat.extraction_unreachable": ("I couldn't reach the rule-extraction service just now, so I haven't checked "
                                    "**{scheme_name}**'s rules yet — here's the description as listed meanwhile. Selecting "
                                    "it again in a moment will retry the check."),
    "chat.extraction_already_failed": ("I already tried automatic rule extraction for **{scheme_name}** earlier this session "
                                       "and it didn't produce reliable eligibility rules, so I won't retry — here's the "
                                       "description as listed."),
    "chat.extraction_failed": ("I wasn't able to reliably extract eligibility rules for this scheme automatically — "
                               "here's the description as listed."),
    "chat.lets_check": "Let's check your eligibility for {scheme_id}.",
    "chat.intake_used": "Starting from what you already told me — I'll only ask about what's still missing. (via {provider})",
    "chat.evaluation_failed": ("I couldn't work out a result for {scheme_id}: one of the answers I have isn't in a form the "
                               "scheme's rules can use (for example, words where a number was needed), and I won't guess. "
                               "This is not a decision about your eligibility. You can start the check again, or ask at "
                               "your local office."),
    "chat.quick_reply_error": "Sorry, something went wrong reading that reply — please try again.",
    "chat.sensitive_reask": "You can answer Yes, No, or “Prefer not to say” — whichever you are comfortable with.",
    "chat.declined": ("That's completely fine — you don't need to tell me. You may qualify for {scheme_id} under a special "
                      "provision. Please check with your local office (for example your Gram Panchayat, Block office or "
                      "social welfare office); they can look at it with you in confidence."),
    "chat.rephrase": "I couldn't quite understand that — could you rephrase? ",
    "chat.rephrase_buttons": "You can also use the Yes/No buttons above.",
    "chat.still_unparsed": "Sorry, I still couldn't quite parse that — could you try rephrasing?",
    "chat.switching_away": "(Switching away from {scheme_id} for now — search for it again anytime to restart that check.)",
    "chat.machine_translated": "Machine-translated from English — the original is authoritative.",
    # --- quick replies ---
    "reply.yes": "Yes",
    "reply.no": "No",
    "reply.decline": "Prefer not to say",
    # --- questions ---
    "question.family_prefix": "This next one is about one of your family members — {question}",
    "question.generic_boolean": 'Do you meet this criterion: "{label}"?',
    "question.generic_value": 'What is your value for "{label}"?',
    "question.household_generic_boolean": 'Does any one of {members} meet this: "{label}"?',
    "question.household_generic_value": 'What is the highest "{label}" of any one of {members}?',
    # --- verdicts (phrasing) ---
    "verdict.headline_eligible": "{emoji} You're eligible for {scheme_id}",
    "verdict.headline_ineligible": "{emoji} You're not eligible for {scheme_id}",
    "verdict.headline_undetermined": "{emoji} One more detail needed for {scheme_id}",
    "verdict.answer_eligible": "Based on what you've told me, you're eligible for {scheme_id} — here's why:",
    "verdict.answer_ineligible": "Based on what you've told me, you're not eligible for {scheme_id} — here's why:",
    "verdict.answer_undetermined": "I need one more detail to be sure about your eligibility for {scheme_id} — let's continue.",
    # --- explanation (rendering) ---
    "trace.header": "What we checked to reach this result:",
    "trace.disqualify_header": "Things that would disqualify you:",
    "trace.yes": "Yes ✅",
    "trace.no": "No ❌",
    "trace.unknown": "Not yet known ❓",
    "trace.all_of": "All of these need to be true",
    "trace.one_of": "At least one of these needs to be true",
    "trace.applies": "Applies to you 🚫",
    "trace.waived": "True for you, but waived by an exception ✅",
    "trace.does_not_apply": "Doesn't apply ✅",
}

_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


def placeholders(s: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(s) if name}


def catalogue() -> dict[str, str]:
    """MESSAGES plus the live ontology's questions and labels (applicant, family-member and household
    forms), generated so they can't drift from the ontology."""
    from schemelogic.conversational.question_selector import _second_to_third_person
    from schemelogic.schema.field_ontology import _DEFAULT_SCOPE, _FIELDS, FAMILY_SCOPE

    out = dict(MESSAGES)
    out.update({f"ui.{k}": v for k, v in ui_strings_english().items()})
    out["family_scope.default"] = _DEFAULT_SCOPE
    out.update({f"family_scope.{sid}": scope for sid, scope in FAMILY_SCOPE.items()})
    for spec in _FIELDS:
        if not spec.schemes:
            continue  # retired: never asked
        out[f"field.{spec.name}"] = spec.citizen_question
        out[f"field_member.{spec.name}"] = _second_to_third_person(spec.citizen_question)
        out[f"label.{spec.name}"] = spec.display_label
        if spec.household_question:
            out[f"field_household.{spec.name}"] = spec.household_question
    for spec in _FIELDS:  # screening facts (is_widow) are asked though they list no scheme
        if spec.name not in {k.split(".", 1)[1] for k in out if k.startswith("field.")} and any(
                f.screened_by == spec.name for f in _FIELDS):
            out[f"field.{spec.name}"] = spec.citizen_question
            out[f"label.{spec.name}"] = spec.display_label
    return out


@lru_cache(maxsize=None)
def ui_strings_english() -> dict[str, str]:
    """The UI chrome strings (conversational/i18n.py's _STRINGS, which frontend/lib/i18n.ts copies
    byte-for-byte), read by parsing the source -- that module imports Streamlit, which nothing here needs."""
    return _ui_strings("en")


def ui_strings_hindi() -> dict[str, str]:
    """The hand-written Hindi UI chrome strings that ship in the app (same source as above)."""
    return _ui_strings("hi")


def _ui_strings(language: str) -> dict[str, str]:
    import ast

    source = (ROOT / "schemelogic" / "conversational" / "i18n.py").read_text(encoding="utf-8")
    for node in ast.parse(source).body:
        target = node.target if isinstance(node, ast.AnnAssign) else (node.targets[0] if isinstance(node, ast.Assign) else None)
        if isinstance(target, ast.Name) and target.id == "_STRINGS":
            return {k: v[language] for k, v in ast.literal_eval(node.value).items() if v.get(language)}
    return {}


@lru_cache(maxsize=None)
def _translations(language: str) -> dict[str, dict]:
    path = I18N_DIR / f"{language}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def reload_translations() -> None:
    _translations.cache_clear()


def translated(key: str, language: str, source: str) -> str | None:
    """The stored translation of `source` under `key`, if it exists, is current and keeps the
    placeholders; otherwise None."""
    if language == "en":
        return None
    entry = _translations(language).get(key)
    if not entry or entry.get("source") != source or not entry.get("text"):
        return None
    if placeholders(entry["text"]) != placeholders(source):
        return None
    return entry["text"]


def review_status(language: str) -> dict:
    """How much of the catalogue a person has reviewed in `language`: "reviewed" only when every entry
    is current and reviewed; "machine" when some text is machine-translated and not all reviewed;
    "none" when nothing is translated yet (the interface shows English)."""
    entries = _translations(language)
    current = {k: e for k, e in entries.items() if isinstance(e, dict) and translated(k, language, e.get("source") or "")}
    total = len(catalogue())
    reviewed = sum(1 for e in current.values() if e.get("status") == "reviewed")
    state = "reviewed" if total and reviewed == total else ("machine" if current else "none")
    return {"state": state, "translated": len(current), "reviewed": reviewed, "total": total}


def text(key: str, language: str = "en", **fields: object) -> str:
    """The string for `key` in `language`, formatted with `fields`. English for "en", and whenever no
    usable translation exists."""
    source = MESSAGES.get(key)
    if source is None:
        source = catalogue()[key]
    template = translated(key, language, source) or source
    return template.format(**fields) if fields else template


def field_text(kind: str, field: str, english: str, language: str, **fields: object) -> str:
    """A field question/label: `english` is what the caller would show in English (already resolved,
    including generated AI-Checked phrasings, which have no catalogue entry and stay English)."""
    template = translated(f"{kind}.{field}", language, english) if language != "en" else None
    template = template or english
    return template.format(**fields) if fields else template


def all_quick_replies(key: str) -> set[str]:
    """The quick-reply text for `key` in every language (a translated button sends its own text)."""
    replies = {MESSAGES[key]}
    for language in LANGUAGES:
        t = translated(key, language, MESSAGES[key])
        if t:
            replies.add(t)
    return replies
