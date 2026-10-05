"""Score the gate re-validation -- final-push item 6. Offline.

    PYTHONPATH=. python scripts/analyze_gate_revalidation.py

SYNTHETIC ERRORS, SMALL SAMPLE (30 errors, 14 mutated variants, 7 clean controls). Results say what the
judge + gate CAN catch on deliberately broken gold, not how often real extractions go wrong.

Error types are reported in three groups that are never pooled into one catch rate:

  A. within the JUDGE's detection design -- dropped_predicate: the judge's "preambular implied fact"
     finding proposes a missing predicate.
  B. within the GATE's design -- fabricated_supersedes: the judge never reviews a draft's existing
     supersedes block, so it can't flag one; what exists to catch fabricated supersedes is the gate's
     check that a retired value literally appears in the source, applied when a judge PROPOSES one. That
     check is applied here directly to each injected supersedes (no quota).
  C. OUTSIDE both designs -- present-but-wrong rules: flipped_operator, wrong_threshold,
     wrong_quantifier, wrong_exception_scope. The judge has no finding type for "this rule is wrong".

Per error the outcome is: corrected (a matching finding the gate auto-accepted, with the right fix),
flagged (a matching finding the gate deferred to a human), wrong_fix (accepted but not the gold
predicate), or missed (no matching finding). Clean controls give the false-defer and false-accept
rates on correct gold.

Alongside, with zero quota: the k=3 AGREEMENT signal (the share of a scheme's independent extraction
samples that produced an identical predicate) as a deferral signal for each candidate predicate --
precision/recall at each threshold with recall per error type, and ECE. A scheme needs >= 2 valid
samples. Writes data/experiments/gate_revalidation_analysis_<date>.json and docs/results/GATE_REVALIDATION.md.
"""

from __future__ import annotations

import copy
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from schemelogic.deferral.calibration_gate import _value_is_literally_grounded  # noqa: E402
from schemelogic.evaluation.structural_f1 import flatten_scheme  # noqa: E402
from schemelogic.experiments import harness  # noqa: E402
from schemelogic.experiments.injected_errors import InjectedError, _get, _sweep, apply  # noqa: E402
from schemelogic.schema.models import Scheme  # noqa: E402

RUN = harness.EXPERIMENTS_DIR / "gate_revalidation"
SAMPLES = harness.EXPERIMENTS_DIR / "self_consistency"
GROUPS = {
    "A_judge_design": ("dropped_predicate",),
    "B_gate_design": ("fabricated_supersedes",),
    "C_outside_design": ("flipped_operator", "wrong_threshold", "wrong_quantifier", "wrong_exception_scope"),
}
GROUP_OF = {k: g for g, kinds in GROUPS.items() for k in kinds}
THRESHOLDS = ((0.0, "0 of 3"), (1 / 3, "at most 1 of 3"), (2 / 3, "at most 2 of 3"), (1.0, "any number of"))


def _field_of(error: dict, gold_data: dict) -> str | None:
    if error["kind"] == "fabricated_supersedes":
        return error["after"]["retired_predicate"]["field"]
    return _get(gold_data, error["location"].split(".except")[0])["field"]


def judge_outcome(error: dict, result: dict | None, gold_data: dict) -> dict:
    """What the judge + gate did about one injected error."""
    if result is None:
        return {"outcome": "not_run"}
    if "judge_failure" in result:
        return {"outcome": "judge_failed", "detail": result["judge_failure"]["reason"]}
    field = _field_of(error, gold_data)
    matches = []
    for finding, decision in zip(result.get("findings", []), result.get("gate_decisions", [])):
        proposed = finding.get("proposed_predicate") or {}
        supersedes = finding.get("proposed_supersedes") or {}
        if proposed.get("field") == field or supersedes.get("retired_field") == field:
            matches.append((finding, decision))
    if not matches:
        return {"outcome": "missed"}
    finding, decision = matches[0]
    if decision["decision"] != "auto_accept":
        return {"outcome": "flagged", "gate_reasons": decision["reasons"]}
    proposed = finding.get("proposed_predicate") or {}
    gold_pred = error.get("before") or {}
    right = (error["kind"] == "dropped_predicate" and proposed.get("op") == gold_pred.get("op")
             and proposed.get("value") == gold_pred.get("value"))
    return {"outcome": "corrected" if right else "wrong_fix"}


