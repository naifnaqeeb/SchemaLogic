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
the design: `docs/GOLD_AUDIT_2026-10-03.md` §6.1. Revised 2026-10-04 after an independent review
(§6.6): applicant scope now waives the whole exclusion once, is rejected with quantifier `self` (so
the 10 `self` exclusions use member scope, verdicts unchanged), and is gold-only — the extractor
can't produce it.

## [RESOLVED 2026-10-04] Gold: AB-PMJAY's 70+ route covers the household, the guidelines cover only the 70+ members

**Where**: `data/gold/AB-PMJAY.json` (and `tests/gold_fixtures.py`) — the inclusion branch and all
14 exceptions read `has_family_member_aged_70_or_above`, a household fact on the applicant's record.

**What**: the 70+ expansion guidelines, §5.2: for new families *"a shared cover up to Rs 5 lakh per
year will be available. This cover will not be available to the other members (who are not of the
age 70 years and above)"*. The cover is shared among the 70+ members; it does not extend to their
household. Verified with the evaluator: a 40-year-old applicant with a 74-year-old parent and no
other route gets **eligible**. Under §5.2 that applicant is not covered by the route.

**Found**: 2026-10-04, looking for the "on a family basis" clause after the except_scope review
(`docs/GOLD_AUDIT_2026-10-03.md` §6.5). Recorded in the scheme's `source_clause`.

**Why deferred**: a gold change, and the user decides those. It also raises a product question —
whether someone asking on behalf of a senior should be modelled — that the re-encoding should settle.

**Status**: **Resolved 2026-10-04.** The route now reads the applicant's own `age >= 70` in the
inclusion and all 14 exceptions; applicant scope stays on the four `some_family_member` exclusions.
The 40-year-old is now ineligible; every other profile is unchanged. Baseline 2 and the extraction
draft both make the old household reading, so each gains a false positive on the new profile
(`docs/GOLD_AUDIT_2026-10-03.md` §6.7, §7.6). Still not modelled: asking on a senior's behalf.

## Schema expressiveness limits (second except_scope review, finding 12)

**Where**: `schemelogic/schema/models.py` — what an `Exclusion` and its `except` can say. Found
2026-10-04 by the second independent review, checking the AB-PMJAY 70+ guidelines against the
mechanism. The 70+ route itself is expressible (now encoded, `docs/GOLD_AUDIT_2026-10-03.md` §6.7);
these parts are not:

- **(a) An exception with more than one condition.** `except` is a single `SimplePredicate`. "Except
  aged 70+ OR (some other condition)" needs a derived boolean field. Splitting it into two exclusions
  is wrong: two exclusions each excepting one condition give `P ∧ ¬(w1 ∧ w2)`, not `P ∧ ¬(w1 ∨ w2)`.
- **(b) The route condition is restated, not referenced.** AB-PMJAY's waiver repeats `age >= 70` in
  the inclusion and 14 exceptions; nothing ties them together, so an edit to one can drift from the
  others. Route-scoped exclusions ("this exclusion applies to routes X, Y only") would be the faithful
  encoding. Today only the gold sync and AB-PMJAY tests would catch a drift.
- **(c) Choices are not rules.** A 70+ senior already in CGHS/ECHS/CAPF or a state scheme chooses
  between it and AB-PMJAY — an election, not an exclusion. Already recorded in AB-PMJAY's
  `source_clause` as unmodelled; MH-LADKI-BAHIN's "one unmarried woman" rule is the same shape.
- **(d) Who counts as family.** The guidelines' family is spouse, *dependent* parents and children,
  and other dependants. The evaluator takes `family_members` as given and can't test dependency.
- **(e) Database status vs current facts.** The SECC exclusions describe a household's 2011 SECC
  record but are encoded as current facts (`owns_refrigerator`). The shared cover and top-ups in
  §5.1/5.2 are benefit amounts, not eligibility, and aren't modelled.
- **(f) Outside the text.** The guideline excerpt doesn't say whether SECC automatic inclusion
  overrides automatic exclusion, and lists only rural parameters.

**Why deferred**: each needs a schema extension (OR-exceptions, route references, election rules) or
a data decision; none produces a wrong verdict on the current gold. **Suggested fix**: (a) and (b)
first — an `except` that accepts an AND/OR node, and an optional `applies_to_routes` on exclusions.

## Kleene evaluation is incomplete when one field feeds several predicates (second review, finding 5)

