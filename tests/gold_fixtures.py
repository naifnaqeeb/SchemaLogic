"""Hand-authored gold scheme JSONs for Phase 0 evaluator smoke-testing (plan Section 8, Phase 0 step 4).

CAVEAT: these are built from secondary sources (news/aggregator sites via web search), not primary
scheme notifications, and have NOT gone through the Section 6.5 draft-then-human-verify workflow
(source-clause pointers, dual annotation). They are `flagged_for_review=True` with moderate
confidence for that reason — treat as illustrative test data for the evaluator, not real gold data.
PM-KISAN (tests/fixtures.py) is the one exception: it's transcribed verbatim from the plan's own
Section 2.2 reference example.
"""

# Applicant-scoped exception put on every AB-PMJAY exclusion (gold fix, 2026-10-03): the 70+
# route is covered "irrespective of socio-economic status", so none of the SECC exclusions may
# block it. Applicant-scoped because four exclusions are some_family_member -- see
# models.ExceptScope and docs/GOLD_AUDIT_2026-10-03.md.
_SEVENTY_PLUS_ROUTE = {"field": "has_family_member_aged_70_or_above", "op": "==", "value": True}

AB_PMJAY = {
    # VERIFIED against three primary NHA/PIB documents (data/raw_documents/AB-PMJAY_primary_*.pdf):
    #   - Beneficiary Identification Guidelines (NHA): SECC 2011's 6 deprivation criteria used by
    #     AB-PMJAY (D1-D5, D7 — D6 deliberately excluded), 5 automatic-inclusion parameters, RSBY
    #     carry-over, urban occupational categories.
    #   - PIB press release, 3 July 2015: verbatim 14-parameter SECC automatic-exclusion list —
    #     the primary source for all 14 exclusions below (previously only 4 were captured, from
    #     secondary sources, and one — "with separate health scheme" — wasn't literally in SECC's
    #     own wording at all).
    #   - Guidelines on Expansion of AB PM-JAY to Senior Citizens 70+ (NHA, approved 11.09.2024):
    #     the has_family_member_aged_70_or_above branch, universal regardless of SECC status.
    "scheme_id": "AB-PMJAY",
    "unit_of_eligibility": "family",
    "inclusion": {
        "or": [
            {"cat": "economic", "field": "is_secc_deprived_household", "op": "==", "value": True},
            {"cat": "economic", "field": "is_secc_automatically_included", "op": "==", "value": True},
            {"cat": "economic", "field": "is_valid_rsby_beneficiary", "op": "==", "value": True},
            {
                "cat": "demographic",
                "field": "has_family_member_aged_70_or_above",
                "op": "==",
                "value": True,
            },
            {
                "cat": "occupation",
                "field": "is_urban_informal_worker",
                "op": "==",
                "value": True,
            },
        ]
    },
    "exclusions": [
        {
            "cat": "economic", "quantifier": "self",
            "field": "household_owns_motorised_vehicle_or_fishing_boat", "op": "==", "value": True,
            "except": _SEVENTY_PLUS_ROUTE, "except_scope": "applicant",
        },
        {
            "cat": "economic", "quantifier": "self",
            "field": "owns_mechanized_agricultural_equipment_3_or_4_wheeler", "op": "==", "value": True,
            "except": _SEVENTY_PLUS_ROUTE, "except_scope": "applicant",
        },
        {
            "cat": "economic", "quantifier": "self",
            "field": "kisan_credit_card_limit_inr", "op": ">", "value": 50000,
            "except": _SEVENTY_PLUS_ROUTE, "except_scope": "applicant",
        },
        {
            "cat": "occupation", "quantifier": "some_family_member",
            "field": "is_govt_employee", "op": "==", "value": True,
            "except": _SEVENTY_PLUS_ROUTE, "except_scope": "applicant",
        },
        {
            "cat": "economic", "quantifier": "self",
            "field": "owns_non_agricultural_enterprise_registered_with_govt", "op": "==", "value": True,
            "except": _SEVENTY_PLUS_ROUTE, "except_scope": "applicant",
        },
        {
            "cat": "economic", "quantifier": "some_family_member",
            "field": "monthly_income_inr", "op": ">", "value": 10000,
            "except": _SEVENTY_PLUS_ROUTE, "except_scope": "applicant",
        },
        {
            "cat": "economic", "quantifier": "some_family_member",
            "field": "paid_income_tax_last_assessment_year", "op": "==", "value": True,
            "except": _SEVENTY_PLUS_ROUTE, "except_scope": "applicant",
        },
        {
            "cat": "economic", "quantifier": "some_family_member",
            "field": "paid_professional_tax", "op": "==", "value": True,
            "except": _SEVENTY_PLUS_ROUTE, "except_scope": "applicant",
        },
        {
            "cat": "economic", "quantifier": "self",
            "field": "house_has_3_or_more_pucca_rooms", "op": "==", "value": True,
            "except": _SEVENTY_PLUS_ROUTE, "except_scope": "applicant",
        },
        {
            "cat": "economic", "quantifier": "self",
            "field": "owns_refrigerator", "op": "==", "value": True,
            "except": _SEVENTY_PLUS_ROUTE, "except_scope": "applicant",
        },
        {
            "cat": "economic", "quantifier": "self",
            "field": "owns_landline_phone", "op": "==", "value": True,
            "except": _SEVENTY_PLUS_ROUTE, "except_scope": "applicant",
        },
        {
            "cat": "economic", "quantifier": "self",
            "field": "owns_gt_2_5_acres_irrigated_land_with_irrigation_equipment", "op": "==", "value": True,
            "except": _SEVENTY_PLUS_ROUTE, "except_scope": "applicant",
        },
        {
            "cat": "economic", "quantifier": "self",
            "field": "owns_5_or_more_acres_irrigated_land_two_or_more_crop_seasons", "op": "==", "value": True,
            "except": _SEVENTY_PLUS_ROUTE, "except_scope": "applicant",
        },
        {
            "cat": "economic", "quantifier": "self",
            "field": "owns_7_5_or_more_acres_land_with_irrigation_equipment", "op": "==", "value": True,
            "except": _SEVENTY_PLUS_ROUTE, "except_scope": "applicant",
        },
    ],
    "temporal_validity": {
        "valid_from": "2018-09-23",
        "valid_to": None,
        "extracted_at": "2026-08-18",
        "supersedes": None,
    },
    "operational_requirements": ["aadhaar_ekyc", "ration_card_or_family_id"],
    "extraction_metadata": {
        "confidence": 0.93,
        "source_clause": (
            "VERIFIED against primary sources (see file header). Inclusion: is_secc_deprived_"
            "household covers SECC's D1/D2/D3/D4/D5/D7 rural deprivation criteria, directly quoted "
            "from the Beneficiary Identification Guidelines ('Total deprived Households ... who "
            "belong to one of the six deprivation criteria amongst D1, D2, D3, D4, D5 and D7') — "
            "D6 ('no literate adult above 25') is part of SECC's general 7-criteria deprivation "
            "grading but explicitly NOT one of the six PM-JAY uses, confirmed by that exact phrase. "
            "is_urban_informal_worker is a SEPARATE inclusion path (corrected in a Phase 3 "
            "structural-F1 check — originally miscategorized as folded into is_secc_deprived_"
            "household, but the document lists it under its own 'Urban occupational categories' "
            "heading, distinct from the rural D1-D7 list): rag picker, beggar, domestic worker, "
            "street vendor, construction worker, and similar SECC urban-informal-worker categories. "
            "is_secc_automatically_included and is_valid_rsby_beneficiary are new umbrella fields, "
            "each directly quoted from the same document ('Automatically included - Households "
            "without shelter; Destitute...'; 'all such enrolled families under RSBY that do not "
            "feature in the targeted groups ... will be included as well'). has_family_member_aged_"
            "70_or_above: directly quoted from the 70+ expansion guidelines ('expansion of AB "
            "PM-JAY to cover all senior citizens of 70 years of age and above irrespective of their "
            "socio-economic status, on family basis', approved 11.09.2024). Exclusions: all 14 "
            "directly quoted verbatim from the PIB SECC press release's numbered list (i-xiv) — "
            "items i/iii/iv/vii previously captured from secondary sources are now primary-cited "
            "exactly; items ii/v/vi/viii/ix/x/xi/xii/xiii/xiv are new. kisan_credit_card_limit_inr "
            "uses op='>' (strict), matching the document's exact wording 'a credit limit of over "
            "Rs. 50,000' — corrected in the same Phase 3 check from an earlier '>=' authoring slip. "
            "Items xii-xiv are compound (acreage AND irrigation-equipment-count) facts folded into "
            "single boolean fields since exclusion predicates can't express an AND of two fields — "
            "flagged as a schema-expressiveness workaround, same pattern as other compound facts "
            "elsewhere in this project. NOT modeled: the one-time, irrevocable choice a 70+ "
            "beneficiary already covered by CGHS/ECHS/CAPF/state schemes must make between their "
            "existing scheme and AB-PMJAY (70+ guidelines, Section 6-7) — this is a genuine "
            "selection/election rule, not a blanket disqualifier, the same shape as MH-LADKI-"
            "BAHIN's unmodeled 'one unmarried woman' rule. Flagged as a known gap rather than "
            "force-fit into a predicate that could misrepresent the actual choice-based rule."
            " GOLD CHANGE 2026-10-03 (docs/GOLD_AUDIT_2026-10-03.md): every exclusion now carries "
            "except has_family_member_aged_70_or_above == true with except_scope 'applicant'. "
            "Reason: the 70+ expansion guidelines cover citizens aged 70+ 'irrespective of their "
            "socio-economic status' and never apply the SECC exclusions to them, but as a flat list"
            " the 14 exclusions applied to every inclusion path -- so a 70+ senior whose household "
            "owned a refrigerator or landline, had a member earning over Rs 10,000/month, or had a "
            "member paying income tax was wrongly ineligible. The exception is applicant-scoped "
            "because the 70+ route is a fact about the applicant's household, while four of these "
            "exclusions are some_family_member: a member-scoped exception would be read off the "
            "member who triggered the exclusion, find nothing, and turn both the 70+ case and an "
            "ordinary correct 'ineligible' into 'undetermined'. Exclusions still apply in full to "
            "the SECC-deprived, automatic-inclusion, RSBY and urban-informal-worker routes. Caveat:"
            " under the guidelines the 70+ cover belongs to the 70+ members specifically, shared on"
            " a family basis; this gold keeps its existing household-level modelling of that route."
        ),
        "flagged_for_review": False,
    },
}

