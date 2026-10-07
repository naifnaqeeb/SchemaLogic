# Gate re-validation on injected errors

*Generated 2026-10-07T09:18:32 by `scripts/analyze_gate_revalidation.py` from code `d1a9b07`, against frozen gold `gold-v2`.*

> **Synthetic errors, small sample.** 30 deliberate mutations of correct gold (14 mutated variants, 7 clean controls), one judge sample each. These numbers say what the judge + gate *can* catch, not how often real extractions go wrong. One error moves a type's rate by 17-25 points. Groups A, B and C are never pooled into one catch rate.

## A. Within the judge's design — a missing rule

| Error type | n | Corrected | Flagged (deferred) | Wrong fix | Missed | Judge failed / not run |
|---|---|---|---|---|---|---|
| dropped_predicate | 6 | 0 | 0 | 0 | 0 | 6 |

## B. Within the gate's design — a fabricated supersedes

| Error type | n | Corrected | Flagged (deferred) | Wrong fix | Missed | Judge failed / not run |
|---|---|---|---|---|---|---|
| fabricated_supersedes | 3 | 0 | 0 | 0 | 0 | 3 |

The gate's fabrication check, applied directly to each injected supersedes:

| Error | Invented retired value | Literally in the source? | Gate would |
|---|---|---|---|
| AB-PMJAY#18 | `False` | False | defer |
| IGNOAPS#12 | `True` | False | defer |
| PM-UJJWALA-2.0#06 | `False` | False | defer |

## C. Outside both designs — a present-but-wrong rule

| Error type | n | Corrected | Flagged (deferred) | Wrong fix | Missed | Judge failed / not run |
|---|---|---|---|---|---|---|
| flipped_operator | 6 | 0 | 0 | 0 | 0 | 6 |
| wrong_threshold | 5 | 0 | 0 | 0 | 0 | 5 |
| wrong_quantifier | 5 | 0 | 0 | 0 | 0 | 5 |
| wrong_exception_scope | 5 | 0 | 0 | 0 | 0 | 5 |

## Clean controls (correct gold, nothing injected)

| Scheme | Judge ran | Findings | Deferred (false defer) | Auto-accepted (a change to correct gold) |
|---|---|---|---|---|
| AB-PMJAY | False | 0 | 0 | 0 |
| IGNOAPS | False | 0 | 0 | 0 |
| MH-LADKI-BAHIN | False | 0 | 0 | 0 |
| PM-KISAN | False | 0 | 0 | 0 |
| PM-UJJWALA-2.0 | False | 0 | 0 | 0 |
| PMAY-G | False | 0 | 0 | 0 |
| PMMVY | False | 0 | 0 | 0 |

## The k=3 agreement signal as a deferral signal (no quota)

A rule is scored by the share of the scheme's independent extraction samples that produced it identically; rules produced by few samples are flagged for review. Every injected error that leaves a wrong rule in the candidate is group C; the negatives are the candidates' correct rules. Skipped (fewer than 2 samples): none. ECE of agreement as P(correct), n = 314 rules: **0.3152**.

**Read recall with care: it is close to guaranteed here.** An injected rule is a mutation of gold that no extraction produced, so the samples almost never contain it and it scores low agreement by construction. A real extraction error is one the model itself made, possibly in every sample. Precision is the informative number: most rules this signal flags are correct rules the samples did not reproduce identically.

| Flag a rule produced by | Flagged | True errors flagged | Precision | Recall | Recall by error type |
|---|---|---|---|---|---|
| 0 of 3 samples | 82 | 15 | 0.183 | 0.882 | flipped_operator 6/6, wrong_exception_scope 1/1, wrong_quantifier 3/5, wrong_threshold 5/5 |
| at most 1 of 3 samples | 95 | 17 | 0.179 | 1.0 | flipped_operator 6/6, wrong_exception_scope 1/1, wrong_quantifier 5/5, wrong_threshold 5/5 |
| at most 2 of 3 samples | 170 | 17 | 0.1 | 1.0 | flipped_operator 6/6, wrong_exception_scope 1/1, wrong_quantifier 5/5, wrong_threshold 5/5 |
| any number of samples | 314 | 17 | 0.054 | 1.0 | flipped_operator 6/6, wrong_exception_scope 1/1, wrong_quantifier 5/5, wrong_threshold 5/5 |

The gold rule each error removed or replaced (a dropped rule or exception, or the original of a flipped / re-thresholded / re-quantified rule): did the samples produce it — would agreement point at what the candidate is missing?

| Error type | Removed rules | Produced by >= 2 of 3 samples |
|---|---|---|
| dropped_predicate | 6 | 5 |
| flipped_operator | 6 | 5 |
| wrong_exception_scope | 5 | 2 |
| wrong_quantifier | 5 | 5 |
| wrong_threshold | 5 | 4 |
