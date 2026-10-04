"""Pure rendering/loading helpers for the annotation review tool (Section 6.5.2), kept separate
from the Streamlit UI (review_app.py) so they're unit-testable without a browser.

Renders the predicate tree as readable English-ish statements ("EXCLUDE if some family member
paid_income_tax_last_assessment_year == True") rather than raw JSON, per the plan's explicit
requirement — an annotator approving raw JSON without reading it defeats the point of review.
"""

from __future__ import annotations

import glob
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from schemelogic.deferral.calibration_gate import GateDecision, evaluate_gate
from schemelogic.extraction.judge_repair import JudgeFinding, JudgeReport
from schemelogic.schema.field_ontology import display_label_for
from schemelogic.schema.models import AndNode, Exclusion, OrNode, Predicate, Scheme


def _field_words(field: str) -> str:
    return field.replace("_", " ")


def predicate_to_english(pred: Predicate) -> str:
    op_words = {"==": "is", "!=": "is not", "<": "<", "<=": "<=", ">": ">", ">=": ">=", "in": "is one of", "not_in": "is not one of"}
    op = pred.op.value if hasattr(pred.op, "value") else pred.op
    return f"{_field_words(pred.field)} {op_words.get(op, op)} {pred.value!r} [{pred.cat.value if hasattr(pred.cat, 'value') else pred.cat}]"


def inclusion_node_to_english(node: Any, indent: int = 0) -> str:
    pad = "  " * indent
    if isinstance(node, Predicate):
        return f"{pad}- {predicate_to_english(node)}"
    if isinstance(node, AndNode):
        lines = [f"{pad}ALL of:"]
        lines += [inclusion_node_to_english(c, indent + 1) for c in node.and_]
        return "\n".join(lines)
    if isinstance(node, OrNode):
        lines = [f"{pad}ANY of:"]
        lines += [inclusion_node_to_english(c, indent + 1) for c in node.or_]
        return "\n".join(lines)
    return f"{pad}<unrecognized node>"


_QUANTIFIER_PHRASE = {
    "self": "the applicant",
    "some_family_member": "some family member",
    "all_family_members": "all family members",
    "count_family_members": "the count of family members matching",
}


def exclusion_to_english(exc: Exclusion) -> str:
    quantifier = exc.quantifier.value if hasattr(exc.quantifier, "value") else exc.quantifier
    who = _QUANTIFIER_PHRASE.get(quantifier, quantifier)
    line = f"EXCLUDE if {who}: {predicate_to_english(exc)}"
    if exc.count_op is not None:
        count_op = exc.count_op.value if hasattr(exc.count_op, "value") else exc.count_op
        line += f" (count {count_op} {exc.count})"
    if exc.except_ is not None:
        scope = exc.except_scope.value if hasattr(exc.except_scope, "value") else exc.except_scope
        whose = "the applicant's record" if scope == "applicant" else "same member"
        line += f"\n    EXCEPT if {whose}: {_field_words(exc.except_.field)} is {exc.except_.value!r}"
    return line


def _trace_node_to_citizen_lines(node: dict[str, Any], lines: list[str], depth: int = 0) -> None:
    """Citizen-facing rendering of a symbolic_engine.evaluate() TRACE node (has `result`/`actual`
    per predicate — not the static predicate-tree scheme_to_english renders above). Uses
    display_label_for(), never the raw snake_case field name — that stays in the technical view
    only (predicate_to_english / inclusion_node_to_english, above)."""
    indent = "  " * depth
    node_type = node.get("type")
    if node_type == "predicate":
        result = node.get("result")
        mark = "Yes ✅" if result is True else ("No ❌" if result is False else "Not yet known ❓")
        lines.append(f"{indent}- {display_label_for(node['field'])}: {mark}")
    elif node_type in ("and", "or"):
        connector = "All of these need to be true" if node_type == "and" else "At least one of these needs to be true"
        lines.append(f"{indent}- {connector}:")
        for child in node.get("children", []):
            _trace_node_to_citizen_lines(child, lines, depth + 1)


def trace_to_citizen_english(trace: dict[str, Any]) -> str:
    """Full citizen-facing rendering of an evaluate() result's trace dict — inclusion criteria
    plus exclusions, every field shown via display_label_for(), never the raw field name and
    never the technical description/source_clause. This is the MAIN "why" view the conversational
    app shows inline; scheme_to_english/predicate_to_english (above) are the technical/annotator
    view, reachable only from a separate "technical detail" expander in the UI, never inline
    alongside this."""
    lines: list[str] = ["What we checked to reach this result:", ""]
    _trace_node_to_citizen_lines(trace["inclusion"], lines)
    exclusions = trace.get("exclusions") or []
    if exclusions:
        lines.append("")
        lines.append("Things that would disqualify you:")
        for excl in exclusions:
            result = excl.get("result")
            if result is True:
                mark = "Applies to you 🚫"
            elif result is False and _was_waived(excl):
                # The disqualifying fact IS true, but an exception sets it aside (e.g. AB-PMJAY's
                # 70+ route, PM-KISAN's Group D carve-out). "Doesn't apply" would tell a 70+ senior
                # who owns a refrigerator that they don't own one.
                mark = "True for you, but waived by an exception ✅"
            elif result is False:
                mark = "Doesn't apply ✅"
            else:
                mark = "Not yet known ❓"
            lines.append(f"- {display_label_for(excl['field'])}: {mark}")
    return "\n".join(lines)


