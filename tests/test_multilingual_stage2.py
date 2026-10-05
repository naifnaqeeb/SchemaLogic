"""Multilingual stage 2 -- replies in the citizen's language (2026-10-05). Fixed strings come from
reviewed-or-unreviewed translation files, with English as the fallback; English output is unchanged.
No network: translations are written to a temporary file, LLM calls are faked."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from schemelogic.annotation.rendering import trace_to_citizen_english
from schemelogic.conversational import chat_engine, description_translation, field_phrasing, messages, router
from schemelogic.conversational.phrasing import plain_template_answer, verdict_headline
from schemelogic.conversational.question_selector import MissingField, build_question
from schemelogic.conversational.session import ConversationSession, _parse_answer, is_decline
from schemelogic.evaluator.symbolic_engine import evaluate
from schemelogic.llm.provider import ProviderResult
from schemelogic.schema import field_ontology
from schemelogic.schema.models import Scheme
from tests.test_chat_engine import _shared_index, deps, state  # noqa: F401 -- fixtures

HI = {
    "chat.greeting": "नमस्ते! अपनी स्थिति बताइए।",
    "chat.lets_check": "आइए {scheme_id} के लिए आपकी पात्रता जाँचें।",
    "reply.yes": "हाँ", "reply.no": "नहीं", "reply.decline": "बताना नहीं चाहते",
    "question.family_prefix": "अगला सवाल आपके परिवार के एक सदस्य के बारे में है — {question}",
    "verdict.headline_eligible": "{emoji} आप {scheme_id} के लिए पात्र हैं",
    "verdict.answer_eligible": "आपकी बताई जानकारी के अनुसार, आप {scheme_id} के लिए पात्र हैं — कारण:",
    "trace.header": "इस नतीजे तक पहुँचने के लिए हमने यह जाँचा:",
    "trace.yes": "हाँ ✅",
    "family_scope.PM-KISAN": "आप, आपके पति या पत्नी, और आपके नाबालिग बच्चे",
    "field.is_citizen_test": None,
    "field.age": "आपकी उम्र कितने साल है?",
    "field_member.age": "उनकी उम्र कितने साल है?",
    "label.age": "उम्र",
    "field_household.monthly_pension_inr": "{members} में से किसी की भी सबसे ज़्यादा मासिक पेंशन कितनी है, रुपये में? (अगर किसी को नहीं मिलती तो 0 लिखें।)",
}


@pytest.fixture(autouse=True)
def _hindi_file(tmp_path, monkeypatch):
    catalogue = messages.catalogue()
    data = {k: {"source": catalogue[k], "text": v, "status": "unreviewed"} for k, v in HI.items() if k in catalogue and v}
    monkeypatch.setattr(messages, "I18N_DIR", tmp_path / "i18n")
    (tmp_path / "i18n").mkdir()
    (tmp_path / "i18n" / "hi.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    messages.reload_translations()
    yield
    messages.reload_translations()


def test_english_is_exactly_the_old_text():
    assert messages.text("chat.greeting", "en") == messages.MESSAGES["chat.greeting"]
    assert messages.text("chat.lets_check", "en", scheme_id="X") == "Let's check your eligibility for X."


def test_a_current_translation_is_used_and_anything_else_falls_back_to_english(tmp_path):
    assert messages.text("chat.lets_check", "hi", scheme_id="PM-KISAN") == "आइए PM-KISAN के लिए आपकी पात्रता जाँचें।"
    assert messages.text("chat.found", "hi") == "Here's what I found"          # not translated
    assert messages.text("chat.greeting", "ta") == messages.MESSAGES["chat.greeting"]  # no Tamil file
    data = json.loads((messages.I18N_DIR / "hi.json").read_text(encoding="utf-8"))
    data["chat.lets_check"]["source"] = "an older English text"               # stale
    data["chat.greeting"]["text"] = "नमस्ते {extra}"                            # placeholder mismatch
    (messages.I18N_DIR / "hi.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    messages.reload_translations()
    assert messages.text("chat.lets_check", "hi", scheme_id="X") == "Let's check your eligibility for X."
    assert messages.text("chat.greeting", "hi") == messages.MESSAGES["chat.greeting"]


def test_questions_family_prefix_and_buttons_in_hindi():
    q = build_question(MissingField(field="age", member="self", cat=None, expected_value=18), language="hi")
    assert q.prompt == "आपकी उम्र कितने साल है?"
    m = build_question(MissingField(field="age", member="family_member[0]", cat=None, expected_value=18), language="hi")
    assert m.prompt == "अगला सवाल आपके परिवार के एक सदस्य के बारे में है — उनकी उम्र कितने साल है?"
    b = build_question(MissingField(field="is_indian_citizen", member="self", cat=None, expected_value=True), language="hi")
    assert b.quick_replies == ("हाँ", "नहीं")
    assert b.prompt == field_ontology.citizen_question_for("is_indian_citizen")  # untranslated -> English


def test_household_question_translates_template_and_scope_or_stays_english():
    from tests.test_household_questions import GOLD
    scheme = GOLD["PM-KISAN"]
    q = build_question(MissingField(field="monthly_pension_inr", member="self", cat=None, expected_value=10000), scheme, "hi")
    assert q.prompt.startswith("आप, आपके पति या पत्नी, और आपके नाबालिग बच्चे में से")
    q = build_question(MissingField(field="monthly_income_inr", member="self", cat=None, expected_value=10000), GOLD["AB-PMJAY"], "hi")
    assert q.prompt.startswith("What is the highest monthly income")  # no Hindi template: whole question English


def test_translated_buttons_parse_back():
    assert _parse_answer("हाँ", "boolean") is True and _parse_answer("नहीं", "boolean") is False
    assert is_decline("बताना नहीं चाहते")


def test_verdict_and_explanation_in_hindi():
    scheme = Scheme.model_validate({
        "scheme_id": "T", "unit_of_eligibility": "individual",
        "inclusion": {"cat": "demographic", "field": "age", "op": ">=", "value": 18},
        "temporal_validity": {"extracted_at": "2026-01-01"}, "extraction_metadata": {"confidence": 1, "source_clause": "x"}})
    result = evaluate(scheme, {"self": {"age": 30}})
    assert verdict_headline(result, "hi").endswith("आप T के लिए पात्र हैं")
    assert plain_template_answer(result, "hi") == "आपकी बताई जानकारी के अनुसार, आप T के लिए पात्र हैं — कारण:"
    assert plain_template_answer(result) == "Based on what you've told me, you're eligible for T — here's why:"
    explanation = trace_to_citizen_english(result.trace, "hi")
    assert explanation.startswith("इस नतीजे तक पहुँचने के लिए हमने यह जाँचा:") and "- उम्र: हाँ ✅" in explanation


def test_the_chat_replies_in_the_detected_language_and_switches_back(state, deps):  # noqa: F811
    with patch.object(chat_engine.router, "classify_message", return_value=router.RouterResult(intent="greeting", language="hi")):
        chat_engine.handle_user_message(state, "नमस्ते", deps)
    assert state["messages"][-1]["text"] == "नमस्ते! अपनी स्थिति बताइए।"
    with patch.object(chat_engine.router, "classify_message", return_value=router.RouterResult(intent="greeting", language="en")):
        chat_engine.handle_user_message(state, "hello", deps)
    assert state["messages"][-1]["text"] == messages.MESSAGES["chat.greeting"]


def test_a_hindi_session_asks_and_answers_in_hindi(state, deps):  # noqa: F811
    state["language"] = "hi"
    chat_engine.select_scheme(state, "TEST", "gold", deps)
    session = state["conversation_session"]
    assert state["messages"][-2]["text"] == "आइए TEST के लिए आपकी पात्रता जाँचें।"
    assert session.pending_question.prompt == "आपकी उम्र कितने साल है?"


def test_scheme_description_is_translated_cached_and_labelled(state, deps):  # noqa: F811
    record = deps.silver_by_slug["silver-1"]
    reply = ProviderResult(content=json.dumps({"description": "एक अप्रमाणित योजना।", "eligibility_text": "कोई भी आवेदन कर सकता है।",
                                               "benefits_text": "नकद लाभ।", "application_process_text": "ऑनलाइन आवेदन करें।"},
                                              ensure_ascii=False), provider_used="groq")
    state["language"] = "hi"
    with patch.object(description_translation, "chat_completion_with_fallback", return_value=reply) as llm:
        chat_engine._show_description_only(state, "silver-1", record, deps)
        chat_engine._show_description_only(state, "silver-1", record, deps)  # second time: cached
    assert llm.call_count == 1
    detail = state["messages"][-1]
    assert detail["machine_translated"] and detail["record"]["description"] == "एक अप्रमाणित योजना।"
    assert detail["original_record"]["description"] == record["description"]
    assert state["messages"][-2]["text"] == messages.MESSAGES["chat.machine_translated"]  # label (English: not in file)


def test_a_failed_description_translation_shows_the_english(state, deps):  # noqa: F811
    state["language"] = "hi"
    chat_engine._show_description_only(state, "silver-1", deps.silver_by_slug["silver-1"], deps)  # conftest: LLM disabled
    detail = state["messages"][-1]
    assert "machine_translated" not in detail and detail["record"] == deps.silver_by_slug["silver-1"]


def test_ai_checked_phrasings_are_cached_per_language():
    assert field_phrasing._cache_key("x", False, "en") == "x" and field_phrasing._cache_key("x", True, "en") == "x@household"
    assert field_phrasing._cache_key("x", True, "ta") == "x@household@ta"
    assert field_phrasing._parse_key("x@household@ta") == ("x", True, "ta")
    assert field_phrasing._parse_key("x") == ("x", False, "en")


def test_translation_validation_rejects_broken_entries():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("tc", Path(__file__).resolve().parents[1] / "scripts" / "translate_catalogue.py")
    tc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tc)
    assert tc.valid("Are you BPL, {name}?", "क्या आप BPL हैं, {name}?")
    assert not tc.valid("Are you BPL, {name}?", "क्या आप गरीबी रेखा से नीचे हैं, {name}?")  # glossary term lost
    assert not tc.valid("Hello {name}", "नमस्ते")                                         # placeholder lost
    assert not tc.valid("**{x}** done", "{x} हो गया")                                      # bold lost
    assert not tc.valid("x", "  ")


def test_ui_chrome_strings_are_in_the_catalogue_and_exported_only_when_valid(tmp_path):
    import importlib.util
    from pathlib import Path

    english = messages.ui_strings_english()
    assert "nav_browse" in english and f"ui.nav_browse" in messages.catalogue()
    (messages.I18N_DIR / "ta.json").write_text(json.dumps({
        "ui.nav_browse": {"source": english["nav_browse"], "text": "அனைத்து திட்டங்களும்", "status": "unreviewed"},
        "ui.step_1": {"source": "an older English", "text": "பழையது", "status": "unreviewed"},
    }, ensure_ascii=False), encoding="utf-8")
    messages.reload_translations()
    spec = importlib.util.spec_from_file_location("ex", Path(__file__).resolve().parents[1] / "scripts" / "export_ui_strings.py")
    ex = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ex)
    built = ex.build()
    assert built["ta"] == {"nav_browse": "அனைத்து திட்டங்களும்"} and built["ur"] == {} and built["mr"] == {}
