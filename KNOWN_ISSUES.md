# Known Issues

Deferred, non-blocking issues found during Phase 2/3 validation. Logged here instead of fixed
immediately so they aren't rediscovered from scratch later. Each entry: what, where, why deferred,
suggested fix.

## [RESOLVED 2026-10-03] Gold: AB-PMJAY applies socio-economic exclusions to the 70+ path

**Where**: `data/gold/AB-PMJAY.json` (and its copy in `tests/gold_fixtures.py`) — the 14 SECC
exclusions and the `has_family_member_aged_70_or_above` inclusion branch.

**What**: the exclusions are a flat list, so they apply to every inclusion path. The NHA's 70+
expansion guidelines (`data/raw_documents/AB-PMJAY_primary_70plus_expansion.pdf`) cover all
citizens aged 70+ *"irrespective of their socio-economic status"* and never apply the SECC
exclusions to them. Verified with the real evaluator: a 70+ senior whose household owns a
refrigerator or landline, has a member earning >₹10,000/month, or has a member paying income tax
gets **ineligible**. That is a wrong verdict from the live app, for exactly the population the 2024
expansion targeted. The gold's own `seventy_plus_eligible_regardless_of_secc` profile set every
exclusion false, so it never exercised the conflict.

**Found**: gold sourcing audit, 2026-10-03 (`docs/GOLD_AUDIT_2026-10-03.md` §3).

**Status**: **Resolved 2026-10-03.** Every exclusion now carries an applicant-scoped exception on
`has_family_member_aged_70_or_above`. That required a backward-compatible evaluator extension,
`except_scope`, because a plain member-scoped exception reads the 70+ fact off whichever family
member triggered the exclusion and yields "undetermined" — including for a household with no 70+
member at all, which was previously, correctly, "ineligible". Full record and the tests that forced
the design: `docs/GOLD_AUDIT_2026-10-03.md` §6.1.

## Question selector asks about branches that are already decided

**Where**: `schemelogic/conversational/question_selector.py`, `_walk_inclusion()` /
`find_missing_fields()`.

**What**: the selector collects every unresolved leaf in the inclusion tree, including leaves under
a branch whose result is already known. The evaluator traces every child of an `or` (it doesn't
short-circuit), so once one alternative is satisfied, the citizen is still asked about all the
others whenever anything else in the scheme is still unknown. Measured 2026-10-03 on PMMVY: a woman
who has already said she is SC/ST — which satisfies the category requirement — is then asked **9
irrelevant questions** (disability, BPL, AB-PMJAY, e-Shram, PM-KISAN, MGNREGA, income, frontline
worker, NFSA) before the one that still matters, the child's birth order. The same shape affects
every scheme with an `or`: PM-UJJWALA's ten categories, AB-PMJAY's five routes, PMAY-G's three, and
any AI-Checked scheme.

Verdicts are never wrong — this is about which questions get asked, not what is concluded. But it
undercuts the reason the plan gives for three-valued verdicts: asking "only the questions still
needed".

**Found**: while encoding the PMMVY age-floor fix, 2026-10-03. That fix works around it by placing
the precise floor LAST in its conjunction; see the PMMVY entry below.

**Suggested fix**: in `_walk_inclusion`, don't descend into a node whose result is already definite.
Under Kleene logic a known True or False can't be changed by resolving the unknowns beneath it, so
those leaves are provably irrelevant. Apply the same per member in `_walk_exclusions`: skip a member
entry whose combined result is already definite, which also covers exclusions waived by an
exception. Needs a test pinning the PMMVY sequence above, and a check that `test_question_selector`
doesn't encode the current over-asking as expected behaviour.

**Why not fixed here**: it changes the question order of every OR-structured conversation, gold and
AI-Checked, which is outside a gold-data fix and deserves its own review.

**Status**: Open as of 2026-10-03.

## [RESOLVED 2026-10-03] Gold: PMMVY age floor is 18, the source says 18 years 7 months

**Where**: `data/gold/PMMVY.json`, `inclusion.and[0]` — `age >= 18`.

**What**: the source (`data/raw_documents/PMMVY.md`) says the beneficiary must be *"between 18 years
7 months and 55 years of age at the time of childbirth"*. The gold's floor drops the 7 months, and
its `source_clause` says the age criterion was "corroborated verbatim" — so the discrepancy was
never recorded. Women aged 18y0m–18y6m get a wrong **eligible**, the harmful direction.

**Found**: gold sourcing audit, 2026-10-03.

