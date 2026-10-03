import pytest

from schemelogic.evaluator.symbolic_engine import (
    EvaluationError,
    Verdict,
    _and3,
    _combine_and3,
    _combine_or3,
    _compare,
    _evaluate_count_constraint,
    _not3,
    _or3,
    evaluate,
)
from schemelogic.schema.models import Scheme
from tests.fixtures import PM_KISAN

PM_KISAN_SCHEME = Scheme.model_validate(PM_KISAN)


def _base_eligible_profile(num_family_members: int = 2) -> dict:
    """A profile with every PM-KISAN field present and set to a non-disqualifying value."""
    member_fields = {
        "paid_income_tax_last_assessment_year": False,
        "is_serving_or_retired_govt_employee": False,
        "is_group_d_class_iv_or_mts": False,
        "monthly_pension_inr": 0,
        "holds_constitutional_or_political_post": False,
        "is_practicing_registered_professional": False,
        "is_nri_per_income_tax_act_1961": False,
    }
    return {
        "self": {
            "is_indian_citizen": True,
            "owns_cultivable_land_in_records": True,
            "is_institutional_landholder": False,
            **member_fields,
        },
        "family_members": [dict(member_fields) for _ in range(num_family_members)],
    }


# --- PM-KISAN end-to-end scenarios (Section 8, Phase 0 step 3) ------------------------


def test_clearly_eligible_family():
    profile = _base_eligible_profile()
    result = evaluate(PM_KISAN_SCHEME, profile)
    assert result.verdict == Verdict.ELIGIBLE
    assert result.trace["excluded_overall"] is False
    assert result.trace["inclusion_result"] is True


def test_clearly_ineligible_income_tax_paying_family_member():
    profile = _base_eligible_profile()
    profile["family_members"][0]["paid_income_tax_last_assessment_year"] = True
    result = evaluate(PM_KISAN_SCHEME, profile)
    assert result.verdict == Verdict.INELIGIBLE
    exclusion_trace = result.trace["exclusions"][0]
    assert exclusion_trace["result"] is True
    assert exclusion_trace["members"][1]["member"] == "family_member[0]"
    assert exclusion_trace["members"][1]["result"] is True


def test_exception_group_d_govt_employee_not_excluded():
    """Group D / Class IV / MTS govt employees are explicitly exempted from the govt-employee exclusion."""
    profile = _base_eligible_profile()
    profile["self"]["is_serving_or_retired_govt_employee"] = True
    profile["self"]["is_group_d_class_iv_or_mts"] = True
    result = evaluate(PM_KISAN_SCHEME, profile)
    assert result.verdict == Verdict.ELIGIBLE
    govt_employee_trace = result.trace["exclusions"][1]
    assert govt_employee_trace["result"] is False
    self_member = govt_employee_trace["members"][0]
    assert self_member["predicate"]["result"] is True
    assert self_member["except"]["result"] is True
    assert self_member["result"] is False


def test_govt_employee_without_exception_is_excluded():
    profile = _base_eligible_profile()
    profile["self"]["is_serving_or_retired_govt_employee"] = True
    profile["self"]["is_group_d_class_iv_or_mts"] = False
    result = evaluate(PM_KISAN_SCHEME, profile)
    assert result.verdict == Verdict.INELIGIBLE


def test_pension_exception_applies_per_family_member():
    profile = _base_eligible_profile(num_family_members=1)
    profile["family_members"][0]["monthly_pension_inr"] = 15000
    profile["family_members"][0]["is_group_d_class_iv_or_mts"] = True
    result = evaluate(PM_KISAN_SCHEME, profile)
    assert result.verdict == Verdict.ELIGIBLE


def test_missing_field_on_self_produces_undetermined_not_false():
    profile = _base_eligible_profile()
    del profile["self"]["is_indian_citizen"]
    result = evaluate(PM_KISAN_SCHEME, profile)
    assert result.verdict == Verdict.UNDETERMINED
    assert result.trace["inclusion_result"] is None


def test_missing_field_on_one_family_member_produces_undetermined():
    profile = _base_eligible_profile(num_family_members=2)
    del profile["family_members"][1]["paid_income_tax_last_assessment_year"]
    result = evaluate(PM_KISAN_SCHEME, profile)
    assert result.verdict == Verdict.UNDETERMINED
    assert result.trace["exclusions"][0]["result"] is None


def test_missing_data_never_silently_defaults_to_eligible():
    """Regression guard for Section 9 principle 4: missing facts must never resolve as if false."""
    profile = _base_eligible_profile()
    del profile["self"]["is_serving_or_retired_govt_employee"]
    result = evaluate(PM_KISAN_SCHEME, profile)
    assert result.verdict != Verdict.ELIGIBLE
    assert result.verdict == Verdict.UNDETERMINED


