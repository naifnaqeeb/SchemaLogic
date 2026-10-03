"""Deterministic next-question selection (Phase 8, Step 2). No LLM call anywhere in this module —
pure logic over the existing symbolic evaluator's trace. This is the safety-critical part of the
conversational layer: it must never guess at a missing fact, only ever ask for it.

Walks the trace dict produced by schemelogic.evaluator.symbolic_engine.evaluate(), finds every
leaf predicate whose `result` is None (which, per that module's own logic, only ever happens when
the field is genuinely absent from the profile — never for any other reason), and returns the
FIRST one it finds as a canned question. "First" is deterministic: inclusion tree first
(depth-first, left-to-right), then exclusions in list order — same order the evaluator itself
walks the scheme, so which question comes first is a direct, explicable function of the scheme
definition, not an arbitrary choice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import re

from schemelogic.evaluator.symbolic_engine import EvaluationResult, Verdict, evaluate
from schemelogic.schema.field_ontology import citizen_question_for
from schemelogic.schema.models import Scheme


@dataclass(frozen=True)
class MissingField:
    field: str
    member: str  # "self" or "family_member[i]" -- matches the trace's own member labels
    cat: str | None
    expected_value: Any  # used only to infer answer_type (bool vs number vs other)


@dataclass(frozen=True)
class Question:
    field: str
    member: str
    answer_type: str  # "boolean" | "number" | "text"
    prompt: str
    quick_replies: tuple[str, ...] | None  # ("Yes", "No") for boolean, else None


def _walk_inclusion(node: dict[str, Any], out: list[MissingField]) -> None:
    node_type = node.get("type")
    if node_type == "predicate":
        if node.get("result") is None:
            out.append(MissingField(field=node["field"], member="self", cat=node.get("cat"), expected_value=node.get("expected")))
        return
    if node_type in ("and", "or"):
        for child in node.get("children", []):
            _walk_inclusion(child, out)


def _walk_exclusions(exclusions_trace: list[dict[str, Any]], out: list[MissingField]) -> None:
    for excl in exclusions_trace:
        for member_entry in excl.get("members", []):
            pred = member_entry["predicate"]
            if pred.get("result") is None:
                out.append(
                    MissingField(
                        field=pred["field"], member=member_entry["member"],
                        cat=pred.get("cat"), expected_value=pred.get("expected"),
                    )
                )
            except_pred = member_entry.get("except")
            if except_pred is not None and except_pred.get("result") is None:
                # An applicant-scoped exception (models.ExceptScope) is read from the applicant's
                # record whichever member triggered the exclusion, so ask the applicant -- asking
                # "one of your family members" for a household-route fact would be wrong, and the
                # answer would land on a record the evaluator never reads.
                out.append(
                    MissingField(
                        field=except_pred["field"],
                        member=member_entry.get("except_member", member_entry["member"]),
                        cat=None, expected_value=except_pred.get("expected"),
                    )
                )


def find_missing_fields(result: EvaluationResult) -> list[MissingField]:
    """Every missing fact in the trace, in evaluation order (inclusion tree, then exclusions),
    NOT deduplicated by field name — the same field can legitimately be missing for two different
    members (e.g. self and family_member[0]), and those are two different questions."""
    out: list[MissingField] = []
    _walk_inclusion(result.trace["inclusion"], out)
    _walk_exclusions(result.trace["exclusions"], out)
    return out


def _answer_type_for(expected_value: Any) -> str:
    if isinstance(expected_value, bool):
        return "boolean"
    if isinstance(expected_value, (int, float)):
        return "number"
    return "text"


_YOU_OBJECT_PATTERN = re.compile(r"\b(to|for|about|of|with|from|by)\s+you\b", re.IGNORECASE)
_YOU_PATTERN = re.compile(r"\byou\b", re.IGNORECASE)
_YOUR_PATTERN = re.compile(r"\byour\b", re.IGNORECASE)


def _second_to_third_person(text: str) -> str:
    """"Are you a woman?" -> "Are they a woman?" for a question being asked about a family
    member other than the applicant. Subject-position "you"/"your" swap to "they"/"their" safely
    (English "you" and "they" share the same verb conjugation — are/do/did/have, never
    does/is — so this never produces a mismatch the way swapping in "he"/"she" would). Object-
    position "you" ("...for you", "...to you") needs "them", not "they" — handled as its own pass
    FIRST, before the generic swap, so it isn't a trap for whoever next writes an
    ontology citizen_question using that phrasing (two real ones already do)."""

    def _replace(pattern: re.Pattern, replacement: str, s: str) -> str:
        def repl(m: re.Match) -> str:
            word = m.group(0)
            return replacement.capitalize() if word[0].isupper() else replacement

        return pattern.sub(repl, s)

    text = _YOU_OBJECT_PATTERN.sub(lambda m: f"{m.group(1)} them", text)
    text = _replace(_YOUR_PATTERN, "their", text)
    text = _replace(_YOU_PATTERN, "they", text)
    return text


def build_question(missing: MissingField) -> Question:
    """Uses the ontology's own citizen_question directly (Part A, readability pass) — never the
    technical `description`. Fields the ontology doesn't know about yet (an ontology_proposed
    field from a live extraction run) get a plain, generic fallback phrasing instead of a
    fabricated question — see citizen_question_for's own docstring for why."""
    answer_type = _answer_type_for(missing.expected_value)
    base_question = citizen_question_for(missing.field)
    if base_question is None:
        label = missing.field.replace("_", " ")
        # Subject-position "you" throughout (not "...to you"/"...for you") so the you->they swap
        # below stays grammatical for family-member questions -- English "you"/"they" share verb
        # conjugation only in subject position, not as the object of a preposition.
        base_question = f'Do you meet this criterion: "{label}"?' if answer_type == "boolean" else f'What is your value for "{label}"?'

    if missing.member == "self":
        prompt = base_question
    else:
        prompt = f"This next one is about one of your family members — {_second_to_third_person(base_question)}"

    quick_replies: tuple[str, ...] | None = ("Yes", "No") if answer_type == "boolean" else None
    return Question(
        field=missing.field, member=missing.member, answer_type=answer_type,
        prompt=prompt, quick_replies=quick_replies,
    )


def select_next_question(scheme: Scheme, profile: dict[str, Any]) -> Question | None:
    """Returns None once the profile already has enough information for a definite verdict
    (ELIGIBLE or INELIGIBLE) — the caller should stop asking questions and move to the final
    answer. Never calls an LLM."""
    result = evaluate(scheme, profile)
    if result.verdict != Verdict.UNDETERMINED:
        return None
    missing = find_missing_fields(result)
    if not missing:
        # Should be unreachable (UNDETERMINED implies at least one None leaf) -- if it ever
        # happens, that's an evaluator/trace-shape bug, not a case to silently paper over here.
        raise RuntimeError(
            f"verdict is undetermined_missing_facts but no missing leaf predicate found in trace "
            f"for scheme {scheme.scheme_id!r} — evaluator/trace-walker mismatch"
        )
    return build_question(missing[0])
