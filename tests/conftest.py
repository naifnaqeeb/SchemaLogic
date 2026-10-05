"""Suite-wide guarantee that tests never spend LLM provider quota.

This project's standing rule is that tests mock every LLM call. That was enforced test-by-test,
which quietly stopped holding: several tests drove real calls and passed anyway, because a failed
provider call is (correctly) a graceful-degradation path everywhere in this codebase -- so a live
call that failed looked exactly like a mocked failure. It only surfaced when the account's key
became usable again and gpt-oss classified a test's "who knows" as a greeting, flipping
test_llm_parse_failure_reprompts_without_mutating_profile.

Verified on 2026-09-16 by hard-blocking api.groq.com at the httpx layer during a full run: nine
real call attempts remained, all from chat_engine tests, and none of them from the router -- they
came from the INTAKE call inside _start_question_loop, whose provider binding a router-only patch
doesn't touch.

Hence this: every module-level binding of chat_completion_with_fallback is defaulted to a
ProviderFailure, so any un-mocked call takes the deterministic fallback path the test was really
exercising instead of reaching the network. Each symbol must be patched where it was imported --
`from ... import chat_completion_with_fallback` copies the reference, so patching
schemelogic.llm.provider alone would miss all four.

A test that wants a specific provider response still patches it locally; an inner patch takes
precedence over these and is restored to them afterwards.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from schemelogic.llm.provider import ProviderFailure

_PROVIDER_BINDINGS = (
    "schemelogic.conversational.router.chat_completion_with_fallback",
    "schemelogic.conversational.intake.chat_completion_with_fallback",
    "schemelogic.conversational.phrasing.chat_completion_with_fallback",
    "schemelogic.conversational.answer_parser.chat_completion_with_fallback",
    "schemelogic.conversational.description_translation.chat_completion_with_fallback",  # stage 2, 2026-10-05
)

_DISABLED = ProviderFailure(
    primary_error="test: live LLM calls are disabled (tests/conftest.py)",
    secondary_error="test: live LLM calls are disabled (tests/conftest.py)",
)


@pytest.fixture(autouse=True)
def _block_provider_calls():
    patches = [patch(target, return_value=_DISABLED) for target in _PROVIDER_BINDINGS]
    for p in patches:
        p.start()
    try:
        yield
    finally:
        for p in patches:
            p.stop()


@pytest.fixture(autouse=True)
def _isolate_disk_caches(tmp_path, monkeypatch):
    """Point every on-disk cache at tmp_path, for every test.

    These caches are keyed by slug/field and live under data/cache/, and most test modules never
    redirected them -- so any test whose extraction SUCCEEDED wrote a real file there. That then
    fed back in as a cache hit: a chat_engine test that stored a scheme under "silver-1" made a
    later test's first extraction attempt never happen at all, failing an assertion about call
    counts for reasons nothing in that test could explain (2026-09-18). Tests must not write to,
    or read from, the project's real caches."""
    monkeypatch.setattr(
        "schemelogic.conversational.ai_checked.DISK_CACHE_DIR", tmp_path / "ai_checked_cache"
    )
    monkeypatch.setattr(
        "schemelogic.conversational.field_phrasing.DISK_CACHE_PATH",
        tmp_path / "field_questions.json",
    )
    monkeypatch.setattr(
        "schemelogic.conversational.description_translation.CACHE_DIR", tmp_path / "translations"
    )


@pytest.fixture(autouse=True)
def _clear_runtime_field_questions():
    """The generated-question registry is module-level state; leaking it between tests would let
    one test's phrasing silently satisfy another's assertion about the generic fallback."""
    from schemelogic.schema import field_ontology

    field_ontology.clear_registered_citizen_questions()
    yield
    field_ontology.clear_registered_citizen_questions()


@pytest.fixture(autouse=True)
def _block_direct_groq_clients(monkeypatch):
    """extraction/extractor.py and extraction/judge_repair.py construct their own Groq client
    rather than going through the provider wrapper (see extractor.py's module docstring for why).
    Those tests all inject a fake client, so a real one being constructed means a test forgot --
    make that loud rather than billable."""

    def _refuse(*args, **kwargs):
        raise AssertionError(
            "A real Groq client was constructed during tests. Pass a fake client "
            "(see tests/test_extractor.py's FakeGroq) instead of letting the call reach the API."
        )

    monkeypatch.setattr("schemelogic.extraction.extractor.Groq", _refuse)
    monkeypatch.setattr("schemelogic.extraction.judge_repair.Groq", _refuse)
