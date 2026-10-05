"""Scoring of the gate re-validation (scripts/analyze_gate_revalidation.py), on fake judge results."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("analyze_gate_revalidation", ROOT / "scripts" / "analyze_gate_revalidation.py")
ga = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ga)

GOLD = ga.harness.frozen_gold("IGNOAPS").model_dump(mode="json", by_alias=True)
DROPPED = {"error_id": "X#01", "scheme_id": "IGNOAPS", "kind": "dropped_predicate", "location": "inclusion.and[0]",
           "before": {"field": "age", "op": ">=", "value": 60}, "after": None, "description": "removed age >= 60"}


def _result(field, decision, op=">=", value=60):
    return {"findings": [{"category": "preambular_implied_fact", "proposed_predicate": {"field": field, "op": op, "value": value}}],
            "gate_decisions": [{"decision": decision, "reasons": ["r"]}]}


def test_outcomes():
    assert ga.judge_outcome(DROPPED, None, GOLD)["outcome"] == "not_run"
    assert ga.judge_outcome(DROPPED, {"judge_failure": {"reason": "api_error"}}, GOLD)["outcome"] == "judge_failed"
    assert ga.judge_outcome(DROPPED, {"findings": [], "gate_decisions": []}, GOLD)["outcome"] == "missed"
    assert ga.judge_outcome(DROPPED, _result("age", "defer_to_review"), GOLD)["outcome"] == "flagged"
    assert ga.judge_outcome(DROPPED, _result("age", "auto_accept"), GOLD)["outcome"] == "corrected"
    assert ga.judge_outcome(DROPPED, _result("age", "auto_accept", value=65), GOLD)["outcome"] == "wrong_fix"
    assert ga.judge_outcome(DROPPED, _result("is_bpl_household", "auto_accept"), GOLD)["outcome"] == "missed"


def test_groups_never_pool_the_judges_design_with_present_but_wrong_rules():
    assert set(ga.GROUPS["A_judge_design"]).isdisjoint(ga.GROUPS["C_outside_design"])
    md = ga.markdown(ga.analyze())
    assert md.index("## A.") < md.index("## B.") < md.index("## C.")
    assert "never pooled into one catch rate" in md


def test_each_present_error_is_attributed_to_its_own_type():
    points, _ = ga.agreement_points(ga.load_candidates())
    kinds = {p["kind"] for p in points if p["error"] and not p.get("missing")}
    assert kinds <= set(ga.GROUPS["C_outside_design"])