IGNOAPS = {
    # VERIFIED against the primary NSAP Programme Guidelines (Ministry of Rural Development;
    # data/raw_documents/IGNOAPS_primary_NSAP_guidelines.pdf, 33 pages — mirrored via
    # esomsa.hp.gov.in, no explicit revision date printed on the document itself, but internal
    # references confirm it postdates 1.4.2014, per para 1.2.6). Corroborated by the Ministry's
    # 2024-25 Annual Report (data/raw_documents/IGNOAPS_primary.pdf, pp.156-163) and a Nov-2025
    # PIB Backgrounder (data/raw_documents/IGNOAPS_primary_PIB_2025.pdf).
    "scheme_id": "IGNOAPS",
    "unit_of_eligibility": "individual",
    "inclusion": {
        "and": [
            {"cat": "demographic", "field": "age", "op": ">=", "value": 60},
            {
                # Gold fix 2026-10-03: BPL, OR the NSAP Para 2.4.3 AIDS-widow carve-out -- the only
                # place the three criteria below appear in any IGNOAPS source. See source_clause.
                "or": [
                    {"cat": "economic", "field": "is_bpl_household", "op": "==", "value": True},
                    {
                        "and": [
                            {"cat": "demographic", "field": "is_widow_suffering_from_aids", "op": "==", "value": True},
                            {"cat": "occupation", "field": "is_govt_employee", "op": "==", "value": False},
                            {"cat": "economic", "field": "family_agricultural_land_acres", "op": "<", "value": 5},
                            {"cat": "economic", "field": "owns_four_wheeler", "op": "==", "value": False},
                        ]
                    },
                ]
            },
        ]
    },
    # Gold fix 2026-10-03: has_regular_family_financial_support removed, and the three Para 2.4.3
    # criteria moved into the carve-out above -- see source_clause.
    "exclusions": [],
    "temporal_validity": {
        "valid_from": "2007-01-01",
        "valid_to": None,
        "extracted_at": "2026-08-18",
        "supersedes": None,
    },
    "operational_requirements": ["bank_or_post_office_account"],
    "extraction_metadata": {
        "confidence": 0.85,
        "source_clause": (
            "VERIFIED against NSAP Programme Guidelines. age>=60 and is_bpl_household directly "
            "quoted from Chapter II Section 2.3 ('The eligible age for IGNOAPS is 60 years'; "
            "'assistance under the sub-schemes of NSAP are applicable for persons belonging to "
            "Below Poverty Line (BPL) category'). valid_from=2007 directly quoted from Chapter I "
            "Para 1.2.4 ('From the year 2007, the scheme was expanded to cover all eligible persons"
            " Below Poverty Line (BPL). The scheme for old aged persons was renamed as Indira "
            "Gandhi National Old Age Pension Scheme (IGNOAPS)') — exact month/day not given in the "
            "source, so 01-01 is a placeholder for 'year 2007', not a literal date. CAVEAT: "
            "has_regular_family_financial_support is an interpretive elevation, not a literal "
            "Section 2.3 line item — it's built from Para 1.1.1's programme-wide 'destitute' "
            "definition ('any person who has little or no regular means of subsistence from his/her"
            " own source of income or through financial support from family members or other "
            "sources'), which reads as philosophical/preambular framing for NSAP as a whole rather "
            "than a numbered IGNOAPS-specific operative test, and may already be substantively "
            "subsumed by the BPL determination itself rather than an independent test. "
            "is_govt_employee / family_agricultural_land_acres>=5 / owns_four_wheeler (self, added "
            "2026-08-18): Para 2.4.3's aside on AIDS-widow prioritization — 'widows suffering from "
            "AIDS who will be considered if they are not attracted by any of the exclusion criteria"
            " of having a job in government, owning five acres of land or more or owning a four "
            "wheeler for own use' — was initially read as an elliptical reference to a separate "
            "BPL/SECC determination methodology and left out of this gold file. Cross-checking "
            "against an independent ontology-constrained LLM extraction run on the same source text"
            " (see data/extraction_runs/IGNOAPS_gpt-oss-120b_ontology_*.json) surfaced the same "
            "three criteria as live IGNOAPS exclusions; re-reading the clause, the phrase names "
            "'the exclusion criteria' as an existing, already-applicable standard (measured even "
            "against the special-case AIDS-widow carve-out), which is a more defensible reading "
            "than treating it as out-of-scope. Corrected here — an example of the draft-extraction "
            "catching a real annotation gap, consistent with the draft-then-verify workflow "
            "(Section 6.5). NOT modeled: the pre-2007 NOAPS restriction that the 2007 BPL expansion"
            " superseded — Para 1.2.4 confirms an expansion happened but doesn't state the prior "
            "restriction's specific numeric criterion, so no supersedes.retired_predicate could be "
            "constructed without guessing. NOT modeled: Para 2.4.3 also implies an alternate "
            "inclusion path for AIDS-affected widows ('except widows suffering from AIDS who will "
            "be considered if they are not attracted by any of the exclusion criteria...') that may"
            " bypass the BPL requirement specifically, but it's ambiguous whether this is a real "
            "alternate eligibility branch or just a processing-priority note (the section header is"
            " 'Priority to particularly vulnerable individuals'), and what exactly it bypasses. "
            "Flagged as a known gap rather than guessed at. GOLD CHANGE 2026-10-03 "
            "(docs/GOLD_AUDIT_2026-10-03.md), SUPERSEDING the sentences above about "
            "has_regular_family_financial_support, about the three Para 2.4.3 criteria being live "
            "IGNOAPS exclusions, and about the AIDS-widow path being NOT modeled: (1) REMOVED the "
            "exclusion has_regular_family_financial_support. It was, as noted above, an "
            "interpretive elevation of NSAP's programme-wide destitute definition (Para 1.1.1), not"
            " an operative IGNOAPS test, and possibly subsumed by BPL; across the full NSAP "
            "guidelines 'support from family' appears only in that definition. Both of Baseline 2's"
            " IGNOAPS harmful errors turned on it. (2) The three criteria -- government job, five "
            "acres or more, a four-wheeler for own use -- are no longer exclusions on every "
            "applicant. All three IGNOAPS sources were searched (the NSAP guidelines, the MoRD "
            "Annual Report 2024-25 and the 2025 PIB backgrounder): the criteria appear only inside "
            "Para 2.4.3's carve-out, 'only BPL persons from the eligible categories would be "
            "considered under NSAP except widows suffering from AIDS who will be considered if they"
            " are not attracted by any of the exclusion criteria of having a job in government, "
            "owning five acres of land or more or owning a four wheeler for own use'; every other "
            "occurrence in the annual report concerns PMAY-G, SECC or the 1997 BPL census. They now"
            " gate that carve-out and nothing else. (3) The carve-out is therefore modeled, as an "
            "alternative to BPL status: age >= 60 AND (is_bpl_household OR "
            "(is_widow_suffering_from_aids AND NOT govt job AND land < 5 acres AND NOT "
            "four-wheeler)). This reads Para 2.4.3 as a real exception to the BPL requirement, "
            "which is what its grammar says ('only BPL persons ... except widows ... who will be "
            "considered if ...'). It remains possible it was meant only as a processing priority --"
            " its section is headed 'Priority to particularly vulnerable individuals' -- and that "
            "it is aimed at the widow pension rather than IGNOAPS; both are recorded here as open. "
            "Net effect: exclusions is now empty, and a 60+ BPL applicant is eligible regardless of"
            " family support, a government job, land or a vehicle, as the operative IGNOAPS "
            "criteria (Section 2.3: age and BPL) state."
        ),
        "flagged_for_review": False,
    },
}

