"""Opening-message intake (Phase 8, Step 3). ONE LLM call via schemelogic.llm.provider, to parse
the citizen's free-text opening message into initial known profile fields, matched against the
scheme's field ontology. On failure (both providers), returns IntakeFailure — the caller (the
Streamlit UI) must fall back to the structured quick-select form instead of blocking. This module
never raises on an LLM failure; it always returns one of the two dataclasses below.

NOT live-tested against a real provider — per this session's explicit constraint (Groq quota
pressure), this is written and unit-tested with mocked providers only. See the Phase 8 report for
the manual-test checklist.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from schemelogic.llm.provider import ProviderFailure, chat_completion_with_fallback
from schemelogic.schema.field_ontology import format_for_prompt


@dataclass
class IntakeResult:
    profile: dict[str, Any]  # {"self": {...}, "family_members": [...]} -- partial; only fields
    # the model was confident the citizen actually stated.
    provider_used: str
    raw_content: str


@dataclass
class IntakeFailure:
    """Never raised — returned. The caller must check isinstance() and fall back to the
    structured quick-select form; this module makes no attempt to guess a profile from a failed
    parse."""

    primary_error: str
    secondary_error: str


def _system_prompt() -> str:
    return (
        "You extract structured facts about a citizen from their own free-text description, to "
        "help check their eligibility for a government welfare scheme. Only extract facts the "
        "citizen ACTUALLY STATED or unambiguously implied — never guess, infer, or assume a "
        "fact they did not mention. It is always better to leave a field out than to guess it.\n\n"
        "Output ONLY a JSON object with this exact shape, nothing else:\n"
        '{"self": {"<field_name>": <value>, ...}, "family_members": [{"<field_name>": <value>, ...}, ...]}\n\n'
        "Use ONLY these canonical field names (reuse exactly as written — never invent a new "
        "one, and never rename one):\n"
        f"{format_for_prompt(compact=True)}\n\n"
        'If nothing in the message maps to a known field, return {"self": {}, "family_members": []}. '
        "Booleans must be JSON true/false, not strings. Numbers must be JSON numbers, not strings."
    )


def parse_opening_message(message: str) -> IntakeResult | IntakeFailure:
    """`scheme` isn't required as a parameter — the canonical field vocabulary is global across
    schemes (schemelogic.schema.field_ontology), and the caller matches the resulting profile
    against whichever scheme the citizen has selected separately. Passing the scheme's own field
    subset would risk silently dropping a fact the citizen stated that happens to belong to a
    different scheme's fields but is still a real, reusable fact (e.g. is_woman)."""
    messages = [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": message},
    ]
    response = chat_completion_with_fallback(
        messages, response_format={"type": "json_object"}, temperature=0.1, max_tokens=600
    )
    if isinstance(response, ProviderFailure):
        return IntakeFailure(primary_error=response.primary_error, secondary_error=response.secondary_error)

    try:
        parsed = json.loads(response.content)
    except json.JSONDecodeError as exc:
        return IntakeFailure(
            primary_error=f"{response.provider_used} returned malformed JSON: {exc}",
            secondary_error="(fallback provider not attempted — malformed JSON is a parse "
            "failure after a successful call, not a call failure, so provider.py's own "
            "fallback logic never triggers for this; treat it as intake failure directly)",
        )

    self_fields = parsed.get("self")
    family_fields = parsed.get("family_members")
    profile = {
        "self": self_fields if isinstance(self_fields, dict) else {},
        "family_members": family_fields if isinstance(family_fields, list) else [],
    }
    return IntakeResult(profile=profile, provider_used=response.provider_used, raw_content=response.content)
