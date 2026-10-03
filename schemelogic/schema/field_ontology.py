"""Canonical predicate-field vocabulary, seeded from the fields actually used across the 6
existing gold scheme JSONs in data/gold/ (PM-KISAN, verified; AB-PMJAY, IGNOAPS, PMAY-G,
PM-UJJWALA-2.0, MH-LADKI-BAHIN, draft).

Problem this solves: independent LLM extraction runs invent their own field spellings for the
same real-world concept (e.g. the gpt-oss-120b PM-KISAN draft used `government_employee` where
gold uses `is_serving_or_retired_govt_employee`, `monthly_pension` vs `monthly_pension_inr`,
`citizenship_status=="NRI"` vs `is_nri_per_income_tax_act_1961`). That's not a reasoning error —
it's vocabulary drift — but it makes structural field-name diffing useless and forces
outcome-equivalence testing to hand-author dual-vocabulary profiles per scheme, which doesn't
scale. This module is the fixed target vocabulary the extractor prompt is built from, so
independent runs converge on the same field names for the same concepts.

Naming convention: snake_case, `is_`/`has_`/`owns_`/`holds_`/`paid_` prefixes for booleans (matches
the style already used consistently across all 6 gold schemes), `_inr` suffix for INR amounts.
No dotted `<entity>.<attribute>` notation — the existing flat snake_case style was already
consistent across all 6 schemes, so introducing a second convention would itself be a source of
drift rather than a fix.

Deliberately NOT organized as a hard enum on the Predicate.field type: a controlled vocabulary
that hard-rejects anything outside it just converts "silent invention" into "silent failure" (the
extraction would error out instead of producing a usable draft). Instead: the extractor prompt is
built from this list and asked to prefer it, and SimplePredicate.ontology_proposed (see
schema/models.py) lets it explicitly flag a genuinely new field instead of inventing one quietly.
Promoting a proposed field to canonical means adding it here by hand after a human looks at it —
that's the "defined process," not silent proliferation.
"""

from __future__ import annotations

from dataclasses import dataclass

from schemelogic.schema.models import PredicateCategory

ValueType = str  # "boolean" | "number" | "string" | "date" — informal, not enforced by Pydantic


@dataclass(frozen=True)
class FieldSpec:
    name: str
    cat: PredicateCategory
    value_type: ValueType
    description: str
    schemes: tuple[str, ...]  # gold scheme(s) currently using this field
    citizen_question: str  # plain-language question a non-technical citizen can answer directly
    # -- NEVER the technical `description` above. question_selector.py uses this, never
    # `description`, for anything shown as a primary chat question (Part A, readability pass).
    display_label: str  # plain-language label for this field in a citizen-facing rule trace --
    # e.g. "Household deprivation status", not `is_secc_deprived_household`. rendering.py's
    # citizen-facing trace view uses this; the raw field name/description stay available only in
    # a separate "technical detail" expander, never inline in the main conversational text.
    draft_aliases: tuple[str, ...] = ()  # divergent spellings an independent LLM draft used instead


