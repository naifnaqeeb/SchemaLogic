"""Minimal LLM extraction: scheme document text -> validated Scheme instance (Phase 1, Section 8).

Uses Groq's `json_schema` structured-output mode (Section 5.1) targeting the existing Scheme
Pydantic model directly — no parallel schema, no instructor/outlines wrapper. `strict: true`
native constrained decoding was tested first and rejected by Groq: it requires every property to
appear in each object's `required` array, and Pydantic's model_json_schema() doesn't do that for
optional/defaulted fields (e.g. `quantifier`, `except`, `valid_to`). `strict: false` was tested
end-to-end against the real recursive Scheme schema (nested and/or trees, free-form
`retired_predicate` dict) and reliably produced valid, Pydantic-conformant JSON, so that's what's
used here.

Extraction is split into two Groq calls, not one, because this account's TPM (tokens/minute) cap
is a flat 8000 across every model on the account (confirmed via `x-ratelimit-limit-tokens`
response headers on gpt-oss-20b/120b and qwen3.6-27b alike — an org-level ceiling, not a
model-specific or `max_tokens`-tunable one). The full Scheme schema plus the field-ontology system
prompt plus a dense source document routinely eats ~7600 of that 8000 in fixed overhead alone,
leaving too little for the completion on schemes with many exclusions (AB-PMJAY: 14 exclusions +
a 4-branch inclusion tree truncated mid-JSON under a single call). Splitting into (1) a
rules-only call — scheme_id/inclusion/exclusions/operational_requirements, the part that actually
needs the field ontology and most of the output budget — and (2) a small metadata-only call —
temporal_validity/extraction_metadata, negligible output, no ontology needed — keeps each call's
fixed overhead + completion comfortably under the shared 8000 cap. The two results are merged in
Python and validated together as one Scheme, so the "never a partial/guessed Scheme" guarantee
still holds: either both calls succeed and validate, or the whole thing is an ExtractionFailure.

`max_tokens` per call is computed dynamically (`_completion_budget()`) from the actual measured
size of the system prompt + JSON schema + document at call time, rather than a hardcoded
constant — a hardcoded value needed retuning every time `field_ontology.py` grew (it did,
repeatedly, as Phase 3 added schemes), and a stale constant tuned for an earlier, smaller ontology
silently 413'd on a later scheme (PM-UJJWALA-2.0, discovered 2026-08-18).

Separately: this account also has a TPD (tokens/PER DAY) cap of 200,000 — distinct from the TPM
cap above, discovered 2026-08-18 when it was hit mid-Phase-3-scaling (`rate_limit_exceeded`, `type:
tokens`, message names TPD specifically). Nothing in this module can work around a daily quota;
if extraction fails with a TPD-mentioning 429, the fix is waiting for the (rolling, not
fixed-clock) daily window to free up headroom, not a code change.

The LLM never outputs an eligibility verdict — this module only ever returns a Scheme (a rule
definition) or an explicit ExtractionFailure. Nothing here evaluates eligibility.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import date
from typing import Callable, Literal

from dotenv import load_dotenv
import openai
from groq import APIError, Groq
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from schemelogic.schema import field_ontology
from schemelogic.schema.models import (
    Exclusion,
    ExtractionMetadata,
    LogicNode,
    Scheme,
    TemporalValidity,
    UnitOfEligibility,
)

load_dotenv()

DEFAULT_MODEL = "openai/gpt-oss-120b"

# Both SDKs' API errors: Groq's own client by default, an OpenAI-SDK client for provider="openrouter".
_API_ERRORS = (APIError, openai.APIError)
UsageSink = Callable[[dict], None]


def _client_for(provider: str):
    """The default client for `provider` -- Groq's SDK for "groq" (unchanged), the shared
    OpenAI-compatible client from schemelogic.llm.provider for anything else."""
    if provider == "groq":
        return Groq(api_key=os.environ["GROQ_API_KEY"])
    from schemelogic.llm.provider import get_provider, make_client

    return make_client(get_provider(provider))


def _report_usage(sink: UsageSink | None, response, call: str) -> None:
    usage = getattr(response, "usage", None)
    if sink is None or usage is None:
        return
    sink({"call": call, "prompt_tokens": getattr(usage, "prompt_tokens", None),
          "completion_tokens": getattr(usage, "completion_tokens", None),
          "total_tokens": getattr(usage, "total_tokens", None)})

# TPM (tokens/minute) budget management — see module docstring. A hardcoded max_tokens constant
# needed retuning every time field_ontology.py grew (it did, repeatedly, as schemes were added —
# PM-UJJWALA-2.0's extraction 413'd against a max_tokens value that had worked fine for AB-PMJAY
# two schemes earlier, purely because the ontology prompt text had grown ~900 tokens in between).
# Computing max_tokens from the ACTUAL fixed-prompt size at call time is self-adjusting and
# doesn't need re-tuning as the ontology keeps growing toward 20-30 schemes.
_TPM_BUDGET = 8000
_TPM_SAFETY_MARGIN = 150  # headroom for tokenizer-estimate error and Groq's own message framing
_MIN_COMPLETION_TOKENS = 500
_MAX_COMPLETION_TOKENS = 4000
_CHARS_PER_TOKEN_ESTIMATE = 3.5  # conservative (real ratio measured 3.5-4.2 depending on prose vs JSON density)


def _estimate_tokens(text: str) -> int:
    """Dependency-free token-count estimate (no tiktoken dependency for one budget heuristic).
    Deliberately conservative (biased toward overestimating) since underestimating risks a 413."""
    return int(len(text) / _CHARS_PER_TOKEN_ESTIMATE)


def _completion_budget(system_prompt: str, document_text: str, json_schema: dict) -> int:
    fixed = _estimate_tokens(system_prompt) + _estimate_tokens(document_text) + _estimate_tokens(json.dumps(json_schema))
    return max(_MIN_COMPLETION_TOKENS, min(_MAX_COMPLETION_TOKENS, _TPM_BUDGET - _TPM_SAFETY_MARGIN - fixed))


class _SchemeCore(BaseModel):
    """Call-1 payload: the part of Scheme that needs the field ontology and most output budget."""

    model_config = ConfigDict(extra="forbid")

    scheme_id: str
    unit_of_eligibility: UnitOfEligibility
    inclusion: LogicNode
    exclusions: list[Exclusion] = Field(default_factory=list)
    operational_requirements: list[str] = Field(default_factory=list)


class _SchemeMeta(BaseModel):
    """Call-2 payload: small, no ontology needed."""

    model_config = ConfigDict(extra="forbid")

    temporal_validity: TemporalValidity
    extraction_metadata: ExtractionMetadata


def _without_except_scope(schema: dict) -> dict:
    """Remove `except_scope` (and its enum) from a JSON schema.

    Applicant-scoped exceptions are gold-only (decided 2026-10-03): one waives a whole exclusion for
    every family member when the applicant meets a condition, which is only right when the source
    text says so, and has to be justified against that text by a human. An extractor that could set
    it would silently turn "this member is exempt" into "everyone is exempt if the applicant is". So
    extraction -- including the live AI-Checked tier -- can only ever produce member scope."""
    schema = json.loads(json.dumps(schema))
    for definition in schema.get("$defs", {}).values():
        definition.get("properties", {}).pop("except_scope", None)
        if "required" in definition:
            definition["required"] = [r for r in definition["required"] if r != "except_scope"]
    schema.get("$defs", {}).pop("ExceptScope", None)
    return schema


def _force_member_scope(core: dict) -> dict:
    """Drop any `except_scope` the model emitted anyway: the schema doesn't offer it, but with
    `strict: false` a model can still produce off-schema keys. Member scope is the default, so this
    can only narrow an exception, never widen one."""
    for exclusion in core.get("exclusions") or []:
        if isinstance(exclusion, dict):
            exclusion.pop("except_scope", None)
    return core


_CORE_JSON_SCHEMA = _without_except_scope(_SchemeCore.model_json_schema())
_META_JSON_SCHEMA = _SchemeMeta.model_json_schema()

FailureReason = Literal[
    "empty_response",
    "malformed_json",
    "schema_validation_failed",
    "api_error",
    "rate_limited",
    "truncated_completion_budget",
]

# Groq reports a structured-output generation that ran out of completion budget mid-JSON as a 400
# `json_validate_failed` whose failed_generation reads "max completion tokens reached before
# generating a valid document" -- NOT as a truncated 200 response. Until this was split out, it
# landed in the catch-all `api_error` bucket, which hid the single most actionable failure cause
# behind the least actionable label (measured 2026-09-15: it was the ONLY hard failure in a
# 16-scheme AI-Checked sample, 1/16).
_TRUNCATION_MARKERS = ("json_validate_failed", "max completion tokens reached")
_RATE_LIMIT_MARKERS = ("rate_limit", "429", "tokens per", "requests per")

_RATE_LIMIT_RETRIES = 2
_RATE_LIMIT_DEFAULT_WAIT = 20.0  # ~a third of the TPM refill window, when Groq sends no hint
_RATE_LIMIT_MAX_WAIT = 45.0  # never block a live chat turn longer than this on one retry


def _retry_after_seconds(exc: APIError) -> float:
    """Groq's own `retry-after` header when present, clamped. Falls back to a fixed wait."""
    headers = getattr(getattr(exc, "response", None), "headers", None) or {}
    for key in ("retry-after", "x-ratelimit-reset-tokens"):
        raw = headers.get(key)
        if not raw:
            continue
        try:
            return min(max(float(str(raw).rstrip("s")), 1.0), _RATE_LIMIT_MAX_WAIT)
        except ValueError:
            continue
    return _RATE_LIMIT_DEFAULT_WAIT


