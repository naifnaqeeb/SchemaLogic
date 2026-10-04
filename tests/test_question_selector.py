from schemelogic.conversational.question_selector import (
    build_question,
    find_missing_fields,
    select_next_question,
)
from schemelogic.evaluator.symbolic_engine import evaluate
from schemelogic.schema.models import Scheme

SCHEME = Scheme.model_validate(
    {
        "scheme_id": "TEST",
        "unit_of_eligibility": "individual",
        "inclusion": {
            "and": [
                {"cat": "demographic", "field": "age", "op": ">=", "value": 18},
                {"cat": "citizenship", "field": "is_citizen", "op": "==", "value": True},
            ]
        },
        "exclusions": [
            {"cat": "economic", "quantifier": "self", "field": "is_wealthy", "op": "==", "value": True},
            {"cat": "political", "quantifier": "some_family_member", "field": "holds_office", "op": "==", "value": True},
        ],
        "temporal_validity": {"valid_from": "2020-01-01", "extracted_at": "2026-01-01"},
        "extraction_metadata": {"confidence": 1.0, "source_clause": "t", "flagged_for_review": False},
    }
)


def test_find_missing_fields_empty_profile_finds_inclusion_fields_first():
    result = evaluate(SCHEME, {"self": {}, "family_members": []})
    missing = find_missing_fields(result)
    fields = [m.field for m in missing]
    # inclusion tree walked before exclusions, left-to-right within the AND
    assert fields[0] == "age"
    assert fields[1] == "is_citizen"


def test_find_missing_fields_stops_asking_about_answered_fields():
    result = evaluate(SCHEME, {"self": {"age": 25}, "family_members": []})
    missing = find_missing_fields(result)
    assert "age" not in [m.field for m in missing]
    assert "is_citizen" in [m.field for m in missing]


def test_select_next_question_returns_first_missing_inclusion_field():
    q = select_next_question(SCHEME, {"self": {}, "family_members": []})
    assert q is not None
    assert q.field == "age"
    assert q.answer_type == "number"
    assert q.quick_replies is None


def test_boolean_field_gets_yes_no_quick_replies():
    q = select_next_question(SCHEME, {"self": {"age": 25}, "family_members": []})
    assert q is not None
    assert q.field == "is_citizen"
    assert q.answer_type == "boolean"
    assert q.quick_replies == ("Yes", "No")


def test_moves_to_exclusions_once_inclusion_resolved():
    profile = {"self": {"age": 25, "is_citizen": True}, "family_members": []}
    q = select_next_question(SCHEME, profile)
    assert q is not None
    assert q.field == "is_wealthy"


def test_returns_none_once_verdict_is_definite_eligible():
    # some_family_member quantifier includes "self" as a checkable member -- must be answered too.
    profile = {
        "self": {"age": 25, "is_citizen": True, "is_wealthy": False, "holds_office": False},
        "family_members": [],
    }
    q = select_next_question(SCHEME, profile)
    assert q is None


def test_returns_none_once_verdict_is_definite_ineligible():
    """Inclusion still partially unknown, but an exclusion already definitely fires -- verdict is
    already INELIGIBLE, so no more questions needed even though age/is_citizen are unanswered."""
    profile = {"self": {"is_wealthy": True}, "family_members": []}
    q = select_next_question(SCHEME, profile)
    assert q is None


def test_family_member_exclusion_produces_family_member_question():
    # self's own holds_office already answered -- only family_member[0]'s is left missing.
    profile = {
        "self": {"age": 25, "is_citizen": True, "is_wealthy": False, "holds_office": False},
        "family_members": [{}],
    }
    q = select_next_question(SCHEME, profile)
    assert q is not None
    assert q.field == "holds_office"
    assert q.member == "family_member[0]"
    assert "family member" in q.prompt


def test_build_question_prompt_is_grammatical_and_contains_description():
    from schemelogic.conversational.question_selector import MissingField

    q = build_question(MissingField(field="is_indian_citizen", member="self", cat="citizenship", expected_value=True))
    assert "you" in q.prompt
    assert q.answer_type == "boolean"


