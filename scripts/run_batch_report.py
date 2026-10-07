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


def _code(failure: dict) -> str:
    detail = failure.get("detail", "")
    return next((c for c in ("json_validate_failed", "request too large", "rate limit") if c in detail.lower()), failure.get("reason", ""))


def _cause(failure: dict, estimate: dict | None) -> str:
    """One attempt's failure in words."""
    code = _code(failure)
    if code == "json_validate_failed":
        size = (f"the prompt is about {estimate['prompt_tokens_estimate']:,} tokens (conservative estimate) of Groq's "
                f"{estimate['request_limit']:,}-token per-request limit for prompt plus answer, " if estimate else "")
        return f"json_validate_failed, no output: {size}and the model spent what was left for the answer on reasoning before any JSON"
    if code == "schema_validation_failed":
        lines = [ln.strip() for ln in failure.get("detail", "").splitlines()]
        where = next((ln for ln in lines if re.match(r"\w+(\.\w+)+$", ln)), "")
        what = next((ln.split("[")[0].strip() for ln in lines if ln.startswith("Input should")), "")
        return ("schema_validation_failed: an answer was produced but did not match the judge's format"
                + (f" ({where}: {what.lower()})" if where else ""))
    return code


def _failure(path: Path) -> str | None:
    """Why a pipeline run produced no repaired scheme (a failed judge call), or None. A failed run is a
    failed run: never scored as if the judge had found nothing (2026-10-06). Every attempt is listed
    with its setting and its own cause -- retries can fail differently from the first call."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    f = payload.get("judge_failure")
    if not f:
        return None
    tried = payload.get("retry_settings") or (["max_tokens_2000"] if payload.get("retried_with_max_tokens") else [])
    attempts = [a.get("judge_failure") or {} for a in payload.get("failed_attempts", [])] + [f]
    settings = ["default settings"] + [SETTING_LABEL.get(s, s) for s in tried]
    est = payload.get("request_estimate")
    if len(attempts) == 1:
        return f"judge call failed ({_cause(f, est)})"
    groups: list[tuple[list[str], str]] = []  # consecutive attempts with the same cause, merged
    for i, a in enumerate(attempts):
        label, cause = settings[i] if i < len(settings) else f"attempt {i + 1}", _cause(a, est)
        if groups and groups[-1][1] == cause:
            groups[-1][0].append(label)
        else:
            groups.append(([label], cause))
    return f"judge call failed on all {len(attempts)} attempts — " + "; ".join(f"{' and '.join(ls)}: {c}" for ls, c in groups)


SETTING_LABEL = {"max_tokens_2000": "max_tokens=2000", "reasoning_low": "reasoning_effort=low"}


def _setting(path: Path) -> str | None:
    """The non-default judge setting a pipeline result came from (a retry), e.g. "reasoning_effort=low"."""
    s = json.loads(path.read_text(encoding="utf-8")).get("judge_setting") or {}
    return ", ".join(f"{k}={v}" for k, v in s.items()) or None


def _applied(path: Path) -> int | None:
    decisions = json.loads(path.read_text(encoding="utf-8")).get("gate_decisions")
    return None if decisions is None else sum(d.get("decision") == "auto_accept" for d in decisions)


def _latest(pattern: str) -> Callable[[str], Path | None]:
    def find(sid: str) -> Path | None:
        files = sorted(EXP.glob(pattern.format(sid=sid)))
        files = [f for f in files if _draft(f) is not None or _failure(f)]
        return files[-1] if files else None
    return find


# name -> (description, finder: scheme_id -> draft file or None)
CONFIGURATIONS: dict[str, tuple[str, Callable[[str], Path | None]]] = {
    "phase3_pipeline": ("2026-08 Phase 3 pipeline: extraction -> judge+repair -> gate (latest stage on disk)", _phase3),
    "baseline3_extraction_only": ("Baseline 3: one extraction, no judge or repair (k=3 run, sample 1)", _sample(1)),
    "pipeline_on_sample1": ("Full pipeline (judge -> gate -> apply approved) on the same extraction as Baseline 3",
                           _latest("pipeline_on_sample1/{sid}.json")),
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
        per_scheme, absent, failed = {}, [], {}
        for sid in schemes:
            path = find(sid)
            if path is None:
                absent.append(sid)
                continue
            if name != "phase3_pipeline" and _failure(path):
                failed[sid] = {"reason": _failure(path), "file": str(path.relative_to(ROOT))}
                continue
            per_scheme[sid] = {"draft_file": str(path.relative_to(ROOT)), **_score(gold[sid], profiles[sid], _draft(path))}
            if _applied(path) is not None:
                per_scheme[sid]["findings_applied"] = _applied(path)
            if name == "pipeline_on_sample1" and _setting(path):
                per_scheme[sid]["judge_setting"] = _setting(path)
        report["configurations"][name] = {"description": description, "absent": absent, "failed": failed,
                                          "per_scheme": per_scheme,
                                          "aggregate": _aggregate(per_scheme) if per_scheme else None}
    report["pipeline_vs_baseline3"] = _paired(report["configurations"])
    for sid in schemes:
        report["baseline2"][sid] = baseline2(sid, gold[sid], profiles[sid])
    return report


def _paired(configs: dict) -> dict:
    """The full pipeline against Baseline 3 on the SAME extraction, only where both produced a scheme:
    a failed judge call or a missing sample is excluded and listed, never counted as "unchanged"."""
    b3, pipe = configs["baseline3_extraction_only"], configs["pipeline_on_sample1"]
    both = [s for s in b3["per_scheme"] if s in pipe["per_scheme"]]
    def side(r: dict) -> dict:
        o = r["outcome_equivalence"]
        return {"f1": r["structural_f1"]["f1"], "agreement": o["agreement_rate"], "false_eligible": o["false_positive_eligible_rate"],
                "false_not_eligible": o["false_negative_eligible_rate"], "other": o["other_mismatch_rate"]}

    rows = [{"scheme": s, "findings_applied": pipe["per_scheme"][s].get("findings_applied"),
             "judge_setting": pipe["per_scheme"][s].get("judge_setting"),
             "baseline3": side(b3["per_scheme"][s]), "pipeline": side(pipe["per_scheme"][s])} for s in both]
    excluded = {**{s: v["reason"] for s, v in pipe["failed"].items()},
                **{s: "no Baseline 3 sample (extraction failed validation)" for s in b3["absent"]},
                **{s: "pipeline not run yet" for s in pipe["absent"] if s not in b3["absent"]}}
    return {"rows": rows, "excluded": excluded,
            "aggregate": {"baseline3": _aggregate({s: b3["per_scheme"][s] for s in both}) if both else None,
                          "pipeline": _aggregate({s: pipe["per_scheme"][s] for s in both}) if both else None}}


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
        if not cfg["per_scheme"] and not cfg.get("failed"):
            lines += [f"*No results yet (absent for all {len(cfg['absent'])} schemes).*"]
            continue
        lines += ["| Scheme | Structural F1 | Exceptions F1 | Outcome agreement | FP (eligible) | FN (eligible) | n | Scalar | Draft |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for sid, r in cfg["per_scheme"].items():
            exc = r["f1_by_category"].get("exception_to_exclusion")
            o, s = r["outcome_equivalence"], r["scalar"]
            lines.append(f"| {sid}{' *(judge: ' + r['judge_setting'] + ')*' if r.get('judge_setting') else ''} | {r['structural_f1']['f1']:.3f} | {'—' if exc is None else format(exc['f1'], '.3f')} | "
                         f"{_pct(o['agreement_rate'])} | {_pct(o['false_positive_eligible_rate'])} | "
                         f"{_pct(o['false_negative_eligible_rate'])} | {o['n_profiles']} | {s['n_matched']}/{s['n_checked']} | "
                         f"`{Path(r['draft_file']).name}` |")
        for sid, f in cfg.get("failed", {}).items():
            lines.append(f"| {sid} | **failed run** — {f['reason']}; excluded | | | | | | | `{Path(f['file']).name}` |")
        a = cfg["aggregate"]
        if a is None:
            continue
        lines.append(f"| **All ({a['schemes']})** | **{a['structural_f1_micro']['f1']:.3f}** (micro) | | "
                     f"**{_pct(a['outcome_equivalence']['agreement_rate'])}** | {_pct(a['outcome_equivalence']['false_positive_eligible_rate'])} | "
                     f"{_pct(a['outcome_equivalence']['false_negative_eligible_rate'])} | {a['outcome_equivalence']['n_profiles']} | | |")
        if cfg["absent"]:
            lines.append(f"\nAbsent: {', '.join(cfg['absent'])}.")
    pv = report.get("pipeline_vs_baseline3")
    if pv:
        lines += ["", "## Full pipeline vs Baseline 3, same extraction", "",
                  "Only schemes where both produced a scheme. A failed judge call is a failed run: excluded and listed, "
                  "not scored as \"no change\".", ""]
        if pv["rows"]:
            lines += ["Each cell: Baseline 3 → pipeline. \"Other\" is almost always *undetermined*: a rule on a field the "
                      "test profiles don't carry. A finding the judge adds usually introduces such a field "
                      "(`ontology_proposed`), so a drop in agreement there is the profiles not answering, not a wrong "
                      "verdict; false eligible / false not eligible are the wrong verdicts.", "",
                      "| Scheme | Findings applied | Structural F1 | Outcome agreement | False eligible | False not eligible | Other (undetermined) |",
                      "|---|---|---|---|---|---|---|"]
            for r in pv["rows"]:
                b, p = r["baseline3"], r["pipeline"]
                label = r["scheme"] + (f" *(judge: {r['judge_setting']})*" if r.get("judge_setting") else "")
                lines.append(f"| {label} | {r['findings_applied']} | {b['f1']:.3f} → {p['f1']:.3f} | "
                             f"{_pct(b['agreement'])} → {_pct(p['agreement'])} | {_pct(b['false_eligible'])} → {_pct(p['false_eligible'])} | "
                             f"{_pct(b['false_not_eligible'])} → {_pct(p['false_not_eligible'])} | {_pct(b['other'])} → {_pct(p['other'])} |")
            ab, ap = pv["aggregate"]["baseline3"], pv["aggregate"]["pipeline"]
            ob, op = ab["outcome_equivalence"], ap["outcome_equivalence"]
            other = lambda o: 1 - o["agreement_rate"] - o["false_positive_eligible_rate"] - o["false_negative_eligible_rate"]  # noqa: E731
            lines.append(f"| **All ({ab['schemes']})** | | **{ab['structural_f1_micro']['f1']:.3f} → {ap['structural_f1_micro']['f1']:.3f}** (micro) | "
                         f"**{_pct(ob['agreement_rate'])} → {_pct(op['agreement_rate'])}** (n={ob['n_profiles']}) | "
                         f"{_pct(ob['false_positive_eligible_rate'])} → {_pct(op['false_positive_eligible_rate'])} | "
                         f"{_pct(ob['false_negative_eligible_rate'])} → {_pct(op['false_negative_eligible_rate'])} | "
                         f"{_pct(other(ob))} → {_pct(other(op))} |")
        else:
            lines.append("*No scheme has both yet.*")
        if any(r.get("judge_setting") for r in pv["rows"]):
            lines += ["", "*(judge: …)* marks a scheme whose judge call used a different setting from the others: its first "
                      "call failed (json_validate_failed) and this is its retry, so it is not an identical-conditions run."]
        if pv["excluded"]:
            lines += ["", "Excluded: " + "; ".join(f"{s} — {why}" for s, why in pv["excluded"].items()) + "."]
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
