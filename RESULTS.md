# Results — SchemeLogic final push

*Built 2026-10-06 21:43 by `scripts/build_results.py` from code `405a497`, against gold frozen at `gold-v2` (`82436ac`). Model `openai/gpt-oss-120b` on Groq's free tier. Regenerate; don't edit.*

**Every sample here is small** (7 gold schemes, 8–14 profiles each, k=3, ~30 injected errors, k=1 per pre-amendment text). Read directions, not decimals. The caveats and the withdrawn claims are in §1. The one-page review summary is [docs/results/REVIEW_SUMMARY.md](docs/results/REVIEW_SUMMARY.md).

## Status

| Experiment | Done | Section |
|---|---|---|
| Batch report: pipeline 2026-08, Baseline 3, Baseline 2 | complete | batch report |
| Full pipeline on Baseline 3's extraction | 6/7 — **partial** | batch report |
| Retry of failed judge calls (max_tokens=2000) | 0/2 retried with reasoning_effort=low; 2 still failed — **not run yet** | batch report |
| Baseline 1 (flat attributes) | 0/7 — **not run yet** | batch report |
| Self-consistency k=3 (PMMVY samples) | 1/3 — **partial** | self-consistency |
| pmksypdmc confidence test | 0/3 — **not run yet** | self-consistency |
| Gate re-validation, judge runs | 0/21 — **not run yet** | gate re-validation |
| Temporal C4 + Marathi arm of C2 | 9/11 — **partial** | temporal / cross-lingual |
| RAG with/without retrieval | 0/4 — **not run yet** | RAG |

## 1. Extraction, pipeline and baselines against gold

*Generated 2026-10-06T21:43:23 by `scripts/run_batch_report.py` from code `405a497`, against frozen gold `gold-v2` (`82436ac`). Offline: no LLM calls. Regenerate rather than edit.*

### Caveats — read first

1. ONTOLOGY CONTAMINATION. The field ontology the extractor is constrained to was built from these same 7 gold schemes (each field lists the schemes it was made for), and the extraction prompt names those fields. Field-name agreement with gold is therefore optimistic: a structural F1 here measures extraction into a vocabulary designed around the answer, not open-world extraction. The AI-Checked tier (schemes outside the gold set) is the only evidence on unseen schemes.
2. SYNTHETIC PROFILES. The profile suites were written by the gold annotator to exercise the rules they encoded, so outcome equivalence tests the scenarios someone already thought of. A rule nobody wrote a profile for cannot disagree.
3. SMALL SAMPLES. 7 schemes, 8-14 profiles each. One profile moves a scheme's rate by 7-12 points; directions are more trustworthy than magnitudes.
4. SHARED SOURCES. Gold, drafts and the direct-LLM baseline mostly read the same source documents. Agreement can mean they share a source's error (the PMAY-G stale-document case, audit doc s7.9).
5. FROZEN GOLD. Everything is scored against tag gold-v2. Open findings of the 2026-10-04 independent gold review are part of that gold, unfixed; a draft that 'disagrees' may be right.

### phase3_pipeline

2026-08 Phase 3 pipeline: extraction -> judge+repair -> gate (latest stage on disk).

| Scheme | Structural F1 | Exceptions F1 | Outcome agreement | FP (eligible) | FN (eligible) | n | Scalar | Draft |
|---|---|---|---|---|---|---|---|---|
| AB-PMJAY | 0.692 | 0.000 | 72.7% | 9.1% | 18.2% | 11 | 2/2 | `AB-PMJAY_gpt-oss-120b_gated_20260818T025520.json` |
| IGNOAPS | 0.267 | — | 33.3% | 0.0% | 25.0% | 12 | 2/2 | `IGNOAPS_gpt-oss-120b_judge_repair_20260818T015010.json` |
| MH-LADKI-BAHIN | 0.800 | 0.000 | 70.0% | 0.0% | 10.0% | 10 | 0/2 | `MH-LADKI-BAHIN_gpt-oss-120b_judge_repair_20260818T015321.json` |
| PM-KISAN | 0.833 | 1.000 | 66.7% | 0.0% | 0.0% | 12 | 2/2 | `PM-KISAN_gpt-oss-120b_judge_repair_20260818T014850.json` |
| PM-UJJWALA-2.0 | 1.000 | — | 100.0% | 0.0% | 0.0% | 9 | 1/2 | `PM-UJJWALA-2.0_gpt-oss-120b_gated_20260818T033601.json` |
| PMAY-G | 0.552 | — | 50.0% | 35.7% | 14.3% | 14 | 1/2 | `PMAY-G_gpt-oss-120b_gated_20260818T031713.json` |
| **All (6)** | **0.716** (micro) | | **63.2%** | 8.8% | 11.8% | 68 | | |

