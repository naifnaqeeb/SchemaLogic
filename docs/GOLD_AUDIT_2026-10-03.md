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

`data/raw_documents/IGNOAPS_primary.pdf` is the whole **Ministry of Rural Development Annual Report
2024-25** (447 pages). It is filed under IGNOAPS deliberately — the IGNOAPS gold cites its
pp.156–163, which cover NSAP — but the same report also covers PMAY-G, and for PMAY-G it is the
primary-quality source that gold never had. *(An earlier draft of this audit called the file
"mislabelled"; the IGNOAPS fixture's own header shows the annotator knew what it was, so that
overstated it.)* Its "revised automatic exclusion criteria under the new phase of the PMAY-G":

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
landline. **Fixed 2026-10-04 — §6.8.** *Originally:* **Not fixed in this pass**: PMAY-G was scoped as document-only, and whether to adopt the
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

Each fix followed the same order: write a profile that exercises the conflict, confirm it fails
against the current gold, change the gold, confirm it passes, and confirm every pre-existing profile
gives the same verdict as before. Both copies of the gold set were changed together, enforced by
`test_gold_json_and_test_fixture_copies_hold_identical_rules`.

### 6.1 AB-PMJAY — the 70+ route bypasses the socio-economic exclusions

**Change.** Every one of the 14 exclusions now carries
`except: has_family_member_aged_70_or_above == true`, with `except_scope: "applicant"`.
*(Revised 2026-10-04 after an independent review, §6.6: the 10 `self` exclusions now use the default
member scope — identical verdicts — and only the 4 `some_family_member` exclusions keep
`"applicant"`.)*

**Why an exception at all.** The required logic is
`eligible = 70plus ∨ (other_routes ∧ ¬excluded)`. A flat exclusion list computes
`(70plus ∨ other_routes) ∧ ¬excluded`, which blocks the 70+ route. The two are equal once every
exclusion carries `∧ ¬70plus`, i.e. an exception on the 70+ fact.

**Why a new scope, and not a plain `except`.** The schema's `except` was member-local: the
evaluator read it from whichever member triggered the exclusion. Four of these exclusions are
`some_family_member` (government employee, income above ₹10,000, income tax, professional tax), so
they are usually triggered by someone other than the applicant — but the 70+ fact is a household
fact, recorded on the applicant. Tested before choosing, with the real evaluator:

| Case | Wanted | Plain member-scoped `except` |
|---|---|---|
| 70+ household, applicant's household owns a refrigerator (`self`) | eligible | eligible ✓ |
| 70+ household, a family member pays income tax (`some_family_member`) | eligible | **undetermined** ✗ |
| *Control:* non-70+ household, a family member pays income tax | ineligible | **undetermined** ✗ — a regression |

The exception was read off the tax-paying member's record, found nothing, and turned both the fix
and a currently-correct verdict into "undetermined". So the evaluator gained `except_scope`
(`schemelogic/schema/models.py`, `ExceptScope`): `"member"` is the default and preserves every
existing exclusion exactly; `"applicant"` reads the exception once from the applicant's record.
`question_selector` asks the applicant (not "one of your family members") when that fact is
missing, and the citizen-facing explanation now says an exclusion was *waived* rather than "doesn't
apply" — a 70+ senior who owns a refrigerator should not be told they don't own one.

**Tests.** 6 engine-level tests for the new scope (`tests/test_symbolic_engine.py`, including one
that pins the member-scoped failure above as the reason the scope exists) and 6 AB-PMJAY tests
(`tests/test_gold_schemes.py`). Five of those six failed against the old gold, as intended; the
sixth is a control showing the exclusions still apply in full to every non-70+ route.

**Profiles added** to `data/profiles/AB-PMJAY.json`:

| Profile | Old gold | New gold |
|---|---|---|
| `seventy_plus_household_refrigerator_and_landline` | ineligible | **eligible** |
| `seventy_plus_family_member_pays_income_tax` | ineligible | **eligible** |

All 8 pre-existing AB-PMJAY profiles give identical verdicts under the old and new gold.

**Cost.** The new field appears in the extraction JSON schema: +112 tokens per core extraction
call. The scope's rationale is kept as a code comment rather than a docstring because Pydantic
embeds docstrings in the schema — as a docstring it cost +436 tokens per call. *(Superseded
2026-10-04, §6.6: the field is now removed from the extraction schema entirely, so the cost is 0.)*

**Caveat, recorded in the `source_clause`.** Under the guidelines the 70+ cover belongs to the 70+
members, shared on a family basis. This gold keeps its existing household-level modelling of that
route; the fix only stops the socio-economic exclusions from blocking it. The clause establishing
who the cover extends to has since been found — §6.5.

### 6.2 PMMVY — the age floor is 18 years 7 months

