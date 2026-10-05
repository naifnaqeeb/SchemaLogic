"""Self-consistency confidence vs self-reported confidence -- final-push item 2. Offline.

    PYTHONPATH=. python scripts/analyze_self_consistency.py

Reads the k extraction samples per scheme (scripts/run_self_consistency.py) and the frozen gold.

Per PREDICATE (every inclusion leaf, exclusion and exception a sample produced):
  - agreement confidence = the share of the scheme's valid samples that produced an identical predicate
    (same location, field, operator, value, quantifier, exception scope) -- 1/k, 2/k or 1;
  - self-reported confidence = the sample's own extraction_metadata.confidence;
  - correct = an identical predicate exists in the frozen gold (paired as multisets).
Per SCHEME: mean agreement, mean self-reported confidence, and accuracy (mean structural F1 and
outcome agreement of the samples against frozen gold).

Reports calibration (reliability bins and expected calibration error, ECE) of each confidence against
predicate correctness, and how each ranks the schemes against their accuracy -- the question behind
the pmksypdmc case (KNOWN_ISSUES: self-reported confidence 0.95 on an extraction that recovered
nothing). Small sample: 7 schemes, k=3. Writes data/experiments/self_consistency_analysis_<date>.json
and docs/results/SELF_CONSISTENCY.md.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from schemelogic.evaluation.outcome_equivalence import evaluate_outcome_equivalence  # noqa: E402
from schemelogic.evaluation.structural_f1 import compare_schemes, flatten_scheme  # noqa: E402
from schemelogic.experiments import harness  # noqa: E402
from schemelogic.schema.models import Scheme  # noqa: E402

SAMPLES = harness.EXPERIMENTS_DIR / "self_consistency"


def load_samples(sid: str) -> list[dict]:
    out = []
    for path in sorted((SAMPLES / sid).glob("sample_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        draft = Scheme.model_validate(payload["draft_extraction"]) if "draft_extraction" in payload else None
        out.append({"sample": payload["sample"], "draft": draft, "failure": payload.get("failure")})
    return out


def ece(points: list[tuple[float, bool]], bins: list[tuple[float, float]]) -> tuple[float | None, list[dict]]:
    """Expected calibration error over (confidence, correct) points, with explicit bins."""
    table, n = [], len(points)
    total = 0.0
    for lo, hi in bins:
        inside = [(c, ok) for c, ok in points if lo <= c <= hi]
        if not inside:
            table.append({"bin": [lo, hi], "n": 0, "mean_confidence": None, "accuracy": None})
            continue
        conf = sum(c for c, _ in inside) / len(inside)
        acc = sum(ok for _, ok in inside) / len(inside)
        total += len(inside) / n * abs(conf - acc)
        table.append({"bin": [lo, hi], "n": len(inside), "mean_confidence": round(conf, 3), "accuracy": round(acc, 3)})
    return (round(total, 4) if n else None), table


def spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None

    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for m in range(i, j + 1):
                r[order[m]] = (i + j) / 2
            i = j + 1
        return r

    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx, vy = sum((a - mx) ** 2 for a in rx) ** 0.5, sum((b - my) ** 2 for b in ry) ** 0.5
    return round(cov / (vx * vy), 3) if vx and vy else None


def analyze() -> dict:
    schemes = [s for s in harness.gold_scheme_ids() if (SAMPLES / s).exists()]
    per_scheme, agreement_points, self_points = {}, [], []
    for sid in schemes:
        samples = load_samples(sid)
        valid = [s for s in samples if s["draft"] is not None]
        if len(valid) < 2:
            # agreement needs at least two samples to agree or disagree -- one sample is not a signal
            per_scheme[sid] = {"k": len(samples), "valid": len(valid), "failures": [s["failure"] for s in samples if s["draft"] is None],
                               "excluded": "fewer than 2 valid samples so far"}
            continue
        gold = harness.frozen_gold(sid)
        profiles = harness.frozen_profiles(sid)
        gold_keys = Counter(p.match_key() for p in flatten_scheme(gold))
        sample_keys = [Counter(p.match_key() for p in flatten_scheme(s["draft"])) for s in valid]
        k_valid = len(valid)
        rows = []
        for i, s in enumerate(valid):
            self_conf = s["draft"].extraction_metadata.confidence
            remaining = Counter(gold_keys)
            for key, count in sample_keys[i].items():
                for _ in range(count):
                    agreement = sum(1 for other in sample_keys if other[key] > 0) / k_valid
                    correct = remaining[key] > 0
                    if correct:
                        remaining[key] -= 1
                    rows.append({"sample": s["sample"], "agreement": agreement, "self_reported": self_conf, "correct": correct})
                    agreement_points.append((agreement, correct))
                    self_points.append((self_conf, correct))
        f1s = [compare_schemes(gold, s["draft"]).overall.f1 for s in valid]
        oes = [evaluate_outcome_equivalence(gold, s["draft"], profiles).agreement_rate for s in valid]
        per_scheme[sid] = {
            "k": len(samples), "valid": k_valid, "failures": [s["failure"] for s in samples if s["draft"] is None],
            "predicates_per_sample": [sum(c.values()) for c in sample_keys],
            "mean_agreement_confidence": round(sum(r["agreement"] for r in rows) / len(rows), 3) if rows else None,
            "unanimous_share": round(sum(1 for r in rows if r["agreement"] == 1) / len(rows), 3) if rows else None,
            "mean_self_reported_confidence": round(sum(s["draft"].extraction_metadata.confidence for s in valid) / k_valid, 3),
            "self_reported_by_sample": [s["draft"].extraction_metadata.confidence for s in valid],
            "mean_structural_f1": round(sum(f1s) / len(f1s), 3), "structural_f1_by_sample": [round(f, 3) for f in f1s],
            "mean_outcome_agreement": round(sum(oes) / len(oes), 3), "outcome_agreement_by_sample": [round(o, 3) for o in oes],
            "predicate_precision": round(sum(r["correct"] for r in rows) / len(rows), 3) if rows else None,
        }
    scored = [s for s, r in per_scheme.items() if "excluded" not in r]
    agreement_bins = [(0.0, 0.34), (0.35, 0.67), (0.68, 1.0)]
    self_bins = [(0.0, 0.5), (0.51, 0.7), (0.71, 0.85), (0.86, 1.0)]
    a_ece, a_table = ece(agreement_points, agreement_bins)
    s_ece, s_table = ece(self_points, self_bins)
    pick = lambda key: [per_scheme[s][key] for s in scored]  # noqa: E731
    return {
        **harness.result_header("self_consistency_analysis", provider="none (offline)", config={"bins": {
            "agreement": agreement_bins, "self_reported": self_bins}}),
        "schemes_with_samples": scored, "per_scheme": per_scheme,
        "predicate_calibration": {
            "n_predicates": len(agreement_points),
            "agreement": {"ece": a_ece, "reliability": a_table},
            "self_reported": {"ece": s_ece, "reliability": s_table},
        },
        "scheme_rank_correlation": {
            "agreement_vs_structural_f1": spearman(pick("mean_agreement_confidence"), pick("mean_structural_f1")),
            "self_reported_vs_structural_f1": spearman(pick("mean_self_reported_confidence"), pick("mean_structural_f1")),
            "agreement_vs_outcome_agreement": spearman(pick("mean_agreement_confidence"), pick("mean_outcome_agreement")),
            "self_reported_vs_outcome_agreement": spearman(pick("mean_self_reported_confidence"), pick("mean_outcome_agreement")),
            "n_schemes": len(scored),
        },
    }


def markdown(a: dict) -> str:
    L = ["# Self-consistency confidence (k samples) vs self-reported confidence", "",
         f"*Generated {a['created_at']} by `scripts/analyze_self_consistency.py` from code `{a['code_commit']}`, "
         f"against frozen gold `{a['gold_tag']}`. Small sample: {len(a['schemes_with_samples'])} schemes, k samples each; "
         "rank correlations over so few schemes are indicative only. Agreement is over a scheme's VALID samples "
         "(a sample that failed schema validation produced no predicates and is listed, not counted); a scheme "
         "needs at least 2 valid samples to be scored.*", "",
         "| Scheme | Valid samples | Predicates per sample | Mean agreement | Unanimous | Self-reported (per sample) | Structural F1 (per sample) | Outcome agreement (mean) |",
         "|---|---|---|---|---|---|---|---|"]
    for sid, r in a["per_scheme"].items():
        if "excluded" in r:
            L.append(f"| {sid} | {r['valid']}/{r['k']} | — | — | — | — | — | — | *({r['excluded']})*")
            continue
        L.append(f"| {sid} | {r['valid']}/{r['k']} | {r['predicates_per_sample']} | {r['mean_agreement_confidence']} | "
                 f"{r['unanimous_share']} | {r['self_reported_by_sample']} | {r['structural_f1_by_sample']} | {r['mean_outcome_agreement']} |")
    c = a["predicate_calibration"]
    L += ["", f"## Predicate-level calibration (n = {c['n_predicates']} predicates)", "",
          "Correct = an identical predicate exists in the frozen gold.", "",
          f"- Agreement confidence: ECE **{c['agreement']['ece']}**",
          f"- Self-reported confidence: ECE **{c['self_reported']['ece']}**", "",
          "| Signal | Bin | n | Mean confidence | Accuracy |", "|---|---|---|---|---|"]
    for name in ("agreement", "self_reported"):
        for b in c[name]["reliability"]:
            L.append(f"| {name} | {b['bin']} | {b['n']} | {b['mean_confidence']} | {b['accuracy']} |")
    r = a["scheme_rank_correlation"]
    L += ["", f"## Scheme ranking (Spearman, n = {r['n_schemes']})", "",
          "| | vs structural F1 | vs outcome agreement |", "|---|---|---|",
          f"| Agreement confidence | {r['agreement_vs_structural_f1']} | {r['agreement_vs_outcome_agreement']} |",
          f"| Self-reported confidence | {r['self_reported_vs_structural_f1']} | {r['self_reported_vs_outcome_agreement']} |"]
    return "\n".join(L) + "\n"


def main() -> None:
    a = analyze()
    out = harness.EXPERIMENTS_DIR / f"self_consistency_analysis_{a['date']}.json"
    out.write_text(json.dumps(a, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    md = ROOT / "docs" / "results" / "SELF_CONSISTENCY.md"
    md.write_text(markdown(a), encoding="utf-8")
    print(f"written: {out.relative_to(ROOT)}, {md.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
