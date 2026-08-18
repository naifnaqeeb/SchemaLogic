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


def build_source_text(record: dict) -> str:
    """Best available text for a silver (myScheme-scraped) record -- there's no raw source
    document for these the way gold schemes have one, so this concatenates whatever scraped
    fields exist."""
    parts = [record.get("scheme_name") or "", record.get("description") or "", record.get("eligibility_text") or ""]
    return "\n\n".join(p for p in parts if p.strip())


def get_or_extract_scheme(slug: str, record: dict, session_cache: dict[str, Scheme | None]) -> Scheme | None:
    """`session_cache` is caller-owned (st.session_state.scheme_cache) and checked FIRST, always
    -- a session-cached None means "already tried and failed this session, don't retry". Returns
    None on any failure (never raises) -- the caller must treat None as "fall back to the
    description-only display", exactly as it would for a scheme that was never AI-Checked at all.
    """
    if slug in session_cache:
        return session_cache[slug]

    disk_hit = _load_from_disk(slug)
    if disk_hit is not None:
        session_cache[slug] = disk_hit
        return disk_hit

    source_text = build_source_text(record)
    if not source_text.strip():
        session_cache[slug] = None
        return None

    try:
        result = extract_scheme(source_text)
    except Exception:  # noqa: BLE001 -- extract_scheme is documented to never raise, but this
        # call site is reached live, mid-chat, under real quota pressure; treating literally any
        # unexpected exception as a plain extraction failure (not a crashed chat) is the whole
        # point of this module.
        session_cache[slug] = None
        return None

    if isinstance(result, ExtractionFailure):
        session_cache[slug] = None
        return None

    session_cache[slug] = result
    _save_to_disk(slug, result)
    return result
