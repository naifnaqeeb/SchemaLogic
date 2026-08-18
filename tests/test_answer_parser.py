"""All LLM calls mocked -- no network, no quota touched."""

from unittest.mock import MagicMock, patch

from schemelogic.conversational.answer_parser import AnswerParseFailure, AnswerParseResult, parse_answer_llm
from schemelogic.llm.provider import ProviderFailure, ProviderResult


def _mock_response(content: str):
    return patch(
        "schemelogic.conversational.answer_parser.chat_completion_with_fallback",
        return_value=ProviderResult(content=content, provider_used="groq"),
    )


def test_confident_boolean_parsed():
    with _mock_response('{"value": true, "confident": true}'):
        result = parse_answer_llm("yeah for sure", "Are you a woman?", "boolean")
    assert isinstance(result, AnswerParseResult)
    assert result.value is True
    assert result.provider_used == "groq"


def test_confident_number_parsed():
    with _mock_response('{"value": 34, "confident": true}'):
        result = parse_answer_llm("I just turned 34", "What is your age?", "number")
    assert isinstance(result, AnswerParseResult)
    assert result.value == 34


def test_confident_text_parsed():
    with _mock_response('{"value": "farmer", "confident": true}'):
        result = parse_answer_llm("I work the land", "What is your occupation?", "text")
    assert isinstance(result, AnswerParseResult)
    assert result.value == "farmer"


def test_low_confidence_returns_failure_not_a_guess():
    with _mock_response('{"value": null, "confident": false}'):
        result = parse_answer_llm("maybe? not sure", "Are you a woman?", "boolean")
    assert isinstance(result, AnswerParseFailure)


def test_type_mismatch_returns_failure():
    """Model says confident but returns the wrong type for the field -- must not silently coerce
    into a guess."""
    with _mock_response('{"value": "yes", "confident": true}'):
        result = parse_answer_llm("yes", "Are you a woman?", "boolean")
    assert isinstance(result, AnswerParseFailure)


def test_both_providers_fail_returns_failure_not_exception():
    with patch(
        "schemelogic.conversational.answer_parser.chat_completion_with_fallback",
        return_value=ProviderFailure(primary_error="429", secondary_error="timeout"),
    ):
        result = parse_answer_llm("yeah", "Are you a woman?", "boolean")
    assert isinstance(result, AnswerParseFailure)
    assert "429" in result.reason


def test_malformed_json_returns_failure():
    with _mock_response("not json {{{"):
        result = parse_answer_llm("yeah", "Are you a woman?", "boolean")
    assert isinstance(result, AnswerParseFailure)


def test_number_bool_confusion_rejected():
    """True/False are technically ints in Python -- must not let a boolean silently pass as a
    valid number answer."""
    with _mock_response('{"value": true, "confident": true}'):
        result = parse_answer_llm("yes", "What is your age?", "number")
    assert isinstance(result, AnswerParseFailure)


# --- language param wiring (presentation-layer language toggle) --------------------------------


def test_language_hi_adds_hindi_instruction_to_system_prompt():
    mock_call = MagicMock(return_value=ProviderResult(content='{"value": true, "confident": true}', provider_used="groq"))
    with patch("schemelogic.conversational.answer_parser.chat_completion_with_fallback", mock_call):
        parse_answer_llm("haan", "Are you a woman?", "boolean", language="hi")
    system_content = mock_call.call_args.args[0][0]["content"]
    assert "Hindi" in system_content


def test_language_en_default_does_not_mention_hindi():
    mock_call = MagicMock(return_value=ProviderResult(content='{"value": true, "confident": true}', provider_used="groq"))
    with patch("schemelogic.conversational.answer_parser.chat_completion_with_fallback", mock_call):
        parse_answer_llm("yes", "Are you a woman?", "boolean")  # language defaults to "en"
    system_content = mock_call.call_args.args[0][0]["content"]
    assert "Hindi" not in system_content
