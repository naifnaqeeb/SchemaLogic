"""One aggregate report across all 7 gold schemes -- final-push item 1. Offline: no LLM calls.

    PYTHONPATH=. python scripts/run_batch_report.py

Scores every extraction CONFIGURATION on disk against the FROZEN gold (tag gold-v2) and its profile
suites, scheme by scheme and in aggregate:

  - structural F1 (overall and per category, exceptions included -- evaluation/structural_f1.py)
  - outcome equivalence (the same evaluator on the gold and on the draft, over the profile suites)
  - scalar checks (unit_of_eligibility, valid_from -- evaluation/scalar_fields.py)
  - Baseline 2 (direct LLM answering): stored answers re-scored against frozen gold, each used only if
    the profile facts it was asked about are the frozen profile's facts

Configurations are discovered, not hard-coded per scheme (CONFIGURATIONS below); a configuration with
no file for a scheme is reported as absent, never filled in. Later items (Baseline 1, the k=3 samples)
plug in by adding an entry. Writes data/experiments/batch_report_<date>.json and
docs/results/BATCH_REPORT.md, each with the caveats and the superseded-claims list built in.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from schemelogic.evaluation import direct_llm_baseline as dlb  # noqa: E402
from schemelogic.evaluation.outcome_equivalence import evaluate_outcome_equivalence  # noqa: E402
from schemelogic.evaluation.scalar_fields import check_scalar_fields  # noqa: E402
from schemelogic.evaluation.structural_f1 import CategoryMetrics, compare_schemes  # noqa: E402
from schemelogic.evaluator.symbolic_engine import evaluate  # noqa: E402
from schemelogic.experiments import harness  # noqa: E402
from schemelogic.schema.models import Scheme  # noqa: E402

RUNS = ROOT / "data" / "extraction_runs"
EXP = harness.EXPERIMENTS_DIR
DRAFT_KEYS = ("gated_extraction", "repaired_scheme", "draft_extraction")

CAVEATS = [
    "ONTOLOGY CONTAMINATION. The field ontology the extractor is constrained to was built from these same 7 "
    "gold schemes (each field lists the schemes it was made for), and the extraction prompt names those "
    "fields. Field-name agreement with gold is therefore optimistic: a structural F1 here measures "
    "extraction into a vocabulary designed around the answer, not open-world extraction. The AI-Checked "
    "tier (schemes outside the gold set) is the only evidence on unseen schemes.",
    "SYNTHETIC PROFILES. The profile suites were written by the gold annotator to exercise the rules they "
    "encoded, so outcome equivalence tests the scenarios someone already thought of. A rule nobody wrote a "
    "profile for cannot disagree.",
    "SMALL SAMPLES. 7 schemes, 8-14 profiles each. One profile moves a scheme's rate by 7-12 points; "
    "directions are more trustworthy than magnitudes.",
    "SHARED SOURCES. Gold, drafts and the direct-LLM baseline mostly read the same source documents. "
    "Agreement can mean they share a source's error (the PMAY-G stale-document case, audit doc s7.9).",
    "FROZEN GOLD. Everything is scored against tag gold-v2. Open findings of the 2026-10-04 independent "
    "gold review are part of that gold, unfixed; a draft that 'disagrees' may be right.",
]


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT).decode("utf-8")


def _draft(path: Path) -> Scheme | None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    key = next((k for k in DRAFT_KEYS if k in payload), None)
    return Scheme.model_validate(payload[key]) if key else None


def _phase3(sid: str) -> Path | None:
    """The 2026-08 pipeline output: gate-approved, else judge+repair, else plain extraction."""
    for kind in ("gated", "judge_repair", "ontology"):
        files = sorted(p for p in RUNS.glob(f"{sid}_gpt-oss-120b_{kind}_2026081*.json") if _draft(p) is not None)
        if files:
            return files[-1]
    return None


def _sample(i: int) -> Callable[[str], Path | None]:
    def find(sid: str) -> Path | None:
        path = EXP / "self_consistency" / sid / f"sample_{i}.json"
        return path if path.exists() and _draft(path) is not None else None
    return find


def _latest(pattern: str) -> Callable[[str], Path | None]:
    def find(sid: str) -> Path | None:
        files = sorted(EXP.glob(pattern.format(sid=sid)))
        files = [f for f in files if _draft(f) is not None]
        return files[-1] if files else None
    return find


# name -> (description, finder: scheme_id -> draft file or None)
CONFIGURATIONS: dict[str, tuple[str, Callable[[str], Path | None]]] = {
    "phase3_pipeline": ("2026-08 Phase 3 pipeline: extraction -> judge+repair -> gate (latest stage on disk)", _phase3),
    "baseline3_extraction_only": ("Baseline 3: one extraction, no judge or repair (k=3 run, sample 1)", _sample(1)),
    "baseline1_flat": ("Baseline 1: flat attribute extraction, no compositional logic", _latest("baseline1/{sid}.json")),
}


def _score(gold: Scheme, profiles: dict, draft: Scheme) -> dict:
    f1 = compare_schemes(gold, draft)
    oe = evaluate_outcome_equivalence(gold, draft, profiles).to_dict()
    sc = check_scalar_fields(gold, draft).to_dict()
    return {
        "structural_f1": f1.overall.to_dict(),
        "f1_by_category": {k: v.to_dict() for k, v in f1.category_metrics.items()},
        "outcome_equivalence": {k: oe[k] for k in ("n_profiles", "agreement_rate", "false_positive_eligible_rate",
                                                     "false_negative_eligible_rate", "other_mismatch_rate")},
        "outcome_disagreements": [c for c in oe["comparisons"] if not c["agree"]],
        "scalar": sc,
    }


def _facts(profile: dict) -> str:
    return json.dumps({"self": profile.get("self"), "family_members": profile.get("family_members")}, sort_keys=True)


def baseline2(sid: str, gold: Scheme, profiles: dict) -> dict | None:
    """The latest stored Baseline 2 answers for this scheme, re-scored against frozen gold."""
    latest = None
    for path in sorted(RUNS.glob("baseline2_direct_llm_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if sid in payload.get("schemes_completed", []):
            latest = (path, next(r for r in payload["reports"] if r["scheme_id"] == sid))
    if latest is None:
        return None
    path, report = latest
    added = _git("log", "--diff-filter=A", "--format=%h", "--", str(path.relative_to(ROOT))).split()
    asked = {}
    if added:
        raw = json.loads(_git("show", f"{added[-1]}:data/profiles/{sid}.json"))
        asked = {k: v for k, v in raw.items() if not k.startswith("_")}
    counts, stale, rows = Counter(), [], []
    for row in report["comparisons"]:
        pid = row["profile_id"]
        if pid not in profiles or pid not in asked or _facts(asked[pid]) != _facts(profiles[pid]):
            stale.append(pid)
            continue
        truth = evaluate(gold, profiles[pid]).verdict
        relation = dlb.classify(row["baseline_verdict"], truth)
        counts[relation] += 1
        rows.append({"profile_id": pid, "baseline": row["baseline_verdict"], "evaluator": truth.value, "relation": relation})
    n = sum(counts.values())
    return {
        "source": path.name, "n": n, "counts": dict(counts), "stale_excluded": stale,
        "agreement_rate": counts["agree"] / n if n else None,
        "harmful_false_positive_rate": counts["false_positive_vs_ineligible"] / n if n else None,
        "false_negative_rate": counts["false_negative"] / n if n else None,
        "disagreements": [r for r in rows if r["relation"] != "agree"],
    }


def _two_column_rows(section: str, header: str) -> list[dict]:
    rows, started = [], False
    for line in section.splitlines():
        if not line.startswith("|"):
            if started:
                break
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells[0] == header:
            started = True
            continue
        if started and len(cells) == 2 and not set(cells[0]) <= set("-"):
            rows.append({"claim": cells[0], "status": cells[1]})
    return rows


def superseded_claims() -> list[dict]:
    """The audit doc's superseded-claims tables (s7.4, and s7.8's structural-F1 table), read live so the
    report can't drift from them."""
    text = (ROOT / "docs" / "GOLD_AUDIT_2026-10-03.md").read_text(encoding="utf-8")
    s74 = text[text.index("### 7.4 Superseded claims"): text.index("### 7.5")]
    s78 = text[text.index("### 7.8 Structural F1 now scores exceptions"):]
    s78 = s78[s78.index("**Superseded structural F1 figures**"):]
    return _two_column_rows(s74, "Earlier claim") + _two_column_rows(s78, "Recorded")


