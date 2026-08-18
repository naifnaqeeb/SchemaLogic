from schemelogic.conversational.question_selector import (
    build_question,
    find_missing_fields,
    select_next_question,
)
from schemelogic.evaluator.symbolic_engine import evaluate
from schemelogic.schema.models import Scheme

SCHEME = Scheme.model_validate(
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


def test_find_missing_fields_empty_profile_finds_inclusion_fields_first():
    result = evaluate(SCHEME, {"self": {}, "family_members": []})
    missing = find_missing_fields(result)
    fields = [m.field for m in missing]
    # inclusion tree walked before exclusions, left-to-right within the AND
    assert fields[0] == "age"
    assert fields[1] == "is_citizen"


def test_find_missing_fields_stops_asking_about_answered_fields():
    result = evaluate(SCHEME, {"self": {"age": 25}, "family_members": []})
    missing = find_missing_fields(result)
    assert "age" not in [m.field for m in missing]
    assert "is_citizen" in [m.field for m in missing]


def test_select_next_question_returns_first_missing_inclusion_field():
    q = select_next_question(SCHEME, {"self": {}, "family_members": []})
    assert q is not None
    assert q.field == "age"
    assert q.answer_type == "number"
    assert q.quick_replies is None


def test_boolean_field_gets_yes_no_quick_replies():
    q = select_next_question(SCHEME, {"self": {"age": 25}, "family_members": []})
    assert q is not None
    assert q.field == "is_citizen"
    assert q.answer_type == "boolean"
    assert q.quick_replies == ("Yes", "No")


def test_moves_to_exclusions_once_inclusion_resolved():
    profile = {"self": {"age": 25, "is_citizen": True}, "family_members": []}
    q = select_next_question(SCHEME, profile)
    assert q is not None
    assert q.field == "is_wealthy"


def test_returns_none_once_verdict_is_definite_eligible():
    # some_family_member quantifier includes "self" as a checkable member -- must be answered too.
    profile = {
        "self": {"age": 25, "is_citizen": True, "is_wealthy": False, "holds_office": False},
        "family_members": [],
    }
    q = select_next_question(SCHEME, profile)
    assert q is None


def test_returns_none_once_verdict_is_definite_ineligible():
    """Inclusion still partially unknown, but an exclusion already definitely fires -- verdict is
    already INELIGIBLE, so no more questions needed even though age/is_citizen are unanswered."""
    profile = {"self": {"is_wealthy": True}, "family_members": []}
    q = select_next_question(SCHEME, profile)
    assert q is None


def test_family_member_exclusion_produces_family_member_question():
    # self's own holds_office already answered -- only family_member[0]'s is left missing.
    profile = {
        "self": {"age": 25, "is_citizen": True, "is_wealthy": False, "holds_office": False},
        "family_members": [{}],
    }
    q = select_next_question(SCHEME, profile)
    assert q is not None
    assert q.field == "holds_office"
    assert q.member == "family_member[0]"
    assert "family member" in q.prompt


def test_build_question_prompt_is_grammatical_and_contains_description():
    from schemelogic.conversational.question_selector import MissingField

    q = build_question(MissingField(field="is_indian_citizen", member="self", cat="citizenship", expected_value=True))
    assert "you" in q.prompt
    assert q.answer_type == "boolean"


def test_unknown_field_falls_back_to_humanized_name():
    from schemelogic.conversational.question_selector import MissingField

    q = build_question(MissingField(field="some_made_up_field", member="self", cat=None, expected_value=True))
    assert "some made up field" in q.prompt


def test_known_field_uses_ontology_citizen_question_verbatim():
    """Part A's core guarantee: the primary chat question comes from citizen_question, never the
    technical `description` field."""
    from schemelogic.conversational.question_selector import MissingField
    from schemelogic.schema.field_ontology import get_field

    spec = get_field("is_secc_deprived_household")
    q = build_question(MissingField(field="is_secc_deprived_household", member="self", cat="economic", expected_value=True))
    assert q.prompt == spec.citizen_question
    assert "SECC" not in q.prompt  # the technical description's jargon must never leak through
    assert "D1" not in q.prompt


def test_family_member_question_uses_third_person_swap_of_real_ontology_text():
    from schemelogic.conversational.question_selector import MissingField

    q = build_question(MissingField(field="is_woman", member="family_member[0]", cat="demographic", expected_value=True))
    assert "Are they a woman?" in q.prompt
    assert "Are you" not in q.prompt


def test_second_to_third_person_handles_subject_object_and_possessive():
    from schemelogic.conversational.question_selector import _second_to_third_person

    assert _second_to_third_person("Are you a woman?") == "Are they a woman?"
    assert _second_to_third_person("Does your household own a refrigerator?") == "Does their household own a refrigerator?"
    assert _second_to_third_person("Is this for you?") == "Is this for them?"
