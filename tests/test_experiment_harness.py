"""The final-push experiment harness and the k-sample runner. No network: the extractor is faked."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from schemelogic.experiments import harness
from schemelogic.extraction.extractor import ExtractionFailure
from schemelogic.schema.models import Scheme

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "EXPERIMENTS_DIR", tmp_path)
    monkeypatch.setattr(harness, "LEDGER", tmp_path / "ledger.jsonl")


def _runner():
    spec = importlib.util.spec_from_file_location("run_self_consistency", ROOT / "scripts" / "run_self_consistency.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.OUT = harness.EXPERIMENTS_DIR / "self_consistency"
    return module


def test_frozen_gold_reads_the_tag_not_the_working_tree():
    assert harness.gold_scheme_ids() == ["AB-PMJAY", "IGNOAPS", "MH-LADKI-BAHIN", "PM-KISAN", "PM-UJJWALA-2.0", "PMAY-G", "PMMVY"]
    assert isinstance(harness.frozen_gold("PMMVY"), Scheme)
    assert harness.frozen_profiles("PMMVY")


def test_result_header_records_everything_a_result_must():
    header = harness.result_header("x", "groq", {"k": 3})
    assert {"gold_tag", "gold_commit", "code_commit", "provider", "model", "config", "date"} <= set(header)
    assert header["gold_tag"] == "gold-v2" and header["model"] == "openai/gpt-oss-120b"


def test_ledger_enforces_the_daily_budget_and_records_measured_usage():
    ledger = harness.Ledger("x", "groq", daily_budget=1_000, sleep=lambda s: None)
    ledger.before_call(500)
    ledger.record({"prompt_tokens": 600, "completion_tokens": 100}, scheme_id="S")
    assert harness.tokens_spent() == 700
    with pytest.raises(harness.BudgetExhausted):
        ledger.before_call(500)


def test_ledger_paces_under_the_per_minute_limit():
    now = [1000.0]
    waits: list[float] = []

    def sleep(s):
        waits.append(s)
        now[0] += s

    ledger = harness.Ledger("x", "groq", daily_budget=10**9, sleep=sleep, clock=lambda: now[0])
    ledger.record({"total_tokens": 7_000})
    ledger.before_call(2_000)  # 7,000 in the last minute + 2,000 > the per-minute target -> wait
    assert waits and now[0] >= 1060


def test_daily_cap_is_recognised():
    assert harness.is_daily_cap("Rate limit reached ... on tokens per day (TPD): Limit 200000")
    assert not harness.is_daily_cap("Rate limit reached ... on tokens per minute (TPM)")


def _fast_ledger(budget: int) -> harness.Ledger:
    """A ledger whose sleep advances its own clock, so pacing costs no real time."""
    now = [0.0]

    def sleep(s):
        now[0] += s

    return harness.Ledger("self_consistency", "groq", daily_budget=budget, sleep=sleep, clock=lambda: now[0])


def _fake_extract(outcomes):
    calls = []

    def extract(text, provider, usage_sink):
        calls.append(provider)
        usage_sink({"call": "scheme_core_extraction", "prompt_tokens": 1000, "completion_tokens": 100, "total_tokens": 1100})
        return outcomes.pop(0)

    return extract, calls


def test_runner_saves_samples_resumes_and_stops_on_the_daily_cap():
    runner = _runner()
    scheme = harness.frozen_gold("PMMVY")
    extract, calls = _fake_extract([scheme, ExtractionFailure(reason="rate_limited", detail="tokens per day (TPD)")])
    ledger = _fast_ledger(10**9)
    assert runner.run(["PMMVY"], k=3, budget=10**9, extract=extract, ledger=ledger) == "daily_cap"
    saved = json.loads(runner.sample_path("PMMVY", 1).read_text(encoding="utf-8"))
    assert saved["gold_tag"] == "gold-v2" and saved["provider"] == "groq" and "draft_extraction" in saved
    assert not runner.sample_path("PMMVY", 2).exists()  # a capped call is never saved as a sample
    assert calls == ["groq", "groq"]

    extract, calls = _fake_extract([scheme, scheme])
    assert runner.run(["PMMVY"], k=3, budget=10**9, extract=extract, ledger=ledger) == "done"
    assert len(calls) == 2  # sample 1 was not redone


def test_runner_saves_a_content_failure_as_a_sample():
    runner = _runner()
    extract, _ = _fake_extract([ExtractionFailure(reason="schema_validation_failed", detail="bad")])
    ledger = _fast_ledger(10**9)
    runner.run(["PMMVY"], k=1, budget=10**9, extract=extract, ledger=ledger)
    assert json.loads(runner.sample_path("PMMVY", 1).read_text(encoding="utf-8"))["failure"]["reason"] == "schema_validation_failed"


def test_runner_stops_before_a_call_that_would_exceed_the_budget():
    runner = _runner()
    extract, calls = _fake_extract([])
    ledger = _fast_ledger(5_000)
    assert runner.run(["PMMVY"], k=1, budget=5_000, extract=extract, ledger=ledger) == "budget"
    assert calls == []


def test_gate_revalidation_runner_saves_findings_and_gate_decisions():
    spec = importlib.util.spec_from_file_location("run_gate_revalidation", ROOT / "scripts" / "run_gate_revalidation.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    runner.OUT = harness.EXPERIMENTS_DIR / "gate_revalidation"
    from schemelogic.extraction.judge_repair import JudgeReport

    calls = []

    def judge(scheme, doc, provider, usage_sink):
        calls.append(scheme.scheme_id)
        usage_sink({"call": "judge_report", "total_tokens": 100})
        return JudgeReport(findings=[])

    assert runner.run(10**9, judge=judge, ledger=_fast_ledger(10**9)) == "done"
    assert len(calls) == 21  # 14 mutated variants + 7 clean controls
    corpus = json.loads((runner.OUT / "corpus.json").read_text(encoding="utf-8"))
    assert corpus["config"]["synthetic"] is True and len(corpus["candidates"]) == 21
    saved = json.loads((runner.OUT / "PMMVY__clean.json").read_text(encoding="utf-8"))
    assert saved["gate_decisions"] == [] and saved["gold_tag"] == "gold-v2"
    assert runner.run(10**9, judge=judge, ledger=_fast_ledger(10**9)) == "done" and len(calls) == 21  # resumes
