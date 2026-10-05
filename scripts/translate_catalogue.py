"""Translate the message catalogue into Hindi, Urdu, Marathi and Tamil -- multilingual stage 2.

LIVE (Groq only, no fallback): batches of the catalogue per language; paced and budgeted by the
experiment ledger; resumable (entries already translated from the current English are skipped).

    PYTHONPATH=. python scripts/translate_catalogue.py [hi ur mr ta] [--budget=175000]
    PYTHONPATH=. python scripts/translate_catalogue.py --sheets                  # regenerate review sheets only
    PYTHONPATH=. python scripts/translate_catalogue.py --mark-reviewed hi all    # or: hi key1 key2 ...
    PYTHONPATH=. python scripts/translate_catalogue.py --import-review hi docs/i18n/REVIEW_hi.csv

Every entry is validated before it is stored: the same {placeholders}, every glossary term in the
English (BPL, SC/ST, Group D, ...) present unchanged, markdown bold kept, non-empty. An invalid entry is
retried once on its own, then left untranslated -- the app falls back to English for it -- and listed in
the review sheet. Stored entries are "unreviewed" until a person marks them reviewed; review sheets in
docs/i18n/REVIEW_<lang>.md put the English beside each translation.

Since 2026-10-05 a translation must also be in the target language: one left identical to the English,
or with no character of the language's script, fails (the first Hindi batch kept "Yes"/"No" in English).
Entries failing the current checks are re-translated on the next run; reviewed entries never are.
The team's sheet is docs/i18n/REVIEW_<lang>.csv (Excel/Sheets; how-to in docs/i18n/HOW_TO_REVIEW.md):
regenerating it keeps what reviewers have filled in, and --import-review applies their verdicts.
"""

from __future__ import annotations

import csv
import json
import re
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


SCRIPTS = {
    "hi": ("Devanagari", r"[\u0900-\u097F]"),
    "mr": ("Devanagari", r"[\u0900-\u097F]"),
    "ur": ("Arabic (Urdu)", r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]"),
    "ta": ("Tamil", r"[\u0B80-\u0BFF]"),
}


def _words(text: str) -> list[str]:
    """English words in `text`, ignoring {placeholders} and glossary terms (which stay in English)."""
    text = re.sub(r"\{[^{}]*\}", " ", text)
    for term in sorted(messages.GLOSSARY, key=len, reverse=True):
        text = text.replace(term, " ")
    return re.findall(r"[A-Za-z]{2,}", text)


def checks(source: str, translation: object, language: str | None = None) -> list[str]:
    """Every automatic check the translation fails (empty list: passes)."""
    if not isinstance(translation, str) or not translation.strip():
        return ["empty"]
    problems = []
    if messages.placeholders(translation) != messages.placeholders(source):
        problems.append("placeholders differ")
    if source.count("**") != translation.count("**"):
        problems.append("bold markers differ")
    problems += [f"glossary term changed: {term}" for term in messages.GLOSSARY
                 if term in source and len(term) > 2 and term not in translation]
    if language in SCRIPTS and _words(source):
        name, pattern = SCRIPTS[language]
        if translation.strip() == source.strip():
            problems.append("identical to the English")
        elif not re.search(pattern, translation):
            problems.append(f"no {name} script")
    return problems


def valid(source: str, translation: object, language: str | None = None) -> bool:
    return not checks(source, translation, language)


def english_kept(source: str, translation: str | None) -> list[str]:
    """English words left in a translation (informational: some are UI labels, like "Select")."""
    return sorted(set(_words(translation or "")), key=str.lower)


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


def seed_hindi_ui(data: dict) -> int:
    """Hindi screen text (ui.*) is hand-written in frontend/lib/i18n.ts, not machine-translated. It goes
    into hi.json exactly as the app shows it, so it is on the Hindi review sheet, and is never sent to
    the LLM; a reviewer's correction reaches the frontend through scripts/export_ui_strings.py."""
    english, hindi = messages.ui_strings_english(), messages.ui_strings_hindi()
    added = 0
    for k, source in english.items():
        key = f"ui.{k}"
        if hindi.get(k) and data.get(key, {}).get("source") != source:
            data[key] = {"source": source, "text": hindi[k], "status": "unreviewed",
                         "origin": "hand-written in frontend/lib/i18n.ts"}
            added += 1
    return added


