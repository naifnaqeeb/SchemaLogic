"""Temporal case study (C4) -- final-push item 9. LIVE for the new arms; scoring is offline.

    PYTHONPATH=. python scripts/run_temporal_case_study.py [--budget=175000]
    PYTHONPATH=. python scripts/run_temporal_case_study.py --score     # offline: JSON + docs/results/TEMPORAL_C4.md

For each gold scheme with a documented amendment, the extractor (defaults, as in the k=3 runs) reads
pre-amendment source text, and its output is compared with what it produced from the current
(post-amendment) document -- the k=3 self-consistency samples, so the post arm costs no new quota.
Measured: is the rule the amendment retired present before and absent after, and is the rule it added
absent before and present after? Detectors match field names and values in the flattened draft and
the report lists the predicates they matched, so every call can be checked by eye.

Arms (pre-amendment texts are verbatim excerpts of official documents; whitespace normalised, page
headers/footers removed; the excerpt itself is saved in each result file because data/raw_documents/
is gitignored):

- PMMVY: Scheme Implementation Guidelines (MWCD, 2017), paras 1.3 and 2.2-2.4 -- first living child
  only. Post: PMMVY 2.0 (second child if a girl).
- MH-LADKI-BAHIN: GR of 28.06.2024 alone (age 21-60, five-acre land exclusion). A second arm reads the
  three GRs (28.06, 03.07, 12.07) in date order, so the extractor must apply the 03.07 amendment
  itself (age to 65, land exclusion deleted); k=3, and it doubles as the Marathi arm of C2 (item 10).
- AB-PMJAY: NHA Beneficiary Identification Guidelines (pre-2024) criteria section plus the SECC 2011
  exclusion list (PIB, 3 July 2015) -- the post document's own sources minus the 2024 70+ guidelines.
  An addition, nothing retired: the 70+ branch should be absent before and present after.
- PMAY-G: Framework for Implementation (MoRD, 2022 edition), para 4.1.1 and Annexure I -- 13
  exclusion parameters including refrigerator, landline and Rs 10,000/month. Post: the updated
  document (Sept-2024 revision: those two deleted, Rs 15,000). Plus the stale-document arm: the 2024
  PIB-based document that lists the deleted items without saying they were deleted (GOLD_AUDIT 7.9),
  re-extracted with current code.
- PM-KISAN: Operational Guidelines as first issued (2018-19; pmkisan.gov.in links them as "Pre-Revised
  Operational Guidelines"), paras 1-3 -- small and marginal farmers, land up to 2 hectares. Post: the
  current document (the 2-hectare limit removed from 1 June 2019).
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Callable, NamedTuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from schemelogic.evaluation.structural_f1 import FlatPredicate, flatten_scheme  # noqa: E402
from schemelogic.experiments import harness  # noqa: E402
from schemelogic.extraction import extractor  # noqa: E402
from schemelogic.schema.models import Scheme  # noqa: E402

ITEM = "temporal_c4"
OUT = harness.EXPERIMENTS_DIR / ITEM
PROVIDER = "groq"
ESTIMATE_PER_SAMPLE = 9_500
RAW = ROOT / "data" / "raw_documents"
CORPUS = ROOT / "data" / "retrieval_corpus"

# Schemes the user listed that are not run, with the reason. Empty since 2026-10-05: PM-KISAN's
# pre-amendment text was found on pmkisan.gov.in, linked as "Pre-Revised Operational Guidelines".
DROPPED: dict[str, str] = {}



class Arm(NamedTuple):
    name: str
    scheme_id: str
    role: str  # "pre", "post_marathi" or "stale"
    k: int
    source: str  # provenance, recorded in each result


ARMS = [
    Arm("PM-KISAN__pre_2019_guidelines", "PM-KISAN", "pre", 1,
        "PM-KISAN Operational Guidelines as first issued, 2018-19 (PM-KISAN_primary_pre_revised_OG.pdf, from "
        "https://pmkisan.gov.in/Documents/OPERATIONAL%20GUIDELINES.pdf, linked there as 'Pre-Revised "
        "Operational Guidelines'), paras 1-3"),
    Arm("PMMVY__pre_2017_guidelines", "PMMVY", "pre", 1,
        "PMMVY Scheme Implementation Guidelines, MWCD 2017 (PMMVY_primary_guidelines_2017.pdf, from "
        "https://nirdpr.org.in/crru/docs/health/PMMVY%20Scheme%20Implemetation%20Guidelines.pdf), paras 1.3, 2.2-2.4"),
    Arm("MH-LADKI-BAHIN__pre_GR_20240628", "MH-LADKI-BAHIN", "pre", 1,
        "GR मबावि 2024/प्र.क्र.96/कार्या-2 of 28.06.2024 (data/retrieval_corpus excerpt)"),
    Arm("MH-LADKI-BAHIN__marathi_GRs_in_order", "MH-LADKI-BAHIN", "post_marathi", 3,
        "GRs of 28.06.2024, 03.07.2024 and 12.07.2024 in date order (data/retrieval_corpus excerpts)"),
    Arm("AB-PMJAY__pre_2024_identification", "AB-PMJAY", "pre", 1,
        "NHA Beneficiary Identification Guidelines (AB-PMJAY_primary_beneficiary_identification.pdf), "
        "section 1A and the covered-categories list; PIB 3 July 2015 SECC 2011 release "
        "(AB-PMJAY_primary_SECC_exclusion.pdf), the 14 exclusion parameters"),
    # k=3 since 2026-10-06: its single sample missed the whole 13-parameter exclusion list
    Arm("PMAY-G__pre_framework_2022", "PMAY-G", "pre", 3,
        "Framework for Implementation of PMAY-G, MoRD, 2022 edition (PMAY-G_primary_framework_2016.pdf, "
        "from https://rh.odisha.gov.in/guidelines/PMAY(G)_guidelines.pdf), para 4.1.1 and Annexure I"),
    Arm("PMAY-G__stale_PIB_2024", "PMAY-G", "stale", 1,
        "PMAY-G_stale_PIB_2024.md (sha256 4ae7bc58...44ef; GOLD_AUDIT 7.9)"),
]


# ---- documents -----------------------------------------------------------------------------------

def _pdf_text(name: str) -> str:
    """Whitespace-normalised text of data/raw_documents/<name>.pdf (cached as data/cache/source_text)."""
    cache = ROOT / "data" / "cache" / "source_text" / f"{name}.txt"
    if cache.exists():
        text = cache.read_text(encoding="utf-8")
    else:
        from pypdf import PdfReader

        text = "\n".join((p.extract_text() or "") for p in PdfReader(RAW / f"{name}.pdf").pages)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(text, encoding="utf-8")
    return re.sub(r"\s+", " ", text)


def _between(text: str, start: str, end: str) -> str:
    """text from `start` up to (not including) `end`; raises rather than guessing if either is missing."""
    i = text.find(start)
    j = text.find(end, i + len(start)) if i >= 0 else -1
    if i < 0 or j < 0:
        raise ValueError(f"excerpt markers not found: {start[:40]!r} .. {end[:40]!r}")
    return text[i:j].strip()


def _gr(date: str) -> str:
    """A retrieval-corpus GR excerpt, keeping its title and citation but not the corpus's own
    annotations (doc_id, effective and superseded dates), which a real GR doesn't carry."""
    lines = (CORPUS / f"MH-LADKI-BAHIN_GR_{date}.txt").read_text(encoding="utf-8").splitlines()
    keep = [ln for ln in lines if not re.match(r"(doc_id|scheme_id|effective_date|supersedes_\w+):", ln)]
    return "\n".join(keep).strip()


