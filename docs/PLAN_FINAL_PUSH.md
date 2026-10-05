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

Measured from each response's `usage` (`data/experiments/token_ledger.jsonl`). Groq free tier: $0.

| Date | Item | Provider | LLM calls | Tokens (measured) | Cost |
|---|---|---|---|---|---|
| 2026-10-05 | k=3 self-consistency, 19 of 21 samples (2 calls each) | Groq | 38 | 167,977 | $0.00 |
| **Total** | | | **38** | **167,977** | **$0.00** |

**Groq's daily cap is a rolling 24h window, not a calendar day** (found 2026-10-05: the first run hit it
at 97.6k tokens of that day because the previous evening's runs were still in the window). The ledger's
budget now checks a rolling 24h total.

## Quota schedule (Groq, ~180k tokens/day)

**Revised 2026-10-05 (day 2).** What is left, by queue, at measured rates (an extraction sample is
~8.8k tokens; a judge call is estimated at 8k). The queues run unattended and wait for the rolling
window (`scripts/run_queue.py`; logs in `data/experiments/logs/`, gitignored):

| Queue | Runs | Est. tokens |
|---|---|---|
| day2 (running; resumes ~00:30 on 10-06) | PMMVY samples 2–3; pmksypdmc k=3; full pipeline on sample 1 (7 judge calls); Baseline 1 (7 calls) | ~146k |
| day3 (starts when day2 exits) | gate re-validation (21 judge calls); RAG with/without retrieval (4) | ~200k |
| day4 (after day3) | temporal C4 + Marathi C2 arm (9 extractions); catalogue translations hi, ur, mr, ta (~32 batches) | ~79k + ~110k |
| then | one short live conversation per language | ~10k |

About 545k in all, so ~3 more rolling windows: **the runs finish around 2026-10-09, not on day 4**
(decision D2 below).

Original estimates (2026-10-05, day 1):

| Day | Quota-heavy runs | Est. tokens |
|---|---|---|
| 1 (2026-10-05) | k=3 extraction samples, 7 schemes (21 extractions; sample 1 doubles as Baseline 3) — as far as the day's budget goes | ~180k |
| 2 | finish k=3; Baseline 1 (7 calls) | ~60k + ~35k |
| 3 | gate re-validation (~30 injected errors); RAG with/without retrieval | ~140k + ~40k |
| 4 | temporal C4 (pre/post extractions); cross-lingual C2; multilingual translations and one live chat per language | ~90k + ~40k + ~50k |

## Plan and status

Legend: ☐ not started · ◐ in progress · ☑ done · ⊘ dropped (with reason)

### Day 1
- ☑ 0. Provider extension (`7254948`): extractor, judge and baseline runners use the provider abstraction (Groq
  default; OpenRouter fallback or explicit `--provider`); default unchanged; tests unmodified.
- ☑ 1. (`c8b7508`; regenerate with `scripts/run_batch_report.py`) Batch runner + one aggregate report across all 7 gold schemes (structural F1, outcome
  equivalence, scalar checks, Baseline 2), with the ontology-contamination caveat and the
  superseded-claims list built in.
- ◐ 2. 19/21 samples done (PMMVY 2 left); analysis `scripts/analyze_self_consistency.py`. **k=3** self-consistency confidence on all 7 schemes (reduced from k=5, D1); compare with
  self-reported confidence, including the pmksypdmc-style inversion.
