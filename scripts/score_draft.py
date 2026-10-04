"""Score extraction drafts against the current gold: outcome equivalence and structural F1. Offline.

    PYTHONPATH=. python scripts/score_draft.py <run.json> [<run.json> ...] --out=<name>

Each run file is a data/extraction_runs/ file holding `draft_extraction`, `gated_extraction` or
`repaired_scheme`. Writes data/extraction_runs/<name>.json with every figure and disagreement, so a
comparison quoted in the audit doc can be regenerated.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from schemelogic.evaluation.outcome_equivalence import evaluate_outcome_equivalence  # noqa: E402
from schemelogic.evaluation.structural_f1 import compare_schemes  # noqa: E402
from schemelogic.schema.models import Scheme  # noqa: E402

RUNS = ROOT / "data" / "extraction_runs"


def score(run_name: str) -> dict:
    payload = json.loads((RUNS / run_name).read_text(encoding="utf-8"))
    key = next(k for k in ("gated_extraction", "repaired_scheme", "draft_extraction") if k in payload)
    draft = Scheme.model_validate(payload[key])
    sid = payload.get("scheme_id") or run_name.split("_")[0]
    gold = Scheme.model_validate_json((ROOT / "data" / "gold" / f"{sid}.json").read_text(encoding="utf-8"))
    raw = json.loads((ROOT / "data" / "profiles" / f"{sid}.json").read_text(encoding="utf-8"))
    oe = evaluate_outcome_equivalence(gold, draft, {k: v for k, v in raw.items() if not k.startswith("_")}).to_dict()
    f1 = compare_schemes(gold, draft).to_dict()
    return {
        "run": run_name, "scheme_id": sid, "source_document_sha256": payload.get("source_document_sha256"),
        "outcome_equivalence": {k: oe[k] for k in ("n_profiles", "agreement_rate", "false_positive_eligible_rate",
                                                     "false_negative_eligible_rate", "other_mismatch_rate")},
        "disagreements": [c for c in oe["comparisons"] if not c["agree"]],
        "structural_f1": f1["overall"],
        "structural_diff": {k: f1[k] for k in ("inclusion_diff", "exclusion_diff", "exception_diff")},
    }


def main(runs: list[str], out_name: str) -> None:
    rows = [score(r) for r in runs]
    (RUNS / f"{out_name}.json").write_text(json.dumps({"rows": rows}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for r in rows:
        oe = r["outcome_equivalence"]
        print(f"{r['run'][:62]:62} agree {oe['agreement_rate']:.1%}  FP {oe['false_positive_eligible_rate']:.1%}  "
              f"FN {oe['false_negative_eligible_rate']:.1%}  F1 {r['structural_f1']['f1']:.3f}")
    print(f"written: data/extraction_runs/{out_name}.json")


if __name__ == "__main__":
    outs = [a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--out=")]
    main([a for a in sys.argv[1:] if not a.startswith("-")], outs[0] if outs else "draft_scores")
