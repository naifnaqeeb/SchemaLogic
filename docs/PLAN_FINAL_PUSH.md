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
- **Providers**: Groq is the default. OpenRouter is a fallback or an explicit choice for batch runs,
  through the existing provider abstraction. The same model, `openai/gpt-oss-120b`, on both — never a
  substitute. Every result file records provider and model.
- **Quota**: quota-heavy experiments run as paced background jobs while quota-free coding continues;
  stop cleanly on rate limits or low credit, never push through.
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

**Blocked pending decision (D1)**: OpenRouter cannot serve `openai/gpt-oss-120b` until credit is added.

## Budget (running)

| Date | Item | Provider | Calls | Tokens (est.) | Cost |
|---|---|---|---|---|---|
| — | — | — | — | — | — |
| **Total** | | | **0** | **0** | **$0.00** |

## Plan and status

Legend: ☐ not started · ◐ in progress · ☑ done · ⊘ dropped (with reason)

### Day 1
- ☐ 0. Provider extension: extractor, judge and baseline runners use the provider abstraction (Groq
  default; OpenRouter fallback or explicit `--provider`); default unchanged; tests unmodified.
- ☐ 1. Batch runner + one aggregate report across all 7 gold schemes (structural F1, outcome
  equivalence, scalar checks, Baseline 2), with the ontology-contamination caveat and the
  superseded-claims list built in.
- ☐ 2. k=5 self-consistency confidence on all 7 schemes; compare with self-reported confidence,
  including the pmksypdmc-style inversion.
- ☐ 3. Baseline 1 (flat attribute extraction) and Baseline 3 (extraction without judge/repair): code
  both, run Baseline 3.
- ☐ 4. Multilingual stage 1 (understanding).

### Day 2
- ☐ 5. Run Baseline 1.
- ☐ 6. Gate re-validation on a synthetic injected-error corpus (≥100 labelled mutations of frozen
  gold): false-accept / false-defer, precision-recall curve, ECE with k=5 confidence.
- ☐ 7. Fix the RAG api_error; with/without-retrieval comparison.
- ☐ 8. Multilingual stage 2 (replies).

### Day 3
- ☐ 9. Temporal case study (C4).
- ☐ 10. Cross-lingual case study (C2).
- ☐ 11. Multilingual stage 3 (interface).
- ☐ 12. README.md, RESULTS.md, full suite, push.

## Decisions needed

- **D1 (2026-10-04)** — OpenRouter has 0 credit, so it cannot serve `openai/gpt-oss-120b`. Options:
  add credit; or run the push on Groq alone (8k TPM / ~200k TPD caps the quota-heavy items — see the
  day-1 report). Also: OpenRouter spreads the model over hosts with different quantizations; pinning
  OpenRouter to the Groq host (`provider.order=["Groq"]`, no fallbacks) would keep the serving stack
  identical to the Groq runs.

## Gold errors found (not fixed during the push)

*None yet. Open findings from the 2026-10-04 independent gold review are in that report and
`KNOWN_ISSUES.md`; they are part of gold-v2 as frozen.*

## Daily reports

*(appended at the end of each day)*