PMAY_G = {
    # VERIFIED against primary/near-primary sources (2026-08, Phase 3):
    #   - PIB Research Unit backgrounder "Pradhan Mantri Awas Yojana - Rural: Building a Better
    #     Future for Rural India" (19 Nov 2024, static.pib.gov.in) — the main source: current
    #     (post-amendment) eligibility criteria, compulsory inclusion categories, and exclusion
    #     criteria, published over two months after the Sept-2024 relaxation so it reflects the
    #     settled post-amendment state, not the announcement-day reporting.
    #   - PIB "Brief note on PMAY-G" (Nov 2019, static.pib.gov.in) — background/history only
    #     (Phase I/II structure, SECC-2011-based identification), not eligibility-relevant beyond
    #     confirming the scheme identifies beneficiaries "as per housing deprivation parameters
    #     and exclusion criteria prescribed under SECC 2011", i.e. the same underlying parameter
    #     set AB-PMJAY draws from.
    #   - Contemporaneous news coverage (BusinessToday, 11 Sep 2024, reporting the Union
    #     Minister's video-conference announcement the day before) for the "10, down from 13"
    #     exclusion-criteria count and confirmation that motorised 3/4-wheelers and mechanized
    #     agricultural equipment remain excluded (used only for the two exclusions the PIB
    #     backgrounder's condensed bullet list doesn't itself spell out).
    #
    # GENUINE PRIMARY-SOURCE GAP (unlike AB-PMJAY, where the exact verbatim numbered PIB
    # exclusion list was retrieved): the actual MoRD/Cabinet notification with the verbatim
    # current 10-point list could not be retrieved (pib.gov.in blocks direct fetches; only PDFs
    # under static.pib.gov.in were fetchable, and none was the primary notification itself). The
    # 11 exclusions below are reconstructed from the PIB backgrounder's prose + the BusinessToday
    # report and are internally consistent with the stated "13->10" reduction, but the reduction
    # arithmetic doesn't reconcile exactly against what's explicitly named as removed (fishing
    # boat, motorised two-wheeler — 2 items — against a claimed 3-item reduction), and one field
    # (owns_gt_2_5_acres_irrigated_land) is a best-effort simplification of what may actually be
    # the same compound (acreage AND irrigation-equipment) fact AB-PMJAY's SECC parameter xii
    # uses — see that field's ontology docstring. Kept flagged_for_review=True and confidence
    # below AB-PMJAY's for this reason, even though every individual fact here IS sourced from an
    # official PIB document (not secondary-aggregator-only, unlike the prior draft).
    "scheme_id": "PMAY-G",
    "unit_of_eligibility": "family",
    "inclusion": {
        "or": [
            {"cat": "economic", "field": "is_houseless", "op": "==", "value": True},
            {"cat": "economic", "field": "lives_in_kutcha_house", "op": "==", "value": True},
            {"cat": "economic", "field": "is_secc_automatically_included", "op": "==", "value": True},
        ]
    },
    "exclusions": [
        {
            "cat": "occupation",
            "quantifier": "some_family_member",
            "field": "is_govt_employee",
            "op": "==",
            "value": True,
        },
        {
            "cat": "economic",
            "quantifier": "self",
            "field": "owns_non_agricultural_enterprise_registered_with_govt",
            "op": "==",
            "value": True,
        },
        {
            "cat": "economic",
            "quantifier": "self",
            "field": "kisan_credit_card_limit_inr",
            "op": ">=",
            "value": 50000,
        },
        {
            "cat": "economic",
            "quantifier": "some_family_member",
            "field": "monthly_income_inr",
            "op": ">",
            "value": 15000,
        },
        {
            "cat": "economic",
            "quantifier": "some_family_member",
            "field": "paid_income_tax_last_assessment_year",
            "op": "==",
            "value": True,
        },
        {
            "cat": "economic",
            "quantifier": "self",
            "field": "owns_refrigerator",
            "op": "==",
            "value": True,
        },
        {
            "cat": "economic",
            "quantifier": "self",
            "field": "owns_landline_phone",
            "op": "==",
            "value": True,
        },
        {
            "cat": "economic",
            "quantifier": "self",
            "field": "owns_gt_2_5_acres_irrigated_land",
            "op": "==",
            "value": True,
        },
        {
            "cat": "economic",
            "quantifier": "self",
            "field": "owns_motorised_three_or_four_wheeler",
            "op": "==",
            "value": True,
        },
        {
            "cat": "economic",
            "quantifier": "self",
            "field": "owns_mechanized_agricultural_equipment_3_or_4_wheeler",
            "op": "==",
            "value": True,
        },
        {
            "cat": "economic",
            "quantifier": "self",
            "field": "owns_pucca_house",
            "op": "==",
            "value": True,
        },
    ],
    "temporal_validity": {
        "valid_from": "2024-09-11",
        "valid_to": None,
        "extracted_at": "2026-08-18",
        "supersedes": {
            "rule_version": "v1_pre_2024_amendment",
            "retired_predicate": {
                "field": "monthly_income_inr",
                "op": ">",
                "value": 10000,
            },
            "amendment_source": (
                "Sept-2024 exclusion-criteria relaxation (announced 10-11 Sep 2024, per "
                "BusinessToday and the PIB Nov-2024 backgrounder): income ceiling raised from "
                "Rs.10,000 to Rs.15,000/month, and exclusion criteria reduced from 13 to 10 "
                "(fishing-boat and motorised-two-wheeler ownership no longer excluded — a second "
                "retired fact this schema's single supersedes.retired_predicate slot can't also "
                "capture; same schema-expressiveness limitation flagged elsewhere in this "
                "project, e.g. AB-PMJAY's unmodeled 70+/CGHS election rule)."
            ),
        },
    },
    "operational_requirements": ["awaas_plus_survey_entry", "aadhaar_seeded_bank_account"],
    "extraction_metadata": {
        "confidence": 0.75,
        "source_clause": (
            "VERIFIED against a PIB Research Unit backgrounder (19 Nov 2024) and corroborating "
            "contemporaneous news coverage (see file header) — a real improvement over the prior "
            "hand-authored-from-secondary-sources draft, but NOT to AB-PMJAY's confidence level: "
            "the actual verbatim numbered MoRD/Cabinet exclusion notification could not be "
            "retrieved (pib.gov.in blocks direct fetch), so this is reconstructed from an official "
            "PR summary rather than the primary notification text itself. Inclusion: "
            "is_houseless and lives_in_kutcha_house directly quoted ('Houseless Households: All "
            "households without any shelter'; 'Households with Kuccha Houses: ... kuccha walls "
            "and kuccha roofs or houses with zero, one, or two rooms as per SECC 2011'). "
            "is_secc_automatically_included reused from AB-PMJAY's ontology entry — PMAY-G's own "
            "'Compulsory Inclusion Criteria' list (destitute/alms, manual scavengers, primitive "
            "tribal groups, legally released bonded laborers) is the same underlying SECC "
            "automatic-inclusion parameter set minus the shelterless case, which is separately "
            "covered here by is_houseless. NOT modeled: the deprivation-score PRIORITY/ranking "
            "parameters (no adult 16-59, female-headed no adult male, no literate adult >25, "
            "disabled member no able-bodied adult, landless manual-labour household) — these rank "
            "among the already-eligible pool for scarce allocation, not a binary eligibility "
            "gate, so out of scope for this project's eligible/ineligible schema, same shape as "
            "AB-PMJAY's and MH-LADKI-BAHIN's other unmodeled selection/priority rules. Exclusions: "
            "kisan_credit_card_limit_inr op='>=' (PIB's own wording is 'credit limit of Rs.50,000 "
            "or above' — note this is op='>=' here, UNLIKE AB-PMJAY's same field where the source "
            "wording 'over Rs.50,000' meant strict '>'; the two schemes' primary wording genuinely "
            "differs on this operator, don't assume they match). monthly_income_inr reclassified "
            "from a self-scoped monthly_household_income_inr field to the shared, "
            "some_family_member-scoped monthly_income_inr field (see ontology docstring). "
            "owns_gt_2_5_acres_irrigated_land is a new, deliberately SEPARATE (simpler, no "
            "irrigation-equipment qualifier) field from AB-PMJAY's compound version — flagged "
            "uncertainty, see its ontology docstring."
        ),
        "flagged_for_review": True,
    },
}

