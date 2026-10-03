# Known Issues

Deferred, non-blocking issues found during Phase 2/3 validation. Logged here instead of fixed
immediately so they aren't rediscovered from scratch later. Each entry: what, where, why deferred,
suggested fix.

## Calibration gate: self-reported confidence can be inverted, not just noisy

**Where**: `schemelogic/deferral/calibration_gate.py` (the `confidence` signal and its
`BASE_CONFIDENCE_THRESHOLD` / `TEMPORAL_CONFIDENCE_THRESHOLD` bars), and
`schemelogic/extraction/extractor.py`'s `_meta_system_prompt`, which asks the model to
self-assess.

**What**: the gate treats a high self-reported `extraction_metadata.confidence` as evidence an
extraction is sound. The AI-Checked diagnosis on 2026-09-15 produced a concrete counterexample
where that signal was not merely weak but backwards.

Scheme `pmksypdmc` (slug in `data/silver/schemes.jsonl`) has the LARGEST source text in that
16-scheme sample — 3,938 characters of description plus eligibility prose. The extraction
collapsed it to a single predicate, `is_indian_citizen == true`, with zero exclusions: no
discriminating eligibility rule at all. It reported `confidence: 0.95` and
`flagged_for_review: false` — the highest confidence and the only unflagged result in the whole
sample. Every one of the 14 genuinely useful extractions alongside it reported confidence
0.3–0.7 with `flagged_for_review: true`.

So on this example the confidence ordering is exactly inverted: the one output that recovered
nothing was the one the model was surest about. Any deferral/calibration claim resting on this
signal (O4/C5, Phase 7) has to contend with that, and an ECE/PR-curve computed over
self-reported confidence will look better than the signal deserves if such cases are rare in the
sample but harmful when they occur.

**Found**: AI-Checked live diagnosis, 2026-09-15. Raw row in
`data/extraction_runs/ai_checked_diagnosis_2026-09-15.jsonl` (`slug: pmksypdmc`).

**Mitigated, not fixed**: `schemelogic/conversational/ai_checked.py`'s `is_vacuous()` now catches
this specific shape STRUCTURALLY (zero discriminating predicates → honest fallback to
description-only), deliberately without consulting confidence, precisely because confidence
couldn't be trusted here. That protects the citizen-facing tier. It does NOT fix the gate: a
partially-collapsed extraction (some real predicates, several missed) would still sail through on
a high self-reported confidence, and `is_vacuous` would not catch it.

**Why deferred**: the real fix is a confidence signal that isn't self-reported — k-sample
self-consistency, as the plan's Phase 1.4 specifies and which was never implemented (the current
number is the model's own guess about itself). That's a separate piece of work with its own quota
cost, not a tweak to the gate's thresholds. Lowering the thresholds would not help: this case
scored 0.95.

**Suggested fix**: implement k=5 self-consistency scoring and have the gate use the AGREEMENT
score rather than (or alongside) the self-reported one; re-run the gate validation afterwards and
check whether `pmksypdmc`-shaped collapses separate from good extractions under the new signal.
Also worth adding a structural signal to the gate itself: predicate count wildly disproportionate
to source-document length is suspicious regardless of stated confidence.

**Status**: Open as of 2026-09-16. Citizen-facing path mitigated structurally; gate unfixed.

## [RESOLVED 2026-09-18] AI-Checked Q&A phrasing is rough for newly-proposed ontology fields

**Where**: `schemelogic/conversational/question_selector.py`'s `build_question()` fallback branch,
reached whenever `schemelogic/schema/field_ontology.py`'s `citizen_question_for(field)` returns
None.

