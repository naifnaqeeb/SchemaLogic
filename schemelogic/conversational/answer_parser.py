"""Free-text answer parsing for the eligibility Q&A loop (conversational redesign, Step 1).

session.py's deterministic `_parse_answer` already handles the easy cases (exact "yes"/"no",
plain numbers) and is tried FIRST, always, by the caller (app.py) -- this module is only reached
when that fails, for things like "yeah for sure", "nah not really", "I just turned 34", "around
5000 a month". It is a normalizer, not a decision-maker: given the one currently-pending question
(field name + answer_type + prompt text), it extracts the single value the citizen appears to be
stating for THAT field, or reports it can't tell. It never touches the profile, never calls the
evaluator, and never states an eligibility fact -- it hands back a plain value (or None) for the
caller to feed through the same deterministic `_parse_answer` path as everything else, so the
no-silent-guessing invariant still holds: an unconfident LLM read is treated exactly like an
unparseable answer (re-prompt), never silently accepted.

On any provider failure, malformed JSON, or a low-confidence read, returns AnswerParseFailure --
never raises, never blocks. The caller's fallback at that point is the same as before this
module existed: ask the citizen to try again, or use the quick-reply buttons for boolean questions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from schemelogic.llm.provider import ProviderFailure, chat_completion_with_fallback


@dataclass
class AnswerParseResult:
    value: Any  # bool | int | float | str -- matches the pending question's answer_type
    provider_used: str


@dataclass
class AnswerParseFailure:
    """Never raised -- returned. Caller re-prompts (or points at quick-reply buttons), exactly as
    it already does for session.AnswerParseError."""

    reason: str


def _system_prompt(question_prompt: str, answer_type: str, language: str = "en") -> str:
    type_instruction = {
        "boolean": 'The expected answer is yes/no. Output {"value": true|false, "confident": true|false}.',
        "number": 'The expected answer is a number. Output {"value": <number>, "confident": true|false}.',
        "text": 'The expected answer is free text. Output {"value": "<the stated value>", "confident": true|false}.',
    }[answer_type]
    prompt = (
        "A citizen was just asked ONE question while checking their eligibility for a government "
        "welfare scheme. You extract the value they're stating for THAT question, nothing else. "
        "You never decide eligibility, never state a verdict, never invent a value they didn't "
        "actually state.\n\n"
        f'The question asked was: "{question_prompt}"\n'
        f"{type_instruction}\n\n"
        'If you cannot confidently tell what value they mean, output {"value": null, "confident": false}. '
        "Output ONLY the JSON object, nothing else."
    )
    if language == "hi":
        # Same as router.py's note: this is about correctly UNDERSTANDING a Hindi-typed answer,
        # not translating output -- the JSON shape/keys stay exactly as specified, and a "text"
        # answer_type's extracted value is captured as the citizen actually stated it, in whatever
        # language that was (never translated -- see this project's scope notes on that).
        prompt += (
            " The citizen may answer in Hindi -- read it correctly either way. The JSON keys "
            "themselves stay in English as specified above; if the answer_type is text, capture "
            "the stated value as given, without translating it."
        )
    return prompt


def parse_answer_llm(
    raw_answer: str, question_prompt: str, answer_type: str, language: str = "en",
) -> AnswerParseResult | AnswerParseFailure:
    messages = [
        {"role": "system", "content": _system_prompt(question_prompt, answer_type, language)},
        {"role": "user", "content": raw_answer},
    ]
    response = chat_completion_with_fallback(
        messages, response_format={"type": "json_object"}, temperature=0.0, max_tokens=100
    )
    if isinstance(response, ProviderFailure):
        return AnswerParseFailure(reason=f"both providers failed: {response.primary_error} / {response.secondary_error}")

    try:
        parsed = json.loads(response.content)
    except json.JSONDecodeError as exc:
        return AnswerParseFailure(reason=f"malformed JSON from {response.provider_used}: {exc}")

    if not parsed.get("confident") or parsed.get("value") is None:
        return AnswerParseFailure(reason="model was not confident it could extract a value")

    value = parsed["value"]
    if answer_type == "boolean" and not isinstance(value, bool):
        return AnswerParseFailure(reason=f"expected boolean, model returned {value!r}")
    if answer_type == "number" and (isinstance(value, bool) or not isinstance(value, (int, float))):
        return AnswerParseFailure(reason=f"expected number, model returned {value!r}")
    if answer_type == "text" and not isinstance(value, str):
        value = str(value)

    return AnswerParseResult(value=value, provider_used=response.provider_used)
