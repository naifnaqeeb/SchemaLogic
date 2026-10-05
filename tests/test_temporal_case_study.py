"""Temporal case study (C4) runner and scoring -- final-push item 9. No network: the extractor is faked
and the documents are stubbed (the pre-amendment PDFs are gitignored)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from schemelogic.evaluation.structural_f1 import flatten_scheme
from schemelogic.experiments import harness
from schemelogic.extraction.extractor import ExtractionFailure
from schemelogic.schema.models import Scheme

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def runner(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "EXPERIMENTS_DIR", tmp_path)
    monkeypatch.setattr(harness, "LEDGER", tmp_path / "ledger.jsonl")
    spec = importlib.util.spec_from_file_location("run_temporal_case_study", ROOT / "scripts" / "run_temporal_case_study.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.OUT = tmp_path / "temporal_c4"
    module.document = lambda arm: f"document of {arm.name}"
    return module


def _ledger():
    now = [0.0]

    def sleep(s):
        now[0] += s

    return harness.Ledger("temporal_c4", "groq", daily_budget=10**9, sleep=sleep, clock=lambda: now[0])


def _scheme(sid: str, inclusion: dict, exclusions: list[dict] | None = None) -> Scheme:
    return Scheme.model_validate({
        "scheme_id": sid, "unit_of_eligibility": "individual", "inclusion": inclusion, "exclusions": exclusions or [],
        "temporal_validity": {"extracted_at": "2026-10-05"}, "extraction_metadata": {"confidence": 0.9, "source_clause": "x"}})


def _pred(field, op, value, cat="demographic"):
    return {"field": field, "op": op, "value": value, "cat": cat}


def test_detectors_tell_old_rule_from_new(runner):
    first_only = flatten_scheme(_scheme("PMMVY", _pred("pregnancy_child_order", "==", 1)))
    assert runner.child_order_rule(first_only)[0] == "first child only"
    gold = flatten_scheme(harness.frozen_gold("PMMVY"))
    assert runner.child_order_rule(gold)[0] == "first child, or second if a girl"
    assert runner.child_order_rule(flatten_scheme(_scheme("PMMVY", _pred("age", ">=", 18))))[0] == "no child-order rule"

    mh = flatten_scheme(harness.frozen_gold("MH-LADKI-BAHIN"))
    assert runner.max_age(mh)[0] == "<= 65"
    land = runner.CHECKS["MH-LADKI-BAHIN"][0][1]
    assert land(mh)[0] == "absent"
    pre = _scheme("MH-LADKI-BAHIN", _pred("age", "<=", 60),
                  [{**_pred("family_agricultural_land_acres", ">", 5, "economic"), "quantifier": "some_family_member"}])
    assert land(flatten_scheme(pre)) == ("present", ["exclusion: family_agricultural_land_acres > 5"])

    assert runner.age_70_branch(flatten_scheme(harness.frozen_gold("AB-PMJAY")))[0] == "present"
    pmay = flatten_scheme(harness.frozen_gold("PMAY-G"))
    assert runner.monthly_income_threshold(pmay)[0] == "15000"
    assert [c[1](pmay)[0] for c in runner.CHECKS["PMAY-G"][:2]] == ["absent", "absent"]


def test_runner_saves_the_excerpt_resumes_and_stops_on_the_daily_cap(runner):
    calls = []
    outcomes = [harness.frozen_gold("PMMVY"), ExtractionFailure(reason="rate_limited", detail="tokens per day (TPD)")]

    def extract(text, provider, usage_sink):
        calls.append(text)
        usage_sink({"call": "scheme_core_extraction", "prompt_tokens": 1000, "completion_tokens": 100, "total_tokens": 1100})
        return outcomes.pop(0)

    ledger = _ledger()
    assert runner.run(10**9, extract=extract, ledger=ledger) == "daily_cap"
    first = runner.ARMS[0]
    saved = json.loads(runner.sample_path(first, 1).read_text(encoding="utf-8"))
    assert saved["gold_tag"] == "gold-v2" and saved["role"] == "pre" and saved["source_excerpt"] == f"document of {first.name}"
    assert not runner.sample_path(runner.ARMS[1], 1).exists()  # a capped call is never saved

    outcomes[:] = [harness.frozen_gold("PMMVY")] * 10
    assert runner.run(10**9, extract=extract, ledger=ledger) == "done"
    assert len(calls) == 2 + sum(a.k for a in runner.ARMS) - 1  # the saved sample was not redone


def test_score_compares_each_arm_with_its_expected_value(runner):
    pre = runner.ARMS[0]  # PMMVY pre-amendment
    runner.sample_path(pre, 1).parent.mkdir(parents=True)
    runner.sample_path(pre, 1).write_text(json.dumps({"draft_extraction": _scheme(
        "PMMVY", _pred("pregnancy_child_order", "==", 1)).model_dump(mode="json", by_alias=True)}), encoding="utf-8")
    post = harness.EXPERIMENTS_DIR / "self_consistency" / "PMMVY"
    post.mkdir(parents=True)
    (post / "sample_1.json").write_text(json.dumps({"draft_extraction": harness.frozen_gold("PMMVY").model_dump(mode="json", by_alias=True)}), encoding="utf-8")
    (post / "sample_2.json").write_text(json.dumps({"failure": {"reason": "schema_validation_failed"}}), encoding="utf-8")

    s = runner.score()
    rows = {r["role"]: r for r in s["summary"] if r["scheme"] == "PMMVY"}
    assert rows["pre"]["as_expected"] == 1 and rows["pre"]["valid_samples"] == 1
    assert rows["post"]["as_expected"] == 1 and rows["post"]["failed_samples"] == 1
    assert "PM-KISAN" in s["dropped"]
    assert "| PMMVY | child-order rule | pre-amendment text | first child only | 1/1 |" in runner.markdown(s)
