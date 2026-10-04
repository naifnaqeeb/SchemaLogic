"""Structural F1 evaluation (plan Section 7, O1/O2), formalizing the manual diff process used by
hand for PM-KISAN, IGNOAPS, and MH-LADKI-BAHIN. Same output shape as those manual reports
(exact_matches / present_but_wrong / missing / hallucinated) so results are comparable across
schemes, plus per-PredicateCategory precision/recall/F1 and a schema-validity rate at batch level.

Matching is field-name based (post-ontology, field names should mostly align — this metric would
be close to useless pre-ontology, when 0/N field names ever matched at all). A predicate is a true
positive only if field, op, value (and quantifier, for exclusions) all match gold exactly. A
matched field with any other difference counts as a "wrong_value" mismatch — contributing to BOTH
a false negative (the correct fact wasn't captured) and a false positive (the draft asserted
something incorrect), standard for slot-filling evaluation. Category metrics are keyed by gold's
`cat` for matched/missing predicates and by draft's `cat` for hallucinated ones (there's no gold
`cat` to charge them against). Gold/draft `cat` disagreements on an otherwise-matched field are
logged separately as `category_tag_mismatches` — a distinct diagnostic from field/value
correctness.

Exceptions are scored too (since 2026-10-04; before that a changed `except` clause could never move
the metric -- AB-PMJAY scored 1.000 before and after a fix that changed real verdicts). Each `except`
is its own predicate at location "exception", paired through the field of the exclusion it belongs
to, and a true positive only if its field, op, value and `except_scope` all match. They are charged
to their own category, "exception_to_exclusion" -- the plan's C3 "exceptions-to-exclusions" -- so a
per-category figure for exceptions measures them. A missing exception is a false negative even when
its exclusion matched; the exclusion's own match is unaffected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from schemelogic.schema.models import AndNode, Exclusion, OrNode, Predicate, PredicateCategory, Scheme

Location = Literal["inclusion", "exclusion", "exception"]
EXCEPTION_CATEGORY = "exception_to_exclusion"  # the plan's C3 "exceptions-to-exclusions" category


def _enum_value(x: Any) -> Any:
    return x.value if hasattr(x, "value") else x


@dataclass(frozen=True)
class FlatPredicate:
    location: Location
    field: str
    cat: str
    op: str
    value: Any
    quantifier: str | None  # None for inclusion predicates
    has_except: bool = False
    parent_field: str | None = None  # location "exception": the field of the exclusion it belongs to
    except_scope: str | None = None  # location "exception" only

    def identity(self) -> tuple[str, str]:
        """What a gold and a draft predicate are paired on: location plus field -- for an exception,
        the field of its exclusion, so each exception is compared with the same exclusion's."""
        return (self.location, self.parent_field if self.location == "exception" else self.field)

    def match_key(self) -> tuple:
        return (self.location, self.parent_field, self.field, self.op, repr(self.value),
                self.quantifier, self.except_scope)


def _flatten_inclusion(node: Any, out: list[FlatPredicate]) -> None:
    if isinstance(node, Predicate):
        out.append(
            FlatPredicate(
                location="inclusion", field=node.field, cat=_enum_value(node.cat),
                op=_enum_value(node.op), value=node.value, quantifier=None,
            )
        )
    elif isinstance(node, AndNode):
        for c in node.and_:
            _flatten_inclusion(c, out)
    elif isinstance(node, OrNode):
        for c in node.or_:
            _flatten_inclusion(c, out)


def _flatten_exclusions(exclusions: list[Exclusion]) -> list[FlatPredicate]:
    return [
        FlatPredicate(
            location="exclusion", field=e.field, cat=_enum_value(e.cat), op=_enum_value(e.op),
            value=e.value, quantifier=_enum_value(e.quantifier), has_except=e.except_ is not None,
        )
        for e in exclusions
    ]


def _flatten_exceptions(exclusions: list[Exclusion]) -> list[FlatPredicate]:
    return [
        FlatPredicate(
            location="exception", field=e.except_.field, cat=EXCEPTION_CATEGORY,
            op=_enum_value(e.except_.op), value=e.except_.value, quantifier=None,
            parent_field=e.field, except_scope=_enum_value(e.except_scope),
        )
        for e in exclusions
        if e.except_ is not None
    ]