def test_definite_exclusion_overrides_undetermined_inclusion():
    """A known disqualification is reported even if inclusion couldn't be fully checked."""
    profile = _base_eligible_profile()
    del profile["self"]["is_indian_citizen"]
    profile["family_members"][0]["paid_income_tax_last_assessment_year"] = True
    result = evaluate(PM_KISAN_SCHEME, profile)
    assert result.trace["inclusion_result"] is None
    assert result.verdict == Verdict.INELIGIBLE


def test_inclusion_false_is_ineligible_even_with_missing_exclusion_data():
    profile = _base_eligible_profile()
    profile["self"]["owns_cultivable_land_in_records"] = False
    del profile["family_members"][0]["paid_income_tax_last_assessment_year"]
    result = evaluate(PM_KISAN_SCHEME, profile)
    assert result.verdict == Verdict.INELIGIBLE


def test_institutional_landholder_self_only_exclusion():
    profile = _base_eligible_profile()
    profile["self"]["is_institutional_landholder"] = True
    result = evaluate(PM_KISAN_SCHEME, profile)
    assert result.verdict == Verdict.INELIGIBLE


def test_no_exclusions_triggered_reports_all_false():
    profile = _base_eligible_profile()
    result = evaluate(PM_KISAN_SCHEME, profile)
    for exclusion_trace in result.trace["exclusions"]:
        assert exclusion_trace["result"] is False


def test_nri_family_member_is_ineligible():
    """Para 4.1(c): NRI status per Income Tax Act 1961 excludes the family."""
    profile = _base_eligible_profile()
    profile["family_members"][0]["is_nri_per_income_tax_act_1961"] = True
    result = evaluate(PM_KISAN_SCHEME, profile)
    assert result.verdict == Verdict.INELIGIBLE


def test_self_nri_is_ineligible():
    profile = _base_eligible_profile()
    profile["self"]["is_nri_per_income_tax_act_1961"] = True
    result = evaluate(PM_KISAN_SCHEME, profile)
    assert result.verdict == Verdict.INELIGIBLE


def test_missing_nri_status_is_undetermined_not_eligible():
    profile = _base_eligible_profile()
    del profile["self"]["is_nri_per_income_tax_act_1961"]
    del profile["family_members"][0]["is_nri_per_income_tax_act_1961"]
    del profile["family_members"][1]["is_nri_per_income_tax_act_1961"]
    result = evaluate(PM_KISAN_SCHEME, profile)
    assert result.verdict == Verdict.UNDETERMINED


# --- all_family_members quantifier (needs an ad hoc scheme; PM-KISAN has none) --------

ALL_MEMBERS_SCHEME = Scheme.model_validate(
    {
        "scheme_id": "TEST-ALL-MEMBERS",
        "unit_of_eligibility": "family",
        "inclusion": {"cat": "demographic", "field": "age", "op": ">=", "value": 18},
        "exclusions": [
            {
                "cat": "economic",
                "quantifier": "all_family_members",
                "field": "is_below_poverty_line",
                "op": "==",
                "value": True,
            }
        ],
        "temporal_validity": {"valid_from": "2020-01-01", "extracted_at": "2026-01-01"},
        "extraction_metadata": {
            "confidence": 0.9,
            "source_clause": "test fixture",
            "flagged_for_review": False,
        },
    }
)


def test_all_family_members_not_all_satisfied_is_not_excluded():
    profile = {
        "self": {"age": 20, "is_below_poverty_line": True},
        "family_members": [{"is_below_poverty_line": True}, {"is_below_poverty_line": False}],
    }
    result = evaluate(ALL_MEMBERS_SCHEME, profile)
    assert result.verdict == Verdict.ELIGIBLE


def test_all_family_members_all_satisfied_is_excluded():
    profile = {
        "self": {"age": 20, "is_below_poverty_line": True},
        "family_members": [{"is_below_poverty_line": True}, {"is_below_poverty_line": True}],
    }
    result = evaluate(ALL_MEMBERS_SCHEME, profile)
    assert result.verdict == Verdict.INELIGIBLE


def test_all_family_members_missing_data_with_no_definite_false_is_undetermined():
    profile = {
        "self": {"age": 20, "is_below_poverty_line": True},
        "family_members": [{"is_below_poverty_line": True}, {}],
    }
    result = evaluate(ALL_MEMBERS_SCHEME, profile)
    assert result.verdict == Verdict.UNDETERMINED


