"""Cross-lingual case study (C2) -- final-push item 10. Offline: no LLM calls.

    PYTHONPATH=. python scripts/analyze_cross_lingual.py

MH-LADKI-BAHIN extracted from Marathi (the three GRs of 28.06, 03.07 and 12.07.2024 in date order --
the temporal_c4 "marathi_GRs_in_order" arm, k=3) and from English (the scheme's current input document,
the k=3 self-consistency samples). Every valid draft runs through the evaluator on the frozen gold's
test profiles: (1) each draft against gold (outcome agreement, false eligible / false not-eligible,
structural F1); (2) drafts against each other, verdict by verdict on the same profiles -- Marathi vs
English pairs, with English-English and Marathi-Marathi pairs as the sampling-noise baseline, so a
language effect has to exceed the disagreement between two samples of the same text.

Not a clean translation pair: the English document is a compilation (the GRs plus official
secondary sources), not a translation of the GRs, and the Marathi input needs the 03.07 amendment
applied (C4). Writes data/experiments/cross_lingual_c2_<date>.json and docs/results/CROSS_LINGUAL_C2.md.
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from schemelogic.evaluation.outcome_equivalence import evaluate_outcome_equivalence  # noqa: E402
from schemelogic.evaluation.structural_f1 import compare_schemes  # noqa: E402
from schemelogic.evaluator.symbolic_engine import evaluate  # noqa: E402
from schemelogic.experiments import harness  # noqa: E402
from schemelogic.schema.models import Scheme  # noqa: E402

SCHEME = "MH-LADKI-BAHIN"
ARMS = {
    "mr": ("Marathi: GRs 28.06, 03.07, 12.07.2024 in date order", "temporal_c4/MH-LADKI-BAHIN__marathi_GRs_in_order"),
    "en": ("English: current input document (compiled)", f"self_consistency/{SCHEME}"),
}
NOT_RUN = [
    "PM-KISAN (Hindi/English): pmkisan.gov.in has a 2019 scheme summary in English and in Hindi "
    "(kept locally as PM-KISAN_summary_english_2019.pdf / PM-KISAN_summary_hindi_2019.pdf). The Hindi PDF "
    "uses a legacy non-Unicode font: its extracted text is corrupted (e.g. निधि comes out as ननधध), so an "
    "extraction from it would test the PDF's font encoding, not the language. Not run; would need OCR.",
    "No other gold scheme's sources include an official parallel text in two languages.",
]


def drafts(lang: str) -> list[tuple[str, Scheme | None]]:
    out = []
    for path in sorted((harness.EXPERIMENTS_DIR / ARMS[lang][1]).glob("sample_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        scheme = Scheme.model_validate(payload["draft_extraction"]) if "draft_extraction" in payload else None
        out.append((f"{lang}:{path.stem}", scheme))
    return out


def analyze() -> dict:
    gold = harness.frozen_gold(SCHEME)
    profiles = harness.frozen_profiles(SCHEME)
    per_draft, valid = [], {}
    for lang in ARMS:
        for name, scheme in drafts(lang):
            if scheme is None:
                per_draft.append({"draft": name, "language": lang, "status": "extraction failed"})
                continue
            valid[name] = scheme
            oe = evaluate_outcome_equivalence(gold, scheme, profiles).to_dict()
            per_draft.append({"draft": name, "language": lang, "status": "ok",
                              "structural_f1": round(compare_schemes(gold, scheme).overall.f1, 3),
                              **{k: oe[k] for k in ("n_profiles", "agreement_rate", "false_positive_eligible_rate",
                                                    "false_negative_eligible_rate", "other_mismatch_rate")}})
    verdicts = {name: {pid: evaluate(s, p).verdict.value for pid, p in profiles.items()} for name, s in valid.items()}
    pairs = []
    for a, b in itertools.combinations(sorted(verdicts), 2):
        differ = [pid for pid in profiles if verdicts[a][pid] != verdicts[b][pid]]
        la, lb = a.split(":")[0], b.split(":")[0]
        kind = f"{la}-{lb}" if la == lb else "mr-en"
        pairs.append({"a": a, "b": b, "kind": kind, "agreement": round(1 - len(differ) / len(profiles), 3),
                      "differ_on": [{"profile": pid, a: verdicts[a][pid], b: verdicts[b][pid]} for pid in differ]})
    by_kind = {}
    for kind in ("en-en", "mr-mr", "mr-en"):
        xs = [p["agreement"] for p in pairs if p["kind"] == kind]
        by_kind[kind] = {"pairs": len(xs), "mean_agreement": round(sum(xs) / len(xs), 3) if xs else None}
    return {**harness.result_header("cross_lingual_c2", "none (offline)", {"scheme": SCHEME, "arms": {k: v[1] for k, v in ARMS.items()}}),
            "n_profiles": len(profiles), "per_draft": per_draft, "pairwise_by_kind": by_kind, "pairs": pairs, "not_run": NOT_RUN}


def _pct(x) -> str:
    return "—" if x is None else f"{100 * x:.1f}%"


def markdown(a: dict) -> str:
    lines = [
        "# Cross-lingual case study (C2)", "",
        f"*Generated {a['date']} by `scripts/analyze_cross_lingual.py` (offline). Gold tag {a['gold_tag']}; "
        f"{a['n_profiles']} frozen test profiles; Groq `{a['model']}` extractions.*", "",
        "**Small sample** (k=3 per language, one scheme). **Not a clean translation pair**: the English input is a "
        "compilation of the GRs and official secondary sources, not a translation; the Marathi input is the original "
        "GR plus two amending GRs, so the extractor must also apply the amendment (see the temporal case study).", "",
        "## Each draft against gold", "",
        "| Draft | Language | Structural F1 | Outcome agreement | False eligible | False not eligible | Other |",
        "|---|---|---|---|---|---|---|",
    ]
    for d in a["per_draft"]:
        if d["status"] != "ok":
            lines.append(f"| {d['draft']} | {d['language']} | {d['status']} | | | | |")
            continue
        lines.append(f"| {d['draft']} | {d['language']} | {d['structural_f1']:.3f} | {_pct(d['agreement_rate'])} | "
                     f"{_pct(d['false_positive_eligible_rate'])} | {_pct(d['false_negative_eligible_rate'])} | {_pct(d['other_mismatch_rate'])} |")
    lines += ["", "## Drafts against each other (same profiles)", "",
              "| Pair kind | Pairs | Mean verdict agreement |", "|---|---|---|"]
    for kind, v in a["pairwise_by_kind"].items():
        lines.append(f"| {kind} | {v['pairs']} | {_pct(v['mean_agreement'])} |")
    lines += ["", "en-en and mr-mr are the noise baseline: two samples of the same text.", "", "### Pairs", ""]
    for p in a["pairs"]:
        lines.append(f"- {p['a']} vs {p['b']}: {_pct(p['agreement'])}"
                     + (f" — differ on {', '.join(d['profile'] for d in p['differ_on'])}" if p["differ_on"] else ""))
    lines += ["", "## Not run", ""] + [f"- {x}" for x in a["not_run"]]
    return "\n".join(lines) + "\n"


def main() -> None:
    a = analyze()
    out = harness.EXPERIMENTS_DIR / f"cross_lingual_c2_{a['date']}.json"
    out.write_text(json.dumps(a, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (ROOT / "docs" / "results" / "CROSS_LINGUAL_C2.md").write_text(markdown(a), encoding="utf-8")
    print(f"written: {out.relative_to(ROOT)}, docs/results/CROSS_LINGUAL_C2.md")


if __name__ == "__main__":
    main()
