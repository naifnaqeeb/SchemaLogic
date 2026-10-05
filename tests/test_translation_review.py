"""Translation checks, team review sheets and the review state the interface shows (2026-10-05).
No network: the LLM call is faked; translation files and sheets live in a temporary directory."""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pytest

from schemelogic.conversational import messages
from schemelogic.experiments import harness

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def tc(tmp_path, monkeypatch):
    monkeypatch.setattr(messages, "I18N_DIR", tmp_path / "i18n")
    monkeypatch.setattr(harness, "EXPERIMENTS_DIR", tmp_path)
    monkeypatch.setattr(harness, "LEDGER", tmp_path / "ledger.jsonl")
    spec = importlib.util.spec_from_file_location("translate_catalogue", ROOT / "scripts" / "translate_catalogue.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "SHEETS", tmp_path / "sheets")
    monkeypatch.setattr(module, "PRECHECK", tmp_path / "i18n" / "precheck_notes.json")
    messages.reload_translations()
    yield module
    messages.reload_translations()


def _write(language: str, entries: dict) -> None:
    messages.I18N_DIR.mkdir(parents=True, exist_ok=True)
    (messages.I18N_DIR / f"{language}.json").write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    messages.reload_translations()


def _rows(path: Path) -> dict[str, dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return {r["key"]: r for r in csv.DictReader(f)}


def test_a_translation_left_in_english_or_in_the_wrong_script_fails(tc):
    assert tc.checks("Yes", "Yes", "hi") == ["identical to the English"]
    assert tc.checks("Yes", "हाँ", "hi") == []
    assert tc.checks("Yes", "हाँ", "ta") == ["no Tamil script"]
    assert tc.checks("Yes", "ہاں", "ur") == []
    assert tc.checks("{emoji} {scheme_id}", "{emoji} {scheme_id}", "hi") == []  # nothing to translate
    assert tc.checks("Aadhaar", "Aadhaar", "mr") == []                          # glossary term only
    assert tc.valid("Are you BPL, {name}?", "क्या आप BPL हैं, {name}?")          # old two-argument form
    assert tc.english_kept("Click Select", "“Select” पर क्लिक करें") == ["Select"]


def test_failing_entries_are_redone_reviewed_ones_never_and_hindi_screen_text_is_not_sent(tc, monkeypatch):
    catalogue = messages.catalogue()
    _write("hi", {
        "reply.yes": {"source": "Yes", "text": "Yes", "status": "unreviewed"},           # fails: redo
        "reply.no": {"source": "No", "text": "No", "status": "reviewed"},                # reviewed: keep
        "chat.found": {"source": catalogue["chat.found"], "text": "यहाँ मैंने जो पाया", "status": "unreviewed"},
    })
    sent = []

    def fake_call(language, batch, ledger):
        sent.extend(batch)
        return {k: "हिंदी पाठ " + " ".join("{" + p + "}" for p in messages.placeholders(v)) for k, v in batch.items()}

    monkeypatch.setattr(tc, "_call", fake_call)
    assert tc.translate("hi", 10**9) == "done"
    assert "reply.yes" in sent and "reply.no" not in sent and "chat.found" not in sent
    assert not any(k.startswith("ui.") for k in sent)
    data = json.loads((messages.I18N_DIR / "hi.json").read_text(encoding="utf-8"))
    assert data["ui.nav_browse"]["text"] == messages.ui_strings_hindi()["nav_browse"]
    assert data["ui.nav_browse"]["origin"].startswith("hand-written")


def test_regenerating_the_sheet_keeps_reviewer_input_and_flags_changed_rows(tc):
    catalogue = messages.catalogue()
    _write("hi", {"chat.found": {"source": catalogue["chat.found"], "text": "यहाँ मैंने जो पाया", "status": "unreviewed"},
                  "reply.yes": {"source": "Yes", "text": "हाँ", "status": "unreviewed"}})
    path = tc.write_csv("hi")
    rows = list(_rows(path).values())
    assert [r["key"] for r in rows[:2]] == ["chat.found", "reply.yes"]  # translated rows first
    filled = _rows(path)
    filled["chat.found"].update({"reviewer verdict (OK / FIX)": "OK", "reviewer": "A"})
    filled["reply.yes"].update({"reviewer verdict (OK / FIX)": "OK", "reviewer": "A"})
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=tc.CSV_COLUMNS)
        w.writeheader()
        w.writerows(filled.values())
    _write("hi", {"chat.found": {"source": catalogue["chat.found"], "text": "यहाँ मैंने जो पाया", "status": "unreviewed"},
                  "reply.yes": {"source": "Yes", "text": "जी हाँ", "status": "unreviewed"}})  # retranslated since
    again = _rows(tc.write_csv("hi"))
    assert again["chat.found"]["reviewer"] == "A" and again["chat.found"]["automatic checks"] == ""
    assert "CHANGED" in again["reply.yes"]["automatic checks"]


def test_importing_a_review_marks_ok_rows_and_applies_valid_fixes_only(tc):
    catalogue = messages.catalogue()
    source = catalogue["verdict.answer_undetermined"]
    _write("hi", {"verdict.answer_undetermined": {"source": source, "text": "मैं एक और विवरण चाहिए {scheme_id}", "status": "unreviewed"},
                  "chat.found": {"source": catalogue["chat.found"], "text": "यहाँ मैंने जो पाया", "status": "unreviewed"},
                  "reply.yes": {"source": "Yes", "text": "हाँ", "status": "unreviewed"}})
    path = tc.write_csv("hi")
    rows = _rows(path)
    rows["chat.found"].update({"reviewer verdict (OK / FIX)": "ok", "reviewer": "A"})
    rows["verdict.answer_undetermined"].update({"reviewer verdict (OK / FIX)": "FIX", "reviewer": "B",
                                                 "corrected translation": "मुझे {scheme_id} के लिए एक और जानकारी चाहिए।"})
    rows["reply.yes"].update({"reviewer verdict (OK / FIX)": "FIX", "corrected translation": "Yes"})  # fails checks
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=tc.CSV_COLUMNS)
        w.writeheader()
        w.writerows(rows.values())
    result = tc.import_review("hi", str(path))
    assert result["ok"] == 1 and result["fixed"] == 1 and [k for k, _ in result["skipped"]] == ["reply.yes"]
    data = json.loads((messages.I18N_DIR / "hi.json").read_text(encoding="utf-8"))
    assert data["chat.found"]["status"] == "reviewed" and data["chat.found"]["reviewed_by"] == "A"
    assert data["verdict.answer_undetermined"]["text"].startswith("मुझे") and data["verdict.answer_undetermined"]["corrected_by_reviewer"]
    assert data["reply.yes"]["status"] == "unreviewed"


