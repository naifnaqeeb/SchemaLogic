"""Unit tests for the outcome-equivalence comparator using synthetic gold/draft schemes —
isolated from any live LLM call, so the FP/FN/other-mismatch classification logic is verifiable
on its own. The PM-KISAN run against the real Groq draft extraction is a separate, one-off script
(not a pytest test, since it needs a live API key and network access)."""

from schemelogic.evaluation.outcome_equivalence import evaluate_outcome_equivalence
from schemelogic.schema.models import Scheme

GOLD_SCHEME = Scheme.model_validate(
    {
        "scheme_id": "TEST-OUTCOME",
        "unit_of_eligibility": "individual",
        "inclusion": {"cat": "demographic", "field": "age", "op": ">=", "value": 18},
        "exclusions": [],
        "temporal_validity": {"valid_from": "2020-01-01", "extracted_at": "2026-01-01"},
        "extraction_metadata": {"confidence": 1.0, "source_clause": "test", "flagged_for_review": False},
    }
)

# Deliberately uses a DIFFERENT field name (adult_flag vs age) to simulate the exact
# field-vocabulary drift seen in the real PM-KISAN draft extraction.
DRAFT_SCHEME = Scheme.model_validate(
    {
        "scheme_id": "TEST-OUTCOME",
        "unit_of_eligibility": "individual",
        "inclusion": {"cat": "demographic", "field": "adult_flag", "op": "==", "value": True},
        "exclusions": [],
        "temporal_validity": {"valid_from": "2020-01-01", "extracted_at": "2026-01-01"},
        "extraction_metadata": {"confidence": 0.7, "source_clause": "draft", "flagged_for_review": True},
    }
)

PROFILES = {
    "both_eligible": {"self": {"age": 20, "adult_flag": True}},
    "false_positive": {"self": {"age": 10, "adult_flag": True}},
    "false_negative": {"self": {"age": 20, "adult_flag": False}},
    "other_mismatch": {"self": {"age": 20}},
    "both_undetermined": {"self": {}},
}


def test_outcome_equivalence_classifies_agreement_and_disagreement_correctly():
    report = evaluate_outcome_equivalence(GOLD_SCHEME, DRAFT_SCHEME, PROFILES)

    assert report.n_profiles == 5
    assert report.agreement_rate == 2 / 5
    assert report.false_positive_eligible_rate == 1 / 5
    assert report.false_negative_eligible_rate == 1 / 5
    assert report.other_mismatch_rate == 1 / 5

    by_id = {c.profile_id: c for c in report.comparisons}
    assert by_id["both_eligible"].agree is True
    assert by_id["false_positive"].disagreement_type == "false_positive_eligible"
    assert by_id["false_negative"].disagreement_type == "false_negative_eligible"
    assert by_id["other_mismatch"].disagreement_type == "other_mismatch"
    assert by_id["both_undetermined"].agree is True
    assert by_id["both_undetermined"].gold_verdict == "undetermined_missing_facts"


def test_identical_schemes_have_perfect_agreement():
    report = evaluate_outcome_equivalence(GOLD_SCHEME, GOLD_SCHEME, PROFILES)
    assert report.agreement_rate == 1.0
    assert report.false_positive_eligible_rate == 0.0
    assert report.false_negative_eligible_rate == 0.0
    assert report.other_mismatch_rate == 0.0


def test_undetermined_mismatch_never_counted_as_false_positive_or_negative():
    """An undetermined verdict on either side must land in other_mismatch, never FP/FN —
    it's asking another question, not asserting a wrong eligibility answer."""
    report = evaluate_outcome_equivalence(
        GOLD_SCHEME, DRAFT_SCHEME, {"p": PROFILES["other_mismatch"]}
    )
    assert report.false_positive_eligible_rate == 0.0
    assert report.false_negative_eligible_rate == 0.0
    assert report.other_mismatch_rate == 1.0
