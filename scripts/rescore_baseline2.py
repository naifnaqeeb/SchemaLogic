"""Re-score Baseline 2 against corrected gold, calling the LLM only where it has to.

LIVE for new profiles only: makes real LLM calls for profiles that have no earlier answer.

    B2_TOKEN_BUDGET=30000 PYTHONPATH=. python scripts/rescore_baseline2.py AB-PMJAY PMMVY PM-UJJWALA-2.0 IGNOAPS
    B2_TOKEN_BUDGET=60000 PYTHONPATH=. python scripts/rescore_baseline2.py AB-PMJAY --label=ab-pmjay-70plus-age
    B2_TOKEN_BUDGET=40000 PYTHONPATH=. python scripts/rescore_baseline2.py PMAY-G --label=pmay-g-updated-doc --no-reuse

Why re-scoring is sound: Baseline 2's LLM is shown the scheme DOCUMENT and the profile FACTS -- never
the gold. When the gold changes but a profile's facts don't, the LLM's answer to that profile is
exactly what it was, and only the evaluator's side of the comparison moves. Re-asking would add
sampling noise and spend quota to measure nothing new. So for each profile in the current suite:

  - its facts are byte-identical to a profile answered in an earlier run (matched by id, or through
    RENAMED for a profile renamed by a gold fix) -> reuse that answer, re-evaluate with the current
    gold, mark the row `answer_source: reused from <file>`;
  - otherwise (a new profile) -> ask the LLM, exactly as scripts/run_baseline2.py would, and mark it
    `answer_source: new_llm_call`.

Facts are compared against the profile file as it was in git at the time of the earlier run's
commit, so "identical" is checked rather than assumed. Same pacing, budget stop and TPD abort as
the main runner; token figures are estimates for the same reason.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from schemelogic.evaluation import direct_llm_baseline as dlb  # noqa: E402

_spec = importlib.util.spec_from_file_location("run_baseline2", ROOT / "scripts" / "run_baseline2.py")
rb2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rb2)

RUNS = ROOT / "data" / "extraction_runs"
TOKEN_BUDGET = int(os.environ.get("B2_TOKEN_BUDGET", "30000"))

# Profiles renamed by a gold fix, facts unchanged: current id -> id in the earlier run.
RENAMED = {("PM-UJJWALA-2.0", "non_citizen_not_excluded_by_source"): "non_citizen_ineligible"}

# The commit at which each earlier run's profiles were current (the run's own commit).
RUN_COMMIT = {
    "baseline2_direct_llm_2026-09-19.json": "262208a",
    "baseline2_direct_llm_2026-10-03.json": "0d53906",
    "baseline2_direct_llm_2026-10-04.json": "8df5080",
}


def _earlier_answers(sid: str) -> tuple[str, dict[str, dict]] | None:
    """The most recent earlier run that completed this scheme: (file, {profile_id: row})."""
    found = None
    for path in sorted(RUNS.glob("baseline2_direct_llm_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if sid not in payload.get("schemes_completed", []) or path.name not in RUN_COMMIT:
            continue
        rep = next(r for r in payload["reports"] if r["scheme_id"] == sid)
        found = (path.name, {c["profile_id"]: c for c in rep["comparisons"]})
    return found


def _facts(profile: dict) -> str:
    return json.dumps({"self": profile.get("self"), "family_members": profile.get("family_members")},
                      sort_keys=True)


def main(schemes: list[str], label: str | None = None, reuse: bool = True) -> None:
    # A second re-score on the same day must not overwrite the first: --label names it.
    out_path = RUNS / f"baseline2_direct_llm_{date.today().isoformat()}{'_' + label if label else ''}.json"
    if out_path.exists():
        raise SystemExit(f"{out_path.name} exists -- pass --label=<name> to write a separate file")
    spent = 0
    reports, completed = [], []
    stopped_reason = None

    for sid in schemes:
        doc, scheme, profiles = rb2._load(sid)
        # --no-reuse: the scheme DOCUMENT changed, so earlier answers no longer answer the same question
        earlier = _earlier_answers(sid) if reuse else None
        earlier_file, earlier_rows = earlier if earlier else (None, {})
        old_profiles = {}
        if earlier_file:
            raw = json.loads(subprocess.check_output(
                ["git", "show", f"{RUN_COMMIT[earlier_file]}:data/profiles/{sid}.json"], cwd=ROOT))
            old_profiles = {k: v for k, v in raw.items() if not k.startswith("_")}

        per_call = rb2._estimate_tokens(doc) + rb2._PER_CALL_OVERHEAD
        new_ids = [pid for pid in profiles
                   if not (RENAMED.get((sid, pid), pid) in earlier_rows
                           and RENAMED.get((sid, pid), pid) in old_profiles
                           and _facts(old_profiles[RENAMED.get((sid, pid), pid)]) == _facts(profiles[pid]))]
        projected = per_call * len(new_ids)
        if spent + projected + rb2._RECOVERY_RESERVE > TOKEN_BUDGET:
            stopped_reason = f"budget: {sid} needs ~{projected:,} for {len(new_ids)} new profiles"
            print(f"[budget] stopping before {sid}: {stopped_reason}", flush=True)
            break

        report = dlb.SchemeBaselineReport(scheme_id=sid)
        sources: dict[str, str] = {}
        print(f"\n=== {sid}: {len(profiles)} profiles, {len(profiles) - len(new_ids)} reused, "
              f"{len(new_ids)} new (~{projected:,} tok) ===", flush=True)

        for pid, profile in profiles.items():
            if pid not in new_ids:
                old_row = earlier_rows[RENAMED.get((sid, pid), pid)]
                answer = dlb.DirectAnswer(verdict=old_row["baseline_verdict"], reason=old_row["baseline_reason"])
                src = f"reused from {earlier_file}" + (
                    f" (as '{RENAMED[(sid, pid)]}')" if (sid, pid) in RENAMED else "")
            else:
                answer = None
                for attempt, cap in enumerate((None, rb2.RECOVERY_MAX_TOKENS)):
                    estimate = per_call if cap is None else per_call + cap
                    rb2._pace(estimate)
                    result = dlb.ask_direct(doc, profile, scheme_name=sid, **({} if cap is None else {"max_tokens": cap}))
                    spent += estimate
                    report.tokens_used += estimate
                    rb2._last.update(at=time.time(), tokens=estimate)
                    if isinstance(result, dlb.DirectAnswer):
                        answer = result
                        break
                    if rb2._is_daily_cap(result.detail):
                        stopped_reason = "daily token cap (TPD) reached"
                        break
                    if attempt == 0 and rb2._is_truncation(result.detail):
                        continue
                    report.failures.append(f"{pid}: {result.detail[:200]}")
                    break
                src = "new_llm_call"
                if stopped_reason:
                    print(f"  [ABORT] {stopped_reason}", flush=True)
                    break
                if answer is None:
                    print(f"  {pid:46} FAILURE {report.failures[-1][:90]}", flush=True)
                    continue

            c = dlb.compare_profile(scheme, pid, profile, answer)
            report.comparisons.append(c)
            sources[pid] = src
            flag = "" if c.relation == "agree" else f"  <-- {c.relation}"
            tag = "NEW " if src == "new_llm_call" else "    "
            print(f"  {tag}{pid:46} llm={c.baseline_verdict:11} eval={c.evaluator_verdict:26}{flag}", flush=True)

        d = report.to_dict()
        for row in d["comparisons"]:
            row["answer_source"] = sources[row["profile_id"]]
        reports.append(d)
        if stopped_reason:
            break
        completed.append(sid)

    payload = {
        "run": "baseline2_direct_llm (re-scored against corrected gold)",
        "date": date.today().isoformat(),
        "methodology_module": "schemelogic/evaluation/direct_llm_baseline.py",
        "rescoring": ("Answers reused verbatim wherever a profile's facts are byte-identical to an earlier "
                      "run's (the LLM never sees the gold); only new profiles were asked. See answer_source."),
        "gold_fixes": "docs/GOLD_AUDIT_2026-10-03.md section 6",
        "label": label,
        "token_budget": TOKEN_BUDGET,
        "tokens_spent_estimated": spent,
        "token_note": "ESTIMATED from document size; ProviderResult does not surface usage.",
        "schemes_completed": completed,
        "schemes_not_attempted": [s for s in schemes if s not in completed],
        "stopped_reason": stopped_reason,
        "reports": reports,
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nnew LLM calls' tokens (estimated): {spent:,} / {TOKEN_BUDGET:,}")
    print(f"completed: {completed}  stopped: {stopped_reason}")
    print(f"output: {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    labels = [a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--label=")]
    main([a for a in sys.argv[1:] if not a.startswith("-")], labels[0] if labels else None,
         reuse="--no-reuse" not in sys.argv[1:])
