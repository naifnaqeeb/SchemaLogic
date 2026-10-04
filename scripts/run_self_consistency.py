"""k independent extraction samples per gold scheme -- final-push item 2 (and Baseline 3).

LIVE: 2 LLM calls per sample. Paced under Groq's per-minute limit, stops cleanly at the day's budget
or Groq's daily cap, and resumes on re-run (saved samples are skipped).

    PYTHONPATH=. python scripts/run_self_consistency.py [--k=3] [--budget=180000] [SCHEME ...]

Each sample: data/experiments/self_consistency/<scheme>/sample_<i>.json, with the standard result
header (gold tag, provider, model, config, date), the source document's SHA-256, the extraction (or
its failure) and the measured token usage of each call. The extractor runs at its normal temperature
(0.2), so samples can differ; that variation is what self-consistency confidence measures. Sample 1
of each scheme is also Baseline 3 -- extraction with no judge or repair. Analysis is offline:
scripts/analyze_self_consistency.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from schemelogic.experiments import harness  # noqa: E402
from schemelogic.extraction import extractor  # noqa: E402

ITEM = "self_consistency"
OUT = harness.EXPERIMENTS_DIR / ITEM
PROVIDER = "groq"
ESTIMATE_PER_SAMPLE = 9_500  # tokens; measured 2026-08/09 at a median ~7.5k core + ~1.5-2k meta


def sample_path(scheme_id: str, i: int) -> Path:
    return OUT / scheme_id / f"sample_{i}.json"


def run(scheme_ids: list[str], k: int, budget: int, extract=extractor.extract_scheme, ledger=None) -> str:
    """Returns why it stopped: "done", "budget" or "daily_cap" / "rate_limited"."""
    ledger = ledger or harness.Ledger(ITEM, PROVIDER, daily_budget=budget)
    for sid in scheme_ids:
        text, sha = harness.source_document(sid)
        for i in range(1, k + 1):
            path = sample_path(sid, i)
            if path.exists():
                continue
            try:
                ledger.before_call(ESTIMATE_PER_SAMPLE)
            except harness.BudgetExhausted as exc:
                print(f"[stop] {exc}", flush=True)
                return "budget"
            usage: list[dict] = []
            result = extract(text, provider=PROVIDER, usage_sink=usage.append)
            for u in usage:
                ledger.record(u, scheme_id=sid, sample=i)
            failure = None if not isinstance(result, extractor.ExtractionFailure) else result
            if failure is not None and (failure.reason == "rate_limited" or harness.is_daily_cap(failure.detail)):
                # not a property of the sample -- don't save it; a re-run retries it
                reason = "daily_cap" if harness.is_daily_cap(failure.detail) else "rate_limited"
                print(f"[stop] {sid} sample {i}: {reason}: {failure.detail[:160]}", flush=True)
                return reason
            payload = {
                **harness.result_header(ITEM, PROVIDER, {"k": k, "temperature": 0.2, "extractor": "defaults"}),
                "scheme_id": sid, "sample": i, "source_document_sha256": sha, "usage": usage,
            }
            if failure is None:
                payload["draft_extraction"] = result.model_dump(mode="json", by_alias=True)
            else:
                payload["failure"] = {"reason": failure.reason, "detail": failure.detail[:2000]}
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            spent = sum(u.get("total_tokens") or 0 for u in usage)
            print(f"  {sid} sample {i}: {'ok' if failure is None else 'FAILED ' + failure.reason} "
                  f"({spent:,} tokens; today {harness.tokens_spent():,})", flush=True)
    return "done"


if __name__ == "__main__":
    args = sys.argv[1:]
    k = int(next((a.split("=", 1)[1] for a in args if a.startswith("--k=")), 3))
    budget = int(next((a.split("=", 1)[1] for a in args if a.startswith("--budget=")), harness.DAILY_BUDGET))
    schemes = [a for a in args if not a.startswith("-")] or harness.gold_scheme_ids()
    print(f"self-consistency: k={k}, schemes={schemes}, budget={budget:,}, today so far {harness.tokens_spent():,}", flush=True)
    print(f"stopped: {run(schemes, k, budget)}", flush=True)
