"""Translate the message catalogue into Hindi, Urdu, Marathi and Tamil -- multilingual stage 2.

LIVE (Groq only, no fallback): batches of the catalogue per language; paced and budgeted by the
experiment ledger; resumable (entries already translated from the current English are skipped).

    PYTHONPATH=. python scripts/translate_catalogue.py [hi ur mr ta] [--budget=175000]
    PYTHONPATH=. python scripts/translate_catalogue.py --sheets                  # regenerate review sheets only
    PYTHONPATH=. python scripts/translate_catalogue.py --mark-reviewed hi all    # or: hi key1 key2 ...

Every entry is validated before it is stored: the same {placeholders}, every glossary term in the
English (BPL, SC/ST, Group D, ...) present unchanged, markdown bold kept, non-empty. An invalid entry is
retried once on its own, then left untranslated -- the app falls back to English for it -- and listed in
the review sheet. Stored entries are "unreviewed" until a person marks them reviewed; review sheets in
docs/i18n/REVIEW_<lang>.md put the English beside each translation.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from schemelogic.conversational import messages  # noqa: E402
from schemelogic.conversational.language import LANGUAGE_NAMES  # noqa: E402
from schemelogic.experiments import harness  # noqa: E402
from schemelogic.llm.provider import GROQ, ProviderFailure, chat_completion_with_fallback  # noqa: E402

ITEM = "translations"
BATCH = 40
ESTIMATE = 4_500
SHEETS = ROOT / "docs" / "i18n"


def system_prompt(language: str) -> str:
    return (
        f"You translate the user-interface strings of an Indian government welfare-scheme eligibility assistant "
        f"from English into {LANGUAGE_NAMES[language]}, for ordinary citizens: plain, polite, natural. The input "
        "is a JSON object {key: English}. Return ONLY a JSON object with exactly the same keys, each value the "
        "translation.\n\nRules:\n"
        "- Keep every {placeholder} in braces exactly as written (e.g. {scheme_id}, {question}, {members}).\n"
        f"- Keep these terms exactly as written, untranslated: {', '.join(messages.GLOSSARY)}.\n"
        "- Keep markdown (**bold**), emoji and quotation marks.\n"
        "- Questions stay questions; keep the meaning exact -- amounts, ages and conditions must not change.\n"
        '- Strings starting "This next one is about one of your family members" refer to the family member in '
        "the third person; keep that."
    )


def valid(source: str, translation: object) -> bool:
    if not isinstance(translation, str) or not translation.strip():
        return False
    if messages.placeholders(translation) != messages.placeholders(source):
        return False
    if source.count("**") != translation.count("**"):
        return False
    return all(term in translation for term in messages.GLOSSARY if term in source and len(term) > 2)


def _call(language: str, batch: dict[str, str], ledger: harness.Ledger) -> dict | str:
    ledger.before_call(ESTIMATE)
    response = chat_completion_with_fallback(
        [{"role": "system", "content": system_prompt(language)},
         {"role": "user", "content": json.dumps(batch, ensure_ascii=False)}],
        primary=GROQ, secondary=None, response_format={"type": "json_object"},
        temperature=0.0, max_tokens=6000, reasoning_effort="low",
    )
    if isinstance(response, ProviderFailure):
        return response.primary_error
    usage = response.usage
    ledger.record({"call": f"translate_{language}", "prompt_tokens": getattr(usage, "prompt_tokens", None),
                   "completion_tokens": getattr(usage, "completion_tokens", None),
                   "total_tokens": getattr(usage, "total_tokens", None)})
    try:
        out = json.loads(response.content)
        return out if isinstance(out, dict) else "not a JSON object"
    except json.JSONDecodeError as exc:
        return f"malformed JSON: {exc}"


def _load(language: str) -> dict:
    path = messages.I18N_DIR / f"{language}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _save(language: str, data: dict) -> None:
    messages.I18N_DIR.mkdir(parents=True, exist_ok=True)
    (messages.I18N_DIR / f"{language}.json").write_text(
        json.dumps(dict(sorted(data.items())), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def translate(language: str, budget: int) -> str:
    ledger = harness.Ledger(ITEM, "groq", daily_budget=budget)
    catalogue = messages.catalogue()
    data = _load(language)
    todo = {k: v for k, v in catalogue.items() if data.get(k, {}).get("source") != v or not data.get(k, {}).get("text")}
    keys = list(todo)
    for start in range(0, len(keys), BATCH):
        batch = {k: todo[k] for k in keys[start: start + BATCH]}
        try:
            result = _call(language, batch, ledger)
        except harness.BudgetExhausted as exc:
            print(f"[stop] {exc}", flush=True)
            return "budget"
        if isinstance(result, str):
            if harness.is_daily_cap(result) or "rate limit" in result.lower():
                print(f"[stop] {language}: {result[:600]}", flush=True)
                return "daily_cap" if harness.is_daily_cap(result) else "rate_limited"
            result = {}
        retry = {k: v for k, v in batch.items() if not valid(v, result.get(k))}
        for k in retry:  # one more try each, alone
            try:
                single = _call(language, {k: batch[k]}, ledger)
            except harness.BudgetExhausted as exc:
                print(f"[stop] {exc}", flush=True)
                _save(language, data)
                return "budget"
            if isinstance(single, dict):
                result[k] = single.get(k)
        for k, source in batch.items():
            ok = valid(source, result.get(k))
            data[k] = {"source": source, "text": result.get(k) if ok else None,
                       "status": "unreviewed" if ok else "failed_validation",
                       "translated_on": date.today().isoformat(), "model": harness.MODEL, "provider": "groq",
                       "gold_tag": harness.GOLD_TAG}
        _save(language, data)
        print(f"  {language}: {min(start + BATCH, len(keys))}/{len(keys)} "
              f"({sum(1 for k in batch if data[k]['text'])} valid in this batch)", flush=True)
    return "done"


def write_sheet(language: str) -> None:
    data = _load(language)
    catalogue = messages.catalogue()
    counts = {s: sum(1 for k in catalogue if data.get(k, {}).get("status") == s) for s in ("reviewed", "unreviewed", "failed_validation")}
    missing = sum(1 for k in catalogue if k not in data or data[k].get("source") != catalogue[k])
    lines = [f"# Review sheet — {LANGUAGE_NAMES[language]} ({language})", "",
             "*Generated by `scripts/translate_catalogue.py --sheets`. Machine translation, **unreviewed until a person "
             "confirms it**: mark entries with `--mark-reviewed " + language + " <key ...>` (or `all`). The app uses "
             "unreviewed translations; a missing, stale or failed one falls back to English.*", "",
             f"Reviewed {counts['reviewed']} · unreviewed {counts['unreviewed']} · failed validation "
             f"{counts['failed_validation']} · not yet translated / stale {missing} · of {len(catalogue)}", "",
             "| Key | English | Translation | Status |", "|---|---|---|---|"]
    for key, source in catalogue.items():
        entry = data.get(key, {})
        status = entry.get("status", "missing") if entry.get("source") == source else ("stale" if entry else "missing")
        cell = lambda s: (s or "").replace("|", "\\|").replace("\n", " ")  # noqa: E731
        lines.append(f"| `{key}` | {cell(source)} | {cell(entry.get('text'))} | {status} |")
    SHEETS.mkdir(parents=True, exist_ok=True)
    (SHEETS / f"REVIEW_{language}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def mark_reviewed(language: str, keys: list[str]) -> None:
    data = _load(language)
    targets = [k for k in data if data[k].get("text")] if keys == ["all"] else keys
    for k in targets:
        if data.get(k, {}).get("text"):
            data[k]["status"] = "reviewed"
            data[k]["reviewed_on"] = date.today().isoformat()
    _save(language, data)
    write_sheet(language)


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--mark-reviewed" in args:
        i = args.index("--mark-reviewed")
        mark_reviewed(args[i + 1], args[i + 2:])
        sys.exit(0)
    languages = [a for a in args if not a.startswith("-")] or list(messages.LANGUAGES)
    if "--sheets" not in args:
        budget = int(next((a.split("=", 1)[1] for a in args if a.startswith("--budget=")), harness.DAILY_BUDGET))
        for lang in languages:
            reason = translate(lang, budget)
            print(f"{lang}: {reason}", flush=True)
            if reason != "done":
                break
    for lang in languages:
        write_sheet(lang)
    print("review sheets written:", ", ".join(f"docs/i18n/REVIEW_{lang}.md" for lang in languages))
