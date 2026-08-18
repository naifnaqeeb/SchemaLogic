"""All LLM calls mocked -- no network, no API keys, no quota touched. Router classification
QUALITY against real messages is explicitly NOT verified here (that needs a live call) -- these
tests only verify: the JSON contract is honored when the provider returns well-formed output, and
every failure mode (both providers down, malformed JSON, an unrecognized intent) degrades to the
heuristic fallback instead of raising.
"""

from unittest.mock import MagicMock, patch

from schemelogic.conversational.router import RouterResult, classify_message, match_shortlist_name
from schemelogic.llm.provider import ProviderFailure, ProviderResult


def _mock_response(content: str):
    return patch(
        "schemelogic.conversational.router.chat_completion_with_fallback",
        return_value=ProviderResult(content=content, provider_used="groq"),
    )


def test_llm_search_intent_parsed():
    with _mock_response('{"intent": "search", "search_query": "farmer looking for support", "target_index": null}'):
        result = classify_message("I'm a farmer looking for support")
    assert result == RouterResult(intent="search", search_query="farmer looking for support", target_index=None, provider_used="groq")


def test_llm_search_intent_with_null_query_uses_raw_message():
    with _mock_response('{"intent": "search", "search_query": null, "target_index": null}'):
        result = classify_message("something for women")
    assert result.intent == "search"
    assert result.search_query == "something for women"


def test_llm_answer_intent():
    with _mock_response('{"intent": "answer", "search_query": null, "target_index": null}'):
        result = classify_message("yeah for sure", has_pending_question=True, pending_question_text="Are you a woman?")
    assert result.intent == "answer"


def test_llm_scheme_lookup_intent_with_index():
    with _mock_response('{"intent": "scheme_lookup", "search_query": null, "target_index": 2}'):
        result = classify_message("tell me more about the second one", has_shortlist=True, shortlist_names=["A", "B"])
    assert result.intent == "scheme_lookup"
    assert result.target_index == 2


def test_llm_greeting_intent():
    with _mock_response('{"intent": "greeting", "search_query": null, "target_index": null}'):
        result = classify_message("thanks so much!")
    assert result.intent == "greeting"


def test_both_providers_fail_falls_back_to_heuristic():
    with patch(
        "schemelogic.conversational.router.chat_completion_with_fallback",
        return_value=ProviderFailure(primary_error="429", secondary_error="timeout"),
    ):
        result = classify_message("hello")
    assert result.intent == "greeting"
    assert result.provider_used is None


def test_malformed_json_falls_back_to_heuristic():
    with _mock_response("not json {{{"):
        result = classify_message("I am a farmer", has_pending_question=False, has_shortlist=False)
    assert result.intent == "search"
    assert result.provider_used is None


def test_unrecognized_intent_falls_back_to_heuristic():
    with _mock_response('{"intent": "do_something_weird"}'):
        result = classify_message("hi")
    assert result.intent == "greeting"
    assert result.provider_used is None


# --- heuristic fallback, tested directly (this is the actual safety net during an outage) -----


def test_heuristic_greeting():
    with patch(
        "schemelogic.conversational.router.chat_completion_with_fallback",
        return_value=ProviderFailure(primary_error="x", secondary_error="y"),
    ):
        assert classify_message("hi").intent == "greeting"
        assert classify_message("thanks!").intent == "greeting"
        assert classify_message("Hello there").intent != "greeting"  # not an exact-match phrase, falls through


def test_heuristic_answer_when_pending_question():
    with patch(
        "schemelogic.conversational.router.chat_completion_with_fallback",
        return_value=ProviderFailure(primary_error="x", secondary_error="y"),
    ):
        result = classify_message("yes", has_pending_question=True)
    assert result.intent == "answer"


def test_heuristic_search_when_no_pending_question():
    with patch(
        "schemelogic.conversational.router.chat_completion_with_fallback",
        return_value=ProviderFailure(primary_error="x", secondary_error="y"),
    ):
        result = classify_message("I'm a farmer looking for financial help", has_pending_question=False)
    assert result.intent == "search"
    assert result.search_query == "I'm a farmer looking for financial help"


def test_heuristic_scheme_lookup_by_number():
    with patch(
        "schemelogic.conversational.router.chat_completion_with_fallback",
        return_value=ProviderFailure(primary_error="x", secondary_error="y"),
    ):
        result = classify_message("check #2", has_shortlist=True)
    assert result.intent == "scheme_lookup"
    assert result.target_index == 2


def test_heuristic_scheme_lookup_by_ordinal_word():
    with patch(
        "schemelogic.conversational.router.chat_completion_with_fallback",
        return_value=ProviderFailure(primary_error="x", secondary_error="y"),
    ):
        result = classify_message("tell me more about the third one", has_shortlist=True)
    assert result.intent == "scheme_lookup"
    assert result.target_index == 3


def test_heuristic_greeting_takes_priority_over_shortlist():
    """Even with a shortlist showing, a plain 'thanks' should not be misread as a lookup."""
    with patch(
        "schemelogic.conversational.router.chat_completion_with_fallback",
        return_value=ProviderFailure(primary_error="x", secondary_error="y"),
    ):
        result = classify_message("thanks", has_shortlist=True, has_pending_question=True)
    assert result.intent == "greeting"


# --- eligibility_request (Bug 1 fix) -----------------------------------------------------------