def test_unknown_field_falls_back_to_humanized_name():
    from schemelogic.conversational.question_selector import MissingField

    q = build_question(MissingField(field="some_made_up_field", member="self", cat=None, expected_value=True))
    assert "some made up field" in q.prompt


def test_known_field_uses_ontology_citizen_question_verbatim():
    """Part A's core guarantee: the primary chat question comes from citizen_question, never the
    technical `description` field."""
    from schemelogic.conversational.question_selector import MissingField
    from schemelogic.schema.field_ontology import get_field

    spec = get_field("is_secc_deprived_household")
    q = build_question(MissingField(field="is_secc_deprived_household", member="self", cat="economic", expected_value=True))
    assert q.prompt == spec.citizen_question
    assert "SECC" not in q.prompt  # the technical description's jargon must never leak through
    assert "D1" not in q.prompt


def test_family_member_question_uses_third_person_swap_of_real_ontology_text():
    from schemelogic.conversational.question_selector import MissingField

    q = build_question(MissingField(field="is_woman", member="family_member[0]", cat="demographic", expected_value=True))
    assert "Are they a woman?" in q.prompt
    assert "Are you" not in q.prompt


def test_second_to_third_person_handles_subject_object_and_possessive():
    from schemelogic.conversational.question_selector import _second_to_third_person

    assert _second_to_third_person("Are you a woman?") == "Are they a woman?"
    assert _second_to_third_person("Does your household own a refrigerator?") == "Does their household own a refrigerator?"
    assert _second_to_third_person("Is this for you?") == "Is this for them?"


# --- only ask what could still change the verdict ------------------------------------------------
# Under Kleene logic a node whose result is already True or False can't be changed by resolving the
# unknowns beneath it, so the selector descends only into UNDETERMINED nodes. Checked two ways: the
# exact PMMVY sequence that exposed the over-asking (KNOWN_ISSUES, 2026-10-03), and a brute-force
# relevance oracle over every gold scheme.

import copy  # noqa: E402
import itertools  # noqa: E402
import json  # noqa: E402
import random  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

from schemelogic.conversational.session import ConversationSession  # noqa: E402
from schemelogic.evaluator.symbolic_engine import Verdict  # noqa: E402

_ROOT = Path(__file__).resolve().parents[1]
_GOLD_IDS = sorted(p.stem for p in (_ROOT / "data" / "gold").glob("*.json"))


def _gold(sid: str) -> Scheme:
    return Scheme.model_validate_json((_ROOT / "data" / "gold" / f"{sid}.json").read_text(encoding="utf-8"))