def translate(language: str, budget: int) -> str:
    ledger = harness.Ledger(ITEM, "groq", daily_budget=budget)
    catalogue = messages.catalogue()
    data = _load(language)
    if language == "hi" and seed_hindi_ui(data):
        _save(language, data)
    def needs_work(k: str, v: str) -> bool:
        entry = data.get(k, {})
        if language == "hi" and k.startswith("ui."):
            return False  # hand-written, seeded above
        if entry.get("source") != v:
            return True
        return entry.get("status") != "reviewed" and not valid(v, entry.get("text"), language)

    todo = {k: v for k, v in catalogue.items() if needs_work(k, v)}
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
        retry = {k: v for k, v in batch.items() if not valid(v, result.get(k), language)}
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
            ok = valid(source, result.get(k), language)
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
             "| Key | English | Translation | Status | Automatic checks |", "|---|---|---|---|---|"]
    for key, source in catalogue.items():
        entry = data.get(key, {})
        status = entry.get("status", "missing") if entry.get("source") == source else ("stale" if entry else "missing")
        cell = lambda s: (s or "").replace("|", "\\|").replace("\n", " ")  # noqa: E731
        flags = "; ".join(checks(source, entry.get("text"), language)) if entry.get("text") else ""
        lines.append(f"| `{key}` | {cell(source)} | {cell(entry.get('text'))} | {status} | {flags} |")
    SHEETS.mkdir(parents=True, exist_ok=True)
    (SHEETS / f"REVIEW_{language}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_csv(language)


WHERE = {"chat": "chat message", "reply": "answer button", "question": "question to the citizen",
         "verdict": "eligibility result", "trace": "explanation of the result", "field": "question to the citizen",
         "field_member": "question about a family member", "field_household": "question about the household",
         "label": "rule name in the explanation", "family_scope": "who counts as family", "ui": "screen text (menus, buttons)"}
CSV_COLUMNS = ["key", "where it appears", "English", "machine translation", "status", "automatic checks",
               "English words kept", "pre-check note", "reviewer verdict (OK / FIX)", "corrected translation",
               "reviewer", "comments"]
REVIEWER_COLUMNS = CSV_COLUMNS[-4:]
PRECHECK = ROOT / "data" / "i18n" / "precheck_notes.json"


def _precheck(language: str) -> dict:
    """Notes from an automated pre-check pass ({key: {"text": checked translation, "note": ...}}); a note
    is shown only while the translation is still the one that was checked. Not a review."""
    return json.loads(PRECHECK.read_text(encoding="utf-8")).get(language, {}) if PRECHECK.exists() else {}


def write_csv(language: str) -> Path:
    """docs/i18n/REVIEW_<lang>.csv for the team. Regenerating keeps the reviewer columns of every row;
    a row whose translation changed since is flagged for a fresh look."""
    path = SHEETS / f"REVIEW_{language}.csv"
    old = {}
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as f:
            old = {row["key"]: row for row in csv.DictReader(f)}
    data, notes = _load(language), _precheck(language)
    rows = []
    for key, source in messages.catalogue().items():
        entry = data.get(key, {})
        text = entry.get("text") if entry.get("source") == source else None
        status = entry.get("status", "not translated yet") if text else ("stale: English changed" if entry else "not translated yet")
        flags = checks(source, text, language) if text else []
        before = old.get(key, {})
        if before and before.get("machine translation") != (text or "") and any(before.get(c) for c in REVIEWER_COLUMNS):
            flags.append("CHANGED since this row was reviewed: please re-check")
        note = notes.get(key, {})
        rows.append({
            "key": key, "where it appears": WHERE.get(key.split(".")[0], "")
            + (" (hand-written, not machine-translated)" if entry.get("origin") else ""), "English": source,
            "machine translation": text or "", "status": status, "automatic checks": "; ".join(flags),
            "English words kept": ", ".join(english_kept(source, text)) if text else "",
            "pre-check note": note.get("note", "") if note.get("text") == text else "",
            **{c: before.get(c, "") for c in REVIEWER_COLUMNS},
        })
    rows.sort(key=lambda r: not r["machine translation"])  # translated rows first; otherwise catalogue order
    SHEETS.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:  # BOM: Excel opens it as UTF-8
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def import_review(language: str, path: str) -> dict:
    """Apply a filled-in sheet: OK marks the translation reviewed (only if it is still the one shown on
    the sheet); FIX stores the corrected translation as reviewed, if it passes the automatic checks."""
    data, catalogue = _load(language), messages.catalogue()
    result = {"ok": 0, "fixed": 0, "skipped": []}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            key, verdict = row["key"], row.get("reviewer verdict (OK / FIX)", "").strip().upper()
            if not verdict:
                continue
            source, entry = catalogue.get(key), data.get(key, {})
            if source is None:
                result["skipped"].append((key, "no longer in the catalogue"))
                continue
            stamp = {"status": "reviewed", "reviewed_on": date.today().isoformat(),
                     "reviewed_by": row.get("reviewer", "").strip()}
            if verdict == "OK":
                if entry.get("source") != source or not entry.get("text") or entry.get("text") != row["machine translation"]:
                    result["skipped"].append((key, "translation changed since the sheet was made, or missing"))
                    continue
                entry.update(stamp)
                result["ok"] += 1
            elif verdict == "FIX":
                fixed = row.get("corrected translation", "").strip()
                problems = checks(source, fixed, language)
                if problems:
                    result["skipped"].append((key, "correction fails: " + "; ".join(problems)))
                    continue
                data[key] = {**entry, "source": source, "text": fixed, "corrected_by_reviewer": True, **stamp}
                result["fixed"] += 1
            else:
                result["skipped"].append((key, f"verdict {verdict!r} is not OK or FIX"))
    _save(language, data)
    write_sheet(language)
    return result


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
    if "--import-review" in args:
        i = args.index("--import-review")
        r = import_review(args[i + 1], args[i + 2])
        print(f"{args[i + 1]}: {r['ok']} confirmed, {r['fixed']} corrected, {len(r['skipped'])} skipped")
        for key, why in r["skipped"]:
            print(f"  skipped {key}: {why}")
        sys.exit(0)
    if "--mark-reviewed" in args:
        i = args.index("--mark-reviewed")
        mark_reviewed(args[i + 1], args[i + 2:])
        sys.exit(0)
    languages = [a for a in args if not a.startswith("-")] or list(messages.LANGUAGES)
    if "--sheets" in args and "hi" in languages:
        hindi = _load("hi")
        if seed_hindi_ui(hindi):
            _save("hi", hindi)
    if "--sheets" not in args:
        budget = int(next((a.split("=", 1)[1] for a in args if a.startswith("--budget=")), harness.DAILY_BUDGET))
        for lang in languages:
            reason = translate(lang, budget)
            print(f"{lang}: {reason}", flush=True)
            if reason != "done":
                break
    for lang in languages:
        write_sheet(lang)
    print("review sheets written:", ", ".join(f"docs/i18n/REVIEW_{lang}.md/.csv" for lang in languages))