- ◐ 3. Baseline 1 (flat attribute extraction) and Baseline 3 (extraction without judge/repair): code
  both ☑ (`8195ad8`), run Baseline 3 ◐ (= k=3 sample 1; 6/7 valid, MH-LADKI-BAHIN's sample 1 failed
  schema validation, PMMVY's done). Added: the full pipeline on the SAME sample 1
  (`scripts/run_pipeline_on_samples.py`, ~56k tokens, day 2) — the 2026-08 pipeline drafts used older
  code and ontology, so they are not a fair comparison.
- ☑ 4. Multilingual stage 1 (understanding) (`6cac897`).

### Day 2
- ◐ 5. Run Baseline 1 — queued (day2 queue, last item).
- ◐ 6. Corpus + runner coded (`3ccd199`, `57735f4`); scoring broken down by error type, the types outside
  the judge's design kept separate (`173a739`); agreement part scored offline; judge run queued (day3). Gate re-validation on a synthetic injected-error corpus of **~30** labelled mutations of frozen
  gold (reduced from ≥100, D1 — reported explicitly as a small-sample result): false-accept /
  false-defer, precision-recall curve, ECE with the k=3 confidence.
- ◐ 7. Fix the RAG api_error ☑ (`1700e9f`: request-too-large under the 8k ceiling); with/without-retrieval
  comparison runner ☑ (`3fc3821`), run queued (day3).
- ☑ 8. Multilingual stage 2 (replies) (`c152bde`). The translations themselves are queued (day4); until
  they exist every non-English string falls back to English.

### Day 3
- ◐ 9. Temporal case study (C4): runner and offline scoring ☑ (`4c14539`, `26ab49c`). **No scheme
  dropped** — official pre-amendment text found for all five: PM-KISAN (guidelines as first issued,
  linked on pmkisan.gov.in as "Pre-Revised Operational Guidelines"), MH-LADKI-BAHIN (GR 28.06.2024),
  AB-PMJAY (NHA identification guidelines + SECC 2011 list; an addition, nothing retired), PMAY-G
  (Framework 2022 edition, 13 parameters) and PMMVY (2017 guidelines); plus the stale PMAY-G
  document. Post arms reuse the k=3 samples (no quota). 9 extractions queued (day4).
- ◐ 10. Cross-lingual case study (C2): analysis ☑ (`26ab49c`); the Marathi arm (three GRs in order, k=3)
  is queued with item 9. Hindi/English: PM-KISAN's 2019 summary exists in both on pmkisan.gov.in, but
  the Hindi PDF uses a legacy non-Unicode font (extracted text is corrupted) — recorded as not run.
- ◐ 11. Multilingual stage 3 (interface): code ☑ (`defed6e`); UI strings for ur/mr/ta and the live
  conversation per language follow the translations.
- ◐ 12. README.md ☑; RESULTS.md once the runs are in; full suite (976 passing on 2026-10-05).

## Design notes (recorded as found)

- **The judge cannot flag a predicate that is present but wrong.** Its findings are only "preambular
  implied fact" (a missing predicate) or "temporal supersession". In the gate re-validation, flipped
  operators, wrong thresholds, quantifiers and exception scopes are therefore outside what judge+gate can
  catch by design; that is reported as a result, and the k=3 agreement signal (a predicate's share of
  independent extraction samples that produced it) is evaluated alongside as a deferral signal at no
  extra quota.
- **The RAG api_error** (2026-08-18, 4/4 cases): the judge's fixed prompt is ~6.4k tokens (ontology +
  schema), ~7.1k with document and draft; retrieved Marathi chunks pushed prompt + completion past Groq's
  8k-per-request ceiling ("request too large"). Context is now fitted; on this account about one Marathi
  chunk fits beside a real document — a limit on the with-retrieval arm, to be stated with its result.
- **Gate candidates are blinded**: the gold's `source_clause` (the annotator's reasoning) is replaced
  before the judge sees a candidate, and the draft is sent compact (AB-PMJAY's indented draft alone
  exceeded the request ceiling).

## Later ideas (not this push)

- **Flag single-sample rules in AI-Checked schemes** (2026-10-05): rules that appear in only 1 of 3
  extraction samples were right 17% of the time on gold (vs 97% for 3/3), so flagging or dropping them
  could improve AI-Checked schemes. But it triples the cost of each live extraction (already ~9k tokens
  against an 8k/min ceiling), so it is not for the live app yet.

## Reporting rules for item 6 (2026-10-05)

- Results broken down **by error type**. The types outside the judge's design (present-but-wrong
  rules: flipped operator, wrong threshold, wrong quantifier, wrong exception scope) are reported
  **separately** from the ones it is meant to catch (dropped predicate, fabricated supersedes). No single
  overall catch rate mixes the two.

## Decisions needed

- **D2 (2026-10-05)** — the remaining runs need ~545k tokens, about three more rolling windows, so they
  finish around **2026-10-09** instead of on day 4. Options: (a) let them run (recommended — they are
  unattended and nothing else waits on quota); (b) cut to fit, e.g. gate re-validation on fewer
  candidates or translations for fewer languages. Until you say otherwise the queues continue in the
  order above.