def test_all_family_members_definite_false_wins_over_missing_data_elsewhere():
    """One member known NOT to satisfy the condition makes the AND definitely False,
    even if another member's data is missing — it shouldn't matter, and shouldn't be undetermined."""
    profile = {
        "self": {"age": 20, "is_below_poverty_line": True},
        "family_members": [{"is_below_poverty_line": False}, {}],
    }
    result = evaluate(ALL_MEMBERS_SCHEME, profile)
    assert result.verdict == Verdict.ELIGIBLE


# --- nested AND/OR inclusion trees -----------------------------------------------------


def test_nested_or_inclusion():
    scheme = Scheme.model_validate(
        {
            "scheme_id": "TEST-OR",
            "unit_of_eligibility": "individual",
            "inclusion": {
                "or": [
                    {"cat": "demographic", "field": "age", "op": ">=", "value": 60},
                    {
                        "and": [
                            {"cat": "demographic", "field": "is_disabled", "op": "==", "value": True},
                            {"cat": "economic", "field": "annual_income_inr", "op": "<=", "value": 100000},
                        ]
                    },
                ]
            },
            "exclusions": [],
            "temporal_validity": {"valid_from": "2020-01-01", "extracted_at": "2026-01-01"},
            "extraction_metadata": {"confidence": 1.0, "source_clause": "test", "flagged_for_review": False},
        }
    )
    senior = evaluate(scheme, {"self": {"age": 65, "is_disabled": False, "annual_income_inr": 500000}})
    assert senior.verdict == Verdict.ELIGIBLE

    disabled_low_income = evaluate(
        scheme, {"self": {"age": 30, "is_disabled": True, "annual_income_inr": 50000}}
    )
    assert disabled_low_income.verdict == Verdict.ELIGIBLE

    neither = evaluate(scheme, {"self": {"age": 30, "is_disabled": False, "annual_income_inr": 500000}})
    assert neither.verdict == Verdict.INELIGIBLE

    # age missing, disabled branch False (known) -> AND short-circuits False -> OR(None, False) = None
    profile_missing_age = {"self": {"is_disabled": False, "annual_income_inr": 50000}}
    result = evaluate(scheme, profile_missing_age)
    assert result.verdict == Verdict.UNDETERMINED


# --- three-valued logic primitives (thorough truth-table coverage) --------------------


@pytest.mark.parametrize(
    "a,b,expected",
    [
        (True, True, True),
        (True, False, False),
        (False, True, False),
        (False, False, False),
        (True, None, None),
        (None, True, None),
        (False, None, False),
        (None, False, False),
        (None, None, None),
    ],
)
def test_and3_truth_table(a, b, expected):
    assert _and3(a, b) is expected


@pytest.mark.parametrize(
    "a,b,expected",
    [
        (True, True, True),
        (True, False, True),
        (False, True, True),
        (False, False, False),
        (True, None, True),
        (None, True, True),
        (False, None, None),
        (None, False, None),
        (None, None, None),
    ],
)
def test_or3_truth_table(a, b, expected):
    assert _or3(a, b) is expected


@pytest.mark.parametrize("a,expected", [(True, False), (False, True), (None, None)])
def test_not3(a, expected):
    assert _not3(a) is expected


def test_combine_and3_and_or3_over_lists():
    assert _combine_and3([True, True, True]) is True
    assert _combine_and3([True, False, None]) is False
    assert _combine_and3([True, None, True]) is None
    assert _combine_or3([False, False, False]) is False
    assert _combine_or3([False, True, None]) is True
    assert _combine_or3([False, None, False]) is None


# --- comparison operators ---------------------------------------------------------------


@pytest.mark.parametrize(
    "op,actual,expected,result",
    [
        ("==", 5, 5, True),
        ("==", 5, 6, False),
        ("!=", 5, 6, True),
        ("<", 5, 10, True),
        ("<=", 10, 10, True),
        (">", 10, 5, True),
        (">=", 10, 10, True),
        ("in", "b", ["a", "b", "c"], True),
        ("not_in", "z", ["a", "b", "c"], True),
    ],
)
def test_compare_operators(op, actual, expected, result):
    assert _compare(op, actual, expected) is result


def test_compare_raises_on_incompatible_types():
    with pytest.raises(EvaluationError):
        _compare("<", "not-a-number", 5)


def test_compare_unknown_operator_raises():
    with pytest.raises(EvaluationError):
        _compare("~=", 1, 1)


# --- count_family_members quantifier (Phase 0.5 extension) ----------------------------

