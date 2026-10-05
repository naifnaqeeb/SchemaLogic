"""Scheme descriptions in the citizen's language, translated on demand (multilingual stage 2).

A silver (myScheme) scheme the system couldn't check is shown as listed: its description, eligibility
text, benefits and application steps. For a citizen writing in Hindi, Urdu, Marathi or Tamil those are
translated once per scheme and language with ONE LLM call, cached on disk, and always shown with a
"machine-translated" label -- the English original stays authoritative and is kept on the message.

WHAT THIS CALL MAY PRODUCE: a translation of the given text. It never sees a citizen's answers and
never decides anything; the verdict path doesn't touch it. A failed or malformed translation costs
only the English original (shown as before) and is never cached.
"""

from __future__ import annotations

import json
from pathlib import Path

from schemelogic.conversational.language import LANGUAGE_NAMES
from schemelogic.conversational.messages import GLOSSARY
from schemelogic.llm.provider import ProviderFailure, chat_completion_with_fallback

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "translations"
FIELDS = ("description", "eligibility_text", "benefits_text", "application_process_text")
_MAX_FIELD_CHARS = 2500  # a scraped field can be long; beyond this, keep the request bounded


def _system_prompt(language: str) -> str:
    return (
        f"Translate the given Indian government welfare scheme text from English into {LANGUAGE_NAMES[language]}, "
        "faithfully and plainly, for a citizen to read. Do not add, remove, soften or summarise anything; "
        "translate amounts, ages and dates exactly. Keep these terms exactly as written, untranslated: "
        f"{', '.join(GLOSSARY)}, and every scheme or programme name. Return ONLY a JSON object with the same "
        "keys as the input, each value the translation of that field."
    )


def _cache_path(slug: str, language: str) -> Path:
    return CACHE_DIR / f"{slug}.{language}.json"


def translate_record(slug: str, record: dict, language: str) -> dict | None:
    """{field: translation} for the record's non-empty text fields, or None (keep the English).
    Never raises."""
    if language not in LANGUAGE_NAMES or language == "en":
        return None
    path = _cache_path(slug, language)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    source = {f: str(record[f])[:_MAX_FIELD_CHARS] for f in FIELDS if record.get(f)}
    if not source:
        return None
    try:
        response = chat_completion_with_fallback(
            [{"role": "system", "content": _system_prompt(language)},
             {"role": "user", "content": json.dumps(source, ensure_ascii=False)}],
            response_format={"type": "json_object"}, temperature=0.0, max_tokens=4000,
        )
    except Exception:  # noqa: BLE001 -- on the live chat path: any failure keeps the English
        return None
    if isinstance(response, ProviderFailure):
        return None
    try:
        translated = json.loads(response.content)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(translated, dict) or set(translated) != set(source) or not all(
            isinstance(v, str) and v.strip() for v in translated.values()):
        return None  # incomplete or malformed: show the English rather than a partial translation
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(translated, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    return translated
