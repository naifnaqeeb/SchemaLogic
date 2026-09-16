"""In-memory per-session chat_engine state store, keyed by a client-generated session_id.
Explicitly fine for this local demo (no database, no persistence across server restarts) -- see
the migration brief. The state dict itself is exactly what chat_engine.py already operates on
(the same MutableMapping contract it uses with Streamlit's st.session_state); this module owns
nothing about ITS shape, only where instances of it live between requests.
"""

from __future__ import annotations

from typing import Any

from schemelogic.conversational import chat_engine

_SESSIONS: dict[str, dict[str, Any]] = {}


def get_state(session_id: str) -> dict[str, Any]:
    state = _SESSIONS.setdefault(session_id, {})
    chat_engine.init_state(state)
    return state


def reset_state(session_id: str) -> dict[str, Any]:
    state = _SESSIONS.setdefault(session_id, {})
    chat_engine.reset(state)
    return state
