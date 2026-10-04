"""A fact a scheme checks for the whole family must be asked of the applicant FOR the household.

The chat stores the applicant's answers on their own record and fills in relatives only if the citizen
describes them, so a family-wide rule ("any member of the household earning more than Rs 10,000") is
only ever answered by the applicant's own answer. Asked "What is your monthly pension?", a farmer whose
wife draws a Rs 20,000 pension says 0 and is told eligible. Found 2026-10-04 (finding 7 of the second
except_scope review) for monthly_income_inr, monthly_pension_inr and is_nri_per_income_tax_act_1961.

The guard below holds every gold scheme, every cached AI-Checked scheme and a synthetic AI-Checked
scheme through the real phrasing step to it. LLM calls are mocked; no quota is touched.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from schemelogic.conversational import field_phrasing
from schemelogic.conversational.question_selector import MissingField, build_question, family_wide_fields
from schemelogic.llm.provider import ProviderFailure, ProviderResult
from schemelogic.schema import field_ontology
from schemelogic.schema.field_ontology import is_household_phrased
from schemelogic.schema.models import Quantifier, Scheme

ROOT = Path(__file__).resolve().parents[1]
GOLD = {p.stem: Scheme.model_validate_json(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "data" / "gold").glob("*.json"))}
AI_CHECKED = {p.stem: Scheme.model_validate_json(p.read_text(encoding="utf-8"))
              for p in sorted((ROOT / "data" / "cache" / "ai_checked").glob("*.json"))}


@pytest.fixture(autouse=True)
def _isolated_phrasing(tmp_path, monkeypatch):
    monkeypatch.setattr(field_phrasing, "DISK_CACHE_PATH", tmp_path / "field_questions.json")
    field_ontology.clear_registered_citizen_questions()
    yield
    field_ontology.clear_registered_citizen_questions()


def _applicant_question(scheme: Scheme, field: str) -> str:
    expected = next(e.value for e in scheme.exclusions if e.field == field)
    return build_question(MissingField(field=field, member="self", cat=None, expected_value=expected), scheme).prompt


def _family_exclusion_fields(scheme: Scheme) -> set[str]:
    return {e.field for e in scheme.exclusions if e.quantifier != Quantifier.SELF}


@pytest.mark.parametrize("sid", sorted({**GOLD, **AI_CHECKED}))
def test_every_family_wide_exclusion_is_asked_of_the_applicant_for_the_household(sid):
    scheme = GOLD.get(sid) or AI_CHECKED[sid]
    for field in _family_exclusion_fields(scheme):
        # a family-wide field must not ALSO be read for the applicant alone, or the household answer
        # stored on the applicant's record would leak into that applicant-only rule
        assert field in family_wide_fields(scheme), (sid, field, "also used for the applicant alone")
        question = _applicant_question(scheme, field)
        assert is_household_phrased(question), (sid, field, question)


@pytest.mark.parametrize("sid", sorted(GOLD))
def test_numeric_household_questions_ask_for_the_highest_value_only_where_that_is_exact(sid):
    """'The highest monthly pension among them' answers 'does ANY member draw more than X' exactly --
    and nothing else (not 'all members', not a count, not 'less than')."""
    for e in GOLD[sid].exclusions:
        spec = field_ontology.get_field(e.field)
        if spec is not None and spec.household_question and spec.value_type == "number":
            assert e.quantifier == Quantifier.SOME_FAMILY_MEMBER and e.op.value in (">", ">="), (sid, e.field)


@pytest.mark.parametrize("sid,field,must_mention", [
    ("PM-KISAN", "monthly_pension_inr", ("husband or wife", "minor children")),  # Para 3's family
    ("PM-KISAN", "is_nri_per_income_tax_act_1961", ("husband or wife", "minor children")),
    ("AB-PMJAY", "monthly_income_inr", ("household",)),  # SECC parameter vi: "any member of household"
    ("PMAY-G", "monthly_income_inr", ("family",)),       # MoRD p.141 vi: "any member of the family"
])
def test_each_scheme_uses_its_own_family_definition(sid, field, must_mention):
    question = _applicant_question(GOLD[sid], field)
    assert all(words in question for words in must_mention), question
    if field.endswith("_inr"):
        assert "highest" in question


def test_a_relative_listed_in_the_profile_is_still_asked_about_individually():
    scheme = GOLD["PM-KISAN"]
    q = build_question(MissingField(field="monthly_pension_inr", member="family_member[0]", cat=None,
                                    expected_value=10000), scheme)
    assert q.prompt.startswith("This next one is about one of your family members")
    assert "highest" not in q.prompt


def test_without_a_scheme_the_individual_question_is_unchanged():
    q = build_question(MissingField(field="monthly_pension_inr", member="self", cat=None, expected_value=10000))
    assert q.prompt == field_ontology.citizen_question_for("monthly_pension_inr")


# --- AI-Checked: the phrasing step phrases family-wide fields for the household -----------------------

_AI_SCHEME = Scheme.model_validate({
    "scheme_id": "SOME-STATE-PENSION", "unit_of_eligibility": "family",
    "inclusion": {"cat": "demographic", "field": "is_resident_of_state", "op": "==", "value": True},
    "exclusions": [
        {"cat": "economic", "quantifier": "some_family_member", "field": "owns_tractor_novel", "op": "==", "value": True},
        {"cat": "economic", "quantifier": "self", "field": "owns_shop_novel", "op": "==", "value": True},
        {"cat": "demographic", "quantifier": "some_family_member", "field": "age", "op": ">=", "value": 80},
    ],
    "temporal_validity": {"extracted_at": "2026-10-04"},
    "extraction_metadata": {"confidence": 0.5, "source_clause": "x", "flagged_for_review": True},
})


def _llm_answering(by_prompt_kind: dict[str, str]):
    def fake(messages, **kwargs):
        household = "EVERY member of the citizen's family" in messages[0]["content"]
        return ProviderResult(content=by_prompt_kind["household" if household else "own"],
                              provider_used="groq")
    return fake


def test_ai_checked_phrasing_generates_a_household_question_for_a_family_wide_novel_field():
    replies = {"own": "Do you own a tractor?", "household": "Does anyone in your family own a tractor?"}
    with patch("schemelogic.conversational.field_phrasing.chat_completion_with_fallback", side_effect=_llm_answering(replies)) as llm:
        field_phrasing.ensure_questions_for_scheme(_AI_SCHEME)
    household_calls = [c for c in llm.call_args_list if "EVERY member" in c.args[0][0]["content"]]
    assert len(household_calls) == 1  # only the family-wide novel field; not owns_shop_novel, not canonical age
    assert _applicant_question(_AI_SCHEME, "owns_tractor_novel") == "Does anyone in your family own a tractor?"
    assert field_ontology.citizen_question_for("owns_shop_novel") == "Do you own a tractor?"  # own-fact phrasing untouched
    cached = json.loads(field_phrasing.DISK_CACHE_PATH.read_text(encoding="utf-8"))
    assert cached["owns_tractor_novel@household"] == "Does anyone in your family own a tractor?"


def test_an_applicant_only_generation_is_rejected_for_a_family_wide_field_and_the_fallback_is_household():
    replies = {"own": "Do you own a tractor?", "household": "Do you own a tractor?"}  # ignored the instruction
    with patch("schemelogic.conversational.field_phrasing.chat_completion_with_fallback", side_effect=_llm_answering(replies)):
        field_phrasing.ensure_questions_for_scheme(_AI_SCHEME)
    question = _applicant_question(_AI_SCHEME, "owns_tractor_novel")
    assert question != "Do you own a tractor?" and is_household_phrased(question)


def test_household_phrasing_survives_a_provider_failure_and_a_canonical_field_without_a_template():
    with patch("schemelogic.conversational.field_phrasing.chat_completion_with_fallback",
               return_value=ProviderFailure(primary_error="429", secondary_error="429")):
        field_phrasing.ensure_questions_for_scheme(_AI_SCHEME)
    for field in ("owns_tractor_novel", "age"):
        assert is_household_phrased(_applicant_question(_AI_SCHEME, field)), field


def test_a_cached_household_phrasing_is_reloaded_after_a_restart():
    field_phrasing.DISK_CACHE_PATH.write_text(json.dumps({"owns_tractor_novel@household": "Does anyone in your family own a tractor?"}), encoding="utf-8")
    field_phrasing.preload_registered_questions()
    assert field_ontology.household_question_for("owns_tractor_novel", "X") == "Does anyone in your family own a tractor?"
