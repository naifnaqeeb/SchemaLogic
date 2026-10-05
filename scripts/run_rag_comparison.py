"""With vs without retrieval -- final-push item 7. LIVE: 2 judge calls per scheme (4 in all).

    PYTHONPATH=. python scripts/run_rag_comparison.py [--budget=175000]

For the two gold schemes with a retrieval corpus (data/retrieval_corpus/: PM-KISAN's amendment
reference, secondary; MH-LADKI-BAHIN's three Marathi GRs, primary), the judge reads the same extraction
draft (the scheme's first valid k=3 sample) twice: without retrieved context, and with the
temporally-filtered retrieved context (judge_context.retrieve_context_for_judge, fitted under Groq's 8k
request ceiling -- with a real document about one Marathi chunk fits). Scored offline against the
gold's recorded supersession: did the judge propose retiring the same field, and what did the gate do?
The 2026-08-18 run of this comparison failed 4/4 with api_error (request too large); see judge_repair.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from schemelogic.deferral.calibration_gate import evaluate_gate_batch  # noqa: E402
from schemelogic.experiments import harness  # noqa: E402
from schemelogic.extraction import judge_repair  # noqa: E402
from schemelogic.schema.models import Scheme  # noqa: E402

ITEM = "rag_comparison"
OUT = harness.EXPERIMENTS_DIR / ITEM
SCHEMES = ("PM-KISAN", "MH-LADKI-BAHIN")
PROVIDER = "groq"
ESTIMATE = 8_000


def _draft(sid: str) -> tuple[Scheme, str] | None:
    for path in sorted((harness.EXPERIMENTS_DIR / "self_consistency" / sid).glob("sample_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if "draft_extraction" in payload:
            return Scheme.model_validate(payload["draft_extraction"]), path.name
    return None


def run(budget: int, judge=judge_repair.run_judge, index=None, ledger=None) -> str:
    from schemelogic.retrieval.indexer import build_index_from_directory
    from schemelogic.retrieval.judge_context import retrieve_context_for_judge

    ledger = ledger or harness.Ledger(ITEM, PROVIDER, daily_budget=budget)
    index = index or build_index_from_directory(ROOT / "data" / "retrieval_corpus")
    for sid in SCHEMES:
        found = _draft(sid)
        if found is None:
            continue
        draft, sample_name = found
        doc, sha = harness.source_document(sid)
        query = f"{sid} eligibility criteria amendment"
        context = retrieve_context_for_judge(index, query, date.today())
        for arm, ctx in (("without_retrieval", None), ("with_retrieval", context)):
            path = OUT / f"{sid}__{arm}.json"
            if path.exists():
                continue
            try:
                ledger.before_call(ESTIMATE)
            except harness.BudgetExhausted as exc:
                print(f"[stop] {exc}", flush=True)
                return "budget"
            usage: list[dict] = []
            report = judge(draft, doc, provider=PROVIDER, usage_sink=usage.append, compact_draft=True, retrieved_context=ctx)
            for u in usage:
                ledger.record(u, scheme_id=sid, arm=arm)
            fitted = None
            if ctx:
                fixed = judge_repair._judge_system_prompt() + doc + json.dumps(draft.model_dump(mode="json", by_alias=True, exclude_defaults=True))
                _, fitted = judge_repair.fit_retrieved_context(ctx, fixed)
            payload = {**harness.result_header(ITEM, PROVIDER, {"query": query, "as_of": date.today().isoformat(),
                                                               "compact_draft": True}),
                       "scheme_id": sid, "arm": arm, "draft_from": f"self_consistency/{sid}/{sample_name}",
                       "source_document_sha256": sha, "retrieved_chars": len(ctx or ""), "context_fit": fitted, "usage": usage}
            if isinstance(report, judge_repair.JudgeFailure):
                if harness.is_daily_cap(report.detail) or "rate limit" in report.detail.lower():
                    print(f"[stop] {sid} {arm}: {report.detail[:600]}", flush=True)
                    return "daily_cap" if harness.is_daily_cap(report.detail) else "rate_limited"
                payload["judge_failure"] = {"reason": report.reason, "detail": report.detail[:2000]}
            else:
                payload["findings"] = [f.model_dump(mode="json") for f in report.findings]
                payload["gate_decisions"] = [d.to_dict() for d in evaluate_gate_batch(report.findings, doc + "\n\n" + (ctx or ""))]
            OUT.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"  {sid} {arm}: {'FAILED ' + report.reason if isinstance(report, judge_repair.JudgeFailure) else len(report.findings)} "
                  f"({sum(u.get('total_tokens') or 0 for u in usage):,} tokens)", flush=True)
    return "done"


def summarize() -> dict:
    """Offline: per scheme and arm, the findings and whether the gold's recorded supersession was found."""
    rows = []
    for sid in SCHEMES:
        gold = harness.frozen_gold(sid)
        sup = gold.temporal_validity.supersedes
        target = sup.retired_predicate.get("field") if sup and isinstance(sup.retired_predicate, dict) else None
        for arm in ("without_retrieval", "with_retrieval"):
            path = OUT / f"{sid}__{arm}.json"
            if not path.exists():
                rows.append({"scheme": sid, "arm": arm, "status": "not run"})
                continue
            r = json.loads(path.read_text(encoding="utf-8"))
            temporal = [f for f in r.get("findings", []) if f.get("category") == "temporal_supersession"]
            hit = [f for f in temporal if (f.get("proposed_supersedes") or {}).get("retired_field") == target]
            decisions = {d["finding_description"]: d["decision"] for d in r.get("gate_decisions", [])}
            rows.append({"scheme": sid, "arm": arm, "status": "judge failed: " + r["judge_failure"]["reason"] if "judge_failure" in r else "ran",
                         "gold_retired_field": target, "context_fit": r.get("context_fit"),
                         "findings": len(r.get("findings", [])), "temporal_findings": len(temporal),
                         "found_gold_supersession": bool(hit),
                         "gate_on_it": decisions.get(hit[0]["description"]) if hit else None})
    return {**harness.result_header("rag_comparison_summary", "none (offline)", {}), "rows": rows}


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--summarize" in args:
        s = summarize()
        out = harness.EXPERIMENTS_DIR / f"rag_comparison_summary_{s['date']}.json"
        out.write_text(json.dumps(s, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        for row in s["rows"]:
            print(row)
        sys.exit(0)
    budget = int(next((a.split("=", 1)[1] for a in args if a.startswith("--budget=")), harness.DAILY_BUDGET))
    print(f"stopped: {run(budget)}", flush=True)
