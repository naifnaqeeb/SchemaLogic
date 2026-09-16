"""FastAPI wrapper tests. Two kinds of coverage here, deliberately kept separate:

1. Real, unmocked calls through LLM-FREE paths only -- selecting a gold scheme with NO query
   context (no intake call) and answering with quick-reply buttons (bypasses the router and the
   free-text answer-parser entirely, same as the Streamlit app). These exercise the actual
   pass-through wiring end-to-end with zero network/LLM cost, same safety discipline as every
   other test session tonight.
2. Anything that would reach phrase_verdict()/router.classify_message()/answer_parser -- mocked
   exactly the way chat_engine.py's own test suite already mocks them. This file adds NO new
   coverage of chat_engine's internal correctness (that's chat_engine's own test suite's job) --
   it only checks that the API layer wires requests/responses to those functions correctly.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from schemelogic.conversational.router import RouterResult
from schemelogic.extraction.extractor import ExtractionFailure

client = TestClient(app)


def _new_session_id(name: str) -> str:
    return f"test-session-{name}"


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_list_examples_does_not_leak_profile():
    r = client.get("/examples")
    assert r.status_code == 200
    examples = r.json()
    assert len(examples) == 3
    for e in examples:
        assert set(e.keys()) == {"label", "description", "scheme_id"}


# --- GET /schemes, GET /schemes/{id} -- pure pass-through over discovery/categories, no LLM ----


def test_list_schemes_default():
    r = client.get("/schemes")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] > 2000  # 7 gold + ~2066 silver
    assert "farmers" in body["categories"]
    assert len(body["results"]) == 60  # default limit


def test_list_schemes_search_query():
    r = client.get("/schemes", params={"query": "Ayushman"})
    body = r.json()
    assert body["total"] >= 1
    assert all("ayushman" in row["name"].lower() for row in body["results"])


def test_list_schemes_category_filter_matches_real_farmers_count():
    r = client.get("/schemes", params={"category": "farmers", "limit": 1000})
    body = r.json()
    assert body["total"] > 300  # matches the empirical whole-dataset check from the build session
    assert all("farmers" in row["categories"] for row in body["results"])


def test_get_scheme_known_gold_id():
    r = client.get("/schemes/PM-KISAN")
    assert r.status_code == 200
    body = r.json()
    assert body["source_type"] == "gold"
    assert body["id"] == "PM-KISAN"


def test_get_scheme_unknown_id_404():
    r = client.get("/schemes/does-not-exist-at-all")
    assert r.status_code == 404


# --- POST /chat/example -- LLM-free path (Missing-data case leaves one field unset, so it never
#     reaches a resolved verdict / never calls phrase_verdict) ---------------------------------


def test_select_example_missing_data_case_reaches_a_question_no_llm():
    session_id = _new_session_id("missing-data")
    r = client.post("/chat/example", json={"session_id": session_id, "label": "Missing-data case"})
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == session_id
    assert body["current_scheme_id"] == "PM-KISAN"
    assert body["current_scheme_tier"] == "gold"
    assert body["pending_question"] is not None
    kinds = [m["kind"] for m in body["messages"]]
    assert "scheme_intro" in kinds
    assert "question" in kinds
    # shortlist/verdict never touched on this path
    assert "verdict" not in kinds


def test_unknown_example_label_404():
    r = client.post("/chat/example", json={"session_id": _new_session_id("bad"), "label": "not a real example"})
    assert r.status_code == 404


def test_quick_reply_advances_without_llm():
    """"Missing-data case" has exactly ONE field missing (citizenship) -- answering it completes
    the profile and resolves immediately, which reaches phrase_verdict(). Mocked defensively here
    for that reason (quick-reply itself -- session.apply_answer + session.advance -- is the
    LLM-free part actually under test; the resolution step it triggers is not)."""
    session_id = _new_session_id("quick-reply")
    client.post("/chat/example", json={"session_id": session_id, "label": "Missing-data case"})

    with patch("schemelogic.conversational.chat_engine.phrase_verdict", return_value="MOCKED"):
        r = client.post("/chat/quick_reply", json={"session_id": session_id, "reply": "Yes"})
    assert r.status_code == 200
    body = r.json()
    verdict_msgs = [m for m in body["messages"] if m["kind"] == "verdict"]
    assert len(verdict_msgs) == 1
    assert verdict_msgs[0]["verdict_value"] == "eligible"


def test_reset_clears_the_session():
    session_id = _new_session_id("reset")
    client.post("/chat/example", json={"session_id": session_id, "label": "Missing-data case"})
    r = client.post("/chat/reset", json={"session_id": session_id})
    assert r.status_code == 200
    body = r.json()
    assert body["messages"] == []
    assert body["current_scheme_id"] is None


def test_select_directly_by_scheme_id_gold_no_query_context():
    """POST /chat/select with no prior search (no query_context) never calls the intake parser --
    same LLM-free guarantee the browse page's direct-select always had."""
    session_id = _new_session_id("direct-select")
    r = client.post("/chat/select", json={"session_id": session_id, "scheme_id": "PM-KISAN", "source_type": "gold"})
    assert r.status_code == 200
    body = r.json()
    assert body["current_scheme_id"] == "PM-KISAN"
    assert body["pending_question"] is not None


# --- Sessions are isolated from each other ------------------------------------------------------


