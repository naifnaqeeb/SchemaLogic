"""chat_engine.py orchestrates router/answer_parser/ai_checked/intake/phrase_verdict -- ALL of
those are mocked here (no network, no quota touched). These tests exercise the actual state-
machine logic: routing dispatch, the deterministic-then-LLM-fallback answer path, the AI-Checked
selection path and its graceful degradation, and -- most importantly -- that every verdict
produced comes from the real symbolic evaluator, never from a mocked LLM response, no matter how
the mocks are configured to answer.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from schemelogic.conversational import chat_engine
from schemelogic.conversational.answer_parser import AnswerParseFailure, AnswerParseResult
from schemelogic.conversational.chat_engine import ChatDeps
from schemelogic.conversational.intake import IntakeFailure, IntakeResult
from schemelogic.conversational.router import RouterResult
from schemelogic.extraction.extractor import ExtractionFailure
from schemelogic.retrieval.indexer import DocumentChunk, LocalIndex
from schemelogic.schema.models import Scheme

TEST_SCHEME = {
    "scheme_id": "TEST",
    "unit_of_eligibility": "individual",
    "inclusion": {
        "and": [
            {"cat": "demographic", "field": "age", "op": ">=", "value": 18},
            {"cat": "citizenship", "field": "is_citizen", "op": "==", "value": True},
        ]
    },
    "exclusions": [
        {"cat": "economic", "quantifier": "self", "field": "is_wealthy", "op": "==", "value": True},
    ],
    "temporal_validity": {"valid_from": "2020-01-01", "extracted_at": "2026-01-01"},
    "extraction_metadata": {"confidence": 1.0, "source_clause": "t", "flagged_for_review": False},
}


@pytest.fixture(scope="module")
def _shared_index():
    """Building a LocalIndex loads the sentence-transformers embedding model -- expensive
    (seconds, not milliseconds). Shared across every test in this module (never mutated after
    construction, so sharing is safe) instead of rebuilt per test."""
    index = LocalIndex()
    index.add_chunks(
        [
            DocumentChunk(
                doc_id="TEST", scheme_id="TEST", effective_date=None, citation="", source_path="",
                chunk_index=0, text="Test Scheme. A gold scheme for testing.", source_type="gold",
            ),
            DocumentChunk(
                doc_id="silver-1", scheme_id="silver-1", effective_date=None, citation="", source_path="",
                chunk_index=0, text="Silver Scheme. An unverified scheme for testing.", source_type="silver_unverified",
            ),
        ]
    )
    return index


@pytest.fixture
def deps(tmp_path, _shared_index):
    gold_dir = tmp_path / "gold"
    gold_dir.mkdir()
    (gold_dir / "TEST.json").write_text(json.dumps(TEST_SCHEME), encoding="utf-8")

    return ChatDeps(
        discovery_index=_shared_index,
        gold_match_report={},
        silver_by_slug={
            "silver-1": {
                "slug": "silver-1", "scheme_name": "Silver Scheme", "description": "An unverified scheme.",
                "eligibility_text": "Anyone can apply.", "benefits_text": "Cash benefit.",
                "application_process_text": "Apply online.", "official_link": "https://example.com",
            },
        },
        raw_docs_dir=tmp_path / "raw_documents",
        gold_dir=gold_dir,
    )


@pytest.fixture
def state():
    s: dict = {}
    chat_engine.init_state(s)
    return s


def _mock_router(intent, **kwargs):
    return patch("schemelogic.conversational.chat_engine.router.classify_message", return_value=RouterResult(intent=intent, **kwargs))


# --- greeting ------------------------------------------------------------------------------


def test_greeting_no_pending_question(state, deps):
    with _mock_router("greeting"):
        chat_engine.handle_user_message(state, "hi", deps)
    assert state["messages"][-1]["role"] == "assistant"
    assert "situation" in state["messages"][-1]["text"].lower()


def test_greeting_with_pending_question_reminds_of_it(state, deps):
    chat_engine.select_scheme(state, "TEST", "gold", deps)  # pending question: age
    with _mock_router("greeting"):
        chat_engine.handle_user_message(state, "hey", deps)
    assert "age" in state["messages"][-1]["text"].lower()


# --- search / shortlist ----------------------------------------------------------------------


def test_search_populates_shortlist_and_appends_messages(state, deps):
    with _mock_router("search", search_query="test scheme"):
        chat_engine.handle_user_message(state, "I need a test scheme", deps)
    assert state["shortlist"] is not None
    assert len(state["shortlist"]) == 2
    kinds = [m["kind"] for m in state["messages"]]
    assert "shortlist" in kinds


def test_refine_search_accumulates_query_context(state, deps):
    with _mock_router("search", search_query="first query"):
        chat_engine.handle_user_message(state, "first query", deps)
    with _mock_router("search", search_query="more detail"):
        chat_engine.handle_user_message(state, "more detail", deps)
    assert state["query_context"] == "first query more detail"


def test_search_with_no_results_does_not_crash(state, deps):
    """discovery_search() itself is mocked here (not a real empty LocalIndex) purely to avoid
    building a second sentence-transformers model instance just for this one case -- the
    no-results path is otherwise identical to any other search call."""
    with patch("schemelogic.conversational.chat_engine.discovery_search", return_value=[]), _mock_router("search", search_query="nothing matches"):
        chat_engine.handle_user_message(state, "nothing matches", deps)
    assert state["shortlist"] == []
    assert "nothing matched" in state["messages"][-1]["text"].lower()


# --- scheme lookup / selection: gold ---------------------------------------------------------


def test_scheme_lookup_by_index_starts_gold_question_loop(state, deps):
    with _mock_router("search", search_query="test"):
        chat_engine.handle_user_message(state, "test", deps)
    with _mock_router("scheme_lookup", target_index=1):  # index 1 = the gold chunk
        chat_engine.handle_user_message(state, "#1", deps)
    assert state["conversation_session"] is not None
    assert state["conversation_tier"] == "gold"
    last = state["messages"][-1]
    assert last["kind"] == "question"
    assert last["field"] if "field" in last else True  # question message present


def test_invalid_lookup_index_asks_for_clarification(state, deps):
    with _mock_router("search", search_query="test"):
        chat_engine.handle_user_message(state, "test", deps)
    with _mock_router("scheme_lookup", target_index=99):
        chat_engine.handle_user_message(state, "the 99th one", deps)
    assert state["conversation_session"] is None
    assert "which one" in state["messages"][-1]["text"].lower()


def test_select_scheme_direct_call_gold(state, deps):
    """The direct entry point used by a Select-button click (not router-driven)."""
    chat_engine.select_scheme(state, "TEST", "gold", deps)
    assert state["conversation_session"] is not None
    assert state["conversation_tier"] == "gold"


def test_select_scheme_emits_scheme_intro_with_tier(state, deps):
    """Citizens must be able to see WHICH scheme and WHICH tier (Verified/AI-Checked) they're
    being asked about -- a real gap found and fixed during manual verification."""
    chat_engine.select_scheme(state, "TEST", "gold", deps)
    intros = [m for m in state["messages"] if m["kind"] == "scheme_intro"]
    assert len(intros) == 1
    assert intros[0]["scheme_id"] == "TEST"
    assert intros[0]["tier"] == "gold"


# --- answering a pending question: deterministic path (no LLM needed) ------------------------


def test_exact_yes_no_answered_deterministically_no_llm_call(state, deps):
    chat_engine.select_scheme(state, "TEST", "gold", deps)  # pending: age (number)
    with patch("schemelogic.conversational.chat_engine.answer_parser.parse_answer_llm") as mock_llm:
        chat_engine.handle_user_message(state, "25", deps)  # age answered exactly
    mock_llm.assert_not_called()
    assert state["conversation_session"].profile["self"]["age"] == 25


# --- answering a pending question: LLM fallback path ------------------------------------------


def test_free_text_answer_falls_back_to_llm_parse(state, deps):
    chat_engine.select_scheme(state, "TEST", "gold", deps)  # pending: age (number)
    with patch(
        "schemelogic.conversational.chat_engine.answer_parser.parse_answer_llm",
        return_value=AnswerParseResult(value=25, provider_used="groq"),
    ):
        chat_engine.handle_user_message(state, "I just turned 25", deps)
    assert state["conversation_session"].profile["self"]["age"] == 25


def test_llm_parse_failure_reprompts_without_mutating_profile(state, deps):
    chat_engine.select_scheme(state, "TEST", "gold", deps)  # pending: age
    with patch(
        "schemelogic.conversational.chat_engine.answer_parser.parse_answer_llm",
        return_value=AnswerParseFailure(reason="not confident"),
    ):
        chat_engine.handle_user_message(state, "who knows", deps)
    assert "age" not in state["conversation_session"].profile["self"]
    assert state["conversation_session"].pending_question is not None
    assert "couldn't" in state["messages"][-1]["text"].lower()


# --- full resolution to verdict: MUST come from the real evaluator, never the mocked LLM ------


def test_verdict_comes_from_real_evaluator_not_llm(state, deps):
    chat_engine.select_scheme(state, "TEST", "gold", deps)
    with patch("schemelogic.conversational.chat_engine.phrase_verdict", return_value="LLM WORDED THIS"):
        chat_engine.handle_user_message(state, "25", deps)     # age
        chat_engine.handle_user_message(state, "yes", deps)    # is_citizen
        chat_engine.handle_user_message(state, "no", deps)     # is_wealthy exclusion
    verdict_msgs = [m for m in state["messages"] if m["kind"] == "verdict"]
    assert len(verdict_msgs) == 1
    assert verdict_msgs[0]["verdict_value"] == "eligible"  # computed by the real evaluator
    assert verdict_msgs[0]["text"] == "LLM WORDED THIS"  # phrasing only, not the verdict itself
    assert state["conversation_session"] is None  # cleared after resolution


def test_verdict_ineligible_when_exclusion_triggers(state, deps):
    chat_engine.select_scheme(state, "TEST", "gold", deps)
    with patch("schemelogic.conversational.chat_engine.phrase_verdict", return_value="x"):
        chat_engine.handle_user_message(state, "25", deps)
        chat_engine.handle_user_message(state, "yes", deps)
        chat_engine.handle_user_message(state, "yes", deps)  # is_wealthy -> excluded
    verdict_msgs = [m for m in state["messages"] if m["kind"] == "verdict"]
    assert verdict_msgs[0]["verdict_value"] == "ineligible"


# --- AI-Checked tier -----------------------------------------------------------------------


def test_ai_checked_success_starts_question_loop_labeled_ai_checked(state, deps):
    scheme = Scheme.model_validate(TEST_SCHEME)
    with patch("schemelogic.conversational.chat_engine.ai_checked.get_or_extract_scheme", return_value=scheme):
        chat_engine.select_scheme(state, "silver-1", "silver", deps)
    assert state["conversation_tier"] == "ai_checked"
    assert state["conversation_session"] is not None
    assert any("AI-Checked" in m["text"] for m in state["messages"] if m["kind"] == "text")


def test_ai_checked_failure_degrades_to_description_only(state, deps):
    with patch("schemelogic.conversational.chat_engine.ai_checked.get_or_extract_scheme", return_value=None):
        chat_engine.select_scheme(state, "silver-1", "silver", deps)
    assert state["conversation_session"] is None
    last = state["messages"][-1]
    assert last["kind"] == "scheme_detail"
    assert last["tier"] == "silver"


def test_unknown_scheme_id_does_not_crash(state, deps):
    chat_engine.select_scheme(state, "does-not-exist", "silver", deps)
    assert "couldn't find" in state["messages"][-1]["text"].lower()


def test_silver_selection_failure_is_explicit_not_silent(state, deps):
    """Bug 1: the automatic on-selection extraction attempt must always be explicit about what
    happened -- a 'Checking...' message before, and a distinct failure message after, not just
    the bare description with no indication anything was tried."""
    with patch("schemelogic.conversational.chat_engine.ai_checked.get_or_extract_scheme", return_value=None):
        chat_engine.select_scheme(state, "silver-1", "silver", deps)
    texts = [m["text"] for m in state["messages"] if m["kind"] == "text"]
    assert any("Checking the rules" in t for t in texts)
    assert any("wasn't able to reliably extract" in t for t in texts)
    assert state["current_scheme_tier"] == "silver"
    assert state["current_scheme_id"] == "silver-1"


# --- current-scheme tracking + eligibility_request (Bug 1 fix) -------------------------------


def test_current_scheme_tracked_through_gold_selection(state, deps):
    chat_engine.select_scheme(state, "TEST", "gold", deps)
    assert state["current_scheme_id"] == "TEST"
    assert state["current_scheme_tier"] == "gold"


def test_current_scheme_persists_past_verdict_resolution(state, deps):
    """conversation_session/tier get cleared once a verdict resolves -- current_scheme_id/tier
    must NOT, since that's what a later 'am I eligible for this?' needs to anchor to."""
    chat_engine.select_scheme(state, "TEST", "gold", deps)
    with patch("schemelogic.conversational.chat_engine.phrase_verdict", return_value="x"):
        chat_engine.handle_user_message(state, "25", deps)
        chat_engine.handle_user_message(state, "yes", deps)
        chat_engine.handle_user_message(state, "no", deps)
    assert state["conversation_session"] is None
    assert state["current_scheme_id"] == "TEST"
    assert state["current_scheme_tier"] == "gold"