PM_UJJWALA = {
    # VERIFIED against PIB Research Unit sources and corroborating secondary coverage (2026-08,
    # Phase 3):
    #   - PIB "SEVEN YEARS OF PRADHAN MANTRI UJJWALA YOJANA (PMUY)" (1 May 2023, static.pib.gov.in)
    #     and PIB "Pradhan Mantri Ujjwala Yojana (State Series)" explainer (27 July 2022,
    #     static.pib.gov.in) — confirm launch dates (PMUY: 1 May 2016; Ujjwala 2.0: 10 Aug 2021)
    #     and that connections are released "in the name of an adult woman of the poor family",
    #     but are stats/history-focused, NOT a detailed eligibility-category breakdown.
    #   - Three independently corroborating secondary summaries (search-engine-synthesized from
    #     multiple outlets, cross-checked against each other) for the actual category list: the
    #     original PMUY base (SECC 2011 list / BPL), Ujjwala 2.0's "seven more categories" (SC/ST,
    #     PMAY-G beneficiary, AAY, forest dweller, Most Backward Classes, Tea & Ex-Tea Garden
    #     Tribes, river-island residents), and a 14-point self-declaration fallback route for poor
    #     households not otherwise covered.
    #
    # GENUINE PRIMARY-SOURCE GAP, same shape as PMAY-G's: no verbatim MoPNG/PIB notification text
    # enumerating the categories could be retrieved (PIB blocks direct fetch; the PIB backgrounder
    # PDFs that WERE retrievable are stats/history-focused, not eligibility-detail-focused). The
    # category list below is corroborated across three independent secondary syntheses agreeing
    # with each other (stronger than a single secondary source, weaker than AB-PMJAY's verbatim
    # numbered PIB list), which is why confidence sits between PMAY-G's and AB-PMJAY's.
    #
    # CORRECTED from the prior draft: is_sc_st_pmay_g_beneficiary was a single compound field
    # ("SC/ST AND PMAY-G beneficiary") — all three sources describe SC/ST and PMAY-G beneficiary
    # as SEPARATE categories, not a compound AND. Split into is_sc_st / is_pmay_g_beneficiary.
    # Added meets_14_point_self_declaration, a real 4th inclusion pathway missing from the prior
    # draft entirely. Renamed lives_on_river_island_without_lpg -> lives_on_river_island (see
    # ontology docstring — the 'without LPG' qualifier duplicated the separate top-level
    # exclusion).
    "scheme_id": "PM-UJJWALA-2.0",
    "unit_of_eligibility": "individual",
    "inclusion": {
        "and": [
            {"cat": "demographic", "field": "is_woman", "op": "==", "value": True},
            {"cat": "demographic", "field": "age", "op": ">=", "value": 18},
            {
                "or": [
                    {"cat": "economic", "field": "is_bpl_household", "op": "==", "value": True},
                    {"cat": "economic", "field": "is_in_secc_2011_list", "op": "==", "value": True},
                    {"cat": "demographic", "field": "is_sc_st", "op": "==", "value": True},
                    {"cat": "demographic", "field": "is_pmay_g_beneficiary", "op": "==", "value": True},
                    {"cat": "economic", "field": "is_aay_beneficiary", "op": "==", "value": True},
                    {"cat": "demographic", "field": "is_forest_dweller", "op": "==", "value": True},
                    {"cat": "demographic", "field": "is_most_backward_class", "op": "==", "value": True},
                    {"cat": "demographic", "field": "is_tea_garden_tribe", "op": "==", "value": True},
                    {"cat": "demographic", "field": "lives_on_river_island", "op": "==", "value": True},
                    {
                        "cat": "economic",
                        "field": "meets_14_point_self_declaration",
                        "op": "==",
                        "value": True,
                    },
                ]
            },
        ]
    },
    "exclusions": [
        {
            "cat": "other",
            "quantifier": "self",
            "field": "household_has_existing_lpg_connection",
            "op": "==",
            "value": True,
        }
    ],
    "temporal_validity": {
        "valid_from": "2021-08-10",
        "valid_to": None,
        "extracted_at": "2026-08-18",
        "supersedes": None,
    },
    "operational_requirements": ["aadhaar_kyc"],
    "extraction_metadata": {
        "confidence": 0.7,
        "source_clause": (
            "VERIFIED launch dates and 'adult woman of the poor family' framing against two PIB "
            "Research Unit documents (see file header); the inclusion category list is corroborated"
            " across three independently cross-checked secondary syntheses rather than a retrieved "
            "verbatim primary notification (pib.gov.in blocks direct fetch; the retrievable PIB "
            "PDFs were stats-focused, not eligibility-detail-focused) — hence confidence between "
            "PMAY-G's (0.75, single secondary corroboration) and AB-PMJAY's (0.93, verbatim "
            "numbered primary list). is_sc_st and is_pmay_g_beneficiary split from the prior "
            "draft's single compound is_sc_st_pmay_g_beneficiary field (see ontology docstring) — "
            "all three sources independently describe these as separate categories. "
            "meets_14_point_self_declaration added as a real 4th inclusion pathway (SECC list / "
            "seven added categories / 14-point self-declaration) missing from the prior draft "
            "entirely. lives_on_river_island renamed from lives_on_river_island_without_lpg "
            "(redundant qualifier, see ontology docstring). NOT independently verified: the exact "
            "age threshold (18 is the standard Indian legal-adult age and matches 'adult woman' "
            "framing in every source checked, but no source stated '18' as a scheme-specific "
            "numeric threshold explicitly). GOLD CHANGE 2026-10-03 (docs/GOLD_AUDIT_2026-10-03.md):"
            " REMOVED the inclusion predicate is_indian_citizen == true. Reason: it had no recorded"
            " source. The source document (data/raw_documents/PM-UJJWALA-2.0.md) never mentions "
            "citizenship -- no 'citizen', 'Indian national' or 'nationality' anywhere -- and this "
            "clause, which documents every other uncertainty above, never accounted for it. Unlike "
            "PM-KISAN's citizenship predicate, which is a documented inference from that scheme's "
            "NRI exclusion, this one was neither stated nor argued for. Both the Phase 3 extractor "
            "(citizenship-category F1 = 0.0) and Baseline 2 (non-citizen profile counted as a "
            "harmful false positive) were charged with errors for disagreeing with it. If the "
            "primary PMUY 2.0 notification does require citizenship, cite that clause here and "
            "restore the predicate."
        ),
        "flagged_for_review": True,
    },
}

