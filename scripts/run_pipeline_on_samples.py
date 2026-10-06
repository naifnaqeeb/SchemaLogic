"""The full pipeline on the SAME extraction Baseline 3 uses -- so judge+repair+gate is measured against
extraction alone on equal footing (final-push item 3's comparison).

LIVE: one judge call per scheme. Paced, budgeted (rolling 24h), resumable.

    PYTHONPATH=. python scripts/run_pipeline_on_samples.py [--budget=175000] [SCHEME ...]

For each scheme: k=3 sample 1 (Baseline 3: extraction only) -> one judge pass (compact draft) -> the
calibration gate on each finding -> only auto-accepted findings applied (the live pipeline's rule).
Writes data/experiments/pipeline_on_sample1/<scheme>.json with the findings, the gate decisions, the
repaired scheme (`gated_extraction`) and measured usage. Scored by scripts/run_batch_report.py
("pipeline_on_sample1", beside "baseline3_extraction_only").
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from schemelogic.deferral.calibration_gate import apply_gate_approved_findings  # noqa: E402
from schemelogic.experiments import harness  # noqa: E402
from schemelogic.extraction import judge_repair  # noqa: E402
from schemelogic.schema.models import Scheme  # noqa: E402

ITEM = "pipeline_on_sample1"
RETRY_MAX_TOKENS = 2000  # Baseline 2's json_validate_failed recovery cap (scripts/run_baseline2.py)
OUT = harness.EXPERIMENTS_DIR / ITEM
SAMPLES = harness.EXPERIMENTS_DIR / "self_consistency"
PROVIDER = "groq"
ESTIMATE = 8_000


def run(scheme_ids: list[str], budget: int, judge=judge_repair.run_judge, ledger=None) -> str:
    ledger = ledger or harness.Ledger(ITEM, PROVIDER, daily_budget=budget)
    for sid in scheme_ids:
        path, sample = OUT / f"{sid}.json", SAMPLES / sid / "sample_1.json"
        if path.exists() or not sample.exists():
            continue
        sample_payload = json.loads(sample.read_text(encoding="utf-8"))
        if "draft_extraction" not in sample_payload:
            continue  # Baseline 3 failed for this scheme: nothing for the pipeline to repair
        draft = Scheme.model_validate(sample_payload["draft_extraction"])
        doc, sha = harness.source_document(sid)
        try:
            ledger.before_call(ESTIMATE)
        except harness.BudgetExhausted as exc:
            print(f"[stop] {exc}", flush=True)
            return "budget"
        usage: list[dict] = []
        report = judge(draft, doc, provider=PROVIDER, usage_sink=usage.append, compact_draft=True)
        for u in usage:
            ledger.record(u, scheme_id=sid)
        payload = {**harness.result_header(ITEM, PROVIDER, {"judge_samples": 1, "compact_draft": True,
                                                           "apply": "gate auto-accepted findings only"}),
                   "scheme_id": sid, "source_document_sha256": sha, "from_sample": f"self_consistency/{sid}/sample_1.json",
                   "usage": usage}
        if isinstance(report, judge_repair.JudgeFailure):
            if harness.is_daily_cap(report.detail) or "rate limit" in report.detail.lower():
                print(f"[stop] {sid}: {report.detail[:600]}", flush=True)
                return "daily_cap" if harness.is_daily_cap(report.detail) else "rate_limited"
            payload["judge_failure"] = {"reason": report.reason, "detail": report.detail[:2000]}
            # no gated_extraction: a failed run is recorded as failed, never as "the judge found nothing"
        else:
            repaired, decisions = apply_gate_approved_findings(draft, report.findings, doc)
            payload["findings"] = [f.model_dump(mode="json") for f in report.findings]
            payload["gate_decisions"] = [d.to_dict() for d in decisions]
            payload["gated_extraction"] = repaired.model_dump(mode="json", by_alias=True)
        OUT.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        _print(sid, payload, usage)
    return "done"


def _print(sid: str, payload: dict, usage: list[dict]) -> None:
    spent = f"({sum(u.get('total_tokens') or 0 for u in usage):,} tokens)"
    if "judge_failure" in payload:
        print(f"  {sid}: JUDGE FAILED ({payload['judge_failure']['reason']}) {spent}", flush=True)
    else:
        print(f"  {sid}: {len(payload.get('findings', []))} findings, "
              f"{sum(d['decision'] == 'auto_accept' for d in payload.get('gate_decisions', []))} applied {spent}", flush=True)


# Retry settings for a judge call that failed with json_validate_failed (gpt-oss spending its whole
# completion budget on reasoning before any JSON). Each is tried at most once per scheme, in the order
# the queue asks for them; the result records which setting produced it.
RETRY_SETTINGS = {
    "max_tokens_2000": {"max_tokens": RETRY_MAX_TOKENS},  # Baseline 2's recovery (2026-10-06 14:32: failed again)
    "reasoning_low": {"reasoning_effort": "low"},          # the extractor's truncation recovery (2026-10-06 evening)
}


def _request_estimate(draft: Scheme, doc: str) -> dict:
    """The judge request's size against Groq's per-request limit (prompt + completion <= 8,000 tokens),
    estimated as judge_repair sizes it -- a failed call returns no usage to measure."""
    from schemelogic.extraction.extractor import _estimate_tokens

    draft_json = json.dumps(draft.model_dump(mode="json", by_alias=True, exclude_defaults=True), ensure_ascii=False, separators=(",", ":"))
    prompt = (judge_repair._judge_system_prompt() + f"SOURCE DOCUMENT:\n{doc}\n\nDRAFT EXTRACTION (already produced from this document):\n{draft_json}"
              + json.dumps(judge_repair._JUDGE_JSON_SCHEMA))
    return {"prompt_tokens_estimate": _estimate_tokens(prompt), "request_limit": judge_repair._REQUEST_CEILING}


def _tried(payload: dict) -> list[str]:
    tried = list(payload.get("retry_settings", []))
    if payload.get("retried_with_max_tokens") and "max_tokens_2000" not in tried:  # results written before the field existed
        tried.insert(0, "max_tokens_2000")
    return tried


def retry_failed(scheme_ids: list[str], budget: int, judge=judge_repair.run_judge, ledger=None,
                 setting: str = "max_tokens_2000") -> str:
    """Re-run every scheme whose judge call failed with json_validate_failed, once with `setting` (see
    RETRY_SETTINGS). Every failed attempt is kept under `failed_attempts`; `judge_setting` records the
    setting of the call this result came from, so a comparison can show it."""
    kwargs = RETRY_SETTINGS[setting]
    ledger = ledger or harness.Ledger(ITEM, PROVIDER, daily_budget=budget)
    for sid in scheme_ids:
        path = OUT / f"{sid}.json"
        if not path.exists():
            continue
        previous = json.loads(path.read_text(encoding="utf-8"))
        failure = previous.get("judge_failure")
        if not failure or "json_validate_failed" not in failure.get("detail", "") or setting in _tried(previous):
            continue
        sample_payload = json.loads((SAMPLES / sid / "sample_1.json").read_text(encoding="utf-8"))
        draft = Scheme.model_validate(sample_payload["draft_extraction"])
        doc, sha = harness.source_document(sid)
        try:
            ledger.before_call(ESTIMATE)
        except harness.BudgetExhausted as exc:
            print(f"[stop] {exc}", flush=True)
            return "budget"
        usage: list[dict] = []
        report = judge(draft, doc, provider=PROVIDER, usage_sink=usage.append, compact_draft=True, **kwargs)
        for u in usage:
            ledger.record(u, scheme_id=sid, retry=setting)
        if isinstance(report, judge_repair.JudgeFailure) and (harness.is_daily_cap(report.detail) or "rate limit" in report.detail.lower()):
            print(f"[stop] {sid}: {report.detail[:600]}", flush=True)
            return "daily_cap" if harness.is_daily_cap(report.detail) else "rate_limited"
        attempt = {k: previous[k] for k in ("created_at", "code_commit", "usage", "judge_failure", "judge_setting") if k in previous}
        payload = {**harness.result_header(ITEM, PROVIDER, {"judge_samples": 1, "compact_draft": True,
                                                           "apply": "gate auto-accepted findings only", **kwargs}),
                   "scheme_id": sid, "source_document_sha256": sha, "from_sample": previous["from_sample"],
                   "usage": usage, "judge_setting": kwargs, "retry_settings": _tried(previous) + [setting],
                   "request_estimate": _request_estimate(draft, doc),
                   "failed_attempts": previous.get("failed_attempts", []) + [attempt]}
        if isinstance(report, judge_repair.JudgeFailure):
            payload["judge_failure"] = {"reason": report.reason, "detail": report.detail[:2000]}
        else:
            repaired, decisions = apply_gate_approved_findings(draft, report.findings, doc)
            payload["findings"] = [f.model_dump(mode="json") for f in report.findings]
            payload["gate_decisions"] = [d.to_dict() for d in decisions]
            payload["gated_extraction"] = repaired.model_dump(mode="json", by_alias=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        _print(f"{sid} (retry, {setting})", payload, usage)
    return "done"


if __name__ == "__main__":
    args = sys.argv[1:]
    budget = int(next((a.split("=", 1)[1] for a in args if a.startswith("--budget=")), harness.DAILY_BUDGET))
    print(f"stopped: {run([a for a in args if not a.startswith('-')] or harness.gold_scheme_ids(), budget)}", flush=True)