def _api_error_reason(detail: str) -> FailureReason:
    d = detail.lower()
    if any(m in d for m in _TRUNCATION_MARKERS):
        return "truncated_completion_budget"
    if any(m in d for m in _RATE_LIMIT_MARKERS):
        return "rate_limited"
    return "api_error"


@dataclass
class ExtractionFailure:
    """Explicit, non-crashing failure — never a partial or guessed Scheme."""

    reason: FailureReason
    detail: str
    raw_response: str | None = None


def _core_system_prompt(ontology_compact: bool = False) -> str:
    """`ontology_compact=True` renders the canonical field vocabulary with each field's
    description truncated to its first sentence (the same rendering judge_repair.py already
    uses). Measured 2026-09-15: drops the core call's fixed prompt overhead ~450 tokens, which on
    a flat 8000 TPM account ceiling converts directly into completion headroom. Off by default so
    the validated gold extraction path is byte-identical to what produced the Phase 3 numbers."""
    return (
        "You extract structured, executable eligibility logic from Indian government welfare "
        "scheme documents into the given JSON schema. You never decide eligibility yourself — "
        "you only extract the rules; a separate deterministic engine evaluates them later.\n\n"
        "Conventions:\n"
        "- `scheme_id`: the scheme's canonical short name/acronym as used in the document "
        "(e.g. 'PM-KISAN'), not a made-up ID.\n"
        "- `inclusion`: a nested and/or tree of predicates that must hold for baseline eligibility.\n"
        "- `exclusions`: a flat list of predicates that disqualify. Each carries a `quantifier`: "
        "'self' (checked only on the applicant), 'some_family_member' (disqualifies if ANY family "
        "member matches, including the applicant), 'all_family_members' (only if ALL do), or "
        "'count_family_members' (compares a COUNT of matching family members against a threshold "
        "via `count_op`/`count` — only use this if the document actually describes a numeric cap, "
        "e.g. 'at most N per household').\n"
        "- `except`: a nested field/op/value predicate carving an exception out of an exclusion "
        "(e.g. government employees excluded EXCEPT Group D staff). It never carries a `cat`.\n"
        "- Every predicate (other than `except`) carries a `cat` category tag from the schema's "
        "controlled vocabulary — pick the closest fit, don't invent new categories.\n"
        "- `value` should be the natural JSON type implied by the field (boolean, number, or "
        "string) — don't stringify numbers or booleans.\n"
        "- Only extract what the document actually states. Do not invent thresholds, exceptions, "
        "or operational requirements that aren't in the text.\n"
        "- Prefer a single umbrella boolean field over expanding a named criteria list into many "
        "granular sub-predicates, unless the document's eligibility logic genuinely depends on "
        "distinguishing the sub-cases (e.g. use one `is_secc_deprived_household` boolean for "
        "'meets any of deprivation criteria D1-D7', not seven separate predicates) — this keeps "
        "output compact and matches how these documents are actually applied operationally.\n\n"
        "CANONICAL FIELD VOCABULARY — reuse these exact field names whenever a predicate matches "
        "one of these concepts, instead of inventing your own spelling. This is the single "
        "biggest thing that breaks comparability between extraction runs, so treat it as a hard "
        "preference, not a suggestion:\n"
        f"{field_ontology.format_for_prompt(compact=ontology_compact)}\n\n"
        "If (and only if) a predicate genuinely doesn't match any concept above, invent a clear "
        "snake_case field name yourself AND set that predicate's `ontology_proposed` to true. "
        "Never invent a new field name silently — either reuse a canonical one, or propose one "
        "explicitly via `ontology_proposed`. Don't set `ontology_proposed` on a predicate whose "
        "field name you reused from the list above."
    )