def _was_waived(excl_trace: dict[str, Any]) -> bool:
    """The disqualifying condition held and an exception set it aside -- either for a member
    (member-scoped exception, recorded per member row) or for the whole exclusion (applicant-scoped
    exception, recorded once at exclusion level with the pre-waiver `condition_result`)."""
    if excl_trace.get("condition_result") is True and (excl_trace.get("except") or {}).get("result") is True:
        return True
    return any(
        (m.get("predicate") or {}).get("result") is True and (m.get("except") or {}).get("result") is True
        for m in excl_trace.get("members", [])
    )


def scheme_to_english(scheme: Scheme) -> str:
    lines = [f"Scheme: {scheme.scheme_id} ({scheme.unit_of_eligibility.value})", "", "INCLUSION (must satisfy):"]
    lines.append(inclusion_node_to_english(scheme.inclusion, indent=1))
    lines.append("")
    lines.append("EXCLUSIONS (any one disqualifies):")
    for i, exc in enumerate(scheme.exclusions):
        lines.append(f"  [{i}] {exclusion_to_english(exc)}")
    return "\n".join(lines)


@dataclass
class DeferredReviewItem:
    scheme_id: str
    finding: JudgeFinding
    decision: GateDecision
    proposed_english: str


def _latest(pattern: str) -> Path | None:
    matches = sorted(glob.glob(pattern))
    return Path(matches[-1]) if matches else None


def _proposed_english(finding: JudgeFinding) -> str:
    if finding.category == "temporal_supersession" and finding.proposed_supersedes:
        ps = finding.proposed_supersedes
        op = ps.retired_op.value if hasattr(ps.retired_op, "value") else ps.retired_op
        return f"RETIRE: {ps.retired_field} {op} {ps.retired_value!r}  (amendment: \"{ps.amendment_source_quote}\")"
    if finding.proposed_predicate:
        p = finding.proposed_predicate
        op = p.op.value if hasattr(p.op, "value") else p.op
        cat = p.cat.value if hasattr(p.cat, "value") else p.cat
        return f"ADD to {p.location}: {_field_words(p.field)} {op} {p.value!r} [{cat}]"
    return "(no concrete proposal)"


def load_all_gate_decisions(scheme_id: str, root: Path) -> tuple[list[DeferredReviewItem], list[DeferredReviewItem]]:
    """Re-derives gate decisions fresh from the logged judge_repair run for scheme_id (not
    cached) so the review queue always reflects the current gate logic, not a stale snapshot.
    Returns (deferred_items, auto_accepted_items) — auto-accepted items still get shown in the
    review tool, carrying their caveat, per Section 6.4 Step 2: auto-accept must stay visibly
    distinct from verified, not get flattened into silence."""
    jr_path = _latest(str(root / "data" / "extraction_runs" / f"{scheme_id}_gpt-oss-120b_judge_repair_*.json"))
    if jr_path is None:
        return [], []
    jr = json.loads(jr_path.read_text(encoding="utf-8"))

    doc_path = root / "data" / "raw_documents" / f"{scheme_id}.md"
    if not doc_path.exists():
        return [], []
    doc_text = doc_path.read_text(encoding="utf-8")

    sample2_path = _latest(str(root / "data" / "extraction_runs" / f"{scheme_id}_gpt-oss-120b_judge_sample2_*.json"))
    repeated_samples = []
    if sample2_path is not None:
        sample2 = json.loads(sample2_path.read_text(encoding="utf-8"))
        repeated_samples = [JudgeReport.model_validate({"findings": sample2["findings"]})]

    deferred: list[DeferredReviewItem] = []
    auto_accepted: list[DeferredReviewItem] = []
    for pass_entry in jr.get("judge_passes", []):
        for finding_dict in pass_entry.get("findings", []):
            finding = JudgeReport.model_validate({"findings": [finding_dict]}).findings[0]
            decision = evaluate_gate(finding, doc_text, repeated_samples=repeated_samples)
            item = DeferredReviewItem(
                scheme_id=scheme_id, finding=finding, decision=decision, proposed_english=_proposed_english(finding)
            )
            (auto_accepted if decision.auto_accepted else deferred).append(item)
    return deferred, auto_accepted


def load_deferred_findings(scheme_id: str, root: Path) -> list[DeferredReviewItem]:
    """Back-compat convenience wrapper — deferred items only."""
    deferred, _auto_accepted = load_all_gate_decisions(scheme_id, root)
    return deferred
