"""Deterministic next-question selection (Phase 8, Step 2). No LLM call anywhere in this module —
pure logic over the existing symbolic evaluator's trace. This is the safety-critical part of the
conversational layer: it must never guess at a missing fact, only ever ask for it.

Walks the trace dict produced by schemelogic.evaluator.symbolic_engine.evaluate(), finds every
leaf predicate whose `result` is None (which, per that module's own logic, only ever happens when
the field is genuinely absent from the profile — never for any other reason) AND that sits under no
already-decided node, so its answer could still change the verdict, and returns the FIRST one it
finds as a canned question. "First" is deterministic: inclusion tree first
(depth-first, left-to-right), then exclusions in list order — same order the evaluator itself
walks the scheme, so which question comes first is a direct, explicable function of the scheme
definition, not an arbitrary choice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import re

from schemelogic.evaluator.symbolic_engine import EvaluationError, EvaluationResult, Verdict, evaluate
from schemelogic.schema.field_ontology import (
    citizen_question_for,
    display_label_for,
    family_scope_for,
    get_field,
    household_question_for,
    is_sensitive,
)
from schemelogic.schema.models import Quantifier
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
    allows_decline: bool = False  # a sensitive fact: "Prefer not to say" is a valid answer


DECLINE_REPLY = "Prefer not to say"


# Only UNDETERMINED nodes are descended into. Under Kleene logic a node already True or False stays so
# however the unknowns beneath it resolve, so nothing under it can change the verdict -- asking about it
# only lengthens the conversation (PMMVY, 2026-10-03: an SC/ST applicant was asked about nine other
# categories her answer had already made irrelevant). Conversely every unknown leaf on an all-undetermined
# path IS still offered, so a fact that could change the verdict is never skipped, and an undetermined
# verdict always has at least one question.


def _walk_inclusion(node: dict[str, Any], out: list[MissingField]) -> None:
    if node.get("result") is not None:
        return
    node_type = node.get("type")
    if node_type == "predicate":
        out.append(MissingField(field=node["field"], member="self", cat=node.get("cat"), expected_value=node.get("expected")))
        return
    if node_type in ("and", "or"):
        for child in node.get("children", []):
            _walk_inclusion(child, out)


def _walk_exclusions(exclusions_trace: list[dict[str, Any]], out: list[MissingField]) -> None:
    for excl in exclusions_trace:
        if excl.get("result") is not None:
            continue  # already fires, or can't -- including an exclusion its exception has waived
        excl_except = excl.get("except")  # present only for an applicant-scoped exception
        condition_open = excl_except is None or excl.get("condition_result") is None
        if condition_open:
            for member_entry in excl.get("members", []):
                if member_entry.get("result") is not None:
                    continue  # this member's part is decided
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
                    # Member-scoped exception: a fact about this member, so ask this member. (The row
                    # is undetermined, so its condition isn't False: the exception still matters.)
                    out.append(
                        MissingField(
                            field=except_pred["field"], member=member_entry["member"],
                            cat=None, expected_value=except_pred.get("expected"),
                        )
                    )
        # Applicant-scoped exception (models.ExceptScope): recorded ONCE, at exclusion level, read from
        # the applicant's record. Ask the applicant -- never "one of your family members", whose record
        # the evaluator doesn't read for it. (The exclusion is undetermined, so its condition isn't
        # False and the exception still matters.)
        if excl_except is not None and excl_except.get("result") is None:
            out.append(
                MissingField(
                    field=excl_except["field"], member=excl.get("except_member", "self"),
                    cat=None, expected_value=excl_except.get("expected"),
                )
            )


def find_missing_fields(result: EvaluationResult) -> list[MissingField]:
    """The missing facts under no already-decided node, in evaluation order (inclusion tree, then
    exclusions). Never leaves out a fact whose answer could change the verdict; when one fact feeds
    several rules it can include some that can't, which select_next_question filters out. NOT
    deduplicated by field name — the same field can legitimately be missing for two different
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