Absent: PMMVY.

### baseline3_extraction_only

Baseline 3: one extraction, no judge or repair (k=3 run, sample 1).

| Scheme | Structural F1 | Exceptions F1 | Outcome agreement | FP (eligible) | FN (eligible) | n | Scalar | Draft |
|---|---|---|---|---|---|---|---|---|
| AB-PMJAY | 0.680 | 0.000 | 81.8% | 0.0% | 18.2% | 11 | 2/2 | `sample_1.json` |
| IGNOAPS | 0.500 | — | 75.0% | 0.0% | 25.0% | 12 | 2/2 | `sample_1.json` |
| PM-KISAN | 0.952 | 1.000 | 91.7% | 8.3% | 0.0% | 12 | 2/2 | `sample_1.json` |
| PM-UJJWALA-2.0 | 0.923 | — | 100.0% | 0.0% | 0.0% | 9 | 2/2 | `sample_1.json` |
| PMAY-G | 0.296 | — | 35.7% | 57.1% | 0.0% | 14 | 1/2 | `sample_1.json` |
| PMMVY | 0.839 | — | 41.7% | 0.0% | 0.0% | 12 | 2/2 | `sample_1.json` |
| **All (6)** | **0.707** (micro) | | **68.6%** | 12.9% | 7.1% | 70 | | |

Absent: MH-LADKI-BAHIN.

### pipeline_on_sample1

Full pipeline (judge -> gate -> apply approved) on the same extraction as Baseline 3.

| Scheme | Structural F1 | Exceptions F1 | Outcome agreement | FP (eligible) | FN (eligible) | n | Scalar | Draft |
|---|---|---|---|---|---|---|---|---|
| IGNOAPS | 0.462 | — | 41.7% | 0.0% | 25.0% | 12 | 2/2 | `IGNOAPS.json` |
| PM-KISAN | 0.909 | 1.000 | 66.7% | 0.0% | 0.0% | 12 | 2/2 | `PM-KISAN.json` |
| PM-UJJWALA-2.0 | 0.923 | — | 100.0% | 0.0% | 0.0% | 9 | 2/2 | `PM-UJJWALA-2.0.json` |
| PMMVY | 0.812 | — | 41.7% | 0.0% | 0.0% | 12 | 2/2 | `PMMVY.json` |
| AB-PMJAY | **failed run** — judge call failed (api_error: json_validate_failed), and again on retry with max_tokens=2000. Cause: the judge's prompt is about 6,295 tokens (conservative estimate) of Groq's 8,000-token per-request limit for prompt plus answer; the answer gets only the remainder (about 2,000 tokens), and the model spends it on reasoning before writing any JSON; excluded | | | | | | | `AB-PMJAY.json` |
| PMAY-G | **failed run** — judge call failed (api_error: json_validate_failed), and again on retry with max_tokens=2000. Cause: the judge's prompt is about 6,276 tokens (conservative estimate) of Groq's 8,000-token per-request limit for prompt plus answer; the answer gets only the remainder (about 2,000 tokens), and the model spends it on reasoning before writing any JSON; excluded | | | | | | | `PMAY-G.json` |
| **All (4)** | **0.817** (micro) | | **60.0%** | 0.0% | 6.7% | 45 | | |

Absent: MH-LADKI-BAHIN.

