"""Chat-turn orchestration for the continuous-chat redesign (Steps 1-3 of the redesign brief).

Deliberately has ZERO Streamlit import -- every function here operates on a plain MutableMapping
(`state`) and an explicit `ChatDeps` bundle, so the entire router-dispatch / free-text-answer /
scheme-selection / live-AI-Checked-extraction orchestration is unit-testable with a plain dict and
mocked dependencies, no Streamlit runtime needed. app.py is a thin Streamlit rendering layer on
top of this module; it owns st.session_state and passes it in as `state`.

NON-NEGOTIABLE INVARIANT, unchanged from the original design and enforced by construction
throughout this module: the LLM never states an eligibility verdict.
  - router.classify_message() only classifies what KIND of message this is.
  - answer_parser.parse_answer_llm() only normalizes a free-text answer into a typed value for the
    ALREADY-DETERMINED pending field -- it never decides whether that value makes the citizen
    eligible.
  - ai_checked.extract_with_reason() only ever produces a Scheme (a rule definition) or None plus
    the reason it failed -- never a verdict, and never a Scheme carrying no discriminating rule
    (see ai_checked.is_vacuous, which fails those honestly to the description-only display).
  - Every verdict in this module comes from ConversationSession.current_result(), which calls
    schemelogic.evaluator.symbolic_engine.evaluate() -- the same deterministic engine gold schemes
    have always used. phrase_verdict() (the one other LLM touchpoint) only words an
    ALREADY-COMPUTED verdict; it cannot change it (see phrasing.py's own system prompt).
If any future change to this module routes an LLM output directly into a verdict, that breaks this
invariant -- don't do it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, MutableMapping

from schemelogic.conversational import ai_checked, answer_parser, router
from schemelogic.conversational.answer_parser import AnswerParseResult
from schemelogic.conversational.intake import IntakeResult, parse_opening_message
from schemelogic.conversational.phrasing import phrase_verdict, verdict_headline
from schemelogic.conversational.session import AnswerParseError, ConversationSession, is_decline
from schemelogic.evaluator.symbolic_engine import EvaluationError
from schemelogic.discovery.indexer import (
    DescriptionMatch,
    NextSteps,
    next_steps_for_silver,
    resolve_next_steps,
    search as discovery_search,
)
from schemelogic.retrieval.indexer import DocumentChunk, LocalIndex
from schemelogic.schema.models import Scheme

State = MutableMapping[str, Any]


@dataclass
class ChatDeps:
    """Everything chat_engine needs from the outside world, injected explicitly so this module
    never touches Streamlit caching or the filesystem directly. app.py builds one of these per
    run from shared.py's cached resources (cheap -- no LLM call in building it)."""

    discovery_index: LocalIndex
    gold_match_report: dict[str, DescriptionMatch]
    silver_by_slug: dict[str, dict]
    raw_docs_dir: Path
    gold_dir: Path
    language: str = "en"  # "en" | "hi" -- threaded into router/phrase_verdict/answer_parser's LLM
    # calls only (their system prompts). Never affects the verdict itself, never translates scraped
    # scheme data, never changes chat_engine's own template strings (see i18n.py's own docstring
    # for the full scope breakdown of what does/doesn't get language-aware treatment tonight).


def load_gold_scheme(gold_dir: Path, scheme_id: str) -> Scheme:
    path = gold_dir / f"{scheme_id}.json"
    return Scheme.model_validate(json.loads(path.read_text(encoding="utf-8")))


# --- state -------------------------------------------------------------------------------------