def _aggregate(per_scheme: dict[str, dict]) -> dict:
    total = CategoryMetrics(category="__overall__")
    oe_n = agree = fp = fn = 0
    for r in per_scheme.values():
        f = r["structural_f1"]
        total.tp, total.fp, total.fn = total.tp + f["tp"], total.fp + f["fp"], total.fn + f["fn"]
        o = r["outcome_equivalence"]
        oe_n += o["n_profiles"]
        agree += round(o["agreement_rate"] * o["n_profiles"])
        fp += round(o["false_positive_eligible_rate"] * o["n_profiles"])
        fn += round(o["false_negative_eligible_rate"] * o["n_profiles"])
    return {"schemes": len(per_scheme), "structural_f1_micro": total.to_dict(),
            "outcome_equivalence": {"n_profiles": oe_n, "agreement_rate": agree / oe_n if oe_n else None,
                                    "false_positive_eligible_rate": fp / oe_n if oe_n else None,
                                    "false_negative_eligible_rate": fn / oe_n if oe_n else None}}


def build() -> dict:
    schemes = harness.gold_scheme_ids()
    report = {**harness.result_header("batch_report", provider="none (offline)", config={
        "configurations": {k: v[0] for k, v in CONFIGURATIONS.items()}}), "caveats": CAVEATS,
              "configurations": {}, "baseline2": {}, "superseded_claims": superseded_claims()}
    gold = {s: harness.frozen_gold(s) for s in schemes}
    profiles = {s: harness.frozen_profiles(s) for s in schemes}
    for name, (description, find) in CONFIGURATIONS.items():
        per_scheme, absent = {}, []
        for sid in schemes:
            path = find(sid)
            if path is None:
                absent.append(sid)
                continue
            per_scheme[sid] = {"draft_file": str(path.relative_to(ROOT)), **_score(gold[sid], profiles[sid], _draft(path))}
        report["configurations"][name] = {"description": description, "absent": absent, "per_scheme": per_scheme,
                                          "aggregate": _aggregate(per_scheme) if per_scheme else None}
    for sid in schemes:
        report["baseline2"][sid] = baseline2(sid, gold[sid], profiles[sid])
    return report


