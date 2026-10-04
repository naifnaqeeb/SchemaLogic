"""LLM-as-judge + bounded, targeted repair (Phase 2, Section 8).

Scoped deliberately narrow: the 3-scheme structural-diff analysis (Fix rounds on PM-KISAN,
IGNOAPS, MH-LADKI-BAHIN) confirmed exactly two recurring extraction failure modes —

1. Preambular/implied facts: the extractor reliably captures explicit enumerated criteria but
   reliably misses eligibility-relevant facts that are only implied by introductory/definitional
   text (PM-KISAN's citizenship, IGNOAPS's destitution test, MH-LADKI-BAHIN's is_woman — 3/3).
2. Temporal supersession: amendment/repeal language describing a change to a prior criterion,
   never reflected in temporal_validity.supersedes (2/2 opportunities missed).

Two other patterns turned up (cross-scheme field-bleed, inconsistent except-clause extraction)
but were each seen only once — NOT confirmed recurring, so NOT repair targets here. Building a
repair mechanism for a one-off observation would be fitting noise; stays an open finding instead.

The judge is never allowed to hand back a whole re-extracted Scheme — only a single proposed
predicate or a single temporal_validity.supersedes patch, quoting the exact source text that
supports it. That's what "regenerate only the flagged predicates, not the whole extraction" means
here: the LLM output surface is scoped to the patch, not the document.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from dotenv import load_dotenv
from groq import APIError, Groq
from pydantic import BaseModel, Field, ValidationError

from schemelogic.extraction.extractor import _API_ERRORS, _client_for, _completion_budget, _report_usage
from schemelogic.schema import field_ontology
from schemelogic.schema.models import (
    AndNode,
    Exclusion,
    Operator,
    Predicate,
    PredicateCategory,
    Quantifier,
    Scheme,
    SimplePredicate,
    Supersedes,
)

load_dotenv()

DEFAULT_MODEL = "openai/gpt-oss-120b"
DEFAULT_MAX_PASSES = 2
DEFAULT_MIN_CONFIDENCE = 0.5


# --- Judge output schema (never a full Scheme — only a targeted patch) --------------------------


class ProposedExceptClause(BaseModel):
    field: str
    op: Operator
    value: Any


class ProposedPredicate(BaseModel):
    location: Literal["inclusion", "exclusion"]
    cat: PredicateCategory
    field: str
    op: Operator
    value: Any
    quantifier: Quantifier = Quantifier.SELF
    ontology_proposed: bool = False
    except_: ProposedExceptClause | None = Field(default=None, alias="except")


class ProposedSupersedes(BaseModel):
    retired_field: str
    retired_op: Operator
    retired_value: Any
    amendment_source_quote: str
    rule_version_label: str = "prior_version"
    new_valid_from: date | None = None


class JudgeFinding(BaseModel):
    category: Literal["preambular_implied_fact", "temporal_supersession"]
    description: str
    source_quote: str
    confidence: float = Field(ge=0.0, le=1.0)
    proposed_predicate: ProposedPredicate | None = None
    proposed_supersedes: ProposedSupersedes | None = None


class JudgeReport(BaseModel):
    findings: list[JudgeFinding] = Field(default_factory=list)


_JUDGE_JSON_SCHEMA = JudgeReport.model_json_schema()

JudgeFailureReason = Literal["empty_response", "malformed_json", "schema_validation_failed", "api_error"]


@dataclass
class JudgeFailure:
    reason: JudgeFailureReason
    detail: str
    raw_response: str | None = None


@dataclass
class RepairResult:
    scheme: Scheme
    judge_passes: list[dict[str, Any]] = field(default_factory=list)
    repair_log: list[dict[str, Any]] = field(default_factory=list)


def _judge_system_prompt() -> str:
    return (
        "You are auditing an LLM's draft extraction of eligibility rules against the ORIGINAL "
        "source document it was extracted from. You are NOT re-extracting from scratch — the "
        "draft mostly already correct. Your job is narrowly scoped to exactly two confirmed "
        "failure patterns, and nothing else:\n\n"
        "1. PREAMBULAR / IMPLIED FACTS: extractors reliably capture facts stated as explicit "
        "enumerated criteria (numbered lists, 'excluded if X'), but reliably MISS "
        "eligibility-relevant facts that are only implied by introductory, definitional, or "
        "objective/background text — text that appears BEFORE the enumerated exclusion/"
        "eligibility list, framed as background rather than an operative rule. Read the "
        "document's introductory and definitional sections specifically. Does any sentence "
        "there imply a status, category, or condition that IS eligibility-relevant but is NOT "
        "captured as its own standalone predicate anywhere in the draft? Example shape: a "
        "programme's stated target population ('targeting the destitute, defined as X') often "
        "implies a test that never appears as a numbered criterion later.\n\n"
        "2. AMENDMENT / SUPERSESSION LANGUAGE: does the document describe that a previously-"
        "stated rule was changed, repealed, extended, or amended — phrases like 'shall be read "
        "as', 'is hereby amended/repealed/extended', 'no longer applies', 'removed', a dated "
        "revision note — where that change is NOT reflected in the draft's "
        "temporal_validity.supersedes field? If supersedes is null and the document describes "
        "ANY such change to a criterion, that's a finding.\n\n"
        "Do NOT invent findings. Do NOT flag anything already correctly captured in the draft. "
        "Do NOT audit anything else — field-name style, missing operational_requirements, "
        "category-tag choices, except-clause completeness, unit_of_eligibility, etc. are OUT OF "
        "SCOPE. Only these two patterns.\n\n"
        "For each real finding, quote the EXACT source text supporting it, and propose the "
        "specific fix:\n"
        "- Preambular/implied fact: propose ONE predicate (cat, field, op, value, quantifier, "
        "and whether it belongs in inclusion or exclusion). Reuse a canonical field below if a "
        "genuine match exists; otherwise propose a new snake_case field name and set "
        "ontology_proposed=true.\n"
        "- Supersession: propose the retired predicate (field/op/value) and quote the amendment "
        "text as amendment_source_quote.\n\n"
        f"CANONICAL FIELD VOCABULARY:\n{field_ontology.format_for_prompt(compact=True)}\n\n"
        "If you find nothing in a category, return no finding for it — an empty findings list "
        "is a valid, correct answer; do not force a finding to have something to say. Set "
        "confidence (0-1) reflecting how directly the source text supports each finding."
    )


def run_judge(
    draft: Scheme,
    document_text: str,
    model: str = DEFAULT_MODEL,
    client: Groq | None = None,
    retrieved_context: str | None = None,
    provider: str = "groq",
    usage_sink=None,
) -> JudgeReport | JudgeFailure:
    """Single judge pass: re-reads the source document against the draft, scoped to the two
    confirmed failure patterns. Never returns a full Scheme — only findings + proposed patches.

    `retrieved_context` (Phase 4, Step 3): pre-formatted, temporally-filtered text from
    schemelogic.retrieval — external amendment/notification documents relevant to this scheme,
    already retrieved and date-filtered by the caller (this function does no retrieval itself, it
    just accepts context and cites it the same way it cites document_text). Optional and additive:
    omitting it reproduces the exact pre-Phase-4 judge behavior, so existing callers/tests are
    unaffected. `provider` / `usage_sink`: see extractor.extract_scheme."""
    client = client or (Groq(api_key=os.environ["GROQ_API_KEY"]) if provider == "groq" else _client_for(provider))
    draft_json = json.dumps(draft.model_dump(mode="json", by_alias=True), indent=2, ensure_ascii=False)
    system_prompt = _judge_system_prompt()
    user_content = (
        f"SOURCE DOCUMENT:\n{document_text}\n\n"
        f"DRAFT EXTRACTION (already produced from this document):\n{draft_json}"
    )
    if retrieved_context:
        user_content += (
            "\n\nRETRIEVED AMENDMENT CONTEXT (external documents, already filtered to those "
            "applicable as of this scheme's effective date — treat as trustworthy supplementary "
            "source material for temporal_supersession findings specifically; the SOURCE "
            "DOCUMENT above remains authoritative for everything else):\n" + retrieved_context
        )

    try:
        response = client.chat.completions.create(
            model=model,
            temperature=0.1,
            max_tokens=_completion_budget(system_prompt, user_content, _JUDGE_JSON_SCHEMA),
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": user_content,
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "judge_report", "schema": _JUDGE_JSON_SCHEMA, "strict": False},
            },
        )
    except _API_ERRORS as exc:
        return JudgeFailure(reason="api_error", detail=str(exc))

    _report_usage(usage_sink, response, "judge_report")
    content = response.choices[0].message.content
    if not content or not content.strip():
        return JudgeFailure(
            reason="empty_response",
            detail=f"judge returned no content (finish_reason={response.choices[0].finish_reason!r})",
        )

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        return JudgeFailure(reason="malformed_json", detail=str(exc), raw_response=content)

    try:
        return JudgeReport.model_validate(parsed)
    except ValidationError as exc:
        return JudgeFailure(reason="schema_validation_failed", detail=str(exc), raw_response=content)


# --- Applying findings: targeted patches only, never a full rebuild -----------------------------


def _add_to_inclusion(inclusion: Any, new_predicate: Predicate) -> AndNode:
    if isinstance(inclusion, AndNode):
        return AndNode(and_=[*inclusion.and_, new_predicate])
    return AndNode(and_=[inclusion, new_predicate])


def apply_judge_findings(
    scheme: Scheme, findings: list[JudgeFinding], min_confidence: float = DEFAULT_MIN_CONFIDENCE
) -> tuple[Scheme, list[dict[str, Any]]]:
    """Apply each finding above the confidence threshold as a targeted patch. Returns the patched
    scheme plus a log entry per finding (applied or skipped, and why) for auditability."""
    working = scheme
    applied_log: list[dict[str, Any]] = []

    for finding in findings:
        entry: dict[str, Any] = {
            "category": finding.category,
            "description": finding.description,
            "confidence": finding.confidence,
        }
        if finding.confidence < min_confidence:
            entry.update(applied=False, reason=f"confidence {finding.confidence} < threshold {min_confidence}")
            applied_log.append(entry)
            continue

        if finding.category == "preambular_implied_fact" and finding.proposed_predicate:
            p = finding.proposed_predicate
            if p.location == "inclusion":
                new_predicate = Predicate(cat=p.cat, field=p.field, op=p.op, value=p.value, ontology_proposed=p.ontology_proposed)
                working = working.model_copy(update={"inclusion": _add_to_inclusion(working.inclusion, new_predicate)})
            else:
                exc_kwargs: dict[str, Any] = dict(
                    cat=p.cat, field=p.field, op=p.op, value=p.value,
                    quantifier=p.quantifier, ontology_proposed=p.ontology_proposed,
                )
                if p.except_:
                    exc_kwargs["except_"] = SimplePredicate(field=p.except_.field, op=p.except_.op, value=p.except_.value)
                new_exclusion = Exclusion(**exc_kwargs)
                working = working.model_copy(update={"exclusions": [*working.exclusions, new_exclusion]})
            entry.update(applied=True, type="predicate", location=p.location, field=p.field)

        elif finding.category == "temporal_supersession" and finding.proposed_supersedes:
            ps = finding.proposed_supersedes
            retired_op = ps.retired_op.value if hasattr(ps.retired_op, "value") else ps.retired_op
            new_supersedes = Supersedes(
                rule_version=ps.rule_version_label,
                retired_predicate={"field": ps.retired_field, "op": retired_op, "value": ps.retired_value},
                amendment_source=ps.amendment_source_quote,
            )
            temporal_update: dict[str, Any] = {"supersedes": new_supersedes}
            if ps.new_valid_from is not None:
                temporal_update["valid_from"] = ps.new_valid_from
            new_temporal = working.temporal_validity.model_copy(update=temporal_update)
            working = working.model_copy(update={"temporal_validity": new_temporal})
            entry.update(applied=True, type="supersedes", field=ps.retired_field)

        else:
            entry.update(applied=False, reason="finding had no actionable proposal for its category")

        applied_log.append(entry)

    return working, applied_log


def judge_and_repair(
    document_text: str,
    draft: Scheme,
    model: str = DEFAULT_MODEL,
    max_passes: int = DEFAULT_MAX_PASSES,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    client: Groq | None = None,
    provider: str = "groq",
    usage_sink=None,
) -> RepairResult:
    """Bounded judge -> targeted-repair loop, capped at max_passes judge calls. Stops early once
    a pass finds nothing, or finds nothing that clears the confidence bar to actually apply."""
    client = client or (Groq(api_key=os.environ["GROQ_API_KEY"]) if provider == "groq" else _client_for(provider))
    current = draft
    judge_passes: list[dict[str, Any]] = []
    repair_log: list[dict[str, Any]] = []

    for pass_num in range(1, max_passes + 1):
        judge_result = run_judge(current, document_text, model=model, client=client, usage_sink=usage_sink)
        if isinstance(judge_result, JudgeFailure):
            judge_passes.append({"pass": pass_num, "failure": {"reason": judge_result.reason, "detail": judge_result.detail}})
            break

        judge_passes.append(
            {"pass": pass_num, "findings": [f.model_dump(mode="json", by_alias=True) for f in judge_result.findings]}
        )
        if not judge_result.findings:
            break

        current, applied_this_pass = apply_judge_findings(current, judge_result.findings, min_confidence=min_confidence)
        repair_log.append({"pass": pass_num, "applied": applied_this_pass})

        if not any(entry["applied"] for entry in applied_this_pass):
            break

    return RepairResult(scheme=current, judge_passes=judge_passes, repair_log=repair_log)
