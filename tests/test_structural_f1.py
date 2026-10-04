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
    # matches the reported "8/9 exact field matches" -- the manual report predates exception scoring;
    # the draft also gets both Group D exceptions right, which the metric now counts separately
    assert result.overall.tp - result.category_metrics["exception_to_exclusion"].tp == 8
    assert result.category_metrics["exception_to_exclusion"].tp == 2


# --- exceptions are scored (2026-10-04) ------------------------------------------------------------
# Before, a changed `except` could never move the metric: AB-PMJAY scored 1.000 before and after a gold
# fix that changed real verdicts. Each exception is now its own predicate, paired through its
# exclusion, charged to the C3 "exceptions-to-exclusions" category.

import subprocess  # noqa: E402

import pytest  # noqa: E402

from schemelogic.evaluation.structural_f1 import EXCEPTION_CATEGORY  # noqa: E402

_GROUP_D = {"field": "is_group_d", "op": "==", "value": True}


def _with_exception(exception: dict | None, scope: str | None = None, field: str = "holds_office") -> Scheme:
    data = json.loads(GOLD.model_dump_json(by_alias=True))
    for excl in data["exclusions"]:
        if excl["field"] == field:
            excl["except"] = exception
            if scope:
                excl["except_scope"] = scope
    return Scheme.model_validate(data)


GOLD_WITH_EXCEPTION = _with_exception(_GROUP_D)


def test_flatten_scheme_includes_each_exception_once():
    flat = flatten_scheme(GOLD_WITH_EXCEPTION)
    exceptions = [p for p in flat if p.location == "exception"]
    assert [(p.parent_field, p.field, p.cat) for p in exceptions] == [("holds_office", "is_group_d", EXCEPTION_CATEGORY)]


def test_identical_exceptions_are_a_true_positive():
    result = compare_schemes(GOLD_WITH_EXCEPTION, GOLD_WITH_EXCEPTION)
    assert result.category_metrics[EXCEPTION_CATEGORY].tp == 1
    assert result.overall.f1 == 1.0
    assert result.exception_diff["exact_matches"] == [{"field": "holds_office"}]


def test_a_missing_exception_is_a_false_negative_and_the_exclusion_still_matches():
    result = compare_schemes(GOLD_WITH_EXCEPTION, GOLD)
    assert result.category_metrics[EXCEPTION_CATEGORY].fn == 1
    assert result.category_metrics["political"].tp == 1  # the exclusion itself is unaffected
    assert result.overall.f1 < 1.0


def test_a_hallucinated_exception_is_a_false_positive():
    result = compare_schemes(GOLD, GOLD_WITH_EXCEPTION)
    assert result.category_metrics[EXCEPTION_CATEGORY].fp == 1
    assert result.exception_diff["hallucinated"][0]["exclusion"] == "holds_office"


@pytest.mark.parametrize("draft_exception,scope", [
    ({"field": "is_group_d", "op": "==", "value": False}, None),        # wrong value
    ({"field": "is_class_iv", "op": "==", "value": True}, None),        # wrong field
    (_GROUP_D, "applicant"),                                            # wrong scope
])
def test_a_wrong_exception_counts_as_both_fp_and_fn(draft_exception, scope):
    result = compare_schemes(GOLD_WITH_EXCEPTION, _with_exception(draft_exception, scope))
    m = result.category_metrics[EXCEPTION_CATEGORY]
    assert (m.tp, m.fp, m.fn) == (0, 1, 1)
    assert result.exception_diff["present_but_wrong"][0]["field"] == "holds_office"


def test_an_exception_is_paired_through_its_own_exclusion():
    """The same exception on a different exclusion is not a match."""
    result = compare_schemes(GOLD_WITH_EXCEPTION, _with_exception(_GROUP_D, field="is_wealthy"))
    m = result.category_metrics[EXCEPTION_CATEGORY]
    assert (m.tp, m.fp, m.fn) == (0, 1, 1)


def test_an_exception_on_the_same_field_as_another_predicate_does_not_collide():
    """AB-PMJAY: the inclusion and all 14 exceptions read `age`. Keyed by field alone they collapsed."""
    gold = _with_exception({"field": "age", "op": ">=", "value": 70}, field="is_wealthy")
    result = compare_schemes(gold, gold)
    assert result.overall.tp == len(flatten_scheme(gold)) == 5
    assert result.overall.f1 == 1.0


def test_the_ab_pmjay_70_plus_fix_now_moves_the_metric():
    """The case that exposed the gap: the 2026-10-03 fix added 14 exceptions and scored 1.000 -> 1.000."""
    def at(ref: str) -> Scheme:
        return Scheme.model_validate_json(subprocess.check_output(["git", "show", f"{ref}:data/gold/AB-PMJAY.json"]))

    draft = Scheme.model_validate(json.loads(Path(
        "data/extraction_runs/AB-PMJAY_gpt-oss-120b_gated_20260818T025520.json").read_text(encoding="utf-8"))["gated_extraction"])
    before, after = compare_schemes(at("5662498"), draft), compare_schemes(at("f6571a9"), draft)  # pre-fix, post-fix
    assert before.overall.f1 == 1.0
    assert after.category_metrics[EXCEPTION_CATEGORY].fn == 14
    assert after.overall.f1 < 1.0
