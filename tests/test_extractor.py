"""extractor.py's failure taxonomy, rate-limit retry and truncation recovery.

The Groq client is faked throughout -- no network, no quota touched. What these tests pin down is
the behaviour added on 2026-09-15 after diagnosing why the live AI-Checked tier kept falling back
to description-only (see data/extraction_runs/ai_checked_diagnosis_2026-09-15.jsonl): one core
extraction call costs a median ~7.5k tokens against this account's flat 8000 TPM ceiling, so a
429 mid-chat was a routine outcome and was not retried, and a truncated structured-output
generation was being filed under the catch-all `api_error`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from groq import APIError

from schemelogic.extraction import extractor
from schemelogic.extraction.extractor import ExtractionFailure, extract_scheme
from schemelogic.schema.models import Scheme

CORE_RESPONSE = {
    "scheme_id": "FAKE",
    "unit_of_eligibility": "individual",
    "inclusion": {"and": [{"cat": "demographic", "field": "is_woman", "op": "==", "value": True}]},
    "exclusions": [],
    "operational_requirements": [],
}
META_RESPONSE = {
    "temporal_validity": {"valid_from": "2020-01-01", "valid_to": None, "extracted_at": "2026-01-01"},
    "extraction_metadata": {"confidence": 0.6, "source_clause": "Sec. 1", "flagged_for_review": True},
}

TRUNCATION_MESSAGE = (
    "Error code: 400 - {'error': {'message': \"Failed to generate JSON. Please adjust your prompt. "
    "See 'failed_generation' for more details.\", 'type': 'invalid_request_error', 'code': "
    "'json_validate_failed', 'failed_generation': 'max completion tokens reached before generating "
    "a valid document'}}"
)
RATE_LIMIT_MESSAGE = (
    "Error code: 429 - {'error': {'message': 'Rate limit reached for model gpt-oss-120b: "
    "Limit 8000, Used 7900. Please try again in 12.5s.', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}"
)


def _api_error(message: str, headers: dict[str, str] | None = None) -> APIError:
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    exc = APIError(message, request, body=None)
    if headers is not None:
        exc.response = httpx.Response(429, headers=headers, request=request)  # type: ignore[attr-defined]
    return exc


@dataclass
class _FakeMessage:
    content: str


@dataclass
class _FakeChoice:
    message: _FakeMessage
    finish_reason: str = "stop"


@dataclass
class _FakeResponse:
    choices: list[_FakeChoice]


@dataclass
class FakeGroq:
    """Programmable stand-in: `outcomes` is consumed one per create() call. A str is returned as
    response content, an Exception is raised, a dict is JSON-encoded as content."""

    outcomes: list[Any]
    calls: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.chat = self
        self.completions = self

    def create(self, **kwargs: Any) -> _FakeResponse:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        content = outcome if isinstance(outcome, str) else json.dumps(outcome)
        return _FakeResponse(choices=[_FakeChoice(message=_FakeMessage(content=content))])


@pytest.fixture
def no_sleep(monkeypatch):
    """Retry backoff must not actually sleep in tests -- record the waits instead."""
    waits: list[float] = []
    monkeypatch.setattr(extractor.time, "sleep", lambda s: waits.append(s))
    return waits


# --- the test-suite quota guards themselves -----------------------------------------------------
# These assert that tests/conftest.py's protections actually fire. Without them the guards are
# unverified claims: the leak they exist to stop (2026-09-16, nine live Groq POSTs during a run
# that reported all-green) was invisible precisely BECAUSE a failed provider call is a legitimate
# degradation path everywhere in this codebase, so a live call and a mocked failure look alike.


def test_constructing_a_real_groq_client_in_tests_is_blocked_loudly():
    with pytest.raises(AssertionError, match="real Groq client was constructed"):
        extractor.Groq(api_key="not-a-real-key")


def test_constructing_a_real_groq_client_in_judge_repair_is_blocked_loudly():
    from schemelogic.extraction import judge_repair

    with pytest.raises(AssertionError, match="real Groq client was constructed"):
        judge_repair.Groq(api_key="not-a-real-key")


def test_provider_wrapper_calls_are_defaulted_to_failure_in_tests():
    """The other half of the guard: the four conversational modules bind
    chat_completion_with_fallback by value, so each binding is patched separately. If any one of
    them were missed, that module's calls would silently reach the network (which is exactly how
    the intake call escaped a router-only patch)."""
    from schemelogic.conversational import answer_parser, intake, phrasing, router
    from schemelogic.llm.provider import ProviderFailure as PF

    for module in (router, intake, phrasing, answer_parser):
        result = module.chat_completion_with_fallback([{"role": "user", "content": "hi"}])
        assert isinstance(result, PF), f"{module.__name__} would have made a live call"


# --- failure taxonomy ---------------------------------------------------------------------------


def test_truncation_is_classified_as_its_own_reason_not_api_error():
    assert extractor._api_error_reason(TRUNCATION_MESSAGE) == "truncated_completion_budget"


def test_rate_limit_is_classified_as_rate_limited():
    assert extractor._api_error_reason(RATE_LIMIT_MESSAGE) == "rate_limited"


def test_unrecognized_api_error_stays_api_error():
    assert extractor._api_error_reason("Error code: 500 - internal server error") == "api_error"


# --- rate-limit retry ---------------------------------------------------------------------------


def test_rate_limited_call_is_retried_and_can_succeed(no_sleep):
    """The live-path fix: a 429 on the first core call used to drop the citizen straight to the
    description-only display even though the same call succeeds seconds later."""
    client = FakeGroq(outcomes=[_api_error(RATE_LIMIT_MESSAGE), CORE_RESPONSE, META_RESPONSE])
    result = extract_scheme("some scheme text", client=client)
    assert isinstance(result, Scheme)
    assert result.scheme_id == "FAKE"
    assert len(no_sleep) == 1  # waited once before retrying


def test_rate_limit_retries_are_bounded_then_reported_honestly(no_sleep):
    client = FakeGroq(outcomes=[_api_error(RATE_LIMIT_MESSAGE)] * 5)
    result = extract_scheme("some scheme text", client=client)
    assert isinstance(result, ExtractionFailure)
    assert result.reason == "rate_limited"
    assert len(client.calls) == extractor._RATE_LIMIT_RETRIES + 1  # no unbounded retry loop


def test_retry_after_header_is_honoured_and_clamped(no_sleep):
    client = FakeGroq(outcomes=[
        _api_error(RATE_LIMIT_MESSAGE, headers={"retry-after": "3"}), CORE_RESPONSE, META_RESPONSE,
    ])
    assert isinstance(extract_scheme("text", client=client), Scheme)
    assert no_sleep == [3.0]


def test_absurd_retry_after_is_clamped_so_a_chat_turn_never_hangs(no_sleep):
    client = FakeGroq(outcomes=[
        _api_error(RATE_LIMIT_MESSAGE, headers={"retry-after": "9999"}), CORE_RESPONSE, META_RESPONSE,
    ])
    assert isinstance(extract_scheme("text", client=client), Scheme)
    assert no_sleep == [extractor._RATE_LIMIT_MAX_WAIT]


def test_non_rate_limit_api_error_is_not_retried(no_sleep):
    client = FakeGroq(outcomes=[_api_error("Error code: 500 - boom")])
    result = extract_scheme("text", client=client)
    assert isinstance(result, ExtractionFailure)
    assert result.reason == "api_error"
    assert len(client.calls) == 1
    assert no_sleep == []


# --- truncation recovery ------------------------------------------------------------------------


def test_truncation_triggers_one_recovery_attempt_with_more_headroom(no_sleep):
    client = FakeGroq(outcomes=[_api_error(TRUNCATION_MESSAGE), CORE_RESPONSE, META_RESPONSE])
    result = extract_scheme("scheme text", client=client)
    assert isinstance(result, Scheme)

    first, retry = client.calls[0], client.calls[1]
    # the retry buys completion headroom two ways, and only on the retry
    assert "reasoning_effort" not in first
    assert retry["reasoning_effort"] == "low"
    assert retry["max_tokens"] > first["max_tokens"]
    assert len(retry["messages"][0]["content"]) < len(first["messages"][0]["content"])


def test_truncation_recovery_failure_is_reported_as_truncation(no_sleep):
    client = FakeGroq(outcomes=[_api_error(TRUNCATION_MESSAGE), _api_error(TRUNCATION_MESSAGE)])
    result = extract_scheme("scheme text", client=client)
    assert isinstance(result, ExtractionFailure)
    assert result.reason == "truncated_completion_budget"
    assert len(client.calls) == 2  # one recovery attempt, not a loop


def test_truncation_is_not_retried_when_already_at_max_headroom(no_sleep):
    """Caller already asked for the cheapest config -- there is nothing left to escalate to."""
    client = FakeGroq(outcomes=[_api_error(TRUNCATION_MESSAGE)])
    result = extract_scheme("text", client=client, reasoning_effort="low", ontology_compact=True)
    assert isinstance(result, ExtractionFailure)
    assert len(client.calls) == 1


# --- defaults preserve the validated gold path --------------------------------------------------


def test_default_call_sends_no_reasoning_effort_and_the_full_ontology(no_sleep):
    """The Phase 3 gold numbers were produced by the pre-2026-09-15 config; defaults must not
    silently drift away from it."""
    client = FakeGroq(outcomes=[CORE_RESPONSE, META_RESPONSE])
    assert isinstance(extract_scheme("text", client=client), Scheme)
    core_call = client.calls[0]
    assert "reasoning_effort" not in core_call
    assert core_call["messages"][0]["content"] == extractor._core_system_prompt()


def test_explicit_knobs_are_passed_through(no_sleep):
    client = FakeGroq(outcomes=[CORE_RESPONSE, META_RESPONSE])
    assert isinstance(
        extract_scheme("text", client=client, reasoning_effort="low", ontology_compact=True), Scheme
    )
    core_call = client.calls[0]
    assert core_call["reasoning_effort"] == "low"
    assert core_call["messages"][0]["content"] == extractor._core_system_prompt(ontology_compact=True)



# --- except_scope is gold-only (decided 2026-10-04) ----------------------------------------------
# An applicant-scoped exception waives a whole exclusion for every family member when the applicant
# meets a condition. That is only right when the source text says so, and must be justified against
# it by a human. Extraction -- including the live AI-Checked tier -- can only produce member scope.


def test_extractor_schema_does_not_offer_except_scope():
    serialized = json.dumps(extractor._CORE_JSON_SCHEMA)
    assert "except_scope" not in serialized
    assert "ExceptScope" not in serialized


def test_an_except_scope_the_model_emits_anyway_is_dropped_to_member(no_sleep):
    """With strict:false a model can still emit off-schema keys; they must never widen an exception."""
    core = json.loads(json.dumps(CORE_RESPONSE))
    core["exclusions"] = [{
        "cat": "economic", "quantifier": "some_family_member", "field": "pays_tax", "op": "==",
        "value": True, "except": {"field": "is_senior", "op": "==", "value": True},
        "except_scope": "applicant",
    }]
    result = extract_scheme("text", client=FakeGroq(outcomes=[core, META_RESPONSE]))
    assert isinstance(result, Scheme)
    assert result.exclusions[0].except_scope.value == "member"