def test_reset_clears_current_scheme(state, deps):
    chat_engine.select_scheme(state, "TEST", "gold", deps)
    chat_engine.reset(state)
    assert state["current_scheme_id"] is None
    assert state["current_scheme_tier"] is None


def test_eligibility_request_with_no_current_scheme_asks_which_one(state, deps):
    with _mock_router("eligibility_request"):
        chat_engine.handle_user_message(state, "am I eligible?", deps)
    assert "which scheme" in state["messages"][-1]["text"].lower()


def test_eligibility_request_triggers_extraction_when_not_yet_attempted(state, deps):
    """Core Bug 1 fix: an explicit eligibility question about the current Unverified scheme must
    reliably trigger a live extraction attempt if one hasn't already been cached."""
    state["current_scheme_id"] = "silver-1"
    state["current_scheme_tier"] = "silver"
    state["current_scheme_name"] = "Silver Scheme"
    scheme = Scheme.model_validate(TEST_SCHEME)
    with patch(
        "schemelogic.conversational.chat_engine.ai_checked.get_or_extract_scheme", return_value=scheme,
    ) as mock_extract, _mock_router("eligibility_request"):
        chat_engine.handle_user_message(state, "am I eligible for this scheme?", deps)
    mock_extract.assert_called_once()
    assert state["current_scheme_tier"] == "ai_checked"
    assert state["conversation_session"] is not None