**Change.** New final conjunct `or[age >= 19, months_since_last_birthday >= 7]`, and a new ontology
field `months_since_last_birthday` (0–11, citizen question: *"How many full months have passed since
your last birthday?"*).

**Why this encoding.** Citizens are asked their age in whole years, so 18 is the only value that
can't decide the floor on its own. Alternatives rejected: a fractional `age >= 18.583` would turn
every whole-year answer of 18 into "ineligible", wrongly rejecting 18y7m–18y11m; a single age-in-
months field would ask every applicant their age in months. The coarse `age >= 18` stays as the first
conjunct, so a 17-year-old is ruled out at the first question.

**Why last.** The question selector asks every unresolved leaf, including ones under an `or` that is
already satisfied (logged separately in `KNOWN_ISSUES.md` — on PMMVY it asks 9 irrelevant questions
of an applicant who has already qualified). Placed earlier, `months_since_last_birthday` would have
been the second question for *every* applicant. Placed last, the verdict is settled before it is
reached for anyone aged 19 or over. A test pins this.

**The `source_clause` claim.** It said the age criterion was "corroborated verbatim" by a second
official source. That was true of the source *text* — which says 18 years 7 months — but read as a
claim about the encoding, which was false. It now says so explicitly. The fixture's own header
comment also quoted "18 years 7 months", so the discrepancy was visible at annotation time.

**Tests.** 7 new (`tests/test_gold_schemes.py`); four failed against the old gold — 18y3m and 18y6m
were wrongly eligible, 18 with months unknown was wrongly eligible rather than undetermined, and the
precise question didn't exist.

**Profiles added** to `data/profiles/PMMVY.json`:

| Profile | Old gold | New gold |
|---|---|---|
| `eighteen_years_three_months_below_floor` | eligible | **ineligible** |
| `eighteen_years_seven_months_at_floor` | eligible | eligible *(boundary control)* |

All 10 pre-existing PMMVY profiles give identical verdicts under the old and new gold.

**Unchanged and still unmodelled:** the source measures age *at the time of childbirth*; both bounds
here use the applicant's current age.

### 6.3 PM-UJJWALA-2.0 — `is_indian_citizen` removed

**Change.** The inclusion predicate `is_indian_citizen == true` is removed.

**Why.** It was the gold set's one unsourced predicate (§2). The source never mentions citizenship,
and the `source_clause` — which documents every other uncertainty in this scheme in detail — never
accounted for it. PM-KISAN's citizenship predicate is different and stays: it is a documented
inference from that scheme's NRI exclusion, and the audit confirmed the inference is accurate. The
new `source_clause` records the condition for restoring it: cite a primary PMUY 2.0 clause that
requires citizenship.

**Tests.** 2 new (`tests/test_gold_schemes.py`), both failing against the old gold: a non-citizen
meeting every stated criterion is eligible, and citizenship is never asked. No existing test had
asserted the rule — the UJJWALA tests only set `is_indian_citizen: True` as a background fact, which
the evaluator now ignores.

**Profile renamed** in `data/profiles/PM-UJJWALA-2.0.json`, facts byte-identical so earlier results
on it stay comparable:

| Profile | Old gold | New gold |
|---|---|---|
| `non_citizen_ineligible` → `non_citizen_not_excluded_by_source` | ineligible | **eligible** |

All 8 other PM-UJJWALA profiles give identical verdicts under the old and new gold.

### 6.4 IGNOAPS — family support removed; the carve-out criteria scoped to the carve-out

**Changes.**
1. The exclusion `has_regular_family_financial_support` is removed.
2. The three criteria — government job, five acres or more, a four-wheeler for own use — are no
   longer exclusions applied to every applicant.
3. The NSAP Para 2.4.3 carve-out is modelled as an alternative to BPL status, with those three
   criteria as its conditions. New field `is_widow_suffering_from_aids`.

```
before:  age >= 60  AND  is_bpl_household
         EXCLUDE if: family support | govt job | land >= 5 acres | four-wheeler

after:   age >= 60  AND  ( is_bpl_household
                           OR ( is_widow_suffering_from_aids AND NOT govt job
                                AND land < 5 acres AND NOT four-wheeler ) )
         (no exclusions)
```

**Why (1).** Its own author called it "an interpretive elevation" of NSAP's programme-wide
*destitute* definition (Para 1.1.1) — "philosophical/preambular framing" that "may already be
subsumed by the BPL determination". Across the 56-page guidelines, "support from family" appears
only in that definition. Both of Baseline 2's IGNOAPS harmful errors turned on it.

**Why (2), and the search behind it.** You asked for the criteria to be restricted to the carve-out
*unless* some source applied them generally. All three IGNOAPS sources were searched: in the NSAP
guidelines and the PIB backgrounder they appear only inside Para 2.4.3; the MoRD annual report has 8
other hits, and every one concerns PMAY-G's exclusion list, the SECC exclusion list, or the 1997 BPL
census methodology — none applies them to IGNOAPS. The default held.

**Why (3) — a judgement call you may want to revisit.** "Restrict to the carve-out's scope" can be
read two ways:
- **Model the carve-out** (done): the criteria survive, but gate only the AIDS-widow route. This
  follows the grammar of Para 2.4.3 — *"only BPL persons … would be considered … except widows
  suffering from AIDS who will be considered if they are not attracted by any of the exclusion
  criteria"* — which is an exception to the BPL requirement.
- **Delete them**, leaving the carve-out unmodelled, as the original gold had flagged it.

The modelled version is more faithful, and it's the only one that doesn't wrongly reject a non-BPL
widow living with AIDS. **But it has a real cost: every non-BPL applicant aged 60+ is now asked
whether she is a widow living with HIV/AIDS.** The question is worded respectfully and says why it's
asked, but it's a sensitive question on a common path. Two ambiguities also remain, both recorded in
the `source_clause`: Para 2.4.3 sits under a heading about *priority* for vulnerable groups, so it
may have been meant as a processing note; and it may be aimed at the widow pension rather than
IGNOAPS.

**Tests.** Five tests asserting the old rules were *replaced*, not deleted, so the three criteria
stay covered under their correct scope: they now rule out the carve-out route and leave the BPL route
alone. 12 tests in the new block; 7 failed against the old gold as intended.

**Profiles.** Facts of all 8 existing profiles are unchanged, so earlier results on them stay
comparable; only their `_comment` metadata changed. Verdicts:

| Profile | Old gold | New gold |
|---|---|---|
| `eligible_baseline` | eligible | eligible |
| `under_60` | ineligible | ineligible |
| `not_bpl` | ineligible | **undetermined** — non-BPL, carve-out status not stated |
| `has_family_support` | ineligible | **eligible** |
| `govt_employee` | ineligible | **eligible** |
| `five_acres_land` | ineligible | **eligible** |
| `owns_four_wheeler` | ineligible | **eligible** |
| `missing_support_data` | undetermined | **eligible** — the missing fact is no longer a criterion |
| *new* `not_bpl_not_aids_widow` | ineligible | ineligible |
| *new* `aids_widow_non_bpl_clear_of_criteria` | ineligible | **eligible** |
| *new* `aids_widow_non_bpl_owns_four_wheeler` | ineligible | ineligible |
| *new* `missing_bpl_status_undetermined` | undetermined | undetermined |

The last profile keeps IGNOAPS's missing-data case — the probe the Baseline 2 silent-default analysis
depends on, which `missing_support_data` no longer is.

### 6.5 AB-PMJAY — who the 70+ cover extends to ("on a family basis")

*Found 2026-10-04. Fixed the same day after a decision — §6.7.*

**The clause.** `AB-PMJAY_primary_70plus_expansion.pdf`, §5.2 (new families):

> For the senior citizens of the age of 70 years and above in the new families, a shared cover up
> to Rs 5 lakh per year will be available. This cover will not be available to the other members
> (who are not of the age 70 years and above) of these new families.

§5.1 gives the 70+ members of families *already* covered an additional shared top-up, and the
enrolment annex treats a person whose own eKYC age is below 70 as "not eligible under the scheme".
"On a family basis" therefore means the cover is *shared among* the household's 70+ members — not
that it extends to the household.

**Consequence.** The gold encodes the route as `has_family_member_aged_70_or_above` on the
applicant's record: a household fact. That is right when the applicant is the senior. It is wrong
for a younger applicant in a household with a 70+ member and no other route: the gold says
**eligible**, §5.2 says that person is not covered by the route. Verified with the evaluator on a
40-year-old applicant with a 70+ parent, no SECC deprivation and no occupational category: eligible.

**Proposed fix (approved 2026-10-04, applied in §6.7).** Re-encode the route on the applicant's own age — `age >= 70` (the ontology field is `age`)
on `self` — in the inclusion and in all 14 exceptions. Every exclusion's exception then reads the
applicant's age, so the four `some_family_member` exclusions still need applicant scope. Open
question that decision must also settle: whether a younger household member asking *on behalf of*
the senior should be modelled at all (the conversational flow currently always evaluates "you").

### 6.6 `except_scope` revised after independent review

On 2026-10-04 a reviewer agent that had not seen the implementation reasoning was given only the
evaluator diff, the new tests and the guideline text. Its findings, and what changed:

| Finding | Change |
|---|---|
| **F1** (major): with `count_family_members`, waiving member by member made the waiver act as a *trigger* — `count < 1` fired because the route zeroed every member | Applicant scope now waives the whole exclusion once: `Q(condition over members) ∧ ¬exception(applicant)`. For `some_family_member` this is equivalent to the old form; for `all_family_members` and counts it is the only correct one. |
| **Q3**: count `== 1`, two taxpayers, route unknown → undetermined, though neither completion can fire it | Fixed by the same change (the shared waiver is one unknown, not one per member). Reproducer test added. |
| **F3**: the trace reported a scope where no exception existed | The trace reports `"member"` when there is no exception. |
| **F4**: applicant scope with quantifier `self` is meaningless | Rejected by the model validator. AB-PMJAY's 10 `self` exclusions moved to member scope; all 10 profiles give identical verdicts. |
| **F5**: extraction could emit applicant scope | Removed from the extractor's JSON schema entirely, and any emitted value is forced to member. Applicant scope is gold-only, justified against source text. A cached AI-Checked scheme carrying it is refused. |

Coverage: every combination in the review's table is a test, plus a three-member test pinning that
the question selector asks the applicant (not `family_members[0]`) for an applicant-scoped
exception fact. The review's two fuzzers are now `tests/test_engine_fuzz.py`:

- **Preservation** — member scope against a frozen copy of the pre-`except_scope` evaluator
  (`tests/reference/`): **40,000 cases, 0 differences** in verdict, exception or trace.
- **Soundness** — every definite verdict checked against every completion of the missing facts,
  all quantifiers, both scopes: **30,000 cases, 0 unsound** (61 skipped for >7 missing facts).
  Undetermined-although-decided: 1,449 of 5,098 applicant-scope undetermined, 1,171 of 4,169
  member-scope — the same ~28% in both, the pre-existing gap from one field feeding several
  predicates, not something the scope adds. Not asserted; printed.
- A targeted test (count quantifiers, applicant scope, disjoint fields) **fails against the
  pre-review evaluator and passes now**.

**Gold serialization.** Gold is now written with `exclude_defaults=True` (`models.dump_gold_json`,
used by the review app and `scripts/audit_gold.py format`). The existing files were *not* in that
form — a plain re-dump differed by 20–244 lines per file — so all 7 were canonicalized once, each
proven model-equal before and after and byte-idempotent on a second pass. From here, re-serializing
produces no diff; `test_every_gold_file_is_in_canonical_form` enforces it, and
`test_except_scope_appears_in_gold_only_where_genuinely_applicant` pins the four AB-PMJAY
exclusions as the only applicant-scoped ones.

### 6.7 AB-PMJAY — the 70+ route tests the applicant's own age

*2026-10-04. Fixes the consequence recorded in §6.5.*

**Change.** The inclusion branch and all 14 exceptions now read `age >= 70` on the applicant's
record, replacing `has_family_member_aged_70_or_above`. The four `some_family_member` exclusions keep
applicant scope, so it is the applicant's age that waives a relative's income tax, income or
government job. `has_family_member_aged_70_or_above` is retired in the ontology (same pattern as
earlier retired fields); `age` now lists AB-PMJAY.

**Protocol.** The failing profile came first — `younger_applicant_with_seventy_plus_parent`: a
40-year-old, 74-year-old parent in the household, no SECC, RSBY or urban-worker route. Old gold:
**eligible**. Confirmed failing as a test against the old gold, then fixed. New gold: **ineligible**.

**Tests added** (`tests/test_gold_schemes.py`): the failing profile; the same household from the
senior's side (the 74-year-old applying is eligible, with a tax-paying, high-earning relative); the
boundary (69 ineligible, 70 and 71 eligible — "70 years of age and above"); and a 75-year-old
relative not waiving a 45-year-old applicant's refrigerator exclusion. The existing AB-PMJAY tests
now give the applicant an age (45, or 72 for the 70+ cases). Their base profile also states
`is_urban_informal_worker: false` explicitly: the household flag had been making the inclusion true
regardless, which hid that this fact was missing.

**Profiles.** Every profile whose verdict needs it now gives the applicant an age: 45 where the
household flag was false, 72 where it was true (the applicant is the senior). The household flag is
kept, so the pre-fix gold can still be evaluated beside the new. `eligible_baseline` (SECC-deprived,
nothing excluded) is decided without age and was left unchanged. Every pre-existing profile gives the
same verdict under old and new gold; only the new profile changes:

| Profile | Old gold | New gold |
|---|---|---|
| *new* `younger_applicant_with_seventy_plus_parent` | eligible | **ineligible** |
| the 10 existing profiles | unchanged | unchanged |

**Not modelled.** Someone asking on a senior's behalf (the conversational flow evaluates the person
answering), and the §5.1 top-up for 70+ members of families already covered — a benefit amount, not
an eligibility rule.