def _profiles(sid: str) -> dict[str, dict]:
    raw = json.loads((_ROOT / "data" / "profiles" / f"{sid}.json").read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def _record(profile: dict, member: str) -> dict:
    return profile["self"] if member == "self" else profile["family_members"][int(member[len("family_member["):-1])]


def _drive(scheme: Scheme, answers: dict, limit: int = 40) -> tuple[list[str], Verdict]:
    """Run the real question loop, answering the applicant's questions from `answers`; an unanswerable
    question ends the run. Returns the questions asked, as 'member.field', and the final verdict."""
    session = ConversationSession(scheme=scheme)
    asked = []
    for _ in range(limit):
        q = session.advance()
        if q is None or q.member != "self" or q.field not in answers:
            break
        asked.append(f"{q.member}.{q.field}")
        session._member_dict(q.member)[q.field] = answers[q.field]
    return asked, session.current_result().verdict


def test_pmmvy_stops_asking_about_categories_once_one_is_satisfied():
    """The case that exposed it (2026-10-03): an SC/ST woman of 25 was then asked 9 questions about the
    other categories -- disability, BPL, AB-PMJAY, e-Shram, PM-KISAN, MGNREGA, income, frontline
    worker, NFSA -- before the one that still mattered, her child's birth order."""
    oracle = {"age": 25, "is_sc_st": True, "pregnancy_child_order": 1,
              # an answer exists for every other question, so over-asking shows up instead of stalling
              "has_40_percent_or_more_disability": False, "is_bpl_household": False,
              "is_ab_pmjay_beneficiary": False, "is_e_shram_registered": False, "is_pm_kisan_beneficiary": False,
              "has_active_mgnrega_job_card": False, "family_annual_income_inr": 900000,
              "is_frontline_worker": False, "is_nfsa_ration_card_holder": False, "child_is_girl": False,
              "months_since_last_birthday": 3}
    asked, verdict = _drive(_gold("PMMVY"), oracle)
    assert asked == ["self.age", "self.is_sc_st", "self.pregnancy_child_order"]
    assert verdict == Verdict.ELIGIBLE


def test_pmmvy_months_are_asked_only_of_an_eighteen_year_old():
    oracle = {"age": 18, "is_sc_st": True, "pregnancy_child_order": 1, "months_since_last_birthday": 9}
    asked, verdict = _drive(_gold("PMMVY"), oracle)
    assert asked == ["self.age", "self.is_sc_st", "self.pregnancy_child_order", "self.months_since_last_birthday"]
    assert verdict == Verdict.ELIGIBLE


def test_pmmvy_a_first_child_is_not_asked_the_childs_sex():
    asked, _ = _drive(_gold("PMMVY"), {"age": 30, "is_sc_st": True, "pregnancy_child_order": 1, "child_is_girl": True})
    assert "self.child_is_girl" not in asked
    asked, _ = _drive(_gold("PMMVY"), {"age": 30, "is_sc_st": True, "pregnancy_child_order": 2, "child_is_girl": True})
    assert asked[-1] == "self.child_is_girl"


def test_exclusions_waived_by_the_applicants_age_are_not_asked_about():
    """AB-PMJAY: a 72-year-old is covered whatever the household's socio-economic facts, so none of the
    14 exclusions -- all waived by the applicant's age -- generates a question."""
    scheme = _gold("AB-PMJAY")
    profile = {"self": {"age": 72}, "family_members": [{}, {}]}
    assert evaluate(scheme, profile).verdict == Verdict.ELIGIBLE
    assert select_next_question(scheme, profile) is None
    # route already met, age unknown: once the age is 70+, all 14 exclusions are waived at once
    profile = {"self": {"is_secc_deprived_household": True, "owns_refrigerator": True}, "family_members": [{}]}
    q = select_next_question(scheme, profile)
    assert (q.member, q.field) == ("self", "age")


def test_an_exception_is_not_asked_for_a_member_the_exclusion_does_not_reach():
    """PM-KISAN's Group D carve-out: a relative who is NOT a government employee can't trigger the
    exclusion, so whether they are Group D is irrelevant -- it used to be asked anyway."""
    scheme = Scheme.model_validate({**SCHEME.model_dump(mode="json", by_alias=True), "exclusions": [{
        "cat": "occupation", "quantifier": "some_family_member", "field": "is_govt_employee", "op": "==",
        "value": True, "except": {"field": "is_group_d", "op": "==", "value": True}}]})
    profile = {"self": {"age": 30, "is_citizen": True, "is_govt_employee": False},
               "family_members": [{"is_govt_employee": False}, {}]}
    asked = [(m.member, m.field) for m in find_missing_fields(evaluate(scheme, profile))]
    assert asked == [("family_member[1]", "is_govt_employee"), ("family_member[1]", "is_group_d")]


# Brute-force relevance oracle ---------------------------------------------------------------------


def _candidate_values(scheme: Scheme, field: str) -> list:
    """Values landing on each side of every predicate on `field` in this scheme."""
    values: set = set()

    def visit(pred):
        if pred.field != field:
            return
        v = pred.value
        if isinstance(v, bool):
            values.update((True, False))
        elif isinstance(v, (int, float)):
            values.update((v - 1, v, v + 1))
        elif isinstance(v, list):
            values.update(v)
            values.add("__other__")
        else:
            values.update((v, "__other__"))

    def walk(node):
        for key in ("and_", "or_"):
            children = getattr(node, key, None)
            if children is not None:
                for child in children:
                    walk(child)
                return
        visit(node)

    walk(scheme.inclusion)
    for excl in scheme.exclusions:
        visit(excl)
        if excl.except_ is not None:
            visit(excl.except_)
    return sorted(values, key=repr)


def _slots(result) -> list[tuple[str, str]]:
    """Every missing (member, field) the trace mentions anywhere, decided branches included."""
    out: list[tuple[str, str]] = []

    def inc(node):
        if node.get("type") == "predicate" and node.get("result") is None:
            out.append(("self", node["field"]))
        for child in node.get("children", []):
            inc(child)

    inc(result.trace["inclusion"])
    for excl in result.trace["exclusions"]:
        for row in excl.get("members", []):
            for key in ("predicate", "except"):
                if row.get(key) is not None and row[key].get("result") is None:
                    out.append((row["member"], row[key]["field"]))
        if excl.get("except") is not None and excl["except"].get("result") is None:
            out.append((excl.get("except_member", "self"), excl["except"]["field"]))
    return list(dict.fromkeys(out))


def _relevant(scheme: Scheme, profile: dict, slots: list, target: tuple) -> bool:
    """Could answering `target` change the verdict, for SOME answers to the other missing facts?"""
    others = [s for s in slots if s != target]
    for combo in itertools.product(*[_candidate_values(scheme, f) for _, f in others]):
        base = copy.deepcopy(profile)
        for (m, f), v in zip(others, combo):
            _record(base, m)[f] = v
        verdicts = set()
        for v in _candidate_values(scheme, target[1]):
            filled = copy.deepcopy(base)
            _record(filled, target[0])[target[1]] = v
            verdicts.add(evaluate(scheme, filled).verdict)
        if len(verdicts) > 1:
            return True
    return False


def _scheme_fields(scheme: Scheme) -> tuple[set[str], set[str]]:
    """(fields read from the applicant, fields read from family members)."""
    applicant: set[str] = set()
    family: set[str] = set()

    def walk(node):
        children = getattr(node, "and_", None) or getattr(node, "or_", None)
        if children is not None:
            for child in children:
                walk(child)
        else:
            applicant.add(node.field)

    walk(scheme.inclusion)
    for excl in scheme.exclusions:
        applicant.add(excl.field)
        if excl.except_ is not None:
            applicant.add(excl.except_.field)
        if excl.quantifier.value != "self":
            family.add(excl.field)
            if excl.except_ is not None and excl.except_scope.value == "member":
                family.add(excl.except_.field)
    return applicant, family


def _partial_profiles(sid: str, rng: random.Random, per_profile: int):
    """Each gold profile, completed with a random value for every fact the scheme reads (so the
    sparse ones don't leave too many unknowns to brute-force), then with 1-6 facts removed."""
    scheme = _gold(sid)
    applicant_fields, family_fields = _scheme_fields(scheme)
    for profile in _profiles(sid).values():
        for _ in range(per_profile):
            p = {"self": dict(profile.get("self", {})),
                 "family_members": [dict(m) for m in profile.get("family_members", [])] or [{}]}
            for f in applicant_fields:
                p["self"].setdefault(f, rng.choice(_candidate_values(scheme, f)))
            for member in p["family_members"]:
                for f in family_fields:
                    member.setdefault(f, rng.choice(_candidate_values(scheme, f)))
            facts = [("self", f) for f in p["self"]] + [
                (f"family_member[{i}]", f) for i, m in enumerate(p["family_members"]) for f in m]
            for member, field in rng.sample(facts, k=min(len(facts), rng.randint(1, 6))):
                _record(p, member).pop(field, None)
            yield p


@pytest.mark.parametrize("sid", _GOLD_IDS)
def test_every_question_could_change_the_verdict_and_none_that_could_is_withheld(sid):
    scheme, rng = _gold(sid), random.Random(sid)
    checked = 0
    for profile in _partial_profiles(sid, rng, per_profile=12):
        result = evaluate(scheme, profile)
        if result.verdict != Verdict.UNDETERMINED:
            continue
        slots = _slots(result)
        if len(slots) > 6:
            continue
        offered = {(m.member, m.field) for m in find_missing_fields(result)}
        relevant = {s for s in slots if _relevant(scheme, profile, slots, s)}
        question = select_next_question(scheme, profile)
        assert (question.member, question.field) in relevant, ("asked an irrelevant question", profile, question)
        assert relevant <= offered, ("withheld a relevant question", relevant - offered, profile)
        checked += 1
    assert checked >= 5, checked