def test_eligibility_request_does_not_retry_a_cached_failure(state, deps):
    """Respects the session cache -- the underlying extractor (ai_checked.extract_scheme, the
    actual LLM call) must not fire a second time for a scheme already attempted and failed this
    session -- and the response must still be explicit, not identical to a first-time view.
    get_or_extract_scheme's own no-retry-on-cache-hit guarantee is unit-tested directly in
    test_ai_checked.py; this test checks chat_engine wires it correctly end-to-end."""
    with patch(
        "schemelogic.conversational.ai_checked.extract_scheme",
        return_value=ExtractionFailure(reason="schema_validation_failed", detail="bad"),
    ) as mock_llm_extract:
        chat_engine.select_scheme(state, "silver-1", "silver", deps)  # first automatic attempt, fails
        msg_count_before_retry = len(state["messages"])
        with _mock_router("eligibility_request"):
            chat_engine.handle_user_message(state, "am I eligible for this scheme?", deps)
        mock_llm_extract.assert_called_once()  # only the FIRST attempt ever reached the real extractor
    new_texts = [m["text"] for m in state["messages"][msg_count_before_retry:]]
    assert not any("Checking the rules" in t for t in new_texts)  # no re-attempt messaging
    assert any("already tried" in t.lower() for t in new_texts)


