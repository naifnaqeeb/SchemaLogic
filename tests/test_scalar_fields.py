import json

from schemelogic.evaluation.scalar_fields import SCALAR_FIELDS, check_scalar_fields
from schemelogic.schema.models import Scheme

GOLD = Scheme.model_validate(
    {
        "scheme_id": "TEST",
        "unit_of_eligibility": "individual",
        "inclusion": {"cat": "demographic", "field": "age", "op": ">=", "value": 18},
        "exclusions": [],
        "temporal_validity": {"valid_from": "2020-01-01", "extracted_at": "2026-01-01"},
        "extraction_metadata": {"confidence": 1.0, "source_clause": "t", "flagged_for_review": False},
    }
)


def _draft(overrides: dict) -> Scheme:
    base = json.loads(GOLD.model_dump_json(by_alias=True))
    for path, value in overrides.items():
        target = base
        *parents, leaf = path.split(".")
        for p in parents:
            target = target[p]
        target[leaf] = value
    return Scheme.model_validate(base)


def test_identical_schemes_no_mismatches():
    report = check_scalar_fields(GOLD, GOLD)
    assert report.mismatches == []
    assert report.match_rate == 1.0
    assert report.n_checked == len(SCALAR_FIELDS)


def test_unit_of_eligibility_mismatch_detected():
    draft = _draft({"unit_of_eligibility": "family"})
    report = check_scalar_fields(GOLD, draft)
    assert len(report.mismatches) == 1
    assert report.mismatches[0].field == "unit_of_eligibility"
    assert report.mismatches[0].gold_value == "individual"
    assert report.mismatches[0].draft_value == "family"
    assert report.match_rate == 0.5


def test_valid_from_mismatch_detected():
    draft = _draft({"temporal_validity.valid_from": "2024-09-10"})
    report = check_scalar_fields(GOLD, draft)
    assert len(report.mismatches) == 1
    assert report.mismatches[0].field == "temporal_validity.valid_from"


def test_both_scalar_fields_wrong():
    draft = _draft({"unit_of_eligibility": "family", "temporal_validity.valid_from": "2024-09-10"})
    report = check_scalar_fields(GOLD, draft)
    assert len(report.mismatches) == 2
    assert report.match_rate == 0.0


def test_to_dict_shape():
    draft = _draft({"unit_of_eligibility": "family"})
    d = check_scalar_fields(GOLD, draft).to_dict()
    assert d["scheme_id"] == "TEST"
    assert d["n_matched"] == 1
    assert d["mismatches"][0]["field"] == "unit_of_eligibility"
