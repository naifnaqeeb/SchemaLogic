"""SchemeLogic conversational eligibility chat — continuous-chat redesign.

Sits on top of the existing, unchanged pipeline: schema (schemelogic.schema.models), the
deterministic symbolic evaluator (schemelogic.evaluator.symbolic_engine), the field ontology's
citizen-facing text (schemelogic.schema.field_ontology), and the already-verified gold-scheme
data in data/gold/. Nothing in Phase 0-4 is modified or bypassed by this file.

This is a THIN Streamlit rendering layer. All state-machine logic (routing, free-text answer
parsing, scheme selection incl. the live AI-Checked extraction tier) lives in chat_engine.py,
which has zero Streamlit dependency and is unit-tested there. This file's job is: render the
persistent message transcript, keep the chat input always live, wire button clicks to
chat_engine's public entry points, and never let an LLM output become a verdict (see
chat_engine.py's own docstring for the non-negotiable invariant this whole layer preserves).

Run with: PYTHONPATH=. streamlit run schemelogic/conversational/app.py
"""

from __future__ import annotations

import streamlit as st

from schemelogic.annotation.rendering import trace_to_citizen_english
from schemelogic.conversational import chat_engine, i18n, shared, voice_input
from schemelogic.conversational.chat_engine import ChatDeps
from schemelogic.conversational.examples import EXAMPLES
from schemelogic.retrieval.indexer import DocumentChunk

st.set_page_config(page_title="SchemeLogic — Eligibility Chat", layout="centered")


def _has_live_pending_question() -> bool:
    session = st.session_state.get("conversation_session")
    return session is not None and session.pending_question is not None


# --- message rendering -------------------------------------------------------------------------


def _render_shortlist_card(msg_index: int, item: DocumentChunk, deps: ChatDeps) -> None:
    with st.container(border=True, key=f"card_{msg_index}_{item.doc_id}"):
        title = shared.esc(item.text.split(".")[0])
        st.markdown(
            f'<div class="sl-card-title">{title}</div>{shared.render_seal(item.source_type)}',
            unsafe_allow_html=True,
        )
        snippet = item.text.split(".", 1)[1].strip() if "." in item.text else ""
        snippet = shared.esc(snippet[:220]) + ("..." if len(snippet) > 220 else "")
        st.markdown(f'<div class="sl-card-snippet">{snippet}</div>', unsafe_allow_html=True)
        link = shared.official_link_for(item.scheme_id, item.source_type)
        if link:
            st.caption(f"[Official page]({link})")
        if st.button("Select", key=f"select_{msg_index}_{item.doc_id}"):
            with st.spinner("One moment..."):
                chat_engine.select_scheme(st.session_state, item.scheme_id, item.source_type, deps)
            st.rerun()


def _render_verdict_message(msg: dict) -> None:
    with st.chat_message("assistant"):
        st.write(msg["text"])
        shared.render_verdict_banner(msg["verdict_value"], msg["headline"])
        st.markdown(shared.render_seal(msg["tier"]), unsafe_allow_html=True)
        if msg["tier"] == "ai_checked":
            # Honest-labelling requirement (see i18n's own note on this key): the AI-Checked Q&A
            # and evaluator are deliberately identical to a Verified scheme's, so the seal badge
            # alone is too quiet a signal at the moment a citizen reads an actual verdict.
            st.warning(i18n.t("ai_checked_verdict_disclaimer"))
        with st.expander("Why? (plain-language explanation)"):
            st.markdown(trace_to_citizen_english(msg["trace"]))
        with st.expander("Technical detail (field names, raw trace)"):
            st.caption("For transparency/audit — not needed to understand the result above.")
            st.json(msg["trace"])
        st.divider()
        shared.render_next_steps_data(msg["next_steps"], is_gold_source_doc_fallback=(msg["tier"] == "gold"))


def _render_scheme_detail_message(msg: dict) -> None:
    record = msg["record"]
    with st.chat_message("assistant"):
        st.markdown(shared.render_seal("silver"), unsafe_allow_html=True)
        st.warning(
            "This scheme hasn't been verified by our system, and automatic rule extraction "
            "either wasn't attempted or didn't produce a usable result — here's what's listed on "
            "the government's myScheme portal. Please confirm the details directly with the "
            "official source before relying on them."
        )
        st.subheader(record.get("scheme_name") or msg["scheme_id"])
        if record.get("description"):
            st.markdown(record["description"])
        if record.get("eligibility_text"):
            st.markdown("**Eligibility (as listed):**")
            st.markdown(record["eligibility_text"])
        st.divider()
        shared.render_next_steps_data(msg["next_steps"])


