"""LLM provider abstraction with automatic fallback (Phase 8, Step 1).

Used ONLY by the conversational layer (schemelogic/conversational/intake.py, phrasing.py) — the
existing extraction/judge/gate pipeline (schemelogic/extraction/*) keeps using its own direct
Groq client, untouched, per explicit instruction: that machinery is already validated and
shouldn't be repointed at a new abstraction under time pressure tonight.

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


@dataclass
class ProviderResult:
    content: str
    provider_used: str  # "groq" | "openrouter" -- lets the UI/logs show whether fallback fired.


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


def _call(config: ProviderConfig, messages: list[dict[str, str]], client: OpenAI | None, **kwargs: Any) -> str:
    client = client or make_client(config)
    response = client.chat.completions.create(
        model=kwargs.pop("model", None) or config.default_model,
        messages=messages,
        **kwargs,
    )
    content = response.choices[0].message.content
    if not content or not content.strip():
        finish_reason = response.choices[0].finish_reason
        raise RuntimeError(f"{config.name} returned empty content (finish_reason={finish_reason!r})")
    return content


def chat_completion_with_fallback(
    messages: list[dict[str, str]],
    primary: ProviderConfig = GROQ,
    secondary: ProviderConfig = OPENROUTER,
    primary_client: OpenAI | None = None,
    secondary_client: OpenAI | None = None,
    **kwargs: Any,
) -> ProviderResult | ProviderFailure:
    """`primary_client`/`secondary_client` are injectable purely for testing (mock a client
    object instead of hitting the network) — production callers should omit them and let
    `make_client` build a real one from the provider's env var."""
    try:
        content = _call(primary, messages, primary_client, **kwargs)
        return ProviderResult(content=content, provider_used=primary.name)
    except Exception as primary_exc:  # noqa: BLE001 -- any failure at all triggers fallback
        try:
            content = _call(secondary, messages, secondary_client, **kwargs)
            return ProviderResult(content=content, provider_used=secondary.name)
        except Exception as secondary_exc:  # noqa: BLE001
            return ProviderFailure(primary_error=str(primary_exc), secondary_error=str(secondary_exc))
