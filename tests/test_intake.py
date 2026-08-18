"""All calls mocked -- no network, no API keys, no Groq quota touched."""

from unittest.mock import patch

from schemelogic.conversational.intake import IntakeFailure, IntakeResult, parse_opening_message
from schemelogic.llm.provider import ProviderFailure, ProviderResult


def test_successful_parse_returns_profile():
    fake_json = '{"self": {"is_woman": true, "age": 30}, "family_members": []}'
    with patch(
        "schemelogic.conversational.intake.chat_completion_with_fallback",
        return_value=ProviderResult(content=fake_json, provider_used="groq"),
    ):
        result = parse_opening_message("I am a 30 year old woman")
    assert isinstance(result, IntakeResult)
    assert result.profile["self"] == {"is_woman": True, "age": 30}
    assert result.provider_used == "groq"


def test_both_providers_fail_returns_intake_failure_not_exception():
    with patch(
        "schemelogic.conversational.intake.chat_completion_with_fallback",
        return_value=ProviderFailure(primary_error="429", secondary_error="timeout"),
    ):
        result = parse_opening_message("I am a 30 year old woman")
    assert isinstance(result, IntakeFailure)
    assert "429" in result.primary_error


def test_malformed_json_response_returns_intake_failure():
    with patch(
        "schemelogic.conversational.intake.chat_completion_with_fallback",
        return_value=ProviderResult(content="not valid json {{{", provider_used="groq"),
    ):
        result = parse_opening_message("hello")
    assert isinstance(result, IntakeFailure)


def test_missing_keys_in_response_default_to_empty():
    with patch(
        "schemelogic.conversational.intake.chat_completion_with_fallback",
        return_value=ProviderResult(content="{}", provider_used="groq"),
    ):
        result = parse_opening_message("hello")
    assert isinstance(result, IntakeResult)
    assert result.profile == {"self": {}, "family_members": []}


def test_non_dict_self_field_defaults_to_empty():
    """Model returning a malformed shape (self as a string, say) shouldn't crash the parser --
    should degrade to an empty dict for that piece, same no-silent-guessing spirit."""
    with patch(
        "schemelogic.conversational.intake.chat_completion_with_fallback",
        return_value=ProviderResult(content='{"self": "not a dict", "family_members": []}', provider_used="groq"),
    ):
        result = parse_opening_message("hello")
    assert isinstance(result, IntakeResult)
    assert result.profile["self"] == {}