MAHARASHTRA_LADKI_BAHIN = {
    # VERIFIED against three primary GRs from Maharashtra's Women & Child Development Dept
    # (data/raw_documents/MH-LADKI-BAHIN_primary_GR_2024{0628,0703,0712}.pdf):
    #   - 28.06.2024 (GR मबावि 2024/प्र.क्र.96/कार्य-2): original scheme, full para 3-6 criteria.
    #   - 03.07.2024 (same no.): amendment — age cap 60->65, removed the >5-acre-land exclusion,
    #     narrowed the govt-employee/pensioner exclusion to regular/permanent only (contractual
    #     workers earning <=2.5L exempted), clarified the other-scheme-benefit exclusion as a
    #     MONTHLY (not lump-sum) Rs.1,500 threshold, added a "max one unmarried woman per family"
    #     eligibility clause.
    #   - 12.07.2024 (same no.): clarified "family" = husband, wife, unmarried children only.
    # Corrected 2026-08-18: the original gold's "2 women already receiving benefit" count
    # exclusion was NOT found in any of these three GRs and has been removed as unverified —
    # it traced back to a fraud-crackdown news article (the420.in), not a primary GR clause. The
    # real per-family numeric constraint is "only one unmarried woman per family may benefit"
    # (03.07.2024 amendment, item 1) — NOT re-added as a predicate here: it's a selection/
    # allocation rule (administratively picks ONE of several unmarried sisters, unspecified which)
    # rather than a blanket family-wide disqualifier, which is what count_family_members expresses.
    # Modeling it correctly would need a schema extension beyond this quantifier's semantics —
    # flagged as a known gap, not force-fit into a predicate that could produce wrong verdicts.
    "scheme_id": "MH-LADKI-BAHIN",
    "unit_of_eligibility": "family",
    "inclusion": {
        "and": [
            {"cat": "demographic", "field": "is_woman", "op": "==", "value": True},
            {"cat": "demographic", "field": "is_maharashtra_resident", "op": "==", "value": True},
            {"cat": "demographic", "field": "age", "op": ">=", "value": 21},
            {"cat": "demographic", "field": "age", "op": "<=", "value": 65},
            {
                "cat": "economic",
                "field": "has_bank_account",
                "op": "==",
                "value": True,
            },
            {
                "cat": "economic",
                "field": "family_annual_income_inr",
                "op": "<=",
                "value": 250000,
            },
        ]
    },
    "exclusions": [
        {
            "cat": "economic",
            "quantifier": "some_family_member",
            "field": "paid_income_tax_last_assessment_year",
            "op": "==",
            "value": True,
        },
        {
            "cat": "occupation",
            "quantifier": "some_family_member",
            "field": "is_regular_govt_employee_or_pensioner",
            "op": "==",
            "value": True,
        },
        {
            "cat": "economic",
            "quantifier": "self",
            "field": "other_govt_scheme_monthly_benefit_inr",
            "op": ">=",
            "value": 1500,
        },
        {
            "cat": "political",
            "quantifier": "some_family_member",
            "field": "holds_constitutional_or_political_post",
            "op": "==",
            "value": True,
        },
        {
            "cat": "political",
            "quantifier": "some_family_member",
            "field": "holds_govt_board_or_corporation_post",
            "op": "==",
            "value": True,
        },
        {
            "cat": "economic",
            "quantifier": "some_family_member",
            "field": "owns_four_wheeler",
            "op": "==",
            "value": True,
            "except": {"field": "owned_vehicle_is_farm_tractor_only", "op": "==", "value": True},
        },
    ],
    "temporal_validity": {
        "valid_from": "2024-07-01",
        "valid_to": None,
        "extracted_at": "2026-08-18",
        "supersedes": {
            "rule_version": "v1_pre_20240703",
            "retired_predicate": {"field": "family_agricultural_land_acres", "op": ">", "value": 5},
            "amendment_source": (
                "GR मबावि 2024/प्र.क्र.96/कार्य-2, दि.03.07.2024, item 6 of the amendment table: "
                "'अ.क्र.(७) येथिल अपात्रतेची अट वगळण्यात येत आहे' (the disqualification condition "
                "at original item 7 — family jointly holds more than 5 acres of farmland — is "
                "hereby removed). Directly quoted and verified against the primary PDF."
            ),
        },
    },
    "operational_requirements": [
        "aadhaar_card",
        "domicile_certificate_or_alternate_proof",
        "family_income_certificate_or_ration_card_exemption",
    ],
    "extraction_metadata": {
        "confidence": 0.9,
        "source_clause": (
            "VERIFIED against primary GRs (see file header). Inclusion: is_woman/age 21-65 "
            "(item 4(3), post-03.07.2024 amendment)/family_annual_income_inr<=250000 (item 4(5)) "
            "directly quoted. is_maharashtra_resident directly quoted (item 4(1)). has_bank_account "
            "matches item 4(4)'s literal 'must have a bank account' — Aadhaar-linkage is a "
            "disbursement-mechanism detail (section 2), not a stated eligibility criterion, so it's "
            "listed under operational_requirements instead, not folded into this predicate. "
            "Exclusions: income tax (item 5(2)), govt employee/pensioner (item 5(3), amended to "
            "exclude only regular/permanent — contractual/outsourced/voluntary workers with "
            "income <=2.5L are explicitly eligible per the amendment, already covered by the "
            "inclusion-side income cap so no separate except-clause was added), other-govt-scheme "
            "monthly benefit >=1500 (item 5(4), amended wording, self-quantified since the clause "
            "says 'the said beneficiary WOMAN', not 'family member'), MP/MLA (item 5(5), reuses "
            "PM-KISAN's holds_constitutional_or_political_post canonical field — same real-world "
            "concept), govt board/corporation post (item 5(6), a distinct appointed-post concept, "
            "new field), four-wheeler except tractor (item 5(8), directly quoted). NOT modeled: "
            "the 'only one unmarried woman per family' rule (03.07.2024 amendment) — see file "
            "header note on why. NOT modeled: item 5(1) (family income >2.5L) since it's redundant "
            "with the inclusion-side income cap, not a separate fact."
        ),
        "flagged_for_review": False,
    },
}