def gate_check_on_supersedes(error: dict, document: str) -> dict:
    """The gate's own fabrication check, applied to the injected supersedes as if a judge proposed it."""
    retired = error["after"]["retired_predicate"]["value"]
    grounded = _value_is_literally_grounded(retired, document)
    return {"retired_value": retired, "literally_in_source": grounded,
            "gate_would": "auto-accept (if confidence cleared the bar)" if grounded else "defer"}


def _valid_samples(sid: str) -> list[Scheme]:
    out = []
    for path in sorted((SAMPLES / sid).glob("sample_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if "draft_extraction" in payload:
            out.append(Scheme.model_validate(payload["draft_extraction"]))
    return out


def _keys_of_error(error: dict) -> tuple[Counter, Counter]:
    """(predicates the error adds, predicates it removes), by applying it ALONE to the gold."""
    gold = harness.frozen_gold(error["scheme_id"])
    data = copy.deepcopy(gold.model_dump(mode="json", by_alias=True))
    apply(data, InjectedError(**error))
    data["exclusions"] = [x for x in data.get("exclusions", []) if x is not None]
    _sweep(data["inclusion"])
    before = Counter(p.match_key() for p in flatten_scheme(gold))
    after = Counter(p.match_key() for p in flatten_scheme(Scheme.model_validate(data)))
    return after - before, before - after


def agreement_points(candidates: list[dict]) -> tuple[list[dict], list[str]]:
    """Each candidate predicate (mutated variants + clean controls): its k=3 agreement and, if it is an
    injected error, which type. Rules an error REMOVED are scored separately: the agreement of the
    missing gold predicate (how strongly the samples say it should be there)."""
    points, skipped = [], []
    sample_keys: dict[str, list[Counter]] = {}
    for cand in candidates:
        sid = cand["scheme_id"]
        if sid not in sample_keys:
            sample_keys[sid] = [Counter(p.match_key() for p in flatten_scheme(s)) for s in _valid_samples(sid)]
        keys = sample_keys[sid]
        if len(keys) < 2:
            skipped.append(sid)
            continue
        gold_keys = Counter(p.match_key() for p in flatten_scheme(harness.frozen_gold(sid)))
        cand_keys = Counter(p.match_key() for p in flatten_scheme(Scheme.model_validate(cand["scheme"])))
        added_by, kind_added, kind_removed = Counter(), {}, {}
        for e in cand["errors"]:
            added, removed = _keys_of_error(e)
            added_by += added
            kind_added.update({k: e["kind"] for k in added})
            kind_removed.update({k: e["kind"] for k in removed})
        for key, count in cand_keys.items():
            agreement = sum(1 for k in keys if k[key] > 0) / len(keys)
            for i in range(count):
                is_error = i < added_by[key]
                points.append({"variant": cand["variant_id"], "scheme": sid, "agreement": agreement, "error": is_error,
                               "kind": kind_added.get(key) if is_error else None, "clean_control": not cand["errors"]})
        for key in gold_keys - cand_keys:
            agreement = sum(1 for k in keys if k[key] > 0) / len(keys)
            points.append({"variant": cand["variant_id"], "scheme": sid, "agreement": agreement, "error": True,
                           "kind": kind_removed.get(key, "unattributed"), "clean_control": False, "missing": True})
    return points, sorted(set(skipped))


def pr_table(points: list[dict]) -> list[dict]:
    """Flag a PRESENT rule for review when at most that share of samples produced it. Positives = injected
    errors; recall also per error type."""
    present = [p for p in points if not p.get("missing")]
    positives = [p for p in present if p["error"]]
    rows = []
    for limit, label in THRESHOLDS:
        flagged = [p for p in present if p["agreement"] <= limit + 1e-9]
        tp = [p for p in flagged if p["error"]]
        rows.append({"flag_if_produced_by": label, "flagged": len(flagged), "true_errors_flagged": len(tp),
                     "precision": round(len(tp) / len(flagged), 3) if flagged else None,
                     "recall": round(len(tp) / len(positives), 3) if positives else None,
                     "recall_by_kind": {k: f"{sum(p['kind'] == k for p in tp)}/{sum(p['kind'] == k for p in positives)}"
                                        for k in sorted({p['kind'] for p in positives})}})
    return rows


def ece(points: list[dict]) -> float | None:
    """Calibration of agreement as P(rule is correct), over present rules."""
    present = [p for p in points if not p.get("missing")]
    if not present:
        return None
    bins = defaultdict(list)
    for p in present:
        bins[round(p["agreement"], 2)].append(not p["error"])
    return round(sum(len(v) / len(present) * abs(c - sum(v) / len(v)) for c, v in bins.items()), 4)


def load_candidates() -> list[dict]:
    corpus = RUN / "corpus.json"
    if corpus.exists():
        return json.loads(corpus.read_text(encoding="utf-8"))["candidates"]
    from importlib import util
    spec = util.spec_from_file_location("run_gate_revalidation", ROOT / "scripts" / "run_gate_revalidation.py")
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.candidates()


def analyze() -> dict:
    candidates = load_candidates()
    results = {}
    for cand in candidates:
        path = RUN / f"{cand['variant_id'].replace('~', '__')}.json"
        results[cand["variant_id"]] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    per_error = []
    for cand in candidates:
        gold_data = harness.frozen_gold(cand["scheme_id"]).model_dump(mode="json", by_alias=True)
        document, _ = harness.source_document(cand["scheme_id"])
        for e in cand["errors"]:
            row = {"error_id": e["error_id"], "scheme": e["scheme_id"], "kind": e["kind"], "group": GROUP_OF[e["kind"]],
                   "description": e["description"], **judge_outcome(e, results[cand["variant_id"]], gold_data)}
            if e["kind"] == "fabricated_supersedes":
                row["gate_check"] = gate_check_on_supersedes(e, document)
            per_error.append(row)
    controls = []
    for cand in (c for c in candidates if not c["errors"]):
        r = results[cand["variant_id"]]
        decisions = (r or {}).get("gate_decisions", [])
        controls.append({"scheme": cand["scheme_id"], "judge_ran": r is not None and "judge_failure" not in r,
                         "findings": len(decisions), "deferred": sum(d["decision"] != "auto_accept" for d in decisions),
                         "auto_accepted": sum(d["decision"] == "auto_accept" for d in decisions)})
    points, skipped = agreement_points(candidates)
    return {
        **harness.result_header("gate_revalidation_analysis", provider="none (offline)",
                                config={"groups": GROUPS, "synthetic": True}),
        "per_error": per_error, "clean_controls": controls,
        "agreement_signal": {"schemes_skipped_fewer_than_2_samples": skipped,
                             "n_present": sum(1 for p in points if not p.get("missing")), "ece": ece(points),
                             "pr": pr_table(points), "missing_rules": [p for p in points if p.get("missing")]},
    }


NAMES = {"A_judge_design": "A. Within the judge's design — a missing rule",
         "B_gate_design": "B. Within the gate's design — a fabricated supersedes",
         "C_outside_design": "C. Outside both designs — a present-but-wrong rule"}


def markdown(a: dict) -> str:
    L = ["# Gate re-validation on injected errors", "",
         f"*Generated {a['created_at']} by `scripts/analyze_gate_revalidation.py` from code `{a['code_commit']}`, "
         f"against frozen gold `{a['gold_tag']}`.*", "",
         "> **Synthetic errors, small sample.** 30 deliberate mutations of correct gold (14 mutated variants, "
         "7 clean controls), one judge sample each. These numbers say what the judge + gate *can* catch, not how "
         "often real extractions go wrong. One error moves a type's rate by 17-25 points. Groups A, B and C are "
         "never pooled into one catch rate.", ""]
    for group, kinds in GROUPS.items():
        L += [f"## {NAMES[group]}", "", "| Error type | n | Corrected | Flagged (deferred) | Wrong fix | Missed | Judge failed / not run |",
              "|---|---|---|---|---|---|---|"]
        for kind in kinds:
            c = Counter(r["outcome"] for r in a["per_error"] if r["kind"] == kind)
            L.append(f"| {kind} | {sum(c.values())} | {c['corrected']} | {c['flagged']} | {c['wrong_fix']} | {c['missed']} | "
                     f"{c['judge_failed'] + c['not_run']} |")
        if group == "B_gate_design":
            L += ["", "The gate's fabrication check, applied directly to each injected supersedes:", "",
                  "| Error | Invented retired value | Literally in the source? | Gate would |", "|---|---|---|---|"]
            for r in a["per_error"]:
                if r["kind"] == "fabricated_supersedes":
                    g = r["gate_check"]
                    L.append(f"| {r['error_id']} | `{g['retired_value']}` | {g['literally_in_source']} | {g['gate_would']} |")
        L.append("")
    L += ["## Clean controls (correct gold, nothing injected)", "",
          "| Scheme | Judge ran | Findings | Deferred (false defer) | Auto-accepted (a change to correct gold) |", "|---|---|---|---|---|"]
    L += [f"| {r['scheme']} | {r['judge_ran']} | {r['findings']} | {r['deferred']} | {r['auto_accepted']} |" for r in a["clean_controls"]]
    s = a["agreement_signal"]
    L += ["", "## The k=3 agreement signal as a deferral signal (no quota)", "",
          "A rule is scored by the share of the scheme's independent extraction samples that produced it identically; "
          "rules produced by few samples are flagged for review. Every injected error that leaves a wrong rule in the "
          "candidate is group C; the negatives are the candidates' correct rules. "
          f"Skipped (fewer than 2 samples): {', '.join(s['schemes_skipped_fewer_than_2_samples']) or 'none'}. "
          f"ECE of agreement as P(correct), n = {s['n_present']} rules: **{s['ece']}**.", "",
          "**Read recall with care: it is close to guaranteed here.** An injected rule is a mutation of gold that "
          "no extraction produced, so the samples almost never contain it and it scores low agreement by "
          "construction. A real extraction error is one the model itself made, possibly in every sample. Precision "
          "is the informative number: most rules this signal flags are correct rules the samples did not reproduce "
          "identically.", "",
          "| Flag a rule produced by | Flagged | True errors flagged | Precision | Recall | Recall by error type |",
          "|---|---|---|---|---|---|"]
    for row in s["pr"]:
        by_kind = ", ".join(f"{k} {v}" for k, v in row["recall_by_kind"].items())
        L.append(f"| {row['flag_if_produced_by']} samples | {row['flagged']} | {row['true_errors_flagged']} | "
                 f"{row['precision']} | {row['recall']} | {by_kind} |")
    if s["missing_rules"]:
        L += ["", "The gold rule each error removed or replaced (a dropped rule or exception, or the original of a flipped / "
              "re-thresholded / re-quantified rule): did the samples produce it — would agreement point at what the "
              "candidate is missing?", "",
              "| Error type | Removed rules | Produced by >= 2 of 3 samples |", "|---|---|---|"]
        for kind in sorted({p["kind"] for p in s["missing_rules"]}):
            rows = [p for p in s["missing_rules"] if p["kind"] == kind]
            L.append(f"| {kind} | {len(rows)} | {sum(p['agreement'] >= 0.66 for p in rows)} |")
    return "\n".join(L) + "\n"


def main() -> None:
    a = analyze()
    out = harness.EXPERIMENTS_DIR / f"gate_revalidation_analysis_{a['date']}.json"
    out.write_text(json.dumps(a, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    md = ROOT / "docs" / "results" / "GATE_REVALIDATION.md"
    md.write_text(markdown(a), encoding="utf-8")
    print(f"written: {out.relative_to(ROOT)}, {md.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
