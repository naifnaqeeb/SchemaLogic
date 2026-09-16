"""Live, on-demand extraction for non-gold ("AI-Checked") schemes (conversational redesign,
Step 3). Reuses extraction/extractor.py's `extract_scheme()` completely unchanged -- that pipeline
is already validated and deliberately stays on its own direct Groq client (see its own module
docstring for why), not this project's Groq->OpenRouter fallback wrapper. That means THIS specific
call is the one LLM-dependent step in the whole redesign without a same-call cross-provider retry;
the graceful-degradation requirement is met a different way here -- extract_scheme() already never
raises and never returns a partial/guessed Scheme (ExtractionFailure on anything wrong), and this
module treats ANY failure, including an unexpected exception, as exactly that: a clean fallback to
the description-only display, never a crash.

The LLM never states an eligibility verdict here either -- extract_scheme() only ever produces a
Scheme (a rule definition). Whether a citizen is eligible under that Scheme is decided the exact
same way as gold: schemelogic.evaluator.symbolic_engine.evaluate(), nothing else.

Caching: session-level (caller-owned dict, e.g. st.session_state.scheme_cache) so re-selecting the
same scheme within a session never re-calls the LLM -- checked first, always. Disk-level (this
module owns it) so a successful extraction survives a server restart too, since a live extraction
call is exactly the kind of thing this project can't afford to redo needlessly under today's quota
pressure. Failures are cached in the session dict only (as None), never on disk -- a failure might
be transient (a rate limit that clears), and poisoning a permanent cache with "this scheme can
never be AI-Checked" on the strength of one bad call would be its own silent-failure mode.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from schemelogic.extraction.extractor import ExtractionFailure, extract_scheme
from schemelogic.schema.models import Scheme

DISK_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "ai_checked"


def _disk_cache_path(slug: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in slug)
    return DISK_CACHE_DIR / f"{safe}.json"


def _load_from_disk(slug: str) -> Scheme | None:
    path = _disk_cache_path(slug)
    if not path.exists():
        return None
    try:
        return Scheme.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValidationError, OSError):
        return None  # a corrupt cache entry degrades to "not cached", never a crash


def _save_to_disk(slug: str, scheme: Scheme) -> None:
    try:
        DISK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _disk_cache_path(slug).write_text(scheme.model_dump_json(indent=2), encoding="utf-8")
    except OSError:
        pass  # disk cache is an optimization, not a requirement -- never fail the request over it


# Fields that carry no eligibility signal on their own -- every scheme in the country is for
# Indian citizens/residents, so a rule set consisting only of these says nothing a citizen didn't
# already know. Kept deliberately short: this list exists to catch a collapsed extraction, not to
# second-guess genuine one-criterion schemes.
_GENERIC_FIELDS = frozenset({"is_indian_citizen", "is_indian_resident", "is_resident_of_state"})


def _substantive_predicate_count(scheme: Scheme) -> int:
    """How many predicates in this rule set actually discriminate between citizens."""

    def walk(node: object) -> list[str]:
        kids = getattr(node, "and_", None) or getattr(node, "or_", None)
        if kids:
            return [f for k in kids for f in walk(k)]
        return [getattr(node, "field", "")]

    inclusion = [f for f in walk(scheme.inclusion) if f not in _GENERIC_FIELDS]
    return len(inclusion) + len(scheme.exclusions)


def is_vacuous(scheme: Scheme) -> bool:
    """True when an extraction validated against the schema but carries no discriminating rule --
    e.g. a whole scheme document reduced to `is_indian_citizen == true`.

    Measured 2026-09-15 on a 16-scheme live sample: 1 of 15 successful extractions was vacuous,
    and it was the LARGEST source document in the sample (3,938 chars), self-reporting
    `confidence: 0.95` with `flagged_for_review: False` -- i.e. the model's own confidence was not
    merely unhelpful here but inverted, so the calibration gate's confidence signal cannot be the
    thing that catches this. Without this guard a citizen would be walked through a one-question
    Q&A and handed a confident-looking ELIGIBLE verdict that means nothing.

    Failing honestly to the description-only display is the correct outcome for these: the point
    of the AI-Checked tier is to run the real evaluator over real extracted rules, not to
    manufacture a Q&A for a scheme whose rules were never actually recovered."""
    return _substantive_predicate_count(scheme) == 0


def build_source_text(record: dict) -> str:
    """Best available text for a silver (myScheme-scraped) record -- there's no raw source
    document for these the way gold schemes have one, so this concatenates whatever scraped
    fields exist."""
    parts = [record.get("scheme_name") or "", record.get("description") or "", record.get("eligibility_text") or ""]
    return "\n\n".join(p for p in parts if p.strip())


# A failure whose cause is the transport/quota, not the document, will plausibly succeed on the
# next attempt -- so it must NOT be remembered as "this scheme can't be AI-Checked". The
# 2026-09-15 diagnosis found this to be the dominant real-world cause of the description-only
# fallback: one extraction costs a median ~7.5k tokens against a flat 8000 TPM account ceiling, so
# an extraction fired in the same minute as the router/intake/phrasing calls gets a 429 -- and the
# session cache then pinned that scheme to description-only for the rest of the session.
_RETRYABLE_FAILURES = frozenset({"rate_limited", "api_error"})


def extract_with_reason(
    slug: str, record: dict, session_cache: dict[str, Scheme | None]
) -> tuple[Scheme | None, ExtractionFailure | None]:
    """Same contract as get_or_extract_scheme, plus WHY it failed when it did, so the caller can
    tell a citizen "the service was busy, try again in a moment" instead of the misleading "these
    rules couldn't be extracted" -- and so a transient failure isn't cached as a permanent one."""
    if slug in session_cache:
        return session_cache[slug], None

    disk_hit = _load_from_disk(slug)
    if disk_hit is not None:
        session_cache[slug] = disk_hit
        return disk_hit, None

    source_text = build_source_text(record)
    if not source_text.strip():
        session_cache[slug] = None
        return None, ExtractionFailure(reason="empty_response", detail="no source text on this record")

    try:
        result = extract_scheme(source_text)
    except Exception as exc:  # noqa: BLE001 -- see module docstring: any unexpected exception
        # mid-chat is a plain extraction failure, never a crashed conversation.
        session_cache[slug] = None
        return None, ExtractionFailure(reason="api_error", detail=f"unexpected {type(exc).__name__}: {exc}")

    if isinstance(result, ExtractionFailure):
        if result.reason not in _RETRYABLE_FAILURES:
            session_cache[slug] = None  # content-shaped failure: same text would fail the same way
        return None, result

    if is_vacuous(result):
        session_cache[slug] = None
        return None, ExtractionFailure(
            reason="schema_validation_failed",
            detail="extraction validated but carried no discriminating eligibility rule",
        )

    session_cache[slug] = result
    _save_to_disk(slug, result)
    return result, None


def get_or_extract_scheme(slug: str, record: dict, session_cache: dict[str, Scheme | None]) -> Scheme | None:
    """`session_cache` is caller-owned (st.session_state.scheme_cache) and checked FIRST, always
    -- a session-cached None means "already tried and failed this session, don't retry". Returns
    None on any failure (never raises) -- the caller must treat None as "fall back to the
    description-only display", exactly as it would for a scheme that was never AI-Checked at all.
    """
    return extract_with_reason(slug, record, session_cache)[0]
