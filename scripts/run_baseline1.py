"""Baseline 1: flat attribute extraction for every gold scheme -- final-push items 3 (code) and 5 (run).

LIVE: one LLM call per scheme. Paced, budgeted and resumable like scripts/run_self_consistency.py.

    PYTHONPATH=. python scripts/run_baseline1.py [--budget=180000] [SCHEME ...]

Writes data/experiments/baseline1/<scheme>.json -- result header, source hash, the raw flat list, the
Scheme it converts to (schemelogic/evaluation/flat_baseline.py) or the failure, measured usage.
Scored by scripts/run_batch_report.py (configuration "baseline1_flat").
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from schemelogic.evaluation import flat_baseline  # noqa: E402
from schemelogic.experiments import harness  # noqa: E402
from schemelogic.extraction.extractor import ExtractionFailure  # noqa: E402

ITEM = "baseline1_flat"
OUT = harness.EXPERIMENTS_DIR / "baseline1"
PROVIDER = "groq"
ESTIMATE = 6_500


def run(scheme_ids: list[str], budget: int, extract=flat_baseline.extract_flat, ledger=None) -> str:
    ledger = ledger or harness.Ledger(ITEM, PROVIDER, daily_budget=budget)
    for sid in scheme_ids:
        path = OUT / f"{sid}.json"
        if path.exists():
            continue
        text, sha = harness.source_document(sid)
        try:
            ledger.before_call(ESTIMATE)
        except harness.BudgetExhausted as exc:
            print(f"[stop] {exc}", flush=True)
            return "budget"
        usage: list[dict] = []
        scheme, raw = extract(text, provider=PROVIDER, usage_sink=usage.append)
        for u in usage:
            ledger.record(u, scheme_id=sid)
        if isinstance(scheme, ExtractionFailure) and (scheme.reason == "rate_limited" or harness.is_daily_cap(scheme.detail)):
            print(f"[stop] {sid}: {scheme.reason}: {scheme.detail[:600]}", flush=True)
            return "daily_cap" if harness.is_daily_cap(scheme.detail) else "rate_limited"
        payload = {**harness.result_header(ITEM, PROVIDER, {"representation": "flat list: AND(required) + self disqualifiers"}),
                   "scheme_id": sid, "source_document_sha256": sha, "usage": usage, "raw_flat": raw}
        if isinstance(scheme, ExtractionFailure):
            payload["failure"] = {"reason": scheme.reason, "detail": scheme.detail[:2000]}
        else:
            payload["draft_extraction"] = scheme.model_dump(mode="json", by_alias=True)
        OUT.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"  {sid}: {'ok' if 'draft_extraction' in payload else 'FAILED'} "
              f"({sum(u.get('total_tokens') or 0 for u in usage):,} tokens; today {harness.tokens_spent():,})", flush=True)
    return "done"


if __name__ == "__main__":
    args = sys.argv[1:]
    budget = int(next((a.split("=", 1)[1] for a in args if a.startswith("--budget=")), harness.DAILY_BUDGET))
    schemes = [a for a in args if not a.startswith("-")] or harness.gold_scheme_ids()
    print(f"stopped: {run(schemes, budget)}", flush=True)