def test_llm_eligibility_request_intent():
    with _mock_response('{"intent": "eligibility_request", "search_query": null, "target_index": null}'):
        result = classify_message("am I eligible for this scheme?", has_current_scheme=True, current_scheme_name="Some Scheme")
    assert result.intent == "eligibility_request"


def test_heuristic_eligibility_request_when_current_scheme_present():
    with patch(
        "schemelogic.conversational.router.chat_completion_with_fallback",
        return_value=ProviderFailure(primary_error="x", secondary_error="y"),
    ):
        result = classify_message("am I eligible for this?", has_current_scheme=True)
    assert result.intent == "eligibility_request"


def test_heuristic_eligibility_phrase_without_current_scheme_falls_through():
    """Same phrasing, but nothing is currently in view -- must not fire eligibility_request with
    no scheme to anchor to (chat_engine gates on this too, but the router shouldn't even offer it)."""
    with patch(
        "schemelogic.conversational.router.chat_completion_with_fallback",
        return_value=ProviderFailure(primary_error="x", secondary_error="y"),
    ):
        result = classify_message("am I eligible for this?", has_current_scheme=False)
    assert result.intent != "eligibility_request"


def test_heuristic_eligibility_request_takes_priority_over_pending_answer():
    """An explicit eligibility question should not be misread as an answer to an unrelated
    pending question -- this was part of Bug 1's root cause."""
    with patch(
        "schemelogic.conversational.router.chat_completion_with_fallback",
        return_value=ProviderFailure(primary_error="x", secondary_error="y"),
    ):
        result = classify_message(
            "am I eligible for this scheme?", has_current_scheme=True, has_pending_question=True,
            pending_question_text="Are you a woman?",
        )
    assert result.intent == "eligibility_request"


def test_heuristic_various_eligibility_phrasings():
    with patch(
        "schemelogic.conversational.router.chat_completion_with_fallback",
        return_value=ProviderFailure(primary_error="x", secondary_error="y"),
    ):
        for phrase in ["do I qualify?", "can I apply for this?", "check my eligibility", "is this for me?"]:
            result = classify_message(phrase, has_current_scheme=True)
            assert result.intent == "eligibility_request", f"{phrase!r} should be eligibility_request"


# --- match_shortlist_name / scheme_lookup-by-name (Bug 2 fix) -----------------------------------


SHORTLIST_NAMES = [
    "Scheme For Subsidy On Interest For Establishment Of 1 To 20 Milch Animal Farm For Scheduled Tribe",
    "Pradhan Mantri Kisan Samman Nidhi",
    "Financial Assistance to Brackish Water Aquaculture Farms",
]


def test_match_shortlist_name_finds_distinctive_reference():
    idx = match_shortlist_name("just tell me the scheme here for scheduled tribe", SHORTLIST_NAMES)
    assert idx == 1


def test_match_shortlist_name_no_match_for_unrelated_text():
    assert match_shortlist_name("I need help paying rent this month", SHORTLIST_NAMES) is None


def test_match_shortlist_name_single_distinctive_word():
    idx = match_shortlist_name("what about the aquaculture one", SHORTLIST_NAMES)
    assert idx == 3


def test_match_shortlist_name_empty_shortlist():
    assert match_shortlist_name("scheduled tribe", []) is None


def test_match_shortlist_name_no_significant_words_in_message():
    assert match_shortlist_name("this that the a", SHORTLIST_NAMES) is None


def test_heuristic_uses_name_match_when_no_index_or_trigger_phrase():
    """The exact real-world failure from the manual test transcript: no number, no ordinal, no
    'tell me more'-style trigger phrase -- just a bare reference to the scheme's distinctive name."""
    with patch(
        "schemelogic.conversational.router.chat_completion_with_fallback",
        return_value=ProviderFailure(primary_error="x", secondary_error="y"),
    ):
        result = classify_message(
            "just tell me the scheme here for scheduled tribe",
            has_shortlist=True, shortlist_names=SHORTLIST_NAMES,
        )
    assert result.intent == "scheme_lookup"
    assert result.target_index == 1


# --- language param wiring (presentation-layer language toggle) --------------------------------


def test_language_hi_adds_hindi_note_to_system_prompt():
    mock_call = MagicMock(return_value=ProviderResult(content='{"intent": "greeting"}', provider_used="groq"))
    with patch("schemelogic.conversational.router.chat_completion_with_fallback", mock_call):
        classify_message("hi", language="hi")
    system_content = mock_call.call_args.args[0][0]["content"]
    assert "Hindi" in system_content


def test_language_en_default_does_not_mention_hindi():
    mock_call = MagicMock(return_value=ProviderResult(content='{"intent": "greeting"}', provider_used="groq"))
    with patch("schemelogic.conversational.router.chat_completion_with_fallback", mock_call):
        classify_message("hi")  # language defaults to "en"
    system_content = mock_call.call_args.args[0][0]["content"]
    assert "Hindi" not in system_content


def test_language_param_never_changes_json_contract_parsing():
    """The language toggle must only affect wording/comprehension instructions -- never the
    intent-classification logic itself."""
    with _mock_response('{"intent": "search", "search_query": "test", "target_index": null}'):
        result = classify_message("test", language="hi")
    assert result.intent == "search"
    assert result.search_query == "test"
