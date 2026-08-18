# SchemeLogic — Implementation Plan & Project Context

**This document is the authoritative context for this project. Read it fully before writing any code.** It is intended to be handed to Claude Code (or any engineering collaborator) as the single source of truth for what we are building, why, and how.

---

## 1. Project Summary

**Title:** SchemeLogic — From Unstructured Welfare-Scheme Documents to Verifiable Eligibility Logic: A Neuro-Symbolic Benchmark and Pipeline for Indian Government Schemes

**Type:** B.Tech final-year research project (VIT, BITE497J), with a target academic paper as a stretch outcome.

**One-line pitch:** An LLM converts messy Indian government welfare-scheme documents into an auditable, executable eligibility-logic format; a deterministic symbolic engine (never the LLM) evaluates citizen eligibility against that logic, producing a full rule trace. We study where and how the extraction step fails.

**Why this matters (motivation):**
- India has 3,000+ central and state welfare schemes. Citizens routinely fail to discover benefits they qualify for.
- LLM chatbots that answer "am I eligible?" directly hallucinate criteria — a wrong "yes" wastes a citizen's time/money on a doomed application; a wrong "no" denies them a benefit they're owed.
- Eligibility logic is genuinely compositional: family-unit exclusions (one disqualified family member disqualifies the household), exceptions-to-exclusions (e.g., government employees excluded EXCEPT Group D/Class IV/MTS staff), cross-scheme mutual exclusivity, and time-varying criteria (schemes get amended).
- **The core design decision:** the LLM only ever extracts structured rules from text. It never decides eligibility. A deterministic symbolic engine evaluates the extracted rules against a citizen profile and returns a verdict with a full, auditable trace. This separation is the project's central safety/trust argument.

**What is NOT novel (be upfront about this in any writeup):** LLM-based extraction of executable rules from legal/regulatory text is an active subfield (Janatian et al. 2023, Zin et al. 2025, Singhal & Breaux 2025, "De Jure" 2026, "From Legal Text to Executable Decision Models" 2026). We are not claiming to invent this mechanism.