def _render_message(msg_index: int, msg: dict, total: int, deps: ChatDeps) -> None:
    kind = msg["kind"]
    if kind == "text":
        with st.chat_message(msg["role"]):
            st.write(msg["text"])
    elif kind == "scheme_intro":
        with st.chat_message("assistant"):
            st.markdown(
                f'{shared.esc(msg["text"])} &nbsp; {shared.render_seal(msg["tier"])}',
                unsafe_allow_html=True,
            )
    elif kind == "shortlist":
        with st.chat_message("assistant"):
            st.write(msg["text"])
            for item in msg["items"]:
                _render_shortlist_card(msg_index, item, deps)
    elif kind == "question":
        with st.chat_message("assistant"):
            st.write(msg["text"])
        is_live = msg_index == total - 1 and _has_live_pending_question()
        quick_replies = msg.get("quick_replies")
        if is_live and quick_replies:
            cols = st.columns(len(quick_replies))
            for col, reply in zip(cols, quick_replies):
                with col:
                    if st.button(reply, key=f"qr_{msg_index}_{reply}", use_container_width=True):
                        with st.spinner("One moment..."):
                            chat_engine.submit_quick_reply(st.session_state, reply, deps)
                        st.rerun()
    elif kind == "verdict":
        _render_verdict_message(msg)
    elif kind == "scheme_detail":
        _render_scheme_detail_message(msg)


# --- hero (shown only before the first message) -------------------------------------------------


def _render_hero() -> None:
    """Matches the Figma home reference: greeting bubble, then a 2-column suggestion-card grid
    (same underlying quick-start examples/behavior as before, restyled -- see the build report for
    why the card COPY stayed as the existing demo-scenario labels rather than the reference's
    free-text search phrasing: these buttons start a specific pre-built demo profile directly,
    not a search, so relabeling them as quoted search queries would misrepresent what a click
    actually does)."""
    with st.chat_message("assistant"):
        st.write(i18n.t("greeting"))

    st.caption(i18n.t("try_one_of_these"))
    with st.container(key="sl_chip_row"):
        examples = list(EXAMPLES)
        for row_start in range(0, len(examples), 2):
            row = examples[row_start : row_start + 2]
            cols = st.columns(2)
            for col, example in zip(cols, row):
                with col:
                    if st.button(f'"{example.label}"', key=f"example_{example.label}"):
                        with st.spinner("..."):
                            deps = shared.build_deps()  # deferred -- only built once actually needed
                            chat_engine.select_scheme(
                                st.session_state, example.scheme_id, "gold", deps, initial_profile=example.profile
                            )
                        st.rerun()
    st.caption(i18n.t("browse_hint"))


# --- main ----------------------------------------------------------------------------------


def main() -> None:
    chat_engine.init_state(st.session_state)
    shared.inject_css()
    shared.render_nav_bar(active="chat")

    messages = st.session_state["messages"]
    if not messages:
        # Deliberately builds NO ChatDeps here -- shared.build_deps() cold-builds the ~2073-doc
        # embedding index on first call (seconds, not instant), and the pure empty-chat hero
        # (greeting, suggestion cards) needs none of that data just to render. Cost is deferred to
        # the first actual interaction (a card click or a typed message), exactly like the
        # pre-redesign home page.
        _render_hero()
    else:
        deps = shared.build_deps()
        for i, msg in enumerate(messages):
            _render_message(i, msg, len(messages), deps)
        st.divider()
        if st.button(i18n.t("start_over")):
            chat_engine.reset(st.session_state)
            st.rerun()

    user_text = st.chat_input(i18n.t("chat_input_placeholder"))
    voice_input.render_input_extras()
    st.markdown(f'<div class="sl-input-disclaimer">{shared.esc(i18n.t("disclaimer"))}</div>', unsafe_allow_html=True)
    if user_text:
        with st.spinner("..."):
            deps = shared.build_deps()
            chat_engine.handle_user_message(st.session_state, user_text, deps)
        st.rerun()


if __name__ == "__main__":
    main()
