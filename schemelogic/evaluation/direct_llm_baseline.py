"""Baseline 2 (plan Section 7): ask an LLM "is this person eligible?" directly, with no symbolic
layer anywhere in the path.

This is the baseline the project's central claim rests on. Everything else here is built to keep
the LLM away from the verdict; this module deliberately does the opposite, so that "the
neuro-symbolic separation matters" becomes a measured comparison instead of an assertion. It is
the ONE place in this codebase where an LLM's output IS the verdict -- permitted because nothing
here touches the citizen-facing path: it is offline evaluation machinery, reached only by the
baseline runner, and its output is never rendered to anyone as advice.

Deliberately a FAIR baseline, not a strawman. It gets:
  - the same primary source document a human annotator worked from (data/raw_documents/<id>.md),
    not a truncated snippet and not the structured gold rules,
  - the complete citizen profile, every fact the symbolic evaluator is given, rendered plainly,
  - an explicit "unsure" option, so it is never forced to guess between eligible/ineligible,
  - the same model the extraction pipeline uses.
Sandbagging it would make the comparison worthless: the interesting result is what a capable model
does when asked the question the way a naive integration would ask it.

The comparison target is the real evaluator's verdict over the same profile, which is what
evaluation/outcome_equivalence.py already does for extracted-vs-gold rules -- same three-valued
vocabulary, same profile suites, so the numbers sit alongside each other.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

from schemelogic.evaluator.symbolic_engine import Verdict, evaluate
from schemelogic.llm.provider import ProviderFailure, chat_completion_with_fallback
from schemelogic.schema.models import Scheme

DirectVerdict = Literal["eligible", "ineligible", "unsure"]
_VALID_VERDICTS = ("eligible", "ineligible", "unsure")

# How a baseline answer relates to the symbolic evaluator's answer on the same profile. Split by
# DIRECTION, never collapsed into one accuracy number: a wrong "eligible" sends a citizen to spend
# time and money on an application that cannot succeed, while a wrong "ineligible" denies someone a
# benefit they are owed. Those are different harms and the project's framing (O4/C5) turns on not
# averaging them together.
Disagreement = Literal[
    "agree",
    "false_positive_vs_ineligible",   # baseline says yes, the rules say no -- wasted application
    "false_positive_vs_undetermined", # baseline says yes, the rules can't tell without more facts
    "false_negative",                 # baseline says no, the rules say yes -- benefit denied
    "over_cautious",                  # baseline unsure, the rules reach a definite verdict
    "other",
]

HARMFUL_POSITIVE = ("false_positive_vs_ineligible", "false_positive_vs_undetermined")


@dataclass
class DirectAnswer:
    verdict: DirectVerdict
    reason: str
    provider_used: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@dataclass
class DirectFailure:
    detail: str


@dataclass
class ProfileComparison:
    profile_id: str
    baseline_verdict: DirectVerdict | None
    evaluator_verdict: str
    relation: Disagreement
    baseline_reason: str = ""


@dataclass
class SchemeBaselineReport:
    scheme_id: str
    comparisons: list[ProfileComparison] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    tokens_used: int = 0

    @property
    def n(self) -> int:
        return len(self.comparisons)

    @property
    def agreement_rate(self) -> float:
        return self._rate("agree")

    @property
    def harmful_positive_rate(self) -> float:
        if not self.n:
            return 0.0
        harmful = sum(1 for c in self.comparisons if c.relation in HARMFUL_POSITIVE)
        return harmful / self.n

    def _rate(self, relation: str) -> float:
        if not self.n:
            return 0.0
        return sum(1 for c in self.comparisons if c.relation == relation) / self.n

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for c in self.comparisons:
            out[c.relation] = out.get(c.relation, 0) + 1
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "scheme_id": self.scheme_id,
            "n_profiles": self.n,
            "agreement_rate": self.agreement_rate,
            "harmful_positive_rate": self.harmful_positive_rate,
            "counts": self.counts(),
            "tokens_used": self.tokens_used,
            "failures": self.failures,
            "comparisons": [
                {
                    "profile_id": c.profile_id,
                    "baseline_verdict": c.baseline_verdict,
                    "evaluator_verdict": c.evaluator_verdict,
                    "relation": c.relation,
                    "baseline_reason": c.baseline_reason,
                }
                for c in self.comparisons
            ],
        }


def render_profile(profile: dict[str, Any]) -> str:
    """The citizen's facts as plain lines. Uses the profile's own field names -- the same names the
    gold rules use -- so the baseline is told exactly what the evaluator is told, no more and no
    less. Booleans are rendered yes/no rather than true/false purely for readability."""

    def render_value(value: Any) -> str:
        if isinstance(value, bool):
            return "yes" if value else "no"
        return str(value)

    lines: list[str] = ["The applicant:"]
    for key, value in (profile.get("self") or {}).items():
        lines.append(f"  - {key}: {render_value(value)}")

    for i, member in enumerate(profile.get("family_members") or [], start=1):
        lines.append(f"Family member {i}:")
        for key, value in member.items():
            lines.append(f"  - {key}: {render_value(value)}")

    if len(lines) == 1:
        lines.append("  (no facts recorded)")
    return "\n".join(lines)


def _system_prompt() -> str:
    return (
        "You are an assistant that answers citizens' questions about eligibility for Indian "
        "government welfare schemes. You will be given a scheme's official document and the facts "
        "known about one applicant. Decide whether that applicant is eligible for the scheme.\n\n"
        'Answer with a JSON object: {"verdict": "eligible" | "ineligible" | "unsure", '
        '"reason": "<one or two sentences>"}\n\n'
        'Use "unsure" if the document or the applicant\'s facts do not let you decide. Do not '
        "guess between eligible and ineligible when you genuinely cannot tell."
    )


def ask_direct(
    document_text: str, profile: dict[str, Any], scheme_name: str | None = None, **call_kwargs: Any
) -> DirectAnswer | DirectFailure:
    """One LLM call, one verdict. No evaluator, no rules, no trace -- this is the whole point."""
    header = f"Scheme: {scheme_name}\n\n" if scheme_name else ""
    user = (
        f"{header}--- SCHEME DOCUMENT ---\n{document_text}\n\n"
        f"--- APPLICANT FACTS ---\n{render_profile(profile)}\n\n"
        "Is this applicant eligible for this scheme?"
    )
    kwargs: dict[str, Any] = {
        "temperature": 0.0,
        # gpt-oss bills reasoning tokens against max_tokens, so a cap sized for the answer alone
        # returns empty content with finish_reason='length' (learned the hard way twice in this
        # project). Generous here so the baseline is never crippled by budget mechanics.
        "max_tokens": 700,
        "response_format": {"type": "json_object"},
    }
    kwargs.update(call_kwargs)

    try:
        response = chat_completion_with_fallback(
            [{"role": "system", "content": _system_prompt()}, {"role": "user", "content": user}],
            **kwargs,
        )
    except Exception as exc:  # noqa: BLE001
        return DirectFailure(detail=f"unexpected {type(exc).__name__}: {exc}")

    if isinstance(response, ProviderFailure):
        return DirectFailure(detail=f"provider failure: {response.primary_error}")

    try:
        parsed = json.loads(response.content or "")
        verdict = str(parsed.get("verdict", "")).strip().lower()
    except (json.JSONDecodeError, AttributeError, TypeError) as exc:
        return DirectFailure(detail=f"unparseable response: {exc}")

    if verdict not in _VALID_VERDICTS:
        return DirectFailure(detail=f"unrecognized verdict {verdict!r}")

    usage = getattr(response, "usage", None)
    return DirectAnswer(
        verdict=verdict,  # type: ignore[arg-type]
        reason=str(parsed.get("reason", ""))[:500],
        provider_used=getattr(response, "provider_used", None),
        prompt_tokens=getattr(usage, "prompt_tokens", None),
        completion_tokens=getattr(usage, "completion_tokens", None),
    )


def classify(baseline: DirectVerdict, evaluator: Verdict) -> Disagreement:
    if baseline == "eligible" and evaluator == Verdict.ELIGIBLE:
        return "agree"
    if baseline == "ineligible" and evaluator == Verdict.INELIGIBLE:
        return "agree"
    if baseline == "unsure" and evaluator == Verdict.UNDETERMINED:
        return "agree"
    if baseline == "eligible" and evaluator == Verdict.INELIGIBLE:
        return "false_positive_vs_ineligible"
    if baseline == "eligible" and evaluator == Verdict.UNDETERMINED:
        return "false_positive_vs_undetermined"
    if baseline == "ineligible" and evaluator == Verdict.ELIGIBLE:
        return "false_negative"
    if baseline == "unsure" and evaluator in (Verdict.ELIGIBLE, Verdict.INELIGIBLE):
        return "over_cautious"
    return "other"


def compare_profile(
    scheme: Scheme, profile_id: str, profile: dict[str, Any], answer: DirectAnswer
) -> ProfileComparison:
    """The evaluator side is computed the ordinary way -- the same evaluate() every verdict in this
    project comes from -- so the baseline is compared against the system's real behaviour, not
    against a second opinion produced for the occasion."""
    evaluator_verdict = evaluate(scheme, profile).verdict
    return ProfileComparison(
        profile_id=profile_id,
        baseline_verdict=answer.verdict,
        evaluator_verdict=evaluator_verdict.value,
        relation=classify(answer.verdict, evaluator_verdict),
        baseline_reason=answer.reason,
    )
