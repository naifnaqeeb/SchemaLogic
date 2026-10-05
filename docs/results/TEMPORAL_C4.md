# Temporal case study (C4)

*Generated 2026-10-06 by `scripts/run_temporal_case_study.py --score` from `data/experiments/temporal_c4/` and `data/experiments/self_consistency/`. Gold tag gold-v2; extractor defaults; Groq `openai/gpt-oss-120b`.*

**Small sample.** One extraction per pre-amendment text (k=1) and three per current document (k=3); the Marathi arm is k=3. A single pre-amendment sample shows what the extractor *can* read from that text, not a rate.

| Scheme | Check | Source | Expected | As expected | Values seen |
|---|---|---|---|---|---|
| PM-KISAN | 2-hectare landholding limit (removed 1 June 2019) | pre-amendment text | present | 1/1 | present |
| PM-KISAN | 2-hectare landholding limit (removed 1 June 2019) | current document (k=3) | absent | 3/3 | absent; absent; absent |
| PMMVY | child-order rule | pre-amendment text | first child only | 1/1 | first child only |
| PMMVY | child-order rule | current document (k=3) | first child, or second if a girl | 0/1 | no child-order rule |
| MH-LADKI-BAHIN | five-acre land exclusion (retired 03.07.2024) | pre-amendment text | present | 1/1 | present |
| MH-LADKI-BAHIN | five-acre land exclusion (retired 03.07.2024) | current document (k=3) | absent | 2/2 (+1 failed) | absent; absent |
| MH-LADKI-BAHIN | five-acre land exclusion (retired 03.07.2024) | Marathi GRs in order | absent | 0/3 | present; present; present |
| MH-LADKI-BAHIN | upper age bound (60 -> 65 on 03.07.2024) | pre-amendment text | <= 60 | 1/1 | <= 60 |
| MH-LADKI-BAHIN | upper age bound (60 -> 65 on 03.07.2024) | current document (k=3) | <= 65 | 2/2 (+1 failed) | <= 65; <= 65 |
| MH-LADKI-BAHIN | upper age bound (60 -> 65 on 03.07.2024) | Marathi GRs in order | <= 65 | 3/3 | <= 65; <= 65; <= 65 |
| AB-PMJAY | 70+ branch (added 2024; nothing retired) | pre-amendment text | absent | *not run yet* | — |
| AB-PMJAY | 70+ branch (added 2024; nothing retired) | current document (k=3) | present | 3/3 | present; present; present |
| PMAY-G | refrigerator exclusion (deleted 2024) | pre-amendment text | present | *not run yet* | — |
| PMAY-G | refrigerator exclusion (deleted 2024) | stale document | present | *not run yet* | — |
| PMAY-G | refrigerator exclusion (deleted 2024) | current document (k=3) | absent | 3/3 | absent; absent; absent |
| PMAY-G | landline exclusion (deleted 2024) | pre-amendment text | present | *not run yet* | — |
| PMAY-G | landline exclusion (deleted 2024) | stale document | present | *not run yet* | — |
| PMAY-G | landline exclusion (deleted 2024) | current document (k=3) | absent | 3/3 | absent; absent; absent |
| PMAY-G | monthly income threshold (10000 -> 15000) | pre-amendment text | 10000 | *not run yet* | — |
| PMAY-G | monthly income threshold (10000 -> 15000) | stale document | 15000 | *not run yet* | — |
| PMAY-G | monthly income threshold (10000 -> 15000) | current document (k=3) | 15000 | 3/3 | 15000; 15000; 15000 |

## Dropped

