"""Behavioral (outcome-equivalence) comparison between a gold Scheme and a draft-extracted Scheme.

Per plan Section 7 (O1, harm-weighted O4/C5): structural field-name diffing is fragile to
vocabulary drift between an LLM's extraction and the gold set's naming conventions — two
predicates can be logically identical and still show up as a structural mismatch. This module
sidesteps that: it never inspects either scheme's internal structure. It runs BOTH schemes
through the same symbolic_engine.evaluate() for each of a set of citizen profiles, and compares
only the resulting verdicts.

Disagreements are split by harm direction, not collapsed into one mismatch count:
- false_positive_eligible: draft says eligible, gold says (definitely) ineligible — a wasted
  application, the citizen is wrongly told to apply.
- false_negative_eligible: draft says ineligible, gold says (definitely) eligible — a denied
  benefit, the citizen is wrongly told they don't qualify.
- other_mismatch: any disagreement involving `undetermined_missing_facts` on either side. This is
  deliberately NOT folded into false_positive/false_negative — an undetermined verdict asks the
  citizen more questions rather than asserting a wrong answer, which is the safe failure mode the
  three-valued design exists to produce. Conflating it with a definite wrong verdict would
  undermine the point of measuring FP/FN separately in the first place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from schemelogic.evaluator.symbolic_engine import Verdict, evaluate
from schemelogic.schema.models import Scheme


@dataclass
class ProfileComparison:
    profile_id: str
    gold_verdict: str
    draft_verdict: str
    agree: bool
    disagreement_type: str | None  # "false_positive_eligible" | "false_negative_eligible" | "other_mismatch" | None


@dataclass
class OutcomeEquivalenceReport:
    scheme_id: str
    n_profiles: int
    agreement_rate: float
    false_positive_eligible_rate: float
    false_negative_eligible_rate: float
    other_mismatch_rate: float
    comparisons: list[ProfileComparison] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scheme_id": self.scheme_id,
            "n_profiles": self.n_profiles,
            "agreement_rate": self.agreement_rate,
            "false_positive_eligible_rate": self.false_positive_eligible_rate,
            "false_negative_eligible_rate": self.false_negative_eligible_rate,
            "other_mismatch_rate": self.other_mismatch_rate,
            "comparisons": [
                {
                    "profile_id": c.profile_id,
                    "gold_verdict": c.gold_verdict,
                    "draft_verdict": c.draft_verdict,
                    "agree": c.agree,
                    "disagreement_type": c.disagreement_type,
                }
                for c in self.comparisons
            ],
        }


def _classify_disagreement(gold_verdict: Verdict, draft_verdict: Verdict) -> str:
    if draft_verdict == Verdict.ELIGIBLE and gold_verdict == Verdict.INELIGIBLE:
        return "false_positive_eligible"
    if gold_verdict == Verdict.ELIGIBLE and draft_verdict == Verdict.INELIGIBLE:
        return "false_negative_eligible"
    return "other_mismatch"


def evaluate_outcome_equivalence(
    gold: Scheme, draft: Scheme, profiles: dict[str, dict]
) -> OutcomeEquivalenceReport:
    """Compare gold vs. draft scheme behavior over a set of {profile_id: profile} citizen profiles.

    Both schemes are run through the identical, unmodified symbolic_engine.evaluate() — this
    function never looks at scheme internals, only at the verdicts each one produces.
    """
    comparisons: list[ProfileComparison] = []
    n_agree = n_fp = n_fn = n_other = 0

    for profile_id, profile in profiles.items():
        gold_verdict = evaluate(gold, profile).verdict
        draft_verdict = evaluate(draft, profile).verdict
        agree = gold_verdict == draft_verdict

        if agree:
            n_agree += 1
            disagreement_type = None
        else:
            disagreement_type = _classify_disagreement(gold_verdict, draft_verdict)
            if disagreement_type == "false_positive_eligible":
                n_fp += 1
            elif disagreement_type == "false_negative_eligible":
                n_fn += 1
            else:
                n_other += 1

        comparisons.append(
            ProfileComparison(
                profile_id=profile_id,
                gold_verdict=gold_verdict.value,
                draft_verdict=draft_verdict.value,
                agree=agree,
                disagreement_type=disagreement_type,
            )
        )

    n = len(profiles)
    return OutcomeEquivalenceReport(
        scheme_id=gold.scheme_id,
        n_profiles=n,
        agreement_rate=n_agree / n,
        false_positive_eligible_rate=n_fp / n,
        false_negative_eligible_rate=n_fn / n,
        other_mismatch_rate=n_other / n,
        comparisons=comparisons,
    )