def _meta_system_prompt(as_of_date: date) -> str:
    return (
        "You extract two small pieces of metadata about an Indian government welfare scheme "
        "document into the given JSON schema: when the scheme's rules are valid, and your own "
        "confidence/sourcing notes about the extraction. You never decide eligibility yourself.\n\n"
        "- `temporal_validity.valid_from`: the date the rules described in the document took "
        "effect. `valid_to`: null unless the document states an end date. `supersedes`: null "
        "unless the document is itself an amendment that explicitly retires a specific prior "
        "rule (in which case describe what was retired and cite the amendment).\n"
        f"- `temporal_validity.extracted_at` should be {as_of_date.isoformat()} (today).\n"
        "- `extraction_metadata.confidence` is your own self-assessed confidence (0-1) that a "
        "full extraction of this document's eligibility rules would be complete and correct.\n"
        "- `extraction_metadata.source_clause` should point to the section/clause the eligibility "
        "rules are drawn from.\n"
        "- Set `extraction_metadata.flagged_for_review` to true if the document is ambiguous or "
        "you're unsure about any rule."
    )


def _call_groq(
    client: Groq,
    model: str,
    max_tokens: int,
    system_prompt: str,
    document_text: str,
    schema_name: str,
    json_schema: dict,
    reasoning_effort: str | None = None,
    rate_limit_retries: int = _RATE_LIMIT_RETRIES,
    sleep: Callable[[float], None] | None = None,
    usage_sink: UsageSink | None = None,
) -> dict | ExtractionFailure:
    """One structured-output call. Returns the parsed JSON dict, or an ExtractionFailure.

    Retries a rate-limited (429) call up to `rate_limit_retries` times, honouring Groq's own
    `retry-after` hint when present. This is the single highest-value reliability fix for the
    live AI-Checked path: one core extraction call costs a median ~7.5k tokens against this
    account's flat 8000 TPM ceiling, so an extraction fired while the router/intake/phrasing
    calls are still inside the same minute gets a 429 and -- before this retry existed -- fell
    straight through to the description-only display even though the extraction itself was
    perfectly capable of succeeding a few seconds later. A daily (TPD) exhaustion still can't be
    retried around, and isn't: the delays here are seconds, not minutes.
    """
    extra = {"reasoning_effort": reasoning_effort} if reasoning_effort else {}
    attempt = 0
    while True:
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=0.2,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": document_text},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema_name,
                        "schema": json_schema,
                        "strict": False,
                    },
                },
                **extra,
            )
            break
        except _API_ERRORS as exc:
            detail = str(exc)
            reason = _api_error_reason(detail)
            if reason != "rate_limited" or attempt >= rate_limit_retries:
                return ExtractionFailure(reason=reason, detail=detail)
            # Resolved at call time, not bound as a default argument, so a test (or a caller with
            # its own pacing) can substitute it -- a default of `time.sleep` would capture the
            # real function at import and make every retry test sleep for real.
            (sleep or time.sleep)(_retry_after_seconds(exc))
            attempt += 1

    _report_usage(usage_sink, response, schema_name)
    choice = response.choices[0]
    content = choice.message.content

    if not content or not content.strip():
        return ExtractionFailure(
            reason="empty_response",
            detail=f"model returned no content (finish_reason={choice.finish_reason!r})",
        )

    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        return ExtractionFailure(reason="malformed_json", detail=str(exc), raw_response=content)