**What**: extractions from myScheme text propose a lot of new field names (1–7 per scheme in the
2026-09-15 sample, since the canonical ontology's 69 fields were grown around 7 gold schemes and
don't cover the long tail of state schemes). A proposed field has no `citizen_question`, so the
citizen is asked the generic fallback instead of a real question:

```
Q2 [boolean] Do you meet this criterion: "is forward community"?
Q6 [boolean] Do you meet this criterion: "bride education up to 5th"?
```

against a gold scheme's `What is your monthly pension amount, in rupees?`. The Q&A is fully
functional and the verdict is computed correctly — this is presentation quality, not correctness —
but it is the main remaining experiential gap between an AI-Checked conversation and a Verified
one, now that the interaction itself is identical (same question loop, same evaluator, same
verdict sections; see `tests/test_chat_engine.py::test_ai_checked_qa_is_identical_to_gold_except_tier`).

**Found**: AI-Checked recovery validation, 2026-09-15 (`dmrnicmasii`, 10 substantive predicates,
most of them newly proposed).

**Why deferred**: the fix is a new LLM touchpoint (generate a plain-language citizen question for
a novel field name), which needs care to stay inside this project's invariant — such a call may
only ever produce QUESTION WORDING, never a field, a value, or anything that reaches the
evaluator — plus caching so it isn't repaid per session, and a deterministic fallback to today's
phrasing when the call fails.

**Suggested fix**: a phrasing step keyed on the field name, one call per novel field, cached to
disk alongside the AI-Checked scheme cache; on any failure fall back to the current raw phrasing
rather than blocking the Q&A. Growing `field_ontology.py` itself is the alternative, and is the
better answer for fields that recur across many schemes.

**Status**: **Resolved 2026-09-18** in commit `c437975` ("feat(ai-checked): plain-language questions
for novel extracted fields"). Kept here as a record, not deleted.

**Resolution**: implemented as the suggested fix. `schemelogic/conversational/field_phrasing.py`
makes one LLM call per NOVEL field (never per scheme, never per session), producing question
wording only, and registers it in a runtime overlay that `field_ontology.citizen_question_for()`
consults after the canonical ontology — so `question_selector.py` stays LLM-free and every consumer
picks it up without plumbing. Canonical, human-written questions are never overridden, and the
overlay is kept out of `FIELD_ONTOLOGY` / `format_for_prompt()` / `all_field_names()` so generated
strings can't leak into the extractor's vocabulary or the structural-F1 comparison. Cached per
field in memory and in `data/cache/field_questions.json`; failures are never cached, and any
failure leaves the old generic phrasing in place rather than blocking the Q&A. Covered by 27 tests
in `tests/test_field_phrasing.py` plus 2 conversation-level tests in `tests/test_chat_engine.py`
(the improvement reaches the question the citizen actually sees; a phrasing failure leaves the
fallback and the Q&A still runs).

**Evidence it works** (live, not mocked):
- `dmrnicmasii` — the scheme that originally exposed this — 6/6 novel fields phrased, second pass 0
  LLM calls. `Do you meet this criterion: "is forward community"?` became `Are you a member of the
  Forward Community?`; `"bride education 10th passed"` became `Has the bride passed the 10th
  standard?`.
- An independent live app session on scheme `fs` (2026-09-19 17:26) phrased 8 more fields on a
  scheme the feature was never tuned against, e.g. `Are you a member of the Other Backward Classes
  (OBC) category?`, `Do you receive a post-matric scholarship for Scheduled Caste or Scheduled
  Tribe?`. 14 phrasings cached across the two schemes; all reviewed by hand.

**How often it matters**: in the 2026-09-19 AI-Checked diagnosis (n=16 new schemes), 61 of 75
substantive predicates — **81.3%** — were novel fields (78.4% pooled over n=32), i.e. roughly four
of every five questions in an AI-Checked conversation now go through this path. Note that figure
measures the feature's REACH, not its quality: the diagnosis runs called the extractor directly and
did not phrase anything. Quality evidence is the hand-reviewed live phrasings above, which is a
small sample (14 fields, 2 schemes).

**Residual imperfections, recorded so they aren't rediscovered**:
- Subject preservation is good but not perfect: `bride_has_degree` → `Do you have a degree?` drops
  the bride, where its sibling fields kept her. Benign when the applicant is the bride, wrong
  otherwise.
- The cache is keyed by field name alone, so the first scheme to phrase a shared field decides its
  wording for every later scheme. Intended (a field is meant to be one reusable concept), but it
  means scheme context only informs the FIRST phrasing of a field.
- Three defects caught only by live validation, now fixed and covered by tests: a `max_tokens=60`
  cap returned empty content on every call (gpt-oss reasoning tokens), `is_forward_community` was
  initially rendered "forward-thinking community" without scheme context, and two contradictory
  validator rules rejected valid third-party and field-sourced-number phrasings.

## Calibration gate: markdown bold markers can break verbatim-quote matching

**Where**: `schemelogic/deferral/calibration_gate.py`, `_quote_is_verbatim()`.

**What**: Source documents in `data/raw_documents/*.md` use markdown `**bold**` around key phrases
(e.g. AB-PMJAY.md's `**Senior citizens 70 years and above (added 11 September 2024)**: the scheme
was expanded...`). A judge quote that spans across a `**` boundary (quoting the prose without the
markdown syntax, as it naturally would) fails the verbatim substring check, since `_normalize()`
doesn't strip markdown syntax — the `**` characters sit in the source but not in the quote.

**Found**: AB-PMJAY Phase 3 check-in (2026-08-18). A judge `temporal_supersession` finding's quote
tripped `quote_verbatim_in_source: False` partly due to this, though the gate still correctly
deferred the finding for other reasons (fabricated boolean `retired_value`, not reproduced on
independent re-sample) — so this hasn't caused a wrong decision yet, just a partially-wrong reason
in the audit trail.

**Why deferred**: Didn't change any gate decision observed so far. Fixing it well requires
deciding how much markdown to strip from `_normalize()` without also loosening the check enough to
let genuinely fabricated quotes slip through (e.g. don't want to strip so aggressively that
`_quote_is_verbatim` starts ignoring real textual differences).

**Suggested fix**: Strip common markdown emphasis syntax (`**`, `*`, `_`, `` ` ``) from both the
quote and the document in `_normalize()` before substring matching. Add a regression test using a
document with the same `**bold**`-spanning-a-quote-boundary shape as AB-PMJAY.md's 70+ clause.

**Status**: Open, unfixed as of 2026-08-18.
