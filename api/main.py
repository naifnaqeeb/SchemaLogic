"""FastAPI wrapper around the existing conversational business logic -- thin pass-through only.
Every endpoint calls straight into chat_engine.py (unchanged), which enforces the project's
non-negotiable invariant itself (the LLM never states a verdict -- see chat_engine.py's own
docstring). This file adds no eligibility logic, no routing logic, no extraction logic; it only
does HTTP plumbing (request parsing, session lookup, response serialization) around calls that
already existed and were already tested before tonight.

Run: uvicorn api.main:app --reload --port 8000   (from the repo root, same PYTHONPATH=. convention
as the Streamlit app and the test suite)
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from schemelogic.conversational import chat_engine
from schemelogic.conversational.examples import EXAMPLES

from . import deps as api_deps
from . import sessions
from .schemes import router as schemes_router
from .serialize import build_chat_response

app = FastAPI(title="SchemeLogic API")

# Local demo only -- wide open CORS so the Next.js dev server (a different port) can call this
# without friction. Tighten this before anything resembling a real deployment.
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"],
)

app.include_router(schemes_router)


class ChatRequest(BaseModel):
    session_id: str
    message: str
    language: str = "en"


class QuickReplyRequest(BaseModel):
    session_id: str
    reply: str
    language: str = "en"


class SelectRequest(BaseModel):
    session_id: str
    scheme_id: str
    source_type: str
    language: str = "en"


class ExampleRequest(BaseModel):
    session_id: str
    label: str
    language: str = "en"


class ResetRequest(BaseModel):
    session_id: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/examples")
def list_examples() -> list[dict]:
    """The quick-start demo cards -- same EXAMPLES data app.py's hero used, just returned as JSON
    instead of rendered as Streamlit buttons. `profile` is deliberately NOT included here (the
    frontend never needs to see or round-trip it) -- POST /chat/example looks it up server-side by
    label, same separation of concerns as the Streamlit version had."""
    return [{"label": e.label, "description": e.description, "scheme_id": e.scheme_id} for e in EXAMPLES]


@app.post("/chat")
def chat(req: ChatRequest) -> dict:
    state = sessions.get_state(req.session_id)
    deps = api_deps.build_deps(language=req.language)
    chat_engine.handle_user_message(state, req.message, deps)
    return build_chat_response(req.session_id, state)


@app.post("/chat/quick_reply")
def quick_reply(req: QuickReplyRequest) -> dict:
    state = sessions.get_state(req.session_id)
    deps = api_deps.build_deps(language=req.language)
    chat_engine.submit_quick_reply(state, req.reply, deps)
    return build_chat_response(req.session_id, state)


@app.post("/chat/select")
def select(req: SelectRequest) -> dict:
    state = sessions.get_state(req.session_id)
    deps = api_deps.build_deps(language=req.language)
    chat_engine.select_scheme(state, req.scheme_id, req.source_type, deps)
    return build_chat_response(req.session_id, state)


@app.post("/chat/example")
def select_example(req: ExampleRequest) -> dict:
    example = next((e for e in EXAMPLES if e.label == req.label), None)
    if example is None:
        raise HTTPException(status_code=404, detail=f"unknown example label {req.label!r}")
    state = sessions.get_state(req.session_id)
    deps = api_deps.build_deps(language=req.language)
    chat_engine.select_scheme(state, example.scheme_id, "gold", deps, initial_profile=example.profile)
    return build_chat_response(req.session_id, state)


@app.post("/chat/reset")
def reset(req: ResetRequest) -> dict:
    state = sessions.reset_state(req.session_id)
    return build_chat_response(req.session_id, state)


@app.get("/chat/{session_id}")
def get_chat(session_id: str) -> dict:
    """Re-fetches the current transcript for a session -- e.g. on a page refresh."""
    state = sessions.get_state(session_id)
    return build_chat_response(session_id, state)
