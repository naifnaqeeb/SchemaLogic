"""Unit tests for the pure-logic half of judge_repair.py (apply_judge_findings) — no live Groq
call needed, since it just takes a Scheme + a list of JudgeFinding and returns a patched Scheme.
The judge call itself (run_judge) needs a live API key/network and is validated in the Phase 2
report against real schemes instead, not here."""

from schemelogic.extraction.judge_repair import (
    JudgeFinding,
    ProposedExceptClause,
    ProposedPredicate,
    ProposedSupersedes,
    apply_judge_findings,
)
from schemelogic.schema.models import AndNode, Predicate, Scheme

BASE_SCHEME = Scheme.model_validate(
    {
        "scheme_id": "TEST-REPAIR",
        "unit_of_eligibility": "individual",
        "inclusion": {"cat": "demographic", "field": "age", "op": ">=", "value": 18},
        "exclusions": [
            {"cat": "economic", "quantifier": "self", "field": "is_wealthy", "op": "==", "value": True}
        ],
        "temporal_validity": {"valid_from": "2020-01-01", "extracted_at": "2026-01-01"},
        "extraction_metadata": {"confidence": 0.9, "source_clause": "test", "flagged_for_review": False},
    }
)


def test_inclusion_finding_wraps_existing_predicate_in_and():
    finding = JudgeFinding(
        category="preambular_implied_fact",
        description="implied citizenship requirement",
        source_quote="...",
        confidence=0.9,
        proposed_predicate=ProposedPredicate(
            location="inclusion", cat="citizenship", field="is_citizen", op="==", value=True
        ),
    )
    repaired, log = apply_judge_findings(BASE_SCHEME, [finding])
    assert isinstance(repaired.inclusion, AndNode)
    fields = {p.field for p in repaired.inclusion.and_}
    assert fields == {"age", "is_citizen"}
    assert log[0]["applied"] is True
    assert log[0]["type"] == "predicate"


def test_exclusion_finding_appended_to_exclusions():
    finding = JudgeFinding(
        category="preambular_implied_fact",
        description="implied destitution test",
        source_quote="...",
        confidence=0.8,
        proposed_predicate=ProposedPredicate(
            location="exclusion", cat="economic", field="has_support", op="==", value=True,
            quantifier="self",
        ),
    )
    repaired, log = apply_judge_findings(BASE_SCHEME, [finding])
    assert len(repaired.exclusions) == 2
    assert repaired.exclusions[-1].field == "has_support"
    assert repaired.exclusions[0].field == "is_wealthy"  # original preserved, untouched


def test_exclusion_finding_with_except_clause():
    finding = JudgeFinding(
        category="preambular_implied_fact",
        description="exclusion with exception",
        source_quote="...",
        confidence=0.8,
        proposed_predicate=ProposedPredicate(
            location="exclusion", cat="occupation", field="is_employee", op="==", value=True,
            quantifier="some_family_member",
            **{"except": ProposedExceptClause(field="is_group_d", op="==", value=True)},
        ),
    )
    repaired, _log = apply_judge_findings(BASE_SCHEME, [finding])
    new_exclusion = repaired.exclusions[-1]
    assert new_exclusion.except_ is not None
    assert new_exclusion.except_.field == "is_group_d"


def test_temporal_supersession_finding_updates_supersedes_and_valid_from():
    finding = JudgeFinding(
        category="temporal_supersession",
        description="amendment removed prior 2-hectare cap",
        source_quote="Effective 1 June 2019, this restriction was removed",
        confidence=0.95,
        proposed_supersedes=ProposedSupersedes(
            retired_field="landholding_hectares", retired_op="<=", retired_value=2,
            amendment_source_quote="Effective 1 June 2019, this restriction was removed",
            new_valid_from="2019-06-01",
        ),
    )
    repaired, log = apply_judge_findings(BASE_SCHEME, [finding])
    assert repaired.temporal_validity.supersedes is not None
    assert repaired.temporal_validity.supersedes.retired_predicate["field"] == "landholding_hectares"
    assert repaired.temporal_validity.valid_from.isoformat() == "2019-06-01"
    assert log[0]["type"] == "supersedes"


def test_temporal_supersession_without_new_valid_from_leaves_valid_from_unchanged():
    finding = JudgeFinding(
        category="temporal_supersession",
        description="amendment",
        source_quote="...",
        confidence=0.9,
        proposed_supersedes=ProposedSupersedes(
            retired_field="x", retired_op="==", retired_value=1,
            amendment_source_quote="...",
        ),
    )
    repaired, _log = apply_judge_findings(BASE_SCHEME, [finding])
    assert repaired.temporal_validity.valid_from == BASE_SCHEME.temporal_validity.valid_from


def test_low_confidence_finding_is_skipped():
    finding = JudgeFinding(
        category="preambular_implied_fact",
        description="low confidence guess",
        source_quote="...",
        confidence=0.1,
        proposed_predicate=ProposedPredicate(
            location="inclusion", cat="other", field="maybe_field", op="==", value=True
        ),
    )
    repaired, log = apply_judge_findings(BASE_SCHEME, [finding], min_confidence=0.5)
    assert repaired == BASE_SCHEME
    assert log[0]["applied"] is False
    assert "confidence" in log[0]["reason"]


def test_finding_without_proposal_is_skipped():
    finding = JudgeFinding(
        category="temporal_supersession",
        description="found something but no concrete proposal",
        source_quote="...",
        confidence=0.9,
        proposed_supersedes=None,
    )
    repaired, log = apply_judge_findings(BASE_SCHEME, [finding])
    assert repaired == BASE_SCHEME
    assert log[0]["applied"] is False


def test_multiple_findings_all_applied_independently():
    findings = [
        JudgeFinding(
            category="preambular_implied_fact", description="a", source_quote="...", confidence=0.9,
            proposed_predicate=ProposedPredicate(location="exclusion", cat="other", field="f1", op="==", value=True),
        ),
        JudgeFinding(
            category="preambular_implied_fact", description="b", source_quote="...", confidence=0.9,
            proposed_predicate=ProposedPredicate(location="exclusion", cat="other", field="f2", op="==", value=True),
        ),
    ]
    repaired, log = apply_judge_findings(BASE_SCHEME, findings)
    assert {e.field for e in repaired.exclusions} == {"is_wealthy", "f1", "f2"}
    assert all(entry["applied"] for entry in log)


def test_original_scheme_not_mutated():
    finding = JudgeFinding(
        category="preambular_implied_fact",
        description="x",
        source_quote="...",
        confidence=0.9,
        proposed_predicate=ProposedPredicate(location="exclusion", cat="other", field="new_field", op="==", value=True),
    )
    apply_judge_findings(BASE_SCHEME, [finding])
    assert len(BASE_SCHEME.exclusions) == 1  # unchanged