**Where**: `schemelogic/evaluator/symbolic_engine.py`. **What**: three-valued evaluation treats each
missing fact as independent at every place it's read, so a field used twice can leave a verdict
undetermined though every value of it decides the same way. Minimal case: exclusion
`some_family_member a == 1 except a == 1 (applicant scope)`, applicant's `a` missing — the condition
on the applicant's row and the waiver cancel for every value of `a`, but the verdict is undetermined.

**Not a safety issue**: it is *sound* — never a wrong definite verdict (30,000-case soundness fuzz, 0
violations) — only sometimes asks a question it didn't need to. It predates `except_scope`; member
scope has the same gap within one member. `tests/test_engine_fuzz.py` prints the rate on every run
(about 15% of undetermined results on its random schemes; 0 when fields are disjoint).

**Possible follow-up (cheap)**: a validator *warning* when an exclusion's `except` tests the same
field as its condition — the only shape in which applicant scope adds a new instance. Not an error:
such a rule can be legitimate.

## [PARTLY RESOLVED 2026-10-04] Conversational flow: family facts default to "no family" (second review, finding 7)

**Where**: `schemelogic/conversational/session.py` (`ConversationSession.profile` starts as
`{"self": {}, "family_members": []}`), `question_selector.py`, `intake.py`.

**What**: every chat begins with an explicit empty family and nothing asks how many family members
there are, so `some_family_member` / `all_family_members` / count exclusions are evaluated over the
applicant's record alone unless the opening message described relatives. For most family-quantified
fields the applicant's question was already worded for the household ("Did you **or a family
member** pay income tax?"), so the answer covered it. Three were not -- `monthly_income_inr`
(AB-PMJAY, PMAY-G), `monthly_pension_inr` and `is_nri_per_income_tax_act_1961` (PM-KISAN) -- and for
those a relative's disqualifying fact was never asked: the chat said **eligible**.

**Resolved (option a, decided 2026-10-04)**: a field a scheme checks for the whole family, and nowhere
for the applicant alone, is asked of the applicant for the household, in that scheme's own family
definition (`FieldSpec.household_question`, `field_ontology.FAMILY_SCOPE`): PM-KISAN "you, your
husband or wife, and your minor children" (Para 3); AB-PMJAY "the members of your household" (SECC
parameter vi); PMAY-G "the members of your family" (MoRD p.141, vi). Numeric facts ask for the
highest value among them, which is exact for "any member ... more than X"; a test confines that
wording to exactly those rules. AI-Checked schemes get a household phrasing for family-wide novel
fields, and a generic household question if none is available -- never an applicant-only one.
`tests/test_household_questions.py` guards every gold scheme, every cached AI-Checked scheme and a
synthetic one. Simulated chats with a truthful citizen over all 80 gold profiles: 4 wrong definite
verdicts before (exactly those three fields), 0 after. Of the 11 an earlier simulation reported, the
other 7 were that simulation answering household-worded questions from the applicant's record only.

**Still open -- the structural follow-up**:
- **(b) Ask household composition.** The household answer lives on the applicant's record; the
  evaluator never sees separate members unless the citizen describes them. A household-size question
  up front, with an absent `family_members` key meaning "family unknown" (undetermined for non-self
  quantifiers) and `[]` meaning "no family", would represent families properly. Measured 2026-10-04
  with a patched evaluator, nothing committed: 0 of 75 gold profiles change; the selector would need
  a "no one else" answer, or it asks about member 0, 1, 2, ... indefinitely.
