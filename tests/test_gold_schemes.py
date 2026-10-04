"""Phase 0 step 4: hand-write gold scheme JSONs, confirm the evaluator gives correct verdicts
on hand-constructed profiles for each. See tests/gold_fixtures.py for the draft-status caveat."""

import pytest

from schemelogic.evaluator.symbolic_engine import Verdict, evaluate
from schemelogic.schema.models import Scheme
from tests.gold_fixtures import (
    AB_PMJAY,
    IGNOAPS,
    MAHARASHTRA_LADKI_BAHIN,
    PM_UJJWALA,
    PMAY_G,
    PMMVY,
)


def test_gold_json_and_test_fixture_copies_hold_identical_rules():
    """The gold set exists twice: data/gold/*.json (read by the app, the evaluation harness and
    Baseline 2) and the Python copies in tests/gold_fixtures.py + tests/fixtures.py (read by every
    test in this file). Nothing previously checked they agreed, so fixing a rule in only one place
    would have left these tests green while asserting the OLD behaviour -- found 2026-10-03 while
    planning the gold-audit fixes. Any gold change must now land in both or this fails."""
    import json
    from pathlib import Path

    from tests.fixtures import PM_KISAN

    gold_dir = Path(__file__).resolve().parents[1] / "data" / "gold"
    copies = {
        "AB-PMJAY": AB_PMJAY, "IGNOAPS": IGNOAPS, "MH-LADKI-BAHIN": MAHARASHTRA_LADKI_BAHIN,
        "PM-UJJWALA-2.0": PM_UJJWALA, "PMAY-G": PMAY_G, "PMMVY": PMMVY, "PM-KISAN": PM_KISAN,
    }
    assert sorted(copies) == sorted(p.stem for p in gold_dir.glob("*.json")), "a gold scheme has no test copy"
    for scheme_id, copy in copies.items():
        disk = Scheme.model_validate(json.loads((gold_dir / f"{scheme_id}.json").read_text(encoding="utf-8")))
        fixture = Scheme.model_validate(copy)
        assert disk.model_dump(mode="json", by_alias=True) == fixture.model_dump(mode="json", by_alias=True), (
            f"{scheme_id}: data/gold JSON and the test fixture copy have drifted apart"
        )


def test_all_gold_schemes_parse():
    for data in (AB_PMJAY, IGNOAPS, PMAY_G, PM_UJJWALA, MAHARASHTRA_LADKI_BAHIN, PMMVY):
        Scheme.model_validate(data)


def test_every_gold_scheme_still_states_a_real_effective_date():
    """`TemporalValidity.valid_from` became optional on 2026-09-15 so that AI-Checked extractions
    from myScheme text (which often states no date) aren't discarded over absent metadata. Gold
    schemes are annotated from primary notifications, which DO carry a date -- this guards against
    that optionality quietly eroding gold-set quality."""
    for data in (AB_PMJAY, IGNOAPS, PMAY_G, PM_UJJWALA, MAHARASHTRA_LADKI_BAHIN, PMMVY):
        scheme = Scheme.model_validate(data)
        assert scheme.temporal_validity.valid_from is not None, f"{scheme.scheme_id} lost its valid_from"


# --- AB-PMJAY ---------------------------------------------------------------------------

AB_PMJAY_SCHEME = Scheme.model_validate(AB_PMJAY)


def _pmjay_base_profile() -> dict:
    return {
        "self": {
            "is_secc_deprived_household": True,
            "is_secc_automatically_included": False,
            "is_valid_rsby_beneficiary": False,
            "is_urban_informal_worker": False,
            "age": 45,
            "household_owns_motorised_vehicle_or_fishing_boat": False,
            "owns_mechanized_agricultural_equipment_3_or_4_wheeler": False,
            "kisan_credit_card_limit_inr": 0,
            "owns_non_agricultural_enterprise_registered_with_govt": False,
            "house_has_3_or_more_pucca_rooms": False,
            "owns_refrigerator": False,
            "owns_landline_phone": False,
            "owns_gt_2_5_acres_irrigated_land_with_irrigation_equipment": False,
            "owns_5_or_more_acres_irrigated_land_two_or_more_crop_seasons": False,
            "owns_7_5_or_more_acres_land_with_irrigation_equipment": False,
            "is_govt_employee": False,
            "monthly_income_inr": 5000,
            "paid_income_tax_last_assessment_year": False,
            "paid_professional_tax": False,
        },
        "family_members": [
            {
                "is_govt_employee": False,
                "monthly_income_inr": 5000,
                "paid_income_tax_last_assessment_year": False,
                "paid_professional_tax": False,
            }
        ],
    }


def test_pmjay_secc_deprived_family_with_no_disqualifiers_is_eligible():
    profile = _pmjay_base_profile()
    assert evaluate(AB_PMJAY_SCHEME, profile).verdict == Verdict.ELIGIBLE