def document(arm: Arm) -> str:
    if arm.name == "PM-KISAN__pre_2019_guidelines":
        t = _pdf_text("PM-KISAN_primary_pre_revised_OG")
        return _between(t, "“Pradhan Mantri KIsan SAmman Nidhi (PM-KISAN)” OPERATIONAL GUIDELINES",
                        "4. Strategy for Implementation")
    if arm.name == "PMMVY__pre_2017_guidelines":
        t = re.sub(r" Chapter - \d+ \d+ ", " ", _pdf_text("PMMVY_primary_guidelines_2017"))  # page footer
        return ("Pradhan Mantri Matru Vandana Yojana (PMMVY) -- Scheme Implementation Guidelines, Ministry of "
                "Women and Child Development, 2017 (excerpts)\n\n"
                + _between(t, "1.3 Under PMMVY", "1.4 T") + "\n\n"
                + _between(t, "2.2 Target beneficiaries 2.2.1", "2.5 Closure of old Maternity Benefit Programme"))
    if arm.name == "MH-LADKI-BAHIN__pre_GR_20240628":
        return _gr("20240628")
    if arm.name == "MH-LADKI-BAHIN__marathi_GRs_in_order":
        return "\n\n---\n\n".join(_gr(d) for d in ("20240628", "20240703", "20240712"))
    if arm.name == "AB-PMJAY__pre_2024_identification":
        t = _pdf_text("AB-PMJAY_primary_beneficiary_identification")
        t = re.sub(r" ?Page \d+ of 15 Beneficiary Identification Guidelines ?", " ", t)
        secc = _pdf_text("AB-PMJAY_primary_SECC_exclusion").replace(" 7.05 Crore(39.39%) 2", "")  # table cell + page no.
        return ("Ayushman Bharat - Pradhan Mantri Jan Arogya Yojana (AB PM-JAY) -- Beneficiary Identification "
                "Guidelines, National Health Authority (excerpts)\n\n"
                + _between(t, "A. AB PM-JAY will target", "B. States covering") + "\n\n"
                + _between(t, "The categories in rural and urban", "The following activities will be carried out")
                + "\n\nSocio Economic and Caste Census 2011 -- PIB release of provisional data for rural India, "
                  "3 July 2015 (excerpt)\n\n"
                + _between(secc, "Total Excluded Households (based on fulfilling any of the 14 parameters",
                           "4. Automatically included"))
    if arm.name == "PMAY-G__pre_framework_2022":
        t = _pdf_text("PMAY-G_primary_framework_2016")
        return ("Framework for Implementation of Pradhan Mantri Awaas Yojana - Gramin (PMAY-G), Ministry of "
                "Rural Development, 2022 edition (excerpts)\n\n"
                + _between(t, "4.1 Universe of Eligible Beneficiaries 4.1.1", "4.2 Prioritisation within the Universe 4.2.1") + "\n\n"
                + _between(t, "Annexure –I EXCLUSION PROCESS", "80 Annexure-II"))
    if arm.name == "PMAY-G__stale_PIB_2024":
        return (RAW / "PMAY-G_stale_PIB_2024.md").read_text(encoding="utf-8")
    raise KeyError(arm.name)