def init_state(state: State) -> None:
    state.setdefault("messages", [])
    state.setdefault("conversation_session", None)
    state.setdefault("conversation_tier", None)
    state.setdefault("shortlist", None)
    state.setdefault("query_context", "")
    state.setdefault("language", "en")  # the citizen's language, detected per message (multilingual stage 1)
    state.setdefault("scheme_cache", {})  # survives reset() -- see reset()'s own docstring
    # "current scheme" is separate from conversation_session/conversation_tier above: it tracks
    # whatever scheme was last selected/displayed and PERSISTS past a resolved verdict or a
    # description-only fallback (conversation_session/tier get cleared once a verdict resolves).
    # This is what a later "am I eligible for THIS scheme?" anchors to -- Bug 1 fix (see
    # _handle_eligibility_request): without it, an explicit eligibility follow-up had nothing
    # reliable to refer to and either misrouted to a fresh search or accidentally re-hit a stale
    # shortlist index, silently reproducing the same description with no explanation.
    state.setdefault("current_scheme_id", None)
    state.setdefault("current_scheme_tier", None)  # "gold" | "ai_checked" | "silver"
    state.setdefault("current_scheme_name", None)


def reset(state: State) -> None:
    for key in (
        "messages", "conversation_session", "conversation_tier", "shortlist", "query_context",
        "current_scheme_id", "current_scheme_tier", "current_scheme_name",
    ):
        state.pop(key, None)
    # scheme_cache is NOT cleared -- it's a pure LLM-call-avoidance cache (Step 3/Step 4's
    # quota-discipline requirement), not conversation state. Clearing it on "start over" would
    # just force a needless re-extraction of a scheme the citizen already looked at this session.
    init_state(state)


def _say(state: State, text: str, kind: str = "text", **extra: Any) -> None:
    state["messages"].append({"role": "assistant", "kind": kind, "text": text, **extra})


def _hear(state: State, text: str) -> None:
    state["messages"].append({"role": "user", "kind": "text", "text": text})


def _shortlist_names(shortlist: list[DocumentChunk] | None) -> list[str]:
    if not shortlist:
        return []
    return [chunk.text.split(".")[0] for chunk in shortlist]


# --- entry point ---------------------------------------------------------------------------------


def handle_user_message(state: State, raw_message: str, deps: ChatDeps) -> None:
    """Called on every chat_input submit, regardless of what phase the conversation is
    conceptually in -- there IS no phase gate anymore. Appends the citizen's message to the
    transcript, classifies it, and appends whatever assistant response results. Never raises: the
    router itself never raises (heuristic fallback), and every branch below has a safe default."""
    init_state(state)
    raw_message = raw_message.strip()
    if not raw_message:
        return
    _hear(state, raw_message)

    session: ConversationSession | None = state.get("conversation_session")
    pending_question = session.pending_question if session else None
    shortlist = state.get("shortlist")
    current_scheme_id = state.get("current_scheme_id")

    if pending_question is not None and pending_question.allows_decline:
        # A sensitive question never reaches the router or the LLM answer parser: either could read a
        # decline ("I'd rather not say") as "no" or as a search, and turn it into a definite verdict.
        _handle_sensitive_answer(state, raw_message, deps)
        return

    result = router.classify_message(
        raw_message,
        has_pending_question=pending_question is not None,
        has_shortlist=bool(shortlist),
        pending_question_text=pending_question.prompt if pending_question else None,
        shortlist_names=_shortlist_names(shortlist),
        has_current_scheme=current_scheme_id is not None,
        current_scheme_name=state.get("current_scheme_name"),
        language=deps.language,
    )

    # Follows switches: every message re-detects. The pipeline stays English internally.
    state["language"] = result.language
    if session is not None:
        session.language = result.language

    if result.intent == "greeting":
        _handle_greeting(state)
    elif result.intent == "eligibility_request":
        # _handle_eligibility_request itself gives a clear "which scheme did you mean?" when
        # there's no current scheme to anchor to -- better than silently falling through to a
        # generic (and likely irrelevant) search for a message that isn't really search text.
        _handle_eligibility_request(state, deps)
    elif result.intent == "answer" and pending_question is not None:
        _handle_answer(state, raw_message, deps, english_text=result.english_text)
    elif result.intent == "scheme_lookup" and shortlist:
        _handle_scheme_lookup(state, result.target_index, deps)
    elif shortlist and (name_match := router.match_shortlist_name(raw_message, _shortlist_names(shortlist))):
        # Bug 2 fix: whatever the router decided (LLM misclassification, or the heuristic
        # fallback missing a bare name reference like "just tell me the scheme here for scheduled
        # tribe"), a message that clearly NAMES an already-shown scheme should never fall through
        # to a brand-new broad search -- checked here too, not just inside the heuristic, so an
        # LLM misclassification is caught the same way an outage-heuristic one would be.
        _handle_scheme_lookup(state, name_match, deps)
    else:
        # "search", or a misclassification with nothing to act on (e.g. "answer" but there's no
        # pending question) -- falling back to search is the safe default: worst case, a
        # confused classification still produces a useful shortlist instead of a dead end.
        # a non-English message searches with its English version (None for English: unchanged)
        _handle_search(state, result.search_query or result.english_text or raw_message, deps)


