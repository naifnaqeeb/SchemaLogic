"""All calls mocked -- no network, no API keys, no Groq quota touched."""

from unittest.mock import MagicMock, patch

from schemelogic.conversational.phrasing import (
    phrase_verdict,
    plain_template_answer,
    verdict_emoji,
    verdict_headline,
)
from schemelogic.evaluator.symbolic_engine import EvaluationResult, Verdict
from schemelogic.llm.provider import ProviderFailure, ProviderResult

_RESULT = EvaluationResult(
    verdict=Verdict.ELIGIBLE,
    trace={"scheme_id": "TEST-SCHEME", "verdict": "eligible", "inclusion": {}, "exclusions": []},
)


def test_plain_template_never_calls_llm_and_states_verdict():
    text = plain_template_answer(_RESULT)
    assert "eligible" in text
    assert "TEST-SCHEME" in text


def test_phrase_verdict_returns_llm_content_on_success():
    with patch(
        "schemelogic.conversational.phrasing.chat_completion_with_fallback",
        return_value=ProviderResult(content="Great news, you qualify!", provider_used="groq"),
    ):
        text = phrase_verdict(_RESULT)
    assert text == "Great news, you qualify!"


def test_phrase_verdict_falls_back_to_template_on_failure():
    with patch(
        "schemelogic.conversational.phrasing.chat_completion_with_fallback",
        return_value=ProviderFailure(primary_error="429", secondary_error="timeout"),
    ):
        text = phrase_verdict(_RESULT)
    assert text == plain_template_answer(_RESULT)


def test_phrase_verdict_never_raises_on_failure():
    with patch(
        "schemelogic.conversational.phrasing.chat_completion_with_fallback",
        return_value=ProviderFailure(primary_error="x", secondary_error="y"),
    ):
        text = phrase_verdict(_RESULT)  # must not raise
    assert isinstance(text, str)


def test_plain_template_covers_all_verdict_values():
    for verdict in Verdict:
        result = EvaluationResult(verdict=verdict, trace={"scheme_id": "S"})
        text = plain_template_answer(result)
        assert isinstance(text, str) and text


def test_plain_template_never_contains_raw_enum_value():
    """The exact bug this was built to prevent: 'undetermined_missing_facts' must never appear
    literally in any user-facing text, on any path -- including the no-LLM fallback."""
    for verdict in Verdict:
        result = EvaluationResult(verdict=verdict, trace={"scheme_id": "S"})
        text = plain_template_answer(result)
        assert verdict.value not in text or verdict.value in ("eligible",)  # "eligible" is also a plain English word
        assert "undetermined_missing_facts" not in text
        assert "_" not in text  # no raw snake_case token of any kind should leak into prose


def test_verdict_headline_never_contains_raw_enum_value():
    for verdict in Verdict:
        result = EvaluationResult(verdict=verdict, trace={"scheme_id": "S"})
        headline = verdict_headline(result)
        assert "undetermined_missing_facts" not in headline
        assert "ineligible" not in headline
        assert "_" not in headline


def test_verdict_headline_includes_emoji_and_scheme_id():
    result = EvaluationResult(verdict=Verdict.ELIGIBLE, trace={"scheme_id": "PM-KISAN"})
    headline = verdict_headline(result)
    assert headline.startswith(verdict_emoji(Verdict.ELIGIBLE))
    assert "PM-KISAN" in headline


def test_verdict_emoji_covers_all_verdicts():
    for verdict in Verdict:
        assert verdict_emoji(verdict)  # non-empty for every verdict, never raises KeyError


# --- language param wiring (presentation-layer language toggle) --------------------------------


def test_language_hi_adds_hindi_instruction_to_system_prompt():
    mock_call = MagicMock(return_value=ProviderResult(content="x", provider_used="groq"))
    with patch("schemelogic.conversational.phrasing.chat_completion_with_fallback", mock_call):
        phrase_verdict(_RESULT, language="hi")
    system_content = mock_call.call_args.args[0][0]["content"]
    assert "Hindi" in system_content


def test_language_en_default_does_not_mention_hindi():
    mock_call = MagicMock(return_value=ProviderResult(content="x", provider_used="groq"))
    with patch("schemelogic.conversational.phrasing.chat_completion_with_fallback", mock_call):
        phrase_verdict(_RESULT)  # language defaults to "en"
    system_content = mock_call.call_args.args[0][0]["content"]
    assert "Hindi" not in system_content


def test_language_param_never_changes_the_verdict_itself():
    """The verdict is already computed before this function is ever called -- the language
    toggle can only change HOW it's worded, never what it says happened."""
    with patch(
        "schemelogic.conversational.phrasing.chat_completion_with_fallback",
        return_value=ProviderFailure(primary_error="x", secondary_error="y"),
    ):
        text = phrase_verdict(_RESULT, language="hi")
    assert "eligible" in text  # fell back to the (English) plain template -- verdict unchanged