**What IS novel (the actual contributions, C1–C5):**
- **C1 — Domain & benchmark:** First gold-annotated, category-tagged eligibility-logic benchmark for Indian welfare schemes. Prior work targets US benefits, EU regulation, traffic law, data-breach law — nothing India-specific.
- **C2 — Cross-lingual rule extraction:** No prior work extracts executable rules from Indic-language policy documents or measures logical equivalence between rules extracted from parallel-language (e.g., Hindi vs. English) notifications of the same scheme.
- **C3 — Category-wise failure taxonomy:** Prior extraction papers report a single aggregate accuracy number. We break errors down by predicate category (demographic thresholds, compound boolean logic, family-unit quantification, exceptions-to-exclusions, cross-scheme exclusivity, temporal clauses, vacuous predicates).
- **C4 — Temporal robustness:** Schemes get amended (e.g., PM-KISAN's June 2019 extension from small/marginal farmers to all landholding families). We test whether re-extraction after an amendment correctly retires the superseded predicate, or silently keeps serving stale rules. This extends 2026 temporal-staleness literature from statutory QA into rule extraction/maintenance specifically.
- **C5 — Harm-weighted, deferral-aware evaluation:** We separate false-positive eligibility errors (wasted applications) from false-negative errors (denied benefits) and measure whether a confidence-based deferral mechanism actually catches the harmful errors before they reach a citizen.

---

## 2. The Eligibility-Logic Schema

Standard JSON Logic handles boolean/comparison logic but is insufficient for real Indian scheme criteria. We extend it with custom fields. **This schema is the backbone of the entire project — get this right first.**

### 2.1 Schema fields

- `scheme_id` — canonical scheme identifier
- `unit_of_eligibility` — `"individual"` | `"family"` (with quantifiers below)
- `inclusion` — nested AND/OR predicate tree (must ALL/ANY be satisfied to qualify)
- `exclusions` — list of predicates that disqualify; each can carry:
  - `quantifier`: `"self"` | `"some_family_member"` | `"all_family_members"` (handles family-unit logic)
  - `except`: a nested predicate representing an exception-to-the-exclusion (e.g., govt employee excluded EXCEPT Group D)
- `temporal_validity`:
  - `valid_from`, `valid_to` (legal validity interval of this rule version)
  - `extracted_at` (when the LLM extracted this version — NOT the same as legal validity)
  - `supersedes`: pointer to the prior rule version + what predicate was retired + the amendment source document
- `operational_requirements` — non-eligibility prerequisites (e.g., Aadhaar-seeded bank account, e-KYC)
- `extraction_metadata`:
  - `confidence` — self-consistency score across k sampled extractions
  - `source_clause` — pointer to the specific clause/section in the source document
  - `flagged_for_review` — boolean, set by the calibration gate

Each predicate carries a `cat` (category) tag. This tagging is what powers the failure taxonomy (C3).

### 2.2 Worked example (PM-KISAN, reference implementation target)

```json
{
  "scheme_id": "PM-KISAN",
  "unit_of_eligibility": "family",
  "inclusion": {
    "and": [
      { "cat": "citizenship", "field": "is_indian_citizen", "op": "==", "value": true },
      { "cat": "occupation", "field": "owns_cultivable_land_in_records", "op": "==", "value": true }
    ]
  },
  "exclusions": [
    {
      "cat": "economic", "quantifier": "some_family_member",
      "field": "paid_income_tax_last_assessment_year", "op": "==", "value": true
    },
    {
      "cat": "occupation", "quantifier": "some_family_member",
      "field": "is_serving_or_retired_govt_employee", "op": "==", "value": true,
      "except": { "field": "is_group_d_class_iv_or_mts", "op": "==", "value": true }
    },
    {
      "cat": "economic", "quantifier": "some_family_member",
      "field": "monthly_pension_inr", "op": ">=", "value": 10000,
      "except": { "field": "is_group_d_class_iv_or_mts", "op": "==", "value": true }
    },
    {
      "cat": "political", "quantifier": "some_family_member",
      "field": "holds_constitutional_or_political_post", "op": "==", "value": true
    },
    {
      "cat": "professional", "quantifier": "some_family_member",
      "field": "is_practicing_registered_professional", "op": "==", "value": true
    },
    {
      "cat": "institutional", "field": "is_institutional_landholder", "op": "==", "value": true
    }
  ],
  "temporal_validity": {
    "valid_from": "2019-06-01", "valid_to": null,
    "extracted_at": "2026-07-17",
    "supersedes": {
      "rule_version": "v1",
      "retired_predicate": { "field": "landholding_hectares", "op": "<=", "value": 2 },
      "amendment_source": "cabinet_decision_2019_06.pdf"
    }
  },
  "operational_requirements": ["aadhaar_seeded_bank_account", "ekyc_completed"],
  "extraction_metadata": {
    "confidence": 0.80,
    "source_clause": "Operational Guidelines Sec. 4",
    "flagged_for_review": false
  }
}
```

### 2.3 Verdict semantics

Verdicts are **three-valued**: `eligible` | `ineligible` | `undetermined_missing_facts`. The third value matters — it's what enables the conversational layer to intelligently ask only the questions still needed (information-gain-based next-question selection), rather than a rigid form.

---

## 3. System Architecture

```
Scheme PDF / notification (English or Indic language)
   │
   ▼
[Ingestion & normalization] — PDF/HTML → clean Markdown, language detection
   │
   ▼
[RAG retrieval layer] — fetches cross-referenced documents (amendment orders,
   │                     related schemes) with temporal version filtering
   ▼
[LLM extraction] — prose clause → extended JSON Logic predicate,
   │                self-consistency confidence computed over k samples
   ▼
[LLM judge + selective repair] — schema validity + internal consistency checks;
   │                              failing extractions are regenerated (bounded budget)
   ▼
[Calibration / deferral gate] — low-confidence rules routed to a human
   │                             reviewer before entering the live rule set
   ▼
[Symbolic evaluator] — deterministic rule engine; three-valued verdicts
   │                    with full auditable rule trace; drives next-question selection
   ▼
[Conversational layer] — citizen-facing chat/form UI, asks only what's still needed
   │
   ▼
[Evaluation harness — offline only] — per-category structural F1, outcome
                                        equivalence, cross-lingual consistency,
                                        temporal-drift measurement, deferral curves
```

**Non-negotiable design rule:** the LLM (in any stage) never outputs an eligibility verdict directly. Only the symbolic evaluator produces verdicts, and every verdict must carry a rule trace (which predicates were checked, in what order, with what values).

---

## 4. Repository Structure (target)

```
schemelogic/
├── IMPLEMENTATION_PLAN.md          # this file
├── README.md
├── pyproject.toml / requirements.txt
├── schemelogic/
│   ├── schema/
│   │   ├── models.py               # Pydantic models for the extended JSON Logic schema
│   │   └── validate.py             # schema validation utilities
│   ├── ingestion/
│   │   ├── pdf_to_markdown.py
│   │   ├── scraper_myscheme.py     # myScheme.gov.in scraper (respect robots.txt/rate limits)
│   │   └── language_detect.py
│   ├── retrieval/
│   │   ├── indexer.py              # embeds + indexes cross-referenced docs
│   │   └── temporal_filter.py      # version-aware retrieval
│   ├── extraction/
│   │   ├── extractor.py            # LLM extraction, structured output
│   │   ├── self_consistency.py     # k-sample confidence scoring
│   │   └── judge_repair.py         # LLM-as-judge + bounded repair loop
│   ├── evaluator/
│   │   ├── symbolic_engine.py      # deterministic rule evaluator, THE core module
│   │   ├── family_quantifiers.py   # some/all/none family-unit logic
│   │   └── trace.py                # rule trace construction
│   ├── deferral/
│   │   └── calibration_gate.py     # confidence-based human-review routing
│   ├── conversational/
│   │   └── question_selector.py    # info-gain next-question logic
│   ├── evaluation/
│   │   ├── structural_f1.py        # per-category predicate P/R/F1
│   │   ├── outcome_equivalence.py  # profile-suite behavioral testing
│   │   ├── cross_lingual.py        # logical-equivalence rate between language pairs
│   │   ├── temporal_drift.py       # superseded-predicate retention rate
│   │   └── deferral_curves.py      # precision-recall of confidence flagging
│   └── demo/
│       └── streamlit_app.py        # conversational eligibility checker demo
├── data/
│   ├── gold/                       # hand-annotated schemes (the benchmark)
│   ├── silver/                     # myScheme structured fields, noisy labels
│   ├── temporal/                   # pre/post-amendment paired annotations
│   ├── multilingual/               # parallel Indic/English notification pairs
│   ├── profiles/                   # synthetic citizen test profiles per scheme
│   └── raw_documents/              # scraped/collected source PDFs (gitignored, large)
├── annotation/
│   ├── guidelines.md               # annotation guidelines for gold set
│   └── label_studio_config.xml     # or spreadsheet template
├── notebooks/                      # exploratory analysis, error inspection
├── tests/
│   ├── test_symbolic_engine.py     # THIS MUST BE THOROUGH — it's the safety-critical module
│   ├── test_schema_validation.py
│   └── test_extraction_pipeline.py
└── paper/                          # LaTeX/writeup source, if pursuing publication
```

---

## 5. Technology Stack

- **Language:** Python 3.11+
- **Structured LLM output:** `instructor` or `outlines` (enforce schema-valid JSON from the LLM)
- **LLM access:** two tracks, used deliberately for different purposes — see Section 5.1 below for full detail.
- **Rule engine:** custom Python evaluator built on top of `json-logic-js`-style semantics — standard JSON Logic libraries will NOT support the quantifier/exception extensions, so this needs to be hand-written (this is fine and expected — it's a small, testable module)
- **Retrieval:** `FAISS` or `Qdrant` for vector search; `BGE-M3` or similar for multilingual embeddings
- **Multilingual:** `AI4Bharat/IndicTrans2` for translation where needed
- **PDF/document processing:** `PyMuPDF` (fitz) or `unstructured` for PDF→Markdown
- **Annotation:** Label Studio (self-hosted) or a structured spreadsheet (Google Sheets/Excel with strict schema validation) — pick based on team comfort; spreadsheet is faster to start with for a 3-person team
- **Demo front end:** Streamlit
- **Testing:** `pytest`, with especially thorough coverage on the symbolic evaluator
- **Experiment tracking:** simple CSV/JSON logs are fine at this scale; don't over-engineer with MLflow/W&B unless it becomes genuinely useful

---

### 5.1 Which LLM(s), and how you access them

**Team has Groq API access (GROQ_API_KEY) — this is the primary/default LLM backend for this project.** Groq serves open-weight models (not its own model — it's an inference provider) at very high speed and low cost, OpenAI-SDK-compatible at `https://api.groq.com/openai/v1`, so switching models is a one-line string change.

**Important — Groq's model lineup changes; verify current model IDs before hardcoding them.** As of this plan being written, Groq has **deprecated** `llama-3.3-70b-versatile` and `llama-3.1-8b-instant` — do not use these even if you see them in older tutorials/blog posts, they may be shut down. Current recommended models on Groq:
- `openai/gpt-oss-120b` — OpenAI's larger open-weight model, Groq's current flagship general-purpose/reasoning recommendation. **Use this as Track A (draft extraction quality / annotation-assist).**
- `openai/gpt-oss-20b` — smaller/faster sibling of the above.
- `moonshotai/kimi-k2-instruct-0905` — notable because Groq explicitly documents **strict structured-output support (`json_schema` mode with constrained decoding)** for this model, which is exactly what you need for schema-conformant extraction. Worth benchmarking against gpt-oss-120b for Track A.
- `qwen/qwen3-32b` — reasoning model, also documented with strong structured-output support.
- `meta-llama/llama-4-scout-17b-16e-instruct` — supports vision, only relevant if you end up needing to read scanned/image PDFs directly.

Before writing any code, have Claude Code run `groq.models.list()` (or `GET https://api.groq.com/openai/v1/models`) to pull the live, current model list — don't trust any hardcoded list (including this one) as ground truth by the time you're actually building.

**Structured output:** Groq supports `json_schema`-mode structured outputs natively on newer models (confirmed for `kimi-k2-instruct-0905`; check current docs for others) with constrained decoding, which can mean you don't need `instructor`/`outlines` as a wrapper at all for those models — plain Groq SDK calls with `response_format={"type": "json_schema", ...}` may be sufficient. Still worth using `instructor` or `outlines` as a fallback/validation layer for models where native structured output isn't guaranteed, or to keep the code path uniform across models.

**Track A vs. Track B, entirely within Groq:** since Groq hosts multiple models at different capability tiers, you can run your "strong model vs. weak model" ablation (the comparison your paper needs, per Section 7's baselines) entirely on Groq without needing a separate paid API — e.g., `gpt-oss-120b` (or `kimi-k2-instruct-0905`) as your main extraction model, `gpt-oss-20b` as the smaller/cheaper comparison point. This is a real, defensible ablation for the paper (frontier open model vs. smaller open model), not a compromise.

**If you later want a closed-frontier-model comparison** (e.g., Claude or GPT-4 proper, not open-weight) for a stronger "best possible extraction quality" reference point, that would need a separate API key from Anthropic or OpenAI — not required to start, but worth keeping as a possible Phase 3+ addition if reviewers/your guide ask "how does this compare to a top-tier closed model," since that's a predictable question given the LLM-extraction literature you're positioning against (Janatian et al. and others used GPT-4).

**Practical operational notes for Claude Code:**
- Check Groq's current rate limits and free-tier quotas at console.groq.com before planning Phase 3+ volume — self-consistency sampling (k=5 samples × 100–150 schemes × repeated ablation runs) adds up in request count even though Groq is cheap/fast, and free tiers typically cap requests-per-minute and requests-per-day.
- Groq offers a **Batch Processing** tier for bulk async jobs at a discount — worth using once you're running extraction across the full gold set repeatedly, rather than hammering the on-demand endpoint.
- Store `GROQ_API_KEY` in a `.env` file (gitignored), never hardcoded or committed.

---

## 6. Dataset Plan

- **Gold set (100–150 schemes):** sampled from myScheme + ministry/state notifications, stratified by central vs. state origin and logic complexity (simple vs. compositional). Dual-annotated with adjudication. Report inter-annotator agreement (Cohen's kappa or similar). Every predicate: category tag, source-clause pointer, verifiability tag (self-declared vs. document-verifiable).
- **Silver set:** myScheme's own structured eligibility fields for 4,000+ schemes, used as noisy labels to scale evaluation beyond the gold set (NOT for training — myScheme's rules are hand-curated by humans and treated as a weak reference, not ground truth for our extraction-faithfulness claims).
- **Temporal subset (20–30 schemes):** documented amendment histories, annotated with pre- and post-amendment rule versions, for the staleness experiments (C4).
- **Multilingual subset (30–40 schemes):** notifications that exist in both an Indian language and English, for cross-lingual consistency experiments (C2).
- **Profile test suites:** synthetic citizen profiles per scheme, including deliberately adversarial boundary cases (income exactly at a threshold, family-member exclusion edge cases), for outcome-equivalence evaluation.

**Annotation guidance for whoever builds the gold set:** write out the annotation guidelines (`annotation/guidelines.md`) BEFORE annotating more than 5–10 schemes. Do a calibration round with the whole team on the same 5 schemes first, compare, resolve disagreements, THEN annotate independently at scale. This avoids having to re-annotate everything later.

---

## 6.5 Annotation Workflow: LLM-Draft-Then-Human-Verify

**Why this matters:** the gold set is the ground truth the entire project measures against. If it is not genuinely human-verified, the evaluation collapses — there is nothing trustworthy left to compare LLM extractions to. At the same time, annotating 100+ schemes from a blank page is slow. The solution is a draft-then-verify pipeline where the LLM accelerates annotation but a human always has final sign-off.

### 6.5.1 Workflow

```
Raw scheme document (prose)
   │
   ▼
[Draft extraction] — same extractor as the pipeline (extraction/extractor.py)
   │                  produces a first-pass schema-conformant JSON
   ▼
[Annotator review] — human opens draft + source document side by side,
   │                  corrects every field, cannot approve without reading
   │                  the actual source clause for each predicate
   ▼
[Second annotator / adjudication] — independent check on a sample (or all,
   │                                for the initial calibration round);
   │                                disagreements resolved by discussion
   ▼
Gold-set entry (data/gold/<scheme_id>.json) + annotation log
```

**Critical rule:** the draft extraction must never be silently accepted. Build the review tool so that every predicate requires an explicit annotator action (confirm / edit / delete / add) before a scheme can be marked "gold." A tool that lets someone click "approve all" without touching each predicate defeats the purpose.

### 6.5.2 Annotation review tool (build this in Phase 0, alongside the evaluator)

A lightweight tool — a Streamlit app is enough, doesn't need to be Label Studio — that for each scheme shows:
- The source document (or the relevant extracted clause) on one side
- The LLM's draft JSON Logic extraction on the other, rendered human-readably (not raw JSON — render the predicate tree as readable English-ish statements, e.g., "EXCLUDE if some family member paid income tax last year")
- Inline edit controls per predicate: confirm / edit value / edit category / delete / add new predicate
- A mandatory `source_clause` pointer field the annotator must fill or confirm for every predicate (forces them to actually locate it in the source, not just eyeball plausibility)
- A free-text "annotator notes" field for ambiguous cases, logged for later failure-taxonomy discussion
- On save: write to `data/gold/<scheme_id>.json`, log annotator ID + timestamp + edit count (edit count is a useful proxy for how far off the draft was — feed this into your Phase 3 analysis)

### 6.5.3 Calibration round (do this before scaling up)

Before annotating at volume, all three team members independently annotate the **same 5 schemes** (start with PM-KISAN plus 4 others of varying complexity). Compare results as a group:
- Where did you disagree, and why? (ambiguous source wording vs. genuine misunderstanding of the schema vs. tool UX confusion)
- Update `annotation/guidelines.md` with concrete resolved examples for each disagreement type
- Only after this calibration round should annotation proceed independently at scale

### 6.5.4 Ongoing quality control

- Dual-annotate a random 15–20% sample of the gold set throughout (not just the calibration round) and report inter-annotator agreement (Cohen's kappa per category) — this number goes directly into your paper as evidence of gold-set reliability
- Track edit count and annotation time per scheme; flag schemes with unusually high edit counts for a second look — the draft may have hit a genuinely hard case worth featuring in the failure taxonomy
- Weekly spot-check: guide or most experienced annotator reviews a handful of completed entries against source documents

### 6.5.5 Division of labor implication

This workflow is what makes the earlier scope estimate (Section on dataset realism) tractable — draft-then-verify is meaningfully faster than blank-page annotation, but still requires real per-scheme human time (expect roughly 15–30 minutes of careful review per scheme once a draft exists, more for high-complexity schemes). Build the review tool early; it will be used continuously from Phase 0 through Phase 3.

---

## 7. Evaluation Metrics (map directly to objectives O1–O5)

- **Structural (O1, O2):** per-predicate precision/recall/F1, broken down by category. Schema-validity rate (does the LLM even produce parseable schema-conformant output).
- **Behavioural (O1):** verdict agreement between LLM-extracted rules and gold rules, evaluated by running BOTH through the identical symbolic evaluator over the profile test suites. Report false-positive eligibility rate and false-negative eligibility rate SEPARATELY (harm-weighted — this is O4/C5, don't collapse them into one accuracy number).
- **Cross-lingual (O5):** logical-equivalence rate between rule-sets extracted from parallel Indic-language vs. English notifications of the same scheme.
- **Temporal (O3):** superseded-predicate retention rate — after feeding the pipeline a post-amendment document, does it still contain the pre-amendment predicate it should have retired?
- **Deferral (O4):** precision-recall curve of the confidence-based flagging mechanism against actually-harmful errors; expected calibration error (ECE).
- **Baselines to compare against:**
  1. Flat attribute extraction (simple slot-filling, no compositional logic) — shows why the compositional schema matters
  2. Direct-LLM eligibility answering (ask the LLM "is this person eligible?" with no symbolic layer) — shows why the neuro-symbolic separation matters, this is your key baseline for the "trust problem" motivation
  3. Extraction pipeline WITHOUT the judge/repair loop — ablation showing the repair loop's contribution

---

## 8. Build Order / Phased Plan

Build in this order. Each phase should produce something runnable and testable before moving to the next — don't build the whole pipeline unintegrated and hope it works at the end.

### Phase 0 — Foundations (do this first, it de-risks everything else)
1. Implement the Pydantic schema models (`schema/models.py`) exactly matching Section 2.
2. Implement the **symbolic evaluator** (`evaluator/symbolic_engine.py`) — pure Python, no LLM involved. Given a schema-conformant rule JSON + a citizen profile dict, return a three-valued verdict + rule trace. Handle: nested AND/OR, quantifiers (self/some_family_member/all_family_members), exception clauses, missing-fact detection (→ `undetermined_missing_facts`).
3. Write thorough unit tests for the evaluator FIRST, including edge cases: all family members must be checked for `some_family_member` exclusions with exceptions applied per-member; missing fields should produce `undetermined`, not silently default to false.
4. Hand-write 5–8 gold scheme JSONs (start with PM-KISAN from Section 2.2, add a few state schemes with real compositional logic) and confirm the evaluator produces correct verdicts on hand-constructed test profiles for each.

**Why this order:** the symbolic evaluator is the safety-critical, easiest-to-get-fully-correct component, and it's needed to run ANY evaluation later (both gold-vs-gold sanity checks and LLM-extracted-vs-gold comparisons run through the same evaluator). Get it right and well-tested before building anything that depends on it.

### Phase 1 — Extraction pipeline (single-pass, no RAG/repair yet)
1. Document ingestion: PDF/HTML → clean Markdown.
2. LLM extraction: structured-output prompt that takes a scheme document (Markdown) and produces schema-conformant JSON. Use `instructor`/`outlines` to enforce this.
3. Run extraction on your Phase-0 gold schemes; compare LLM output to gold by hand. Log concrete failure examples — this is your first real empirical evidence for the project's motivation ("compositional logic — quantifiers, exceptions — is where extraction breaks").
4. Implement self-consistency confidence: sample k=5 extractions per scheme, measure agreement, produce a `confidence` score.

### Phase 2 — Judge/repair + calibration gate
1. LLM-as-judge: given an extraction + source clause, score schema validity and internal consistency; flag issues.
2. Bounded repair loop: regenerate only the flagged predicates, not the whole extraction, within a small iteration budget.
3. Calibration gate: route low-confidence extractions to a "needs human review" queue instead of silently entering the live rule set.

### Phase 3 — Structural + behavioural evaluation harness
1. `evaluation/structural_f1.py`: per-category precision/recall/F1 against gold.
2. `evaluation/outcome_equivalence.py`: run both gold and LLM-extracted rules through the symbolic evaluator over your profile test suites; compute agreement, split into false-positive/false-negative eligibility rates.
3. Scale up gold annotation toward 100–150 schemes in parallel with this (this is the most time-consuming, non-code-heavy task — plan team bandwidth accordingly, it can run concurrently with engineering work).

### Phase 4 — RAG retrieval layer
1. Index amendment orders and cross-referenced documents.
2. Temporal version filtering: given an "as of" date, retrieve the correct version of a referenced rule.
3. Integrate into the extraction pipeline (Phase 1 extraction now has access to retrieved context).

### Phase 5 — Temporal-drift experiments (C4)
1. Build the temporal subset (20–30 schemes with amendment history).
2. Run extraction on pre- and post-amendment source documents.
3. Measure superseded-predicate retention rate.

### Phase 6 — Cross-lingual experiments (C2)
1. Build the multilingual subset (30–40 schemes with parallel Indic/English notifications).
2. Run extraction independently on each language version.
3. Measure logical-equivalence rate (this needs a well-defined equivalence check — likely: run both rule-sets through the symbolic evaluator over the same profile suite and compare verdicts, rather than trying to diff the JSON structures directly, since structurally different-but-equivalent rules are expected).

### Phase 7 — Deferral evaluation (O4/C5)
1. Deliberately inject/collect known-harmful extraction errors (from your accumulated failure examples).
2. Measure whether the confidence gate catches them — precision-recall curve, ECE.

### Phase 8 — Conversational demo + baselines
1. Streamlit app: citizen answers questions (info-gain-selected), gets verdict + trace, for a handful of demo schemes.
2. Implement and run the three baselines (flat extraction, direct-LLM-answering, no-repair-loop ablation) for comparison tables.

### Phase 9 — Write-up
1. Consolidate all evaluation results into tables/figures.
2. Draft paper targeting ACM COMPASS / NLLP workshop / ICEGOV / JURIX / an IEEE or Springer Scopus-indexed venue, with journal extension target: *Artificial Intelligence and Law* (Springer).

---

## 9. Key Engineering Principles for Claude Code to Follow

1. **Never let the LLM output an eligibility verdict.** If you're implementing any code path where an LLM's output is used directly as `eligible`/`ineligible` without going through `evaluator/symbolic_engine.py`, stop — that violates the core design principle and defeats the point of the project.
2. **The symbolic evaluator must be deterministic and fully unit-tested before anything else depends on it.** Treat it like safety-critical code, because the whole trust argument of the paper rests on it being correct.
3. **Every verdict must carry a rule trace** — which predicates were evaluated, their values, and how they combined to produce the verdict. This is required for the "auditable" claim.
4. **Missing facts should produce `undetermined_missing_facts`, never a silent default.** Defaulting missing family-member data to "false" (i.e., assuming no disqualifying condition) is exactly the kind of silent failure mode this project is trying to prevent — don't reproduce it in the implementation.
5. **Keep category tags (`cat`) consistent and controlled** — define the category vocabulary once (e.g., in `schema/models.py` as an enum) and don't let it drift, since the entire failure-taxonomy analysis depends on consistent tagging.
6. **Log everything needed for the failure taxonomy as you go** — don't just log pass/fail on extraction; log which category of predicate failed and how, from Phase 1 onward, even before the formal evaluation harness exists in Phase 3. Retrofitting this later means re-running extraction on everything.
7. **Respect scraping etiquette** on myScheme.gov.in and ministry sites (rate limits, robots.txt, caching downloaded documents locally rather than re-fetching).
8. **Don't over-build the RAG/retrieval layer (Phase 4) before Phases 0–3 are solid.** It's tempting to build the "impressive" parts first, but the evaluator and extraction-vs-gold comparison are what actually generate your results.

---

## 10. Immediate Next Steps (start here)

1. Set up the repo structure from Section 4.
2. Implement `schema/models.py` (Pydantic models matching Section 2).
3. Implement and thoroughly test `evaluator/symbolic_engine.py` against the PM-KISAN example (Section 2.2) plus hand-constructed test profiles covering: a clearly eligible family, a clearly ineligible family (income-tax-paying member), an exception case (Group D government employee — should NOT be excluded), and a missing-data case (should return `undetermined_missing_facts`, not a false verdict).
4. Once the evaluator is solid, hand-annotate 5–8 real schemes and confirm correct behavior end-to-end (JSON → evaluator → correct verdict on constructed profiles).
5. Only then move to Phase 1 (LLM extraction).