# member_results, count_op, count, expected — boundary logic worked through per operator,
# not assumed to follow one shared pattern.
COUNT_CONSTRAINT_CASES = [
    # <=2 : "missing member could only help, not hurt" -> definite True even with a None present
    pytest.param([True, True], "<=", 2, True, id="lte-exact-cap-no-missing"),
    pytest.param([True, True, True], "<=", 2, False, id="lte-over-cap-definite-false"),
    pytest.param([True, None], "<=", 2, True, id="lte-missing-cannot-exceed-cap-definite-true"),
    pytest.param([True, True, None], "<=", 2, None, id="lte-missing-could-push-over-cap-undetermined"),
    # <2
    pytest.param([True], "<", 2, True, id="lt-below-threshold-definite-true"),
    pytest.param([True, True], "<", 2, False, id="lt-at-threshold-definite-false"),
    pytest.param([True, None], "<", 2, None, id="lt-missing-could-tip-either-way-undetermined"),
    # >=2 (the Ladki Bahin cap direction: "already 2 enrolled -> exclude the 3rd")
    pytest.param([True, True], ">=", 2, True, id="gte-exact-threshold-definite-true"),
    pytest.param([True], ">=", 2, False, id="gte-cannot-reach-threshold-definite-false"),
    pytest.param([True, None], ">=", 2, None, id="gte-missing-could-reach-threshold-undetermined"),
    # >2
    pytest.param([True, True, True], ">", 2, True, id="gt-over-threshold-definite-true"),
    pytest.param([True, True], ">", 2, False, id="gt-at-threshold-not-over-definite-false"),
    pytest.param([True, True, None], ">", 2, None, id="gt-missing-could-push-over-undetermined"),
    # ==2
    pytest.param([True, True], "==", 2, True, id="eq-exact-no-missing-definite-true"),
    pytest.param([True, True, True], "==", 2, False, id="eq-outside-range-no-missing-definite-false"),
    pytest.param([False, None], "==", 2, False, id="eq-missing-cannot-reach-target-definite-false"),
    pytest.param([True, None], "==", 2, None, id="eq-target-inside-achievable-range-undetermined"),
]


@pytest.mark.parametrize("member_results,count_op,count,expected", COUNT_CONSTRAINT_CASES)
def test_count_constraint_boundary_logic(member_results, count_op, count, expected):
    result, _trace = _evaluate_count_constraint(member_results, count_op, count)
    assert result is expected


def test_count_constraint_trace_reports_true_false_missing_breakdown():
    _result, trace = _evaluate_count_constraint([True, False, None, None], ">=", 2)
    assert trace["true_count"] == 1
    assert trace["false_count"] == 1
    assert trace["missing_count"] == 2
    assert trace["achievable_range"] == [1, 3]


COUNT_SCHEME = Scheme.model_validate(
    {
        "scheme_id": "TEST-COUNT",
        "unit_of_eligibility": "family",
        "inclusion": {"cat": "demographic", "field": "age", "op": ">=", "value": 18},
        "exclusions": [
            {
                "cat": "family_unit",
                "quantifier": "count_family_members",
                "field": "is_below_poverty_line",
                "op": "==",
                "value": True,
                "count_op": ">=",
                "count": 2,
            }
        ],
        "temporal_validity": {"valid_from": "2020-01-01", "extracted_at": "2026-01-01"},
        "extraction_metadata": {"confidence": 0.9, "source_clause": "test fixture", "flagged_for_review": False},
    }
)


def test_count_quantifier_end_to_end_at_cap_is_ineligible():
    profile = {
        "self": {"age": 20, "is_below_poverty_line": True},
        "family_members": [{"is_below_poverty_line": True}],
    }
    result = evaluate(COUNT_SCHEME, profile)
    assert result.verdict == Verdict.INELIGIBLE
    assert result.trace["exclusions"][0]["count_constraint"]["result"] is True


def test_count_quantifier_end_to_end_under_cap_is_eligible():
    profile = {
        "self": {"age": 20, "is_below_poverty_line": True},
        "family_members": [{"is_below_poverty_line": False}],
    }
    result = evaluate(COUNT_SCHEME, profile)
    assert result.verdict == Verdict.ELIGIBLE


def test_count_quantifier_end_to_end_missing_member_is_undetermined():
    profile = {
        "self": {"age": 20, "is_below_poverty_line": True},
        "family_members": [{}],
    }
    result = evaluate(COUNT_SCHEME, profile)
    assert result.verdict == Verdict.UNDETERMINED
    assert result.trace["exclusions"][0]["count_constraint"]["result"] is None


