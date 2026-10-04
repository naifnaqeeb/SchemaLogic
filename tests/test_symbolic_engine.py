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
    excl = result.trace["exclusions"][0]
    assert excl["members"][1]["predicate"]["result"] is True  # the member DID pay tax...
    assert excl["condition_result"] is True  # ...so the exclusion's condition held...
    assert excl["except"]["result"] is True  # ...and the applicant's exception waived it, once
    assert excl["except_member"] == "self"
    assert excl["result"] is False
    # recorded once at exclusion level -- never repeated on a family member's row, where a
    # consumer could mistake it for that member's fact
    assert all("except" not in m for m in excl["members"])


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


# --- except_scope coverage: every combination from the 2026-10-04 independent review ------------
# The first review found the 6 tests above covered only some_family_member with one member, and
# found a real bug in the combinations they missed (count quantifiers). Each combination it listed
# is pinned below. Under applicant scope the waiver applies to the WHOLE exclusion, once:
# result = Q(condition over members) AND NOT exception(applicant).


def _route_scheme(quantifier: str, count_op: str | None = None, count: int | None = None,
                  extra_exclusions: tuple = ()) -> Scheme:
    excl = {
        "cat": "economic", "quantifier": quantifier, "field": "pays_tax", "op": "==", "value": True,
        "except": {"field": "household_route", "op": "==", "value": True}, "except_scope": "applicant",
    }
    if count_op is not None:
        excl.update(count_op=count_op, count=count)
    return Scheme.model_validate({
        "scheme_id": "ROUTE", "unit_of_eligibility": "family",
        "inclusion": {"cat": "economic", "field": "is_poor", "op": "==", "value": True},
        "exclusions": [excl, *extra_exclusions],
        "temporal_validity": {"valid_from": "2020-01-01", "extracted_at": "2026-01-01"},
        "extraction_metadata": {"confidence": 1.0, "source_clause": "t", "flagged_for_review": False},
    })


def _household(route, applicant_pays, *members_pay):
    me = {"is_poor": True}
    if applicant_pays is not None:
        me["pays_tax"] = applicant_pays
    if route is not None:
        me["household_route"] = route
    return {"self": me, "family_members": [({"pays_tax": m} if m is not None else {}) for m in members_pay]}


E, I, U = Verdict.ELIGIBLE, Verdict.INELIGIBLE, Verdict.UNDETERMINED


@pytest.mark.parametrize("route,applicant,members,expected", [
    (True, True, (True, True), E),     # everyone pays tax, but the route waives the exclusion
    (False, True, (True, True), I),    # no route: everyone pays tax -> excluded
    (False, True, (True, False), E),   # no route: not everyone pays tax -> not excluded
    (None, True, (True, True), U),     # route unknown and everyone pays tax -> can't tell
    (False, None, (True, True), U),    # applicant's own fact missing -> "all" undecided
    (False, False, (None, None), E),   # one known False already makes "all" false
])
def test_applicant_scope_with_all_family_members(route, applicant, members, expected):
    assert evaluate(_route_scheme("all_family_members"), _household(route, applicant, *members)).verdict == expected


# count_family_members, every operator. The defining property of a waiver: the applicant is never
# worse off WITH the exception than with no exception at all -- the first review found the opposite for
# "<", "<=" and "==" (a 70+ applicant made ineligible BECAUSE of the waiver). Compared against the
# no-exception baseline, with the route present, absent and unknown, and with missing member facts.
_RANK = {Verdict.INELIGIBLE: 0, Verdict.UNDETERMINED: 1, Verdict.ELIGIBLE: 2}


def _no_exception(scheme: Scheme) -> Scheme:
    data = scheme.model_dump(mode="json", by_alias=True)
    for excl in data["exclusions"]:
        excl["except"] = None
        excl["except_scope"] = "member"
    return Scheme.model_validate(data)