def test_pmjay_income_tax_paying_family_member_is_ineligible():
    profile = _pmjay_base_profile()
    profile["family_members"][0]["paid_income_tax_last_assessment_year"] = True
    assert evaluate(AB_PMJAY_SCHEME, profile).verdict == Verdict.INELIGIBLE


def test_pmjay_missing_deprivation_and_age_data_is_undetermined():
    profile = _pmjay_base_profile()
    del profile["self"]["is_secc_deprived_household"]
    del profile["self"]["age"]
    assert evaluate(AB_PMJAY_SCHEME, profile).verdict == Verdict.UNDETERMINED


def test_pmjay_seventy_plus_applicant_eligible_regardless_of_secc():
    """2024 amendment: universal for 70+, irrespective of SECC/BPL status."""
    profile = _pmjay_base_profile()
    profile["self"]["is_secc_deprived_household"] = False
    profile["self"]["age"] = 72
    assert evaluate(AB_PMJAY_SCHEME, profile).verdict == Verdict.ELIGIBLE


# --- AB-PMJAY 70+ route covers the 70+ person, not their household (gold fix, 2026-10-04) --------
# NHA 70+ guidelines s5.2: "a shared cover up to Rs 5 lakh per year will be available. This cover will
# not be available to the other members (who are not of the age 70 years and above)". The route tests
# the APPLICANT's own age. See docs/GOLD_AUDIT_2026-10-03.md section 6.7.


def test_pmjay_younger_applicant_with_a_seventy_plus_parent_is_not_covered_by_the_route():
    profile = _pmjay_base_profile()
    profile["self"]["is_secc_deprived_household"] = False  # no other route
    profile["self"]["age"] = 40
    profile["self"]["has_family_member_aged_70_or_above"] = True  # true, but no longer what the route tests
    profile["family_members"][0]["age"] = 74
    assert evaluate(AB_PMJAY_SCHEME, profile).verdict == Verdict.INELIGIBLE


def test_pmjay_the_seventy_plus_parent_themselves_is_covered():
    """The same household from the senior's side: the 74-year-old applying is eligible, and the
    relatives' socio-economic facts don't block it."""
    profile = _pmjay_base_profile()
    profile["self"]["is_secc_deprived_household"] = False
    profile["self"]["age"] = 74
    profile["family_members"][0].update(age=40, paid_income_tax_last_assessment_year=True, monthly_income_inr=40000)
    assert evaluate(AB_PMJAY_SCHEME, profile).verdict == Verdict.ELIGIBLE


@pytest.mark.parametrize("age,expected", [(69, Verdict.INELIGIBLE), (70, Verdict.ELIGIBLE), (71, Verdict.ELIGIBLE)])
def test_pmjay_seventy_plus_boundary_is_the_applicants_seventieth_year(age, expected):
    """'70 years of age and above': 70 itself qualifies."""
    profile = _pmjay_base_profile()
    profile["self"]["is_secc_deprived_household"] = False
    profile["self"]["age"] = age
    assert evaluate(AB_PMJAY_SCHEME, profile).verdict == expected


def test_pmjay_a_seventy_plus_relative_does_not_waive_the_applicants_exclusions():
    """The waiver reads the applicant's age, not a relative's: a 45-year-old SECC-deprived applicant
    whose household owns a refrigerator is excluded even with a 75-year-old in the family."""
    profile = _pmjay_base_profile()
    profile["self"]["owns_refrigerator"] = True
    profile["family_members"][0]["age"] = 75
    assert evaluate(AB_PMJAY_SCHEME, profile).verdict == Verdict.INELIGIBLE


# --- AB-PMJAY 70+ path vs the socio-economic exclusions (gold fix, 2026-10-03) -----------------
# The NHA 70+ expansion guidelines cover citizens aged 70+ "irrespective of their socio-economic
# status" and never apply the 14 SECC exclusions to them. The gold applied those exclusions to every
# inclusion path, so the 70+ route was blocked by exactly the facts it is meant to ignore. The
# existing 70+ test above set every exclusion false and so never noticed. These exercise it.
# See docs/GOLD_AUDIT_2026-10-03.md section 3 and section 6.


def _pmjay_seventy_plus_profile() -> dict:
    profile = _pmjay_base_profile()
    profile["self"]["is_secc_deprived_household"] = False  # qualifies ONLY via the 70+ route
    profile["self"]["age"] = 72
    return profile


def test_pmjay_seventy_plus_with_household_refrigerator_is_still_eligible():
    """A self-quantified exclusion must not block the 70+ route."""
    profile = _pmjay_seventy_plus_profile()
    profile["self"]["owns_refrigerator"] = True
    assert evaluate(AB_PMJAY_SCHEME, profile).verdict == Verdict.ELIGIBLE


def test_pmjay_seventy_plus_with_income_tax_paying_family_member_is_still_eligible():
    """The hard case. Income tax is a some_family_member exclusion, so it is triggered by a member
    OTHER than the applicant -- and the 70+ fact lives on the applicant's record, not that member's.
    An exception evaluated on the triggering member cannot see it."""
    profile = _pmjay_seventy_plus_profile()
    profile["family_members"][0]["paid_income_tax_last_assessment_year"] = True
    assert evaluate(AB_PMJAY_SCHEME, profile).verdict == Verdict.ELIGIBLE


