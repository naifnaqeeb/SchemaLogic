# Review summary — SchemeLogic (as of 2026-10-07, 09:30)

*Built only from results already on disk; no new LLM calls. Every number below is against the gold
frozen at tag `gold-v2` and comes from a generated report (linked), so it can be regenerated.
Model: `openai/gpt-oss-120b` on Groq (free tier). **All samples are small**; read directions, not
decimals.*

> **Final state for the review.** The background queue stops at 2026-10-07 10:00, so the demo has the
> full Groq quota, and nothing more runs before the review. **Done:** k=3 self-consistency on all 7 schemes; the full
> pipeline on Baseline 3's extraction (5 of 7 compared; see §4); the temporal case study, all arms; the
> cross-lingual Marathi arm; translations in Hindi, Urdu, Marathi and Tamil (machine, unreviewed).
> **Not run:** Baseline 1, gate re-validation (judge part), RAG with/without retrieval, and the third sample
> of the pmksypdmc test.

## 1. The gold audit changed the headline claim — [audit](../GOLD_AUDIT_2026-10-03.md)

92 gold predicates were checked against primary sources: 85 sourced, 6 implied, 1 unsourced (since
removed). The bigger problem was **encoding**: two gold errors gave wrong verdicts in the live app (e.g.
a 70+ senior denied AB-PMJAY for owning a refrigerator). The same mis-scoping appeared in the gold, the
extractor and the direct-LLM baseline, so **agreement between systems built from the same document
measures the document, not correctness**. Once the gold was corrected, the direct-LLM baseline's errors
**switched direction**, from apparent harmful "eligible" answers to wrongly denied benefits. 20 earlier
claims are withdrawn or superseded (listed in the [batch report](BATCH_REPORT.md)).

## 2. Self-consistency is a better confidence signal than the model's own — [report](SELF_CONSISTENCY.md)

k=3 extractions per scheme, 7 schemes, **244 predicates**.

| Rule appears in | 1 of 3 samples | 2 of 3 | 3 of 3 |
|---|---|---|---|
| Matches gold | **15%** (n=26) | 80% (n=66) | **97%** (n=152) |

- **Calibration error (ECE):** agreement **0.081** vs self-reported 0.092. The model reports 0.85–0.97 for
  almost everything.
- **Ranking schemes by quality** (Spearman vs structural F1, **n=7**): agreement **0.82**, self-reported
  **0.19**.
- **One PMMVY sample collapsed** to 5 predicates (F1 0.18) at a self-reported 0.95.
- **Limit:** agreement measures consistency, not completeness. pmksypdmc's known collapse (a long scheme
  reduced to "is an Indian citizen") repeated in both samples run, at 0.95 self-reported, and its one rule
  scores full agreement.

*Caveat: the field ontology was built from these 7 schemes, which flatters field-name matching.*

## 3. Direct LLM answering (Baseline 2) on corrected gold — [batch report](BATCH_REPORT.md)

**n = 80 profiles, 7 schemes:** **90.0%** agreement, **1.2%** harmful false "eligible", **6.2%** false
"not eligible". Each wrong denial applied an exclusion to someone the source exempts. *Caveat: the
profiles were written by the gold annotator; one profile moves a scheme's rate by 7–12 points.*

## 4. Extraction alone (Baseline 3) vs the full pipeline on the same extraction — [batch report](BATCH_REPORT.md)