@pytest.mark.parametrize("op,n", [("<", 1), ("<=", 0), ("<=", 1), ("==", 0), ("==", 1), (">", 0), (">=", 1), (">=", 2)])
@pytest.mark.parametrize("members", [(True,), (False,), (None,), (True, True), (False, False), (True, False), (True, None)])
@pytest.mark.parametrize("route", [True, False, None])
def test_applicant_scope_with_count_never_makes_the_applicant_worse_off(op, n, members, route):
    scheme = _route_scheme("count_family_members", op, n)
    profile = _household(route, False, *members)
    with_exception = evaluate(scheme, profile).verdict
    assert _RANK[with_exception] >= _RANK[evaluate(_no_exception(scheme), profile).verdict]
    if route is True:
        assert with_exception == E  # waived: the exclusion cannot fire whatever the members' facts


def test_review_reproducer_f1_count_waiver_is_not_a_trigger():
    """Independent review, finding F1: count `< 1`, applicant with the route, a taxpaying son. The
    per-member waiver zeroed every member, so "fewer than one taxpayer" fired because of the waiver."""
    scheme = _route_scheme("count_family_members", "<", 1)
    assert evaluate(scheme, _household(True, False, True)).verdict == E
    assert evaluate(scheme, _household(False, False, True)).verdict == E  # 1 taxpayer: "<1" is false


def test_review_reproducer_q3_count_is_decided_when_the_route_is_unknown():
    """Independent review, Q3: count `== 1`, two taxpayers, route unknown. With the route nothing
    counts; without it the count is 2. Neither is 1, so the exclusion can't fire either way --
    per-member waiving treated the shared waiver as independent unknowns and said undetermined."""
    assert evaluate(_route_scheme("count_family_members", "==", 1), _household(None, True, True)).verdict == E


@pytest.mark.parametrize("op,n,members,expected", [
    (">=", 1, (True,), U),       # one taxpayer: excluded unless the route waives it -> unknown
    (">=", 1, (False,), E),      # nobody pays tax: can't fire whatever the route
    (">=", 3, (True, True), E),  # applicant known False, so at most 2 taxpayers: ">= 3" can't fire
])
def test_applicant_scope_with_count_and_unknown_route(op, n, members, expected):
    assert evaluate(_route_scheme("count_family_members", op, n), _household(None, False, *members)).verdict == expected


def test_applicant_scope_waived_route_decides_despite_missing_family_facts():
    for q in ("some_family_member", "all_family_members"):
        assert evaluate(_route_scheme(q), _household(True, None, None, None)).verdict == E


def test_applicant_scope_no_route_with_missing_family_facts_is_undetermined():
    assert evaluate(_route_scheme("some_family_member"), _household(False, False, None)).verdict == U


def test_applicant_exception_missing_while_family_facts_missing_is_undetermined():
    assert evaluate(_route_scheme("some_family_member"), _household(None, None, None)).verdict == U


def test_applicant_scope_with_empty_family():
    scheme = _route_scheme("some_family_member")
    assert evaluate(scheme, _household(False, True)).verdict == I
    assert evaluate(scheme, _household(True, True)).verdict == E
    assert evaluate(scheme, _household(False, False)).verdict == E


def test_applicant_scope_with_no_family_members_key():
    profile = {"self": {"is_poor": True, "pays_tax": True, "household_route": False}}
    assert evaluate(_route_scheme("some_family_member"), profile).verdict == I
    profile["self"]["household_route"] = True
    assert evaluate(_route_scheme("some_family_member"), profile).verdict == E


def test_applicant_scope_with_no_self_key_is_undetermined_not_a_crash():
    result = evaluate(_route_scheme("some_family_member"), {"family_members": [{"pays_tax": True}]})
    assert result.verdict == U
    assert result.trace["exclusions"][0]["except"]["result"] is None


