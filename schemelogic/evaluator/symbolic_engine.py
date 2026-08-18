"""Deterministic symbolic evaluator (Phase 0, Section 8 of IMPLEMENTATION_PLAN.md).

Pure Python, no LLM involved. Given a `Scheme` + a citizen profile dict, returns a
three-valued verdict plus a full, auditable rule trace. This is the safety-critical
module the project's trust argument rests on — missing facts must always produce
`undetermined_missing_facts`, never a silent False default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from schemelogic.schema.models import (
    AndNode,
    CountOperator,
    Exclusion,
    OrNode,
    Predicate,
    Quantifier,
    Scheme,
    SimplePredicate,
)

Trit = Optional[bool]  # Kleene three-valued logic: True / False / None (unknown)


class Verdict(str, Enum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    UNDETERMINED = "undetermined_missing_facts"


class EvaluationError(Exception):
    """Raised for malformed inputs (e.g. comparing incompatible types) — never for missing facts."""


@dataclass
class EvaluationResult:
    verdict: Verdict
    trace: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"verdict": self.verdict.value, "trace": self.trace}


# --- Kleene three-valued logic helpers -------------------------------------------------


def _not3(a: Trit) -> Trit:
    return None if a is None else (not a)


def _and3(a: Trit, b: Trit) -> Trit:
    if a is False or b is False:
        return False
    if a is None or b is None:
        return None
    return True


def _or3(a: Trit, b: Trit) -> Trit:
    if a is True or b is True:
        return True
    if a is None or b is None:
        return None
    return False


def _combine_and3(values: list[Trit]) -> Trit:
    result: Trit = True
    for v in values:
        result = _and3(result, v)
    return result


def _combine_or3(values: list[Trit]) -> Trit:
    result: Trit = False
    for v in values:
        result = _or3(result, v)
    return result


# --- Leaf predicate comparison ------------------------------------------------------------


def _compare(op: str, actual: Any, expected: Any) -> bool:
    if op == "==":
        return actual == expected
    if op == "!=":
        return actual != expected
    if op == "in":
        return actual in expected
    if op == "not_in":
        return actual not in expected
    if op in ("<", "<=", ">", ">="):
        try:
            if op == "<":
                return actual < expected
            if op == "<=":
                return actual <= expected
            if op == ">":
                return actual > expected
            return actual >= expected
        except TypeError as exc:
            raise EvaluationError(
                f"cannot compare actual={actual!r} ({type(actual).__name__}) "
                f"with expected={expected!r} ({type(expected).__name__}) using op {op!r}"
            ) from exc
    raise EvaluationError(f"unknown operator {op!r}")


def _evaluate_predicate(
    pred: Predicate | SimplePredicate, member: dict[str, Any]
) -> tuple[Trit, Any]:
    """Returns (result, actual_value). result is None (undetermined) if the field is missing."""
    if pred.field not in member:
        return None, None
    actual = member[pred.field]
    op = pred.op.value if hasattr(pred.op, "value") else pred.op
    return _compare(op, actual, pred.value), actual


def _predicate_trace(pred: Any, result: Trit, actual: Any) -> dict[str, Any]:
    op = pred.op.value if hasattr(pred.op, "value") else pred.op
    cat_attr = getattr(pred, "cat", None)
    cat = cat_attr.value if hasattr(cat_attr, "value") else cat_attr
    return {
        "type": "predicate",
        "cat": cat,
        "field": pred.field,
        "op": op,
        "expected": pred.value,
        "actual": actual,
        "result": result,
    }


# --- Inclusion tree (AND/OR) evaluation ----------------------------------------------------


def _eval_node(node: Any, self_profile: dict[str, Any]) -> tuple[Trit, dict[str, Any]]:
    if isinstance(node, Predicate):
        result, actual = _evaluate_predicate(node, self_profile)
        return result, _predicate_trace(node, result, actual)

    if isinstance(node, AndNode):
        child_results: list[Trit] = []
        child_traces: list[dict[str, Any]] = []
        for child in node.and_:
            r, t = _eval_node(child, self_profile)
            child_results.append(r)
            child_traces.append(t)
        combined = _combine_and3(child_results)
        return combined, {"type": "and", "result": combined, "children": child_traces}

    if isinstance(node, OrNode):
        child_results = []
        child_traces = []
        for child in node.or_:
            r, t = _eval_node(child, self_profile)
            child_results.append(r)
            child_traces.append(t)
        combined = _combine_or3(child_results)
        return combined, {"type": "or", "result": combined, "children": child_traces}

    raise EvaluationError(f"unrecognized logic node type: {type(node)!r}")


# --- Exclusions (quantifiers + except) -----------------------------------------------------


def _members_for_quantifier(
    profile: dict[str, Any], quantifier: Quantifier
) -> list[tuple[str, dict[str, Any]]]:
    self_member = profile.get("self", {})
    if quantifier == Quantifier.SELF:
        return [("self", self_member)]

    family_members = profile.get("family_members", [])
    members = [("self", self_member)]
    members += [(f"family_member[{i}]", m) for i, m in enumerate(family_members)]
    return members


def _evaluate_count_constraint(
    member_results: list[Trit], count_op: CountOperator, count: int
) -> tuple[Trit, dict[str, Any]]:
    """Three-valued count-vs-threshold comparison.

    Each unresolved (None) member could independently resolve True or False, so the achievable
    count spans [true_count, true_count + none_count]. The constraint is only definite if it
    holds (or fails) across that *entire* range — otherwise a still-missing fact could flip the
    outcome, so it must be undetermined, same as everywhere else in this engine.
    """
    true_count = sum(1 for r in member_results if r is True)
    false_count = sum(1 for r in member_results if r is False)
    none_count = sum(1 for r in member_results if r is None)
    min_possible = true_count
    max_possible = true_count + none_count

    op = count_op.value if hasattr(count_op, "value") else count_op

    if op == "<=":
        result = True if max_possible <= count else (False if min_possible > count else None)
    elif op == "<":
        result = True if max_possible < count else (False if min_possible >= count else None)
    elif op == ">=":
        result = True if min_possible >= count else (False if max_possible < count else None)
    elif op == ">":
        result = True if min_possible > count else (False if max_possible <= count else None)
    elif op == "==":
        if min_possible == max_possible == count:
            result = True
        elif count < min_possible or count > max_possible:
            result = False
        else:
            result = None
    else:
        raise EvaluationError(f"unknown count operator {op!r}")

    trace = {
        "true_count": true_count,
        "false_count": false_count,
        "missing_count": none_count,
        "achievable_range": [min_possible, max_possible],
        "count_op": op,
        "count": count,
        "result": result,
    }
    return result, trace


def _eval_exclusion(
    exclusion: Exclusion, profile: dict[str, Any]
) -> tuple[Trit, dict[str, Any]]:
    members = _members_for_quantifier(profile, exclusion.quantifier)

    member_traces: list[dict[str, Any]] = []
    member_results: list[Trit] = []

    for label, member_dict in members:
        pred_result, pred_actual = _evaluate_predicate(exclusion, member_dict)

        if exclusion.except_ is not None:
            except_result, except_actual = _evaluate_predicate(exclusion.except_, member_dict)
        else:
            except_result, except_actual = False, None

        disqualifies = _and3(pred_result, _not3(except_result))
        member_results.append(disqualifies)

        member_trace: dict[str, Any] = {
            "member": label,
            "predicate": _predicate_trace(exclusion, pred_result, pred_actual),
            "result": disqualifies,
        }
        if exclusion.except_ is not None:
            member_trace["except"] = _predicate_trace(
                exclusion.except_, except_result, except_actual
            )
        member_traces.append(member_trace)

    count_trace: dict[str, Any] | None = None
    if exclusion.quantifier == Quantifier.ALL_FAMILY_MEMBERS:
        combined = _combine_and3(member_results)
    elif exclusion.quantifier == Quantifier.COUNT_FAMILY_MEMBERS:
        combined, count_trace = _evaluate_count_constraint(
            member_results, exclusion.count_op, exclusion.count
        )
    else:
        combined = _combine_or3(member_results)

    cat = exclusion.cat.value if hasattr(exclusion.cat, "value") else exclusion.cat
    trace = {
        "cat": cat,
        "field": exclusion.field,
        "quantifier": exclusion.quantifier.value,
        "has_except": exclusion.except_ is not None,
        "result": combined,
        "members": member_traces,
    }
    if count_trace is not None:
        trace["count_constraint"] = count_trace
    return combined, trace


# --- Top-level verdict combination ---------------------------------------------------------


def _final_verdict(inclusion_result: Trit, excluded: Trit) -> Verdict:
    if excluded is True:
        return Verdict.INELIGIBLE
    if inclusion_result is False:
        return Verdict.INELIGIBLE
    if inclusion_result is True and excluded is False:
        return Verdict.ELIGIBLE
    return Verdict.UNDETERMINED


def evaluate(scheme: Scheme, profile: dict[str, Any]) -> EvaluationResult:
    """Evaluate `scheme` against `profile`.

    profile shape: {"self": {field: value, ...}, "family_members": [{field: value, ...}, ...]}
    "self" is included when checking `some_family_member` / `all_family_members` quantifiers,
    since the applicant is themselves a family member.
    """
    inclusion_result, inclusion_trace = _eval_node(scheme.inclusion, profile.get("self", {}))

    exclusion_results: list[Trit] = []
    exclusions_trace: list[dict[str, Any]] = []
    for i, excl in enumerate(scheme.exclusions):
        result, trace = _eval_exclusion(excl, profile)
        exclusion_results.append(result)
        trace["index"] = i
        exclusions_trace.append(trace)

    excluded_overall = _combine_or3(exclusion_results) if exclusion_results else False
    verdict = _final_verdict(inclusion_result, excluded_overall)

    trace = {
        "scheme_id": scheme.scheme_id,
        "inclusion": inclusion_trace,
        "inclusion_result": inclusion_result,
        "exclusions": exclusions_trace,
        "excluded_overall": excluded_overall,
        "operational_requirements": list(scheme.operational_requirements),
        "verdict": verdict.value,
    }
    return EvaluationResult(verdict=verdict, trace=trace)
