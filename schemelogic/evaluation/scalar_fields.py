"""Scalar Scheme-field grounding check (Phase 3 checkpoint addition).

structural_f1.py only flattens `inclusion`/`exclusions` predicates — by design, since those are
what P/R/F1 measures. That leaves whole-Scheme scalar fields invisible to any metric: two
confirmed instances of a scalar field being silently wrong found during Phase 3 scaling —
AB-PMJAY's `temporal_validity.valid_from` fabricated as a specific day the source document never
stated, and PM-UJJWALA-2.0's `unit_of_eligibility` extracted as 'family' when gold/the source both
say 'individual' (the evaluator never reads `unit_of_eligibility`, so this didn't show up in
outcome-equivalence either — a silent miss with no other metric that would have caught it).

Deliberately NOT folded into structural_f1.py's StructuralComparisonResult — reported as its own
small, separate result, same treatment as the temporal-groundedness check the calibration gate
already does for judge findings. Extensible: add a (name, accessor) pair to `SCALAR_FIELDS` for
any additional scalar field found to need this treatment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from schemelogic.schema.models import Scheme


def _enum_value(x: Any) -> Any:
    return x.value if hasattr(x, "value") else x


# (field_name, accessor) — accessor pulls the comparable value off a Scheme. Add more pairs here
# as additional scalar-field misses get confirmed.
SCALAR_FIELDS: list[tuple[str, Callable[[Scheme], Any]]] = [
    ("unit_of_eligibility", lambda s: _enum_value(s.unit_of_eligibility)),
    ("temporal_validity.valid_from", lambda s: s.temporal_validity.valid_from),
]


@dataclass
class ScalarFieldMismatch:
    field: str
    gold_value: Any
    draft_value: Any


@dataclass
class ScalarFieldReport:
    scheme_id: str
    n_checked: int
    mismatches: list[ScalarFieldMismatch]

    @property
    def n_matched(self) -> int:
        return self.n_checked - len(self.mismatches)

    @property
    def match_rate(self) -> float:
        return self.n_matched / self.n_checked if self.n_checked else 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "scheme_id": self.scheme_id,
            "n_checked": self.n_checked,
            "n_matched": self.n_matched,
            "match_rate": round(self.match_rate, 4),
            "mismatches": [
                {"field": m.field, "gold_value": str(m.gold_value), "draft_value": str(m.draft_value)}
                for m in self.mismatches
            ],
        }


def check_scalar_fields(gold: Scheme, draft: Scheme) -> ScalarFieldReport:
    mismatches = []
    for name, accessor in SCALAR_FIELDS:
        gold_value = accessor(gold)
        draft_value = accessor(draft)
        if gold_value != draft_value:
            mismatches.append(ScalarFieldMismatch(field=name, gold_value=gold_value, draft_value=draft_value))
    return ScalarFieldReport(scheme_id=gold.scheme_id, n_checked=len(SCALAR_FIELDS), mismatches=mismatches)