def family_wide_fields(scheme: Scheme) -> set[str]:
    """Fields this scheme checks for the whole family (a non-self exclusion quantifier) and nowhere
    for the applicant alone. Asked of the applicant, such a fact must be asked for the household: the
    answer is stored on the applicant's record, which is the only one the chat fills in unless the
    citizen described relatives, so an applicant-only question never reaches a relative's fact."""
    family = {e.field for e in scheme.exclusions if e.quantifier != Quantifier.SELF}
    own: set[str] = {e.field for e in scheme.exclusions if e.quantifier == Quantifier.SELF}

    def walk(node: Any) -> None:
        children = getattr(node, "and_", None) or getattr(node, "or_", None)
        if children is not None:
            for child in children:
                walk(child)
        else:
            own.add(node.field)

    walk(scheme.inclusion)
    return family - own


def household_question(field: str, scheme_id: str, answer_type: str) -> str:
    """The applicant's question for a family-wide fact: the field's own household phrasing for this
    scheme if it has one, else a plain generic one -- never an applicant-only question."""
    specific = household_question_for(field, scheme_id)
    if specific:
        return specific
    members, label = family_scope_for(scheme_id), display_label_for(field)
    if answer_type == "number":
        return f'What is the highest "{label}" of any one of {members}?'
    return f'Does any one of {members} meet this: "{label}"?'


def build_question(missing: MissingField, scheme: Scheme | None = None) -> Question:
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

    if missing.member == "self" and scheme is not None and missing.field in family_wide_fields(scheme):
        prompt = household_question(missing.field, scheme.scheme_id, answer_type)
    elif missing.member == "self":
        prompt = base_question
    else:
        prompt = f"This next one is about one of your family members — {_second_to_third_person(base_question)}"

    quick_replies: tuple[str, ...] | None = ("Yes", "No") if answer_type == "boolean" else None
    allows_decline = is_sensitive(missing.field)
    if allows_decline:
        quick_replies = (*(quick_replies or ()), DECLINE_REPLY)
    return Question(
        field=missing.field, member=missing.member, answer_type=answer_type,
        prompt=prompt, quick_replies=quick_replies, allows_decline=allows_decline,
    )


# --- exact relevance ------------------------------------------------------------------------------
# The walk above is exact while each field appears once. When one fact feeds several rules (AB-PMJAY's
# 70+ age waives all 14 exclusions; PM-KISAN's Group D carve-out sits on two), a fact can sit on an
# undetermined path and still be unable to change the verdict -- e.g. with a refrigerator owned and age
# unknown, AB-PMJAY's vehicle question can't matter: 70+ waives everything, under 70 the refrigerator
# excludes. So before asking, the selector PROVES the answer could change the verdict.


class _SearchBudgetExceeded(Exception):
    pass


_SEARCH_BUDGET = 20_000  # evaluate() calls per candidate; far above anything the gold schemes need


def _candidate_values(scheme: Scheme, field: str) -> list[Any]:
    """Values covering every region the scheme's predicates on `field` distinguish: each side of and on
    every numeric threshold (with midpoints, so thresholds closer than 1 apart are still separated),
    True/False for booleans, each listed value plus one that matches none for strings and lists."""
    values: list[Any] = []
    numbers: set[float] = set()

    def visit(pred: Any) -> None:
        if pred.field != field:
            return
        v = pred.value
        if isinstance(v, bool):
            values.extend((True, False))
        elif isinstance(v, (int, float)):
            numbers.add(v)
        elif isinstance(v, list):
            values.extend(v)
            values.append("__none_of_these__")
        else:
            values.extend((v, "__none_of_these__"))

    def walk(node: Any) -> None:
        children = getattr(node, "and_", None) or getattr(node, "or_", None)
        if children is not None:
            for child in children:
                walk(child)
        else:
            visit(node)

    walk(scheme.inclusion)
    for excl in scheme.exclusions:
        visit(excl)
        if excl.except_ is not None:
            visit(excl.except_)
    if numbers:
        ordered = sorted(numbers)
        values.extend(ordered)
        values.extend((ordered[0] - 1, ordered[-1] + 1))
        values.extend((a + b) / 2 for a, b in zip(ordered, ordered[1:]))
    return list(dict.fromkeys(values))  # stable de-duplication