def test_pmjay_seventy_plus_with_high_earning_family_member_is_still_eligible():
    profile = _pmjay_seventy_plus_profile()
    profile["family_members"][0]["monthly_income_inr"] = 25000
    assert evaluate(AB_PMJAY_SCHEME, profile).verdict == Verdict.ELIGIBLE


def test_pmjay_seventy_plus_with_every_exclusion_triggered_is_still_eligible():
    """Irrespective of socio-economic status means all of it, at once."""
    profile = _pmjay_seventy_plus_profile()
    for field, value in list(profile["self"].items()):
        if isinstance(value, bool) and field not in (
            "is_secc_deprived_household", "is_secc_automatically_included",
            "is_valid_rsby_beneficiary",
        ):
            profile["self"][field] = True
    profile["self"]["kisan_credit_card_limit_inr"] = 100000
    profile["family_members"][0].update(
        is_govt_employee=True, monthly_income_inr=50000,
        paid_income_tax_last_assessment_year=True, paid_professional_tax=True,
    )
    assert evaluate(AB_PMJAY_SCHEME, profile).verdict == Verdict.ELIGIBLE


def test_pmjay_exclusions_still_apply_to_non_seventy_plus_routes():
    """Control: the fix must narrow the exclusions to the non-70+ routes, not switch them off."""
    profile = _pmjay_base_profile()  # SECC-deprived, applicant aged 45
    profile["family_members"][0]["paid_income_tax_last_assessment_year"] = True
    assert evaluate(AB_PMJAY_SCHEME, profile).verdict == Verdict.INELIGIBLE
    profile = _pmjay_base_profile()
    profile["self"]["owns_refrigerator"] = True
    assert evaluate(AB_PMJAY_SCHEME, profile).verdict == Verdict.INELIGIBLE


def test_pmjay_unknown_seventy_plus_status_with_an_exclusion_is_undetermined_not_ineligible():
    """SECC-deprived, owns a refrigerator, applicant's age not yet known. If they are 70+ they are
    eligible; if not, the refrigerator excludes them. Neither verdict is justified until the fact is
    known -- so undetermined, and the question to ask is the age one."""
    profile = _pmjay_base_profile()
    del profile["self"]["age"]
    profile["self"]["owns_refrigerator"] = True
    assert evaluate(AB_PMJAY_SCHEME, profile).verdict == Verdict.UNDETERMINED


def test_pmjay_mechanized_agri_equipment_is_ineligible():
    profile = _pmjay_base_profile()
    profile["self"]["owns_mechanized_agricultural_equipment_3_or_4_wheeler"] = True
    assert evaluate(AB_PMJAY_SCHEME, profile).verdict == Verdict.INELIGIBLE


def test_pmjay_monthly_income_over_threshold_is_ineligible():
    profile = _pmjay_base_profile()
    profile["family_members"][0]["monthly_income_inr"] = 15000
    assert evaluate(AB_PMJAY_SCHEME, profile).verdict == Verdict.INELIGIBLE


def test_pmjay_refrigerator_is_ineligible():
    profile = _pmjay_base_profile()
    profile["self"]["owns_refrigerator"] = True
    assert evaluate(AB_PMJAY_SCHEME, profile).verdict == Verdict.INELIGIBLE


def test_pmjay_compound_irrigated_land_exclusion_is_ineligible():
    profile = _pmjay_base_profile()
    profile["self"]["owns_gt_2_5_acres_irrigated_land_with_irrigation_equipment"] = True
    assert evaluate(AB_PMJAY_SCHEME, profile).verdict == Verdict.INELIGIBLE


# --- IGNOAPS ------------------------------------------------------------------------------

IGNOAPS_SCHEME = Scheme.model_validate(IGNOAPS)


def _ignoaps_base_profile() -> dict:
    return {
        "self": {
            "age": 65,
            "is_bpl_household": True,
            "has_regular_family_financial_support": False,
            "is_govt_employee": False,
            "family_agricultural_land_acres": 0,
            "owns_four_wheeler": False,
        }
    }


def test_ignoaps_elderly_bpl_no_support_is_eligible():
    profile = _ignoaps_base_profile()
    assert evaluate(IGNOAPS_SCHEME, profile).verdict == Verdict.ELIGIBLE


def test_ignoaps_under_60_is_ineligible():
    profile = _ignoaps_base_profile()
    profile["self"]["age"] = 45
    assert evaluate(IGNOAPS_SCHEME, profile).verdict == Verdict.INELIGIBLE
def test_ignoaps_under_five_acres_land_is_eligible():
    profile = _ignoaps_base_profile()
    profile["self"]["family_agricultural_land_acres"] = 4.99
    assert evaluate(IGNOAPS_SCHEME, profile).verdict == Verdict.ELIGIBLE