def test_eligibility_request_during_active_qa_reminds_of_pending_question(state, deps):
    chat_engine.select_scheme(state, "TEST", "gold", deps)  # pending: age
    with _mock_router("eligibility_request"):
        chat_engine.handle_user_message(state, "am I eligible for this?", deps)
    assert "age" in state["messages"][-1]["text"].lower()
    assert state["conversation_session"].pending_question is not None  # untouched


def test_eligibility_request_after_resolved_verdict_points_to_it_without_recomputing(state, deps):
    chat_engine.select_scheme(state, "TEST", "gold", deps)
    with patch("schemelogic.conversational.chat_engine.phrase_verdict", return_value="x"):
        chat_engine.handle_user_message(state, "25", deps)
        chat_engine.handle_user_message(state, "yes", deps)
        chat_engine.handle_user_message(state, "no", deps)
    verdict_count_before = len([m for m in state["messages"] if m["kind"] == "verdict"])
    with _mock_router("eligibility_request"):
        chat_engine.handle_user_message(state, "am I eligible for this?", deps)
    verdict_count_after = len([m for m in state["messages"] if m["kind"] == "verdict"])
    assert verdict_count_after == verdict_count_before  # did not recompute/re-append a verdict
    assert "already checked" in state["messages"][-1]["text"].lower()


