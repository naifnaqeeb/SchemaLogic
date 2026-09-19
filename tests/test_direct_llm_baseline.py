"""Baseline 2 (direct-LLM eligibility answering). Provider mocked throughout.

This module is the one place in the codebase where an LLM's output IS a verdict, so what these
tests pin down is (a) that the classification of baseline-vs-evaluator disagreement is correct and
DIRECTIONAL, since averaging the two error directions together would destroy the measurement the
baseline exists to produce, and (b) that the baseline is fed fairly -- a strawman baseline would
make the whole comparison worthless.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from schemelogic.evaluation import direct_llm_baseline as dlb
from schemelogic.evaluator.symbolic_engine import Verdict
from schemelogic.llm.provider import ProviderFailure, ProviderResult
from schemelogic.schema.models import Scheme
from tests.fixtures import PM_KISAN

SCHEME = Scheme.model_validate(PM_KISAN)


def _answer(verdict: str, reason: str = "because"):
    return patch(
        "schemelogic.evaluation.direct_llm_baseline.chat_completion_with_fallback",
        return_value=ProviderResult(
            content=json.dumps({"verdict": verdict, "reason": reason}), provider_used="groq"
        ),
    )


# --- directional classification -----------------------------------------------------------------


@pytest.mark.parametrize(
    "baseline,evaluator,expected",
    [
        ("eligible", Verdict.ELIGIBLE, "agree"),
        ("ineligible", Verdict.INELIGIBLE, "agree"),
        ("unsure", Verdict.UNDETERMINED, "agree"),
        ("eligible", Verdict.INELIGIBLE, "false_positive_vs_ineligible"),
        ("eligible", Verdict.UNDETERMINED, "false_positive_vs_undetermined"),
        ("ineligible", Verdict.ELIGIBLE, "false_negative"),
        ("unsure", Verdict.ELIGIBLE, "over_cautious"),
        ("unsure", Verdict.INELIGIBLE, "over_cautious"),
        ("ineligible", Verdict.UNDETERMINED, "other"),
    ],
)
def test_disagreement_is_classified_by_direction(baseline, evaluator, expected):
    assert dlb.classify(baseline, evaluator) == expected


def test_both_harmful_positive_directions_are_counted_as_harmful():
    """A wrong "eligible" is the harm the project's framing is built around: it sends a citizen to
    spend time and money on an application that cannot succeed. Claiming eligibility the rules
    can't support (UNDETERMINED) is the same harm -- the citizen acts on it identically."""
    assert set(dlb.HARMFUL_POSITIVE) == {
        "false_positive_vs_ineligible",
        "false_positive_vs_undetermined",
    }


def test_report_separates_agreement_from_harmful_rate():
    report = dlb.SchemeBaselineReport(scheme_id="X")
    report.comparisons = [
        dlb.ProfileComparison("a", "eligible", "eligible", "agree"),
        dlb.ProfileComparison("b", "eligible", "ineligible", "false_positive_vs_ineligible"),
        dlb.ProfileComparison("c", "eligible", "undetermined_missing_facts", "false_positive_vs_undetermined"),
        dlb.ProfileComparison("d", "ineligible", "eligible", "false_negative"),
    ]
    assert report.agreement_rate == 0.25
    assert report.harmful_positive_rate == 0.5  # both positive directions, not averaged away
    assert report.counts()["false_negative"] == 1


# --- the baseline is fed fairly -------------------------------------------------------------------


def test_profile_rendering_includes_every_fact_the_evaluator_gets():
    profile = {
        "self": {"is_indian_citizen": True, "monthly_pension_inr": 12000, "is_wealthy": False},
        "family_members": [{"paid_income_tax_last_assessment_year": True}],
    }
    rendered = dlb.render_profile(profile)
    assert "is_indian_citizen: yes" in rendered
    assert "monthly_pension_inr: 12000" in rendered
    assert "is_wealthy: no" in rendered
    assert "Family member 1" in rendered
    assert "paid_income_tax_last_assessment_year: yes" in rendered


def test_empty_profile_renders_explicitly_rather_than_silently_blank():
    rendered = dlb.render_profile({"self": {}, "family_members": []})
    assert "no facts recorded" in rendered


def test_the_call_sends_the_whole_source_document_not_the_structured_rules():
    doc = "PM-KISAN operational guidelines. Exclusion: income tax payers. " * 5
    with _answer("eligible") as call:
        dlb.ask_direct(doc, {"self": {"is_indian_citizen": True}, "family_members": []}, "PM-KISAN")
    user_msg = call.call_args.args[0][1]["content"]
    assert doc in user_msg
    assert "inclusion" not in user_msg.lower()  # no gold rule structure leaks in
    assert "exclusions" not in user_msg.lower()


def test_unsure_is_offered_so_the_baseline_is_never_forced_to_guess():
    assert "unsure" in dlb._system_prompt()
    assert "Do not guess" in dlb._system_prompt()


# --- failure handling -----------------------------------------------------------------------------


def test_provider_failure_is_reported_not_silently_counted_as_a_verdict():
    with patch(
        "schemelogic.evaluation.direct_llm_baseline.chat_completion_with_fallback",
        return_value=ProviderFailure(primary_error="down", secondary_error="down"),
    ):
        result = dlb.ask_direct("doc", {"self": {}, "family_members": []})
    assert isinstance(result, dlb.DirectFailure)


def test_unrecognized_verdict_is_a_failure_not_a_coerced_answer():
    with _answer("probably"):
        result = dlb.ask_direct("doc", {"self": {}, "family_members": []})
    assert isinstance(result, dlb.DirectFailure)
    assert "probably" in result.detail


def test_unparseable_response_is_a_failure():
    with patch(
        "schemelogic.evaluation.direct_llm_baseline.chat_completion_with_fallback",
        return_value=ProviderResult(content="not json at all", provider_used="groq"),
    ):
        assert isinstance(dlb.ask_direct("doc", {"self": {}, "family_members": []}), dlb.DirectFailure)


# --- the evaluator side is the real one -----------------------------------------------------------


def test_comparison_uses_the_real_symbolic_evaluator():
    """An income-tax-paying family member is a hard PM-KISAN exclusion, so the evaluator must say
    ineligible regardless of what the mocked LLM claims -- the baseline never influences it."""
    profile = {
        "self": {
            "is_indian_citizen": True,
            "owns_cultivable_land_in_records": True,
            "is_institutional_landholder": False,
            "paid_income_tax_last_assessment_year": True,
            "is_serving_or_retired_govt_employee": False,
            "monthly_pension_inr": 0,
            "holds_constitutional_or_political_post": False,
            "is_practicing_registered_professional": False,
            "is_nri_per_income_tax_act_1961": False,
        },
        "family_members": [],
    }
    with _answer("eligible", "looks like a farmer"):
        answer = dlb.ask_direct("doc", profile, "PM-KISAN")
    comparison = dlb.compare_profile(SCHEME, "tax_payer", profile, answer)
    assert comparison.evaluator_verdict == "ineligible"
    assert comparison.relation == "false_positive_vs_ineligible"
