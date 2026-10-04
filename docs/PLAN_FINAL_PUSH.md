# Final push — plan and running log

*3-day push started 2026-10-04. This file is updated as items complete, so the plan survives across
sessions. Newest status at the top of each section.*

## Ground rules

- **Gold is frozen at tag `gold-v2`** (commit `82436ac`). Every experiment in this push runs against it.
  A gold error an experiment exposes is logged under [Gold errors found](#gold-errors-found-not-fixed-during-the-push),
  not fixed mid-push.
- **Nothing existing may break**: all current tests pass unmodified; English behaviour stays
  identical; only the evaluator decides a verdict, everywhere.
- **Keys**: `OPENROUTER_API_KEY` and `GROQ_API_KEY` live in `.env` (gitignored). Never printed,
  logged or committed.
- **Providers (decided 2026-10-05, D1)**: every experiment runs on **Groq's free tier only**, model
  `openai/gpt-oss-120b`. No credit is added to OpenRouter; it stays only as the chat's existing
  fallback and is never used for experiments. The extractor, judge and baseline runners still gain a
  `provider` option through the provider abstraction (Groq default, behaviour unchanged). Every
  result file records provider and model.
- **Quota**: quota-heavy runs are spread over **4 days at ~180k tokens/day**, a margin under Groq's
  ~200k daily cap, as paced background jobs (8k tokens/min) while quota-free coding continues. Stop
  cleanly on a rate limit or the day's budget; never push through. Token use is measured from each
  response's `usage`, not estimated, and logged to `data/experiments/token_ledger.jsonl`.
- **Reproducibility**: all runners and scripts live in the repo. Every result file records the gold
  tag, provider, model, config and date.
- **Reporting**: at the end of each day — done, not done, tokens and cost spent, decisions needed.

## Provider status

*Checked 2026-10-04, read-only (no completions):*

| | Groq | OpenRouter |
|---|---|---|
| Model | `openai/gpt-oss-120b` | `openai/gpt-oss-120b` listed, ~20 hosting providers (fp4 / fp8 / bf16; Groq is one of them) |
| Limits | 8,000 tokens/min; ~200k tokens/day (inferred, not in headers); 1,000 requests/day | key on the free tier; per-request rate limit not reported |
| Pricing | free tier | $0.03–0.15 per M prompt tokens, $0.17–0.95 per M completion tokens, by host |
| Credit | n/a | **0** (total credits 0, usage 0) |
| Can serve the model now? | yes | **no** — paid endpoints need credit; the `:free` variant has 0 endpoints |

**Decided (D1, 2026-10-05)**: Groq free tier only. OpenRouter is not used for experiments.

## Budget (running)

| Date | Item | Provider | Calls | Tokens (est.) | Cost |
|---|---|---|---|---|---|
| — | — | — | — | — | — |
| **Total** | | | **0** | **0** | **$0.00** |

## Quota schedule (Groq, ~180k tokens/day)

Estimates, to be replaced by measured usage as runs complete:

| Day | Quota-heavy runs | Est. tokens |
|---|---|---|
| 1 (2026-10-05) | k=3 extraction samples, 7 schemes (21 extractions; sample 1 doubles as Baseline 3) — as far as the day's budget goes | ~180k |
| 2 | finish k=3; Baseline 1 (7 calls) | ~60k + ~35k |
| 3 | gate re-validation (~30 injected errors); RAG with/without retrieval | ~140k + ~40k |
| 4 | temporal C4 (pre/post extractions); cross-lingual C2; multilingual translations and one live chat per language | ~90k + ~40k + ~50k |

## Plan and status

Legend: ☐ not started · ◐ in progress · ☑ done · ⊘ dropped (with reason)

### Day 1
- ☐ 0. Provider extension: extractor, judge and baseline runners use the provider abstraction (Groq
  default; OpenRouter fallback or explicit `--provider`); default unchanged; tests unmodified.
- ☐ 1. Batch runner + one aggregate report across all 7 gold schemes (structural F1, outcome
  equivalence, scalar checks, Baseline 2), with the ontology-contamination caveat and the
  superseded-claims list built in.
- ☐ 2. **k=3** self-consistency confidence on all 7 schemes (reduced from k=5, D1); compare with
  self-reported confidence, including the pmksypdmc-style inversion.
- ☐ 3. Baseline 1 (flat attribute extraction) and Baseline 3 (extraction without judge/repair): code
  both, run Baseline 3.
- ☐ 4. Multilingual stage 1 (understanding).

### Day 2
- ☐ 5. Run Baseline 1.
- ☐ 6. Gate re-validation on a synthetic injected-error corpus of **~30** labelled mutations of frozen
  gold (reduced from ≥100, D1 — reported explicitly as a small-sample result): false-accept /
  false-defer, precision-recall curve, ECE with the k=3 confidence.
- ☐ 7. Fix the RAG api_error; with/without-retrieval comparison.
- ☐ 8. Multilingual stage 2 (replies).

### Day 3
- ☐ 9. Temporal case study (C4).
- ☐ 10. Cross-lingual case study (C2).
- ☐ 11. Multilingual stage 3 (interface).
- ☐ 12. README.md, RESULTS.md, full suite, push.

## Decisions needed

- ~~**D1 (2026-10-04)** — OpenRouter has 0 credit.~~ **Decided 2026-10-05**: no credit; Groq free tier
  only; k=3 instead of k=5; ~30 injected errors instead of ≥100; quota-heavy runs over 4 days at
  ~180k tokens/day; OpenRouter only as the chat's existing fallback.

## Gold errors found (not fixed during the push)

*None yet. Open findings from the 2026-10-04 independent gold review are in that report and
`KNOWN_ISSUES.md`; they are part of gold-v2 as frozen.*

## Daily reports

*(appended at the end of each day)*
