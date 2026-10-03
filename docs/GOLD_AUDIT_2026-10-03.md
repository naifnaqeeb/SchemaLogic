# Gold-set sourcing audit — 2026-10-03

Every predicate in every `data/gold/*.json` checked against the documents it is meant to come from.
No LLM calls; the classification is a manual judgement, made reproducible by
`scripts/audit_gold.py` (`table`, `show`, `search`, `extract`, `sync`).

**Sections 1–5 record the gold set exactly as it stood when audited, before any fix.** Changes made
in response are recorded in section 6, each with its reason, and every gold change is also recorded
in that scheme's own `source_clause`. Superseded numbers are listed in section 7.

## 0. Method

Each predicate is classified against two layers of source, because they answer different questions:

- **The `.md` in `data/raw_documents/`** — what the extractor and Baseline 2 were actually given. A
  rule absent from it cannot fairly be counted as an extractor miss.
- **The primary documents** — what the gold was annotated against. Saved for PM-KISAN (operational
  guidelines), IGNOAPS (NSAP guidelines, MoRD annual report, PIB), MH-LADKI-BAHIN (three Marathi
  GRs, plus verbatim transcripts in `data/retrieval_corpus/`) and AB-PMJAY (three NHA/PIB
  documents). **PM-UJJWALA-2.0, PMAY-G and PMMVY have no primary saved**: their `.md` files are
  compiled from PIB backgrounders and secondary coverage, and "sourced" for them means sourced to
  that, which each gold already discloses.

Classes:

| Class | Meaning |
|---|---|
| **S** — Sourced | The rule is stated in the cited source. |
| **I** — Inferred, documented | Not literally stated, but the gold says it is an inference and why. |
| **U** — Unsourced | No supporting text, and no documented inference. |

A fourth kind of problem did not fit these classes and is reported separately in section 3:
**sourced but mis-encoded** — the rule is in the source, but the gold encodes it wrongly.

PDF text extraction breaks words ("pu cca", "Househol d"), so every apparent absence was
re-checked with a shorter term before being recorded as one.

## 1. Summary

| Scheme | Predicates | S | I | **U** | Checked against |
|---|---|---|---|---|---|
| AB-PMJAY | 19 | 19 | 0 | 0 | `.md` + 3 primary PDFs |
| IGNOAPS | 6 | 2 | 4 | 0 | `.md` + 3 primary PDFs |
| MH-LADKI-BAHIN | 13 | 13 | 0 | 0 | `.md` + 3 Marathi GRs |
| PM-KISAN | 11 | 10 | 1 | 0 | `.md` + primary PDF |
| PM-UJJWALA-2.0 | 14 | 12 | 1 | **1** | `.md` only |
| PMAY-G | 14 | 14 | 0 | 0 | `.md` only *(but see §4)* |
| PMMVY | 15 | 15 | 0 | 0 | `.md` only |
| **Total** | **92** | **85** | **6** | **1** | |

Only one predicate in the gold set is unsourced. The more serious findings are the encoding errors
in §3, two of which produce wrong verdicts in the live app.

## 2. Per-predicate classification (pre-fix)

### AB-PMJAY (19)

