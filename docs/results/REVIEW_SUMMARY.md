# Review summary — SchemeLogic (as of 2026-10-06, 03:00)

*Built only from results already on disk; no new LLM calls. Every number below is against the gold
frozen at tag `gold-v2` and comes from a generated report (linked), so it can be regenerated.
Model: `openai/gpt-oss-120b` on Groq (free tier). **All samples are small**; read directions, not
decimals.*

> **Done overnight:** Hindi translations (293/300; 7 to translate by hand); full pipeline on Baseline 3's
> extraction (4 valid, 2 failed judge calls); temporal case study 6/9; the Marathi arm of the cross-lingual study.
> **Still running (the queue stops 2026-10-07 10:00 so the demo has the full Groq quota):** the last 3
> temporal arms (PMAY-G ×2, AB-PMJAY) → retry of the 2 failed judge calls → Urdu, Marathi, Tamil.
> **Will not run before the review:** Baseline 1, gate re-validation on injected errors (judge part),
> RAG with/without retrieval, PMMVY samples 2–3, the pmksypdmc test. Progress: `python scripts/queue_status.py`.

## 1. The gold audit changed the headline claim — [audit](../GOLD_AUDIT_2026-10-03.md)

92 gold predicates were checked against primary sources: 85 were sourced, 6 implied, and 1 unsourced (since removed). The bigger
problem was **encoding**: two gold errors gave wrong verdicts in the live app (e.g. a 70+ senior
denied AB-PMJAY for owning a refrigerator). The same mis-scoping appeared in the gold, in the extractor and in the
direct-LLM baseline, so **agreement between systems built from the same document measures the document,
not correctness**. Once the gold was corrected, the direct-LLM baseline's errors **switched direction**: from apparent harmful
"eligible" answers to wrongly denied benefits. 20 earlier claims are withdrawn or superseded (listed
in the [batch report](BATCH_REPORT.md)).

## 2. Self-consistency is a better confidence signal than the model's own — [report](SELF_CONSISTENCY.md)

k=3 extractions per scheme, 6 schemes scored (PMMVY has 1 sample so far), **212 predicates**.

| Rule appears in | 1 of 3 samples | 2 of 3 | 3 of 3 |
|---|---|---|---|
| Matches gold | **17%** (n=23) | 73% (n=40) | **97%** (n=149) |

Calibration error (ECE): agreement **0.057** vs self-reported **0.089**. The model reports 0.85–0.97 for
almost everything. Ranking schemes by quality (Spearman vs structural F1, **n=6**): agreement **0.89**,
self-reported 0.58. PMAY-G has the lowest agreement (0.64) and the lowest F1, yet self-reports 0.85–0.95.
*Caveat: the field ontology was built from these 7 schemes, which flatters field-name matching.*

## 3. Direct LLM answering (Baseline 2) on corrected gold — [batch report](BATCH_REPORT.md)

**n = 80 profiles, 7 schemes:** **90.0%** agreement, **1.2%** harmful false "eligible", **6.2%** false
"not eligible". Each wrong denial applied an exclusion to someone the source exempts. *Caveat: the
profiles were written by the gold annotator; one profile moves a scheme's rate by 7–12 points.*

## 4. Extraction alone (Baseline 3) vs the full pipeline on the same extraction — [batch report](BATCH_REPORT.md)

**Baseline 3** (6 schemes, MH-LADKI-BAHIN's sample failed schema validation; **n = 70 profiles**):
structural F1 **0.707**, outcome agreement **68.6%**, false "eligible" 12.9% (mostly PMAY-G, whose sample
missed the housing exclusions), false "not eligible" 7.1%.

**Full pipeline** (judge → gate → apply approved findings) on the same 4 extractions where both ran
(**n = 45**): F1 0.844 → 0.817, agreement 75.6% → **60.0%**, false "eligible" 2.2% → **0.0%**, false
"not eligible" unchanged at 6.7%. The whole drop is *undetermined* verdicts (15.6% → 33.3%): each finding
the gate accepted added a rule on a new field (`is_destitute`, `max_one_beneficiary_per_family`,
`is_pregnant_or_lactating`) that the test profiles don't carry, so the evaluator can't decide them.
The pipeline caused no wrong verdicts, and the extra rules make it ask more questions. **Two of six judge calls failed**
(AB-PMJAY, PMAY-G: `json_validate_failed`). They are reported as failed runs, excluded from the comparison, and queued for
one retry at a higher completion cap.

## 5. Temporal case study (amendments) — [report](TEMPORAL_C4.md)

Pre-amendment text: one extraction each (k=1). Current document: k=3. Each current document states
the old rule and its removal.

| Amendment | From the pre-amendment text | From the current document |
|---|---|---|
| PM-KISAN: 2-hectare limit removed (2019) | limit present, 1/1 | limit absent, 3/3 |
| MH-LADKI-BAHIN: five-acre exclusion deleted, age 60 → 65 (2024) | both old rules, 1/1 | both new, 2/2 (one sample failed) |
| ↳ same, from the three Marathi GRs in date order | — | age 65, 3/3; **five-acre exclusion kept, 3/3** |
| PMMVY 2.0: second child if a girl (2022) | "first child only", 1/1 | **0/1**: no child-order rule at all |
| PMAY-G: refrigerator, landline deleted; ₹10,000 → ₹15,000 (2024) | *still running* | deleted rules absent and ₹15,000, 3/3 |
| AB-PMJAY: 70+ branch added (2024) | *still running* | present, 3/3 |

The extractor reads each version correctly when given that version alone. Given the original GR plus the
amending GR, it applied one amendment (age) and **kept the deleted exclusion**, even though two of
the three samples recorded that condition as superseded. On 10-04, PMAY-G's single run did the same with the
deleted refrigerator and landline exclusions. Retirement is the step that fails.

## 6. Cross-lingual (Marathi GRs vs the English document, MH-LADKI-BAHIN) — [report](CROSS_LINGUAL_C2.md)

Marathi drafts (k=3) agree with gold on **60%** of 10 profiles, English drafts (2 valid) on 70–80%. None
gives a wrong eligible/not-eligible verdict; the rest is undetermined. Marathi vs English drafts agree with
each other on **85%** of verdicts, against 90% between the two English samples and 100% among the Marathi
ones. *Not a clean translation pair*: the English document is a compilation, and the Marathi input needs
the amendment applied (§5).

## What is not claimed

- No result here is on unseen schemes: the AI-Checked tier is the only evidence for those.
- No gate-on-injected-errors judge numbers yet. The agreement signal's recall on injected errors is
  near-guaranteed by construction, so it is not claimed as a result.
- Hindi (used in the demo) is machine-translated and not yet reviewed, and the app says so on every page.
  Urdu, Marathi and Tamil are not translated yet.