def flatten_scheme(scheme: Scheme) -> list[FlatPredicate]:
    inclusion: list[FlatPredicate] = []
    _flatten_inclusion(scheme.inclusion, inclusion)
    return inclusion + _flatten_exclusions(scheme.exclusions) + _flatten_exceptions(scheme.exclusions)


@dataclass
class CategoryMetrics:
    category: str
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 1.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category, "tp": self.tp, "fp": self.fp, "fn": self.fn,
            "precision": round(self.precision, 4), "recall": round(self.recall, 4), "f1": round(self.f1, 4),
        }


@dataclass
class CategoryTagMismatch:
    location: Location
    field: str
    gold_cat: str
    draft_cat: str


@dataclass
class StructuralComparisonResult:
    scheme_id: str
    inclusion_diff: dict[str, list[dict[str, Any]]]
    exclusion_diff: dict[str, list[dict[str, Any]]]
    exception_diff: dict[str, list[dict[str, Any]]]
    category_metrics: dict[str, CategoryMetrics]
    overall: CategoryMetrics
    category_tag_mismatches: list[CategoryTagMismatch]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scheme_id": self.scheme_id,
            "inclusion_diff": self.inclusion_diff,
            "exclusion_diff": self.exclusion_diff,
            "exception_diff": self.exception_diff,
            "category_metrics": {k: v.to_dict() for k, v in self.category_metrics.items()},
            "overall": self.overall.to_dict(),
            "category_tag_mismatches": [
                {"location": m.location, "field": m.field, "gold_cat": m.gold_cat, "draft_cat": m.draft_cat}
                for m in self.category_tag_mismatches
            ],
        }


def _predicate_summary(p: FlatPredicate) -> dict[str, Any]:
    d = {"field": p.field, "cat": p.cat, "op": p.op, "value": p.value}
    if p.location == "exclusion":
        d["quantifier"] = p.quantifier
        d["has_except"] = p.has_except
    if p.location == "exception":
        d["exclusion"] = p.parent_field
        d["except_scope"] = p.except_scope
    return d


Pairing = list[tuple[FlatPredicate | None, FlatPredicate | None]]


def _pair(gold_preds: list[FlatPredicate], draft_preds: list[FlatPredicate]) -> Pairing:
    """Pair gold with draft predicates sharing an identity (location + field), as MULTISETS: two
    predicates on one field in one place -- a lower and an upper age bound -- are two predicates, not
    one. Within an identity, exact matches pair first, then the remainder pair in order (a wrong
    value: both a false negative and a false positive); what's left over is missing (gold only) or
    hallucinated (draft only). Before 2026-10-04 a dict keyed by identity kept only the last
    predicate of each field and silently dropped the others."""
    by_id: dict[tuple[str, str], tuple[list[FlatPredicate], list[FlatPredicate]]] = {}
    for g in gold_preds:
        by_id.setdefault(g.identity(), ([], []))[0].append(g)
    for d in draft_preds:
        by_id.setdefault(d.identity(), ([], []))[1].append(d)

    pairs: Pairing = []
    for gold_list, draft_list in by_id.values():
        gold_left, draft_left = list(gold_list), list(draft_list)
        for g in list(gold_left):
            match = next((d for d in draft_left if d.match_key() == g.match_key()), None)
            if match is not None:
                pairs.append((g, match))
                gold_left.remove(g)
                draft_left.remove(match)
        while gold_left and draft_left:
            pairs.append((gold_left.pop(0), draft_left.pop(0)))
        pairs.extend((g, None) for g in gold_left)
        pairs.extend((None, d) for d in draft_left)
    return pairs


def _diff_location(gold_preds: list[FlatPredicate], draft_preds: list[FlatPredicate]) -> dict[str, list[dict[str, Any]]]:
    exact_matches, present_but_wrong, missing, hallucinated = [], [], [], []
    for g, d in _pair(gold_preds, draft_preds):
        if d is None:
            missing.append(_predicate_summary(g))
        elif g is None:
            hallucinated.append(_predicate_summary(d))
        elif g.match_key() == d.match_key():
            exact_matches.append({"field": g.identity()[1]})
        else:
            present_but_wrong.append({"field": g.identity()[1], "gold": _predicate_summary(g), "draft": _predicate_summary(d)})
    return {
        "exact_matches": exact_matches, "present_but_wrong": present_but_wrong,
        "missing": missing, "hallucinated": hallucinated,
    }