### 6.8 PMAY-G — exclusions taken from the MoRD Annual Report 2024-25

*2026-10-04. Resolves §4: the annual report is adopted as PMAY-G's source for its exclusions.*

**Source.** Ministry of Rural Development Annual Report 2024-25, p.141, "revised automatic exclusion
criteria under the new phase of the PMAY-G" (quoted in §4), and the sentence before it: *"As per the
Union Cabinet approval, the provisions with regard to mechanised two-wheelers, mechanised fishing
boats, landline phones and refrigerators have been deleted."* Re-read from the PDF for this fix.

**Change.** The 11 exclusions become 12, in the report's order:

| Report | Gold before | Gold after |
|---|---|---|
| Step 1: pucca roof and/or pucca wall | `owns_pucca_house` (a fully pucca house) | `house_has_pucca_roof_or_wall == true` |
| Step 1: more than 2 rooms | *(absent)* | `house_room_count > 2` |
| i–vii | as before | unchanged (same fields, operators, quantifiers) |
| viii. Paying professional tax | *(absent)* | `paid_professional_tax` (`some_family_member`, like income tax) |
| ix. 2.5 acres **or more** irrigated | `owns_gt_2_5_acres_irrigated_land` ("more than") | `irrigated_land_acres >= 2.5` |
| x. 5 acres or more unirrigated | *(absent)* | `unirrigated_land_acres >= 5` |
| *(deleted by the Cabinet)* | `owns_refrigerator`, `owns_landline_phone` | **removed** |

