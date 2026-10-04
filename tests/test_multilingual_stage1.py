"""Multilingual stage 1 -- understanding (2026-10-05). The pipeline stays English internally: the router's
existing call also returns the language and an English version of a non-English message; search uses
the English version; the deterministic answer parser reads yes/no words and native digits; the session
follows language switches. English behaviour is unchanged. No network: the provider is faked."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from schemelogic.conversational import chat_engine, router
from schemelogic.conversational.language import devanagari_guess, normalize_digits, script_language, yes_no
from schemelogic.conversational.session import AnswerParseError, _parse_answer
from schemelogic.llm.provider import ProviderFailure, ProviderResult
from tests.test_chat_engine import TEST_SCHEME, _shared_index, deps, state  # noqa: F401 -- fixtures


@pytest.mark.parametrize("text,expected", [
    ("I am a farmer from Bihar", "en"),
    ("ram is my name", "en"),                          # one marker word is not enough
    ("mujhe kisan yojana chahiye", "hi"),              # romanised Hindi
    ("मैं किसान हूँ", "deva"),
    ("میں کسان ہوں", "ur"),
    ("நான் ஒரு விவசாயி", "ta"),
])
def test_script_language(text, expected):
    assert script_language(text) == expected


def test_devanagari_is_hindi_unless_it_reads_as_marathi():
    assert devanagari_guess("मैं किसान हूँ") == "hi"
    assert devanagari_guess("मी शेतकरी आहे") == "mr"


@pytest.mark.parametrize("native,ascii_", [("४५", "45"), ("٤٥", "45"), ("۴۵", "45"), ("௪௫", "45"), ("12500", "12500")])
def test_native_digits_normalise(native, ascii_):
    assert normalize_digits(native) == ascii_


@pytest.mark.parametrize("word,value", [
    ("हाँ", True), ("नहीं", False), ("होय", True), ("नाही", False), ("haan", True), ("Nahi", False),
    ("ہاں", True), ("نہیں", False), ("ஆம்", True), ("இல்லை", False), ("maybe", None), ("yes", None),
])
def test_yes_no_words(word, value):
    assert yes_no(word) is value


@pytest.mark.parametrize("raw,answer_type,value", [
    ("हाँ", "boolean", True), ("nahi", "boolean", False), ("இல்லை", "boolean", False),
    ("४५", "number", 45), ("٦٠", "number", 60), ("௭௦", "number", 70), ("२.५", "number", 2.5),
    ("yes", "boolean", True), ("no", "boolean", False), ("45", "number", 45),   # English unchanged
])
def test_the_deterministic_parser_reads_them(raw, answer_type, value):
    assert _parse_answer(raw, answer_type) == value


def test_unrecognised_answers_still_raise_so_the_llm_fallback_runs():
    with pytest.raises(AnswerParseError):
        _parse_answer("shayad", "boolean")


# --- the router: same call, English untouched ---------------------------------------------------------


def _capture(content: str):
    calls = []

    def fake(messages, **kwargs):
        calls.append({"messages": messages, **kwargs})
        return ProviderResult(content=content, provider_used="groq")
    return fake, calls


def test_an_english_message_gets_exactly_the_old_prompt_and_budget():
    fake, calls = _capture('{"intent": "search", "search_query": "farmer support"}')
    with patch.object(router, "chat_completion_with_fallback", side_effect=fake):
        result = router.classify_message("I'm a farmer looking for support")
    expected_system = router._system_prompt(False, False, None, [], False, None, "en")
    assert calls[0]["messages"][0]["content"] == expected_system
    assert calls[0]["max_tokens"] == 150
    assert (result.language, result.english_text) == ("en", None)


def test_a_hindi_message_gets_language_and_english_from_the_same_call():
    fake, calls = _capture(json.dumps({"intent": "search", "search_query": "pension for old farmers",
                                       "language": "hi", "english": "I am an old farmer, I need a pension"}))
    with patch.object(router, "chat_completion_with_fallback", side_effect=fake):
        result = router.classify_message("मैं बूढ़ा किसान हूँ, मुझे पेंशन चाहिए")
    assert len(calls) == 1
    assert router._MULTILINGUAL_SUFFIX in calls[0]["messages"][0]["content"] and calls[0]["max_tokens"] == 450
    assert (result.language, result.english_text, result.search_query) == (
        "hi", "I am an old farmer, I need a pension", "pension for old farmers")


def test_an_unknown_language_label_falls_back_to_the_script_guess():
    fake, _ = _capture(json.dumps({"intent": "greeting", "language": "xx", "english": "hello"}))
    with patch.object(router, "chat_completion_with_fallback", side_effect=fake):
        assert router.classify_message("मी शेतकरी आहे").language == "mr"


def test_provider_failure_still_classifies_and_reports_the_script_language():
    with patch.object(router, "chat_completion_with_fallback", return_value=ProviderFailure("x", "y")):
        result = router.classify_message("நான் ஒரு விவசாயி")
    assert result.language == "ta" and result.english_text is None and result.intent == "search"


# --- the chat: search in English, language follows switches --------------------------------------------


def test_a_non_english_search_uses_the_english_version(state, deps):  # noqa: F811
    hindi = router.RouterResult(intent="search", search_query=None, language="hi", english_text="old age pension")
    with patch.object(chat_engine.router, "classify_message", return_value=hindi), \
         patch.object(chat_engine, "discovery_search", return_value=[]) as search:
        chat_engine.handle_user_message(state, "बुढ़ापा पेंशन", deps)
    assert search.call_args.args[1] == "old age pension"
    assert state["language"] == "hi"


def test_the_session_follows_a_language_switch(state, deps):  # noqa: F811
    chat_engine.select_scheme(state, "TEST", "gold", deps)  # pending: age
    session = state["conversation_session"]
    for language, text in (("hi", "४०"), ("en", "yes")):
        result = router.RouterResult(intent="answer", language=language)
        with patch.object(chat_engine.router, "classify_message", return_value=result):
            chat_engine.handle_user_message(state, text, deps)
        assert state["language"] == language and session.language == language
    assert session.profile["self"]["age"] == 40  # the Devanagari digits were read deterministically


def test_the_llm_answer_fallback_gets_the_english_text(state, deps):  # noqa: F811
    chat_engine.select_scheme(state, "TEST", "gold", deps)
    result = router.RouterResult(intent="answer", language="hi", english_text="I am forty years old")
    with patch.object(chat_engine.router, "classify_message", return_value=result), \
         patch.object(chat_engine.answer_parser, "parse_answer_llm", return_value=ProviderFailure("x", "y")) as llm:
        chat_engine.handle_user_message(state, "मेरी उम्र चालीस साल है", deps)
    assert llm.call_args.args[0] == "I am forty years old"