def test_review_state_is_reviewed_only_when_every_entry_is(tc):
    assert messages.review_status("ta")["state"] == "none"
    catalogue = messages.catalogue()
    _write("ta", {"chat.found": {"source": catalogue["chat.found"], "text": "நான் கண்டது", "status": "reviewed"}})
    assert messages.review_status("ta") == {"state": "machine", "translated": 1, "reviewed": 1, "total": len(catalogue)}
    _write("ta", {k: {"source": v, "text": v, "status": "reviewed"} for k, v in catalogue.items()})
    assert messages.review_status("ta")["state"] == "reviewed"


def test_pucca_and_kutcha_may_be_translated_into_hindi_but_stay_glossary_elsewhere(tc):
    source = "Does your family live in a kutcha house?"
    assert tc.checks(source, "क्या आपका परिवार कच्चे घर में रहता है?", "hi") == []
    assert tc.checks(source, "உங்கள் குடும்பம் மண் வீட்டில் வசிக்கிறதா?", "ta") == ["glossary term changed: kutcha"]
    assert tc.checks("Do you hold an e-Shram card?", "क्या आपके पास ई-श्रम कार्ड है?", "hi") == ["glossary term changed: e-Shram"]
    assert "पक्का" in tc.system_prompt("hi") and "pucca" not in tc.system_prompt("hi").split("untranslated:")[1].split(".")[0]


def test_entries_handed_to_people_are_never_sent_to_the_model_and_lead_the_sheet(tc, monkeypatch):
    catalogue = messages.catalogue()
    key = "field.is_e_shram_registered"
    _write("hi", {key: {"source": catalogue[key], "text": None, "status": "failed_validation"}})
    assert tc.mark_manual("hi", ["failed"]) == [key]
    sent = []
    monkeypatch.setattr(tc, "_call", lambda language, batch, ledger: sent.extend(batch) or {k: "हिंदी" for k in batch})
    tc.translate("hi", 10**9)
    assert key not in sent
    first = next(iter(_rows(tc.SHEETS / "REVIEW_hi.csv").values()))
    assert first["key"] == key and first["status"] == "TRANSLATE BY HAND" and first["machine translation"] == ""
    assert "FIX" in first["automatic checks"]