_FIELDS: tuple[FieldSpec, ...] = (
    # --- citizenship -----------------------------------------------------------------------
    FieldSpec(
        "is_indian_citizen", PredicateCategory.CITIZENSHIP, "boolean",
        "Applicant holds Indian citizenship.",
        schemes=("PM-KISAN", "PM-UJJWALA-2.0"),
        # PM-KISAN's primary source doesn't state this as a standalone clause (it's inferred
        # from the NRI exclusion) — the gpt-oss-120b draft never extracted it at all, so there's
        # no draft spelling to alias here; that's a missed-predicate problem, not a naming one.
        citizen_question="Are you an Indian citizen?",
        display_label="Indian citizenship",
    ),
    FieldSpec(
        "is_nri_per_income_tax_act_1961", PredicateCategory.CITIZENSHIP, "boolean",
        "Applicant/family is a Non-Resident Indian per the Income Tax Act, 1961.",
        schemes=("PM-KISAN",),
        draft_aliases=("citizenship_status",),  # draft used citizenship_status=="NRI" (string enum, not boolean)
        citizen_question="Are you classified as a Non-Resident Indian (NRI) under Indian income tax rules?",
        display_label="NRI status",
    ),

    # --- demographic -------------------------------------------------------------------------
    FieldSpec(
        "age", PredicateCategory.DEMOGRAPHIC, "number",
        "Applicant's age in years.",
        schemes=("IGNOAPS", "MH-LADKI-BAHIN", "PM-UJJWALA-2.0", "PMMVY"),
        citizen_question="What is your age, in years?",
        display_label="Age",
    ),
    FieldSpec(
        "is_widow_suffering_from_aids", PredicateCategory.DEMOGRAPHIC, "boolean",
        "Applicant is a widow living with HIV/AIDS. Gates the NSAP Para 2.4.3 carve-out: such widows "
        "may be considered without BPL status if they are clear of the stated exclusion criteria "
        "(government job, 5+ acres of land, a four-wheeler for own use). Added 2026-10-03 "
        "(docs/GOLD_AUDIT_2026-10-03.md section 6.4).",
        schemes=("IGNOAPS",),
        citizen_question="Are you a widow living with HIV or AIDS? (This is asked only because it can "
                         "make you eligible even without a BPL card.)",
        display_label="Widow living with HIV/AIDS",
    ),
    FieldSpec(
        "months_since_last_birthday", PredicateCategory.DEMOGRAPHIC, "number",
        "Whole months elapsed since the applicant's most recent birthday (0-11). Pairs with `age` "
        "(whole years) to express an age threshold that isn't a whole number of years -- PMMVY's "
        "floor is 18 years 7 months, so at age 18 exactly, whole years alone can't decide it. "
        "Added 2026-10-03 (docs/GOLD_AUDIT_2026-10-03.md section 6.2).",
        schemes=("PMMVY",),
        citizen_question="How many full months have passed since your last birthday? (0 to 11)",
        display_label="Months since last birthday",
    ),
    FieldSpec(
        "is_woman", PredicateCategory.DEMOGRAPHIC, "boolean",
        "Applicant is a woman.",
        schemes=("MH-LADKI-BAHIN", "PM-UJJWALA-2.0"),
        citizen_question="Are you a woman?",
        display_label="Gender: woman",
    ),
    FieldSpec(
        "is_maharashtra_resident", PredicateCategory.DEMOGRAPHIC, "boolean",
        "Applicant is a permanent resident of Maharashtra. State-specific — follow the "
        "is_<state>_resident pattern for other state schemes rather than a generic field.",
        schemes=("MH-LADKI-BAHIN",),
        citizen_question="Are you a permanent resident of Maharashtra?",
        display_label="Maharashtra residency",
    ),
    FieldSpec(
        "has_family_member_aged_70_or_above", PredicateCategory.DEMOGRAPHIC, "boolean",
        "At least one family member is aged 70 or above.",
        schemes=("AB-PMJAY",),
        citizen_question="Does anyone in your family belong to your household and is 70 years of age or older?",
        display_label="Senior citizen (70+) in family",
    ),
    FieldSpec(
        "is_sc_st_pmay_g_beneficiary", PredicateCategory.DEMOGRAPHIC, "boolean",
        "RETIRED during PM-UJJWALA-2.0's Phase 3 primary-source verification (2026-08): "
        "multiple corroborating secondary sources describe 'seven more categories' added under "
        "Ujjwala 2.0 as SC/ST households and PMAY-Gramin beneficiaries SEPARATELY, not a single "
        "compound SC/ST-AND-PMAY-G category — split into is_sc_st and is_pmay_g_beneficiary. Kept "
        "in the ontology only as a documentation/traceability target, same pattern as "
        "family_agricultural_land_acres.",
        schemes=(),
        citizen_question="(Retired field — split into is_sc_st and is_pmay_g_beneficiary; not asked directly.)",
        display_label="SC/ST + PMAY-G beneficiary (retired field)",
    ),
    FieldSpec(
        "is_sc_st", PredicateCategory.DEMOGRAPHIC, "boolean",
        "Applicant's household is Scheduled Caste (SC) or Scheduled Tribe (ST) — one of Ujjwala "
        "2.0's added inclusion categories, separate from PMAY-G beneficiary status.",
        schemes=("PM-UJJWALA-2.0",),
        citizen_question="Does your household belong to a Scheduled Caste (SC) or Scheduled Tribe (ST)?",
        display_label="SC/ST status",
    ),
    FieldSpec(
        "is_pmay_g_beneficiary", PredicateCategory.DEMOGRAPHIC, "boolean",
        "Applicant's household is a Pradhan Mantri Awaas Yojana - Gramin beneficiary — one of "
        "Ujjwala 2.0's added inclusion categories, separate from SC/ST status.",
        schemes=("PM-UJJWALA-2.0",),
        citizen_question="Is your household already a beneficiary of the PMAY-Gramin (rural housing) scheme?",
        display_label="PMAY-G beneficiary status",
    ),
    FieldSpec(
        "is_forest_dweller", PredicateCategory.DEMOGRAPHIC, "boolean",
        "Applicant is a forest dweller.", schemes=("PM-UJJWALA-2.0",),
        citizen_question="Are you recognized as a forest dweller?",
        display_label="Forest dweller status",
    ),
    FieldSpec(
        "is_most_backward_class", PredicateCategory.DEMOGRAPHIC, "boolean",
        "Applicant belongs to a Most Backward Class category.", schemes=("PM-UJJWALA-2.0",),
        citizen_question="Do you belong to a community classified as a Most Backward Class?",
        display_label="Most Backward Class status",
    ),
    FieldSpec(
        "is_tea_garden_tribe", PredicateCategory.DEMOGRAPHIC, "boolean",
        "Applicant belongs to a Tea & Ex-Tea Garden Tribe.", schemes=("PM-UJJWALA-2.0",),
        citizen_question="Do you belong to a Tea or Ex-Tea Garden Tribe community?",
        display_label="Tea garden tribe status",
    ),
    FieldSpec(
        "lives_on_river_island", PredicateCategory.DEMOGRAPHIC, "boolean",
        "Applicant lives on a river island. Renamed from lives_on_river_island_without_lpg during "
        "Phase 3 verification — the 'without LPG' qualifier was redundant with the scheme's "
        "separate, already-modeled household_has_existing_lpg_connection exclusion; no other "
        "inclusion branch bakes that same condition into its own field name.",
        schemes=("PM-UJJWALA-2.0",),
        citizen_question="Do you live on a river island?",
        display_label="River island residency",
    ),
    FieldSpec(
        "meets_14_point_self_declaration", PredicateCategory.ECONOMIC, "boolean",
        "Applicant's household submitted Ujjwala 2.0's 14-point self-declaration form claiming "
        "poor-household status — the fallback inclusion route for households not otherwise "
        "covered by SECC 2011, BPL, or the seven added categories.",
        schemes=("PM-UJJWALA-2.0",),
        citizen_question="If none of the other categories apply to you, would you be able to submit a self-declaration form stating your household is poor?",
        display_label="Self-declared poor household",
    ),

    # --- economic ------------------------------------------------------------------------------
    FieldSpec(
        "is_secc_deprived_household", PredicateCategory.ECONOMIC, "boolean",
        "Household meets one of SECC 2011's 6 rural deprivation criteria used by AB-PMJAY "
        "targeting (D1/D2/D3/D4/D5/D7 — PM-JAY deliberately excludes D6 'no literate adult over "
        "25' from its own targeting). Urban occupational-worker categories are a separate "
        "inclusion path — see is_urban_informal_worker.",
        schemes=("AB-PMJAY",),
        citizen_question="Does your household fall under one of the government's official rural poverty-deprivation categories (for example: no adult wage-earner, a female-headed household with no adult male, a disabled member with no able-bodied adult, or a landless household relying on manual labour)?",
        display_label="Household deprivation status",
    ),
    FieldSpec(
        "is_secc_automatically_included", PredicateCategory.ECONOMIC, "boolean",
        "Household meets one of SECC 2011's automatic-inclusion parameters: shelterless; "
        "destitute/living on alms; manual scavenger family; primitive tribal group; legally "
        "released bonded labour. AB-PMJAY uses all 5 (shelterless as its own umbrella-included "
        "case). PMAY-G's own 'compulsory inclusion' list (PIB Research Unit backgrounder, "
        "2024-11-19) has the same 4 non-shelterless categories — shelterless is instead covered "
        "there by the separate is_houseless field, so treat this field as 'destitute/manual "
        "scavenger/primitive tribal/bonded labour' for PMAY-G specifically.",
        schemes=("AB-PMJAY", "PMAY-G"),
        citizen_question="Does your household fall into one of the automatically-included categories: destitute/living on alms, a manual scavenger family, a primitive tribal group, or a legally released bonded labourer family?",
        display_label="Automatic inclusion category",
    ),
    FieldSpec(
        "is_valid_rsby_beneficiary", PredicateCategory.ECONOMIC, "boolean",
        "Family is a valid, premium-paid RSBY (Rashtriya Swasthya Bima Yojana) enrollee not "
        "otherwise featured in the SECC-targeted groups.",
        schemes=("AB-PMJAY",),
        citizen_question="Is your family a valid, premium-paid beneficiary of the earlier RSBY health insurance scheme?",
        display_label="RSBY beneficiary status",
    ),
    FieldSpec(
        "is_bpl_household", PredicateCategory.ECONOMIC, "boolean",
        "Household is classified Below Poverty Line.",
        schemes=("IGNOAPS", "PM-UJJWALA-2.0", "PMMVY"),
        citizen_question="Is your household officially classified as Below Poverty Line (BPL)?",
        display_label="Below Poverty Line (BPL) status",
    ),
    FieldSpec(
        "paid_income_tax_last_assessment_year", PredicateCategory.ECONOMIC, "boolean",
        "Person paid income tax in the last assessment year.",
        schemes=("PM-KISAN", "AB-PMJAY", "MH-LADKI-BAHIN", "PMAY-G"),
        draft_aliases=("paid_income_tax_last_year",),
        citizen_question="Did you or a family member pay income tax in the last assessment year?",
        display_label="Income tax payment",
    ),
    FieldSpec(
        "household_owns_motorised_vehicle_or_fishing_boat", PredicateCategory.ECONOMIC, "boolean",
        "Household owns a motorised vehicle or fishing boat.", schemes=("AB-PMJAY",),
        citizen_question="Does your household own a motorised vehicle or a fishing boat?",
        display_label="Motorised vehicle or fishing boat ownership",
    ),
    FieldSpec(
        "kisan_credit_card_limit_inr", PredicateCategory.ECONOMIC, "number",
        "Kisan Credit Card sanctioned limit, in INR.", schemes=("AB-PMJAY", "PMAY-G"),
        citizen_question="What is the sanctioned limit on your Kisan Credit Card, in rupees? (Enter 0 if you don't have one.)",
        display_label="Kisan Credit Card limit",
    ),
    FieldSpec(
        "owns_mechanized_agricultural_equipment_3_or_4_wheeler", PredicateCategory.ECONOMIC, "boolean",
        "Household owns mechanized 3- or 4-wheeler agricultural equipment (SECC exclusion "
        "parameter ii).", schemes=("AB-PMJAY", "PMAY-G"),
        citizen_question="Does your household own mechanised 3-wheeler or 4-wheeler agricultural equipment, like a tractor?",
        display_label="Mechanised agricultural equipment ownership",
    ),
    FieldSpec(
        "owns_non_agricultural_enterprise_registered_with_govt", PredicateCategory.ECONOMIC, "boolean",
        "Household owns a non-agricultural enterprise registered with the government (SECC "
        "exclusion parameter v).", schemes=("AB-PMJAY", "PMAY-G"),
        citizen_question="Does your household own a non-agricultural business registered with the government?",
        display_label="Registered non-agricultural business",
    ),
    FieldSpec(
        "monthly_income_inr", PredicateCategory.ECONOMIC, "number",
        "A family member's monthly income, in INR (SECC exclusion parameter vi; threshold varies "
        "by scheme — AB-PMJAY: >Rs.10,000/month; PMAY-G: >Rs.15,000/month as of the Sept-2024 "
        "revision, up from Rs.10,000). PMAY-G's earlier draft gold used a separate "
        "monthly_household_income_inr field (self-scoped, household-level) — reclassified to this "
        "shared field (some_family_member-scoped) during PMAY-G's Phase 3 primary-source "
        "verification, since PMAY-G's exclusion criteria are drawn from the same SECC 2011 "
        "automatic-exclusion parameter set as AB-PMJAY's, and the per-member framing matches "
        "SECC's own parameter vi wording more closely than a household-aggregate figure.",
        schemes=("AB-PMJAY", "PMAY-G"),
        citizen_question="What is the monthly income, in rupees?",
        display_label="Monthly income",
    ),
    FieldSpec(
        "paid_professional_tax", PredicateCategory.ECONOMIC, "boolean",
        "Family member pays professional tax (SECC exclusion parameter viii).", schemes=("AB-PMJAY",),
        citizen_question="Does your family pay professional tax?",
        display_label="Professional tax payment",
    ),
    FieldSpec(
        "house_has_3_or_more_pucca_rooms", PredicateCategory.ECONOMIC, "boolean",
        "Household has 3 or more rooms with pucca (permanent) walls and roof (SECC exclusion "
        "parameter ix).", schemes=("AB-PMJAY",),
        citizen_question="Does your house have 3 or more rooms built with permanent (pucca) walls and roof?",
        display_label="Pucca house room count",
    ),
    FieldSpec(
        "owns_refrigerator", PredicateCategory.ECONOMIC, "boolean",
        "Household owns a refrigerator (SECC exclusion parameter x).",
        schemes=("AB-PMJAY", "PMAY-G"),
        citizen_question="Does your household own a refrigerator?",
        display_label="Refrigerator ownership",
    ),
    FieldSpec(
        "owns_landline_phone", PredicateCategory.ECONOMIC, "boolean",
        "Household owns a landline phone (SECC exclusion parameter xi).",
        schemes=("AB-PMJAY", "PMAY-G"),
        citizen_question="Does your household own a landline telephone?",
        display_label="Landline phone ownership",
    ),
    FieldSpec(
        "owns_gt_2_5_acres_irrigated_land_with_irrigation_equipment", PredicateCategory.ECONOMIC, "boolean",
        "Household owns more than 2.5 acres of irrigated land with at least 1 irrigation "
        "equipment (SECC exclusion parameter xii — a compound fact, folded into one boolean "
        "since exclusion predicates can only test a single field, not an AND of two).",
        schemes=("AB-PMJAY",),
        citizen_question="Does your household own more than 2.5 acres of irrigated land, along with irrigation equipment?",
        display_label="Irrigated land with equipment (>2.5 acres)",
    ),
    FieldSpec(
        "owns_gt_2_5_acres_irrigated_land", PredicateCategory.ECONOMIC, "boolean",
        "Household owns more than 2.5 acres of irrigated land. PMAY-G's own summary phrasing of "
        "this exclusion, per a PIB Research Unit backgrounder, doesn't carry AB-PMJAY's additional "
        "irrigation-equipment qualifier — kept as a SEPARATE, simpler field rather than reused "
        "under owns_gt_2_5_acres_irrigated_land_with_irrigation_equipment, since that would assert "
        "an unstated qualifier. Genuine uncertainty: PMAY-G draws its exclusion parameters from "
        "the same SECC 2011 set as AB-PMJAY, so the actual notification may carry the same "
        "compound wording — the backgrounder used to verify this is a PR summary, not the "
        "verbatim numbered official list, which could not be retrieved.",
        schemes=("PMAY-G",),
        citizen_question="Does your household own more than 2.5 acres of irrigated land?",
        display_label="Irrigated land ownership (>2.5 acres)",
    ),
    FieldSpec(
        "owns_5_or_more_acres_irrigated_land_two_or_more_crop_seasons", PredicateCategory.ECONOMIC, "boolean",
        "Household owns 5 or more acres of irrigated land used for two or more crop seasons "
        "(SECC exclusion parameter xiii — compound fact, same reasoning as above).",
        schemes=("AB-PMJAY",),
        citizen_question="Does your household own 5 or more acres of irrigated land used for two or more crop seasons a year?",
        display_label="Irrigated land, multi-season (5+ acres)",
    ),
    FieldSpec(
        "owns_7_5_or_more_acres_land_with_irrigation_equipment", PredicateCategory.ECONOMIC, "boolean",
        "Household owns at least 7.5 acres of land with at least one irrigation equipment (SECC "
        "exclusion parameter xiv — compound fact, same reasoning as above).",
        schemes=("AB-PMJAY",),
        citizen_question="Does your household own at least 7.5 acres of land, along with irrigation equipment?",
        display_label="Large landholding with irrigation equipment (7.5+ acres)",
    ),
    FieldSpec(
        "has_regular_family_financial_support", PredicateCategory.ECONOMIC, "boolean",
        "Applicant has a regular source of financial support from family/elsewhere.",
        schemes=("IGNOAPS",),
        citizen_question="Do you have a regular source of financial support from family or elsewhere?",
        display_label="Regular family financial support",
    ),
    FieldSpec(
        "has_aadhaar_linked_bank_account", PredicateCategory.ECONOMIC, "boolean",
        "Applicant's bank account is Aadhaar-linked.", schemes=("MH-LADKI-BAHIN",),
        citizen_question="Is your bank account linked to your Aadhaar number?",
        display_label="Aadhaar-linked bank account",
    ),
    FieldSpec(
        "family_annual_income_inr", PredicateCategory.ECONOMIC, "number",
        "Combined family annual income, in INR.", schemes=("MH-LADKI-BAHIN", "PMMVY"),
        citizen_question="What is your family's combined annual income, in rupees?",
        display_label="Family annual income",
    ),
    FieldSpec(
        "has_40_percent_or_more_disability", PredicateCategory.DEMOGRAPHIC, "boolean",
        "Applicant has a partial (>=40%) or full disability certificate.", schemes=("PMMVY",),
        citizen_question="Do you have a disability certificate showing 40% or more disability?",
        display_label="Disability status (40%+)",
    ),
    FieldSpec(
        "is_ab_pmjay_beneficiary", PredicateCategory.CROSS_SCHEME, "boolean",
        "Applicant is a beneficiary under AB-PMJAY (Ayushman Bharat ID) — a genuine "
        "cross-scheme eligibility dependency: PMMVY treats AB-PMJAY beneficiary status as one "
        "of its own inclusion categories.",
        schemes=("PMMVY",),
        citizen_question="Is your family already a beneficiary of the Ayushman Bharat (AB-PMJAY) health scheme?",
        display_label="Ayushman Bharat (AB-PMJAY) beneficiary status",
    ),
    FieldSpec(
        "is_pm_kisan_beneficiary", PredicateCategory.CROSS_SCHEME, "boolean",
        "Applicant's household is a beneficiary under PM-KISAN — another cross-scheme "
        "eligibility dependency, same shape as is_ab_pmjay_beneficiary.",
        schemes=("PMMVY",),
        citizen_question="Is your household already a beneficiary of the PM-KISAN scheme?",
        display_label="PM-KISAN beneficiary status",
    ),
    FieldSpec(
        "is_e_shram_registered", PredicateCategory.ECONOMIC, "boolean",
        "Applicant holds an e-Shram card (Ministry of Labour unorganised-worker registry).",
        schemes=("PMMVY",),
        citizen_question="Do you hold an e-Shram card (the government's unorganised-worker registration)?",
        display_label="e-Shram registration",
    ),
    FieldSpec(
        "has_active_mgnrega_job_card", PredicateCategory.ECONOMIC, "boolean",
        "Applicant's household holds an active MGNREGA job card.", schemes=("PMMVY",),
        citizen_question="Does your household hold an active MGNREGA job card?",
        display_label="MGNREGA job card status",
    ),
    FieldSpec(
        "is_frontline_worker", PredicateCategory.OCCUPATION, "boolean",
        "Applicant is engaged as a frontline worker (Anganwadi Worker/Helper or ASHA).",
        schemes=("PMMVY",),
        citizen_question="Are you employed as a frontline worker, such as an Anganwadi worker/helper or ASHA worker?",
        display_label="Frontline worker status",
    ),
    FieldSpec(
        "is_nfsa_ration_card_holder", PredicateCategory.ECONOMIC, "boolean",
        "Applicant's household holds a ration card covered under the National Food Security "
        "Act, 2013.", schemes=("PMMVY",),
        citizen_question="Does your household hold a ration card covered under the National Food Security Act?",
        display_label="NFSA ration card status",
    ),
    FieldSpec(
        "pregnancy_child_order", PredicateCategory.DEMOGRAPHIC, "number",
        "Which living-child number this pregnancy/birth represents for the applicant (1 = "
        "first child, 2 = second child, etc.).", schemes=("PMMVY",),
        citizen_question="For this pregnancy or birth, which child is this for you — first, second, etc.? (Enter the number.)",
        display_label="Child order (this pregnancy/birth)",
    ),
    FieldSpec(
        "child_is_girl", PredicateCategory.DEMOGRAPHIC, "boolean",
        "Whether the child from this pregnancy/birth is a girl — relevant only when "
        "pregnancy_child_order == 2 (PMMVY 2.0's second-child-if-girl extension).",
        schemes=("PMMVY",),
        citizen_question="Is the child from this pregnancy/birth a girl?",
        display_label="Child's gender (this pregnancy/birth)",
    ),
    FieldSpec(
        "owns_four_wheeler", PredicateCategory.ECONOMIC, "boolean",
        "Family owns a private four-wheeler.", schemes=("MH-LADKI-BAHIN",),
        citizen_question="Does your family own a private four-wheeler, such as a car or SUV?",
        display_label="Four-wheeler ownership",
    ),
    FieldSpec(
        "owned_vehicle_is_farm_tractor_only", PredicateCategory.ECONOMIC, "boolean",
        "The owned four-wheeler is a farm tractor only (except-clause target for owns_four_wheeler).",
        schemes=("MH-LADKI-BAHIN",),
        citizen_question="Is the four-wheeler your family owns only a farm tractor, and not a car or other vehicle?",
        display_label="Four-wheeler is a farm tractor only",
    ),
    FieldSpec(
        "has_bank_account", PredicateCategory.ECONOMIC, "boolean",
        "Applicant has a bank account (not necessarily Aadhaar-linked — that's a separate "
        "disbursement-mechanism concern, see operational_requirements).",
        schemes=("MH-LADKI-BAHIN",),
        citizen_question="Do you have a bank account?",
        display_label="Bank account status",
    ),
    FieldSpec(
        "other_govt_scheme_monthly_benefit_inr", PredicateCategory.ECONOMIC, "number",
        "Monthly benefit amount the applicant already receives from another government "
        "financial scheme, in INR.", schemes=("MH-LADKI-BAHIN",),
        citizen_question="How much do you already receive per month from another government financial scheme, in rupees? (Enter 0 if none.)",
        display_label="Other government scheme monthly benefit",
    ),
    FieldSpec(
        "family_agricultural_land_acres", PredicateCategory.ECONOMIC, "number",
        "Combined agricultural landholding of the family, in acres. Retained in the ontology "
        "as a documentation/traceability target for temporal_validity.supersedes.retired_predicate "
        "references (Predicate typing isn't enforced inside that dict) — not currently used as a "
        "live predicate in any gold scheme.",
        schemes=(),
        citizen_question="(Retired field — not asked directly; kept only for internal traceability.)",
        display_label="Family agricultural landholding (retired field)",
    ),
    FieldSpec(
        "monthly_pension_inr", PredicateCategory.ECONOMIC, "number",
        "Monthly pension amount, in INR.", schemes=("PM-KISAN",),
        draft_aliases=("monthly_pension",),
        citizen_question="What is your monthly pension amount, in rupees? (Enter 0 if you don't receive a pension.)",
        display_label="Monthly pension",
    ),
    FieldSpec(
        "is_houseless", PredicateCategory.ECONOMIC, "boolean",
        "Family has no house.", schemes=("PMAY-G",),
        citizen_question="Does your family currently have no house at all?",
        display_label="Houseless status",
    ),
    FieldSpec(
        "lives_in_kutcha_house", PredicateCategory.ECONOMIC, "boolean",
        "Family lives in a kutcha (non-permanent) house.", schemes=("PMAY-G",),
        citizen_question="Does your family live in a kutcha house — one made of non-permanent materials like mud, thatch, or loose brick?",
        display_label="Kutcha house residency",
    ),
    FieldSpec(
        "monthly_household_income_inr", PredicateCategory.ECONOMIC, "number",
        "RETIRED for PMAY-G during Phase 3 primary-source verification (2026-08) in favor of the "
        "shared monthly_income_inr field (see its docstring) — kept in the ontology only as a "
        "documentation/traceability target, same pattern as family_agricultural_land_acres.",
        schemes=(),
        citizen_question="(Retired field — replaced by monthly_income_inr; not asked directly.)",
        display_label="Monthly household income (retired field)",
    ),
    FieldSpec(
        "owns_motorised_three_or_four_wheeler", PredicateCategory.ECONOMIC, "boolean",
        "Household owns a motorised three- or four-wheeler.", schemes=("PMAY-G",),
        citizen_question="Does your household own a motorised three-wheeler or four-wheeler?",
        display_label="Motorised 3/4-wheeler ownership",
    ),
    FieldSpec(
        "owns_pucca_house", PredicateCategory.ECONOMIC, "boolean",
        "Household already owns a pucca (permanent) house.", schemes=("PMAY-G",),
        citizen_question="Does your household already own a pucca (permanent) house?",
        display_label="Pucca house ownership",
    ),
    FieldSpec(
        "is_aay_beneficiary", PredicateCategory.ECONOMIC, "boolean",
        "Household is an Antyodaya Anna Yojana beneficiary.", schemes=("PM-UJJWALA-2.0",),
        citizen_question="Is your household a beneficiary of the Antyodaya Anna Yojana (AAY) scheme?",
        display_label="Antyodaya Anna Yojana (AAY) beneficiary status",
    ),
    FieldSpec(
        "is_in_secc_2011_list", PredicateCategory.ECONOMIC, "boolean",
        "Household appears in the SECC 2011 list.", schemes=("PM-UJJWALA-2.0",),
        citizen_question="Does your household appear in the government's SECC 2011 survey list?",
        display_label="SECC 2011 listing",
    ),

    # --- occupation ------------------------------------------------------------------------------
    FieldSpec(
        "owns_cultivable_land_in_records", PredicateCategory.OCCUPATION, "boolean",
        "Family owns cultivable land per official state land records.", schemes=("PM-KISAN",),
        # draft split this one concept into two vaguer predicates (family_type=="farmer" AND
        # land_records_verified==true) rather than a single misnamed field — no clean 1:1 alias.
        citizen_question="Does your family own cultivable land according to official state land records?",
        display_label="Cultivable landholding (official records)",
    ),
    FieldSpec(
        "is_serving_or_retired_govt_employee", PredicateCategory.OCCUPATION, "boolean",
        "Family member is a serving or retired government officer/employee (per PM-KISAN Para "
        "4.1(b)(iii) scope: Central/State ministries, PSEs, autonomous institutions, local bodies).",
        schemes=("PM-KISAN",),
        draft_aliases=("government_employee",),
        citizen_question="Is any family member a serving or retired government employee, at a central/state ministry, public-sector undertaking, or local body?",
        display_label="Government employment status",
    ),
    FieldSpec(
        "is_regular_govt_employee_or_pensioner", PredicateCategory.OCCUPATION, "boolean",
        "Family member is a regular/permanent govt employee or pensioner.",
        schemes=("MH-LADKI-BAHIN",),
        citizen_question="Is any family member a regular/permanent government employee or a government pensioner?",
        display_label="Regular government employee/pensioner status",
    ),
    FieldSpec(
        "is_govt_employee", PredicateCategory.OCCUPATION, "boolean",
        "Family member is a government employee (unqualified/general scope; SECC exclusion "
        "parameter iv verbatim: 'Household member government employee'). Retired the earlier "
        "is_govt_employee_with_separate_health_scheme field during AB-PMJAY's primary-source "
        "re-verification (2026-08) — that qualifier wasn't literally in the SECC exclusion "
        "wording, and this field already existed for PMAY-G, so reused rather than duplicated.",
        schemes=("PMAY-G", "AB-PMJAY"),
        citizen_question="Is any family member a government employee?",
        display_label="Government employment status",
    ),
    FieldSpec(
        "is_group_d_class_iv_or_mts", PredicateCategory.OCCUPATION, "boolean",
        "Employee is Multi Tasking Staff / Class IV / Group D — the standard exception carve-out "
        "on govt-employee and pensioner exclusions across PM-KISAN Para 4.1(b)(iii)-(iv).",
        schemes=("PM-KISAN",),
        draft_aliases=("employee_group",),  # draft used employee_group in [...] (list-membership, not boolean)
        citizen_question="Is that family member specifically a Group D, Class IV, or Multi-Tasking Staff (MTS) employee?",
        display_label="Group D / Class IV / MTS employee status",
    ),
    FieldSpec(
        "is_urban_informal_worker", PredicateCategory.OCCUPATION, "boolean",
        "Applicant falls under one of SECC 2011's urban informal-worker occupational categories "
        "(rag picker, beggar, domestic worker, street vendor/cobbler/hawker, construction worker, "
        "sweeper/sanitation worker, home-based worker/artisan, transport worker, shop worker/"
        "assistant, electrician/mechanic, washer-man/chowkidar, and similar) — a separate "
        "inclusion path from the rural is_secc_deprived_household criteria.",
        schemes=("AB-PMJAY",),
        citizen_question="Do you work in an urban informal occupation — for example, rag picker, domestic worker, street vendor, construction worker, or sanitation worker?",
        display_label="Urban informal worker status",
    ),

    # --- political ------------------------------------------------------------------------------
    FieldSpec(
        "holds_constitutional_or_political_post", PredicateCategory.POLITICAL, "boolean",
        "Family member holds/held a constitutional post, or an elected political office "
        "(Minister/MP/MLA/MLC/Mayor/District Panchayat Chairperson).",
        schemes=("PM-KISAN",),
        draft_aliases=("holds_constitutional_post", "holds_political_office"),  # draft split into two
        citizen_question="Does any family member hold or has held a constitutional post or elected political office, such as Minister, MP, MLA, MLC, or Mayor?",
        display_label="Constitutional or elected political post",
    ),
    FieldSpec(
        "holds_govt_board_or_corporation_post", PredicateCategory.POLITICAL, "boolean",
        "Family member is Chairperson/Vice-Chairperson/Director/Member of a Central or State "
        "Government Board/Corporation/Undertaking — distinct from holds_constitutional_or_"
        "political_post (elected legislative office): this is an appointed/nominated post.",
        schemes=("MH-LADKI-BAHIN",),
        # Replaces the earlier holds_elected_or_nominated_govt_post field, which conflated this
        # with the MP/MLA concept already covered by holds_constitutional_or_political_post —
        # retired during MH-LADKI-BAHIN's primary-source re-verification (2026-08-18).
        citizen_question="Does any family member serve as Chairperson, Vice-Chairperson, Director, or Member of a government Board or Corporation?",
        display_label="Government board/corporation post",
    ),

    # --- professional ------------------------------------------------------------------------------
    FieldSpec(
        "is_practicing_registered_professional", PredicateCategory.PROFESSIONAL, "boolean",
        "Family member is a Doctor/Engineer/Lawyer/Chartered Accountant/Architect registered "
        "with their professional body and actively practicing.",
        schemes=("PM-KISAN",),
        draft_aliases=("profession",),  # draft used an enumerated string list instead of a boolean
        citizen_question="Is any family member a practicing, professionally-registered Doctor, Engineer, Lawyer, Chartered Accountant, or Architect?",
        display_label="Registered professional status",
    ),

    # --- institutional ------------------------------------------------------------------------------
    FieldSpec(
        "is_institutional_landholder", PredicateCategory.INSTITUTIONAL, "boolean",
        "Landholding is institutional (not a private farmer family).", schemes=("PM-KISAN",),
        draft_aliases=("institutional_landholder",),
        citizen_question="Is your land owned by an institution rather than by your family directly?",
        display_label="Institutional landholding status",
    ),

    # --- family_unit ------------------------------------------------------------------------------
    FieldSpec(
        "is_receiving_ladki_bahin_benefit", PredicateCategory.FAMILY_UNIT, "boolean",
        "Family member is already receiving the Ladki Bahin benefit (count_family_members target "
        "for the 'max 2 women per household' cap).",
        schemes=("MH-LADKI-BAHIN",),
        citizen_question="Is this family member already receiving the Ladki Bahin benefit?",
        display_label="Already receiving this benefit",
    ),

    # --- other ------------------------------------------------------------------------------
    FieldSpec(
        "household_has_existing_lpg_connection", PredicateCategory.OTHER, "boolean",
        "Household already has an LPG connection from any Oil Marketing Company.",
        schemes=("PM-UJJWALA-2.0",),
        citizen_question="Does your household already have an LPG gas connection?",
        display_label="Existing LPG connection",
    ),

    # --- temporal / cross_scheme / vacuous ---------------------------------------------------
    # No fields attested yet in the 6 gold schemes — populate when Phase 5 (temporal-drift) and
    # cross-scheme-exclusivity work actually needs them. Not pre-invented.
)

