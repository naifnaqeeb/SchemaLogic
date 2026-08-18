import copy

import pytest
from pydantic import ValidationError

from schemelogic.schema.models import Scheme
from tests.fixtures import PM_KISAN


def test_pm_kisan_parses():
    scheme = Scheme.model_validate(PM_KISAN)
    assert scheme.scheme_id == "PM-KISAN"
    assert scheme.unit_of_eligibility.value == "family"
    assert len(scheme.exclusions) == 7
    assert scheme.exclusions[1].except_.field == "is_group_d_class_iv_or_mts"


def test_round_trip_dump_and_reload():
    scheme = Scheme.model_validate(PM_KISAN)
    dumped = scheme.model_dump(mode="json", by_alias=True)
    reloaded = Scheme.model_validate(dumped)
    assert reloaded == scheme


def test_unknown_field_rejected():
    bad = copy.deepcopy(PM_KISAN)
    bad["not_a_real_field"] = 123
    with pytest.raises(ValidationError):
        Scheme.model_validate(bad)


def test_unknown_category_rejected():
    bad = copy.deepcopy(PM_KISAN)
    bad["inclusion"]["and"][0]["cat"] = "not_a_real_category"
    with pytest.raises(ValidationError):
        Scheme.model_validate(bad)


def test_unknown_operator_rejected():
    bad = copy.deepcopy(PM_KISAN)
    bad["inclusion"]["and"][0]["op"] = "~="
    with pytest.raises(ValidationError):
        Scheme.model_validate(bad)


def test_valid_to_before_valid_from_rejected():
    bad = copy.deepcopy(PM_KISAN)
    bad["temporal_validity"]["valid_from"] = "2024-01-01"
    bad["temporal_validity"]["valid_to"] = "2023-01-01"
    with pytest.raises(ValidationError):
        Scheme.model_validate(bad)


def test_confidence_out_of_range_rejected():
    bad = copy.deepcopy(PM_KISAN)
    bad["extraction_metadata"]["confidence"] = 1.5
    with pytest.raises(ValidationError):
        Scheme.model_validate(bad)


def test_except_predicate_has_no_cat_field():
    scheme = Scheme.model_validate(PM_KISAN)
    except_pred = scheme.exclusions[1].except_
    assert not hasattr(except_pred, "cat")


def test_nested_or_inclusion_parses():
    data = copy.deepcopy(PM_KISAN)
    data["inclusion"] = {
        "or": [
            {"cat": "citizenship", "field": "is_indian_citizen", "op": "==", "value": True},
            {
                "and": [
                    {"cat": "occupation", "field": "owns_cultivable_land_in_records", "op": "==", "value": True},
                ]
            },
        ]
    }
    scheme = Scheme.model_validate(data)
    assert scheme.inclusion.or_[1].and_[0].field == "owns_cultivable_land_in_records"


def test_simple_scheme_no_exclusions():
    data = copy.deepcopy(PM_KISAN)
    data["exclusions"] = []
    scheme = Scheme.model_validate(data)
    assert scheme.exclusions == []


# --- count_family_members quantifier (Phase 0.5 extension) ----------------------------


def _count_exclusion(**overrides) -> dict:
    base = {
        "cat": "family_unit",
        "quantifier": "count_family_members",
        "field": "is_below_poverty_line",
        "op": "==",
        "value": True,
        "count_op": ">=",
        "count": 2,
    }
    base.update(overrides)
    return base


def test_count_quantifier_with_count_op_and_count_parses():
    data = copy.deepcopy(PM_KISAN)
    data["exclusions"] = [_count_exclusion()]
    scheme = Scheme.model_validate(data)
    assert scheme.exclusions[0].count_op.value == ">="
    assert scheme.exclusions[0].count == 2


def test_count_quantifier_missing_count_op_rejected():
    data = copy.deepcopy(PM_KISAN)
    exclusion = _count_exclusion()
    del exclusion["count_op"]
    data["exclusions"] = [exclusion]
    with pytest.raises(ValidationError):
        Scheme.model_validate(data)


def test_count_quantifier_missing_count_rejected():
    data = copy.deepcopy(PM_KISAN)
    exclusion = _count_exclusion()
    del exclusion["count"]
    data["exclusions"] = [exclusion]
    with pytest.raises(ValidationError):
        Scheme.model_validate(data)


def test_count_fields_on_non_count_quantifier_rejected():
    """count_op/count must not silently coexist with some/all quantifier semantics."""
    data = copy.deepcopy(PM_KISAN)
    exclusion = _count_exclusion(quantifier="some_family_member")
    data["exclusions"] = [exclusion]
    with pytest.raises(ValidationError):
        Scheme.model_validate(data)


def test_negative_count_rejected():
    data = copy.deepcopy(PM_KISAN)
    data["exclusions"] = [_count_exclusion(count=-1)]
    with pytest.raises(ValidationError):
        Scheme.model_validate(data)


def test_unknown_count_operator_rejected():
    data = copy.deepcopy(PM_KISAN)
    data["exclusions"] = [_count_exclusion(count_op="~=")]
    with pytest.raises(ValidationError):
        Scheme.model_validate(data)