# ---- runner --------------------------------------------------------------------------------------

def sample_path(arm: Arm, i: int) -> Path:
    return OUT / arm.name / f"sample_{i}.json"


def run(budget: int, extract=extractor.extract_scheme, ledger=None, arms=None) -> str:
    """Returns why it stopped: "done", "budget", "daily_cap" or "rate_limited". Resumable."""
    ledger = ledger or harness.Ledger(ITEM, PROVIDER, daily_budget=budget)
    for arm in arms or ARMS:
        text = document(arm)
        sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        for i in range(1, arm.k + 1):
            path = sample_path(arm, i)
            if path.exists():
                continue
            try:
                ledger.before_call(ESTIMATE_PER_SAMPLE)
            except harness.BudgetExhausted as exc:
                print(f"[stop] {exc}", flush=True)
                return "budget"
            usage: list[dict] = []
            result = extract(text, provider=PROVIDER, usage_sink=usage.append)
            for u in usage:
                ledger.record(u, scheme_id=arm.scheme_id, arm=arm.name, sample=i)
            failure = result if isinstance(result, extractor.ExtractionFailure) else None
            if failure is not None and (failure.reason == "rate_limited" or harness.is_daily_cap(failure.detail)):
                reason = "daily_cap" if harness.is_daily_cap(failure.detail) else "rate_limited"
                print(f"[stop] {arm.name} sample {i}: {reason}: {failure.detail[:600]}", flush=True)
                return reason
            payload = {
                **harness.result_header(ITEM, PROVIDER, {"k": arm.k, "temperature": 0.2, "extractor": "defaults"}),
                "scheme_id": arm.scheme_id, "arm": arm.name, "role": arm.role, "sample": i,
                "source": arm.source, "source_document_sha256": sha, "source_excerpt": text, "usage": usage,
            }
            if failure is None:
                payload["draft_extraction"] = result.model_dump(mode="json", by_alias=True)
            else:
                payload["failure"] = {"reason": failure.reason, "detail": failure.detail[:2000]}
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            spent = sum(u.get("total_tokens") or 0 for u in usage)
            print(f"  {arm.name} sample {i}: {'ok' if failure is None else 'FAILED ' + failure.reason} ({spent:,} tokens)", flush=True)
    return "done"


# ---- scoring (offline) ---------------------------------------------------------------------------

def _show(p: FlatPredicate) -> str:
    return f"{p.location}: {p.field} {p.op} {p.value!r}"


def _matching(preds, pattern: str) -> list[FlatPredicate]:
    return [p for p in preds if p.location != "exception" and re.search(pattern, p.field)]