def test_sessions_are_isolated():
    a, b = _new_session_id("iso-a"), _new_session_id("iso-b")
    client.post("/chat/example", json={"session_id": a, "label": "Missing-data case"})
    fresh_b = client.get(f"/chat/{b}").json()
    assert fresh_b["messages"] == []
    assert fresh_b["current_scheme_id"] is None


# --- paths that WOULD reach a live LLM call -- mocked, same pattern chat_engine's own tests use -


def test_verdict_resolution_via_api_uses_mocked_phrase_verdict_not_real_call():
    """"Group D exception case" has every field already filled in -- selecting it resolves
    IMMEDIATELY (chat_engine's own docstring says so), which means it reaches phrase_verdict() on
    the very first call. Must be mocked, exactly like chat_engine's own verdict tests."""
    session_id = _new_session_id("group-d")
    with patch("schemelogic.conversational.chat_engine.phrase_verdict", return_value="MOCKED PHRASING"):
        r = client.post("/chat/example", json={"session_id": session_id, "label": "Group D exception case"})
    assert r.status_code == 200
    body = r.json()
    verdict_msgs = [m for m in body["messages"] if m["kind"] == "verdict"]
    assert len(verdict_msgs) == 1
    assert verdict_msgs[0]["verdict_value"] == "eligible"  # from the REAL evaluator, not the mock
    assert verdict_msgs[0]["text"] == "MOCKED PHRASING"  # wording only, from the mock
    assert body["current_scheme_id"] == "PM-KISAN"  # current_scheme persists past resolution
    assert body["pending_question"] is None  # nothing left pending
    # plain_explanation reuses the existing trace_to_citizen_english() renderer -- the frontend
    # has no business logic of its own to reimplement that walk.
    assert isinstance(verdict_msgs[0]["plain_explanation"], str)
    assert len(verdict_msgs[0]["plain_explanation"]) > 0


def test_chat_endpoint_search_intent_mocked_router():
    """A typed message always goes through the router first -- mocked here (same as
    router.py/chat_engine.py's own test suites) rather than hit a live provider."""
    session_id = _new_session_id("search")
    with patch(
        "schemelogic.conversational.chat_engine.router.classify_message",
        return_value=RouterResult(intent="search", search_query="farmer support"),
    ):
        r = client.post("/chat", json={"session_id": session_id, "message": "farmer support"})
    assert r.status_code == 200
    body = r.json()
    kinds = [m["kind"] for m in body["messages"]]
    assert "shortlist" in kinds


def test_dataclass_fields_in_shortlist_message_are_json_safe():
    """DocumentChunk instances embedded in a 'shortlist' message must serialize cleanly (this is
    exactly the bug class api/serialize.py exists to prevent)."""
    session_id = _new_session_id("serialize-check")
    with patch(
        "schemelogic.conversational.chat_engine.router.classify_message",
        return_value=RouterResult(intent="search", search_query="Ayushman Bharat"),
    ):
        r = client.post("/chat", json={"session_id": session_id, "message": "Ayushman Bharat"})
    body = r.json()  # TestClient already round-trips this through real JSON encode/decode
    shortlist_msgs = [m for m in body["messages"] if m["kind"] == "shortlist"]
    assert len(shortlist_msgs) == 1
    items = shortlist_msgs[0]["items"]
    assert len(items) > 0
    for item in items:
        assert isinstance(item["doc_id"], str)
        assert isinstance(item["text"], str)
        assert item["source_type"] in ("gold", "silver_unverified")


# --- AI-Checked / silver flows through the API -- mocked, same pattern chat_engine's own suite --


def _a_real_silver_slug() -> str:
    from api import deps as api_deps

    return api_deps.get_silver_records()[0]["slug"]


def test_select_silver_scheme_ai_checked_success_via_api():
    from schemelogic.schema.models import Scheme

    from tests.fixtures import PM_KISAN

    slug = _a_real_silver_slug()
    session_id = _new_session_id("ai-checked-success")
    scheme = Scheme.model_validate(PM_KISAN)
    with patch("schemelogic.conversational.chat_engine.ai_checked.extract_with_reason", return_value=(scheme, None)):
        r = client.post("/chat/select", json={"session_id": session_id, "scheme_id": slug, "source_type": "silver"})
    assert r.status_code == 200
    body = r.json()
    assert body["current_scheme_tier"] == "ai_checked"
    assert body["pending_question"] is not None
    assert any("AI-Checked" in m["text"] for m in body["messages"] if m["kind"] == "text")


def test_select_silver_scheme_extraction_failure_degrades_to_scheme_detail_via_api():
    slug = _a_real_silver_slug()
    session_id = _new_session_id("ai-checked-failure")
    with patch("schemelogic.conversational.chat_engine.ai_checked.extract_with_reason", return_value=(None, ExtractionFailure(reason="schema_validation_failed", detail="x"))):
        r = client.post("/chat/select", json={"session_id": session_id, "scheme_id": slug, "source_type": "silver"})
    assert r.status_code == 200
    body = r.json()
    assert body["current_scheme_tier"] == "silver"
    kinds = [m["kind"] for m in body["messages"]]
    assert "scheme_detail" in kinds
    detail_msg = next(m for m in body["messages"] if m["kind"] == "scheme_detail")
    assert detail_msg["record"]["scheme_name"] is not None
    # scheme_detail's record/description text must already be mojibake-clean (fixed at the data
    # layer -- this just confirms the API doesn't reintroduce corruption on the way out)
    assert "â€" not in str(detail_msg["record"])
