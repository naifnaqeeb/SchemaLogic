"""Unit tests for calibration_gate.py using synthetic findings — isolated from any live judge
call. The real 3-scheme validation (does it correctly defer IGNOAPS's fabrication, correctly
accept MH-LADKI-BAHIN's real fixes, etc.) is a separate reported run, not a pytest test, since it
needs the already-logged Phase 2 artifacts and is a one-time validation exercise, not a regression
suite. This file locks down the gate's own decision logic in isolation."""

from schemelogic.deferral.calibration_gate import (
    AUTO_ACCEPT_CAVEAT,
    apply_gate_approved_findings,
    check_self_consistency,
    evaluate_gate,
    evaluate_gate_batch,
)
from schemelogic.schema.models import Scheme
from schemelogic.extraction.judge_repair import JudgeFinding, JudgeReport, ProposedPredicate, ProposedSupersedes

DOC_TEXT = (
    "A 'farmer family' is defined as husband, wife, and minor children who own cultivable land. "
    "The scheme was originally launched restricted to families owning up to 2 hectares. "
    "Effective 1 June 2019, this restriction was removed."
)


def _temporal_finding(retired_value, confidence=0.95, quote_ok=True):
    return JudgeFinding(
        category="temporal_supersession",
        description="d",
        source_quote="Effective 1 June 2019, this restriction was removed." if quote_ok else "totally fabricated sentence never in the doc",
        confidence=confidence,
        proposed_supersedes=ProposedSupersedes(
            retired_field="landholding_hectares", retired_op="<=", retired_value=retired_value,
            amendment_source_quote="Effective 1 June 2019, this restriction was removed.",
        ),
    )


def _predicate_finding(field="is_citizen", confidence=0.9, quote_ok=True, location="inclusion"):
    return JudgeFinding(
        category="preambular_implied_fact",
        description="d",
        source_quote="husband, wife, and minor children who own cultivable land" if quote_ok else "never said this anywhere",
        confidence=confidence,
        proposed_predicate=ProposedPredicate(location=location, cat="citizenship", field=field, op="==", value=True),
    )


def test_temporal_finding_with_literal_grounded_value_accepts():
    finding = _temporal_finding(retired_value=2, confidence=0.95)
    decision = evaluate_gate(finding, DOC_TEXT)
    assert decision.decision == "auto_accept"
    assert decision.signals["retired_value_literally_grounded"] is True


def test_temporal_finding_with_fabricated_boolean_value_defers():
    """The exact IGNOAPS shape: a real quote establishing change happened, but the specific
    retired_value (a boolean) is never literally stated — must defer regardless of confidence."""
    finding = _temporal_finding(retired_value=False, confidence=0.97)
    decision = evaluate_gate(finding, DOC_TEXT)
    assert decision.decision == "defer_to_review"
    assert decision.signals["retired_value_literally_grounded"] is False
    assert any("fabrication pattern" in r for r in decision.reasons)


def test_ellipsis_truncated_quote_still_counts_as_verbatim():
    """Real bug found during gate validation: the judge truncates long quotes with its own '...',
    which isn't literal fabrication — each side of the ellipsis just needs to independently
    appear in the document."""
    finding = _temporal_finding(retired_value=2, confidence=0.95)
    finding.source_quote = "The scheme was originally launched...Effective 1 June 2019, this restriction was removed."
    decision = evaluate_gate(finding, DOC_TEXT)
    assert decision.signals["quote_verbatim_in_source"] is True


def test_wholesale_fabricated_quote_with_ellipsis_still_defers():
    finding = _temporal_finding(retired_value=2, confidence=0.95)
    finding.source_quote = "This sentence never appeared...nor did this one, at all, anywhere in the document."
    decision = evaluate_gate(finding, DOC_TEXT)
    assert decision.signals["quote_verbatim_in_source"] is False


def test_fabricated_quote_defers_regardless_of_category():
    finding = _predicate_finding(quote_ok=False, confidence=0.99)
    decision = evaluate_gate(finding, DOC_TEXT)
    assert decision.decision == "defer_to_review"
    assert decision.signals["quote_verbatim_in_source"] is False


def test_temporal_finding_with_comma_formatted_value_accepts():
    """Real bug found during PMAY-G gate validation: 'up from Rs. 10,000' in the doc didn't match
    retired_value=10000, since '10000' never appears as a contiguous substring of '10,000' — a
    correct, well-grounded finding was wrongly deferred purely over thousands-separator commas,
    which are near-universal in Indian-English INR amounts."""
    doc = "The monthly income threshold was raised to Rs. 15,000 (up from Rs. 10,000)."
    finding = _temporal_finding(retired_value=10000, confidence=0.97)
    finding.source_quote = "raised to Rs. 15,000 (up from Rs. 10,000)"
    finding.proposed_supersedes.amendment_source_quote = finding.source_quote
    decision = evaluate_gate(finding, doc)
    assert decision.signals["retired_value_literally_grounded"] is True