def child_order_rule(preds) -> tuple[str, list[str]]:
    hits = [p for p in _matching(preds, r"child_order|birth_order|living_child|first_child|second_child|"
                                        r"girl|parity|number_of_children|children_count|child_count")]
    if any(re.search(r"girl|second", p.field) or (p.value == 2 and "order" in p.field) for p in hits):
        label = "first child, or second if a girl"
    elif hits:
        label = "first child only"
    else:
        label = "no child-order rule"
    return label, [_show(p) for p in hits]


def _presence(pattern: str, location: str | None = None):
    def check(preds) -> tuple[str, list[str]]:
        hits = [p for p in _matching(preds, pattern) if location is None or p.location == location]
        return ("present" if hits else "absent"), [_show(p) for p in hits]
    return check


def max_age(preds) -> tuple[str, list[str]]:
    hits = [p for p in preds if p.location == "inclusion" and p.field == "age" and p.op in ("<=", "<")]
    return (", ".join(f"{p.op} {p.value}" for p in hits) or "none"), [_show(p) for p in hits]


def age_70_branch(preds) -> tuple[str, list[str]]:
    hits = [p for p in preds if p.location == "inclusion" and ((p.field == "age" and p.op in (">=", ">")
            and isinstance(p.value, (int, float)) and 69 <= p.value <= 70) or re.search(r"senior|aged_70", p.field))]
    return ("present" if hits else "absent"), [_show(p) for p in hits]


def landholding_cap(preds) -> tuple[str, list[str]]:
    """An upper bound on land in the inclusion, or a 'more than N hectares' exclusion."""
    hits = [p for p in _matching(preds, r"land|hectare|acre")
            if (p.location == "inclusion" and p.op in ("<=", "<")) or (p.location == "exclusion" and p.op in (">", ">="))]
    return ("present" if hits else "absent"), [_show(p) for p in hits]


def monthly_income_threshold(preds) -> tuple[str, list[str]]:
    hits = [p for p in _matching(preds, r"income|earning") if "month" in p.field]
    return (", ".join(sorted({str(p.value) for p in hits})) or "none"), [_show(p) for p in hits]


# (check, detector, expected value by role); "post" is the current document's k=3 samples
CHECKS: dict[str, list[tuple[str, Callable, dict[str, str]]]] = {
    "PM-KISAN": [("2-hectare landholding limit (removed 1 June 2019)", landholding_cap, {"pre": "present", "post": "absent"})],
    "PMMVY": [("child-order rule", child_order_rule,
               {"pre": "first child only", "post": "first child, or second if a girl"})],
    "MH-LADKI-BAHIN": [
        ("five-acre land exclusion (retired 03.07.2024)", _presence(r"land|acre"),
         {"pre": "present", "post": "absent", "post_marathi": "absent"}),
        ("upper age bound (60 -> 65 on 03.07.2024)", max_age,
         {"pre": "<= 60", "post": "<= 65", "post_marathi": "<= 65"}),
    ],
    "AB-PMJAY": [("70+ branch (added 2024; nothing retired)", age_70_branch, {"pre": "absent", "post": "present"})],
    "PMAY-G": [
        ("refrigerator exclusion (deleted 2024)", _presence(r"refrig|fridge"),
         {"pre": "present", "stale": "present", "post": "absent"}),
        ("landline exclusion (deleted 2024)", _presence(r"landline|telephone|phone"),
         {"pre": "present", "stale": "present", "post": "absent"}),
        ("monthly income threshold (10000 -> 15000)", monthly_income_threshold,
         {"pre": "10000", "stale": "15000", "post": "15000"}),
    ],
}


def _samples(sid: str) -> list[tuple[str, str, Path]]:
    """(arm label, role, path) for every sample of the scheme: the new arms plus the k=3 post samples."""
    out = [(a.name, a.role, p) for a in ARMS if a.scheme_id == sid for p in sorted((OUT / a.name).glob("sample_*.json"))]
    post = sorted((harness.EXPERIMENTS_DIR / "self_consistency" / sid).glob("sample_*.json"))
    return out + [(f"{sid}__post_current_document (k=3 self-consistency)", "post", p) for p in post]


