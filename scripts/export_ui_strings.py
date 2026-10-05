"""Export the translated UI chrome strings for the frontend -- multilingual stage 3. Offline.

    PYTHONPATH=. python scripts/export_ui_strings.py

Writes frontend/lib/ui_strings.generated.json: {language: {key: text}} for Urdu, Marathi and Tamil,
from the "ui.*" entries of data/i18n/<lang>.json -- only translations that are current (their English
source unchanged) and keep their placeholders; anything else is left out and the frontend shows English.
English and Hindi stay in frontend/lib/i18n.ts as before. Regenerate after translating or reviewing.

Also writes frontend/lib/ui_language_status.generated.json: each language's review state (messages.
review_status), so the interface marks a language as machine-translated and unreviewed until the team
has reviewed all of it (2026-10-05).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from schemelogic.conversational import messages  # noqa: E402

OUT = ROOT / "frontend" / "lib" / "ui_strings.generated.json"
STATUS_OUT = ROOT / "frontend" / "lib" / "ui_language_status.generated.json"
LANGUAGES = ("hi", "ur", "mr", "ta")  # hi: only where a reviewer's correction differs from i18n.ts


def build() -> dict[str, dict[str, str]]:
    english, hindi = messages.ui_strings_english(), messages.ui_strings_hindi()
    out: dict[str, dict[str, str]] = {}
    for language in LANGUAGES:
        strings = {}
        for key, source in english.items():
            t = messages.translated(f"ui.{key}", language, source)
            if t and (language != "hi" or t != hindi.get(key)):
                strings[key] = t
        out[language] = strings
    return out


def status() -> dict[str, dict]:
    return {language: messages.review_status(language) for language in messages.LANGUAGES}


def main() -> None:
    messages.reload_translations()
    data, states = build(), status()
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    STATUS_OUT.write_text(json.dumps(states, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"written: {OUT.relative_to(ROOT)} ({', '.join(f'{k}: {len(v)}' for k, v in data.items())}); "
          f"{STATUS_OUT.relative_to(ROOT)} ("
          + ", ".join(f"{k}: {v['state']}, {v['reviewed']}/{v['total']} reviewed" for k, v in states.items()) + ")")


if __name__ == "__main__":
    main()
