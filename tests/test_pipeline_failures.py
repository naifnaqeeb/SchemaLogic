"""A failed judge call is a failed run (2026-10-06): recorded as such, excluded from the pipeline-vs-
Baseline-3 comparison, and retried once at a higher max_tokens. No network: the judge is faked."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from schemelogic.experiments import harness
from schemelogic.extraction.judge_repair import JudgeFailure, JudgeReport

ROOT = Path(__file__).resolve().parents[1]


def _script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "EXPERIMENTS_DIR", tmp_path)
    monkeypatch.setattr(harness, "LEDGER", tmp_path / "ledger.jsonl")
    module = _script("run_pipeline_on_samples")
    module.OUT, module.SAMPLES = tmp_path / "pipeline_on_sample1", tmp_path / "self_consistency"
    for sid in ("PM-KISAN", "PMMVY"):
        (module.SAMPLES / sid).mkdir(parents=True)
        (module.SAMPLES / sid / "sample_1.json").write_text(json.dumps(
            {"draft_extraction": harness.frozen_gold(sid).model_dump(mode="json", by_alias=True)}), encoding="utf-8")
    return module


def _ledger():
    now = [0.0]

    def sleep(s):
        now[0] += s

    return harness.Ledger("pipeline_on_sample1", "groq", daily_budget=10**9, sleep=sleep, clock=lambda: now[0])


FAIL = JudgeFailure(reason="api_error", detail="Error code: 400 - {'code': 'json_validate_failed', 'failed_generation': ''}")


def test_a_failed_judge_call_is_recorded_without_a_repaired_scheme_and_retried_once(pipeline):
    seen = []

    def judge(draft, doc, provider, usage_sink, compact_draft, max_tokens=None):
        seen.append((draft.scheme_id, max_tokens))
        return FAIL if max_tokens is None and draft.scheme_id == "PM-KISAN" else JudgeReport(findings=[])

    assert pipeline.run(["PM-KISAN", "PMMVY"], 10**9, judge=judge, ledger=_ledger()) == "done"
    failed = json.loads((pipeline.OUT / "PM-KISAN.json").read_text(encoding="utf-8"))
    assert "judge_failure" in failed and "gated_extraction" not in failed

    assert pipeline.retry_failed(["PM-KISAN", "PMMVY"], 10**9, judge=judge, ledger=_ledger()) == "done"
    assert seen[-1] == ("PM-KISAN", pipeline.RETRY_MAX_TOKENS) and len(seen) == 3  # PMMVY not retried
    retried = json.loads((pipeline.OUT / "PM-KISAN.json").read_text(encoding="utf-8"))
    assert "gated_extraction" in retried and retried["failed_attempts"][0]["judge_failure"]["reason"] == "api_error"
    pipeline.retry_failed(["PM-KISAN"], 10**9, judge=judge, ledger=_ledger())
    assert len(seen) == 3  # never a second retry


def test_the_batch_report_lists_failed_runs_and_leaves_them_out_of_the_comparison(pipeline, monkeypatch):
    def judge(draft, doc, provider, usage_sink, compact_draft, max_tokens=None):
        return FAIL if draft.scheme_id == "PM-KISAN" else JudgeReport(findings=[])

    pipeline.run(["PM-KISAN", "PMMVY"], 10**9, judge=judge, ledger=_ledger())
    br = _script("run_batch_report")
    monkeypatch.setattr(br, "EXP", harness.EXPERIMENTS_DIR)
    monkeypatch.setattr(br, "baseline2", lambda sid, gold, profiles: None)
    monkeypatch.setattr(br, "ROOT", harness.EXPERIMENTS_DIR)
    monkeypatch.setattr(br, "superseded_claims", lambda: [])
    monkeypatch.setattr(br, "CONFIGURATIONS", {k: v for k, v in br.CONFIGURATIONS.items()
                                               if k in ("baseline3_extraction_only", "pipeline_on_sample1")})
    report = br.build()
    pipe = report["configurations"]["pipeline_on_sample1"]
    assert "PM-KISAN" in pipe["failed"] and "PM-KISAN" not in pipe["per_scheme"]
    assert "json_validate_failed" in pipe["failed"]["PM-KISAN"]["reason"]
    paired = report["pipeline_vs_baseline3"]
    assert [r["scheme"] for r in paired["rows"]] == ["PMMVY"] and "PM-KISAN" in paired["excluded"]
    md = br.markdown(report)
    assert "**failed run**" in md and "## Full pipeline vs Baseline 3, same extraction" in md
