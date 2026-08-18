import json
from pathlib import Path

from schemelogic.evaluation.structural_f1 import build_batch_report, compare_schemes, flatten_scheme
from schemelogic.schema.models import Scheme

GOLD = Scheme.model_validate(
    {
        "scheme_id": "TEST",
        "unit_of_eligibility": "individual",
        "inclusion": {
            "and": [
                {"cat": "demographic", "field": "age", "op": ">=", "value": 18},
                {"cat": "citizenship", "field": "is_citizen", "op": "==", "value": True},
            ]
        },
        "exclusions": [
            {"cat": "economic", "quantifier": "self", "field": "is_wealthy", "op": "==", "value": True},
            {"cat": "political", "quantifier": "some_family_member", "field": "holds_office", "op": "==", "value": True},
        ],
        "temporal_validity": {"valid_from": "2020-01-01", "extracted_at": "2026-01-01"},
        "extraction_metadata": {"confidence": 1.0, "source_clause": "t", "flagged_for_review": False},
    }
)


def _draft(overrides: dict) -> Scheme:
    base = json.loads(GOLD.model_dump_json(by_alias=True))
    base.update(overrides)
    return Scheme.model_validate(base)


def test_flatten_scheme_counts_inclusion_and_exclusion():
    flat = flatten_scheme(GOLD)
    assert len(flat) == 4
    assert {p.location for p in flat} == {"inclusion", "exclusion"}


def test_identical_schemes_perfect_f1():
    result = compare_schemes(GOLD, GOLD)
    assert result.overall.tp == 4
    assert result.overall.fp == 0
    assert result.overall.fn == 0
    assert result.overall.precision == 1.0
    assert result.overall.recall == 1.0
    assert result.overall.f1 == 1.0
    assert result.inclusion_diff["missing"] == []
    assert result.inclusion_diff["hallucinated"] == []


def test_missing_predicate_is_a_false_negative():
    draft = _draft({"inclusion": {"cat": "demographic", "field": "age", "op": ">=", "value": 18}})
    result = compare_schemes(GOLD, draft)
    assert any(m["field"] == "is_citizen" for m in result.inclusion_diff["missing"])
    assert result.category_metrics["citizenship"].fn == 1
    assert result.category_metrics["citizenship"].tp == 0


def test_hallucinated_predicate_is_a_false_positive_under_draft_category():
    draft = _draft(
        {
            "inclusion": {
                "and": [
                    {"cat": "demographic", "field": "age", "op": ">=", "value": 18},
                    {"cat": "citizenship", "field": "is_citizen", "op": "==", "value": True},
                    {"cat": "other", "field": "made_up_field", "op": "==", "value": True},
                ]
            }
        }
    )
    result = compare_schemes(GOLD, draft)
    assert any(m["field"] == "made_up_field" for m in result.inclusion_diff["hallucinated"])
    assert result.category_metrics["other"].fp == 1


def test_wrong_value_counts_as_both_fp_and_fn():
    draft = _draft(
        {
            "exclusions": [
                {"cat": "economic", "quantifier": "self", "field": "is_wealthy", "op": "==", "value": False},
                {"cat": "political", "quantifier": "some_family_member", "field": "holds_office", "op": "==", "value": True},
            ]
        }
    )
    result = compare_schemes(GOLD, draft)
    assert any(m["field"] == "is_wealthy" for m in result.exclusion_diff["present_but_wrong"])
    econ = result.category_metrics["economic"]
    assert econ.fn == 1 and econ.fp == 1 and econ.tp == 0


def test_category_tag_mismatch_logged_separately_from_value_correctness():
    """Field/op/value all match but gold and draft disagree on the cat tag — still a TP for
    field-value correctness, but flagged as its own diagnostic."""
    draft = _draft(
        {
            "exclusions": [
                {"cat": "occupation", "quantifier": "self", "field": "is_wealthy", "op": "==", "value": True},
                {"cat": "political", "quantifier": "some_family_member", "field": "holds_office", "op": "==", "value": True},
            ]
        }
    )
    result = compare_schemes(GOLD, draft)
    assert result.category_metrics["economic"].tp == 1  # matched under GOLD's cat
    assert len(result.category_tag_mismatches) == 1
    assert result.category_tag_mismatches[0].field == "is_wealthy"
    assert result.category_tag_mismatches[0].gold_cat == "economic"
    assert result.category_tag_mismatches[0].draft_cat == "occupation"


def test_quantifier_mismatch_on_exclusion_counts_as_wrong_value():
    draft = _draft(
        {
            "exclusions": [
                {"cat": "economic", "quantifier": "all_family_members", "field": "is_wealthy", "op": "==", "value": True},
                {"cat": "political", "quantifier": "some_family_member", "field": "holds_office", "op": "==", "value": True},
            ]
        }
    )
    result = compare_schemes(GOLD, draft)
    assert any(m["field"] == "is_wealthy" for m in result.exclusion_diff["present_but_wrong"])


def test_build_batch_report_schema_validity_rate_counts_none_drafts():
    entries = [("TEST", GOLD, GOLD), ("FAILED", GOLD, None)]
    report = build_batch_report(entries)
    assert report.n_attempted == 2
    assert report.n_schema_valid == 1
    assert report.schema_validity_rate == 0.5
    assert len(report.per_scheme) == 1


def test_build_batch_report_aggregates_across_schemes():
    other_gold = Scheme.model_validate(
        {
            "scheme_id": "TEST2", "unit_of_eligibility": "individual",
            "inclusion": {"cat": "demographic", "field": "age", "op": ">=", "value": 21},
            "exclusions": [],
            "temporal_validity": {"valid_from": "2020-01-01", "extracted_at": "2026-01-01"},
            "extraction_metadata": {"confidence": 1.0, "source_clause": "t", "flagged_for_review": False},
        }
    )
    entries = [("TEST", GOLD, GOLD), ("TEST2", other_gold, other_gold)]
    report = build_batch_report(entries)
    assert report.aggregate_category_metrics["demographic"].tp == 2  # 1 from each scheme
    assert report.aggregate_overall.tp == 5  # 4 (TEST) + 1 (TEST2)


# --- Real-data sanity check against the 3 already-manually-verified schemes ---------------------


def _latest_ontology_draft(scheme_id: str) -> Scheme:
    import glob

    runs = sorted(glob.glob(f"data/extraction_runs/{scheme_id}_gpt-oss-120b_ontology_*.json"))
    runs = [r for r in runs if "draft_extraction" in json.loads(Path(r).read_text(encoding="utf-8"))]
    draft_dump = json.loads(Path(runs[-1]).read_text(encoding="utf-8"))["draft_extraction"]
    return Scheme.model_validate(draft_dump)


def test_pm_kisan_structural_f1_matches_manual_report():
    gold = Scheme.model_validate(json.loads(Path("data/gold/PM-KISAN.json").read_text(encoding="utf-8")))
    draft = _latest_ontology_draft("PM-KISAN")
    result = compare_schemes(gold, draft)
    missing_fields = {m["field"] for m in result.inclusion_diff["missing"] + result.exclusion_diff["missing"]}
    assert missing_fields == {"is_indian_citizen"}  # the one confirmed-recurring gap, per the manual report
    assert result.overall.tp == 8  # matches the reported "8/9 exact field matches"