PMMVY = {
    # VERIFIED against a PIB Backgrounder "Pradhan Mantri Matru Vandana Yojana: Empowering
    # mothers, shaping generations" (24 August 2025, static.pib.gov.in) — includes a direct
    # PMMVY-vs-PMMVY-2.0 before/after comparison table and an explicit "Eligibility Criteria &
    # Exclusions" section with an inclusion-category table. Age criterion (18 years 7 months to
    # 55 years, AT TIME OF CHILDBIRTH) independently corroborated verbatim by a second official
    # source: the Savitribai Phule National Institute of Women & Child Development (an autonomous
    # body under the Ministry of Women & Child Development) FAQ page. The means-tested (not
    # universal) nature of eligibility — despite NFSA 2013's universal-maternity-benefit framing —
    # cross-checked against an independent secondary summary (IMPRI policy institute) that
    # explicitly flags this as a genuine gap between NFSA's statutory intent and PMMVY's actual
    # targeted implementation.
    #
    # Strongest primary-source grounding of any Phase 3 scheme so far for the AMENDMENT itself
    # (the PIB backgrounder's before/after table is as close to a verbatim comparison as any
    # source retrieved this phase) — but the inclusion category list, while corroborated across
    # two independent sources, could not be checked against the actual MWCD notification/scheme
    # guidelines PDF (not retrievable; pib.gov.in blocks direct fetch as with every other scheme
    # this phase). Confidence set accordingly: above PMAY-G/PM-UJJWALA, at AB-PMJAY's level for
    # the temporal/amendment facts, one notch below for the category list specifically.
    #
    # NOT MODELED (genuine gap, left out rather than guessed): a government-employment /
    # other-maternity-benefit-scheme exclusion, appearing only in ONE low-confidence secondary
    # aggregator (never corroborated by any primary/near-primary source retrieved) — plausible (a
    # standard anti-double-dipping convention in maternity-benefit scheme design) but not
    # confirmed, so deliberately left out of exclusions rather than risking a confidently-wrong
    # predicate. "Other vulnerable groups as notified by Central Government" (the table's 10th
    # inclusion-category row) is also unmodeled — open-ended/non-enumerable, same treatment as
    # other too-vague-to-encode categories skipped elsewhere in this project.
    #
    # Age modeled as age>=18 (not the literal "18 years 7 months") — a deliberate rounding
    # simplification flagged here rather than silently applied: the fractional-month precision
    # isn't practically representable against how profile data is actually collected/tested
    # elsewhere in this project, and is very plausibly downstream of "must have been 18 at LMP,
    # accounting for a ~9-month pregnancy" rather than an independently chosen threshold.
    "scheme_id": "PMMVY",
    "unit_of_eligibility": "individual",
    "inclusion": {
        "and": [
            {"cat": "demographic", "field": "age", "op": ">=", "value": 18},
            {"cat": "demographic", "field": "age", "op": "<=", "value": 55},
            {
                "or": [
                    {"cat": "demographic", "field": "is_sc_st", "op": "==", "value": True},
                    {
                        "cat": "demographic",
                        "field": "has_40_percent_or_more_disability",
                        "op": "==",
                        "value": True,
                    },
                    {"cat": "economic", "field": "is_bpl_household", "op": "==", "value": True},
                    {
                        "cat": "cross_scheme",
                        "field": "is_ab_pmjay_beneficiary",
                        "op": "==",
                        "value": True,
                    },
                    {"cat": "economic", "field": "is_e_shram_registered", "op": "==", "value": True},
                    {
                        "cat": "cross_scheme",
                        "field": "is_pm_kisan_beneficiary",
                        "op": "==",
                        "value": True,
                    },
                    {
                        "cat": "economic",
                        "field": "has_active_mgnrega_job_card",
                        "op": "==",
                        "value": True,
                    },
                    {
                        "cat": "economic",
                        "field": "family_annual_income_inr",
                        "op": "<",
                        "value": 800000,
                    },
                    {"cat": "occupation", "field": "is_frontline_worker", "op": "==", "value": True},
                    {
                        "cat": "economic",
                        "field": "is_nfsa_ration_card_holder",
                        "op": "==",
                        "value": True,
                    },
                ]
            },
            {
                "or": [
                    {"cat": "demographic", "field": "pregnancy_child_order", "op": "==", "value": 1},
                    {
                        "and": [
                            {
                                "cat": "demographic",
                                "field": "pregnancy_child_order",
                                "op": "==",
                                "value": 2,
                            },
                            {"cat": "demographic", "field": "child_is_girl", "op": "==", "value": True},
                        ]
                    },
                ]
            },
            # Precise age floor, 18 years 7 months (gold fix 2026-10-03). Placed LAST so the
            # months question is only reached for an 18-year-old -- see the source_clause.
            {
                "or": [
                    {"cat": "demographic", "field": "age", "op": ">=", "value": 19},
                    {"cat": "demographic", "field": "months_since_last_birthday", "op": ">=", "value": 7},
                ]
            },
        ]
    },
    "exclusions": [],
    "temporal_validity": {
        "valid_from": "2022-04-01",
        "valid_to": None,
        "extracted_at": "2026-08-18",
        "supersedes": {
            "rule_version": "PMMVY_1.0_pre_2022",
            "retired_predicate": {"field": "pregnancy_child_order", "op": "==", "value": 1},
            "amendment_source": (
                "PMMVY 2.0 (effective 1 April 2022, per PIB backgrounder's before/after table): "
                "prior rule covered the first living child ONLY; extended to also cover the "
                "second living child if it is a girl, to promote positive attitudes towards girls "
                "and improve the Sex Ratio at Birth."
            ),
        },
    },
    "operational_requirements": [
        "mcp_card",
        "aadhaar_authentication",
        "dbt_aadhaar_seeded_account",
        "pmmvysoft_registration_within_270_days_of_childbirth",
    ],
    "extraction_metadata": {
        "confidence": 0.85,
        "source_clause": (
            "VERIFIED against a PIB Backgrounder (24 Aug 2025) with an explicit PMMVY-vs-2.0 "
            "before/after comparison table (temporal/amendment facts) and an 'Eligibility Criteria "
            "& Exclusions' section (age, category table) — age criterion ('between 18 years 7 "
            "months and 55 years of age at the time of childbirth') independently corroborated "
            "verbatim by a second official source (Savitribai Phule National Institute of Women & "
            "Child Development FAQ). CORRECTED 2026-10-03: that corroboration was of the SOURCE "
            "TEXT, not of this gold's encoding -- until 2026-10-03 the gold encoded the floor as "
            "age >= 18, silently dropping the 7 months, and this clause's earlier wording "
            "('corroborated verbatim') implied the encoded predicate matched the source when it did"
            " not. Means-tested (not universal) nature cross-checked against an independent "
            "policy-institute summary. NOT independently checked against the actual MWCD scheme "
            "guidelines/notification PDF (not retrievable — same pib.gov.in fetch-blocking issue as"
            " every other Phase 3 scheme). 'Other vulnerable groups as notified by Central "
            "Government' (10th inclusion category) intentionally unmodeled — open-ended, not a "
            "concrete predicate. A government-employment/other-maternity-benefit exclusion "
            "appearing in one low-confidence secondary source only was deliberately NOT included "
            "(see file header) rather than guessed. GOLD CHANGE 2026-10-03 "
            "(docs/GOLD_AUDIT_2026-10-03.md): added inclusion conjunct or[age >= 19, "
            "months_since_last_birthday >= 7], encoding the 18-years-7-months floor. Reason: with "
            "age >= 18 alone, women aged 18y0m-18y6m were wrongly eligible (the harmful direction)."
            " Ages are asked in whole years, so 18 is the only ambiguous value; the coarse age >= "
            "18 conjunct is kept first so a 17-year-old is ruled out at the first question, and the"
            " precise floor is placed LAST in the conjunction so that the months question is only "
            "ever reached for an 18-year-old (the question selector asks every unresolved leaf, "
            "even under an already-satisfied 'or' -- see KNOWN_ISSUES.md). The 55-year ceiling is "
            "unchanged. Still NOT modeled, unchanged by this fix: the source measures age 'at the "
            "time of childbirth', while both bounds here use the applicant's current age."
        ),
        "flagged_for_review": True,
    },
}

ALL_GOLD_SCHEMES = {
    "AB-PMJAY": AB_PMJAY,
    "IGNOAPS": IGNOAPS,
    "PMAY-G": PMAY_G,
    "PM-UJJWALA-2.0": PM_UJJWALA,
    "MH-LADKI-BAHIN": MAHARASHTRA_LADKI_BAHIN,
    "PMMVY": PMMVY,
}