def test_predicate_boolean_value_not_held_to_literal_grounding():
    """Non-temporal predicates aren't penalized for having a boolean value — only temporal
    supersedes claims get the strict literal-value check."""
    finding = _predicate_finding(confidence=0.9)
    decision = evaluate_gate(finding, DOC_TEXT)
    assert decision.decision == "auto_accept"
    assert "retired_value_literally_grounded" not in decision.signals


def test_temporal_stricter_threshold_than_predicate():
    """Same confidence (0.8) — predicate clears the base threshold, temporal doesn't clear the
    stricter one."""
    predicate = _predicate_finding(confidence=0.8)
    temporal = _temporal_finding(retired_value=2, confidence=0.8)
    assert evaluate_gate(predicate, DOC_TEXT).decision == "auto_accept"
    assert evaluate_gate(temporal, DOC_TEXT).decision == "defer_to_review"


def test_self_consistency_reproduced_does_not_raise_bar():
    finding = _predicate_finding(field="is_citizen", confidence=0.75)
    reproduced_sample = JudgeReport(findings=[_predicate_finding(field="is_citizen")])
    decision = evaluate_gate(finding, DOC_TEXT, repeated_samples=[reproduced_sample])
    assert decision.signals["self_consistent_across_samples"] is True
    assert decision.signals["threshold_used"] == 0.7
    assert decision.decision == "auto_accept"


def test_self_consistency_not_reproduced_raises_bar_but_does_not_hard_block():
    """A confidence that clears the base threshold but not the raised one must defer; one that
    clears even the raised bar still gets through — self-consistency adjusts, doesn't gate alone."""
    low = _predicate_finding(field="is_citizen", confidence=0.75)
    high = _predicate_finding(field="is_citizen", confidence=0.85)
    different_sample = JudgeReport(findings=[_predicate_finding(field="something_else")])

    low_decision = evaluate_gate(low, DOC_TEXT, repeated_samples=[different_sample])
    assert low_decision.signals["self_consistent_across_samples"] is False
    assert low_decision.signals["threshold_used"] == 0.8
    assert low_decision.decision == "defer_to_review"

    high_decision = evaluate_gate(high, DOC_TEXT, repeated_samples=[different_sample])
    assert high_decision.decision == "auto_accept"


def test_check_self_consistency_returns_none_without_samples():
    finding = _predicate_finding()
    assert check_self_consistency(finding, []) is None


def test_evaluate_gate_batch_preserves_order_and_count():
    findings = [_predicate_finding(field="a"), _temporal_finding(2), _predicate_finding(field="b", quote_ok=False)]
    decisions = evaluate_gate_batch(findings, DOC_TEXT)
    assert len(decisions) == 3
    assert [d.finding is f for d, f in zip(decisions, findings)] == [True, True, True]
    assert decisions[2].decision == "defer_to_review"


def test_every_decision_has_at_least_one_human_readable_reason():
    findings = [_predicate_finding(), _temporal_finding(False), _predicate_finding(quote_ok=False)]
    for decision in evaluate_gate_batch(findings, DOC_TEXT):
        assert len(decision.reasons) >= 1
        assert all(isinstance(r, str) and r for r in decision.reasons)


def test_auto_accept_always_carries_the_caveat():
    accepted = evaluate_gate(_predicate_finding(confidence=0.9), DOC_TEXT)
    assert accepted.decision == "auto_accept"
    assert accepted.caveat == AUTO_ACCEPT_CAVEAT
    assert "does NOT mean" in accepted.caveat


def test_deferred_decision_has_no_caveat():
    deferred = evaluate_gate(_predicate_finding(quote_ok=False), DOC_TEXT)
    assert deferred.decision == "defer_to_review"
    assert deferred.caveat is None


def test_gate_decision_to_dict_includes_caveat_field():
    accepted = evaluate_gate(_predicate_finding(confidence=0.9), DOC_TEXT)
    d = accepted.to_dict()
    assert d["caveat"] == AUTO_ACCEPT_CAVEAT
    assert d["decision"] == "auto_accept"


SCHEME = Scheme.model_validate(
    {
        "scheme_id": "TEST", "unit_of_eligibility": "individual",
        "inclusion": {"cat": "demographic", "field": "age", "op": ">=", "value": 18},
        "exclusions": [],
        "temporal_validity": {"valid_from": "2020-01-01", "extracted_at": "2026-01-01"},
        "extraction_metadata": {"confidence": 1.0, "source_clause": "t", "flagged_for_review": False},
    }
)


def test_apply_gate_approved_findings_only_merges_accepted():
    good = _predicate_finding(field="is_citizen", confidence=0.9)
    bad = _predicate_finding(field="is_wealthy", confidence=0.9, quote_ok=False)
    patched, decisions = apply_gate_approved_findings(SCHEME, [good, bad], DOC_TEXT)

    fields = {p.field for p in patched.inclusion.and_} if hasattr(patched.inclusion, "and_") else {patched.inclusion.field}
    assert "is_citizen" in fields
    assert "is_wealthy" not in fields
    assert len(decisions) == 2
    assert {d.decision for d in decisions} == {"auto_accept", "defer_to_review"}
