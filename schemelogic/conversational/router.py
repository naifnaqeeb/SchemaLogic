"""Per-turn message router (conversational redesign, Step 2). ONE combined LLM call classifying
a chat message into an intent, so the continuous-chat UI (app.py) knows what to do with whatever
the citizen just typed, instead of gating input behind separate full-screen phases.

The LLM here NEVER decides eligibility and never touches the profile/evaluator directly -- it only
classifies the shape of the message (greeting / search / answer-to-pending-question / reference to
an already-shown scheme). All four downstream handlers still go through the same deterministic
machinery as before (search -> discovery.indexer, answer -> session.apply_answer + the real
evaluator, scheme_lookup -> shared.route_to_scheme-style selection). This module is pure
classification, nothing else.

On ANY failure (both providers down, malformed JSON, an intent value we don't recognize), falls
back to a keyword/regex heuristic classifier -- never raises, never blocks the chat. Quality of the
heuristic is deliberately modest (it only has to keep the chat usable during an outage, not be a
good router); the LLM path is what actually needs to be good, and that's the piece this module
can't verify without a real call (see tests/test_router.py's docstring).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal

from schemelogic.llm.provider import ProviderFailure, chat_completion_with_fallback

Intent = Literal["greeting", "search", "answer", "scheme_lookup", "eligibility_request"]
_VALID_INTENTS = {"greeting", "search", "answer", "scheme_lookup", "eligibility_request"}


@dataclass
class RouterResult:
    intent: Intent
    search_query: str | None = None  # for "search": the text to run discovery search on
    target_index: int | None = None  # for "scheme_lookup": 1-based index into the shown shortlist
    provider_used: str | None = None  # None when the heuristic fallback fired, not the LLM


_GREETING_WORDS = {
    "hi", "hello", "hey", "yo", "hiya", "howdy",
    "thanks", "thank you", "thankyou", "ty",
    "bye", "goodbye", "see ya", "ok", "okay", "cool", "great", "nice",
}

_ORDINAL_WORDS = {
    "first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3,
    "fourth": 4, "4th": 4, "fifth": 5, "5th": 5, "sixth": 6, "6th": 6,
}

_LOOKUP_TRIGGER_PHRASES = (
    "tell me more", "more detail", "more about", "what about", "more info",
    "know more", "look at", "check", "select",
)

_INDEX_PATTERN = re.compile(r"#\s*(\d+)|\bnumber\s*(\d+)|\b(\d+)\b")

# Bug 2 fix: "just tell me the scheme here for scheduled tribe" -- referring to a shortlist item
# by a distinctive piece of its NAME, with no number/ordinal/trigger-phrase -- was falling through
# to a brand-new "search" instead of being recognized as a reference to the already-shown scheme.
# Neither the trigger-phrase list above nor the index/ordinal pattern catch a bare name reference,
# so this does direct token-overlap matching against the shown shortlist's names.
_WORD_PATTERN = re.compile(r"[a-z0-9]+")
_MATCH_STOPWORDS = {
    "the", "a", "an", "for", "of", "and", "or", "to", "in", "on", "with", "this", "that", "one",
    "scheme", "yojana", "just", "tell", "me", "here", "please", "can", "you", "show", "give",
    "about", "check", "select", "is", "are", "it", "what", "which", "there", "my", "i",
}


def _significant_tokens(text: str) -> set[str]:
    return {t for t in _WORD_PATTERN.findall(text.lower()) if t not in _MATCH_STOPWORDS and len(t) > 2}


def match_shortlist_name(message: str, shortlist_names: list[str]) -> int | None:
    """1-based index of the shortlist item this message most plausibly names, or None. Deliberately
    conservative: requires the message's OWN distinctive content words (after stripping filler and
    domain-generic words like "scheme"/"yojana") to be almost entirely accounted for by one item's
    name -- a loose one-common-word overlap isn't enough, so this doesn't hijack an unrelated new
    search that happens to share a word with an old shortlist item."""
    if not shortlist_names:
        return None
    msg_sig = _significant_tokens(message)
    if not msg_sig:
        return None
    required_overlap = min(2, len(msg_sig))
    best_idx, best_score = None, 0.0
    for i, name in enumerate(shortlist_names, start=1):
        overlap = msg_sig & _significant_tokens(name)
        if len(overlap) < required_overlap:
            continue
        score = len(overlap) / len(msg_sig)
        if score > best_score:
            best_score, best_idx = score, i
    return best_idx if best_score >= 0.6 else None

# Bug 1 fix: an explicit eligibility question about the scheme currently in view (e.g. "am I
# eligible for this scheme?", "do I qualify?", "can I get this?") was falling through to "search"
# or an accidental stale "scheme_lookup" match, silently reproducing the same description-only
# view with no extraction attempt and no explanation. These phrases get first priority (ahead of
# even "answer") whenever a current scheme is in context -- a citizen explicitly asking about
# eligibility should never be misread as answering an unrelated pending question.
_ELIGIBILITY_PHRASES = (
    "am i eligible", "am i qualified", "do i qualify", "can i get this", "can i apply",
    "is this for me", "check my eligibility", "check eligibility", "eligibility for this",
    "eligible for this",
)


def _heuristic_classify(
    message: str, *, has_pending_question: bool, has_shortlist: bool, has_current_scheme: bool = False,
    shortlist_names: list[str] | None = None,
) -> RouterResult:
    stripped = message.strip()
    lowered = stripped.lower().rstrip("!.,? ")
    shortlist_names = shortlist_names or []

    if lowered in _GREETING_WORDS or (len(lowered) <= 4 and lowered in {"hi", "hey", "yo", "sup"}):
        return RouterResult(intent="greeting")

    if has_current_scheme and any(phrase in lowered for phrase in _ELIGIBILITY_PHRASES):
        return RouterResult(intent="eligibility_request")

    if has_shortlist:
        mentions_lookup = any(phrase in lowered for phrase in _LOOKUP_TRIGGER_PHRASES)
        target_index = None
        m = _INDEX_PATTERN.search(lowered)
        if m:
            target_index = int(next(g for g in m.groups() if g is not None))
        else:
            for word, idx in _ORDINAL_WORDS.items():
                if re.search(rf"\b{re.escape(word)}\b", lowered):
                    target_index = idx
                    break
        if target_index is None:
            target_index = match_shortlist_name(stripped, shortlist_names)  # Bug 2 fix
        if mentions_lookup or target_index is not None:
            return RouterResult(intent="scheme_lookup", target_index=target_index)

    if has_pending_question:
        return RouterResult(intent="answer")

    return RouterResult(intent="search", search_query=stripped)


def _system_prompt(
    has_pending_question: bool, has_shortlist: bool, pending_question_text: str | None,
    shortlist_names: list[str], has_current_scheme: bool, current_scheme_name: str | None,
    language: str = "en",
) -> str:
    context_lines = []
    if has_pending_question and pending_question_text:
        context_lines.append(f'A question is currently pending and awaiting the citizen\'s answer: "{pending_question_text}"')
    if has_shortlist and shortlist_names:
        numbered = "\n".join(f"{i}. {name}" for i, name in enumerate(shortlist_names, start=1))
        context_lines.append(f"A shortlist of schemes was just shown:\n{numbered}")
    if has_current_scheme:
        context_lines.append(f"The scheme currently in view/being discussed is: {current_scheme_name or '(unnamed)'}")
    context = "\n\n".join(context_lines) if context_lines else "No pending question, shortlist, or current scheme right now."

    return (
        "You classify one message in an ongoing chat between a citizen and a government welfare "
        "scheme eligibility assistant. You never decide eligibility or state any scheme fact "
        "yourself -- you only classify what KIND of message this is, so the app knows which "
        "existing (non-LLM) logic to route it to.\n\n"
        f"Current context:\n{context}\n\n"
        "Classify the citizen's next message into exactly one intent:\n"
        '- "greeting": small talk, thanks, a greeting, or anything with no informational content '
        "relevant to a scheme search or the pending question.\n"
        '- "search": describes their situation or what kind of help they want, to search for '
        "schemes (this includes REFINING a previous search with more detail).\n"
        '- "answer": answers the currently pending question (only valid if one is pending).\n'
        '- "scheme_lookup": refers to a specific scheme from the shortlist above by number or '
        "description (\"tell me more about #2\", \"the second one\", \"check the third one\").\n"
        '- "eligibility_request": explicitly asks about eligibility/qualification for the '
        '"scheme currently in view" above ("am I eligible for this?", "do I qualify?", "can I '
        "apply?\") -- ONLY valid if a current scheme is in context above. Prefer this over "
        '"answer" whenever the message is clearly an eligibility question rather than a direct '
        "answer to the pending question's specific fact.\n\n"
        "Output ONLY a JSON object: "
        '{"intent": "greeting"|"search"|"answer"|"scheme_lookup"|"eligibility_request", '
        '"search_query": <string or null, only for "search">, '
        '"target_index": <integer or null, only for "scheme_lookup", 1-based>}'
    ) + (
        # The router's OWN output is a fixed-schema JSON classification, not citizen-facing prose
        # -- there's nothing here to "respond in Hindi" about. What DOES matter for a Hindi-typing
        # citizen is that the classifier correctly understands a Hindi message; this note is about
        # comprehension, not output language, and the JSON keys/enum values stay in English either way.
        " The citizen may write their message in Hindi -- classify it correctly either way. The "
        "JSON keys and intent/enum values themselves must stay exactly as specified above, in English."
        if language == "hi" else ""
    )


def classify_message(
    message: str,
    *,
    has_pending_question: bool = False,
    has_shortlist: bool = False,
    pending_question_text: str | None = None,
    shortlist_names: list[str] | None = None,
    has_current_scheme: bool = False,
    current_scheme_name: str | None = None,
    language: str = "en",
) -> RouterResult:
    shortlist_names = shortlist_names or []
    messages = [
        {
            "role": "system",
            "content": _system_prompt(
                has_pending_question, has_shortlist, pending_question_text, shortlist_names,
                has_current_scheme, current_scheme_name, language,
            ),
        },
        {"role": "user", "content": message},
    ]
    response = chat_completion_with_fallback(
        messages, response_format={"type": "json_object"}, temperature=0.0, max_tokens=150
    )
    if isinstance(response, ProviderFailure):
        return _heuristic_classify(
            message, has_pending_question=has_pending_question, has_shortlist=has_shortlist,
            has_current_scheme=has_current_scheme, shortlist_names=shortlist_names,
        )

    try:
        parsed = json.loads(response.content)
        intent = parsed.get("intent")
        if intent not in _VALID_INTENTS:
            raise ValueError(f"unrecognized intent {intent!r}")
    except (json.JSONDecodeError, ValueError, AttributeError):
        return _heuristic_classify(
            message, has_pending_question=has_pending_question, has_shortlist=has_shortlist,
            has_current_scheme=has_current_scheme, shortlist_names=shortlist_names,
        )

    target_index = parsed.get("target_index")
    target_index = int(target_index) if isinstance(target_index, (int, float)) else None
    search_query = parsed.get("search_query")
    search_query = search_query if isinstance(search_query, str) and search_query.strip() else None

    if intent == "search" and search_query is None:
        search_query = message.strip()  # LLM classified it as search but left the query out -- use the raw message

    return RouterResult(
        intent=intent,
        search_query=search_query if intent == "search" else None,
        target_index=target_index if intent == "scheme_lookup" else None,
        provider_used=response.provider_used,
    )
