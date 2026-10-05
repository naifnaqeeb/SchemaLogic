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

    def judge(scheme, doc, provider, usage_sink, compact_draft):
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


def test_gate_candidates_hide_the_gold_annotators_reasoning():
    spec = importlib.util.spec_from_file_location("run_gate_revalidation", ROOT / "scripts" / "run_gate_revalidation.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    for cand in runner.candidates():
        assert cand["scheme"]["extraction_metadata"]["source_clause"] == runner.NEUTRAL_SOURCE_CLAUSE


def test_pipeline_on_samples_applies_only_gate_approved_findings():
    spec = importlib.util.spec_from_file_location("run_pipeline_on_samples", ROOT / "scripts" / "run_pipeline_on_samples.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    runner.OUT = harness.EXPERIMENTS_DIR / "pipeline_on_sample1"
    runner.SAMPLES = harness.EXPERIMENTS_DIR / "self_consistency"
    gold = harness.frozen_gold("PMMVY")
    (runner.SAMPLES / "PMMVY").mkdir(parents=True)
    (runner.SAMPLES / "PMMVY" / "sample_1.json").write_text(
        json.dumps({"draft_extraction": gold.model_dump(mode="json", by_alias=True)}), encoding="utf-8")
    from schemelogic.extraction.judge_repair import JudgeFinding, JudgeReport

    finding = JudgeFinding(category="preambular_implied_fact", description="d", source_quote="not in the document at all",
                           confidence=0.99, proposed_predicate={"location": "inclusion", "cat": "other", "field": "made_up", "op": "==", "value": True})

    def judge(scheme, doc, provider, usage_sink, compact_draft):
        return JudgeReport(findings=[finding])

    assert runner.run(["PMMVY"], 10**9, judge=judge, ledger=_fast_ledger(10**9)) == "done"
    saved = json.loads((runner.OUT / "PMMVY.json").read_text(encoding="utf-8"))
    assert saved["gate_decisions"][0]["decision"] == "defer_to_review"  # quote not in the source
    assert "made_up" not in json.dumps(saved["gated_extraction"])        # so nothing was applied


def test_seconds_until_headroom_reads_the_rolling_window():
    from datetime import datetime, timedelta

    now = datetime(2026, 10, 5, 15, 0)
    rows = [{"ts": (now - timedelta(hours=14)).isoformat(), "total_tokens": 100_000},
            {"ts": (now - timedelta(hours=1)).isoformat(), "total_tokens": 70_000}]
    harness.LEDGER.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    assert harness.seconds_until_headroom(5_000, budget=180_000, now=now) == 0
    wait = harness.seconds_until_headroom(20_000, budget=180_000, now=now)
    assert abs(wait - 10 * 3600) < 1  # the 100k row leaves the window 24h after it was recorded


def test_rag_comparison_runs_both_arms_on_the_same_draft():
    spec = importlib.util.spec_from_file_location("run_rag_comparison", ROOT / "scripts" / "run_rag_comparison.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    runner.OUT = harness.EXPERIMENTS_DIR / "rag_comparison"
    sc = harness.EXPERIMENTS_DIR / "self_consistency"
    for sid in runner.SCHEMES:
        (sc / sid).mkdir(parents=True, exist_ok=True)
        (sc / sid / "sample_1.json").write_text(json.dumps({"draft_extraction": harness.frozen_gold(sid).model_dump(mode="json", by_alias=True)}), encoding="utf-8")
    from schemelogic.extraction.judge_repair import JudgeReport

    seen = []

    class Index:
        def query(self, q, top_k):
            return []

    def judge(draft, doc, provider, usage_sink, compact_draft, retrieved_context):
        seen.append((draft.scheme_id, retrieved_context))
        return JudgeReport(findings=[])

    assert runner.run(10**9, judge=judge, index=Index(), ledger=_fast_ledger(10**9)) == "done"
    assert [s for s, _ in seen] == ["PM-KISAN", "PM-KISAN", "MH-LADKI-BAHIN", "MH-LADKI-BAHIN"]
    assert {r["status"] for r in runner.summarize()["rows"]} == {"ran"}
