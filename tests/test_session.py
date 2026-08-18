import pytest

from schemelogic.conversational.session import AnswerParseError, ConversationSession
from schemelogic.evaluator.symbolic_engine import Verdict
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
        ],
        "temporal_validity": {"valid_from": "2020-01-01", "extracted_at": "2026-01-01"},
        "extraction_metadata": {"confidence": 1.0, "source_clause": "t", "flagged_for_review": False},
    }
)


def test_new_session_starts_with_empty_profile():
    session = ConversationSession(scheme=SCHEME)
    assert session.profile == {"self": {}, "family_members": []}
    assert session.pending_question is None


def test_advance_sets_pending_question_for_first_missing_field():
    session = ConversationSession(scheme=SCHEME)
    q = session.advance()
    assert q is not None
    assert q.field == "age"
    assert session.pending_question is q
    assert session.turns[-1] == {"role": "assistant", "text": q.prompt}


def test_apply_answer_writes_to_profile_and_clears_pending():
    session = ConversationSession(scheme=SCHEME)
    session.advance()  # pending: age (number)
    session.apply_answer("25")
    assert session.profile["self"]["age"] == 25
    assert session.pending_question is None
    assert session.turns[-1] == {"role": "user", "text": "25"}


def test_apply_answer_boolean_parses_yes_no():
    session = ConversationSession(scheme=SCHEME)
    session.profile["self"]["age"] = 25
    session.advance()  # pending: is_citizen (boolean)
    assert session.pending_question.field == "is_citizen"
    session.apply_answer("yes")
    assert session.profile["self"]["is_citizen"] is True


def test_apply_answer_bad_boolean_raises_and_leaves_pending_intact():
    session = ConversationSession(scheme=SCHEME)
    session.advance()
    with pytest.raises(AnswerParseError):
        session.apply_answer("maybe")
    assert session.pending_question is not None  # not cleared on bad input
    assert "age" not in session.profile["self"]  # not silently written either


def test_apply_answer_bad_number_raises():
    session = ConversationSession(scheme=SCHEME)
    session.advance()  # pending: age
    with pytest.raises(AnswerParseError):
        session.apply_answer("not a number")


def test_apply_answer_without_pending_question_raises():
    session = ConversationSession(scheme=SCHEME)
    with pytest.raises(RuntimeError):
        session.apply_answer("25")


def test_full_flow_reaches_definite_verdict():
    session = ConversationSession(scheme=SCHEME)
    session.advance()
    session.apply_answer("25")  # age
    session.advance()
    session.apply_answer("yes")  # is_citizen
    session.advance()
    session.apply_answer("no")  # is_wealthy
    q = session.advance()
    assert q is None
    assert session.is_resolved()
    assert session.current_result().verdict == Verdict.ELIGIBLE


def test_family_member_field_written_to_correct_index():
    session = ConversationSession(scheme=SCHEME)
    session.profile["family_members"] = [{}]
    from schemelogic.conversational.question_selector import Question

    session.pending_question = Question(
        field="some_field", member="family_member[0]", answer_type="boolean",
        prompt="test", quick_replies=("Yes", "No"),
    )
    session.apply_answer("yes")
    assert session.profile["family_members"][0]["some_field"] is True


def test_family_member_dict_grows_list_if_needed():
    session = ConversationSession(scheme=SCHEME)
    from schemelogic.conversational.question_selector import Question

    session.pending_question = Question(
        field="some_field", member="family_member[2]", answer_type="boolean",
        prompt="test", quick_replies=("Yes", "No"),
    )
    session.apply_answer("yes")
    assert len(session.profile["family_members"]) == 3
    assert session.profile["family_members"][2]["some_field"] is True
