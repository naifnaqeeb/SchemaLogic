"""field_phrasing.py: generated citizen questions for fields the canonical ontology doesn't cover.

Provider calls are mocked throughout (tests/conftest.py also hard-defaults them to failure, so an
un-mocked call here degrades to the fallback rather than reaching the network). The disk cache is
redirected to tmp_path so tests never touch data/cache/.

What matters most in here is the NEGATIVE space: this module adds an LLM call to the live chat
path, so every way it can fail must leave the conversation exactly as good as it was before.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from schemelogic.conversational import field_phrasing
from schemelogic.llm.provider import ProviderFailure, ProviderResult
from schemelogic.schema import field_ontology
from schemelogic.schema.models import Scheme

NOVEL_SCHEME = {
    "scheme_id": "NOVEL",
    "unit_of_eligibility": "individual",
    "inclusion": {
        "and": [
            {"cat": "citizenship", "field": "is_indian_citizen", "op": "==", "value": True},
            {"cat": "other", "field": "is_forward_community", "op": "==", "value": True,
             "ontology_proposed": True},
            {"cat": "demographic", "field": "bride_education_10th_passed", "op": "==", "value": True,
             "ontology_proposed": True},
        ]
    },
    "exclusions": [
        {"cat": "economic", "quantifier": "self", "field": "coffee_holdings_hectares", "op": ">",
         "value": 5, "ontology_proposed": True},
    ],
    "temporal_validity": {"valid_from": "2020-01-01", "extracted_at": "2026-01-01"},
    "extraction_metadata": {"confidence": 0.5, "source_clause": "x", "flagged_for_review": True},
}


@pytest.fixture(autouse=True)
def _isolated_caches(tmp_path, monkeypatch):
    monkeypatch.setattr(field_phrasing, "DISK_CACHE_PATH", tmp_path / "field_questions.json")
    field_ontology.clear_registered_citizen_questions()
    yield
    field_ontology.clear_registered_citizen_questions()


def _ok(content: str):
    return patch(
        "schemelogic.conversational.field_phrasing.chat_completion_with_fallback",
        return_value=ProviderResult(content=content, provider_used="groq"),
    )


def _down():
    return patch(
        "schemelogic.conversational.field_phrasing.chat_completion_with_fallback",
        return_value=ProviderFailure(primary_error="x", secondary_error="y"),
    )


# --- the happy path -----------------------------------------------------------------------------


def test_generates_a_question_for_a_novel_field():
    with _ok("Do you belong to a Forward Community?"):
        q = field_phrasing.phrase_field_question("is_forward_community")
    assert q == "Do you belong to a Forward Community?"


def test_registered_question_is_what_the_ontology_now_returns():
    """The whole integration: question_selector reads citizen_question_for(), so registering here
    is what actually changes the question a citizen sees."""
    assert field_ontology.citizen_question_for("is_forward_community") is None
    with _ok("Do you belong to a Forward Community?"):
        field_phrasing.ensure_questions_for_scheme(Scheme.model_validate(NOVEL_SCHEME))
    assert field_ontology.citizen_question_for("is_forward_community") == "Do you belong to a Forward Community?"


def test_ensure_returns_count_and_skips_canonical_fields():
    with _ok("Have you got a thing you can answer about?"):
        n = field_phrasing.ensure_questions_for_scheme(Scheme.model_validate(NOVEL_SCHEME))
    # 3 novel fields; is_indian_citizen is canonical and must be left alone
    assert n == 3
    assert "is_indian_citizen" not in field_ontology.registered_citizen_questions()


def test_canonical_field_phrasing_is_never_overridden():
    canonical = field_ontology.citizen_question_for("is_indian_citizen")
    assert canonical
    assert field_ontology.register_citizen_question("is_indian_citizen", "Some generated thing?") is False
    assert field_ontology.citizen_question_for("is_indian_citizen") == canonical


def test_no_llm_call_for_a_canonical_field():
    with patch("schemelogic.conversational.field_phrasing.chat_completion_with_fallback") as call:
        assert field_phrasing.phrase_field_question("is_indian_citizen") is None
    call.assert_not_called()


# --- failure is always survivable ---------------------------------------------------------------


def test_provider_failure_returns_none_so_the_caller_keeps_its_fallback():
    with _down():
        assert field_phrasing.phrase_field_question("is_forward_community") is None
    assert field_ontology.citizen_question_for("is_forward_community") is None


def test_unexpected_exception_does_not_propagate_into_the_chat():
    with patch(
        "schemelogic.conversational.field_phrasing.chat_completion_with_fallback",
        side_effect=RuntimeError("boom"),
    ):
        assert field_phrasing.phrase_field_question("is_forward_community") is None


def test_failures_are_not_cached_so_an_outage_is_not_permanent():
    with _down():
        field_phrasing.phrase_field_question("is_forward_community")
    with _ok("Do you belong to a Forward Community?"):
        q = field_phrasing.phrase_field_question("is_forward_community")
    assert q == "Do you belong to a Forward Community?"


@pytest.mark.parametrize(
    "bad,why",
    [
        ("Is the applicant's income above 50000?", "invents a numeric threshold"),
        ("Do you earn more than ₹10,000 a month?", "invents a currency amount"),
        ("Were you married after 2019?", "invents a date"),
        ("is_forward_community", "not a question, echoes the field name"),
        ("Forward community.", "not a question"),
        ("?", "too short"),
        ("Do you meet the criterion " + "x" * 200 + "?", "too long"),
        ("Is this person a member?", "does not address the citizen as you"),
        ("Do you belong to a Forward Community?\nAlso, what is your name?", "multiple lines"),
    ],
)
def test_implausible_generations_are_rejected_in_favour_of_the_fallback(bad, why):
    """A rejected generation costs only the old generic phrasing; an accepted bad one is shown to
    a citizen as though the system understood the rule. Numbers/dates/amounts are rejected because
    the predicate's threshold belongs to the evaluator -- a question must ask for the citizen's
    fact, never assert the rule."""
    with _ok(bad):
        assert field_phrasing.phrase_field_question("is_forward_community") is None, why


def test_a_number_already_in_the_field_name_is_allowed_through():
    """Rejecting every digit blocked fields that can't be asked about without one --
    `bride_education_10th_passed` needs to say "10th". Only digits the model introduced by itself
    count as fabrication (2026-09-18)."""
    with _ok("Has the bride passed the 10th standard?"):
        q = field_phrasing.phrase_field_question("bride_education_10th_passed")
    assert q == "Has the bride passed the 10th standard?"


def test_a_number_not_in_the_field_name_is_still_rejected():
    with _ok("Has the bride passed the 12th standard?"):
        assert field_phrasing.phrase_field_question("bride_education_10th_passed") is None


def test_question_about_a_named_third_party_subject_is_accepted():
    """The prompt asks for the field's subject to be preserved, so a question about the bride must
    not then be rejected for failing to say "you" -- those two rules contradicted each other and
    the contradiction silently kept good questions off the screen."""
    with _ok("Is the bride's education up to the 5th standard?"):
        q = field_phrasing.phrase_field_question("bride_education_up_to_5th")
    assert q == "Is the bride's education up to the 5th standard?"


def test_question_unrelated_to_the_field_and_not_addressed_to_you_is_rejected():
    with _ok("Is this person a member?"):
        assert field_phrasing.phrase_field_question("is_forward_community") is None


def test_scheme_context_is_sent_so_domain_terms_are_read_correctly():
    """Without the scheme name, `is_forward_community` was rendered "forward-thinking community"
    -- a confident wrong question, worse than the fallback it replaced."""
    with _ok("Are you a member of the Forward Community?") as call:
        field_phrasing.phrase_field_question(
            "is_forward_community", scheme_context="Inter-caste Marriage Assistance Scheme"
        )
    user_msg = call.call_args.args[0][1]["content"]
    assert "Inter-caste Marriage Assistance Scheme" in user_msg


def test_official_category_names_are_named_in_the_prompt():
    prompt = field_phrasing._system_prompt("boolean")
    for term in ("Forward Community", "Backward Class", "Scheduled Caste", "Group D"):
        assert term in prompt
    assert "PRESERVE THE SUBJECT" in prompt


# --- caching ------------------------------------------------------------------------------------


def test_second_call_for_same_field_uses_cache_not_a_second_llm_call():
    with _ok("Do you belong to a Forward Community?") as call:
        field_phrasing.phrase_field_question("is_forward_community")
        field_phrasing.phrase_field_question("is_forward_community")
    assert call.call_count == 1


def test_cache_persists_to_disk_and_preloads_without_any_llm_call():
    with _ok("Do you belong to a Forward Community?"):
        field_phrasing.phrase_field_question("is_forward_community")
    assert json.loads(field_phrasing.DISK_CACHE_PATH.read_text(encoding="utf-8")) == {
        "is_forward_community": "Do you belong to a Forward Community?"
    }

    field_ontology.clear_registered_citizen_questions()
    with patch("schemelogic.conversational.field_phrasing.chat_completion_with_fallback") as call:
        assert field_phrasing.preload_registered_questions() == 1
    call.assert_not_called()
    assert field_ontology.citizen_question_for("is_forward_community") == "Do you belong to a Forward Community?"


def test_corrupt_disk_cache_degrades_to_no_cache_not_a_crash():
    field_phrasing.DISK_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    field_phrasing.DISK_CACHE_PATH.write_text("{not json", encoding="utf-8")
    with _ok("Do you belong to a Forward Community?"):
        assert field_phrasing.phrase_field_question("is_forward_community")


# --- answer-type awareness ----------------------------------------------------------------------


def test_number_field_asks_for_a_number_not_a_yes_no():
    """The generated question must match the answer affordance question_selector will give: a
    number field gets free text, a boolean gets Yes/No buttons."""
    with _ok("How many hectares of coffee do you hold?") as call:
        field_phrasing.ensure_questions_for_scheme(Scheme.model_validate(NOVEL_SCHEME))
    prompts = [c.kwargs.get("messages", c.args[0] if c.args else [])[0]["content"] for c in call.call_args_list]
    number_prompt = [p for p in prompts if "single number" in p]
    assert number_prompt, "the numeric field's prompt should ask for a number-shaped question"