def score() -> dict:
    rows = []
    for sid, checks in CHECKS.items():
        for arm, role, path in _samples(sid):
            payload = json.loads(path.read_text(encoding="utf-8"))
            row = {"scheme": sid, "arm": arm, "role": role, "sample": path.stem,
                   "file": path.relative_to(harness.EXPERIMENTS_DIR).as_posix()}
            if "draft_extraction" not in payload:
                rows.append({**row, "status": f"extraction failed: {payload.get('failure', {}).get('reason')}"})
                rows[-1]["checks"] = []
                continue
            scheme = Scheme.model_validate(payload["draft_extraction"])
            preds = flatten_scheme(scheme)
            sup = scheme.temporal_validity.supersedes
            row.update(status="ok", supersedes_recorded=(sup.retired_predicate if sup else None), checks=[])
            for name, detect, expected in checks:
                value, matched = detect(preds)
                want = expected.get(role)
                row["checks"].append({"check": name, "value": value, "expected": want,
                                      "as_expected": None if want is None else value == want, "matched": matched})
            rows.append(row)
    summary = []
    for sid, checks in CHECKS.items():
        for name, _, expected in checks:
            for role in expected:
                vals = [c for r in rows if r["scheme"] == sid and r["role"] == role for c in r["checks"] if c["check"] == name]
                failed = sum(1 for r in rows if r["scheme"] == sid and r["role"] == role and r["status"] != "ok")
                summary.append({"scheme": sid, "check": name, "role": role, "expected": expected[role],
                                "as_expected": sum(1 for c in vals if c["as_expected"]), "valid_samples": len(vals),
                                "failed_samples": failed, "values": [c["value"] for c in vals]})
    return {**harness.result_header("temporal_c4_score", "none (offline)", {"detectors": "field-name/value patterns; see rows[].checks[].matched"}),
            "dropped": DROPPED, "summary": summary, "rows": rows}


ROLE_LABEL = {"pre": "pre-amendment text", "post": "current document (k=3)", "post_marathi": "Marathi GRs in order",
              "stale": "stale document"}


def markdown(s: dict) -> str:
    lines = [
        "# Temporal case study (C4)",
        "",
        f"*Generated {s['date']} by `scripts/run_temporal_case_study.py --score` from `data/experiments/temporal_c4/` "
        f"and `data/experiments/self_consistency/`. Gold tag {s['gold_tag']}; extractor defaults; Groq "
        f"`{harness.MODEL}`.*",
        "",
        "**Small sample.** One extraction per pre-amendment text (k=1) and three per current document (k=3); "
        "the Marathi arm and PMAY-G's pre-amendment arm are k=3 (the latter after its first sample missed the whole "
        "exclusion list). A single pre-amendment sample shows what the extractor *can* read from that text, "
        "not a rate. A valid sample that misses the rule entirely counts against \"as expected\".",
        "",
        "| Scheme | Check | Source | Expected | As expected | Values seen |",
        "|---|---|---|---|---|---|",
    ]
    for r in s["summary"]:
        n = (f"{r['as_expected']}/{r['valid_samples']}" + (f" (+{r['failed_samples']} failed)" if r["failed_samples"] else "")
             if r["valid_samples"] or r["failed_samples"] else "*not run yet*")
        lines.append(f"| {r['scheme']} | {r['check']} | {ROLE_LABEL[r['role']]} | {r['expected']} | {n} | "
                     f"{'; '.join(r['values']) or '—'} |")
    lines += ["", "## Dropped", ""] + ([f"- **{k}**: {v}" for k, v in s["dropped"].items()] or [
        "None: official pre-amendment text was found for every listed scheme (sources in each arm's result file)."])
    lines += ["", "## Per sample (matched predicates)", ""]
    for r in s["rows"]:
        lines.append(f"- **{r['arm']}** {r['sample']}: {r['status']}"
                     + (f"; supersedes recorded: `{json.dumps(r['supersedes_recorded'], ensure_ascii=False)}`" if r.get("supersedes_recorded") else ""))
        for c in r["checks"]:
            lines.append(f"  - {c['check']}: **{c['value']}** — {'; '.join(c['matched']) or 'no matching predicate'}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--score" in args:
        s = score()
        out = harness.EXPERIMENTS_DIR / f"temporal_c4_{s['date']}.json"
        out.write_text(json.dumps(s, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (ROOT / "docs" / "results" / "TEMPORAL_C4.md").write_text(markdown(s), encoding="utf-8")
        print(f"written: {out.relative_to(ROOT)}, docs/results/TEMPORAL_C4.md")
        sys.exit(0)
    if "--show" in args:  # print each arm's document and its size, no LLM call
        for a in ARMS:
            print(f"===== {a.name}\n{document(a)}\n")
        sys.exit(0)
    budget = int(next((a.split("=", 1)[1] for a in args if a.startswith("--budget=")), harness.DAILY_BUDGET))
    print(f"stopped: {run(budget)}", flush=True)