Quantifiers follow the report's wording: "any member" items (iv, vi) are `some_family_member`;
household assets and holdings are household facts on the applicant's record; the two "paying … tax"
items are `some_family_member`, as income tax already was. The "11 vs 10" count is explained: the
pucca filter is Step 1, not one of the 10. `owns_pucca_house` and `owns_gt_2_5_acres_irrigated_land`
are retired in the ontology; four fields are new. The extraction prompt is 427 characters shorter.

**Protocol.** Tests first, against the old gold: refrigerator and landline no longer exclude;
professional tax excludes; 5 acres unirrigated excludes (4.9 doesn't); exactly 2.5 acres irrigated
excludes (2.4 doesn't); 3 rooms excludes (2 doesn't); a pucca roof or wall alone excludes. 9 failed
before the fix, all pass after.

**Profiles.** Every profile now carries the report's facts alongside the old ones, so the old gold can
still be evaluated beside the new. Four profiles added, one per new criterion. Old vs new:

| Profile | Old gold | New gold |
|---|---|---|
| `refrigerator` | ineligible | **eligible** |
| `landline_phone` | ineligible | **eligible** |
| *new* `professional_tax_family_member` | eligible | **ineligible** |
| *new* `unirrigated_land_five_acres` | eligible | **ineligible** |
| *new* `irrigated_land_exactly_two_and_a_half_acres` | eligible | **ineligible** |
| *new* `kutcha_house_with_three_rooms` | eligible | **ineligible** |
| the other 8 | unchanged | unchanged |

**Still open.** Whether Step 1 and the 10 parameters apply to compulsory-inclusion households (the gold
applies every exclusion to every route, as before). The inclusion side is still sourced from the PIB
backgrounder; confidence (0.75) and the review flag are unchanged for that reason.

## 7. Superseded figures

Every figure below that the fixes touched, recomputed on 2026-10-04. Reproducible:
`scripts/reevaluate_gold_fixes.py` (outcome equivalence, structural F1 — offline),
`scripts/rescore_baseline2.py` and `scripts/summarize_baseline2.py` (Baseline 2).

**How "old" was verified.** Each old outcome-equivalence and structural-F1 figure was *reproduced*
from the pre-fix gold and profiles, read out of git at the audit snapshot `5662498`, before being
compared. All of them reproduced exactly (F1 at the 4-decimal precision it was recorded at), so the
corrected numbers come from the same drafts and the same functions — only the gold and profile
suites differ.

**How Baseline 2 was re-scored.** Its LLM is shown the scheme document and the profile facts, never
the gold. For the 35 profiles whose facts are byte-identical to an earlier run (checked against that
run's commit, including the renamed PM-UJJWALA profile), the stored answer was reused and re-scored
against the corrected gold; only the 8 new profiles were asked live (~23.9k tokens, estimated). Each
row records its `answer_source`.

### 7.1 Baseline 2 — direct-LLM eligibility answering

| Scheme | Old n | Old agree | Old harmful FP | Old FN | | New n | New agree | New harmful FP | New FN |
|---|---|---|---|---|---|---|---|---|---|
| AB-PMJAY | 8 | 100.0% | 0.0% | 0.0% | → | 10 | **80.0%** | 0.0% | **20.0%** |
| IGNOAPS | 8 | 75.0% | 25.0% | 0.0% | → | 12 | **66.7%** | **0.0%** | **25.0%** |
| PM-UJJWALA-2.0 | 9 | 88.9% | 11.1% | 0.0% | → | 9 | **100.0%** | **0.0%** | 0.0% |
| PMMVY | 10 | 100.0% | 0.0% | 0.0% | → | 12 | 100.0% | 0.0% | 0.0% |
| PM-KISAN | 12 | 91.7% | 0.0% | 0.0% | | 12 | 91.7% | 0.0% | 0.0% *(unchanged)* |
| MH-LADKI-BAHIN | 10 | 100.0% | 0.0% | 0.0% | | 10 | 100.0% | 0.0% | 0.0% *(unchanged)* |
| PMAY-G | 10 | 100.0% | 0.0% | 0.0% | | 10 | 100.0% | 0.0% | 0.0% *(unchanged)* |
| **Aggregate** | **67** | **94.0%** | **4.5%** | **0.0%** | → | **75** | **90.7%** | **0.0%** | **6.7%** |
| *excl. contested* | *66* | *95.5%* | *3.0%* | *0.0%* | | *—* | *(no contested rows remain)* | | |

New breakdown: 68 agree, 5 false negative, 1 over-cautious (PM-KISAN, unchanged), 1 other (IGNOAPS
`not_bpl`: LLM "ineligible", gold now undetermined because the carve-out's fact is absent).

**Silent default on missing information** — every profile on which the evaluator returns
undetermined:

| | Old | New |
|---|---|---|
| Profiles where the rules couldn't decide | 7 | 8 |
| LLM answered "unsure" (correct deferral) | 6 | 7 |
| **LLM answered "eligible" anyway** | **1 (IGNOAPS)** | **0** |
| LLM answered "ineligible" anyway | 0 | 1 (IGNOAPS `not_bpl`) |

### 7.2 Outcome equivalence — extraction draft vs gold

| Figure | n | Agree | FP (eligible) | FN (eligible) | Other |
|---|---|---|---|---|---|
| AB-PMJAY, Phase 3 check-in | 8 → 10 | 100.0% → **80.0%** | 0.0% → 0.0% | 0.0% → **20.0%** | 0.0% → 0.0% |
| PM-UJJWALA-2.0, Phase 3 check-in | 9 → 9 | 88.9% → **100.0%** | 11.1% → **0.0%** | 0.0% → 0.0% | 0.0% → 0.0% |
| IGNOAPS, ontology draft (pre-repair) | 8 → 12 | 62.5% → **58.3%** | 12.5% → **0.0%** | 0.0% → **25.0%** | 25.0% → 16.7% |
| IGNOAPS, post judge+repair | 8 → 12 | 62.5% → **33.3%** | 0.0% → 0.0% | 0.0% → **25.0%** | 37.5% → 41.7% |

PMMVY was never extracted, so it has no outcome-equivalence figure to supersede.

### 7.3 Structural F1

| Figure | Old (recorded) | New |
|---|---|---|
| AB-PMJAY, Phase 3 check-in | 1.000 | 1.000 — **blind to the fix**: the metric never scores `except` clauses |
| PM-UJJWALA-2.0, Phase 3 check-in | 0.963 | **1.000** |
| PM-UJJWALA-2.0, citizenship-category F1 | 0.0 (fn = 1) | **category no longer present** — the "miss" was the unsourced predicate |
| IGNOAPS (either draft) | never reported | 0.286 / 0.267 *(pre-fix would have been 0.714 / 0.667; reported here for completeness, not superseding anything)* |

### 7.4 Superseded claims

These earlier statements should no longer be cited:

| Earlier claim | Status |
|---|---|
| Baseline 2: 94.0% agreement, **4.5% harmful false positives**, 0% false negatives (n=67) | **Superseded** by 90.7% / **0.0%** / **6.7%** (n=75). |
| "Every harmful Baseline 2 error rests on contested or unsourced gold" | **Confirmed and now resolved**: with that gold corrected, there are none. |
| IGNOAPS as an example of the LLM **silently defaulting to "eligible"** on missing information | **Withdrawn.** It was an artifact of the doubted family-support predicate. On corrected gold the LLM never defaulted to eligible (0/8). |
| "The direct baseline handled exception clauses correctly" (2026-09-19) | **Narrowed.** True of *member-level* exceptions stated next to their exclusion (PM-KISAN Group D, MH-LADKI-BAHIN tractor). False of *route-level* exemptions stated elsewhere in the document (AB-PMJAY 70+) — see §7.5. |
| PM-UJJWALA extractor citizenship miss (F1 0.0) | **Withdrawn** — gold-side, the predicate was unsourced. |
| "Preambular / implied-fact miss" recurring 4 times | **Superseded** by 1 of 4 (§5). |
| AB-PMJAY extraction draft: 100% outcome agreement with gold | **Superseded** by 80.0% — the 100% was a shared error (§7.5) — and then by 72.7% after the §6.7 re-encoding (§7.6). |
| Baseline 2: 90.7% agreement, **0.0% harmful false positives**, 6.7% false negatives (n=75) | **Superseded** by 89.5% / **1.3%** / 6.6% (n=76) after the §6.7 re-encoding (§7.6). |
| AB-PMJAY structural F1 1.000 | **Superseded** by 0.947 (§7.6). |
| PMAY-G extraction draft: 90.0% outcome agreement, structural F1 0.857 | **Superseded** by 50.0% / 0.552 against the MoRD-sourced gold (§7.7) — mostly a source gap, see the caveat there. |
| Baseline 2: 89.5% agreement, 1.3% harmful FP, 6.6% FN (n=76) | **Superseded** by 82.5% / 6.2% / 8.8% (n=80) (§7.7). |
| PMAY-G Baseline 2: 100% agreement | **Superseded** by 57.1% (§7.7). |

### 7.5 What the corrections show

1. **Baseline 2's errors switched direction.** On the old gold, its errors looked like the harmful
   false positives the project's framing is built around, including one apparent silent default. On
   corrected gold it had **no** false positives and **five false negatives** (one harmful false
   positive has since appeared, from the §6.7 fix — §7.6): in every one, it
   applied an exclusion to someone the source exempts. That is still a harm — a wrongly denied
   benefit — and the plan's harm-weighted framing (C5) counts both directions. But it is a different
   claim from the one previously made, and the paper should make this one.

2. **The baseline, the extractor and the original gold all made the same errors.** The AB-PMJAY
   extraction draft denies the 70+ senior with a refrigerator exactly as the old gold did and as
   Baseline 2 does. All three IGNOAPS sources of judgement — draft, gold, baseline — applied the
   carve-out criteria to everyone. So the failure isn't "LLM versus symbolic". The same misreading of
   compositional scope — which applicants an exclusion applies to — occurred in an LLM answering
   directly, an LLM extracting rules, and a human-verified gold. The symbolic layer evaluated the
   wrong rule faithfully; what caught it was checking the rule against primary text.

3. **Gold-vs-draft agreement cannot detect an error both share.** AB-PMJAY's 100% outcome
   agreement was two systems agreeing on a mistake. For IGNOAPS it was worse than coincidence: its
   `source_clause` records that the three criteria were *added to the gold because an extraction run
   proposed them*, and calls that "the draft-extraction catching a real annotation gap". The
   extractor's mis-scoped reading entered the gold through the draft-then-verify workflow, and the
   gold then "confirmed" the extractor. Plan §6.5's workflow guards against the annotator
   rubber-stamping a draft; it doesn't guard against the annotator being *persuaded* by one. An
   independent source check before accepting a draft-proposed predicate would have.

4. **Where compositional logic actually breaks — a sharper, smaller claim.** Member-level exceptions
   stated beside their exclusion ("…excluding Group D employees") were read correctly everywhere.
   Route-level exemptions stated in a *different section* from the exclusions they override (AB-PMJAY:
   the 70+ expansion is a separate guideline from the SECC list) were missed by every system,
   human included. That is consistent with the plan's thesis that exceptions are where things break,
   but it rests on two schemes, and three of the five false negatives (IGNOAPS) depend on the
   carve-out reading chosen in §6.4. Treat it as a hypothesis with two supporting cases, not a
   finding.

5. **The exception gap in structural F1 matters for the C3 claims.** The metric matches exclusions
   without looking at their `except` clauses, so it scored AB-PMJAY 1.000 before and after a fix
   that changed real verdicts. Any per-category F1 claim about exceptions-to-exclusions currently
   rests on a metric that doesn't measure them. Logged in `KNOWN_ISSUES.md`.

6. **None of this is a large sample.** 75 profiles, 7 schemes; every rate above moves by several
   points with a single row. The direction of these findings is well supported; the magnitudes are
   not.

### 7.6 AB-PMJAY after the 70+ re-encoding (§6.7)

"Old" is the gold immediately before §6.7 (commit `d5ff107`), so this compares the 70+ re-encoding
alone. Reproduced before comparing: outcome equivalence at `d5ff107` gives 80.0%, the corrected
figure §7.2 reports. Offline figures: `scripts/reevaluate_gold_fixes.py --old-ref d5ff107 --only
AB-PMJAY` → `data/extraction_runs/gold_fix_reevaluation_2026-10-04_AB-PMJAY_vs_d5ff107.json`.

**Baseline 2.** Adding the applicant's age changed the facts of 8 existing profiles, so their stored
answers could no longer be reused: those 8 and the new profile were asked live (9 calls, ~24.2k
tokens estimated; `baseline2_direct_llm_2026-10-04_ab-pmjay-70plus-age.json`). The 8 re-asked
profiles got the same verdicts as before.

| AB-PMJAY | n | Agree | Harmful FP | FN |
|---|---|---|---|---|
| Before §6.7 | 10 | 80.0% | 0.0% | 20.0% |
| After §6.7 | 11 | **72.7%** | **9.1%** | 18.2% |

| Baseline 2, all 7 schemes | n | Agree | Harmful FP | FN | Over-cautious |
|---|---|---|---|---|---|
| Before §6.7 | 75 | 90.7% | 0.0% | 6.7% | 1.3% |
| After §6.7 | 76 | **89.5%** | **1.3%** | 6.6% | 1.3% |

The new disagreement is the new profile: the LLM calls the 40-year-old **eligible** — "the family
includes a member aged 74, qualifying under the senior-citizen (70+) expansion". It makes the same
household reading the old gold did.

**Outcome equivalence — extraction draft vs gold.**

| Figure | n | Agree | FP (eligible) | FN (eligible) |
|---|---|---|---|---|
| AB-PMJAY, Phase 3 check-in | 10 → 11 | 80.0% → **72.7%** | 0.0% → **9.1%** | 20.0% → 18.2% |

The draft (`has_family_member_aged_70_or_above` in its inclusion) also calls the 40-year-old eligible.

**Structural F1.** AB-PMJAY 1.000 → **0.947**: the inclusion leaf changed from the household flag to
`age >= 70`, and the draft has the household flag. The 14 exceptions changed too, but the metric
still doesn't score `except` clauses (`KNOWN_ISSUES.md`), so this figure reflects only the inclusion.

**What it adds to §7.5.** The same misreading — the 70+ cover extended to the household — appears in
the direct LLM, the extraction draft and the original gold. That is a third instance of the pattern
in §7.5 point 2: the scope of a rule (who the cover reaches) read too broadly in all three sources,
and caught only by checking the primary text.

### 7.7 PMAY-G after the MoRD re-sourcing (§6.8)

"Old" is the gold immediately before §6.8 (commit `68c186e`; PMAY-G's gold was unchanged since the
audit snapshot). Reproduced before comparing: outcome equivalence 90.0% and structural F1 0.857, both
exactly as recorded at the Phase 3 check-in. Offline figures:
`gold_fix_reevaluation_2026-10-04_PMAY-G_vs_68c186e.json`.

**Read these figures with one caveat.** Both the extraction draft and Baseline 2's LLM were given
`data/raw_documents/PMAY-G.md` — the PIB-based compilation the old gold was built from. It still lists
the refrigerator and landline exclusions and has neither professional tax, unirrigated land, the
"or more" wording nor the room count. So every new disagreement below is the comparison system
faithfully applying an outdated source, not a reasoning error. They measure the source gap, and would
largely disappear if the report's p.141 text were added to that document — a change to what both
systems are shown, so left for a decision.

**Outcome equivalence — extraction draft vs gold.**

| Figure | n | Agree | FP (eligible) | FN (eligible) |
|---|---|---|---|---|
| PMAY-G, Phase 3 check-in | 10 → 14 | 90.0% → **50.0%** | 10.0% → **35.7%** | 0.0% → **14.3%** |

The one pre-existing disagreement (`income_over_ceiling`) is unchanged; the six new ones are the six
profiles whose verdict the fix changed, each matching the old gold.

**Structural F1.** 0.857 → **0.552**: the draft has the two deleted exclusions, the two retired
fields, and none of the four new ones.

**Baseline 2.** Every profile's facts changed, so all 14 were asked live (~25.9k tokens estimated;
`baseline2_direct_llm_2026-10-04_pmay-g-mord.json`). The 10 re-asked profiles gave identical answers.

| PMAY-G | n | Agree | Harmful FP | FN |
|---|---|---|---|---|
| Before §6.8 | 10 | 100.0% | 0.0% | 0.0% |
| After §6.8 | 14 | **57.1%** | **28.6%** | **14.3%** |

| Baseline 2, all 7 schemes | n | Agree | Harmful FP | FN | Over-cautious |
|---|---|---|---|---|---|
| After §6.7 | 76 | 89.5% | 1.3% | 6.6% | 1.3% |
| After §6.8 | 80 | **82.5%** | **6.2%** | **8.8%** | 1.2% |

The harmful false positives are the four new criteria (the LLM's document doesn't have them); the
false negatives are the refrigerator and landline (its document still has them).
