"""Pure logic, no Streamlit runtime needed -- st.session_state works as a plain dict-like object
outside a real app context (confirmed elsewhere in this project already)."""

import streamlit as st

from schemelogic.conversational import i18n


def _reset():
    st.session_state.pop("language", None)


def test_defaults_to_english():
    _reset()
    assert i18n.current_language() == "en"


def test_toggle_switches_to_hindi_and_back():
    _reset()
    i18n.toggle_language()
    assert i18n.current_language() == "hi"
    i18n.toggle_language()
    assert i18n.current_language() == "en"


def test_t_returns_language_specific_string():
    _reset()
    assert i18n.t("start_over") == "Start over"
    i18n.toggle_language()
    assert i18n.t("start_over") == "फिर से शुरू करें"
    _reset()


def test_t_falls_back_to_key_for_unknown_key():
    _reset()
    assert i18n.t("this_key_does_not_exist") == "this_key_does_not_exist"


def test_every_string_has_both_languages():
    """No silent partial translation -- every UI-chrome key promises both en and hi."""
    for key, entry in i18n._STRINGS.items():
        assert "en" in entry, f"{key} missing en"
        assert "hi" in entry, f"{key} missing hi"
        assert entry["en"].strip()
        assert entry["hi"].strip()