def test_count_quantifier_definite_over_cap_ignores_missing_member_elsewhere():
    profile = {
        "self": {"age": 20, "is_below_poverty_line": True},
        "family_members": [{"is_below_poverty_line": True}, {"is_below_poverty_line": True}, {}],
    }
    result = evaluate(COUNT_SCHEME, profile)
    assert result.verdict == Verdict.INELIGIBLE
    assert result.trace["exclusions"][0]["count_constraint"]["result"] is True


# --- except_scope: whose record an exclusion's exception is read from (2026-10-03) ---------------
# A household-route exemption (AB-PMJAY's 70+ route) can't be expressed with a member-scoped
# exception: for an exclusion triggered by a family member, the exception would be read off THAT
# member's record, which doesn't carry the household fact. See models.ExceptScope.

ROUTE_SCHEME = Scheme.model_validate({
    "scheme_id": "ROUTE",
    "unit_of_eligibility": "family",
    "inclusion": {"or": [
        {"cat": "economic", "field": "is_poor", "op": "==", "value": True},
        {"cat": "demographic", "field": "household_route", "op": "==", "value": True},
    ]},
    "exclusions": [{
        "cat": "economic", "quantifier": "some_family_member",
        "field": "pays_tax", "op": "==", "value": True,
        "except": {"field": "household_route", "op": "==", "value": True},
        "except_scope": "applicant",
    }],
    "temporal_validity": {"valid_from": "2020-01-01", "extracted_at": "2026-01-01"},
    "extraction_metadata": {"confidence": 1.0, "source_clause": "t", "flagged_for_review": False},
})


def _route_profile(route, member_pays_tax: bool) -> dict:
    self_record = {"is_poor": True, "pays_tax": False}
    if route is not None:
        self_record["household_route"] = route
    return {"self": self_record, "family_members": [{"pays_tax": member_pays_tax}]}


def test_applicant_scoped_exception_waives_an_exclusion_triggered_by_another_member():
    result = evaluate(ROUTE_SCHEME, _route_profile(route=True, member_pays_tax=True))
    assert result.verdict == Verdict.ELIGIBLE
    member = result.trace["exclusions"][0]["members"][1]
    assert member["predicate"]["result"] is True  # the member DID pay tax...
    assert member["except"]["result"] is True  # ...and the exception, read from self, waived it
    assert member["except_member"] == "self"


def test_applicant_scoped_exception_false_still_excludes_definitely():
    """The regression a member-scoped exception would cause: with no household route, a tax-paying
    member must exclude DEFINITELY, not collapse to undetermined."""
    result = evaluate(ROUTE_SCHEME, _route_profile(route=False, member_pays_tax=True))
    assert result.verdict == Verdict.INELIGIBLE


def test_applicant_scoped_exception_missing_is_undetermined_and_asks_the_applicant():
    from schemelogic.conversational.question_selector import select_next_question

    profile = _route_profile(route=None, member_pays_tax=True)
    assert evaluate(ROUTE_SCHEME, profile).verdict == Verdict.UNDETERMINED
    question = select_next_question(ROUTE_SCHEME, profile)
    assert question.field == "household_route"
    assert question.member == "self"  # not "one of your family members"


def test_member_scoped_exception_cannot_express_a_household_route():
    """Documents WHY except_scope exists: the identical scheme with the default member scope reads
    the route off the tax-paying member, finds nothing, and gets both cases wrong."""
    data = ROUTE_SCHEME.model_dump(mode="json", by_alias=True)
    data["exclusions"][0]["except_scope"] = "member"
    member_scoped = Scheme.model_validate(data)
    assert evaluate(member_scoped, _route_profile(True, True)).verdict == Verdict.UNDETERMINED
    assert evaluate(member_scoped, _route_profile(False, True)).verdict == Verdict.UNDETERMINED


def test_default_scope_is_member_so_existing_exceptions_are_unchanged():
    """PM-KISAN's Group D carve-out exempts the employee themselves -- member scope is right, and
    it is what every exclusion written before except_scope existed gets by default."""
    assert all(e.except_scope.value == "member" for e in PM_KISAN_SCHEME.exclusions)
    profile = _base_eligible_profile()
    profile["family_members"][0]["is_serving_or_retired_govt_employee"] = True
    profile["family_members"][0]["is_group_d_class_iv_or_mts"] = True
    assert evaluate(PM_KISAN_SCHEME, profile).verdict == Verdict.ELIGIBLE


def test_except_scope_without_an_except_clause_is_rejected():
    data = ROUTE_SCHEME.model_dump(mode="json", by_alias=True)
    del data["exclusions"][0]["except"]
    with pytest.raises(ValueError, match="except_scope"):
        Scheme.model_validate(data)
