"""Shared fixtures for schema/evaluator tests.

PM-KISAN is verified against the primary source: PM-KISAN Operational Guidelines (Revised as on
29.03.2020), Ministry of Agriculture & Farmers' Welfare, DAC&FW — downloaded from
pmkisan.gov.in/Documents/RevisedPM-KISANOperationalGuidelines(English).pdf and saved at
data/raw_documents/PM-KISAN_primary.pdf. Started from the plan's Section 2.2 illustrative version;
corrected/extended against the primary text on 2026-08-17 (added the Para 4.1(c) NRI exclusion;
see extraction_metadata.source_clause for exactly which predicates are directly quoted vs.
inferred vs. not yet primary-source-verified)."""

PM_KISAN = {
    "scheme_id": "PM-KISAN",
    "unit_of_eligibility": "family",
    "inclusion": {
        "and": [
            {"cat": "citizenship", "field": "is_indian_citizen", "op": "==", "value": True},
            {
                "cat": "occupation",
                "field": "owns_cultivable_land_in_records",
                "op": "==",
                "value": True,
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
            "field": "is_serving_or_retired_govt_employee",
            "op": "==",
            "value": True,
            "except": {"field": "is_group_d_class_iv_or_mts", "op": "==", "value": True},
        },
        {
            "cat": "economic",
            "quantifier": "some_family_member",
            "field": "monthly_pension_inr",
            "op": ">=",
            "value": 10000,
            "except": {"field": "is_group_d_class_iv_or_mts", "op": "==", "value": True},
        },
        {
            "cat": "political",
            "quantifier": "some_family_member",
            "field": "holds_constitutional_or_political_post",
            "op": "==",
            "value": True,
        },
        {
            "cat": "professional",
            "quantifier": "some_family_member",
            "field": "is_practicing_registered_professional",
            "op": "==",
            "value": True,
        },
        {
            "cat": "institutional",
            "field": "is_institutional_landholder",
            "op": "==",
            "value": True,
        },
        {
            "cat": "citizenship",
            "quantifier": "some_family_member",
            "field": "is_nri_per_income_tax_act_1961",
            "op": "==",
            "value": True,
        },
    ],
    "temporal_validity": {
        "valid_from": "2019-06-01",
        "valid_to": None,
        "extracted_at": "2026-08-17",
        "supersedes": {
            "rule_version": "v1",
            "retired_predicate": {"field": "landholding_hectares", "op": "<=", "value": 2},
            "amendment_source": (
                "Union Cabinet decision, 1 June 2019, extending PM-KISAN from small/marginal "
                "(<=2 hectare) farmer families to all landholding farmer families. NOTE: the "
                "primary cabinet decision document itself was not located/verified in this pass "
                "(not present in the Operational Guidelines PDF, which only presents the "
                "already-amended rule) — this rests on well-corroborated contemporaneous PIB/news "
                "coverage, not a primary document pointer. Flagged for a future annotator to close "
                "out with the actual cabinet decision document."
            ),
        },
    },
    "operational_requirements": ["aadhaar_seeded_bank_account", "ekyc_completed"],
    "extraction_metadata": {
        "confidence": 0.95,
        "source_clause": (
            "VERIFIED against primary source: PM-KISAN Operational Guidelines (Revised as on "
            "29.03.2020), DAC&FW, Ministry of Agriculture & Farmers' Welfare "
            "(data/raw_documents/PM-KISAN_primary.pdf). Para 3 (family definition + "
            "owns_cultivable_land_in_records inclusion criterion, directly quoted). Para 4.1(a) "
            "(institutional landholders, self-quantified, directly quoted). Para 4.1(b)(i)-(ii) "
            "(constitutional-post and political-office holders, bundled into one predicate here — "
            "a grouping choice, not a literal quote — some_family_member). Para 4.1(b)(iii)-(iv) "
            "(govt employees / pensioners >=10,000/month, both carrying the Multi Tasking Staff / "
            "Class IV / Group D exception, directly quoted). Para 4.1(b)(v) (income tax payers, "
            "directly quoted). Para 4.1(b)(vi) (registered professionals in active practice, "
            "abstracted from the specific Doctor/Engineer/Lawyer/CA/Architect list into one "
            "boolean predicate). Para 4.1(c) (NRI per Income Tax Act 1961, added 2026-08-17; "
            "quantifier some_family_member is a modeling choice — clause text says 'families... "
            "who are NRIs' without the 'one or more of its members' phrasing used elsewhere in "
            "4.1(b), and is explicitly scoped to 'new beneficiaries being uploaded'). CAVEAT: "
            "inclusion's is_indian_citizen predicate is NOT a directly-stated standalone clause in "
            "the primary document — it's inferred from the Para 4.1(c) NRI exclusion plus the "
            "scheme's 'landholding farmers' families in the country' framing, kept as a "
            "conservative inclusion-side operationalization. temporal_validity.supersedes.amendment_source "
            "is not primary-source-verified (see that field's own note)."
        ),
        "flagged_for_review": False,
    },
}