def test_multiple_members_and_mixed_scopes():
    member_scoped = {
        "cat": "occupation", "quantifier": "some_family_member", "field": "govt_job", "op": "==", "value": True,
        "except": {"field": "is_group_d", "op": "==", "value": True},
    }
    scheme = _route_scheme("some_family_member", extra_exclusions=(member_scoped,))

    def profile(route, *members):
        return {"self": {"is_poor": True, "pays_tax": False, "govt_job": False, "household_route": route},
                "family_members": list(members)}

    # the route waives the tax exclusion for every member, but NOT the member-scoped govt-job one
    assert evaluate(scheme, profile(True, {"pays_tax": True, "govt_job": False},
                                    {"pays_tax": True, "govt_job": False})).verdict == E
    assert evaluate(scheme, profile(True, {"pays_tax": False, "govt_job": True, "is_group_d": False})).verdict == I
    # a Group D member's own exception still works alongside an applicant-scoped one
    assert evaluate(scheme, profile(False, {"pays_tax": False, "govt_job": True, "is_group_d": True},
                                    {"pays_tax": False, "govt_job": False})).verdict == E
    assert evaluate(scheme, profile(False, {"pays_tax": False, "govt_job": False},
                                    {"pays_tax": True, "govt_job": False})).verdict == I


def test_trace_reports_member_scope_when_there_is_no_exception():
    """Independent review F3: the trace said None where the model says "member"."""
    data = _route_scheme("some_family_member").model_dump(mode="json", by_alias=True)
    data["exclusions"] = [{"cat": "economic", "quantifier": "some_family_member",
                           "field": "pays_tax", "op": "==", "value": True}]
    excl = evaluate(Scheme.model_validate(data), _household(None, False, False)).trace["exclusions"][0]
    assert excl["except_scope"] == "member"
    assert excl["has_except"] is False


def test_member_scope_trace_rows_are_unchanged_by_except_scope():
    """Member scope keeps the exact pre-2026-10-03 shape: the exception on each member row, and no
    exclusion-level exception, condition_result or except_member."""
    profile = _base_eligible_profile()
    profile["family_members"][0]["is_serving_or_retired_govt_employee"] = True
    profile["family_members"][0]["is_group_d_class_iv_or_mts"] = True
    excl = evaluate(PM_KISAN_SCHEME, profile).trace["exclusions"][1]
    assert not {"except", "except_member", "condition_result"} & set(excl)
    assert all("except_member" not in m and "except" in m for m in excl["members"])


def test_applicant_scope_with_self_quantifier_is_rejected():
    """Independent review F4: with quantifier 'self' applicant scope changes nothing, so accepting it
    could only hide a mistake."""
    with pytest.raises(ValueError, match="no effect with quantifier 'self'"):
        _route_scheme("self")


def test_selector_asks_the_applicant_not_a_family_member_for_an_applicant_scoped_exception():
    """Independent review F2, with several family members: the applicant's fact is asked once, of the
    applicant -- never of family_member[0], whose record the evaluator doesn't read for it."""
    from schemelogic.conversational.question_selector import find_missing_fields, select_next_question

    scheme = _route_scheme("some_family_member")
    profile = _household(None, False, True, True, False)
    question = select_next_question(scheme, profile)
    assert (question.field, question.member) == ("household_route", "self")
    asks = [m.member for m in find_missing_fields(evaluate(scheme, profile)) if m.field == "household_route"]
    assert asks == ["self"]


# --- gaps found by the second independent review (2026-10-04, finding 9) ------------------------


@pytest.mark.parametrize("op,n,members,expected", [
    ("<", 1, (True,), E),          # 1 taxpayer: "< 1" can't fire whatever the route
    ("<", 1, (False,), U),         # 0 taxpayers: fires unless the (unknown) route waives it
    ("<", 2, (True, True), E),
    ("<", 2, (True, None), U),     # 1 or 2 taxpayers, route unknown
    ("<=", 0, (False,), U),
    ("<=", 0, (True,), E),
    ("<=", 1, (True, True), E),
    ("<=", 1, (None,), U),         # 0 or 1 taxpayers: "<= 1" holds either way; only the route decides
])
def test_applicant_scope_with_count_less_than_and_unknown_route(op, n, members, expected):
    assert evaluate(_route_scheme("count_family_members", op, n), _household(None, False, *members)).verdict == expected


def test_applicant_scope_with_count_less_than_decides_once_the_route_is_known():
    scheme = _route_scheme("count_family_members", "<=", 1)
    assert evaluate(scheme, _household(False, False, None)).verdict == I
    assert evaluate(scheme, _household(True, False, None)).verdict == E