| # | Location | Predicate | Kind | Class | Note |
|---|---|---|---|---|---|
| P01 | `incl.or[0]` | `is_secc_deprived_household == true` | inclusion | S | D1–D5, D7 umbrella; D6 exclusion verified against Beneficiary Identification Guidelines. |
| P02 | `incl.or[1]` | `is_secc_automatically_included == true` | inclusion | S | Five automatic-inclusion parameters. |
| P03 | `incl.or[2]` | `is_valid_rsby_beneficiary == true` | inclusion | S | RSBY carry-over clause. |
| P04 | `incl.or[3]` | `has_family_member_aged_70_or_above == true` | inclusion | S | 70+ expansion guidelines, 11.09.2024. **See §3: the exclusions are wrongly applied to this path.** |
| P05 | `incl.or[4]` | `is_urban_informal_worker == true` | inclusion | S | Urban occupational categories. |
| P06 | `excl[0]` | `household_owns_motorised_vehicle_or_fishing_boat == true` | exclusion (self) | S | SECC item i. |
| P07 | `excl[1]` | `owns_mechanized_agricultural_equipment_3_or_4_wheeler == true` | exclusion (self) | S | SECC item ii. |
| P08 | `excl[2]` | `kisan_credit_card_limit_inr > 50000` | exclusion (self) | S | SECC item iii, "over Rs. 50,000" → strict `>`, confirmed in the PDF. |
| P09 | `excl[3]` | `is_govt_employee == true` | exclusion (some_family_member) | S | SECC item iv. |
| P10 | `excl[4]` | `owns_non_agricultural_enterprise_registered_with_govt == true` | exclusion (self) | S | SECC item v. |
| P11 | `excl[5]` | `monthly_income_inr > 10000` | exclusion (some_family_member) | S | SECC item vi. |
| P12 | `excl[6]` | `paid_income_tax_last_assessment_year == true` | exclusion (some_family_member) | S | SECC item vii. |
| P13 | `excl[7]` | `paid_professional_tax == true` | exclusion (some_family_member) | S | SECC item viii. |
| P14 | `excl[8]` | `house_has_3_or_more_pucca_rooms == true` | exclusion (self) | S | SECC item ix ("pu cca" in the extracted text). |
| P15 | `excl[9]` | `owns_refrigerator == true` | exclusion (self) | S | SECC item x. |
| P16 | `excl[10]` | `owns_landline_phone == true` | exclusion (self) | S | SECC item xi. |
| P17 | `excl[11]` | `owns_gt_2_5_acres_irrigated_land_with_irrigation_equipment == true` | exclusion (self) | S | SECC item xii; compound fact folded into one boolean (documented). |
| P18 | `excl[12]` | `owns_5_or_more_acres_irrigated_land_two_or_more_crop_seasons == true` | exclusion (self) | S | SECC item xiii. |
| P19 | `excl[13]` | `owns_7_5_or_more_acres_land_with_irrigation_equipment == true` | exclusion (self) | S | SECC item xiv. |

All 14 SECC exclusions verified verbatim against the PIB SECC press release (primary).

### IGNOAPS (6)

| # | Location | Predicate | Kind | Class | Note |
|---|---|---|---|---|---|
| P01 | `incl.and[0]` | `age >= 60` | inclusion | S | NSAP guidelines §2.3. |
| P02 | `incl.and[1]` | `is_bpl_household == true` | inclusion | S | NSAP guidelines §2.3. |
| P03 | `excl[0]` | `has_regular_family_financial_support == true` | exclusion (self) | I | **Documented, and doubted by its own author.** The gold calls it "an interpretive elevation" of the programme-wide *destitute* definition (Para 1.1.1), "philosophical/preambular framing", which "may already be subsumed by the BPL determination". Across all 56 pages of the guidelines, "support from family" appears once, in that definition. |
| P04 | `excl[1]` | `is_govt_employee == true` | exclusion (self) | I *(borderline)* | Stated verbatim only inside the AIDS-widow carve-out (§2.4.3). Applying it to every applicant is the gold's documented reading. |
| P05 | `excl[2]` | `family_agricultural_land_acres >= 5` | exclusion (self) | I *(borderline)* | As P04. |
| P06 | `excl[3]` | `owns_four_wheeler == true` | exclusion (self) | I *(borderline)* | As P04. |

P04–P06 could defensibly be classed S: the words are in the source. They are classed I because the
gold applies them more broadly than the sentence that contains them. All three IGNOAPS PDFs were
searched for any text applying them generally — see §6, IGNOAPS.

### MH-LADKI-BAHIN (13)