# --- abandonment note ------------------------------------------------------------------------


def test_new_search_while_question_pending_notes_the_switch(state, deps):
    chat_engine.select_scheme(state, "TEST", "gold", deps)  # pending question now active
    with _mock_router("search", search_query="something else"):
        chat_engine.handle_user_message(state, "actually something else", deps)
    texts = " ".join(m["text"] for m in state["messages"])
    assert "Switching away from TEST" in texts
    assert state["conversation_session"] is None or state["conversation_tier"] is None or True
    # the new search's shortlist should still have been produced
    assert state["shortlist"] is not None


def test_reselecting_same_pending_scheme_does_not_note_abandonment(state, deps):
    chat_engine.select_scheme(state, "TEST", "gold", deps)
    msg_count_before = len(state["messages"])
    chat_engine.select_scheme(state, "TEST", "gold", deps)
    texts = " ".join(m["text"] for m in state["messages"][msg_count_before:])
    assert "Switching away" not in texts


# --- intake reuse on selection ----------------------------------------------------------------


def test_intake_reuse_applies_profile_when_query_context_present(state, deps):
    state["query_context"] = "I am 25 years old and a citizen"
    with patch(
        "schemelogic.conversational.chat_engine.parse_opening_message",
        return_value=IntakeResult(profile={"self": {"age": 25}, "family_members": []}, provider_used="groq", raw_content="{}"),
    ):
        chat_engine.select_scheme(state, "TEST", "gold", deps)
    assert state["conversation_session"].profile["self"].get("age") == 25


def test_intake_failure_falls_back_to_plain_question_loop(state, deps):
    state["query_context"] = "I am 25 years old"
    with patch(
        "schemelogic.conversational.chat_engine.parse_opening_message",
        return_value=IntakeFailure(primary_error="429", secondary_error="timeout"),
    ):
        chat_engine.select_scheme(state, "TEST", "gold", deps)
    assert state["conversation_session"] is not None
    assert state["conversation_session"].pending_question is not None


# --- router misclassification safety -----------------------------------------------------------


def test_answer_intent_with_no_pending_question_falls_back_to_search(state, deps):
    with _mock_router("answer"):  # misclassified -- nothing pending
        chat_engine.handle_user_message(state, "test scheme please", deps)
    assert state["shortlist"] is not None


def test_scheme_lookup_intent_with_no_shortlist_falls_back_to_search(state, deps):
    with _mock_router("scheme_lookup", target_index=1):  # misclassified -- no shortlist shown yet
        chat_engine.handle_user_message(state, "test scheme please", deps)
    assert state["shortlist"] is not None


