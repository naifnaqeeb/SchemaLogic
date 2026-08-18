"""Final-answer phrasing (Phase 8, Step 3). ONE OPTIONAL LLM call via schemelogic.llm.provider,
to phrase the verdict + rule trace conversationally. On failure (both providers), falls back to
a plain template — this function ALWAYS returns a string, never raises, never blocks.

NOT live-tested against a real provider — written and unit-tested with mocked providers only.
See the Phase 8 report for the manual-test checklist.
"""

from __future__ import annotations

import json

from schemelogic.evaluator.symbolic_engine import EvaluationResult, Verdict
from schemelogic.llm.provider import ProviderFailure, chat_completion_with_fallback

_VERDICT_PHRASE = {
    Verdict.ELIGIBLE: "you're eligible",
    Verdict.INELIGIBLE: "you're not eligible",
}

_VERDICT_EMOJI = {
    Verdict.ELIGIBLE: "🟢",
    Verdict.INELIGIBLE: "🔴",
    Verdict.UNDETERMINED: "🟡",
}


def verdict_emoji(verdict: Verdict) -> str:
    return _VERDICT_EMOJI[verdict]


def verdict_headline(result: EvaluationResult) -> str:
    """Short, single-line, human-readable summary — for a badge/header anywhere in the UI.
    NEVER the raw Verdict enum value (e.g. "undetermined_missing_facts") — every caller that
    used to build its own badge text from `result.verdict.value` directly must use this instead."""
    scheme_id = result.trace.get("scheme_id", "this scheme")
    emoji = verdict_emoji(result.verdict)
    if result.verdict == Verdict.UNDETERMINED:
        return f"{emoji} One more detail needed for {scheme_id}"
    return f"{emoji} {_VERDICT_PHRASE[result.verdict].capitalize()} for {scheme_id}"


def plain_template_answer(result: EvaluationResult) -> str:
    """The non-LLM fallback. Always available, always correct (same verdict the LLM path would
    have phrased, just less warmly worded) — this is the actual safety net, not a degraded
    experience to apologize for. Never contains a raw Verdict enum value; runs with zero LLM
    dependency, so `phrase_verdict`'s optional LLM call is an enhancement on top of this, never
    the only source of readable text."""
    scheme_id = result.trace.get("scheme_id", "this scheme")
    if result.verdict == Verdict.UNDETERMINED:
        return f"I need one more detail to be sure about your eligibility for {scheme_id} — let's continue."
    return f"Based on what you've told me, {_VERDICT_PHRASE[result.verdict]} for {scheme_id} — here's why:"


def _system_prompt(language: str = "en") -> str:
    prompt = (
        "You explain a government welfare scheme eligibility result to a citizen in plain, "
        "warm, one-paragraph language. You are NOT deciding eligibility — a separate "
        "deterministic engine already decided it and gave you the verdict and full rule trace "
        "below; you only phrase the result and briefly summarize the reasons from the trace. "
        "Never contradict the given verdict. Never state a fact not present in the trace. Never "
        "invent additional conditions, next steps, or advice beyond what the trace supports."
    )
    if language == "hi":
        # The language toggle is presentation-layer only tonight -- it instructs THIS call's
        # wording, nothing else. It never changes the verdict itself (that's computed before this
        # function is ever called) and never translates the scraped scheme data quoted inside the
        # trace, which stays in its original language regardless.
        prompt += " Respond in Hindi (हिन्दी), not English."
    return prompt


def phrase_verdict(result: EvaluationResult, language: str = "en") -> str:
    """Always returns a string — never raises, never blocks on an LLM failure. `language`
    ("en"/"hi") only affects the WORDING of this LLM call -- it cannot and does not change what
    verdict gets phrased, since `result` already carries the final, evaluator-computed verdict."""
    trace_json = json.dumps(result.trace, indent=2, default=str)
    messages = [
        {"role": "system", "content": _system_prompt(language)},
        {"role": "user", "content": f"Verdict: {result.verdict.value}\n\nRule trace:\n{trace_json}"},
    ]
    response = chat_completion_with_fallback(messages, temperature=0.3, max_tokens=300)
    if isinstance(response, ProviderFailure):
        return plain_template_answer(result)
    return response.content
