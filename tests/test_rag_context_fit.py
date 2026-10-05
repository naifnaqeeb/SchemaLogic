"""The judge fits retrieved context into Groq's 8k request ceiling (2026-10-05 fix for the RAG
validation's 4/4 api_error). Without retrieved context nothing changes."""

from __future__ import annotations

import json
from types import SimpleNamespace

from schemelogic.extraction import judge_repair as jr
from schemelogic.schema.models import Scheme

CHUNK = "[GR_{i} — citation — effective 2024-07-03 — source_type: primary — similarity 0.5]\n" + "माझी लाडकी बहीण योजना " * 40


def _context(n: int) -> str:
    return "\n\n".join(CHUNK.format(i=i) for i in range(n))


def test_short_context_is_kept_whole():
    ctx, stats = jr.fit_retrieved_context(_context(1), "short prompt")
    assert ctx == _context(1) and stats["chunks_kept"] == 1


def test_long_context_keeps_whole_leading_chunks_within_the_ceiling():
    fixed = "x" * 3500 * 5  # ~5,000 prompt tokens before retrieval
    ctx, stats = jr.fit_retrieved_context(_context(12), fixed)
    assert 0 < stats["chunks_kept"] < 12
    assert ctx == _context(stats["chunks_kept"])  # whole chunks, best-ranked first
    assert jr._conservative_tokens(fixed) + jr._conservative_tokens(ctx) + jr._MIN_JUDGE_COMPLETION <= jr._REQUEST_CEILING


def test_devanagari_is_not_undercounted():
    assert jr._conservative_tokens("माझी लाडकी बहीण") > len("माझी लाडकी बहीण") / 3.5


class FakeClient:
    def __init__(self):
        self.calls = []
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        msg = SimpleNamespace(content=json.dumps({"findings": []}))
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="stop")], usage=None)


DRAFT = Scheme.model_validate({
    "scheme_id": "X", "unit_of_eligibility": "individual",
    "inclusion": {"cat": "demographic", "field": "is_woman", "op": "==", "value": True},
    "temporal_validity": {"extracted_at": "2026-01-01"},
    "extraction_metadata": {"confidence": 0.5, "source_clause": "x"}})


def test_run_judge_without_retrieval_sends_exactly_what_it_did():
    client = FakeClient()
    jr.run_judge(DRAFT, "doc", client=client)
    assert "RETRIEVED AMENDMENT CONTEXT" not in client.calls[0]["messages"][1]["content"]


def test_run_judge_with_a_long_retrieval_stays_under_the_request_ceiling():
    client = FakeClient()
    jr.run_judge(DRAFT, "document " * 100, client=client, retrieved_context=_context(20))
    sent = client.calls[0]
    prompt = sent["messages"][0]["content"] + sent["messages"][1]["content"]
    assert "RETRIEVED AMENDMENT CONTEXT" in sent["messages"][1]["content"]
    assert jr._conservative_tokens(prompt) + jr._MIN_JUDGE_COMPLETION <= jr._REQUEST_CEILING


def test_no_room_means_no_context_rather_than_a_rejected_request():
    client = FakeClient()
    jr.run_judge(DRAFT, "document " * 2500, client=client, retrieved_context=_context(20))
    assert "RETRIEVED AMENDMENT CONTEXT" not in client.calls[0]["messages"][1]["content"]
