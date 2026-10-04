"""The provider option on the extractor, judge and Baseline 2 (2026-10-05). Defaults unchanged; an
explicit provider is honoured; experiments can turn the fallback off; real token usage is reported.
No network: every client is a fake."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import openai
import pytest

from schemelogic.evaluation import direct_llm_baseline as dlb
from schemelogic.extraction import extractor, judge_repair
from schemelogic.llm import provider
from schemelogic.llm.provider import GROQ, OPENROUTER, ProviderFailure, chat_completion_with_fallback, get_provider
from schemelogic.schema.models import Scheme

CORE = {"scheme_id": "FAKE", "unit_of_eligibility": "individual",
        "inclusion": {"and": [{"cat": "demographic", "field": "is_woman", "op": "==", "value": True}]},
        "exclusions": [], "operational_requirements": []}
META = {"temporal_validity": {"valid_from": "2020-01-01", "valid_to": None, "extracted_at": "2026-01-01"},
        "extraction_metadata": {"confidence": 0.6, "source_clause": "x", "flagged_for_review": True}}


class FakeClient:
    """OpenAI-SDK-shaped fake: outcomes consumed per call; dict -> JSON content with usage."""

    def __init__(self, outcomes):
        self.outcomes, self.calls = list(outcomes), []
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        message = SimpleNamespace(content=json.dumps(outcome))
        return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")],
                               usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20, total_tokens=120))


def test_get_provider_names_the_two_providers_and_rejects_anything_else():
    assert get_provider("groq") is GROQ and get_provider("openrouter") is OPENROUTER
    with pytest.raises(ValueError, match="unknown provider"):
        get_provider("grok")


def test_no_fallback_means_a_primary_failure_is_a_failure_and_the_secondary_is_never_called():
    primary = FakeClient([RuntimeError("429 rate limit")])
    secondary = FakeClient([{"verdict": "eligible"}])
    result = chat_completion_with_fallback([{"role": "user", "content": "x"}], secondary=None,
                                           primary_client=primary, secondary_client=secondary)
    assert isinstance(result, ProviderFailure) and result.secondary_error == "no fallback configured"
    assert secondary.calls == []


def test_a_provider_result_carries_usage_and_model():
    result = chat_completion_with_fallback([{"role": "user", "content": "x"}], primary_client=FakeClient([{"a": 1}]))
    assert result.provider_used == "groq" and result.model == "openai/gpt-oss-120b"
    assert result.usage.prompt_tokens == 100


def test_extractor_reports_real_token_usage_for_each_call():
    usage: list[dict] = []
    result = extractor.extract_scheme("text", client=FakeClient([CORE, META]), usage_sink=usage.append)
    assert isinstance(result, Scheme)
    assert [u["call"] for u in usage] == ["scheme_core_extraction", "scheme_meta_extraction"]
    assert all(u["total_tokens"] == 120 for u in usage)


def test_extractor_with_provider_openrouter_builds_the_shared_client_and_handles_its_errors(monkeypatch):
    fake = FakeClient([openai.APIError("boom", httpx.Request("POST", "https://openrouter.ai"), body=None)])
    built = []
    monkeypatch.setattr(provider, "make_client", lambda config: built.append(config.name) or fake)
    result = extractor.extract_scheme("text", provider="openrouter")
    assert built == ["openrouter"]
    assert isinstance(result, extractor.ExtractionFailure) and result.reason == "api_error"


def test_extractor_default_provider_is_still_groqs_own_client():
    """conftest blocks real Groq construction, so reaching it proves the default path is unchanged."""
    with pytest.raises(AssertionError, match="real Groq client was constructed"):
        extractor.extract_scheme("text")


def test_judge_reports_usage():
    usage: list[dict] = []
    draft = Scheme.model_validate({**CORE, **META})
    report = judge_repair.run_judge(draft, "doc", client=FakeClient([{"findings": []}]), usage_sink=usage.append)
    assert not isinstance(report, judge_repair.JudgeFailure)
    assert usage and usage[0]["call"] == "judge_report"


@pytest.mark.parametrize("kwargs,primary,secondary", [
    ({}, GROQ, OPENROUTER),                                     # default unchanged
    ({"fallback": False}, GROQ, None),                          # experiments
    ({"provider": "openrouter"}, OPENROUTER, None),             # no self-fallback
])
def test_baseline2_provider_and_fallback(kwargs, primary, secondary):
    captured = {}

    def fake(messages, primary, secondary, **kw):
        captured.update(primary=primary, secondary=secondary)
        return provider.ProviderResult(content='{"verdict": "eligible", "reason": "r"}', provider_used=primary.name,
                                       usage=SimpleNamespace(prompt_tokens=5, completion_tokens=2))

    with patch.object(dlb, "chat_completion_with_fallback", side_effect=fake):
        answer = dlb.ask_direct("doc", {"self": {}}, **kwargs)
    assert captured == {"primary": primary, "secondary": secondary}
    assert answer.provider_used == primary.name and answer.prompt_tokens == 5
