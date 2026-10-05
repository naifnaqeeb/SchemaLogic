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
            payload["gated_extraction"] = sample_payload["draft_extraction"]  # nothing applied
        else:
            repaired, decisions = apply_gate_approved_findings(draft, report.findings, doc)
            payload["findings"] = [f.model_dump(mode="json") for f in report.findings]
            payload["gate_decisions"] = [d.to_dict() for d in decisions]
            payload["gated_extraction"] = repaired.model_dump(mode="json", by_alias=True)
        OUT.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"  {sid}: {len(payload.get('findings', []))} findings, "
              f"{sum(d['decision'] == 'auto_accept' for d in payload.get('gate_decisions', []))} applied "
              f"({sum(u.get('total_tokens') or 0 for u in usage):,} tokens)", flush=True)
    return "done"


if __name__ == "__main__":
    args = sys.argv[1:]
    budget = int(next((a.split("=", 1)[1] for a in args if a.startswith("--budget=")), harness.DAILY_BUDGET))
    print(f"stopped: {run([a for a in args if not a.startswith('-')] or harness.gold_scheme_ids(), budget)}", flush=True)