# --- IGNOAPS: family support removed; carve-out criteria scoped to the carve-out (2026-10-03) ----
# Replaces five tests that asserted the old rules:
#   - family support excluded / its absence left the verdict undetermined. The predicate was an
#     "interpretive elevation" of NSAP's programme-wide destitute definition that its own author
#     doubted, and is removed.
#   - government job / 5+ acres / four-wheeler excluded EVERY applicant. All three IGNOAPS sources
#     state them only inside the Para 2.4.3 carve-out ("except widows suffering from AIDS who will be
#     considered if they are not attracted by any of the exclusion criteria..."), so they now gate
#     that carve-out route and nothing else.
# See docs/GOLD_AUDIT_2026-10-03.md section 6.4.


def _ignoaps_aids_widow_profile() -> dict:
    """Not BPL -- eligible, if at all, only through the Para 2.4.3 carve-out."""
    return {
        "self": {
            "age": 65,
            "is_bpl_household": False,
            "is_widow_suffering_from_aids": True,
            "is_govt_employee": False,
            "family_agricultural_land_acres": 0,
            "owns_four_wheeler": False,
        }
    }


def test_ignoaps_bpl_applicant_with_family_support_is_still_eligible():
    profile = _ignoaps_base_profile()
    profile["self"]["has_regular_family_financial_support"] = True
    assert evaluate(IGNOAPS_SCHEME, profile).verdict == Verdict.ELIGIBLE


def test_ignoaps_family_support_is_never_asked():
    from schemelogic.conversational.question_selector import select_next_question

    profile = {"self": {"age": 65}, "family_members": []}
    asked: list[str] = []
    while (q := select_next_question(IGNOAPS_SCHEME, profile)) is not None:
        asked.append(q.field)
        profile["self"][q.field] = True if q.answer_type == "boolean" else 0
    assert "has_regular_family_financial_support" not in asked


def test_ignoaps_bpl_applicant_with_govt_job_is_eligible():
    """Carve-out criterion: does not apply to the ordinary BPL route."""
    profile = _ignoaps_base_profile()
    profile["self"]["is_govt_employee"] = True
    assert evaluate(IGNOAPS_SCHEME, profile).verdict == Verdict.ELIGIBLE


def test_ignoaps_bpl_applicant_with_five_acres_is_eligible():
    profile = _ignoaps_base_profile()
    profile["self"]["family_agricultural_land_acres"] = 5
    assert evaluate(IGNOAPS_SCHEME, profile).verdict == Verdict.ELIGIBLE


def test_ignoaps_bpl_applicant_with_four_wheeler_is_eligible():
    profile = _ignoaps_base_profile()
    profile["self"]["owns_four_wheeler"] = True
    assert evaluate(IGNOAPS_SCHEME, profile).verdict == Verdict.ELIGIBLE


def test_ignoaps_non_bpl_aids_widow_clear_of_the_criteria_is_eligible():
    assert evaluate(IGNOAPS_SCHEME, _ignoaps_aids_widow_profile()).verdict == Verdict.ELIGIBLE


def test_ignoaps_non_bpl_aids_widow_with_govt_job_is_ineligible():
    profile = _ignoaps_aids_widow_profile()
    profile["self"]["is_govt_employee"] = True
    assert evaluate(IGNOAPS_SCHEME, profile).verdict == Verdict.INELIGIBLE


def test_ignoaps_non_bpl_aids_widow_with_five_acres_is_ineligible():
    """The criterion is 'five acres of land or more', so exactly 5 counts."""
    profile = _ignoaps_aids_widow_profile()
    profile["self"]["family_agricultural_land_acres"] = 5
    assert evaluate(IGNOAPS_SCHEME, profile).verdict == Verdict.INELIGIBLE


def test_ignoaps_non_bpl_aids_widow_with_four_wheeler_is_ineligible():
    profile = _ignoaps_aids_widow_profile()
    profile["self"]["owns_four_wheeler"] = True
    assert evaluate(IGNOAPS_SCHEME, profile).verdict == Verdict.INELIGIBLE


def test_ignoaps_non_bpl_without_the_carve_out_is_ineligible():
    profile = _ignoaps_aids_widow_profile()
    profile["self"]["is_widow_suffering_from_aids"] = False
    assert evaluate(IGNOAPS_SCHEME, profile).verdict == Verdict.INELIGIBLE


def test_ignoaps_non_bpl_aids_widow_with_criteria_unknown_is_undetermined():
    profile = _ignoaps_aids_widow_profile()
    del profile["self"]["is_govt_employee"]
    assert evaluate(IGNOAPS_SCHEME, profile).verdict == Verdict.UNDETERMINED


def test_ignoaps_bpl_status_unknown_is_undetermined():
    """IGNOAPS keeps a missing-data case: with family support gone, BPL status is what's unknown."""
    profile = _ignoaps_base_profile()
    del profile["self"]["is_bpl_household"]
    assert evaluate(IGNOAPS_SCHEME, profile).verdict == Verdict.UNDETERMINED


# --- PMAY-G ---------------------------------------------------------------------------------

PMAY_G_SCHEME = Scheme.model_validate(PMAY_G)