def _pct(x) -> str:
    return "—" if x is None else f"{100 * x:.1f}%"


def markdown(report: dict) -> str:
    lines = ["# Batch report — all gold schemes", "",
             f"*Generated {report['created_at']} by `scripts/run_batch_report.py` from code `{report['code_commit']}`, "
             f"against frozen gold `{report['gold_tag']}` (`{report['gold_commit'][:7]}`). Offline: no LLM calls. "
             "Regenerate rather than edit.*", "", "## Caveats — read first", ""]
    lines += [f"{i}. {c}" for i, c in enumerate(report["caveats"], 1)]
    for name, cfg in report["configurations"].items():
        lines += ["", f"## {name}", "", cfg["description"] + ".", ""]
        if not cfg["per_scheme"]:
            lines += [f"*No results yet (absent for all {len(cfg['absent'])} schemes).*"]
            continue
        lines += ["| Scheme | Structural F1 | Exceptions F1 | Outcome agreement | FP (eligible) | FN (eligible) | n | Scalar | Draft |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for sid, r in cfg["per_scheme"].items():
            exc = r["f1_by_category"].get("exception_to_exclusion")
            o, s = r["outcome_equivalence"], r["scalar"]
            lines.append(f"| {sid} | {r['structural_f1']['f1']:.3f} | {'—' if exc is None else format(exc['f1'], '.3f')} | "
                         f"{_pct(o['agreement_rate'])} | {_pct(o['false_positive_eligible_rate'])} | "
                         f"{_pct(o['false_negative_eligible_rate'])} | {o['n_profiles']} | {s['n_matched']}/{s['n_checked']} | "
                         f"`{Path(r['draft_file']).name}` |")
        a = cfg["aggregate"]
        lines.append(f"| **All ({a['schemes']})** | **{a['structural_f1_micro']['f1']:.3f}** (micro) | | "
                     f"**{_pct(a['outcome_equivalence']['agreement_rate'])}** | {_pct(a['outcome_equivalence']['false_positive_eligible_rate'])} | "
                     f"{_pct(a['outcome_equivalence']['false_negative_eligible_rate'])} | {a['outcome_equivalence']['n_profiles']} | | |")
        if cfg["absent"]:
            lines.append(f"\nAbsent: {', '.join(cfg['absent'])}.")
    lines += ["", "## Baseline 2 — direct LLM answering, re-scored against frozen gold", "",
              "| Scheme | n | Agreement | Harmful FP | FN | Stale answers excluded | Answers from |", "|---|---|---|---|---|---|---|"]
    tot = Counter()
    for sid, b in report["baseline2"].items():
        if b is None:
            lines.append(f"| {sid} | — | — | — | — | — | no run |")
            continue
        tot.update(b["counts"])
        lines.append(f"| {sid} | {b['n']} | {_pct(b['agreement_rate'])} | {_pct(b['harmful_false_positive_rate'])} | "
                     f"{_pct(b['false_negative_rate'])} | {len(b['stale_excluded'])} | `{b['source']}` |")
    n = sum(tot.values())
    if n:
        lines.append(f"| **All** | **{n}** | **{_pct(tot['agree'] / n)}** | **{_pct(tot['false_positive_vs_ineligible'] / n)}** | "
                     f"**{_pct(tot['false_negative'] / n)}** | | |")
    lines += ["", "## Superseded claims (from the audit doc, s7.4) — do not cite the left column", "",
              "| Earlier claim | Status |", "|---|---|"]
    lines += [f"| {r['claim']} | {r['status']} |" for r in report["superseded_claims"]]
    return "\n".join(lines) + "\n"


def main() -> None:
    report = build()
    out = EXP / f"batch_report_{report['date']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    md = ROOT / "docs" / "results" / "BATCH_REPORT.md"
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(markdown(report), encoding="utf-8")
    print(f"written: {out.relative_to(ROOT)}, {md.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