| # | Location | Predicate | Kind | Class | Note |
|---|---|---|---|---|---|
| P01 | `incl.and[0]` | `is_woman == true` | inclusion | S | Para 4(2): "Married, widowed, divorced, abandoned, and destitute women of the State"; 4(1) "the beneficiary woman". Stated as the grammatical subject, not as a standalone clause — see §5. |
| P02 | `incl.and[1]` | `is_maharashtra_resident == true` | inclusion | S | Para 4(1). |
| P03 | `incl.and[2]` | `age >= 21` | inclusion | S | Para 4(3), as amended 03.07.2024. |
| P04 | `incl.and[3]` | `age <= 65` | inclusion | S | Para 4(3). |
| P05 | `incl.and[4]` | `has_bank_account == true` | inclusion | S | Para 4(4). |
| P06 | `incl.and[5]` | `family_annual_income_inr <= 250000` | inclusion | S | Para 4(5). |
| P07 | `excl[0]` | `paid_income_tax_last_assessment_year == true` | exclusion (some_family_member) | S | Para 5(2). |
| P08 | `excl[1]` | `is_regular_govt_employee_or_pensioner == true` | exclusion (some_family_member) | S | Para 5(3), as amended. |
| P09 | `excl[2]` | `other_govt_scheme_monthly_benefit_inr >= 1500` | exclusion (self) | S | Para 5(4). |
| P10 | `excl[3]` | `holds_constitutional_or_political_post == true` | exclusion (some_family_member) | S | Para 5(5). **See §3: the field is broader than the clause.** |
| P11 | `excl[4]` | `holds_govt_board_or_corporation_post == true` | exclusion (some_family_member) | S | Para 5(6). |
| P12 | `excl[5]` | `owns_four_wheeler == true` | exclusion (some_family_member) | S | Marathi GR item **(८)**. The English `.md` renumbers it 7; the gold's "5(8)" citation is correct. |
| P13 | `excl[5].except` | `owned_vehicle_is_farm_tractor_only == true` | exception | S | Same clause: "(ट्रॅक्टर वगळून)" — excluding tractors. |

Key terms spot-checked against the verbatim Marathi transcripts in `data/retrieval_corpus/`.

### PM-KISAN (11)

| # | Location | Predicate | Kind | Class | Note |
|---|---|---|---|---|---|
| P01 | `incl.and[0]` | `is_indian_citizen == true` | inclusion | I | The gold's CAVEAT records it as inferred from the Para 4.1(c) NRI exclusion. Confirmed accurate: the primary PDF's only occurrence of "citizens" concerns Aadhaar issuance in Assam/Meghalaya/J&K, not eligibility. |
| P02 | `incl.and[1]` | `owns_cultivable_land_in_records == true` | inclusion | S | Para 3. |
| P03 | `excl[0]` | `paid_income_tax_last_assessment_year == true` | exclusion (some_family_member) | S | Para 4.1(b)(v). |
| P04 | `excl[1]` | `is_serving_or_retired_govt_employee == true` | exclusion (some_family_member) | S | Para 4.1(b)(iii). |
| P05 | `excl[1].except` | `is_group_d_class_iv_or_mts == true` | exception | S | Same clause. |
| P06 | `excl[2]` | `monthly_pension_inr >= 10000` | exclusion (some_family_member) | S | Para 4.1(b)(iv). |
| P07 | `excl[2].except` | `is_group_d_class_iv_or_mts == true` | exception | S | Same clause. |
| P08 | `excl[3]` | `holds_constitutional_or_political_post == true` | exclusion (some_family_member) | S | Para 4.1(b)(i)–(ii), bundled (documented). |
| P09 | `excl[4]` | `is_practicing_registered_professional == true` | exclusion (some_family_member) | S | Para 4.1(b)(vi), abstracted (documented). |
| P10 | `excl[5]` | `is_institutional_landholder == true` | exclusion (self) | S | Para 4.1(a). |
| P11 | `excl[6]` | `is_nri_per_income_tax_act_1961 == true` | exclusion (some_family_member) | S | Para 4.1(c); quantifier a documented modeling choice. |

### PM-UJJWALA-2.0 (14)