**Status**: **Resolved 2026-10-03.** Added the conjunct `or[age >= 19, months_since_last_birthday >= 7]`
plus a new ontology field `months_since_last_birthday`. Ages are asked in whole years, so 18 is the
only ambiguous value, and the months question is only ever reached for an 18-year-old. The
`source_clause` now says plainly that "corroborated verbatim" referred to the source text, not this
gold's encoding. Still unmodelled, as before: the source measures age *at the time of childbirth*,
while the gold uses current age. Record: `docs/GOLD_AUDIT_2026-10-03.md` §6.2.

## Gold: IGNOAPS exclusions rest on an inference its author doubts, and on an out-of-scope clause

**Where**: `data/gold/IGNOAPS.json` exclusions.

**What**: `has_regular_family_financial_support` is built from the NSAP programme-wide *destitute*
definition (Para 1.1.1); the gold's own `source_clause` calls it "an interpretive elevation",
"philosophical/preambular framing" that "may already be subsumed by the BPL determination". Both of
Baseline 2's IGNOAPS harmful errors turn on it. The other three exclusions (government job, 5+ acres,
four-wheeler) appear verbatim only inside the §2.4.3 AIDS-widow carve-out — "except widows suffering
from AIDS who will be considered if they are not attracted by any of the exclusion criteria…" — but
the gold applies them to every applicant.

**Found**: gold sourcing audit, 2026-10-03.

**Status**: Open as of 2026-10-03 — scheduled for fix in this pass.

## Gold: PMMVY encodes "first/second living child" as birth order

**Where**: `data/gold/PMMVY.json`, `inclusion.and[3]` — `pregnancy_child_order`.

**What**: the source covers the *first living child* and, under PMMVY 2.0, the *second living child*
if a girl. `pregnancy_child_order` reads as birth order, which differs whenever an earlier child has
died: a woman whose first child died would, by the source, be claiming for her first *living* child,
but the gold would count it as order 2 and demand a girl. Undocumented.

**What would resolve it**: the MWCD scheme guidelines or notification text defining "living child"
for PMMVY purposes (the gold was built from a PIB backgrounder; the guidelines were never
retrieved). If that text confirms the living-child reading, re-encode as a count of living children,
with a citizen question that asks it that way.

**Status**: Open, document-only (no primary source on hand).

## Gold: PMAY-G exclusions — a primary source now contradicts the gold

**Where**: `data/gold/PMAY-G.json` exclusions.

**What**: logged originally as two questions — the source `.md` says exclusions were "reduced from 13
to 10 parameters" but lists 11, and identically worded "Households with…" clauses get
inconsistent quantifiers (`some_family_member` for govt employee, income and tax; `self` for
enterprise, assets and land).

The audit then found a primary-quality source that answers the first question:
`data/raw_documents/IGNOAPS_primary.pdf` is actually the **MoRD Annual Report 2024-25**, and it
states PMAY-G's revised criteria directly (`docs/GOLD_AUDIT_2026-10-03.md` §4). Against it, the gold
has four concrete errors:
- `owns_refrigerator` and `owns_landline_phone` are exclusions the Union Cabinet **deleted** —
  households owning either get a wrong "ineligible";
- *paying professional tax* and *5+ acres of unirrigated land* are exclusions the gold is missing;
- irrigated land is "2.5 acres **or more**" (`>=`), where the gold has `>`;
- pucca housing is a separate Step 1 pre-filter (pucca roof and/or wall, or more than 2 rooms), not
  one of the 10 — which explains the "11 vs 10" count, and is broader than `owns_pucca_house`.

The quantifier inconsistency remains: the annual report words some criteria as "any member" and
others as household-level, which partly matches the gold and partly doesn't.

**What would resolve it**: a decision to adopt the MoRD annual report as PMAY-G's authoritative
source. It is an official Ministry publication, more authoritative than the PIB backgrounder and
news coverage the gold was built from. If adopted: remove the two deleted exclusions, add the two
missing ones, correct the operator, re-model the pucca pre-filter, and align quantifiers with the
report's wording. Ideally also rename the PDF so it isn't filed under IGNOAPS.

**Status**: Open, document-only by decision for this pass, although a primary source is now on hand.

## Gold: MH-LADKI-BAHIN's MP/MLA exclusion uses a broader field

**Where**: `data/gold/MH-LADKI-BAHIN.json`, `excl[3]` — `holds_constitutional_or_political_post`.

**What**: the Marathi GR clause (५) is literally "ज्यांच्या कुटुंबातील सदस्य विद्यमान किंवा माजी
खासदार/आमदार आहे" — a family member who is a current or former **MP/MLA**. The gold reuses
PM-KISAN's canonical `holds_constitutional_or_political_post`, which also covers constitutional
posts, ministers, mayors and district panchayat chairs. A family with a former mayor would be
wrongly excluded. The `source_clause` calls it "the same real-world concept"; it isn't.

