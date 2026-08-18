from pathlib import Path

from schemelogic.annotation.rendering import (
    exclusion_to_english,
    inclusion_node_to_english,
    load_deferred_findings,
    predicate_to_english,
    scheme_to_english,
    trace_to_citizen_english,
)
from schemelogic.evaluator.symbolic_engine import evaluate
from schemelogic.schema.models import Scheme
from tests.fixtures import PM_KISAN

PM_KISAN_SCHEME = Scheme.model_validate(PM_KISAN)


def test_predicate_to_english_is_readable_not_raw_json():
    text = predicate_to_english(PM_KISAN_SCHEME.inclusion.and_[0])
    assert "is indian citizen" in text
    assert "True" in text
    assert "{" not in text  # not raw JSON


def test_inclusion_node_to_english_renders_and_structure():
    text = inclusion_node_to_english(PM_KISAN_SCHEME.inclusion)
    assert "ALL of:" in text
    assert "is indian citizen" in text
    assert "owns cultivable land in records" in text


def test_exclusion_to_english_includes_quantifier_and_except():
    govt_employee_exclusion = PM_KISAN_SCHEME.exclusions[1]
    text = exclusion_to_english(govt_employee_exclusion)
    assert "EXCLUDE if some family member" in text
    assert "EXCEPT" in text
    assert "group d" in text.lower()


def test_exclusion_to_english_self_quantifier_phrasing():
    institutional = PM_KISAN_SCHEME.exclusions[5]
    text = exclusion_to_english(institutional)
    assert "EXCLUDE if the applicant" in text


def test_scheme_to_english_includes_all_sections():
    text = scheme_to_english(PM_KISAN_SCHEME)
    assert "Scheme: PM-KISAN" in text
    assert "INCLUSION" in text
    assert "EXCLUSIONS" in text
    assert text.count("EXCLUDE if") == len(PM_KISAN_SCHEME.exclusions)


def test_load_deferred_findings_only_returns_gate_deferred_items():
    root = Path(".")
    ignoaps_deferred = load_deferred_findings("IGNOAPS", root)
    assert len(ignoaps_deferred) == 2
    for item in ignoaps_deferred:
        assert item.decision.decision == "defer_to_review"
        assert item.decision.reasons  # human-readable reasons present
        assert item.proposed_english  # a concrete proposal, not just a vague flag


def test_load_deferred_findings_empty_for_scheme_without_judge_repair_run():
    root = Path(".")
    assert load_deferred_findings("NOT-A-REAL-SCHEME", root) == []


def test_trace_to_citizen_english_uses_display_labels_not_field_names():
    profile = {
        "self": {
            "is_indian_citizen": True, "owns_cultivable_land_in_records": True,
            "is_institutional_landholder": False,
            "paid_income_tax_last_assessment_year": False,
            "is_serving_or_retired_govt_employee": False, "is_group_d_class_iv_or_mts": False,
            "monthly_pension_inr": 0,
            "holds_constitutional_or_political_post": False, "holds_elected_or_nominated_govt_post": False,
            "is_practicing_registered_professional": False,
            "is_nri_per_income_tax_act_1961": False,
        },
        "family_members": [],
    }
    result = evaluate(PM_KISAN_SCHEME, profile)
    text = trace_to_citizen_english(result.trace)
    assert "is_indian_citizen" not in text  # raw field name must never leak through
    assert "Indian citizenship" in text  # display_label_for("is_indian_citizen")
    assert "{" not in text  # not raw JSON


def test_trace_to_citizen_english_shows_not_yet_known_for_missing_facts():
    result = evaluate(PM_KISAN_SCHEME, {"self": {}, "family_members": []})
    text = trace_to_citizen_english(result.trace)
    assert "Not yet known" in text


def test_trace_to_citizen_english_never_contains_technical_description_jargon():
    """Spot-checks a scheme whose technical description contains jargon a citizen-facing view
    must never surface (AB-PMJAY's is_secc_deprived_household mentions 'SECC 2011', 'D1/D2...')."""
    import json
    from pathlib import Path as P

    ab_pmjay = Scheme.model_validate(json.loads(P("data/gold/AB-PMJAY.json").read_text(encoding="utf-8")))
    result = evaluate(ab_pmjay, {"self": {}, "family_members": []})
    text = trace_to_citizen_english(result.trace)
    assert "SECC" not in text
    assert "D1" not in text