def _pmayg_base_profile() -> dict:
    return {
        "self": {
            "is_houseless": False,
            "lives_in_kutcha_house": True,
            "is_secc_automatically_included": False,
            "is_govt_employee": False,
            "owns_non_agricultural_enterprise_registered_with_govt": False,
            "kisan_credit_card_limit_inr": 0,
            "owns_refrigerator": False,
            "owns_landline_phone": False,
            "owns_gt_2_5_acres_irrigated_land": False,
            "owns_motorised_three_or_four_wheeler": False,
            "owns_mechanized_agricultural_equipment_3_or_4_wheeler": False,
            "owns_pucca_house": False,
            "monthly_income_inr": 5000,
            "paid_income_tax_last_assessment_year": False,
        },
        "family_members": [
            {
                "is_govt_employee": False,
                "monthly_income_inr": 5000,
                "paid_income_tax_last_assessment_year": False,
            }
        ],
    }


def test_pmayg_kutcha_house_low_income_is_eligible():
    profile = _pmayg_base_profile()
    assert evaluate(PMAY_G_SCHEME, profile).verdict == Verdict.ELIGIBLE


def test_pmayg_income_over_ceiling_is_ineligible():
    profile = _pmayg_base_profile()
    profile["family_members"][0]["monthly_income_inr"] = 20000
    assert evaluate(PMAY_G_SCHEME, profile).verdict == Verdict.INELIGIBLE


def test_pmayg_missing_housing_status_is_undetermined():
    profile = _pmayg_base_profile()
    del profile["self"]["is_houseless"]
    del profile["self"]["lives_in_kutcha_house"]
    del profile["self"]["is_secc_automatically_included"]
    assert evaluate(PMAY_G_SCHEME, profile).verdict == Verdict.UNDETERMINED


def test_pmayg_secc_automatically_included_regardless_of_housing_is_eligible():
    profile = _pmayg_base_profile()
    profile["self"]["lives_in_kutcha_house"] = False
    profile["self"]["is_secc_automatically_included"] = True
    assert evaluate(PMAY_G_SCHEME, profile).verdict == Verdict.ELIGIBLE


def test_pmayg_refrigerator_is_ineligible():
    profile = _pmayg_base_profile()
    profile["self"]["owns_refrigerator"] = True
    assert evaluate(PMAY_G_SCHEME, profile).verdict == Verdict.INELIGIBLE


def test_pmayg_landline_phone_is_ineligible():
    profile = _pmayg_base_profile()
    profile["self"]["owns_landline_phone"] = True
    assert evaluate(PMAY_G_SCHEME, profile).verdict == Verdict.INELIGIBLE


def test_pmayg_irrigated_land_over_threshold_is_ineligible():
    profile = _pmayg_base_profile()
    profile["self"]["owns_gt_2_5_acres_irrigated_land"] = True
    assert evaluate(PMAY_G_SCHEME, profile).verdict == Verdict.INELIGIBLE


def test_pmayg_mechanized_agri_equipment_is_ineligible():
    profile = _pmayg_base_profile()
    profile["self"]["owns_mechanized_agricultural_equipment_3_or_4_wheeler"] = True
    assert evaluate(PMAY_G_SCHEME, profile).verdict == Verdict.INELIGIBLE


def test_pmayg_non_agricultural_enterprise_is_ineligible():
    profile = _pmayg_base_profile()
    profile["self"]["owns_non_agricultural_enterprise_registered_with_govt"] = True
    assert evaluate(PMAY_G_SCHEME, profile).verdict == Verdict.INELIGIBLE


def test_pmayg_income_tax_family_member_is_ineligible():
    profile = _pmayg_base_profile()
    profile["family_members"][0]["paid_income_tax_last_assessment_year"] = True
    assert evaluate(PMAY_G_SCHEME, profile).verdict == Verdict.INELIGIBLE


# --- PM Ujjwala 2.0 -------------------------------------------------------------------------

PM_UJJWALA_SCHEME = Scheme.model_validate(PM_UJJWALA)


def test_ujjwala_bpl_woman_no_existing_connection_is_eligible():
    profile = {
        "self": {
            "is_woman": True,
            "age": 25,
            "is_indian_citizen": True,
            "is_bpl_household": True,
            "household_has_existing_lpg_connection": False,
        }
    }
    assert evaluate(PM_UJJWALA_SCHEME, profile).verdict == Verdict.ELIGIBLE


def test_ujjwala_already_has_lpg_connection_is_ineligible():
    profile = {
        "self": {
            "is_woman": True,
            "age": 25,
            "is_indian_citizen": True,
            "is_bpl_household": True,
            "household_has_existing_lpg_connection": True,
        }
    }
    assert evaluate(PM_UJJWALA_SCHEME, profile).verdict == Verdict.INELIGIBLE


def test_ujjwala_no_category_membership_known_is_undetermined():
    profile = {
        "self": {
            "is_woman": True,
            "age": 25,
            "is_indian_citizen": True,
            "household_has_existing_lpg_connection": False,
        }
    }
    assert evaluate(PM_UJJWALA_SCHEME, profile).verdict == Verdict.UNDETERMINED


