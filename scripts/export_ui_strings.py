"""Export the translated UI chrome strings for the frontend -- multilingual stage 3. Offline.

    PYTHONPATH=. python scripts/export_ui_strings.py

Writes frontend/lib/ui_strings.generated.json: {language: {key: text}} for Urdu, Marathi and Tamil,
from the "ui.*" entries of data/i18n/<lang>.json -- only translations that are current (their English
source unchanged) and keep their placeholders; anything else is left out and the frontend shows English.
English and Hindi stay in frontend/lib/i18n.ts as before. Regenerate after translating or reviewing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from schemelogic.conversational import messages  # noqa: E402

OUT = ROOT / "frontend" / "lib" / "ui_strings.generated.json"
LANGUAGES = ("ur", "mr", "ta")


def build() -> dict[str, dict[str, str]]:
    english = messages.ui_strings_english()
    out: dict[str, dict[str, str]] = {}
    for language in LANGUAGES:
        strings = {}
        for key, source in english.items():
            t = messages.translated(f"ui.{key}", language, source)
            if t:
                strings[key] = t
        out[language] = strings
    return out


if __name__ == "__main__":
    data = build()
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(f"written: {OUT.relative_to(ROOT)} ({', '.join(f'{k}: {len(v)}' for k, v in data.items())})")