### baseline1_flat

Baseline 1: flat attribute extraction, no compositional logic.

*No results yet (absent for all 7 schemes).*

### Full pipeline vs Baseline 3, same extraction

Only schemes where both produced a scheme. A failed judge call is a failed run: excluded and listed, not scored as "no change".

Each cell: Baseline 3 → pipeline. "Other" is almost always *undetermined*: a rule on a field the test profiles don't carry. A finding the judge adds usually introduces such a field (`ontology_proposed`), so a drop in agreement there is the profiles not answering, not a wrong verdict; false eligible / false not eligible are the wrong verdicts.

| Scheme | Findings applied | Structural F1 | Outcome agreement | False eligible | False not eligible | Other (undetermined) |
|---|---|---|---|---|---|---|
| IGNOAPS | 1 | 0.500 → 0.462 | 75.0% → 41.7% | 0.0% → 0.0% | 25.0% → 25.0% | 0.0% → 33.3% |
| PM-KISAN | 1 | 0.952 → 0.909 | 91.7% → 66.7% | 8.3% → 0.0% | 0.0% → 0.0% | 0.0% → 33.3% |
| PM-UJJWALA-2.0 | 0 | 0.923 → 0.923 | 100.0% → 100.0% | 0.0% → 0.0% | 0.0% → 0.0% | 0.0% → 0.0% |
| PMMVY | 1 | 0.839 → 0.812 | 41.7% → 41.7% | 0.0% → 0.0% | 0.0% → 0.0% | 58.3% → 58.3% |
| **All (4)** | | **0.844 → 0.817** (micro) | **75.6% → 60.0%** (n=45) | 2.2% → 0.0% | 6.7% → 6.7% | 15.6% → 33.3% |

Excluded: AB-PMJAY — judge call failed (api_error: json_validate_failed), and again on retry with max_tokens=2000. Cause: the judge's prompt is about 6,295 tokens (conservative estimate) of Groq's 8,000-token per-request limit for prompt plus answer; the answer gets only the remainder (about 2,000 tokens), and the model spends it on reasoning before writing any JSON; PMAY-G — judge call failed (api_error: json_validate_failed), and again on retry with max_tokens=2000. Cause: the judge's prompt is about 6,276 tokens (conservative estimate) of Groq's 8,000-token per-request limit for prompt plus answer; the answer gets only the remainder (about 2,000 tokens), and the model spends it on reasoning before writing any JSON; MH-LADKI-BAHIN — no Baseline 3 sample (extraction failed validation).

### Baseline 2 — direct LLM answering, re-scored against frozen gold

| Scheme | n | Agreement | Harmful FP | FN | Stale answers excluded | Answers from |
|---|---|---|---|---|---|---|
| AB-PMJAY | 11 | 72.7% | 9.1% | 18.2% | 0 | `baseline2_direct_llm_2026-10-04_ab-pmjay-70plus-age.json` |
| IGNOAPS | 12 | 66.7% | 0.0% | 25.0% | 0 | `baseline2_direct_llm_2026-10-04.json` |
| MH-LADKI-BAHIN | 10 | 100.0% | 0.0% | 0.0% | 0 | `baseline2_direct_llm_2026-09-19.json` |
| PM-KISAN | 12 | 91.7% | 0.0% | 0.0% | 0 | `baseline2_direct_llm_2026-09-19.json` |
| PM-UJJWALA-2.0 | 9 | 100.0% | 0.0% | 0.0% | 0 | `baseline2_direct_llm_2026-10-04.json` |
| PMAY-G | 14 | 100.0% | 0.0% | 0.0% | 0 | `baseline2_direct_llm_2026-10-04_pmay-g-updated-doc.json` |
| PMMVY | 12 | 100.0% | 0.0% | 0.0% | 0 | `baseline2_direct_llm_2026-10-04.json` |
| **All** | **80** | **90.0%** | **1.2%** | **6.2%** | | |