| # | Location | Predicate | Kind | Class | Note |
|---|---|---|---|---|---|
| P01 | `incl.and[0]` | `is_woman == true` | inclusion | S | "adult woman". |
| P02 | `incl.and[1]` | `age >= 18` | inclusion | I | The source says "adult"; the gold records that no source states 18. |
| P03 | `incl.and[2]` | `is_indian_citizen == true` | inclusion | **U** | **Not in the source; no inference recorded.** The `source_clause` documents every other uncertainty and is silent on this one. |
| P04 | `incl.and[3].or[0]` | `is_bpl_household == true` | inclusion | S | Original PMUY base. |
| P05 | `incl.and[3].or[1]` | `is_in_secc_2011_list == true` | inclusion | S | Original PMUY base. |
| P06 | `incl.and[3].or[2]` | `is_sc_st == true` | inclusion | S | 2.0 category. |
| P07 | `incl.and[3].or[3]` | `is_pmay_g_beneficiary == true` | inclusion | S | 2.0 category. |
| P08 | `incl.and[3].or[4]` | `is_aay_beneficiary == true` | inclusion | S | 2.0 category. |
| P09 | `incl.and[3].or[5]` | `is_forest_dweller == true` | inclusion | S | 2.0 category. |
| P10 | `incl.and[3].or[6]` | `is_most_backward_class == true` | inclusion | S | 2.0 category. |
| P11 | `incl.and[3].or[7]` | `is_tea_garden_tribe == true` | inclusion | S | 2.0 category. |
| P12 | `incl.and[3].or[8]` | `lives_on_river_island == true` | inclusion | S | 2.0 category. |
| P13 | `incl.and[3].or[9]` | `meets_14_point_self_declaration == true` | inclusion | S | Fallback route. |
| P14 | `excl[0]` | `household_has_existing_lpg_connection == true` | exclusion (self) | S | "does not already have an LPG connection". |

### PMAY-G (14)