def compare_schemes(gold: Scheme, draft: Scheme) -> StructuralComparisonResult:
    gold_flat = flatten_scheme(gold)
    draft_flat = flatten_scheme(draft)

    def at(preds: list[FlatPredicate], location: str) -> list[FlatPredicate]:
        return [p for p in preds if p.location == location]

    inclusion_diff = _diff_location(at(gold_flat, "inclusion"), at(draft_flat, "inclusion"))
    exclusion_diff = _diff_location(at(gold_flat, "exclusion"), at(draft_flat, "exclusion"))
    exception_diff = _diff_location(at(gold_flat, "exception"), at(draft_flat, "exception"))

    category_metrics: dict[str, CategoryMetrics] = {}

    def _metrics_for(cat: str) -> CategoryMetrics:
        return category_metrics.setdefault(cat, CategoryMetrics(category=cat))

    category_tag_mismatches: list[CategoryTagMismatch] = []

    # Paired on (location, field) as multisets -- see _pair. Keyed by field alone (before 2026-10-04),
    # an exception collided with an exclusion or inclusion leaf on the same field (AB-PMJAY's age).
    for g, d in _pair(gold_flat, draft_flat):
        if g is None:
            _metrics_for(d.cat).fp += 1
            continue
        m = _metrics_for(g.cat)
        if d is None:
            m.fn += 1
            continue
        if g.match_key() == d.match_key():
            m.tp += 1
        else:
            m.fn += 1
            m.fp += 1
        if g.cat != d.cat:
            category_tag_mismatches.append(
                CategoryTagMismatch(location=g.location, field=g.identity()[1], gold_cat=g.cat, draft_cat=d.cat)
            )

    overall = CategoryMetrics(category="__overall__")
    for m in category_metrics.values():
        overall.tp += m.tp
        overall.fp += m.fp
        overall.fn += m.fn

    return StructuralComparisonResult(
        scheme_id=gold.scheme_id,
        inclusion_diff=inclusion_diff,
        exclusion_diff=exclusion_diff,
        exception_diff=exception_diff,
        category_metrics=category_metrics,
        overall=overall,
        category_tag_mismatches=category_tag_mismatches,
    )


@dataclass
class BatchStructuralReport:
    n_attempted: int
    n_schema_valid: int
    per_scheme: list[StructuralComparisonResult]
    aggregate_category_metrics: dict[str, CategoryMetrics]
    aggregate_overall: CategoryMetrics

    @property
    def schema_validity_rate(self) -> float:
        return self.n_schema_valid / self.n_attempted if self.n_attempted else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_attempted": self.n_attempted,
            "n_schema_valid": self.n_schema_valid,
            "schema_validity_rate": round(self.schema_validity_rate, 4),
            "per_scheme": [r.to_dict() for r in self.per_scheme],
            "aggregate_category_metrics": {k: v.to_dict() for k, v in self.aggregate_category_metrics.items()},
            "aggregate_overall": self.aggregate_overall.to_dict(),
        }


def build_batch_report(entries: list[tuple[str, Scheme, Scheme | None]]) -> BatchStructuralReport:
    """entries: (scheme_id, gold_scheme, draft_scheme_or_None). None means extraction for this
    scheme did not produce a schema-valid Scheme at all (an ExtractionFailure) — counted toward
    schema_validity_rate but excluded from the category P/R/F1 aggregation, since there's nothing
    structural to compare."""
    per_scheme: list[StructuralComparisonResult] = []
    n_valid = 0
    aggregate: dict[str, CategoryMetrics] = {}

    for scheme_id, gold, draft in entries:
        if draft is None:
            continue
        n_valid += 1
        result = compare_schemes(gold, draft)
        per_scheme.append(result)
        for cat, m in result.category_metrics.items():
            agg = aggregate.setdefault(cat, CategoryMetrics(category=cat))
            agg.tp += m.tp
            agg.fp += m.fp
            agg.fn += m.fn

    overall = CategoryMetrics(category="__overall__")
    for m in aggregate.values():
        overall.tp += m.tp
        overall.fp += m.fp
        overall.fn += m.fn

    return BatchStructuralReport(
        n_attempted=len(entries), n_schema_valid=n_valid, per_scheme=per_scheme,
        aggregate_category_metrics=aggregate, aggregate_overall=overall,
    )
