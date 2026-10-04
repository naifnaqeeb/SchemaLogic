"""LLM provider abstraction with automatic fallback (Phase 8, Step 1).

Used by the conversational layer (intake.py, phrasing.py, ...) with Groq primary and OpenRouter
fallback. Since 2026-10-05 the extraction, judge and baseline runners can also name a provider
explicitly (`provider="groq"` -- the default, behaviour unchanged -- or `"openrouter"`) through
`get_provider` / `make_client`; experiments run on Groq only and never fall back (see
docs/PLAN_FINAL_PUSH.md), so `chat_completion_with_fallback` accepts `secondary=None`.

Both Groq and OpenRouter expose OpenAI-SDK-compatible chat completion endpoints, so this wraps a
single `openai.OpenAI` client per provider (base_url + api_key swap), not two separate SDKs.

Fallback: try the primary provider once; on ANY failure (rate limit, timeout, malformed/empty
response, anything), try the secondary once. Never a third attempt on either provider — a second
failure on the same provider would just burn more quota for no new information, and this project
already hit that exact daily-quota wall repeatedly tonight.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"
DEFAULT_OPENROUTER_MODEL = "openai/gpt-oss-120b"
# ^ OpenRouter's model-id namespace mostly mirrors upstream provider IDs but isn't guaranteed
# identical — kept the same string as the Groq model used everywhere else in this project for
# consistency; confirm it resolves on OpenRouter's side before relying on it in production (not
# verified with a live call tonight, per the no-self-testing constraint).


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    api_key_env: str
    base_url: str
    default_model: str


GROQ = ProviderConfig(
    name="groq", api_key_env="GROQ_API_KEY", base_url=GROQ_BASE_URL, default_model=DEFAULT_GROQ_MODEL
)
OPENROUTER = ProviderConfig(
    name="openrouter", api_key_env="OPENROUTER_API_KEY", base_url=OPENROUTER_BASE_URL,
    default_model=DEFAULT_OPENROUTER_MODEL,
)
PROVIDERS: dict[str, ProviderConfig] = {GROQ.name: GROQ, OPENROUTER.name: OPENROUTER}


def get_provider(name: str) -> ProviderConfig:
    """The ProviderConfig for "groq" or "openrouter". Unknown names fail loudly -- a typo must never
    quietly run an experiment against some other provider."""
    try:
        return PROVIDERS[name]
    except KeyError:
        raise ValueError(f"unknown provider {name!r}; expected one of {sorted(PROVIDERS)}") from None


@dataclass
class ProviderResult:
    content: str
    provider_used: str  # "groq" | "openrouter" -- lets the UI/logs show whether fallback fired.
    usage: Any = None  # the response's token usage (prompt_tokens / completion_tokens), when reported
    model: str | None = None


@dataclass
class ProviderFailure:
    """Both providers failed. Never raised — callers (intake.py, phrasing.py) must handle this
    explicitly and fall back to their own non-LLM path. Nothing in this module ever blocks."""

    primary_error: str
    secondary_error: str


def make_client(config: ProviderConfig) -> OpenAI:
    api_key = os.environ.get(config.api_key_env)
    if not api_key:
        raise RuntimeError(f"{config.api_key_env} is not set")
    return OpenAI(api_key=api_key, base_url=config.base_url)


def _call(config: ProviderConfig, messages: list[dict[str, str]], client: OpenAI | None, **kwargs: Any) -> ProviderResult:
    client = client or make_client(config)
    model = kwargs.pop("model", None) or config.default_model
    response = client.chat.completions.create(model=model, messages=messages, **kwargs)
    content = response.choices[0].message.content
    if not content or not content.strip():
        finish_reason = response.choices[0].finish_reason
        raise RuntimeError(f"{config.name} returned empty content (finish_reason={finish_reason!r})")
    return ProviderResult(content=content, provider_used=config.name,
                          usage=getattr(response, "usage", None), model=model)


def chat_completion_with_fallback(
    messages: list[dict[str, str]],
    primary: ProviderConfig = GROQ,
    secondary: ProviderConfig | None = OPENROUTER,
    primary_client: OpenAI | None = None,
    secondary_client: OpenAI | None = None,
    **kwargs: Any,
) -> ProviderResult | ProviderFailure:
    """`primary_client`/`secondary_client` are injectable purely for testing (mock a client
    object instead of hitting the network) — production callers should omit them and let
    `make_client` build a real one from the provider's env var. `secondary=None` means no fallback:
    a primary failure is returned as a ProviderFailure (experiments use this, so a result can never
    silently come from a different provider than the one recorded)."""
    try:
        return _call(primary, messages, primary_client, **dict(kwargs))
    except Exception as primary_exc:  # noqa: BLE001 -- any failure at all triggers fallback
        if secondary is None:
            return ProviderFailure(primary_error=str(primary_exc), secondary_error="no fallback configured")
        try:
            return _call(secondary, messages, secondary_client, **dict(kwargs))
        except Exception as secondary_exc:  # noqa: BLE001
            return ProviderFailure(primary_error=str(primary_exc), secondary_error=str(secondary_exc))