def test_ujjwala_sc_st_alone_is_eligible():
    """SC/ST and PMAY-G beneficiary are separate categories, not a compound AND."""
    profile = {
        "self": {
            "is_woman": True,
            "age": 25,
            "is_indian_citizen": True,
            "is_sc_st": True,
            "is_pmay_g_beneficiary": False,
            "household_has_existing_lpg_connection": False,
        }
    }
    assert evaluate(PM_UJJWALA_SCHEME, profile).verdict == Verdict.ELIGIBLE


def test_ujjwala_pmay_g_beneficiary_alone_is_eligible():
    profile = {
        "self": {
            "is_woman": True,
            "age": 25,
            "is_indian_citizen": True,
            "is_sc_st": False,
            "is_pmay_g_beneficiary": True,
            "household_has_existing_lpg_connection": False,
        }
    }
    assert evaluate(PM_UJJWALA_SCHEME, profile).verdict == Verdict.ELIGIBLE


def test_ujjwala_14_point_self_declaration_is_eligible():
    profile = {
        "self": {
            "is_woman": True,
            "age": 25,
            "is_indian_citizen": True,
            "meets_14_point_self_declaration": True,
            "household_has_existing_lpg_connection": False,
        }
    }
    assert evaluate(PM_UJJWALA_SCHEME, profile).verdict == Verdict.ELIGIBLE


# --- Maharashtra Ladki Bahin ------------------------------------------------------------------

LADKI_BAHIN_SCHEME = Scheme.model_validate(MAHARASHTRA_LADKI_BAHIN)


def _ladki_bahin_base_profile() -> dict:
    return {
        "self": {
            "is_woman": True,
            "is_maharashtra_resident": True,
            "age": 30,
            "has_bank_account": True,
            "family_annual_income_inr": 200000,
            "paid_income_tax_last_assessment_year": False,
            "is_regular_govt_employee_or_pensioner": False,
            "other_govt_scheme_monthly_benefit_inr": 0,
            "holds_constitutional_or_political_post": False,
            "holds_govt_board_or_corporation_post": False,
            "owns_four_wheeler": False,
            "owned_vehicle_is_farm_tractor_only": False,
        },
        "family_members": [
            {
                "paid_income_tax_last_assessment_year": False,
                "is_regular_govt_employee_or_pensioner": False,
                "holds_constitutional_or_political_post": False,
                "holds_govt_board_or_corporation_post": False,
                "owns_four_wheeler": False,
                "owned_vehicle_is_farm_tractor_only": False,
            }
        ],
    }


def test_ladki_bahin_eligible_woman():
    profile = _ladki_bahin_base_profile()
    assert evaluate(LADKI_BAHIN_SCHEME, profile).verdict == Verdict.ELIGIBLE


def test_ladki_bahin_over_age_65_is_ineligible():
    profile = _ladki_bahin_base_profile()
    profile["self"]["age"] = 70
    assert evaluate(LADKI_BAHIN_SCHEME, profile).verdict == Verdict.INELIGIBLE


def test_ladki_bahin_four_wheeler_owner_is_ineligible():
    profile = _ladki_bahin_base_profile()
    profile["self"]["owns_four_wheeler"] = True
    assert evaluate(LADKI_BAHIN_SCHEME, profile).verdict == Verdict.INELIGIBLE


def test_ladki_bahin_tractor_only_exception_still_eligible():
    """Owning a farm tractor is explicitly carved out of the four-wheeler exclusion."""
    profile = _ladki_bahin_base_profile()
    profile["self"]["owns_four_wheeler"] = True
    profile["self"]["owned_vehicle_is_farm_tractor_only"] = True
    assert evaluate(LADKI_BAHIN_SCHEME, profile).verdict == Verdict.ELIGIBLE


def test_ladki_bahin_missing_income_data_is_undetermined():
    profile = _ladki_bahin_base_profile()
    del profile["self"]["family_annual_income_inr"]
    assert evaluate(LADKI_BAHIN_SCHEME, profile).verdict == Verdict.UNDETERMINED


def test_ladki_bahin_other_govt_scheme_benefit_over_threshold_is_ineligible():
    """03.07.2024 amendment: excluded if already receiving >=Rs.1,500/month from another govt scheme."""
    profile = _ladki_bahin_base_profile()
    profile["self"]["other_govt_scheme_monthly_benefit_inr"] = 1500
    assert evaluate(LADKI_BAHIN_SCHEME, profile).verdict == Verdict.INELIGIBLE


def test_ladki_bahin_mp_mla_family_member_is_ineligible():
    """Item 5(5): current/former MP or MLA — reuses PM-KISAN's holds_constitutional_or_political_post."""
    profile = _ladki_bahin_base_profile()
    profile["family_members"][0]["holds_constitutional_or_political_post"] = True
    assert evaluate(LADKI_BAHIN_SCHEME, profile).verdict == Verdict.INELIGIBLE