def _with(profile: dict[str, Any], assignment: dict[tuple[str, str], Any]) -> dict[str, Any]:
    filled = {"self": dict(profile.get("self", {})),
              "family_members": [dict(m) for m in profile.get("family_members", [])]}
    if "family_members" not in profile:
        del filled["family_members"]  # keep "no key" distinct from "empty family"
    for (member, field), value in assignment.items():
        record = filled["self"] if member == "self" else filled["family_members"][int(member[len("family_member["):-1])]
        record[field] = value
    return filled


def _could_change_verdict(scheme: Scheme, profile: dict[str, Any], target: tuple[str, str]) -> bool:
    """Is there some way of answering the OTHER missing facts under which two answers to `target` give
    different verdicts? Depth-first over the other facts, pruned by the evaluator itself: a branch ends
    as soon as every answer to `target` gives the same definite verdict (nothing below can separate
    them -- definite verdicts are sound) or two answers give different definite verdicts (a witness)."""
    target_values = _candidate_values(scheme, target[1])
    calls = [0]

    def search(assignment: dict[tuple[str, str], Any]) -> bool:
        results = []
        for value in target_values:
            calls[0] += 1
            if calls[0] > _SEARCH_BUDGET:
                raise _SearchBudgetExceeded
            results.append(evaluate(scheme, _with(profile, {**assignment, target: value})))
        definite = {r.verdict for r in results if r.verdict != Verdict.UNDETERMINED}
        if len(definite) > 1:
            return True
        open_results = [r for r in results if r.verdict == Verdict.UNDETERMINED]
        if not open_results:
            return False
        branch = next(
            ((m.member, m.field) for r in open_results for m in find_missing_fields(r)
             if (m.member, m.field) != target and (m.member, m.field) not in assignment),
            None,
        )
        if branch is None:
            return True  # unreachable (an undetermined result always has an open fact); if not, ask
        return any(search({**assignment, branch: v}) for v in _candidate_values(scheme, branch[1]))

    try:
        return search({})
    except (_SearchBudgetExceeded, EvaluationError):
        return True  # can't prove it irrelevant: ask, as the structural walk alone would


def _screened_question(missing: MissingField, profile: dict[str, Any], scheme: Scheme) -> Question:
    """A sensitive fact with a gentler screening question is preceded by it: an answer of No settles
    the sensitive fact without asking it (ConversationSession.apply_answer)."""
    spec = get_field(missing.field)
    screen = spec.screened_by if spec is not None else None
    if screen is not None:
        record = profile.get("self", {}) if missing.member == "self" else (
            profile.get("family_members", [])[int(missing.member[len("family_member["):-1])])
        if screen not in record:
            return build_question(MissingField(field=screen, member=missing.member, cat=None, expected_value=True), scheme)
    return build_question(missing, scheme)


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
    candidates = list(dict.fromkeys(missing))  # the same fact can be offered by several rules
    relevant = [c for c in candidates if _could_change_verdict(scheme, profile, (c.member, c.field))]
    # A sensitive fact is asked only when it is the one still deciding: every other fact that could
    # change the verdict is asked first, and any of them may make it irrelevant (IGNOAPS: a BPL card,
    # a government job, five acres or a four-wheeler each settle the verdict without it).
    ordinary = [c for c in relevant if not is_sensitive(c.field)]
    if ordinary:
        return build_question(ordinary[0], scheme)
    if relevant:
        return _screened_question(relevant[0], profile, scheme)
    # No single answer can change the verdict, yet the evaluator can't decide: the fact feeding several
    # rules cancels out (KNOWN_ISSUES, "Kleene evaluation is incomplete..."). Asking the first fact
    # resolves that, and is the only way the conversation reaches the verdict every answer leads to.
    return build_question(candidates[0], scheme)
