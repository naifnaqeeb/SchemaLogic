"""JSON-safe serialization for chat_engine.py's message dicts. Those dicts can embed dataclass
instances (DocumentChunk on a "shortlist" message, NextSteps on "verdict"/"scheme_detail"
messages) and, inside DocumentChunk, a date field -- none of that is JSON-serializable as-is.
This is pure presentation-layer glue: it never inspects WHAT a message means, only recursively
flattens dataclasses/dates into plain dicts/strings so FastAPI's JSON encoder can handle it. No
business logic lives here, and chat_engine.py's own message-construction code is untouched.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from schemelogic.annotation.rendering import trace_to_citizen_english
from schemelogic.conversational.session import ConversationSession


def _serialize_value(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _serialize_value(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, (list, tuple)):
        return [_serialize_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    if hasattr(value, "isoformat"):  # date/datetime
        return value.isoformat()
    return value


def serialize_message(msg: dict) -> dict:
    """Streamlit's app.py rendered the plain-language "Why?" explanation on the fly, at render
    time, by calling trace_to_citizen_english(msg["trace"]) -- there was never a rendered-text
    field stored on the message itself, only the raw trace dict. The frontend has no business
    logic of its own to reimplement that walk, so this calls the SAME existing, untouched function
    once here and adds its output as a plain field on the serialized verdict message. This is the
    one place this module reaches beyond pure reformatting -- it's still zero new logic, just an
    existing render function's output exposed over the wire instead of called directly in a
    Streamlit script."""
    out = {k: _serialize_value(v) for k, v in msg.items()}
    if msg.get("kind") == "verdict" and isinstance(msg.get("trace"), dict):
        out["plain_explanation"] = trace_to_citizen_english(msg["trace"])
    return out


def serialize_pending_question(session: ConversationSession | None) -> dict | None:
    if session is None or session.pending_question is None:
        return None
    q = session.pending_question
    return {
        "field": q.field,
        "member": q.member,
        "answer_type": q.answer_type,
        "prompt": q.prompt,
        "quick_replies": list(q.quick_replies) if q.quick_replies else None,
        "allows_decline": q.allows_decline,
    }


def build_chat_response(session_id: str, state: dict) -> dict:
    session = state.get("conversation_session")
    return {
        "session_id": session_id,
        "messages": [serialize_message(m) for m in state.get("messages", [])],
        "pending_question": serialize_pending_question(session),
        "current_scheme_id": state.get("current_scheme_id"),
        "current_scheme_tier": state.get("current_scheme_tier"),
        "detected_language": state.get("language", "en"),  # multilingual stage 1: the citizen's language
    }