FIELD_ONTOLOGY: dict[str, FieldSpec] = {f.name: f for f in _FIELDS}


def get_field(name: str) -> FieldSpec | None:
    return FIELD_ONTOLOGY.get(name)


def display_label_for(field: str) -> str:
    """Plain-language label for `field`, for any citizen-facing surface (chat questions, rule
    trace). Falls back to a humanized field name for fields not yet in the canonical ontology
    (e.g. an ontology_proposed field an extraction run invented) — never the raw snake_case name,
    and never the technical `description`."""
    spec = get_field(field)
    return spec.display_label if spec is not None else field.replace("_", " ").capitalize()


# Runtime phrasings for fields NOT in the canonical ontology above — populated by
# conversational/field_phrasing.py when an AI-Checked extraction proposes a field the ontology has
# never seen (75% of extracted fields in the 2026-09-15 sample). Deliberately a separate dict, not
# entries in FIELD_ONTOLOGY: these are display strings only, carry no `cat`/`value_type`/`schemes`
# provenance, were never human-reviewed, and must not leak into format_for_prompt() (which teaches
# the extractor its canonical vocabulary) or into all_field_names() (which the structural-F1
# comparison treats as the known vocabulary). A canonical field's phrasing is never overridden.
_RUNTIME_CITIZEN_QUESTIONS: dict[str, str] = {}