# --- greeting --------------------------------------------------------------------------------


def _handle_greeting(state: State) -> None:
    """No LLM call for the reply itself -- a friendly canned response costs nothing and keeps
    quota for the calls that actually need it (Step 4's discipline requirement)."""
    session: ConversationSession | None = state.get("conversation_session")
    if session is not None and session.pending_question is not None:
        _say(state, f"No rush! Whenever you're ready: {session.pending_question.prompt}")
        return
    _say(state, "Hey! Tell me a bit about your situation or what kind of help you're looking for, and I'll check real scheme rules for you.")


# --- eligibility request (Bug 1 fix: "am I eligible for this?" about the currently-shown scheme) --


def _handle_eligibility_request(state: State, deps: ChatDeps) -> None:
    scheme_id = state.get("current_scheme_id")
    tier = state.get("current_scheme_tier")
    if scheme_id is None:
        _say(state, "Which scheme did you mean? Search for one first, or pick one from Browse all schemes.")
        return

    if tier in ("gold", "ai_checked"):
        session: ConversationSession | None = state.get("conversation_session")
        if session is not None and session.pending_question is not None:
            _say(state, f"Let's finish checking {scheme_id} first — {session.pending_question.prompt}")
        else:
            _say(state, f"I already checked {scheme_id} for you above — scroll up to see the result, or search again to check a different scheme.")
        return

    # tier == "silver": extraction hasn't succeeded for this scheme (not yet tried, or already
    # tried and failed) -- _attempt_ai_checked_extraction is explicit about which, and respects
    # the session cache either way.
    record = deps.silver_by_slug.get(scheme_id)
    if record is None:
        _say(state, "Sorry, I couldn't find that scheme anymore.")
        return
    _attempt_ai_checked_extraction(state, scheme_id, record, deps)


# --- search / refine ---------------------------------------------------------------------------


def _note_if_abandoning_pending(state: State, new_scheme_id: str | None = None) -> None:
    session: ConversationSession | None = state.get("conversation_session")
    if session is None or session.pending_question is None:
        return
    if new_scheme_id is not None and session.scheme.scheme_id == new_scheme_id:
        return  # re-selecting the same in-progress scheme isn't an abandonment
    _say(state, f"(Switching away from {session.scheme.scheme_id} for now — search for it again anytime to restart that check.)")


def _handle_search(state: State, query: str, deps: ChatDeps) -> None:
    _note_if_abandoning_pending(state)
    state["query_context"] = f"{state.get('query_context', '')} {query}".strip() if state.get("shortlist") else query
    results = discovery_search(deps.discovery_index, state["query_context"], top_k=6)
    items = [chunk for chunk, _score in results]
    state["shortlist"] = items
    if not items:
        _say(state, "Nothing matched closely. Try describing it differently, or a different situation.")
        return
    _say(state, "Here's what I found", kind="shortlist", items=items)
    _say(state, "Want more detail on any of these, or should I check your eligibility for one? Just tell me, or click Select.")


# --- scheme lookup / selection -----------------------------------------------------------------


def _handle_scheme_lookup(state: State, target_index: int | None, deps: ChatDeps) -> None:
    shortlist: list[DocumentChunk] = state.get("shortlist") or []
    if target_index is None or not (1 <= target_index <= len(shortlist)):
        _say(state, 'Which one did you mean? Say the number (e.g. "#2") or click Select on a card above.')
        return
    chunk = shortlist[target_index - 1]
    select_scheme(state, chunk.scheme_id, chunk.source_type, deps)