| # | Location | Predicate | Kind | Class | Note |
|---|---|---|---|---|---|
| P01 | `incl.or[0]` | `is_houseless == true` | inclusion | S | |
| P02 | `incl.or[1]` | `lives_in_kutcha_house == true` | inclusion | S | |
| P03 | `incl.or[2]` | `is_secc_automatically_included == true` | inclusion | S | Compulsory-inclusion categories stated; mapping onto AB-PMJAY's field is a documented modeling choice. |
| P04 | `excl[0]` | `is_govt_employee == true` | exclusion (some_family_member) | S | |
| P05 | `excl[1]` | `owns_non_agricultural_enterprise_registered_with_govt == true` | exclusion (self) | S | |
| P06 | `excl[2]` | `kisan_credit_card_limit_inr >= 50000` | exclusion (self) | S | "Rs. 50,000 or above" → `>=` (documented contrast with AB-PMJAY's `>`). |
| P07 | `excl[3]` | `monthly_income_inr > 15000` | exclusion (some_family_member) | S | |
| P08 | `excl[4]` | `paid_income_tax_last_assessment_year == true` | exclusion (some_family_member) | S | |
| P09 | `excl[5]` | `owns_refrigerator == true` | exclusion (self) | S | Stated in the `.md` — **but contradicted by the primary found in §4.** |
| P10 | `excl[6]` | `owns_landline_phone == true` | exclusion (self) | S | As P09. |
| P11 | `excl[7]` | `owns_gt_2_5_acres_irrigated_land == true` | exclusion (self) | S | `.md`: "more than 2.5 acres". Primary (§4): "2.5 acres or more". |
| P12 | `excl[8]` | `owns_motorised_three_or_four_wheeler == true` | exclusion (self) | S | |
| P13 | `excl[9]` | `owns_mechanized_agricultural_equipment_3_or_4_wheeler == true` | exclusion (self) | S | |
| P14 | `excl[10]` | `owns_pucca_house == true` | exclusion (self) | S | |

Classified S against the `.md`, which is all the gold was built from. §4 shows that `.md` is wrong.

### PMMVY (15)

| # | Location | Predicate | Kind | Class | Note |
|---|---|---|---|---|---|
| P01 | `incl.and[0]` | `age >= 18` | inclusion | S | **See §3: the source says 18 years 7 months.** |
| P02 | `incl.and[1]` | `age <= 55` | inclusion | S | |
| P03 | `incl.and[2].or[0]` | `is_sc_st == true` | inclusion | S | |
| P04 | `incl.and[2].or[1]` | `has_40_percent_or_more_disability == true` | inclusion | S | "partial (40% or more) or full". |
| P05 | `incl.and[2].or[2]` | `is_bpl_household == true` | inclusion | S | |
| P06 | `incl.and[2].or[3]` | `is_ab_pmjay_beneficiary == true` | inclusion | S | |
| P07 | `incl.and[2].or[4]` | `is_e_shram_registered == true` | inclusion | S | |
| P08 | `incl.and[2].or[5]` | `is_pm_kisan_beneficiary == true` | inclusion | S | |
| P09 | `incl.and[2].or[6]` | `has_active_mgnrega_job_card == true` | inclusion | S | |
| P10 | `incl.and[2].or[7]` | `family_annual_income_inr < 800000` | inclusion | S | "less than Rs. 8 lakh". |
| P11 | `incl.and[2].or[8]` | `is_frontline_worker == true` | inclusion | S | |
| P12 | `incl.and[2].or[9]` | `is_nfsa_ration_card_holder == true` | inclusion | S | |
| P13 | `incl.and[3].or[0]` | `pregnancy_child_order == 1` | inclusion | S | "first living child". **See §3.** |
| P14 | `incl.and[3].or[1].and[0]` | `pregnancy_child_order == 2` | inclusion | S | "second living child". **See §3.** |
| P15 | `incl.and[3].or[1].and[1]` | `child_is_girl == true` | inclusion | S | |

## 3. Sourced but mis-encoded

| Scheme | Issue | Effect | Priority |
|---|---|---|---|
| **AB-PMJAY** | The 14 socio-economic exclusions apply to every inclusion path, including 70+. The NHA guidelines cover 70+ citizens *"irrespective of their socio-economic status"*, and never apply the SECC exclusions to them. | **A wrong "ineligible" from the live app.** Verified with the real evaluator: a 70+ senior with a refrigerator, a landline, a member earning >₹10k, or a member paying income tax is denied. The gold's own 70+ profile set every exclusion false, so this was never exercised. | Fixed — §6 |
| **PMMVY** | Source floor: *"18 years 7 months"*. Gold: `age >= 18`. Not recorded; the `source_clause` claims the age criterion was "corroborated verbatim". | **A wrong "eligible"** — the harmful direction — for women aged 18y0m–18y6m. | Fixed — §6 |
| PMMVY | "First / second **living** child" encoded as `pregnancy_child_order`. Birth order is not living-child order. Undocumented. | Wrong verdicts where an earlier child has died. | Documented only |
| PMAY-G | Source says exclusions were *"reduced from 13 to 10 parameters"*, then lists 11. | One predicate spurious or the count wrong. **Resolved by a primary found during this audit — §4.** | Documented only |
| PMAY-G | Identically worded "Households with…" clauses get `some_family_member` (govt employee, income, tax) or `self` (enterprise, assets, land). Undocumented. | Inconsistent family-level handling. | Documented only |
| MH-LADKI-BAHIN | GR clause (५) is literally "current or former **MP/MLA**". The gold reuses PM-KISAN's broader `holds_constitutional_or_political_post`. | Would wrongly exclude a family with, e.g., a former mayor. | Documented only |

## 4. PMAY-G: a primary source turned up during the audit

`data/raw_documents/IGNOAPS_primary.pdf` is mislabelled: it is the **Ministry of Rural Development
Annual Report 2024-25** (447 pages). It covers PMAY-G, and it is the primary-quality source this
gold never had. Its "revised automatic exclusion criteria under the new phase of the PMAY-G":

> Step 1: Exclusion of pucca houses — All households living in houses with pucca roof and/or pucca
> wall and households living in houses with more than 2 rooms are filtered out.
> Step 2: Automatic Exclusion criteria — … any one of the 10 parameters listed below …
> i. Motorised three/four-wheeler · ii. Mechanised three/four-wheeler agricultural equipment ·
> iii. Kisan Credit Card with credit limit of Rs. 50,000 or above · iv. Household with any member
> as a Government employee · v. Households with non-agricultural enterprises registered with the
> Government · vi. Any member of the family earning more than Rs.15,000 per month · vii. Paying
> income tax · viii. Paying professional tax · ix. Own 2.5 acres or more of irrigated land ·
> x. Own 5 acres or more of unirrigated land

and, a page earlier: *"the provisions with regard to mechanised two-wheelers, mechanised fishing
boats, **landline phones and refrigerators have been deleted**."*

So the "11 vs 10" puzzle is real but its answer is four concrete gold errors, not a miscount:

| Gold predicate | Primary says | Error |
|---|---|---|
| `owns_refrigerator` | deleted by Cabinet | **wrong exclusion** — denies eligible households |
| `owns_landline_phone` | deleted by Cabinet | **wrong exclusion** — denies eligible households |
| *(absent)* | viii. paying professional tax | missing exclusion |
| *(absent)* | x. 5+ acres unirrigated land | missing exclusion |
| `owns_gt_2_5_acres_irrigated_land` | "2.5 acres **or more**" | `>` should be `>=` |
| `owns_pucca_house` | Step 1 filter: pucca roof **and/or** wall, or >2 rooms | a pre-filter, not one of the 10 — explains the count; definition broader than the gold field |

The two wrong exclusions produce a wrong "ineligible" for households owning a refrigerator or a
landline. **Not fixed in this pass**: PMAY-G was scoped as document-only, and whether to adopt the
annual report as the authoritative source is a decision for the gold owner. Logged in
`KNOWN_ISSUES.md` with this resolution path.

## 5. The "preambular / implied-fact miss" recount

Four extractor omissions had been counted toward a "preambular / implied-fact" failure pattern. In
all four the field is absent from the extractor's `draft_extraction` and present only in
`gold_fields` or a diff's `missing` list, so the omission itself is real. Whether it is a fault
depends on whether the extractor's input stated the rule. Every one of these runs read its scheme's
`.md`, and the extractor's own prompt says *"Only extract what the document actually states."*

| Case | Omitted by extractor? | Stated in the extractor's input? | Gold class | Verdict |
|---|---|---|---|---|
| PM-KISAN `is_indian_citizen` | yes | **no** | I | **Gold-side.** The extractor followed its input and its instructions. |
| IGNOAPS `has_regular_family_financial_support` | yes | only as programme-wide preamble | I (doubted by its author) | **Gold-side** — contested. |
| MH-LADKI-BAHIN `is_woman` | yes | **yes**, operative clause 4(2) | S | **Genuine extractor miss.** |
| PM-UJJWALA-2.0 `is_indian_citizen` | yes | **no** | U | **Gold-side.** |

**Honest recurrence: 1 of 4.** And the one genuine case was mislabelled: `is_woman` is not
preambular. It sits in the operative eligibility clause, as the grammatical subject ("…women of the
State"). The real pattern is narrower: *an eligibility condition expressed as the subject of every
clause rather than as a clause of its own.* The judge caught it and repair added it, which is the
pipeline working as designed. At n=1 it is an observation, not a finding.

**Consequence for Baseline 2.** Every harmful-direction disagreement it reported sits on a predicate
classed I or U here: both IGNOAPS cases turn on `has_regular_family_financial_support`, and the
PM-UJJWALA case turns on its unsourced citizenship predicate. On sourced gold alone, Baseline 2 had
no unambiguous harmful error — which does not show the LLM was right, only that the measurement
could not separate LLM error from gold error exactly where every harmful case sat.

## 6. Fixes applied

*Recorded as each fix lands. Every change is also written into the scheme's own `source_clause`.*

(pending)

## 7. Superseded figures

*Old and corrected numbers, side by side, once the fixes are re-evaluated.*

(pending)