def register_citizen_question(field: str, question: str) -> bool:
    """Record a generated citizen question for a non-canonical `field`. Returns False (and changes
    nothing) for a field the canonical ontology already covers — a human-written question always
    wins over a generated one."""
    if get_field(field) is not None or not question.strip():
        return False
    _RUNTIME_CITIZEN_QUESTIONS[field] = question.strip()
    return True


def registered_citizen_questions() -> dict[str, str]:
    """Read-only view of the runtime phrasings, for tests and cache persistence."""
    return dict(_RUNTIME_CITIZEN_QUESTIONS)


def clear_registered_citizen_questions() -> None:
    _RUNTIME_CITIZEN_QUESTIONS.clear()


def citizen_question_for(field: str) -> str | None:
    """The canonical citizen_question for `field`, a generated one if field_phrasing registered
    it, or None if neither exists (caller must supply its own generic fallback phrasing in that
    case — this function never fabricates one, since a fabricated question for an unknown field is
    exactly the kind of silent-guessing this project avoids everywhere else).

    Canonical first, always: a generated phrasing can only ever fill a gap, never replace a
    human-written question."""
    spec = get_field(field)
    if spec is not None:
        return spec.citizen_question
    return _RUNTIME_CITIZEN_QUESTIONS.get(field)


def fields_by_category(cat: PredicateCategory) -> list[FieldSpec]:
    return [f for f in _FIELDS if f.cat == cat]