**Baseline 3** (6 schemes; MH-LADKI-BAHIN's sample failed schema validation; **n = 70 profiles**):
structural F1 **0.707**, outcome agreement **68.6%**, false "eligible" 12.9%, false "not eligible" 7.1%.

**Full pipeline** (judge → gate → apply approved findings), on the same extractions where both ran (5
schemes, **n = 59**):

| | Baseline 3 | Full pipeline |
|---|---|---|
| Structural F1 | 0.718 | 0.694 |
| Outcome agreement | 66.1% | **49.2%** |
| False "eligible" | 15.3% | **0.0%** |
| False "not eligible" | 5.1% | 5.1% |
| Undetermined | 13.6% | 45.8% |

- **The whole drop is undetermined verdicts.** Each finding the gate accepted added a rule on a new field
  (e.g. `is_destitute`) that the test profiles don't carry. The pipeline introduced no wrong verdicts and
  removed every false "eligible", at the cost of more questions.
- **PMAY-G** is in the comparison only through a retry with `reasoning_effort=low`, so it is marked as a
  different setting.
- **AB-PMJAY failed on all three attempts** and is excluded:
  - The first two (default, and `max_tokens=2000`) returned no output. The judge's prompt is about 6.3k
    tokens (estimate) of Groq's 8k per-request limit, and the model spent the rest on reasoning.
  - The third (`reasoning_effort=low`) produced an answer that broke the judge's format: a supersession
    with no field named. It is logged in KNOWN_ISSUES as a fix for after the review.

## 5. Temporal case study (amendments) — [report](TEMPORAL_C4.md)

Pre-amendment text: k=1, except PMAY-G (k=3). Current document: k=3. Each current document states the
old rule and its removal.

| Amendment | From the pre-amendment text | From the current document |
|---|---|---|
| PM-KISAN: 2-hectare limit removed (2019) | limit present, 1/1 | limit absent, 3/3 |
| MH-LADKI-BAHIN: five-acre exclusion deleted, age 60 → 65 (2024) | both old rules, 1/1 | both new, 2/2 (one sample failed) |
| ↳ same, from the three Marathi GRs in date order | — | age 65, 3/3; **five-acre exclusion kept, 3/3** |
| PMMVY 2.0: second child if a girl (2022) | "first child only", 1/1 | **no child-order rule at all, 3/3** |
| PMAY-G: refrigerator, landline deleted; ₹10,000 → ₹15,000 (2024) | old rules, **2/3**; the first sample missed the whole 13-item exclusion list | deleted rules absent and ₹15,000, 3/3 |
| ↳ same, from the stale 2024 document (lists the deleted items, no deletion notice) | — | refrigerator and landline kept, ₹15,000, 1/1: read as written |
| AB-PMJAY: 70+ branch added (2024) | absent, 1/1 | present, 3/3 |

- **One version alone is read correctly**, in all five pre-amendment texts; PMAY-G's first sample is the
  exception.
- **Retirement is the step that fails.** Given the original GR plus the amending GR, the extractor applied
  one amendment (age) and **kept the deleted exclusion**, even though two of the three samples recorded it as
  superseded. Given PMMVY's document, which states the old and new child rules, it **dropped the rule
  altogether** in every sample.

## 6. Cross-lingual (Marathi GRs vs the English document, MH-LADKI-BAHIN) — [report](CROSS_LINGUAL_C2.md)

- **Against gold:** Marathi drafts (k=3) agree with gold on **60%** of 10 profiles; English drafts (2 valid)
  on 70–80%. Neither gives a wrong eligible/not-eligible verdict; the rest is undetermined.
- **Against each other:** Marathi and English drafts agree on **85%** of verdicts, against 90% between the
  two English samples and 100% among the Marathi ones.

*Not a clean translation pair*: the English document is a compilation, and the Marathi input needs the
amendment applied (§5).

## What is not claimed

- **Unseen schemes:** no result here is on unseen schemes; the AI-Checked tier is the only evidence for
  those.
- **Gate on injected errors:** no judge numbers. The agreement signal's recall on injected errors is
  near-guaranteed by construction, so it is not claimed.
- **Translations:**
  - All four languages are machine-translated and not yet reviewed; the app says so on every page.
  - The demo uses English and Hindi.
  - Entries the checks rejected are left for people to translate: Hindi 7, Urdu 5, Marathi 2, Tamil 5.