- **Per-member exceptions collapse onto the applicant's record.** PM-KISAN's pension exclusion
  exempts Group D employees member by member. Asked for the household, "the highest pension in the
  family" and "is that family member Group D?" are both stored on the applicant's record, so the
  exception is checked against one blended record: a Group D applicant whose husband draws a
  Rs 20,000 non-Group-D pension can be exempted by her own status. The same holds for any
  member-scoped exception on a family-wide exclusion (PM-KISAN's government-employee exclusion too).
  Only (b) -- real per-member records -- fixes it.

## [RESOLVED 2026-10-04] Structural F1 never scores `except` clauses

**Where**: `schemelogic/evaluation/structural_f1.py` — `FlatPredicate.match_key()` is
`(location, field, op, value, quantifier)`. `has_except` is recorded but not compared, and the
exception's own field/op/value and its `except_scope` are never examined.

**What**: a draft that drops an exception, has the wrong one, or scopes it wrongly scores the same as
one that gets it right. Concretely, AB-PMJAY's structural F1 is 1.000 both before and after the
2026-10-03 fix, which added 14 exceptions and changed real verdicts. Exceptions-to-exclusions is one
of the plan's headline C3 failure categories, so any per-category F1 claim about them currently rests
on a metric that doesn't measure them.

**Found**: re-deriving figures after the gold fixes, 2026-10-04 (`docs/GOLD_AUDIT_2026-10-03.md` §7.3).

**Suggested fix**: score each `except` as its own predicate (location `exception`, keyed on the parent
exclusion's field plus the exception's field/op/value/scope), so a missing or wrong exception
produces a false negative or false positive in its own right. That changes reported F1 figures, so
re-derive them alongside the change.

**Status**: Open as of 2026-10-04.

**Status**: **Resolved 2026-10-04.** Each exception is now its own predicate, paired through its exclusion and charged to an `exception_to_exclusion` category (the plan's C3 "exceptions-to-exclusions"); predicates are paired on (location, field), which also corrected a collision in one MH-LADKI-BAHIN draft. Re-run on all 7 schemes, with superseded figures listed: `docs/GOLD_AUDIT_2026-10-03.md` §7.8. AB-PMJAY's gate-approved draft now scores 0.692 (0/14 exceptions).

## [RESOLVED 2026-10-04] Structural F1 collapses two predicates on the same field in the same location

**Where**: `schemelogic/evaluation/structural_f1.py`, `_diff_location` / `compare_schemes` (pairing by `identity()`).

**What**: predicates are paired on (location, field), so two predicates on one field in the same place — a lower and an upper age bound (MH-LADKI-BAHIN; PMMVY's `age >= 18`, `age <= 55`, `age >= 19`) — collapse to the last one, and the others are never scored. Pre-existing (before 2026-10-04 the key was the field alone, which was worse). No figure on record involves PMMVY, which was never extracted; MH-LADKI-BAHIN's drafts carry both bounds too, so its figures count one bound pair instead of two.

**Status**: **Resolved 2026-10-04** — predicates are paired as multisets per (location, field): exact matches first, then the remainder as wrong values, leftovers missing or hallucinated. Only MH-LADKI-BAHIN's figures moved: ontology draft 0.769 → 0.786, judge+repair 0.786 → 0.800 (`docs/GOLD_AUDIT_2026-10-03.md` §7.8).

## [RESOLVED 2026-10-04] Question selector asks about branches that are already decided

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

**Status**: **Resolved 2026-10-04.** `find_missing_fields` descends only into undetermined nodes
(inclusion nodes, exclusions, member rows), so nothing under a decided branch is offered — exact when
each fact appears once. Where one fact feeds several rules (AB-PMJAY's age waives all 14 exclusions;
PM-KISAN's Group D carve-out sits on two), a fact can sit on an undetermined path and still be unable
to change the verdict, so `select_next_question` also proves relevance before asking: a deterministic
search over the other missing facts (values on each side of every threshold), pruned by the
evaluator's own definite verdicts. A brute-force oracle over every gold scheme (361 partial profiles)
confirms each question asked can change the verdict and that no fact that could is withheld. The
PMMVY sequence is now age → SC/ST → birth order (3 questions, was 12). Over simulated chats on every
gold profile, 15% fewer questions (452 → 383) with identical verdicts; the slowest turn took 19 ms.
One exception, by necessity: when the evaluator is undetermined only through the incompleteness in
"Kleene evaluation is incomplete…" above, no single answer can change the verdict, and the selector
asks the first candidate so the conversation can reach it. PMMVY's "precise floor placed LAST"
ordering workaround is no longer needed; it is harmless and was left in the gold as is, and that
`source_clause` remark about the selector is now historical (updated with a dated note, 2026-10-04).

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

## [RESOLVED 2026-10-03] Gold: IGNOAPS exclusions rest on an inference its author doubts, and on an out-of-scope clause

**Where**: `data/gold/IGNOAPS.json` exclusions.

**What**: `has_regular_family_financial_support` is built from the NSAP programme-wide *destitute*
definition (Para 1.1.1); the gold's own `source_clause` calls it "an interpretive elevation",
"philosophical/preambular framing" that "may already be subsumed by the BPL determination". Both of
Baseline 2's IGNOAPS harmful errors turn on it. The other three exclusions (government job, 5+ acres,
four-wheeler) appear verbatim only inside the §2.4.3 AIDS-widow carve-out — "except widows suffering
from AIDS who will be considered if they are not attracted by any of the exclusion criteria…" — but
the gold applies them to every applicant.

**Found**: gold sourcing audit, 2026-10-03.

**Status**: **Resolved 2026-10-03.** `has_regular_family_financial_support` removed. The three criteria now gate only the Para 2.4.3 AIDS-widow carve-out, which is modelled as an alternative to BPL status (new field `is_widow_suffering_from_aids`), after searching all three IGNOAPS sources and finding no text that applies them generally. **Decided 2026-10-04 — how the question is asked**: the carve-out stays modelled, and the HIV/AIDS fact is marked `sensitive` in the ontology. The chat asks it only when it is the one fact still deciding the verdict — after age, BPL status and the carve-out's three criteria, any of which can settle the verdict first — and only after a gentler screening question, "Are you a widow?", whose No settles it without asking. It offers "Prefer not to say": that answer is read deterministically (never by the router or the LLM answer parser, which could read a decline as "no"), leaves the fact unknown, and ends the check with "you may qualify under a special provision; please check with your local office" — never a verdict. Exhaustive check over every combination of the IGNOAPS facts: asked only of 60+, non-BPL widows clear of all three criteria, and always as the deciding fact. Record: `docs/GOLD_AUDIT_2026-10-03.md` §6.4.

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

## [RESOLVED 2026-10-04] Gold: PMAY-G exclusions — a primary source now contradicts the gold

**Where**: `data/gold/PMAY-G.json` exclusions.

**What**: logged originally as two questions — the source `.md` says exclusions were "reduced from 13
to 10 parameters" but lists 11, and identically worded "Households with…" clauses get
inconsistent quantifiers (`some_family_member` for govt employee, income and tax; `self` for
enterprise, assets and land).

The audit then found a primary-quality source that answers the first question:
`data/raw_documents/IGNOAPS_primary.pdf` is the whole **MoRD Annual Report 2024-25** — filed under
IGNOAPS because the IGNOAPS gold cites its NSAP pages — and it also states PMAY-G's revised criteria
directly (`docs/GOLD_AUDIT_2026-10-03.md` §4). Against it, the gold
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
report's wording. Worth also saving the PMAY-G pages under a PMAY-G name, so the next audit finds
them where it looks.

**Status**: **Resolved 2026-10-04.** The MoRD Annual Report 2024-25 is adopted for PMAY-G's exclusions: refrigerator and landline removed; professional tax and 5+ acres unirrigated added; irrigated land now `irrigated_land_acres >= 2.5`; the Step 1 pucca filter modelled as a pucca roof or wall, or more than 2 rooms (`docs/GOLD_AUDIT_2026-10-03.md` §6.8). Quantifiers already matched the report's wording. Still open: whether the exclusions apply to compulsory-inclusion households, and the inclusion side is still PIB-sourced.

**Follow-up done 2026-10-04**: the report's p.141 text was appended to `data/raw_documents/PMAY-G.md` and the draft and Baseline 2 re-run (`docs/GOLD_AUDIT_2026-10-03.md` §7.9): Baseline 2 100%; the new draft drops every harmful error but still keeps the deleted refrigerator and landline exclusions. The stale-document results are kept as a record.

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

## Judge: a supersession finding with no retired field rejects the whole report (fix after the review)

**Where**: `schemelogic/extraction/judge_repair.py` — `ProposedSupersedes.retired_field: str` (and
`retired_op`), validated by `JudgeReport.model_validate` in `run_judge`.

**What**: on the final-push retry of AB-PMJAY's pipeline run (2026-10-07, `reasoning_effort="low"`, after
two `json_validate_failed` attempts), the judge returned a complete report, but its first finding was a
`temporal_supersession` whose `proposed_supersedes.retired_field` and `retired_op` were `null`. The response
schema is sent with `strict: False`, so Groq accepted it; Pydantic then rejected the WHOLE report
(`schema_validation_failed`), discarding any valid findings alongside it. A supersession with nothing to
retire (AB-PMJAY's 70+ change is an addition, not a retirement) has no valid encoding today.
Record: `data/experiments/pipeline_on_sample1/AB-PMJAY.json` (all three attempts kept).

**Why deferred**: decided 2026-10-07 — no re-runs before the review; AB-PMJAY stays a failed run in
every report, with both causes stated (two attempts: prompt size against Groq's 8k per-request limit;
the third: this).

**Suggested fix**: validate findings one by one and report an invalid finding as such instead of failing
the report (only the bad finding is lost); and/or let the schema express "addition, nothing retired"
(e.g. a separate finding category, or a nullable `retired_*` with the gate deferring such findings). Add a
regression test with this exact payload shape, then re-run AB-PMJAY's judge call.

**Status**: Open as of 2026-10-07.