def select_scheme(state: State, scheme_id: str, source_type: str, deps: ChatDeps, initial_profile: dict | None = None) -> None:
    """The ONE selection pathway -- called whether the citizen typed a reference to a shortlist
    item (router: scheme_lookup), clicked a Select button on a shortlist card, clicked Select on
    the browse-all-schemes page, or clicked a quick-start example chip. `source_type` is "gold" or
    anything else (silver/AI-Checked candidate). `initial_profile` is for the quick-start chips'
    pre-built demo profiles ONLY -- a structured dict applied directly, at zero LLM cost, taking
    priority over the query_context-based intake parse below (which is for free text, not a
    ready-made profile)."""
    init_state(state)
    _note_if_abandoning_pending(state, new_scheme_id=scheme_id)
    if source_type == "gold":
        scheme = load_gold_scheme(deps.gold_dir, scheme_id)
        state["current_scheme_id"] = scheme_id
        state["current_scheme_tier"] = "gold"
        state["current_scheme_name"] = scheme_id
        _start_question_loop(state, scheme_id, "gold", scheme, deps, initial_profile=initial_profile)
        return

    record = deps.silver_by_slug.get(scheme_id)
    if record is None:
        _say(state, "Sorry, I couldn't find that scheme anymore.")
        return

    state["current_scheme_id"] = scheme_id
    state["current_scheme_name"] = record.get("scheme_name", scheme_id)
    _attempt_ai_checked_extraction(state, scheme_id, record, deps, initial_profile=initial_profile)


def _attempt_ai_checked_extraction(
    state: State, scheme_id: str, record: dict, deps: ChatDeps, initial_profile: dict | None = None,
) -> None:
    """Shared by select_scheme (the automatic attempt on first selecting a silver scheme) and
    _handle_eligibility_request (an explicit follow-up like "am I eligible for this?" -- Bug 1
    fix). ALWAYS explicit about what happened -- never silently re-shows the same description-only
    view with no explanation of whether extraction was even tried. ALWAYS respects the session
    cache: a scheme already attempted this session (success or failure) is never re-submitted to
    the LLM, whether this call came from the automatic path or the explicit one."""
    cache = state["scheme_cache"]
    already_attempted = scheme_id in cache
    if not already_attempted:
        _say(state, "Checking the rules for this scheme now...")
    scheme, failure = ai_checked.extract_with_reason(scheme_id, record, cache)

    if scheme is not None:
        if not already_attempted:
            _say(
                state,
                f"I ran automatic rule extraction on **{record.get('scheme_name', scheme_id)}** and it "
                "validated, so I can check your eligibility the same way as a verified scheme — just "
                "know this is AI-Checked (rules extracted automatically), not human-verified.",
            )
        state["current_scheme_tier"] = "ai_checked"
        _start_question_loop(state, scheme_id, "ai_checked", scheme, deps, initial_profile=initial_profile)
        return

    state["current_scheme_tier"] = "silver"
    if failure is not None and failure.reason in ("rate_limited", "api_error"):
        # A transient/quota failure, NOT a scheme whose rules can't be extracted -- saying
        # otherwise would be a false statement about the scheme, and would discourage the citizen
        # from the retry that will very likely work (see ai_checked._RETRYABLE_FAILURES: these
        # aren't session-cached either, so selecting the scheme again really does retry).
        _say(
            state,
            f"I couldn't reach the rule-extraction service just now, so I haven't checked "
            f"**{record.get('scheme_name', scheme_id)}**'s rules yet — here's the description as "
            "listed meanwhile. Selecting it again in a moment will retry the check.",
        )
    elif already_attempted:
        _say(
            state,
            f"I already tried automatic rule extraction for **{record.get('scheme_name', scheme_id)}** "
            "earlier this session and it didn't produce reliable eligibility rules, so I won't retry — "
            "here's the description as listed.",
        )
    else:
        _say(
            state,
            "I wasn't able to reliably extract eligibility rules for this scheme automatically — "
            "here's the description as listed.",
        )
    _show_description_only(state, scheme_id, record, deps)


