# Batch report — all gold schemes

*Generated 2026-10-05T14:37:10 by `scripts/run_batch_report.py` from code `14d17f9`, against frozen gold `gold-v2` (`82436ac`). Offline: no LLM calls. Regenerate rather than edit.*

## Caveats — read first

1. ONTOLOGY CONTAMINATION. The field ontology the extractor is constrained to was built from these same 7 gold schemes (each field lists the schemes it was made for), and the extraction prompt names those fields. Field-name agreement with gold is therefore optimistic: a structural F1 here measures extraction into a vocabulary designed around the answer, not open-world extraction. The AI-Checked tier (schemes outside the gold set) is the only evidence on unseen schemes.
2. SYNTHETIC PROFILES. The profile suites were written by the gold annotator to exercise the rules they encoded, so outcome equivalence tests the scenarios someone already thought of. A rule nobody wrote a profile for cannot disagree.
3. SMALL SAMPLES. 7 schemes, 8-14 profiles each. One profile moves a scheme's rate by 7-12 points; directions are more trustworthy than magnitudes.
4. SHARED SOURCES. Gold, drafts and the direct-LLM baseline mostly read the same source documents. Agreement can mean they share a source's error (the PMAY-G stale-document case, audit doc s7.9).
5. FROZEN GOLD. Everything is scored against tag gold-v2. Open findings of the 2026-10-04 independent gold review are part of that gold, unfixed; a draft that 'disagrees' may be right.

## phase3_pipeline

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

## baseline3_extraction_only

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

## pipeline_on_sample1

Full pipeline (judge -> gate -> apply approved) on the same extraction as Baseline 3.

*No results yet (absent for all 7 schemes).*

## baseline1_flat

Baseline 1: flat attribute extraction, no compositional logic.

*No results yet (absent for all 7 schemes).*

## Baseline 2 — direct LLM answering, re-scored against frozen gold

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

## Superseded claims (from the audit doc, s7.4) — do not cite the left column

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
