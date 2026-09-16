"""Phase 0 step 4: hand-write gold scheme JSONs, confirm the evaluator gives correct verdicts
on hand-constructed profiles for each. See tests/gold_fixtures.py for the draft-status caveat."""

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
            "has_family_member_aged_70_or_above": False,
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
    del profile["self"]["has_family_member_aged_70_or_above"]
    assert evaluate(AB_PMJAY_SCHEME, profile).verdict == Verdict.UNDETERMINED


def test_pmjay_seventy_plus_family_member_eligible_regardless_of_secc():
    """2024 amendment: universal for 70+, irrespective of SECC/BPL status."""
    profile = _pmjay_base_profile()
    profile["self"]["is_secc_deprived_household"] = False
    profile["self"]["has_family_member_aged_70_or_above"] = True
    assert evaluate(AB_PMJAY_SCHEME, profile).verdict == Verdict.ELIGIBLE


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


def test_ignoaps_has_family_support_is_ineligible():
    profile = _ignoaps_base_profile()
    profile["self"]["has_regular_family_financial_support"] = True
    assert evaluate(IGNOAPS_SCHEME, profile).verdict == Verdict.INELIGIBLE


def test_ignoaps_missing_support_field_is_undetermined():
    profile = _ignoaps_base_profile()
    del profile["self"]["has_regular_family_financial_support"]
    assert evaluate(IGNOAPS_SCHEME, profile).verdict == Verdict.UNDETERMINED


def test_ignoaps_govt_employee_is_ineligible():
    """Para 2.4.3's exclusion-criteria aside, applied as a real IGNOAPS exclusion."""
    profile = _ignoaps_base_profile()
    profile["self"]["is_govt_employee"] = True
    assert evaluate(IGNOAPS_SCHEME, profile).verdict == Verdict.INELIGIBLE


def test_ignoaps_five_acres_land_is_ineligible():
    profile = _ignoaps_base_profile()
    profile["self"]["family_agricultural_land_acres"] = 5
    assert evaluate(IGNOAPS_SCHEME, profile).verdict == Verdict.INELIGIBLE


def test_ignoaps_under_five_acres_land_is_eligible():
    profile = _ignoaps_base_profile()
    profile["self"]["family_agricultural_land_acres"] = 4.99
    assert evaluate(IGNOAPS_SCHEME, profile).verdict == Verdict.ELIGIBLE


def test_ignoaps_four_wheeler_owner_is_ineligible():
    profile = _ignoaps_base_profile()
    profile["self"]["owns_four_wheeler"] = True
    assert evaluate(IGNOAPS_SCHEME, profile).verdict == Verdict.INELIGIBLE


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