**What would resolve it**: no new source is needed, since the GR is primary and unambiguous. Add a
narrower `is_current_or_former_mp_or_mla` field for this scheme. It's listed as document-only
because it's a field-design change for the gold owner to approve rather than a clear error of fact.

**Status**: Open, document-only.

## Test hazard: the gold set exists twice

**Where**: `data/gold/*.json` (read by the app, the evaluation harness and Baseline 2) and the
Python copies in `tests/gold_fixtures.py` / `tests/fixtures.py` (read by `tests/test_gold_schemes.py`).

**What**: nothing checked the two agreed. A gold fix applied to only one would leave the gold tests
green while asserting the old behaviour. They were found to be in sync on 2026-10-03, before any
fix. `tests/gold_fixtures.py`'s docstring also still describes the copies as unverified
"illustrative test data", which is no longer true.

**Mitigated**: `test_gold_json_and_test_fixture_copies_hold_identical_rules` now fails on any drift,
and `scripts/audit_gold.py sync` checks the same thing.

**What would resolve it fully**: generate the test copies from `data/gold/` (or have the tests load
the JSON directly) so there is one source of truth.

**Status**: Mitigated, not resolved.

## [RESOLVED 2026-10-03] Gold: PM-UJJWALA-2.0's citizenship predicate has no recorded source

**Where**: `data/gold/PM-UJJWALA-2.0.json`, `inclusion.and[2]` —
`{"field": "is_indian_citizen", "op": "==", "value": true}` — and the profile that exercises it,
`data/profiles/PM-UJJWALA-2.0.json` → `non_citizen_ineligible`.

**What**: the gold makes Indian citizenship a gating inclusion condition, but the scheme's source
document (`data/raw_documents/PM-UJJWALA-2.0.md`) never mentions citizenship — no match for
"citizen", "Indian national" or "nationality" anywhere in it — and the gold's own `source_clause`,
which carefully documents every other uncertainty (the unstated age threshold, the
secondary-source category list, field renames), says nothing about where this predicate came
from.

Contrast PM-KISAN, whose gold explicitly records its own `is_indian_citizen` as "NOT a
directly-stated standalone clause... inferred from the Para 4.1(c) NRI exclusion". That is a
documented inference a reader can evaluate. PM-UJJWALA's is undocumented.

**Why it matters — two independent systems have now "failed" on exactly this predicate**:
- Phase 3 check-in, 2026-08-18: the extractor missed it (citizenship-category F1 = 0.0, fn = 1).
- Baseline 2, 2026-10-03: the direct-LLM baseline answered "eligible" for `non_citizen_ineligible`
  where the evaluator says ineligible, counted as a harmful false positive.

Both were judged against a rule the source they were given does not contain. In both cases the
"error" may be faithfulness to the document. The profile's own `_comment` says this was "the
field the draft was expected to miss going into this run", so the predicate was known to be weak
when the profile was written.

The real PMUY guidelines may well require citizenship; if so, the primary notification saying so
needs to be cited in `source_clause` and ideally added to the source document. If not, the
predicate should come out of the gold. Either way the current state silently charges the
extractor and the baseline for disagreeing with an unsourced rule.

**Effect on reported numbers**: Baseline 2 is reported both ways until this is resolved
(see `scripts/summarize_baseline2.py`):
  - counting the row: 67 profiles, agreement 94.0%, harmful-positive 4.5% (3/67)
  - excluding it as contested: 66 profiles, agreement 95.5%, harmful-positive 3.0% (2/66)
The Phase 3 PM-UJJWALA citizenship false negative should be read with the same caveat.

**Found**: Baseline 2 completion run, 2026-10-03.

**Why not fixed here**: it's a ground-truth decision for whoever owns the gold set, and changing
gold silently moves every number already reported against it. Same root cause the status reports
keep flagging: the gold set was built without the plan's annotation process (no guidelines, no
dual annotation, no annotation log), so nothing forced every predicate to carry a source.

**Suggested fix**: locate the primary PMUY 2.0 notification clause on citizenship. If found, cite
it in `source_clause` and add it to the source document. If not, remove the predicate and
re-derive the affected numbers. Worth then auditing all 7 gold schemes for any other predicate
whose `source_clause` doesn't account for it — this was found by accident.

**Status**: **Resolved 2026-10-03** — predicate removed from both gold copies, per the decision to treat it as unsourced. The `source_clause` records the condition for restoring it (a cited primary PMUY 2.0 clause requiring citizenship). The profile was renamed `non_citizen_not_excluded_by_source`, facts unchanged, and the Baseline 2 contested-row caveat for it no longer applies. Record: `docs/GOLD_AUDIT_2026-10-03.md` §6.3.

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