def extract_scheme(
    document_text: str,
    model: str = DEFAULT_MODEL,
    as_of_date: date | None = None,
    client: Groq | None = None,
    reasoning_effort: str | None = None,
    ontology_compact: bool = False,
    provider: str = "groq",
    usage_sink: UsageSink | None = None,
) -> Scheme | ExtractionFailure:
    """Extract a schema-conformant Scheme from raw scheme document text via Groq.

    Runs two structured-output calls (rules, then metadata — see module docstring for why) and
    merges them. Returns a validated Scheme on success, or an explicit ExtractionFailure
    describing exactly what went wrong (API error, empty/refused response, malformed JSON, or a
    Pydantic ValidationError) — never a partial or guessed Scheme. Mirrors the evaluator's "no
    silent guessing on missing/bad data" principle, applied to the extraction layer.
    """
    as_of_date = as_of_date or date.today()
    client = client or _client_for(provider)

    core_system_prompt = _core_system_prompt(ontology_compact=ontology_compact)
    core = _call_groq(
        client,
        model,
        _completion_budget(core_system_prompt, document_text, _CORE_JSON_SCHEMA),
        core_system_prompt,
        document_text,
        "scheme_core_extraction",
        _CORE_JSON_SCHEMA,
        reasoning_effort=reasoning_effort,
        usage_sink=usage_sink,
    )

    if isinstance(core, ExtractionFailure) and core.reason == "truncated_completion_budget":
        # Recovery attempt, reached ONLY where the call above already failed -- so this can never
        # change the output of a currently-succeeding extraction (gold included). Both knobs buy
        # completion headroom: the compact ontology shrinks the fixed prompt (~450 tokens), and
        # reasoning_effort="low" stops gpt-oss's reasoning tokens from consuming the JSON budget
        # they're billed against. Measured 2026-09-15 on the one truncating scheme in the
        # AI-Checked sample (dmrnicmasii, a 7-criterion Tamil Nadu scheme): completion dropped
        # 1,107 -> 454 tokens and the extraction validated. Not enabled by default because it
        # can't be assumed quality-neutral for schemes that DO fit the budget.
        if not (ontology_compact and reasoning_effort == "low"):
            retry_prompt = _core_system_prompt(ontology_compact=True)
            core = _call_groq(
                client,
                model,
                _completion_budget(retry_prompt, document_text, _CORE_JSON_SCHEMA),
                retry_prompt,
                document_text,
                "scheme_core_extraction",
                _CORE_JSON_SCHEMA,
                reasoning_effort="low",
                usage_sink=usage_sink,
            )

    if isinstance(core, ExtractionFailure):
        return core

    meta_system_prompt = _meta_system_prompt(as_of_date)
    meta = _call_groq(
        client,
        model,
        _completion_budget(meta_system_prompt, document_text, _META_JSON_SCHEMA),
        meta_system_prompt,
        document_text,
        "scheme_meta_extraction",
        _META_JSON_SCHEMA,
        reasoning_effort=reasoning_effort,
        usage_sink=usage_sink,
    )
    if isinstance(meta, ExtractionFailure):
        return meta

    merged = {**_force_member_scope(core), **meta}
    try:
        return Scheme.model_validate(merged)
    except ValidationError as exc:
        return ExtractionFailure(
            reason="schema_validation_failed",
            detail=str(exc),
            raw_response=json.dumps({"core": core, "meta": meta}),
        )