def _apply_initial_profile(session: ConversationSession, profile: dict) -> None:
    session.profile["self"].update(profile.get("self", {}))
    for i, member in enumerate(profile.get("family_members", [])):
        while len(session.profile["family_members"]) <= i:
            session.profile["family_members"].append({})
        session.profile["family_members"][i].update(member)


def _start_question_loop(
    state: State, scheme_id: str, tier: str, scheme: Scheme, deps: ChatDeps, initial_profile: dict | None = None,
) -> None:
    _say(state, f"Let's check your eligibility for {scheme_id}.", kind="scheme_intro", scheme_id=scheme_id, tier=tier)
    # Bug 3 fix: once a real Q&A session starts, a shortlist selection is no longer a live
    # possibility -- clearing it here stops a stale shortlist from several turns earlier from
    # confusing the router (heuristic AND live LLM, since it also drops out of the system prompt)
    # into reading a free-text answer as a shortlist reference (see router._heuristic_classify's
    # matching fix for the other half of this).
    state["shortlist"] = None
    session = ConversationSession(scheme=scheme)
    query_context = state.get("query_context", "")
    if initial_profile:
        _apply_initial_profile(session, initial_profile)
    elif query_context:
        intake_result = parse_opening_message(query_context)
        if isinstance(intake_result, IntakeResult):
            _apply_initial_profile(session, intake_result.profile)
            _say(
                state,
                f"Starting from what you already told me — I'll only ask about what's still "
                f"missing. (via {intake_result.provider_used})",
            )
    state["conversation_session"] = session
    state["conversation_tier"] = tier
    _advance(state, deps)


def _advance(state: State, deps: ChatDeps) -> None:
    """Runs the deterministic question loop one step: asks the next question (never an LLM call),
    or -- once nothing is missing -- resolves the verdict via the real evaluator and phrases it.
    phrase_verdict() is the only LLM call in this function, and it only WORDS an already-computed
    verdict (see this module's own top-level invariant note)."""
    session: ConversationSession = state["conversation_session"]
    tier = state["conversation_tier"]
    try:
        q = session.advance()
        result = session.current_result() if q is None else None
    except EvaluationError as exc:
        _evaluation_failed(state, session, exc)
        return
    if q is not None:
        _say(state, q.prompt, kind="question", quick_replies=q.quick_replies)
        return

    phrased = phrase_verdict(result, language=deps.language)
    next_steps = _resolve_next_steps(session.scheme.scheme_id, tier, deps)
    _say(
        state, phrased, kind="verdict",
        verdict_value=result.verdict.value, headline=verdict_headline(result), trace=result.trace,
        scheme_id=session.scheme.scheme_id, tier=tier, next_steps=next_steps,
    )
    state["conversation_session"] = None
    state["conversation_tier"] = None


def _evaluation_failed(state: State, session: ConversationSession, exc: EvaluationError) -> None:
    """The evaluator refuses to compare facts of the wrong type (e.g. a word where a number belongs,
    which the intake parser can produce) rather than guess -- see symbolic_engine.EvaluationError.
    That is not a verdict, so none is shown: the citizen is told plainly, pointed to the local
    office, and the session ends so the bad fact isn't re-evaluated on every later message."""
    _say(
        state,
        f"I couldn't work out a result for {session.scheme.scheme_id}: one of the answers I have isn't in "
        "a form the scheme's rules can use (for example, words where a number was needed), and I won't "
        "guess. This is not a decision about your eligibility. You can start the check again, or ask "
        "at your local office.",
        # kind stays "text" so both UIs render it; `error` marks it for anything that needs to tell
        error="evaluation_error", scheme_id=session.scheme.scheme_id, detail=str(exc),
    )
    state["conversation_session"] = None
    state["conversation_tier"] = None