def test_ladki_bahin_govt_board_post_family_member_is_ineligible():
    """Item 5(6): Chairperson/Director/Member of a govt Board/Corporation — distinct from MP/MLA."""
    profile = _ladki_bahin_base_profile()
    profile["family_members"][0]["holds_govt_board_or_corporation_post"] = True
    assert evaluate(LADKI_BAHIN_SCHEME, profile).verdict == Verdict.INELIGIBLE


# --- PMMVY ------------------------------------------------------------------------------------

PMMVY_SCHEME = Scheme.model_validate(PMMVY)


def _pmmvy_base_profile() -> dict:
    return {
        "self": {
            "age": 25,
            "is_sc_st": False,
            "has_40_percent_or_more_disability": False,
            "is_bpl_household": True,
            "is_ab_pmjay_beneficiary": False,
            "is_e_shram_registered": False,
            "is_pm_kisan_beneficiary": False,
            "has_active_mgnrega_job_card": False,
            "family_annual_income_inr": 200000,
            "is_frontline_worker": False,
            "is_nfsa_ration_card_holder": False,
            "pregnancy_child_order": 1,
            "child_is_girl": False,
        }
    }


def test_pmmvy_bpl_first_child_is_eligible():
    profile = _pmmvy_base_profile()
    assert evaluate(PMMVY_SCHEME, profile).verdict == Verdict.ELIGIBLE


def test_pmmvy_second_child_boy_is_ineligible():
    """PMMVY 2.0's second-child extension only applies if the second child is a girl."""
    profile = _pmmvy_base_profile()
    profile["self"]["pregnancy_child_order"] = 2
    profile["self"]["child_is_girl"] = False
    assert evaluate(PMMVY_SCHEME, profile).verdict == Verdict.INELIGIBLE


def test_pmmvy_second_child_girl_is_eligible():
    profile = _pmmvy_base_profile()
    profile["self"]["pregnancy_child_order"] = 2
    profile["self"]["child_is_girl"] = True
    assert evaluate(PMMVY_SCHEME, profile).verdict == Verdict.ELIGIBLE


def test_pmmvy_third_child_is_ineligible():
    profile = _pmmvy_base_profile()
    profile["self"]["pregnancy_child_order"] = 3
    assert evaluate(PMMVY_SCHEME, profile).verdict == Verdict.INELIGIBLE


def test_pmmvy_under_18_is_ineligible():
    profile = _pmmvy_base_profile()
    profile["self"]["age"] = 16
    assert evaluate(PMMVY_SCHEME, profile).verdict == Verdict.INELIGIBLE


def test_pmmvy_over_55_is_ineligible():
    profile = _pmmvy_base_profile()
    profile["self"]["age"] = 60
    assert evaluate(PMMVY_SCHEME, profile).verdict == Verdict.INELIGIBLE


def test_pmmvy_no_category_membership_is_ineligible():
    """No category matches -> fails the category OR-tree even with valid age/parity."""
    profile = _pmmvy_base_profile()
    profile["self"]["is_bpl_household"] = False
    profile["self"]["family_annual_income_inr"] = 1000000
    assert evaluate(PMMVY_SCHEME, profile).verdict == Verdict.INELIGIBLE


def test_pmmvy_ab_pmjay_beneficiary_alone_is_eligible():
    """Cross-scheme category: AB-PMJAY beneficiary status alone qualifies, no BPL needed."""
    profile = _pmmvy_base_profile()
    profile["self"]["is_bpl_household"] = False
    profile["self"]["is_ab_pmjay_beneficiary"] = True
    assert evaluate(PMMVY_SCHEME, profile).verdict == Verdict.ELIGIBLE


def test_pmmvy_income_based_eligibility_alone_is_eligible():
    profile = _pmmvy_base_profile()
    profile["self"]["is_bpl_household"] = False
    profile["self"]["family_annual_income_inr"] = 750000
    assert evaluate(PMMVY_SCHEME, profile).verdict == Verdict.ELIGIBLE


def test_pmmvy_missing_parity_data_is_undetermined():
    profile = _pmmvy_base_profile()
    del profile["self"]["pregnancy_child_order"]
    assert evaluate(PMMVY_SCHEME, profile).verdict == Verdict.UNDETERMINED


# --- PMMVY age floor: 18 years 7 months, not 18 (gold fix, 2026-10-03) -------------------------
# Source: "between 18 years 7 months and 55 years of age". The gold had `age >= 18`, so women aged
# 18y0m-18y6m got a wrong ELIGIBLE -- the harmful direction. Ages are asked in whole years, so 18 is
# the one ambiguous value; only then is the months-since-last-birthday question needed.
# See docs/GOLD_AUDIT_2026-10-03.md section 6.2.


def _pmmvy_at(years: int, months: int | None) -> dict:
    profile = _pmmvy_base_profile()
    profile["self"]["age"] = years
    if months is not None:
        profile["self"]["months_since_last_birthday"] = months
    return profile


