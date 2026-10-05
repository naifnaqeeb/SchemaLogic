"""Gate re-validation on the synthetic injected-error corpus -- final-push item 6.

LIVE: one judge call per mutated variant (14) and per clean control (the 7 unmutated gold schemes).
Paced, budgeted (rolling 24h) and resumable.

    PYTHONPATH=. python scripts/run_gate_revalidation.py [--budget=175000]

For each candidate scheme the judge reads the source document and the candidate, and the calibration
gate decides accept/defer on each finding -- the pipeline exactly as it runs on a real extraction, with
one judge sample (no re-sample: the self-consistency signal is absent, as the gate allows). Writes
data/experiments/gate_revalidation/corpus.json (the labelled errors) and one file per candidate with the
judge report, gate decisions and measured usage. Scoring is offline: scripts/analyze_gate_revalidation.py.
SYNTHETIC errors: what the gate can catch, not how often real errors occur. Small sample (~30 errors).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from schemelogic.deferral.calibration_gate import evaluate_gate_batch  # noqa: E402
from schemelogic.experiments import harness, injected_errors  # noqa: E402
from schemelogic.extraction import judge_repair  # noqa: E402
from schemelogic.schema.models import Scheme  # noqa: E402

ITEM = "gate_revalidation"
OUT = harness.EXPERIMENTS_DIR / ITEM
PROVIDER = "groq"
ESTIMATE = 8_000


NEUTRAL_SOURCE_CLAUSE = "(not provided)"


def _blind(scheme: dict) -> dict:
    """The judge must see a candidate the way it sees a real extraction: the gold's source_clause is
    the annotator's reasoning and audit history -- it would both leak the answers and inflate the
    prompt past Groq's 8k-per-request ceiling -- so it is replaced, as is the gold's confidence."""
    meta = scheme["extraction_metadata"]
    meta["source_clause"], meta["confidence"], meta["flagged_for_review"] = NEUTRAL_SOURCE_CLAUSE, 0.8, False
    return scheme


def candidates() -> list[dict]:
    golds = {s: harness.frozen_gold(s) for s in harness.gold_scheme_ids()}
    variants = injected_errors.build_corpus(golds)
    controls = [{"variant_id": f"{sid}~clean", "scheme_id": sid, "errors": [],
                 "scheme": g.model_dump(mode="json", by_alias=True)} for sid, g in golds.items()]
    for cand in variants + controls:
        _blind(cand["scheme"])
    return variants + controls


def run(budget: int, judge=judge_repair.run_judge, ledger=None) -> str:
    ledger = ledger or harness.Ledger(ITEM, PROVIDER, daily_budget=budget)
    cands = candidates()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "corpus.json").write_text(json.dumps({
        **harness.result_header(ITEM, PROVIDER, {"n_errors": 30, "per_variant": 3, "seed": 20261005, "synthetic": True}),
        "candidates": cands}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for cand in cands:
        path = OUT / f"{cand['variant_id'].replace('~', '__')}.json"
        if path.exists():
            continue
        doc, sha = harness.source_document(cand["scheme_id"])
        try:
            ledger.before_call(ESTIMATE)
        except harness.BudgetExhausted as exc:
            print(f"[stop] {exc}", flush=True)
            return "budget"
        usage: list[dict] = []
        report = judge(Scheme.model_validate(cand["scheme"]), doc, provider=PROVIDER, usage_sink=usage.append)
        for u in usage:
            ledger.record(u, scheme_id=cand["scheme_id"], variant=cand["variant_id"])
        payload = {**harness.result_header(ITEM, PROVIDER, {"judge_samples": 1}), "variant_id": cand["variant_id"],
                   "scheme_id": cand["scheme_id"], "source_document_sha256": sha, "usage": usage,
                   "injected_error_ids": [e["error_id"] for e in cand["errors"]]}
        if isinstance(report, judge_repair.JudgeFailure):
            if harness.is_daily_cap(report.detail) or "rate limit" in report.detail.lower():
                print(f"[stop] {cand['variant_id']}: {report.detail[:600]}", flush=True)
                return "daily_cap" if harness.is_daily_cap(report.detail) else "rate_limited"
            payload["judge_failure"] = {"reason": report.reason, "detail": report.detail[:2000]}
        else:
            decisions = evaluate_gate_batch(report.findings, doc)
            payload["findings"] = [f.model_dump(mode="json") for f in report.findings]
            payload["gate_decisions"] = [d.to_dict() for d in decisions]
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"  {cand['variant_id']}: {len(payload.get('findings', []))} findings "
              f"({sum(u.get('total_tokens') or 0 for u in usage):,} tokens; 24h {harness.tokens_spent_rolling():,})", flush=True)
    return "done"


if __name__ == "__main__":
    budget = int(next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--budget=")), harness.DAILY_BUDGET))
    print(f"stopped: {run(budget)}", flush=True)
