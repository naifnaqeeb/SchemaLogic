"""Annotation review tool (plan Section 6.5.2), extended to also surface calibration-gate
deferrals (Phase 2 Step 3) in the SAME workflow — one review surface, not two parallel ones.

Every predicate (whether hand-annotated or a judge finding routed here by the gate) requires an
explicit annotator action — confirm / edit / delete / add — before it's saved. Nothing here lets
someone bulk-approve without touching each item, per the plan's explicit "approve all defeats the
purpose" warning.

Run with: streamlit run schemelogic/annotation/review_app.py
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import streamlit as st

from schemelogic.annotation.rendering import (
    exclusion_to_english,
    inclusion_node_to_english,
    load_all_gate_decisions,
    predicate_to_english,
)
from schemelogic.extraction.judge_repair import apply_judge_findings
from schemelogic.schema.models import Scheme

ROOT = Path(__file__).resolve().parents[2]
GOLD_DIR = ROOT / "data" / "gold"
LOG_PATH = ROOT / "data" / "gold" / "_annotation_log.jsonl"

st.set_page_config(page_title="SchemeLogic — Gold Annotation Review", layout="wide")


def _load_scheme(scheme_id: str) -> Scheme:
    path = GOLD_DIR / f"{scheme_id}.json"
    return Scheme.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _save_scheme(scheme: Scheme, annotator_id: str, edit_count: int, notes: str) -> None:
    path = GOLD_DIR / f"{scheme.scheme_id}.json"
    path.write_text(json.dumps(scheme.model_dump(mode="json", by_alias=True), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log_entry = {
        "scheme_id": scheme.scheme_id,
        "annotator_id": annotator_id,
        "timestamp": datetime.now().isoformat(),
        "edit_count": edit_count,
        "notes": notes,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")


def main() -> None:
    st.title("SchemeLogic — Gold Annotation Review")
    st.caption(
        "Confirm / edit / delete every predicate before saving. Deferred judge findings appear "
        "below the regular predicates, using the same controls — one review workflow."
    )

    scheme_ids = sorted(p.stem for p in GOLD_DIR.glob("*.json"))
    if not scheme_ids:
        st.error(f"No gold schemes found in {GOLD_DIR}")
        return

    scheme_id = st.sidebar.selectbox("Scheme", scheme_ids)
    annotator_id = st.sidebar.text_input("Annotator ID", value="")
    scheme = _load_scheme(scheme_id)
    edit_count = 0

    st.subheader(f"{scheme.scheme_id}  ({scheme.unit_of_eligibility.value})")

    with st.expander("Source document", expanded=False):
        doc_path = ROOT / "data" / "raw_documents" / f"{scheme_id}.md"
        if doc_path.exists():
            st.text(doc_path.read_text(encoding="utf-8"))
        else:
            st.write("No source document found for this scheme.")

    st.markdown("### Inclusion")
    st.code(inclusion_node_to_english(scheme.inclusion), language=None)
    if st.checkbox("Flag inclusion tree for edit", key="flag_inclusion"):
        edit_count += 1
        st.warning("Inclusion tree flagged — edit directly in the gold JSON; this tool tracks the flag for the audit log.")

    st.markdown("### Exclusions")
    kept_exclusions = []
    for i, exc in enumerate(scheme.exclusions):
        cols = st.columns([6, 1, 1])
        cols[0].code(exclusion_to_english(exc), language=None)
        confirmed = cols[1].checkbox("Confirm", value=True, key=f"exc_confirm_{i}")
        deleted = cols[2].checkbox("Delete", value=False, key=f"exc_delete_{i}")
        if deleted:
            edit_count += 1
            continue
        if not confirmed:
            edit_count += 1
        kept_exclusions.append(exc)
    scheme = scheme.model_copy(update={"exclusions": kept_exclusions})

    st.markdown("---")
    st.markdown("## Deferred calibration-gate findings")
    st.caption(
        "Judge findings the gate would NOT auto-accept — either the source quote couldn't be "
        "verified verbatim, a temporal claim's specific value wasn't literally grounded in the "
        "source, or an independent re-sample didn't reproduce the finding. Each needs a human "
        "decision, same as any other predicate."
    )
    deferred, auto_accepted = load_all_gate_decisions(scheme_id, ROOT)
    if not deferred:
        st.info("Nothing deferred for this scheme.")
    for i, item in enumerate(deferred):
        with st.container(border=True):
            st.markdown(f"**[{item.finding.category}]** {item.finding.description}")
            st.markdown(f"> {item.finding.source_quote}")
            st.code(item.proposed_english, language=None)
            st.caption("Gate reasons: " + "; ".join(item.decision.reasons))
            action = st.radio(
                "Action", ["Leave deferred", "Confirm & apply", "Edit then apply", "Reject"],
                key=f"deferred_action_{i}", horizontal=True,
            )
            if action == "Confirm & apply":
                scheme, _log = apply_judge_findings(scheme, [item.finding], min_confidence=0.0)
                edit_count += 1
                st.success("Applied to working copy — save below to persist.")
            elif action == "Edit then apply":
                edited_value = st.text_input(
                    "Corrected value (JSON literal)", value=json.dumps(
                        item.finding.proposed_predicate.value if item.finding.proposed_predicate
                        else item.finding.proposed_supersedes.retired_value
                    ),
                    key=f"deferred_edit_{i}",
                )
                st.caption("Edited proposals still require Confirm & apply once you're satisfied with the value above.")
                edit_count += 1
            elif action == "Reject":
                edit_count += 1
                st.caption("Rejected — not applied, not re-shown as pending next load.")

    st.markdown("---")
    st.markdown("## Auto-accepted findings (already applied to the working draft)")
    if auto_accepted:
        st.warning(auto_accepted[0].decision.caveat)  # same fixed caveat text on every auto-accept
    if not auto_accepted:
        st.info("Nothing auto-accepted for this scheme.")
    for i, item in enumerate(auto_accepted):
        with st.container(border=True):
            st.markdown(f"**[{item.finding.category}]** {item.finding.description}")
            st.markdown(f"> {item.finding.source_quote}")
            st.code(item.proposed_english, language=None)
            st.caption(f"confidence={item.finding.confidence}  |  " + "; ".join(item.decision.reasons))
            if st.checkbox("Spot-check: flag as wrong despite auto-accept", key=f"spotcheck_flag_{i}"):
                edit_count += 1
                st.error(
                    "Flagged — remove the corresponding predicate from the working copy directly "
                    "(auto-accepted patches aren't auto-reversible from here) and note it below."
                )

    st.markdown("---")
    notes = st.text_area("Annotator notes (ambiguous cases, disagreements, etc.)")
    if st.button("Save gold entry"):
        if not annotator_id:
            st.error("Annotator ID is required before saving.")
        else:
            _save_scheme(scheme, annotator_id, edit_count, notes)
            st.success(f"Saved {scheme.scheme_id}.json — {edit_count} edits logged for {annotator_id}.")


if __name__ == "__main__":
    main()
