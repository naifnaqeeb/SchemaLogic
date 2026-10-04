"""Baseline 1 -- flat attribute extraction, no compositional logic (final-push item 3).

The same model, the same source document and the same canonical field vocabulary as the main
extractor, in one structured call -- but the output is a FLAT list of conditions, each either
"required" or "disqualifying": no and/or nesting, no family quantifiers, no exceptions, no temporal
supersession. That isolates what the compositional schema adds.

To be scored with the same evaluator and metrics, the flat list is turned into a Scheme the only way a
flat list can be read: every required condition must hold (AND), and any disqualifying condition,
checked on the applicant, excludes. Alternatives ("any of these categories"), family-wide
exclusions and exceptions are exactly what this representation cannot say.
"""

from __future__ import annotations

from datetime import date

from schemelogic.extraction.extractor import (
    DEFAULT_MODEL,
    ExtractionFailure,
    UsageSink,
    _call_groq,
    _client_for,
    _completion_budget,
)
from schemelogic.schema import field_ontology
from schemelogic.schema.models import Scheme

_FLAT_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "scheme_id": {"type": "string"},
        "criteria": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "op": {"type": "string", "enum": ["==", "!=", "<", "<=", ">", ">=", "in", "not_in"]},
                    "value": {},
                    "cat": {"type": "string"},
                    "kind": {"type": "string", "enum": ["required", "disqualifying"]},
                },
                "required": ["field", "op", "value", "kind"],
            },
        },
    },
    "required": ["scheme_id", "criteria"],
}


def system_prompt() -> str:
    return (
        "You list the eligibility conditions of an Indian government welfare scheme document as a FLAT "
        "list of attribute conditions. You never decide eligibility yourself.\n\n"
        "For each condition the document states, give `field`, `op`, `value`, a `cat` category, and "
        "`kind`: 'required' (the applicant must meet it) or 'disqualifying' (meeting it makes the "
        "applicant ineligible). Use the natural JSON type for `value`. Only list what the document "
        "states; do not invent thresholds.\n\n"
        "CANONICAL FIELD VOCABULARY — reuse these exact field names whenever a condition matches one "
        "of these concepts:\n"
        f"{field_ontology.format_for_prompt()}\n\n"
        "If a condition matches none of them, invent a clear snake_case field name."
    )


def to_scheme(flat: dict, as_of: date | None = None) -> Scheme | ExtractionFailure:
    """AND of the required conditions; each disqualifying condition a self-checked exclusion."""
    as_of = as_of or date.today()
    criteria = flat.get("criteria") or []

    def predicate(c: dict) -> dict:
        return {"field": c["field"], "op": c["op"], "value": c["value"], "cat": c.get("cat") or "other"}

    required = [predicate(c) for c in criteria if c.get("kind") == "required"]
    disqualifying = [{**predicate(c), "quantifier": "self"} for c in criteria if c.get("kind") == "disqualifying"]
    if not required:
        return ExtractionFailure(reason="schema_validation_failed", detail="flat baseline: no required condition extracted")
    data = {
        "scheme_id": flat.get("scheme_id") or "UNKNOWN",
        "unit_of_eligibility": "individual",
        "inclusion": {"and": required},
        "exclusions": disqualifying,
        "temporal_validity": {"extracted_at": as_of.isoformat()},
        "extraction_metadata": {"confidence": 0.0, "source_clause": "baseline 1: flat attribute list (no confidence asked)",
                                "flagged_for_review": True},
    }
    try:
        return Scheme.model_validate(data)
    except Exception as exc:  # noqa: BLE001 -- an invalid flat output is a failure, like any extraction
        return ExtractionFailure(reason="schema_validation_failed", detail=str(exc)[:2000])


def extract_flat(document_text: str, model: str = DEFAULT_MODEL, client=None, provider: str = "groq",
                 usage_sink: UsageSink | None = None) -> tuple[Scheme | ExtractionFailure, dict | None]:
    """One call. Returns (the Scheme it converts to, or a failure; the raw flat list)."""
    client = client or _client_for(provider)
    prompt = system_prompt()
    raw = _call_groq(client, model, _completion_budget(prompt, document_text, _FLAT_JSON_SCHEMA), prompt,
                     document_text, "flat_eligibility_conditions", _FLAT_JSON_SCHEMA, usage_sink=usage_sink)
    if isinstance(raw, ExtractionFailure):
        return raw, None
    return to_scheme(raw), raw