def test_mixed_scopes_with_no_family_members_key():
    """Pins CURRENT behaviour: an absent family_members key is read as an empty family (finding 7 of
    the second review questions that; this test will change if that ruling does)."""
    member_scoped = {
        "cat": "occupation", "quantifier": "some_family_member", "field": "govt_job", "op": "==", "value": True,
        "except": {"field": "is_group_d", "op": "==", "value": True},
    }
    scheme = _route_scheme("some_family_member", extra_exclusions=(member_scoped,))

    def applicant(**facts):
        return {"self": {"is_poor": True, **facts}}

    assert evaluate(scheme, applicant(pays_tax=True, household_route=True, govt_job=True, is_group_d=True)).verdict == E
    assert evaluate(scheme, applicant(pays_tax=True, household_route=True, govt_job=True, is_group_d=False)).verdict == I
    assert evaluate(scheme, applicant(pays_tax=True, household_route=False, govt_job=False)).verdict == I
    assert evaluate(scheme, applicant(pays_tax=False, household_route=None, govt_job=False)).verdict == E


def test_explicit_member_scope_without_an_exception_is_accepted_as_the_default():
    data = _route_scheme("some_family_member").model_dump(mode="json", by_alias=True)
    data["exclusions"][0].update({"except": None, "except_scope": "member"})
    assert Scheme.model_validate(data).exclusions[0].except_scope.value == "member"


def test_applicant_scope_without_an_exception_names_the_scope_in_the_error():
    data = _route_scheme("some_family_member").model_dump(mode="json", by_alias=True)
    data["exclusions"][0]["except"] = None
    with pytest.raises(ValueError, match="except_scope 'applicant' requires an `except` clause"):
        Scheme.model_validate(data)


@pytest.mark.parametrize("bad", ["Applicant", "household", "self", "", None])
def test_unknown_except_scope_values_are_rejected(bad):
    data = _route_scheme("some_family_member").model_dump(mode="json", by_alias=True)
    data["exclusions"][0]["except_scope"] = bad
    with pytest.raises(ValueError):
        Scheme.model_validate(data)


def test_dump_gold_json_round_trips_and_is_idempotent():
    import json
    from pathlib import Path

    from schemelogic.schema.models import dump_gold_json

    schemes = [_route_scheme(q) for q in ("some_family_member", "all_family_members")]
    schemes.append(_route_scheme("count_family_members", "<", 1))
    gold_dir = Path(__file__).resolve().parents[1] / "data" / "gold"
    schemes += [Scheme.model_validate_json(p.read_text(encoding="utf-8")) for p in sorted(gold_dir.glob("*.json"))]
    assert len(schemes) >= 10
    for scheme in schemes:
        text = dump_gold_json(scheme)
        again = Scheme.model_validate(json.loads(text))
        assert again == scheme
        assert dump_gold_json(again) == text
        # the applicant scope survives the omission of defaults; the member default doesn't appear
        assert ('"except_scope": "applicant"' in text) == any(
            e.except_scope.value == "applicant" for e in scheme.exclusions)
        assert '"except_scope": "member"' not in text


def test_trace_consumers_handle_an_applicant_scoped_waiver():
    """Under applicant scope a member row's `result` is that member's raw condition and carries no
    `except`; the waiver is recorded once, at exclusion level. Every reader of the trace must cope:
    the citizen explanation says "waived", not "applies to you", on an ELIGIBLE verdict."""
    from schemelogic.annotation.rendering import trace_to_citizen_english
    from schemelogic.conversational.phrasing import plain_template_answer
    from schemelogic.conversational.question_selector import find_missing_fields

    result = evaluate(_route_scheme("some_family_member"), _household(True, True, True, None))
    assert result.verdict == E
    excl = result.trace["exclusions"][0]
    assert excl["has_except"] is True and all("except" not in m for m in excl["members"])
    assert excl["members"][0]["result"] is True  # raw condition: the applicant DOES pay tax

    text = trace_to_citizen_english(result.trace)
    assert "waived by an exception" in text
    assert "Applies to you" not in text
    assert "eligible" in plain_template_answer(result).lower()
    find_missing_fields(result)  # must not raise on rows without `except`