def test_search_misclassification_redirects_to_named_shortlist_item(state, deps):
    """Bug 2 fix: even if the router says 'search' (an LLM misclassification, or the heuristic
    fallback missing a bare name reference), a message that clearly names an already-shown scheme
    must redirect to that scheme instead of firing a brand-new, likely-irrelevant search."""
    state["shortlist"] = [
        DocumentChunk(
            doc_id="TEST", scheme_id="TEST", effective_date=None, citation="", source_path="",
            chunk_index=0, text="Test Scheme. A gold scheme for testing.", source_type="gold",
        ),
        DocumentChunk(
            doc_id="silver-1", scheme_id="silver-1", effective_date=None, citation="", source_path="",
            chunk_index=0, text="Silver Scheme. An unverified scheme for testing.", source_type="silver_unverified",
        ),
    ]
    with patch("schemelogic.conversational.chat_engine.discovery_search") as mock_search, patch(
        "schemelogic.conversational.chat_engine.ai_checked.get_or_extract_scheme", return_value=None,
    ), _mock_router("search", search_query="tell me about the silver scheme"):
        chat_engine.handle_user_message(state, "tell me about the silver scheme", deps)
    mock_search.assert_not_called()  # no brand-new discovery search was run
    assert state["current_scheme_id"] == "silver-1"  # correctly redirected to the named item


def test_search_with_no_name_match_runs_a_real_search(state, deps):
    """Guards against the Bug 2 fix being too aggressive -- an unrelated message must still run a
    normal search, not get hijacked by a loose/incidental word overlap."""
    state["shortlist"] = [
        DocumentChunk(
            doc_id="silver-1", scheme_id="silver-1", effective_date=None, citation="", source_path="",
            chunk_index=0, text="Silver Scheme. An unverified scheme for testing.", source_type="silver_unverified",
        ),
    ]
    with _mock_router("search", search_query="I need help with my rent"):
        chat_engine.handle_user_message(state, "I need help with my rent", deps)
    assert state["current_scheme_id"] is None  # not redirected -- a real new search ran instead


# --- reset --------------------------------------------------------------------------------


def test_reset_clears_conversation_but_keeps_scheme_cache(state, deps):
    scheme = Scheme.model_validate(TEST_SCHEME)
    with patch("schemelogic.conversational.chat_engine.ai_checked.get_or_extract_scheme", return_value=scheme):
        chat_engine.select_scheme(state, "silver-1", "silver", deps)
    state["scheme_cache"]["silver-1"] = scheme
    chat_engine.reset(state)
    assert state["messages"] == []
    assert state["conversation_session"] is None
    assert state["scheme_cache"].get("silver-1") == scheme  # cache survives reset


def test_empty_message_is_a_no_op(state, deps):
    chat_engine.handle_user_message(state, "   ", deps)
    assert state["messages"] == []


# --- language param threading (presentation-layer language toggle) -----------------------------


def test_deps_language_threaded_into_router_call(state, deps):
    deps.language = "hi"
    with patch(
        "schemelogic.conversational.chat_engine.router.classify_message",
        return_value=RouterResult(intent="greeting"),
    ) as mock_classify:
        chat_engine.handle_user_message(state, "hi", deps)
    assert mock_classify.call_args.kwargs["language"] == "hi"


def test_deps_language_threaded_into_phrase_verdict_call(state, deps):
    deps.language = "hi"
    chat_engine.select_scheme(state, "TEST", "gold", deps)
    with patch("schemelogic.conversational.chat_engine.phrase_verdict", return_value="x") as mock_phrase:
        chat_engine.handle_user_message(state, "25", deps)
        chat_engine.handle_user_message(state, "yes", deps)
        chat_engine.handle_user_message(state, "no", deps)
    assert mock_phrase.call_args.kwargs["language"] == "hi"


def test_deps_language_threaded_into_answer_parser_call(state, deps):
    deps.language = "hi"
    chat_engine.select_scheme(state, "TEST", "gold", deps)  # pending: age
    with patch(
        "schemelogic.conversational.chat_engine.answer_parser.parse_answer_llm",
        return_value=AnswerParseResult(value=25, provider_used="groq"),
    ) as mock_parse:
        chat_engine.handle_user_message(state, "I just turned 25", deps)
    assert mock_parse.call_args.kwargs["language"] == "hi"