- ~~**D1 (2026-10-04)** — OpenRouter has 0 credit.~~ **Decided 2026-10-05**: no credit; Groq free tier
  only; k=3 instead of k=5; ~30 injected errors instead of ≥100; quota-heavy runs over 4 days at
  ~180k tokens/day; OpenRouter only as the chat's existing fallback.

## Gold errors found (not fixed during the push)

*None yet. Open findings from the 2026-10-04 independent gold review are in that report and
`KNOWN_ISSUES.md`; they are part of gold-v2 as frozen.*

## Daily reports

*(appended at the end of each day)*

### Day 1 — 2026-10-05

**Done**
- Plan, gold frozen at `gold-v2`. OpenRouter checked (0 credit) → Groq only (D1).
- Item 0: provider option on extractor/judge/Baseline 2, measured usage, no-fallback switch; all existing tests unmodified.
- Experiment harness: frozen-gold reads from the tag, standard result header, token ledger, rolling-24h budget, per-minute pacing.
- Item 1: batch runner + aggregate report (`docs/results/BATCH_REPORT.md`), caveats and 20 superseded claims built in.
- Item 2: 19 of 21 k=3 samples; offline analysis (`docs/results/SELF_CONSISTENCY.md`).
- Item 3: Baseline 1 code; Baseline 3 = sample 1 (results in the batch report); pipeline-on-sample-1 runner for a fair comparison.
- Item 4: multilingual stage 1.
- Ahead of schedule (code only): injected-error corpus + gate runner (item 6), RAG api_error diagnosed and fixed (item 7), pmksypdmc sampling option.

**Interim results (k=3, 6 schemes scored; small sample)**
- Predicate-level calibration (212 predicates): agreement ECE **0.057** vs self-reported **0.089**. Predicates in 1/3 samples are right 17% of the time, 2/3 → 73%, 3/3 → 97%; self-reported confidence sits at 0.85–0.97 for nearly everything.
- Scheme ranking vs structural F1 (Spearman, n=6): agreement **0.76**, self-reported **0.41**. PMAY-G: lowest agreement (0.64), lowest F1, self-reported 0.85–0.95.
- Baseline 3 (one extraction, no judge/repair), 6 schemes: structural F1 0.707 micro, outcome agreement 68.6%.

**Not done**: PMMVY samples 2–3; pmksypdmc sampling; stage 2–3; all day-2+ runs.

**Tokens / cost**: 167,977 measured (38 calls), $0.00.

**Needs your decision**: none blocking. FYI the gate re-validation design note above (the judge's two finding types bound what it can catch).

### Day 2 — 2026-10-05

**Done**
- Item 6: gate re-validation scoring by error type; present-but-wrong types reported apart from the
  ones the judge is meant to catch (your note). Agreement signal scored offline: all 15 present-but-wrong
  injected rules had agreement ≤ 1/3 (recall 1.0), precision ~0.19 (PMMVY skipped, 1 sample).
- Item 7: RAG comparison runner (fix was day 1).
- Item 8: multilingual stage 2 — replies, questions, verdicts and explanations in the citizen's
  language; description translation, cached and labelled; translation validator and review sheets.
- Item 9: temporal C4 runner; all five schemes have official pre-amendment text (PM-KISAN's found
  today on pmkisan.gov.in, so it is not dropped).
- Item 10: C2 analysis (Marathi vs English, with a same-language noise baseline).
- Item 11: stage 3 code — five-language menu, Urdu right-to-left, speech-recognition language.
- Item 12: README.md.
- Plan note: flag 1-of-3 rules in AI-Checked schemes, as a later idea (your note).
- Already visible from the k=3 post samples (no new quota): PMAY-G's deleted refrigerator and
  landline exclusions were dropped in 3/3 samples from the updated document (the single 2026-10-04
  run had kept them); AB-PMJAY's 70+ branch present 3/3; MH-LADKI's age bound 65 and no land
  exclusion 2/2 (the third sample failed validation); PMMVY's one sample has **no** child-order rule
  at all.

**Not done**: every quota run of items 5, 6, 7, 9, 10 and the translations — the rolling window was
spent on day 1's samples. All are queued and run unattended (see the quota schedule).

**Tokens / cost**: 0 today (the window was full from day 1); total 167,977, $0.00.

**Needs your decision**: D2 (finish ~2026-10-09, or cut).