def all_field_names() -> list[str]:
    return list(FIELD_ONTOLOGY.keys())


def format_for_prompt(compact: bool = False) -> str:
    """Render the ontology as a category-grouped list for the extraction system prompt.

    Excludes retired fields (empty `schemes` tuple, e.g. is_sc_st_pmay_g_beneficiary) — they exist
    only as documentation/traceability targets for humans reading this file, and including them
    here was pure prompt-token waste (verbose "RETIRED... see X" docstrings the LLM has no use
    for) discovered 2026-08-18 while diagnosing a PMMVY extraction failure: the ontology prompt
    had grown enough since AB-PMJAY that a scheme with a genuinely complex inclusion tree ran out
    of completion budget under the account's 8000 TPM cap (see extractor.py's module docstring).
    This alone doesn't solve the deeper scaling problem — the full ontology (all schemes) is sent
    on every extraction call by design, for cross-scheme field reuse, so this prompt will keep
    growing as more schemes are added — but it's a free, safe trim.

    `compact=True` (used by judge_repair.py's system prompt, see its own note): truncates each
    field's description to its first sentence. Found necessary 2026-08-18, same session as the
    retired-field trim above — the judge's own completion budget had shrunk enough (ontology
    growth eating more of the fixed 8000 TPM ceiling) that even gpt-oss-120b started failing
    structured-output validation on a judge call that had worked earlier the same day. The judge
    needs field NAMES for reuse far more than it needs each field's full multi-sentence
    docstring (which often carries historical/administrative context — retirement notes,
    cross-scheme provenance — genuinely useful for a human reading this file or an extractor
    forming a brand-new predicate, but not for a judge whose job is narrower: verify existing
    predicates and occasionally propose ONE new one for an obviously-implied fact)."""
    lines = []
    for cat in PredicateCategory:
        fields = [f for f in fields_by_category(cat) if f.schemes]
        if not fields:
            continue
        lines.append(f"{cat.value}:")
        for f in fields:
            description = f.description.split(". ")[0].rstrip(".") + "." if compact else f.description
            lines.append(f"  - {f.name} ({f.value_type}): {description}")
    return "\n".join(lines)
