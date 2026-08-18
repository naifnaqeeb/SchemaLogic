"""Calibration / deferral gate (Phase 2, plan Section 6.4 / Section 8 Phase 2 item 3).

Sits between judge/repair output and the live gold-set rule store. Every JudgeFinding gets
either auto-accepted or deferred to human review — never silently applied without a decision,
and never silently dropped either (a deferred finding still needs a human answer).

Deliberately NOT a learned/black-box confidence score. Built from three signals the Phase 2
validation run gave concrete evidence for:

1. Source-quote groundedness — is the finding's source_quote actually verbatim in the document
   (catches wholesale fabrication), and — for temporal_supersession findings specifically — is
   the proposed retired_value itself literally present in the source (catches IGNOAPS's failure
   mode exactly: a real quote establishing THAT something changed, stretched into a specific
   prior-rule VALUE the document never actually states). This check is deliberately NOT applied
   to ordinary predicate findings' boolean values — "value: true" is never literally quoted in
   prose, so holding predicates to the same bar as supersedes claims would just defer everything.
2. Self-consistency across independent judge samples for the same finding, when available —
   optional, since it needs more than one sample (either repeated judge calls, or if unavailable,
   the decision proceeds without this signal rather than blocking on it).
3. Category-based risk weighting — temporal_supersession claims use a stricter acceptance bar
   than plain predicate additions, since that's specifically where fabrication was observed.

Every decision carries human-readable reasons, not just a boolean — the point is a defensible
audit trail, not a score.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from schemelogic.extraction.judge_repair import JudgeFinding, JudgeReport

BASE_CONFIDENCE_THRESHOLD = 0.7
TEMPORAL_CONFIDENCE_THRESHOLD = 0.9

_WORD_TO_NUM = {
    w: n
    for n, w in enumerate(
        [
            "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
            "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
            "eighteen", "nineteen", "twenty",
        ]
    )
}
for _tens_word, _tens_val in [("thirty", 30), ("forty", 40), ("fifty", 50), ("sixty", 60),
                               ("seventy", 70), ("eighty", 80), ("ninety", 90), ("hundred", 100)]:
    _WORD_TO_NUM[_tens_word] = _tens_val


def _normalize(text: str) -> str:
    text = text.lower()
    text = text.replace("‑", "-").replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


_ELLIPSIS_RE = re.compile(r"\.\.\.+|…")
_MIN_SEGMENT_LEN = 15  # ignore tiny fragments an ellipsis-split could leave behind


def _quote_is_verbatim(quote: str, document_text: str) -> bool:
    """Verbatim-substring check, tolerant of the judge truncating a long quote with its own
    '...' — that's the model shortening what it copies, not fabricating text, and treating it as
    equivalent to full fabrication was a real false-defer found during gate validation (a genuine
    PM-KISAN supersedes finding, otherwise well-grounded, got wrongly deferred over this alone).
    Splits on any ellipsis and requires each non-trivial segment to appear verbatim — segments
    don't need to be contiguous, since the judge may have elided material in between.

    KNOWN ISSUE (see KNOWN_ISSUES.md): markdown `**bold**` markers in source docs can split a
    genuine quote and fail this check, since `_normalize()` doesn't strip markdown syntax. Hasn't
    flipped a gate decision yet (AB-PMJAY, 2026-08-18) but is a latent false-defer risk. Deferred,
    not fixed."""
    if not quote:
        return False
    normalized_doc = _normalize(document_text)
    segments = [s.strip() for s in _ELLIPSIS_RE.split(_normalize(quote))]
    segments = [s for s in segments if len(s) >= _MIN_SEGMENT_LEN]
    if not segments:
        return _normalize(quote) in normalized_doc
    return all(s in normalized_doc for s in segments)


def _value_is_literally_grounded(value: Any, document_text: str) -> bool:
    """Only meaningful for concrete, literally-quotable values (numbers, short strings). Booleans
    are never literally 'quoted' in prose ('true'/'false' appearing is essentially always
    coincidental), so they're treated as inherently ungrounded — which is exactly the shape of
    the IGNOAPS fabrication (retired_value=False, invented rather than stated)."""
    if isinstance(value, bool):
        return False
    normalized_doc = _normalize(document_text)
    if isinstance(value, (int, float)):
        digit_form = str(int(value)) if float(value).is_integer() else str(value)
        # Indian-English INR amounts are near-universally comma-grouped ("Rs. 10,000"). Strip
        # commas from a *copy* of the document text for this check only — found via PMAY-G's
        # monthly_income_inr supersedes finding (retired_value=10000) being wrongly deferred
        # despite the document literally stating "raised to Rs. 15,000 (up from Rs. 10,000)",
        # because "10000" never appears as a contiguous substring of "...up from rs. 10,000)".
        if digit_form in normalized_doc or digit_form in normalized_doc.replace(",", ""):
            return True
        word_form = next((w for w, n in _WORD_TO_NUM.items() if n == value), None)
        return word_form is not None and word_form in normalized_doc
    return _normalize(str(value)) in normalized_doc


def _finding_target_key(finding: JudgeFinding) -> str | None:
    """The specific claim being made, used to match a finding against an independent re-sample."""
    if finding.category == "temporal_supersession" and finding.proposed_supersedes:
        return f"supersedes:{finding.proposed_supersedes.retired_field}"
    if finding.category == "preambular_implied_fact" and finding.proposed_predicate:
        return f"predicate:{finding.proposed_predicate.field}"
    return None


def check_self_consistency(finding: JudgeFinding, repeated_samples: list[JudgeReport]) -> bool | None:
    """Did independent re-samples reproduce this same specific claim? None if no samples given —
    self-consistency is an optional signal, not a required one."""
    target = _finding_target_key(finding)
    if target is None or not repeated_samples:
        return None
    for sample in repeated_samples:
        for other in sample.findings:
            if _finding_target_key(other) == target:
                return True
    return False


AUTO_ACCEPT_CAVEAT = (
    "AUTO-ACCEPT means this finding passed the fabrication/groundedness checks — it does NOT mean "
    "the predicate was verified correct. Confirmed false-accept shape at validation time: "
    "plausible-sounding but incoherent or redundant predicates (a real, verbatim-quoted source "
    "sentence stretched into an unwarranted or nonsensical predicate). Keep this visible wherever "
    "auto-accept decisions are logged or reviewed — do not flatten it into a bare 'gate said fine'."
)


@dataclass
class GateDecision:
    decision: str  # "auto_accept" | "defer_to_review"
    reasons: list[str]
    signals: dict[str, Any]
    finding: JudgeFinding = field(repr=False)
    caveat: str | None = None

    def __post_init__(self) -> None:
        if self.decision == "auto_accept" and self.caveat is None:
            self.caveat = AUTO_ACCEPT_CAVEAT

    @property
    def auto_accepted(self) -> bool:
        return self.decision == "auto_accept"

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "reasons": self.reasons,
            "signals": self.signals,
            "caveat": self.caveat,
            "finding_category": self.finding.category,
            "finding_description": self.finding.description,
        }


def evaluate_gate(
    finding: JudgeFinding,
    document_text: str,
    repeated_samples: list[JudgeReport] | None = None,
) -> GateDecision:
    reasons: list[str] = []
    signals: dict[str, Any] = {}
    is_temporal = finding.category == "temporal_supersession"

    quote_verbatim = _quote_is_verbatim(finding.source_quote, document_text)
    signals["quote_verbatim_in_source"] = quote_verbatim
    if not quote_verbatim:
        reasons.append("source_quote is not found verbatim in the document — possible fabricated citation")

    value_grounded: bool | None = None
    if is_temporal and finding.proposed_supersedes:
        value_grounded = _value_is_literally_grounded(finding.proposed_supersedes.retired_value, document_text)
        signals["retired_value_literally_grounded"] = value_grounded
        if not value_grounded:
            reasons.append(
                f"temporal claim's retired_value={finding.proposed_supersedes.retired_value!r} does not "
                "appear literally in the source — the document may establish that something changed "
                "without stating what the prior value was; this is exactly IGNOAPS's fabrication pattern"
            )

    # Self-consistency is deliberately a SOFT signal, not a hard gate — validated empirically, not
    # assumed. A real second independent sample showed it's noisy at n=1: it would have wrongly
    # deferred a genuinely correct MH-LADKI-BAHIN finding (is_woman) just because one extra sample
    # phrased something else instead, while IGNOAPS's fabricated supersedes value was reproduced
    # IDENTICALLY across both samples — consistency alone would have scored that fabrication
    # *higher* confidence, not lower. It still adjusts the bar (stricter threshold), it just can't
    # unilaterally force a defer the way source-quote groundedness can.
    consistent = check_self_consistency(finding, repeated_samples or [])
    signals["self_consistent_across_samples"] = consistent
    if consistent is False:
        reasons.append(
            "an independent re-sample of the judge did not reproduce this specific finding — "
            "raises the acceptance bar but does not block on its own (see module docstring)"
        )

    threshold = TEMPORAL_CONFIDENCE_THRESHOLD if is_temporal else BASE_CONFIDENCE_THRESHOLD
    if consistent is False:
        threshold = round(threshold + 0.1, 2)
    signals["confidence"] = finding.confidence
    signals["threshold_used"] = threshold
    below_threshold = finding.confidence < threshold
    if below_threshold:
        reasons.append(
            f"confidence {finding.confidence} below the "
            f"{'stricter temporal-claim' if is_temporal else 'base'} threshold {threshold}"
        )

    hard_fail = (not quote_verbatim) or (is_temporal and value_grounded is False)
    decision = "defer_to_review" if (hard_fail or below_threshold) else "auto_accept"

    if decision == "auto_accept" and not reasons:
        reasons.append("source quote verbatim, confidence above threshold, no contradicting signals")

    return GateDecision(decision=decision, reasons=reasons, signals=signals, finding=finding)


def evaluate_gate_batch(
    findings: list[JudgeFinding],
    document_text: str,
    repeated_samples: list[JudgeReport] | None = None,
) -> list[GateDecision]:
    return [evaluate_gate(f, document_text, repeated_samples) for f in findings]


def apply_gate_approved_findings(
    scheme: "Scheme",
    findings: list[JudgeFinding],
    document_text: str,
    repeated_samples: list[JudgeReport] | None = None,
) -> tuple["Scheme", list[GateDecision]]:
    """The gate as the real accept/defer mechanism for the pipeline (Section 6.4): only findings
    the gate auto-accepts get merged into the returned scheme, via judge_repair's own targeted
    patch-application logic (reused, not reimplemented). Deferred findings are returned in the
    decision list — untouched, unmerged, routed to the review tool — never silently applied and
    never silently dropped."""
    from schemelogic.extraction.judge_repair import apply_judge_findings

    decisions = evaluate_gate_batch(findings, document_text, repeated_samples)
    approved = [d.finding for d in decisions if d.auto_accepted]
    patched_scheme, _log = apply_judge_findings(scheme, approved, min_confidence=0.0)
    return patched_scheme, decisions
