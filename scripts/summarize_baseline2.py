"""Aggregate every Baseline 2 run on disk into one per-scheme + overall report.

Offline: reads data/extraction_runs/baseline2_direct_llm_*.json, makes no LLM calls.

    PYTHONPATH=. python scripts/summarize_baseline2.py

Beyond the agreement / harmful-positive / false-negative rates, this answers the question the first
run left open: is the IGNOAPS failure -- the LLM answering "eligible" for a profile whose deciding
fact is MISSING, where the evaluator returns undetermined_missing_facts -- a general behaviour, or
one scheme's anecdote? It does that by examining EVERY profile on which the evaluator returned
undetermined, across all schemes, rather than only the disagreements: the denominator is "times
the rules said they could not decide", and the question is how often the LLM decided anyway.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from schemelogic.evaluation.direct_llm_baseline import HARMFUL_POSITIVE  # noqa: E402

UNDETERMINED = "undetermined_missing_facts"

# Rows whose GOLD verdict is itself in question, reported both with and without them rather than
# silently kept or silently dropped. Each entry must point at the KNOWN_ISSUES.md entry explaining
# it -- this is not a place to quietly discard results that look bad.
CONTESTED: set[tuple[str, str]] = set()
# Was {("PM-UJJWALA-2.0", "non_citizen_ineligible")} until 2026-10-03, when the gold's unsourced
# is_indian_citizen predicate was removed (docs/GOLD_AUDIT_2026-10-03.md section 6.3) and the profile
# renamed non_citizen_not_excluded_by_source. The row is no longer contested: the gold it is scored
# against is now sourced. The mechanism stays for the next case.


def load_reports() -> dict[str, dict]:
    """scheme_id -> report. If a scheme appears in more than one run, the latest file wins."""
    by_scheme: dict[str, dict] = {}
    for path in sorted((ROOT / "data" / "extraction_runs").glob("baseline2_direct_llm_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        completed = set(payload.get("schemes_completed", []))
        for report in payload.get("reports", []):
            if report["scheme_id"] in completed:
                report["_source"] = path.name
                by_scheme[report["scheme_id"]] = report
    return by_scheme


def pct(a: int, b: int) -> str:
    return f"{100 * a / b:5.1f}%" if b else "   n/a"


def main() -> None:
    reports = load_reports()
    if not reports:
        print("no completed Baseline 2 runs on disk")
        return

    print(f"{'scheme':16} {'n':>3} {'agree':>7} {'harmful+':>9} {'false-':>7} {'over-':>7}  source")
    print(f"{'':16} {'':>3} {'':>7} {'positive':>9} {'neg':>7} {'caution':>7}")
    print("-" * 78)
    all_rows: list[tuple[str, dict]] = []
    for scheme_id in sorted(reports):
        r = reports[scheme_id]
        rows = r["comparisons"]
        all_rows.extend((scheme_id, c) for c in rows)
        n = len(rows)
        rel = Counter(c["relation"] for c in rows)
        harmful = sum(rel[h] for h in HARMFUL_POSITIVE)
        print(f"{scheme_id:16} {n:3} {pct(rel['agree'], n):>7} {pct(harmful, n):>9} "
              f"{pct(rel['false_negative'], n):>7} {pct(rel['over_cautious'], n):>7}  {r['_source']}")

    n = len(all_rows)
    rel = Counter(c["relation"] for _, c in all_rows)
    harmful = sum(rel[h] for h in HARMFUL_POSITIVE)
    print("-" * 78)
    print(f"{'AGGREGATE':16} {n:3} {pct(rel['agree'], n):>7} {pct(harmful, n):>9} "
          f"{pct(rel['false_negative'], n):>7} {pct(rel['over_cautious'], n):>7}")
    clean = [(s, c) for s, c in all_rows if (s, c["profile_id"]) not in CONTESTED]
    if len(clean) != n:
        cn = len(clean)
        crel = Counter(c["relation"] for _, c in clean)
        charm = sum(crel[h] for h in HARMFUL_POSITIVE)
        print(f"{'excl. contested':16} {cn:3} {pct(crel['agree'], cn):>7} {pct(charm, cn):>9} "
              f"{pct(crel['false_negative'], cn):>7} {pct(crel['over_cautious'], cn):>7}  "
              f"({n - cn} row(s) whose gold verdict is itself in question -- see KNOWN_ISSUES.md)")
    print(f"\nfull breakdown: {dict(rel)}")

    print("\n=== every disagreement ===")
    for scheme_id, c in all_rows:
        if c["relation"] != "agree":
            contested = "  [CONTESTED GOLD]" if (scheme_id, c["profile_id"]) in CONTESTED else ""
            print(f"  [{scheme_id}] {c['profile_id']}: llm={c['baseline_verdict']} "
                  f"eval={c['evaluator_verdict']} -> {c['relation']}{contested}")
            print(f"      reason: {c['baseline_reason'][:200]}")

    # The key question: when the rules say "can't decide, a fact is missing", what does the LLM do?
    print("\n=== silent default on missing information: every profile the evaluator marked undetermined ===")
    undetermined = [(s, c) for s, c in all_rows if c["evaluator_verdict"] == UNDETERMINED]
    llm_said = Counter(c["baseline_verdict"] for _, c in undetermined)
    for scheme_id, c in undetermined:
        verdict = c["baseline_verdict"]
        tag = {"eligible": "SILENT DEFAULT (harmful)", "unsure": "deferred correctly",
               "ineligible": "decided against (not harmful, still wrong)"}.get(verdict, verdict)
        print(f"  [{scheme_id:16}] {c['profile_id']:46} llm={verdict:10} {tag}")
    m = len(undetermined)
    print(f"\n  rules could not decide on {m} profiles across {len({s for s, _ in undetermined})} schemes")
    print(f"  LLM deferred ('unsure')        : {llm_said['unsure']}/{m} {pct(llm_said['unsure'], m)}")
    print(f"  LLM said ELIGIBLE anyway       : {llm_said['eligible']}/{m} {pct(llm_said['eligible'], m)}")
    print(f"  LLM said ineligible anyway     : {llm_said['ineligible']}/{m} {pct(llm_said['ineligible'], m)}")
    silent = sorted({s for s, c in undetermined if c["baseline_verdict"] == "eligible"})
    print(f"  schemes where the silent default occurred: {silent or 'none'}")

    sources = Counter(
        "new LLM call" if c.get("answer_source") == "new_llm_call"
        else ("reused (re-scored against corrected gold)" if c.get("answer_source") else "original run")
        for _, c in all_rows
    )
    print(f"\nwhere each answer came from: {dict(sources)}")

    recovered = sum(1 for _, c in all_rows if c.get("recovered_with_higher_max_tokens"))
    print(f"\nrows recovered from json_validate_failed at a higher completion cap: {recovered}")
    failures = [(s, f) for s, r in reports.items() for f in r.get("failures", [])]
    if failures:
        print("unrecovered failures (excluded from all rates above):")
        for s, f in failures:
            print(f"  [{s}] {f[:150]}")


if __name__ == "__main__":
    main()
