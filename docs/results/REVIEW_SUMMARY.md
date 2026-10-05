# Review summary — SchemeLogic (as of 2026-10-05)

*Built only from results already on disk; no new LLM calls. Every number below is against the gold
frozen at tag `gold-v2` and comes from a generated report (linked), so it can be regenerated.
Model: `openai/gpt-oss-120b` on Groq (free tier). **All samples are small**; read directions, not
decimals.*

> **Still running (background queue, stops 2026-10-07 10:00 so the demo has the full Groq quota):**
> catalogue translations (Hindi first, then Urdu, Marathi, Tamil) → full pipeline (judge → gate) on
> Baseline 3's extraction → temporal case study, pre-amendment arms (+ Marathi arm of the cross-lingual
> study). **Will not run before the review** at the current quota: Baseline 1, gate re-validation on
> injected errors (judge part), RAG with/without retrieval, PMMVY samples 2–3, the pmksypdmc test.
> Tables for these show "no results yet". Check progress: `python scripts/queue_status.py`.

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

## 4. One extraction, no judge or repair (Baseline 3) — [batch report](BATCH_REPORT.md)

6 schemes (MH-LADKI-BAHIN's sample failed schema validation), **n = 70 profiles**: structural F1
**0.707** (micro), outcome agreement **68.6%**, false "eligible" 12.9%, false "not eligible" 7.1%. Most of
the false "eligible" answers come from PMAY-G: that sample missed the housing exclusions (57.1% false
"eligible" on its 14 profiles). This is the comparison point for the full pipeline on the *same*
extraction, which is still running.

## 5. Early temporal signal (amendments) — [interim report](TEMPORAL_C4.md)

Only the current-document side so far: the k=3 samples, which cost no new quota. Each current document
states both the old rule and its removal.

| Amendment | Old rule correctly absent / new rule present |
|---|---|
| PM-KISAN: 2-hectare limit removed (2019) | 3/3 |
| PMAY-G: refrigerator, landline exclusions deleted (2024) | 3/3 each, and ₹15,000 not ₹10,000, 3/3. A single earlier run *kept* both deleted rules. |
| MH-LADKI-BAHIN: five-acre exclusion removed, age 60 → 65 (2024) | 2/2 (third sample failed validation) |
| AB-PMJAY: 70+ branch added (2024) | 3/3 |
| PMMVY 2.0: second child if a girl (2022) | **0/1**. The one sample has no child-order rule at all. |

The pre-amendment arms are queued. Official pre-amendment texts were found for all five schemes,
including PM-KISAN's guidelines as first issued (pmkisan.gov.in). Without them, "absent after" cannot
be told apart from "never extracted".

## What is not claimed

- No result here is on unseen schemes: the AI-Checked tier is the only evidence for those.
- No cross-lingual (Marathi vs English) or gate-on-injected-errors numbers yet.
- The UI's Urdu, Marathi and Tamil strings are machine translations that no one has reviewed yet.