### Superseded claims (from the audit doc, s7.4) — do not cite the left column

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
| PMAY-G Baseline 2 57.1%, aggregate 82.5% / 6.2% / 8.8% (§7.7) | Stale-document results, kept as a record; with the updated document **100%** and **90.0% / 1.2% / 6.2%** (§7.9). |
| PMAY-G extraction draft 50.0% / F1 0.552 (§7.7) | Stale-document result, kept; with the updated document 50.0% (FP 0.0%) / **0.839** (§7.9). |
| AB-PMJAY Phase 3 check-in, 1.000 (and 0.947 in §7.6) | **0.692** |
| PM-UJJWALA-2.0 Phase 3 check-in, 0.963 | 1.000 (gold fix; the metric change doesn't affect it) |
| PMAY-G Phase 3 check-in, 0.857 (and 0.552 in §7.7) | 0.552 (gold fix; unchanged by the metric) |
| PM-KISAN manual report, "8/9 exact field matches" (F1 0.889) | **0.909**: 8/9 fields plus 2/2 exceptions |
| MH-LADKI-BAHIN ontology draft, 0.818 | **0.786** |
| IGNOAPS 0.714 / 0.667 (never reported; §7.3) | 0.286 / 0.267 (gold fix) |

## 2. Self-consistency confidence

*Generated 2026-10-06T21:43:24 by `scripts/analyze_self_consistency.py` from code `405a497`, against frozen gold `gold-v2`. Small sample: 6 schemes, k samples each; rank correlations over so few schemes are indicative only. Agreement is over a scheme's VALID samples (a sample that failed schema validation produced no predicates and is listed, not counted); a scheme needs at least 2 valid samples to be scored.*

| Scheme | Valid samples | Predicates per sample | Mean agreement | Unanimous | Self-reported (per sample) | Structural F1 (per sample) | Outcome agreement (mean) |
|---|---|---|---|---|---|---|---|
| AB-PMJAY | 3/3 | [17, 13, 20] | 0.88 | 0.72 | [0.95, 0.96, 0.95] | [0.68, 0.565, 0.679] | 0.758 |
| IGNOAPS | 3/3 | [6, 6, 6] | 0.778 | 0.5 | [0.9, 0.6, 0.9] | [0.5, 0.333, 0.5] | 0.722 |
| MH-LADKI-BAHIN | 2/3 | [15, 17] | 0.906 | 0.812 | [0.95, 0.95] | [0.857, 0.867] | 0.75 |
| PM-KISAN | 3/3 | [10, 10, 10] | 1.0 | 1.0 | [0.95, 0.95, 0.95] | [0.952, 0.952, 0.952] | 0.917 |
| PM-UJJWALA-2.0 | 3/3 | [13, 13, 13] | 0.966 | 0.923 | [0.95, 0.95, 0.95] | [0.923, 1.0, 1.0] | 1.0 |
| PMAY-G | 3/3 | [12, 18, 13] | 0.643 | 0.279 | [0.85, 0.85, 0.95] | [0.296, 0.667, 0.929] | 0.548 |
| PMMVY | 1/1 | — | — | — | — | — | — | *(fewer than 2 valid samples so far)*

### Predicate-level calibration (n = 212 predicates)

Correct = an identical predicate exists in the frozen gold.

- Agreement confidence: ECE **0.0566**
- Self-reported confidence: ECE **0.0888**

| Signal | Bin | n | Mean confidence | Accuracy |
|---|---|---|---|---|
| agreement | [0.0, 0.34] | 23 | 0.333 | 0.174 |
| agreement | [0.35, 0.67] | 40 | 0.642 | 0.725 |
| agreement | [0.68, 1.0] | 149 | 1.0 | 0.966 |
| self_reported | [0.0, 0.5] | 0 | None | None |
| self_reported | [0.51, 0.7] | 6 | 0.6 | 0.333 |
| self_reported | [0.71, 0.85] | 30 | 0.85 | 0.5 |
| self_reported | [0.86, 1.0] | 176 | 0.947 | 0.909 |

### Scheme ranking (Spearman, n = 6)

| | vs structural F1 | vs outcome agreement |
|---|---|---|
| Agreement confidence | 0.886 | 0.886 |
| Self-reported confidence | 0.577 | 0.638 |

## 3. Gate re-validation on injected errors

*Generated 2026-10-06T21:43:25 by `scripts/analyze_gate_revalidation.py` from code `405a497`, against frozen gold `gold-v2`.*

> **Synthetic errors, small sample.** 30 deliberate mutations of correct gold (14 mutated variants, 7 clean controls), one judge sample each. These numbers say what the judge + gate *can* catch, not how often real extractions go wrong. One error moves a type's rate by 17-25 points. Groups A, B and C are never pooled into one catch rate.

### A. Within the judge's design — a missing rule

| Error type | n | Corrected | Flagged (deferred) | Wrong fix | Missed | Judge failed / not run |
|---|---|---|---|---|---|---|
| dropped_predicate | 6 | 0 | 0 | 0 | 0 | 6 |

### B. Within the gate's design — a fabricated supersedes

| Error type | n | Corrected | Flagged (deferred) | Wrong fix | Missed | Judge failed / not run |
|---|---|---|---|---|---|---|
| fabricated_supersedes | 3 | 0 | 0 | 0 | 0 | 3 |

The gate's fabrication check, applied directly to each injected supersedes:

| Error | Invented retired value | Literally in the source? | Gate would |
|---|---|---|---|
| AB-PMJAY#18 | `False` | False | defer |
| IGNOAPS#12 | `True` | False | defer |
| PM-UJJWALA-2.0#06 | `False` | False | defer |

### C. Outside both designs — a present-but-wrong rule

| Error type | n | Corrected | Flagged (deferred) | Wrong fix | Missed | Judge failed / not run |
|---|---|---|---|---|---|---|
| flipped_operator | 6 | 0 | 0 | 0 | 0 | 6 |
| wrong_threshold | 5 | 0 | 0 | 0 | 0 | 5 |
| wrong_quantifier | 5 | 0 | 0 | 0 | 0 | 5 |
| wrong_exception_scope | 5 | 0 | 0 | 0 | 0 | 5 |

### Clean controls (correct gold, nothing injected)

| Scheme | Judge ran | Findings | Deferred (false defer) | Auto-accepted (a change to correct gold) |
|---|---|---|---|---|
| AB-PMJAY | False | 0 | 0 | 0 |
| IGNOAPS | False | 0 | 0 | 0 |
| MH-LADKI-BAHIN | False | 0 | 0 | 0 |
| PM-KISAN | False | 0 | 0 | 0 |
| PM-UJJWALA-2.0 | False | 0 | 0 | 0 |
| PMAY-G | False | 0 | 0 | 0 |
| PMMVY | False | 0 | 0 | 0 |

### The k=3 agreement signal as a deferral signal (no quota)

A rule is scored by the share of the scheme's independent extraction samples that produced it identically; rules produced by few samples are flagged for review. Every injected error that leaves a wrong rule in the candidate is group C; the negatives are the candidates' correct rules. Skipped (fewer than 2 samples): PMMVY. ECE of agreement as P(correct), n = 265 rules: **0.2871**.

**Read recall with care: it is close to guaranteed here.** An injected rule is a mutation of gold that no extraction produced, so the samples almost never contain it and it scores low agreement by construction. A real extraction error is one the model itself made, possibly in every sample. Precision is the informative number: most rules this signal flags are correct rules the samples did not reproduce identically.

| Flag a rule produced by | Flagged | True errors flagged | Precision | Recall | Recall by error type |
|---|---|---|---|---|---|
| 0 of 3 samples | 68 | 13 | 0.191 | 0.867 | flipped_operator 4/4, wrong_exception_scope 1/1, wrong_quantifier 3/5, wrong_threshold 5/5 |
| at most 1 of 3 samples | 81 | 15 | 0.185 | 1.0 | flipped_operator 4/4, wrong_exception_scope 1/1, wrong_quantifier 5/5, wrong_threshold 5/5 |
| at most 2 of 3 samples | 123 | 15 | 0.122 | 1.0 | flipped_operator 4/4, wrong_exception_scope 1/1, wrong_quantifier 5/5, wrong_threshold 5/5 |
| any number of samples | 265 | 15 | 0.057 | 1.0 | flipped_operator 4/4, wrong_exception_scope 1/1, wrong_quantifier 5/5, wrong_threshold 5/5 |

The gold rule each error removed or replaced (a dropped rule or exception, or the original of a flipped / re-thresholded / re-quantified rule): did the samples produce it — would agreement point at what the candidate is missing?

| Error type | Removed rules | Produced by >= 2 of 3 samples |
|---|---|---|
| dropped_predicate | 4 | 3 |
| flipped_operator | 4 | 3 |
| wrong_exception_scope | 5 | 2 |
| wrong_quantifier | 5 | 5 |
| wrong_threshold | 5 | 4 |

## 4. Temporal case study (C4)

*Generated 2026-10-06 by `scripts/run_temporal_case_study.py --score` from `data/experiments/temporal_c4/` and `data/experiments/self_consistency/`. Gold tag gold-v2; extractor defaults; Groq `openai/gpt-oss-120b`.*

**Small sample.** One extraction per pre-amendment text (k=1) and three per current document (k=3); the Marathi arm and PMAY-G's pre-amendment arm are k=3 (the latter after its first sample missed the whole exclusion list). A single pre-amendment sample shows what the extractor *can* read from that text, not a rate. A valid sample that misses the rule entirely counts against "as expected".

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
| AB-PMJAY | 70+ branch (added 2024; nothing retired) | pre-amendment text | absent | 1/1 | absent |
| AB-PMJAY | 70+ branch (added 2024; nothing retired) | current document (k=3) | present | 3/3 | present; present; present |
| PMAY-G | refrigerator exclusion (deleted 2024) | pre-amendment text | present | 0/1 | absent |
| PMAY-G | refrigerator exclusion (deleted 2024) | stale document | present | 1/1 | present |
| PMAY-G | refrigerator exclusion (deleted 2024) | current document (k=3) | absent | 3/3 | absent; absent; absent |
| PMAY-G | landline exclusion (deleted 2024) | pre-amendment text | present | 0/1 | absent |
| PMAY-G | landline exclusion (deleted 2024) | stale document | present | 1/1 | present |
| PMAY-G | landline exclusion (deleted 2024) | current document (k=3) | absent | 3/3 | absent; absent; absent |
| PMAY-G | monthly income threshold (10000 -> 15000) | pre-amendment text | 10000 | 0/1 | none |
| PMAY-G | monthly income threshold (10000 -> 15000) | stale document | 15000 | 1/1 | 15000 |
| PMAY-G | monthly income threshold (10000 -> 15000) | current document (k=3) | 15000 | 3/3 | 15000; 15000; 15000 |

### Dropped

None: official pre-amendment text was found for every listed scheme (sources in each arm's result file).

### Per sample (matched predicates)

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
- **AB-PMJAY__pre_2024_identification** sample_1: ok
  - 70+ branch (added 2024; nothing retired): **absent** — no matching predicate
- **AB-PMJAY__post_current_document (k=3 self-consistency)** sample_1: ok
  - 70+ branch (added 2024; nothing retired): **present** — inclusion: age >= 70
- **AB-PMJAY__post_current_document (k=3 self-consistency)** sample_2: ok
  - 70+ branch (added 2024; nothing retired): **present** — inclusion: age >= 70
- **AB-PMJAY__post_current_document (k=3 self-consistency)** sample_3: ok
  - 70+ branch (added 2024; nothing retired): **present** — inclusion: age >= 70
- **PMAY-G__pre_framework_2022** sample_1: ok
  - refrigerator exclusion (deleted 2024): **absent** — no matching predicate
  - landline exclusion (deleted 2024): **absent** — no matching predicate
  - monthly income threshold (10000 -> 15000): **none** — no matching predicate
- **PMAY-G__stale_PIB_2024** sample_1: ok
  - refrigerator exclusion (deleted 2024): **present** — exclusion: owns_refrigerator == True
  - landline exclusion (deleted 2024): **present** — exclusion: owns_landline_phone == True
  - monthly income threshold (10000 -> 15000): **15000** — exclusion: monthly_income_inr > 15000
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

## 5. Cross-lingual case study (C2)

*Generated 2026-10-06 by `scripts/analyze_cross_lingual.py` (offline). Gold tag gold-v2; 10 frozen test profiles; Groq `openai/gpt-oss-120b` extractions.*

**Small sample** (k=3 per language, one scheme). **Not a clean translation pair**: the English input is a compilation of the GRs and official secondary sources, not a translation; the Marathi input is the original GR plus two amending GRs, so the extractor must also apply the amendment (see the temporal case study).

### Each draft against gold

| Draft | Language | Structural F1 | Outcome agreement | False eligible | False not eligible | Other |
|---|---|---|---|---|---|---|
| mr:sample_1 | mr | 0.600 | 60.0% | 0.0% | 0.0% | 40.0% |
| mr:sample_2 | mr | 0.690 | 60.0% | 0.0% | 0.0% | 40.0% |
| mr:sample_3 | mr | 0.733 | 60.0% | 0.0% | 0.0% | 40.0% |
| en:sample_1 | en | extraction failed | | | | |
| en:sample_2 | en | 0.857 | 80.0% | 0.0% | 0.0% | 20.0% |
| en:sample_3 | en | 0.867 | 70.0% | 0.0% | 0.0% | 30.0% |

### Drafts against each other (same profiles)

| Pair kind | Pairs | Mean verdict agreement |
|---|---|---|
| en-en | 1 | 90.0% |
| mr-mr | 3 | 100.0% |
| mr-en | 6 | 85.0% |

en-en and mr-mr are the noise baseline: two samples of the same text.

#### Pairs

- en:sample_2 vs en:sample_3: 90.0% — differ on govt_employee_family_member
- en:sample_2 vs mr:sample_1: 80.0% — differ on govt_employee_family_member, other_govt_scheme_benefit_at_threshold
- en:sample_2 vs mr:sample_2: 80.0% — differ on govt_employee_family_member, other_govt_scheme_benefit_at_threshold
- en:sample_2 vs mr:sample_3: 80.0% — differ on govt_employee_family_member, other_govt_scheme_benefit_at_threshold
- en:sample_3 vs mr:sample_1: 90.0% — differ on other_govt_scheme_benefit_at_threshold
- en:sample_3 vs mr:sample_2: 90.0% — differ on other_govt_scheme_benefit_at_threshold
- en:sample_3 vs mr:sample_3: 90.0% — differ on other_govt_scheme_benefit_at_threshold
- mr:sample_1 vs mr:sample_2: 100.0%
- mr:sample_1 vs mr:sample_3: 100.0%
- mr:sample_2 vs mr:sample_3: 100.0%

### Not run

- PM-KISAN (Hindi/English): pmkisan.gov.in has a 2019 scheme summary in English and in Hindi (kept locally as PM-KISAN_summary_english_2019.pdf / PM-KISAN_summary_hindi_2019.pdf). The Hindi PDF uses a legacy non-Unicode font: its extracted text is corrupted (e.g. निधि comes out as ननधध), so an extraction from it would test the PDF's font encoding, not the language. Not run; would need OCR.
- No other gold scheme's sources include an official parallel text in two languages.

## 6. RAG: the judge with and without retrieval

*Not run yet* (queued after the gate re-validation).

## 7. Translations

| Language | State | Translated | Reviewed by a person | Catalogue |
|---|---|---|---|---|
| Hindi | machine | 293 | 0 | 300 |
| Urdu | machine | 295 | 0 | 300 |
| Marathi | machine | 159 | 0 | 300 |
| Tamil | none | 0 | 0 | 300 |

"machine": machine-translated and not yet reviewed; the app says so on every page. Review sheets: `docs/i18n/REVIEW_<lang>.csv`.