def _resolve_next_steps(scheme_id: str, tier: str, deps: ChatDeps) -> NextSteps:
    if tier == "gold":
        match = deps.gold_match_report.get(scheme_id)
        if match is None:
            return NextSteps(benefits_text=None, application_process_text=None, official_link=None, source="none")
        return resolve_next_steps(scheme_id, match, deps.silver_by_slug, deps.raw_docs_dir)
    record = deps.silver_by_slug.get(scheme_id)
    if record is None:
        return NextSteps(benefits_text=None, application_process_text=None, official_link=None, source="none")
    return next_steps_for_silver(record)


def _show_description_only(state: State, scheme_id: str, record: dict, deps: ChatDeps) -> None:
    ns = next_steps_for_silver(record)
    _say(state, "", kind="scheme_detail", scheme_id=scheme_id, tier="silver", record=record, next_steps=ns)


# --- answering a pending question ---------------------------------------------------------------


def _to_canonical_answer_string(value: Any, answer_type: str) -> str:
    if answer_type == "boolean":
        return "yes" if value else "no"
    return str(value)


def submit_quick_reply(state: State, reply_text: str, deps: ChatDeps) -> None:
    """The quick-reply-button entry point (Yes/No clicks) -- bypasses the router entirely, since a
    button click is already unambiguous (unlike free chat_input text, there's no classification
    needed). Still goes through the exact same deterministic apply_answer + _advance path as any
    other answer."""
    session: ConversationSession | None = state.get("conversation_session")
    if session is None or session.pending_question is None:
        return
    _hear(state, reply_text)
    if session.pending_question.allows_decline and is_decline(reply_text):
        _declined(state, session)
        return
    try:
        session.apply_answer(reply_text)
    except AnswerParseError:
        _say(state, "Sorry, something went wrong reading that reply — please try again.")
        return
    _advance(state, deps)


def _handle_sensitive_answer(state: State, raw_message: str, deps: ChatDeps) -> None:
    """Yes, No or a decline -- read deterministically. Anything else is asked again, never guessed."""
    session: ConversationSession = state["conversation_session"]
    if is_decline(raw_message):
        _declined(state, session)
        return
    try:
        session.apply_answer(raw_message)
    except AnswerParseError:
        _say(state, "You can answer Yes, No, or “Prefer not to say” — whichever you are comfortable with.")
        return
    _advance(state, deps)


def _declined(state: State, session: ConversationSession) -> None:
    """The citizen chose not to disclose a sensitive fact. That fact stays unknown in the profile, so no
    verdict is computed or shown -- not eligible, not ineligible. They are pointed, gently, to the local
    office, which can consider the special provision in confidence. The check ends here."""
    session.decline_pending()
    scheme_id = session.scheme.scheme_id
    _say(
        state,
        f"That's completely fine — you don't need to tell me. You may qualify for {scheme_id} under a "
        "special provision. Please check with your local office (for example your Gram Panchayat, Block "
        "office or social welfare office); they can look at it with you in confidence.",
        # kind stays "text" so both UIs render it; `outcome` marks it -- never a verdict
        outcome="special_provision_check_locally", scheme_id=scheme_id,
    )
    state["conversation_session"] = None
    state["conversation_tier"] = None


def _handle_answer(state: State, raw_message: str, deps: ChatDeps, english_text: str | None = None) -> None:
    session: ConversationSession = state["conversation_session"]
    q = session.pending_question
    try:
        session.apply_answer(raw_message)
    except AnswerParseError:
        # the deterministic parse above saw the citizen's own words; the LLM fallback gets the
        # English version when there is one (None for English: unchanged)
        llm_result = answer_parser.parse_answer_llm(english_text or raw_message, q.prompt, q.answer_type, language=deps.language)
        if not isinstance(llm_result, AnswerParseResult):
            _say(state, "I couldn't quite understand that — could you rephrase? " + (
                "You can also use the Yes/No buttons above." if q.quick_replies else ""
            ))
            return
        normalized = _to_canonical_answer_string(llm_result.value, q.answer_type)
        try:
            session.apply_answer(normalized)
        except AnswerParseError:
            _say(state, "Sorry, I still couldn't quite parse that — could you try rephrasing?")
            return
    _advance(state, deps)
