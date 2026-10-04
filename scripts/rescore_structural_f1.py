"""Re-score structural F1 now that it scores `except` clauses (2026-10-04). Offline, no LLM calls.

    PYTHONPATH=. python scripts/rescore_structural_f1.py

For every scheme, every extraction draft on disk (ontology draft, judge+repair output, gate-approved
output) is scored four ways, so each change is visible on its own:

  old metric, audit-snapshot gold   -- what was (or would have been) reported; reproduces the records
  new metric, audit-snapshot gold   -- the metric change alone
  old metric, current gold          -- the gold fixes alone
  new metric, current gold          -- the figure to cite now

The old metric is the module as it was before the change (OLD_METRIC_REF), loaded from git, so this
stays reproducible. The audit snapshot is the gold as audited (OLD_GOLD_REF), before any 2026-10-03/04
fix. A scheme with no draft (PMMVY was never extracted) is listed with nothing to score.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from schemelogic.evaluation import structural_f1 as new_metric  # noqa: E402
from schemelogic.schema.models import Scheme  # noqa: E402

OLD_METRIC_REF = "043a8e8"  # last commit before exceptions were scored
OLD_GOLD_REF = "5662498"    # gold sourcing audit snapshot
RUNS = ROOT / "data" / "extraction_runs"
DRAFT_KEYS = {"_ontology_": "draft_extraction", "_judge_repair_": "repaired_scheme", "_gated_": "gated_extraction"}


def _git(ref: str, rel: str) -> str:
    return subprocess.check_output(["git", "show", f"{ref}:{rel}"], cwd=ROOT).decode("utf-8")


def _old_metric():
    path = Path(tempfile.mkdtemp()) / "structural_f1_old.py"
    path.write_text(_git(OLD_METRIC_REF, "schemelogic/evaluation/structural_f1.py"), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("structural_f1_old", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["structural_f1_old"] = module
    spec.loader.exec_module(module)
    return module


def _drafts(sid: str):
    for path in sorted(RUNS.glob(f"{sid}_gpt-oss-120b_*.json")):
        key = next((k for marker, k in DRAFT_KEYS.items() if marker in path.name), None)
        if key is None:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if key in payload:
            yield path.name, Scheme.model_validate(payload[key])


def _score(module, gold: Scheme, draft: Scheme) -> dict:
    result = module.compare_schemes(gold, draft)
    exc = result.category_metrics.get(getattr(module, "EXCEPTION_CATEGORY", "-"))
    return {"f1": round(result.overall.f1, 4), "tp": result.overall.tp, "fp": result.overall.fp,
            "fn": result.overall.fn, "exceptions": None if exc is None else exc.to_dict()}


def main() -> None:
    old_metric = _old_metric()
    rows, no_draft = [], []
    for sid in sorted(p.stem for p in (ROOT / "data" / "gold").glob("*.json")):
        drafts = list(_drafts(sid))
        if not drafts:
            no_draft.append(sid)
            continue
        snapshot = Scheme.model_validate_json(_git(OLD_GOLD_REF, f"data/gold/{sid}.json"))
        current = Scheme.model_validate_json((ROOT / "data" / "gold" / f"{sid}.json").read_text(encoding="utf-8"))
        for name, draft in drafts:
            rows.append({
                "scheme": sid, "draft_run": name,
                "old_metric_snapshot_gold": _score(old_metric, snapshot, draft),
                "new_metric_snapshot_gold": _score(new_metric, snapshot, draft),
                "old_metric_current_gold": _score(old_metric, current, draft),
                "new_metric_current_gold": _score(new_metric, current, draft),
            })

    out = RUNS / f"structural_f1_rescore_{date.today().isoformat()}.json"
    out.write_text(json.dumps({"old_metric_ref": OLD_METRIC_REF, "old_gold_ref": OLD_GOLD_REF,
                               "schemes_without_a_draft": no_draft, "rows": rows},
                              indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"{'scheme':15} {'draft':52} {'old/snap':>8} {'new/snap':>8} {'old/now':>8} {'new/now':>8}  exceptions now (tp/fp/fn)")
    for r in rows:
        e = r["new_metric_current_gold"]["exceptions"]
        exc = "-" if e is None else f"{e['tp']}/{e['fp']}/{e['fn']}"
        print(f"{r['scheme']:15} {r['draft_run'][:52]:52} {r['old_metric_snapshot_gold']['f1']:8.3f} "
              f"{r['new_metric_snapshot_gold']['f1']:8.3f} {r['old_metric_current_gold']['f1']:8.3f} "
              f"{r['new_metric_current_gold']['f1']:8.3f}  {exc}")
    print(f"\nno extraction draft (nothing to score): {', '.join(no_draft) or 'none'}")
    print(f"written: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
