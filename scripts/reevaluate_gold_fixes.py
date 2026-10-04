"""Re-derive every outcome-equivalence and structural-F1 figure the 2026-10-03 gold fixes affect.

Offline: no LLM calls. The extraction drafts are the ones already on disk in data/extraction_runs/;
only the gold rules and the profile suites they're judged against have changed.

    PYTHONPATH=. python scripts/reevaluate_gold_fixes.py
    PYTHONPATH=. python scripts/reevaluate_gold_fixes.py --old-ref <commit> --only AB-PMJAY

`--old-ref` sets the "before" snapshot (default OLD_REF, the audit snapshot); `--only` limits the
run to one scheme. A later fix is compared against the gold just before it, e.g. AB-PMJAY's 70+
re-encoding (2026-10-04) against the commit preceding it.

For each previously reported figure this:
  1. reads the figure as it was RECORDED at the time;
  2. REPRODUCES it from the pre-fix gold and profiles, read out of git at OLD_REF -- if that doesn't
     match the recording, the re-run method can't be trusted for that row and the row says so,
     instead of silently comparing against a number it didn't regenerate;
  3. computes the CORRECTED figure from the current gold and profiles, same draft, same functions.

Structural F1 note: evaluation/structural_f1.py matches exclusions on (location, field, op, value,
quantifier) and never scores `except` clauses at all, so a fix that only adds exceptions -- AB-PMJAY's
-- cannot move it. That is a pre-existing gap in the metric, recorded in the audit doc, not something
this script works around.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from schemelogic.evaluation.outcome_equivalence import evaluate_outcome_equivalence  # noqa: E402
from schemelogic.evaluation.structural_f1 import compare_schemes  # noqa: E402
from schemelogic.schema.models import Scheme  # noqa: E402

OLD_REF = "5662498"  # gold sourcing audit snapshot: gold and profiles exactly as audited, pre-fix
RUNS = ROOT / "data" / "extraction_runs"

# (scheme, what the figure was, draft run file, key holding the draft, file the figure was recorded in)
FIGURES = [
    ("AB-PMJAY", "Phase 3 check-in, gate-approved draft",
     "AB-PMJAY_gpt-oss-120b_gated_20260818T025520.json", "gated_extraction",
     "AB-PMJAY_phase3_checkin_20260818T025948.json"),
    ("PM-UJJWALA-2.0", "Phase 3 check-in, gate-approved draft",
     "PM-UJJWALA-2.0_gpt-oss-120b_gated_20260818T033601.json", "gated_extraction",
     "PM-UJJWALA-2.0_phase3_checkin_20260818T033654.json"),
    ("IGNOAPS", "outcome equivalence, ontology draft (pre-repair)",
     "IGNOAPS_gpt-oss-120b_ontology_20260818T012625.json", "draft_extraction",
     "IGNOAPS_gpt-oss-120b_outcome_equivalence_20260818T013510.json"),
    ("IGNOAPS", "outcome equivalence, post judge+repair",
     "IGNOAPS_gpt-oss-120b_judge_repair_20260818T015010.json", "repaired_scheme",
     "IGNOAPS_gpt-oss-120b_post_repair_outcome_equivalence_20260818T015448.json"),
]


def _git_json(ref: str, rel: str) -> dict:
    return json.loads(subprocess.check_output(["git", "show", f"{ref}:{rel}"], cwd=ROOT))


def _profiles(raw: dict) -> dict:
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def _oe(report) -> dict:
    d = report.to_dict()
    return {k: d[k] for k in ("n_profiles", "agreement_rate", "false_positive_eligible_rate",
                              "false_negative_eligible_rate", "other_mismatch_rate")}


def _recorded(rec: dict) -> tuple[dict | None, dict | None]:
    oe = rec.get("outcome_equivalence") or rec.get("report")
    sf = rec.get("structural_f1")
    oe = {k: oe[k] for k in ("n_profiles", "agreement_rate", "false_positive_eligible_rate",
                             "false_negative_eligible_rate", "other_mismatch_rate")} if oe else None
    f1 = sf["overall"]["f1"] if sf else None
    return oe, f1


def _close(a: dict | None, b: dict | None) -> bool:
    if a is None or b is None:
        return False
    return all(abs(float(a[k]) - float(b[k])) < 1e-9 for k in a)


def main(old_ref: str = OLD_REF, only: str | None = None) -> None:
    rows = []
    for sid, what, draft_file, key, rec_file in FIGURES:
        if only and sid != only:
            continue
        draft = Scheme.model_validate(json.loads((RUNS / draft_file).read_text(encoding="utf-8"))[key])
        rec_oe, rec_f1 = _recorded(json.loads((RUNS / rec_file).read_text(encoding="utf-8")))

        old_gold = Scheme.model_validate(_git_json(old_ref, f"data/gold/{sid}.json"))
        old_prof = _profiles(_git_json(old_ref, f"data/profiles/{sid}.json"))
        new_gold = Scheme.model_validate(json.loads((ROOT / "data" / "gold" / f"{sid}.json").read_text(encoding="utf-8")))
        new_prof = _profiles(json.loads((ROOT / "data" / "profiles" / f"{sid}.json").read_text(encoding="utf-8")))

        old_oe = _oe(evaluate_outcome_equivalence(old_gold, draft, old_prof))
        new_report = evaluate_outcome_equivalence(new_gold, draft, new_prof)
        new_oe = _oe(new_report)
        old_f1 = compare_schemes(old_gold, draft).overall.f1
        new_f1 = compare_schemes(new_gold, draft).overall.f1

        rows.append({
            "scheme": sid, "figure": what, "draft_run": draft_file, "recorded_in": rec_file,
            "outcome_equivalence": {
                "recorded": rec_oe, "reproduced_pre_fix": old_oe,
                "reproduced_matches_recorded": _close(rec_oe, old_oe), "corrected": new_oe,
            },
            "structural_f1": {
                "recorded": rec_f1, "reproduced_pre_fix": old_f1,
                # Recorded F1 values were stored rounded to 4 decimal places (e.g. 0.963 for
                # 0.96296...), so "reproduced" means equal at that precision.
                "reproduced_matches_recorded": rec_f1 is not None and abs(rec_f1 - old_f1) < 5e-5,
                "corrected": new_f1,
            },
            "corrected_disagreements": [
                c for c in new_report.to_dict()["comparisons"] if not c["agree"]
            ],
        })

    suffix = "" if old_ref == OLD_REF and only is None else f"_{only or 'all'}_vs_{old_ref}"
    out = RUNS / f"gold_fix_reevaluation_{date.today().isoformat()}{suffix}.json"
    out.write_text(json.dumps({"old_ref": old_ref, "rows": rows}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def pct(x):
        return "—" if x is None else f"{100 * x:.1f}%"

    print("OUTCOME EQUIVALENCE (gold vs extraction draft, same evaluator)")
    print(f"{'scheme':16} {'figure':48} {'recorded':>9} {'reproduced':>11} {'match':>6} {'CORRECTED':>10}  n old->new   fp old->new")
    for r in rows:
        oe = r["outcome_equivalence"]
        rec, rep, new = oe["recorded"], oe["reproduced_pre_fix"], oe["corrected"]
        print(f"{r['scheme']:16} {r['figure']:48} {pct(rec and rec['agreement_rate']):>9} "
              f"{pct(rep['agreement_rate']):>11} {'yes' if oe['reproduced_matches_recorded'] else 'NO':>6} "
              f"{pct(new['agreement_rate']):>10}  {rep['n_profiles']:>3}->{new['n_profiles']:<3}   "
              f"{pct(rep['false_positive_eligible_rate'])}->{pct(new['false_positive_eligible_rate'])}")
    print("\nSTRUCTURAL F1 (overall)")
    for r in rows:
        sf = r["structural_f1"]
        rec = "—" if sf["recorded"] is None else f"{sf['recorded']:.3f}"
        print(f"{r['scheme']:16} {r['figure']:48} recorded={rec:>6} reproduced={sf['reproduced_pre_fix']:.3f} "
              f"match={'yes' if sf['reproduced_matches_recorded'] else ('n/a' if sf['recorded'] is None else 'NO')} "
              f"CORRECTED={sf['corrected']:.3f}")
    print(f"\nwritten: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--old-ref", default=OLD_REF)
    parser.add_argument("--only", default=None)
    args = parser.parse_args()
    main(args.old_ref, args.only)