None: official pre-amendment text was found for every listed scheme (sources in each arm's result file).

## Per sample (matched predicates)

- **PM-KISAN__pre_2019_guidelines** sample_1: ok
  - 2-hectare landholding limit (removed 1 June 2019): **present** — inclusion: cultivable_land_hectares <= 2
- **PM-KISAN__post_current_document (k=3 self-consistency)** sample_1: ok
  - 2-hectare landholding limit (removed 1 June 2019): **absent** — no matching predicate
- **PM-KISAN__post_current_document (k=3 self-consistency)** sample_2: ok
  - 2-hectare landholding limit (removed 1 June 2019): **absent** — no matching predicate
- **PM-KISAN__post_current_document (k=3 self-consistency)** sample_3: ok
  - 2-hectare landholding limit (removed 1 June 2019): **absent** — no matching predicate
- **PMMVY__pre_2017_guidelines** sample_1: ok
  - child-order rule: **first child only** — inclusion: pregnancy_child_order == 1
- **PMMVY__post_current_document (k=3 self-consistency)** sample_1: ok
  - child-order rule: **no child-order rule** — no matching predicate
- **MH-LADKI-BAHIN__pre_GR_20240628** sample_1: ok
  - five-acre land exclusion (retired 03.07.2024): **present** — exclusion: family_agricultural_land_acres > 5
  - upper age bound (60 -> 65 on 03.07.2024): **<= 60** — inclusion: age <= 60
- **MH-LADKI-BAHIN__marathi_GRs_in_order** sample_1: ok; supersedes recorded: `{"age_upper_limit": 60, "farm_land_condition": ">5 acres"}`
  - five-acre land exclusion (retired 03.07.2024): **present** — exclusion: family_agricultural_land_acres > 5
  - upper age bound (60 -> 65 on 03.07.2024): **<= 65** — inclusion: age <= 65
- **MH-LADKI-BAHIN__marathi_GRs_in_order** sample_2: ok; supersedes recorded: `{"age_upper_limit": "60 years", "disqualification_condition_7": "family land >5 acres"}`
  - five-acre land exclusion (retired 03.07.2024): **present** — exclusion: family_agricultural_land_acres > 5
  - upper age bound (60 -> 65 on 03.07.2024): **<= 65** — inclusion: age <= 65
- **MH-LADKI-BAHIN__marathi_GRs_in_order** sample_3: ok
  - five-acre land exclusion (retired 03.07.2024): **present** — exclusion: family_agricultural_land_acres > 5
  - upper age bound (60 -> 65 on 03.07.2024): **<= 65** — inclusion: age <= 65
- **MH-LADKI-BAHIN__post_current_document (k=3 self-consistency)** sample_1: extraction failed: schema_validation_failed
- **MH-LADKI-BAHIN__post_current_document (k=3 self-consistency)** sample_2: ok; supersedes recorded: `{"disqualification_condition": "families whose members jointly hold more than five acres of agricultural land"}`
  - five-acre land exclusion (retired 03.07.2024): **absent** — no matching predicate
  - upper age bound (60 -> 65 on 03.07.2024): **<= 65** — inclusion: age <= 65
- **MH-LADKI-BAHIN__post_current_document (k=3 self-consistency)** sample_3: ok
  - five-acre land exclusion (retired 03.07.2024): **absent** — no matching predicate
  - upper age bound (60 -> 65 on 03.07.2024): **<= 65** — inclusion: age <= 65
- **AB-PMJAY__post_current_document (k=3 self-consistency)** sample_1: ok
  - 70+ branch (added 2024; nothing retired): **present** — inclusion: age >= 70
- **AB-PMJAY__post_current_document (k=3 self-consistency)** sample_2: ok
  - 70+ branch (added 2024; nothing retired): **present** — inclusion: age >= 70
- **AB-PMJAY__post_current_document (k=3 self-consistency)** sample_3: ok
  - 70+ branch (added 2024; nothing retired): **present** — inclusion: age >= 70
- **PMAY-G__post_current_document (k=3 self-consistency)** sample_1: ok
  - refrigerator exclusion (deleted 2024): **absent** — no matching predicate
  - landline exclusion (deleted 2024): **absent** — no matching predicate
  - monthly income threshold (10000 -> 15000): **15000** — exclusion: monthly_income_inr > 15000
- **PMAY-G__post_current_document (k=3 self-consistency)** sample_2: ok; supersedes recorded: `{"removed_exclusions": ["ownership of fishing boat", "ownership of motorised two-wheeler", "landline phone ownership", "refrigerator ownership", "mechanised two-wheeler agricultural equipment"], "reduced_exclusion_parameters": 13, "new_exclusion_parameters": 10}`
  - refrigerator exclusion (deleted 2024): **absent** — no matching predicate
  - landline exclusion (deleted 2024): **absent** — no matching predicate
  - monthly income threshold (10000 -> 15000): **15000** — exclusion: monthly_income_inr > 15000
- **PMAY-G__post_current_document (k=3 self-consistency)** sample_3: ok; supersedes recorded: `{"fishing_boat_exclusion": true, "motorised_two_wheeler_exclusion": true, "income_threshold": "Rs 10,000 per month"}`
  - refrigerator exclusion (deleted 2024): **absent** — no matching predicate
  - landline exclusion (deleted 2024): **absent** — no matching predicate
  - monthly income threshold (10000 -> 15000): **15000** — exclusion: monthly_income_inr > 15000