def test_pmmvy_eighteen_years_three_months_is_below_the_floor():
    assert evaluate(PMMVY_SCHEME, _pmmvy_at(18, 3)).verdict == Verdict.INELIGIBLE


def test_pmmvy_eighteen_years_six_months_is_below_the_floor():
    assert evaluate(PMMVY_SCHEME, _pmmvy_at(18, 6)).verdict == Verdict.INELIGIBLE


def test_pmmvy_eighteen_years_seven_months_is_exactly_the_floor():
    assert evaluate(PMMVY_SCHEME, _pmmvy_at(18, 7)).verdict == Verdict.ELIGIBLE


def test_pmmvy_eighteen_with_months_unknown_is_undetermined_not_eligible():
    """At 18 the whole-year age alone can't decide it -- the old gold said eligible."""
    assert evaluate(PMMVY_SCHEME, _pmmvy_at(18, None)).verdict == Verdict.UNDETERMINED


def test_pmmvy_nineteen_and_over_needs_no_months():
    assert evaluate(PMMVY_SCHEME, _pmmvy_at(19, None)).verdict == Verdict.ELIGIBLE


def test_pmmvy_seventeen_is_ineligible_without_asking_months():
    assert evaluate(PMMVY_SCHEME, _pmmvy_at(17, None)).verdict == Verdict.INELIGIBLE


def test_pmmvy_months_question_is_only_ever_asked_of_an_eighteen_year_old():
    """The question selector asks every unresolved leaf, including ones under an already-satisfied
    `or` (logged in KNOWN_ISSUES). The precise floor sits LAST in the conjunction so that, for anyone
    19 or over, the verdict is settled before it is ever reached."""
    from schemelogic.conversational.question_selector import select_next_question

    def asked_fields(start: dict) -> list[str]:
        profile = {"self": dict(start), "family_members": []}
        fields: list[str] = []
        while (q := select_next_question(PMMVY_SCHEME, profile)) is not None:
            fields.append(q.field)
            profile["self"][q.field] = {"pregnancy_child_order": 1, "months_since_last_birthday": 9}.get(
                q.field, False if q.answer_type == "boolean" else 100000
            )
        return fields

    assert "months_since_last_birthday" not in asked_fields({"age": 30, "is_bpl_household": True})
    assert "months_since_last_birthday" not in asked_fields({"age": 17})
    assert "months_since_last_birthday" in asked_fields({"age": 18, "is_bpl_household": True})


# --- PM-UJJWALA-2.0: citizenship is not a stated requirement (gold fix, 2026-10-03) ------------
# The gold gated eligibility on is_indian_citizen, but the source document never mentions
# citizenship and the gold's source_clause -- which documents every other uncertainty -- never
# sourced it. Both the extractor (Phase 3) and Baseline 2 were charged with errors for disagreeing
# with it. See docs/GOLD_AUDIT_2026-10-03.md section 6.3.


def test_ujjwala_non_citizen_meeting_every_stated_criterion_is_not_excluded():
    profile = {
        "self": {
            "is_woman": True,
            "age": 25,
            "is_indian_citizen": False,
            "is_bpl_household": True,
            "household_has_existing_lpg_connection": False,
        }
    }
    assert evaluate(PM_UJJWALA_SCHEME, profile).verdict == Verdict.ELIGIBLE


def test_ujjwala_citizenship_is_never_asked():
    """A requirement with no source must not cost the citizen a question either."""
    from schemelogic.conversational.question_selector import select_next_question

    profile = {"self": {"is_woman": True, "age": 25}, "family_members": []}
    asked: list[str] = []
    while (q := select_next_question(PM_UJJWALA_SCHEME, profile)) is not None:
        asked.append(q.field)
        profile["self"][q.field] = q.field == "is_bpl_household" if q.answer_type == "boolean" else 30
    assert "is_indian_citizen" not in asked



def test_every_gold_file_is_in_canonical_form():
    """Gold is written by models.dump_gold_json only (fields at their default omitted), so adding a
    defaulted field to the schema can't rewrite every file, and a hand edit that isn't canonical fails
    here instead of drifting. Fix with: PYTHONPATH=. python scripts/audit_gold.py format"""
    import json
    from pathlib import Path

    from schemelogic.schema.models import dump_gold_json

    for path in sorted((Path(__file__).resolve().parents[1] / "data" / "gold").glob("*.json")):
        text = path.read_text(encoding="utf-8")
        assert text == dump_gold_json(Scheme.model_validate(json.loads(text))), f"{path.name} is not canonical"


def test_except_scope_appears_in_gold_only_where_genuinely_applicant():
    import json
    from pathlib import Path

    for path in sorted((Path(__file__).resolve().parents[1] / "data" / "gold").glob("*.json")):
        # canonical form omits an empty exclusions list (IGNOAPS has none)
        for excl in json.loads(path.read_text(encoding="utf-8")).get("exclusions", []):
            if "except_scope" in excl:
                assert excl["except_scope"] == "applicant", f"{path.name}: member scope written explicitly"
                assert excl.get("quantifier", "self") != "self"
