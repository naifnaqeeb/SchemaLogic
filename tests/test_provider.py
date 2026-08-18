"""All calls here are mocked -- no network, no API keys, no Groq quota touched."""

from unittest.mock import MagicMock

from schemelogic.llm.provider import (
    GROQ,
    OPENROUTER,
    ProviderFailure,
    ProviderResult,
    chat_completion_with_fallback,
)


def _fake_client(content: str | None = "hello", finish_reason: str = "stop", raise_exc: Exception | None = None):
    client = MagicMock()
    if raise_exc is not None:
        client.chat.completions.create.side_effect = raise_exc
        return client
    response = MagicMock()
    choice = MagicMock()
    choice.message.content = content
    choice.finish_reason = finish_reason
    response.choices = [choice]
    client.chat.completions.create.return_value = response
    return client


def test_primary_success_no_fallback():
    primary_client = _fake_client(content="primary answer")
    secondary_client = _fake_client(content="secondary answer")
    result = chat_completion_with_fallback(
        [{"role": "user", "content": "hi"}],
        primary_client=primary_client, secondary_client=secondary_client,
    )
    assert isinstance(result, ProviderResult)
    assert result.content == "primary answer"
    assert result.provider_used == "groq"
    secondary_client.chat.completions.create.assert_not_called()


def test_primary_raises_falls_back_to_secondary():
    primary_client = _fake_client(raise_exc=RuntimeError("429 rate limited"))
    secondary_client = _fake_client(content="fallback answer")
    result = chat_completion_with_fallback(
        [{"role": "user", "content": "hi"}],
        primary_client=primary_client, secondary_client=secondary_client,
    )
    assert isinstance(result, ProviderResult)
    assert result.content == "fallback answer"
    assert result.provider_used == "openrouter"


def test_primary_empty_content_falls_back():
    """Empty content counts as a failure -- not just exceptions."""
    primary_client = _fake_client(content="")
    secondary_client = _fake_client(content="fallback answer")
    result = chat_completion_with_fallback(
        [{"role": "user", "content": "hi"}],
        primary_client=primary_client, secondary_client=secondary_client,
    )
    assert isinstance(result, ProviderResult)
    assert result.provider_used == "openrouter"


def test_both_fail_returns_failure_not_exception():
    primary_client = _fake_client(raise_exc=RuntimeError("primary down"))
    secondary_client = _fake_client(raise_exc=RuntimeError("secondary down"))
    result = chat_completion_with_fallback(
        [{"role": "user", "content": "hi"}],
        primary_client=primary_client, secondary_client=secondary_client,
    )
    assert isinstance(result, ProviderFailure)
    assert "primary down" in result.primary_error
    assert "secondary down" in result.secondary_error


def test_never_retries_same_provider_twice():
    """Primary fails once -> goes straight to secondary, exactly one call each."""
    primary_client = _fake_client(raise_exc=RuntimeError("fail"))
    secondary_client = _fake_client(content="ok")
    chat_completion_with_fallback(
        [{"role": "user", "content": "hi"}],
        primary_client=primary_client, secondary_client=secondary_client,
    )
    assert primary_client.chat.completions.create.call_count == 1
    assert secondary_client.chat.completions.create.call_count == 1


def test_default_provider_configs():
    assert GROQ.name == "groq"
    assert OPENROUTER.name == "openrouter"
    assert GROQ.api_key_env == "GROQ_API_KEY"
    assert OPENROUTER.api_key_env == "OPENROUTER_API_KEY"
