# Silver-Set Coverage & Quality Report

Generated 2026-08-18, against `data/silver/schemes.jsonl` (2066 records). Pure characterization
of what the scrape actually produced — no per-scheme verification, no gold comparison (silver
records were never routed through extraction/judge/gate; there's nothing to diff them against).

Source: `shrijayan/gov_myscheme` on Hugging Face (Apache-2.0), reused rather than re-scraping
myscheme.gov.in from scratch. See `schemelogic/ingestion/silver_scraper.py`'s module docstring for
why (README overstates what's in the repo — no ready CSV/JSON/Parquet actually exists, only 2067
raw per-scheme PDF page-captures after content-hash dedup).

## Headline numbers

| Metric | Value |
|---|---|
| Files listed (unique by content hash) | 2067 |
| Successfully parsed | 2066 |
| Parse failures | 1 (`text_data/test` — an empty placeholder file left in the source repo, not a real scheme) |
| Records with a `parse_warning` (unrecognized page shape) | 0 |
| Records with an Exclusions tab | 412 / 2066 (19.9%) |
| Scheme-name collisions across different slugs | 0 (content-hash dedup was clean) |

## 1. Field completeness

Overall, and broken down by region (state/UT vs. central — see "Region classification" note below):

| Field | Overall | State/UT (n=1531) | Central/Other (n=515) | Unknown region (n=20) |
|---|---|---|---|---|
| `scheme_name` | 100.0% | 100.0% | 100.0% | 100.0% |
| `description` | 100.0% | 100.0% | 100.0% | 100.0% |
| `eligibility_text` | 100.0% | 100.0% | 100.0% | 100.0% |
| `benefits_text` | 100.0% | 100.0% | 100.0% | 100.0% |
| `application_process_text` | 99.9% (2064/2066) | 99.9% | 99.8% | 100.0% |

**This is suspiciously clean, and I checked it wasn't a bug before trusting it**: verified via
length-distribution sanity checks (below) rather than just trusting the boolean presence check.
It holds up — myScheme's page template is extremely consistent, and the parser's sequential
"Check Eligibility → Details → Benefits → Eligibility → …" anchor search reliably finds every
section on nearly every page. Two genuine misses in `application_process_text` out of 2066, not a
parsing failure pattern.

No meaningful difference between state/UT and central schemes — coverage is uniform. The category
breakdown genuinely doesn't change the completeness picture; it matters more for the mojibake
numbers below.

**Region classification** (`classify_region()`): built from a new `ministry_or_state` field
(extracted from the text between the "Check Eligibility" button label and the repeated scheme
name), matched against a plain list of India's 28 states + 8 UTs. 1531 state/UT, 515
central/other, 20 unclassifiable (the ministry/state label itself wasn't found — same 20 records,
1.0%). This is a rough proxy, not an authoritative classification — a central scheme whose label
happens to be a bare state name would misclassify, though none were spot-checked for this
specifically.

## 2. Mojibake prevalence — the real headline finding

**Not a minor cosmetic issue — it affects the large majority of records.** Two distinct,
independent corruption patterns exist in the source PDFs (both are font-CMap bugs in myScheme's
own page-capture process, not something this parser or a different PDF library would fix):

1. **`â`-prefixed sequences** (curly quotes, em-dashes, bullets, the ₹ sign each decode as 2-3
   garbled codepoints starting with U+00E2): **1751 / 2066 records (84.8%)** have at least one
   field affected.
2. **Stray BOM artifacts** (`ï»¿`, a leaked byte-order-mark, usually appearing mid-sentence where
   the original page had some special character): **1566 / 2066 records (75.8%)**.

**Combined — either pattern present — 2000 / 2066 records (96.8%).** Only 66 records (3.2%) are
completely clean of both.

By field, for the `â`-prefixed pattern specifically:

| Field | Records affected | % of all records |
|---|---|---|
| `benefits_text` | 1395 | 67.5% |
| `description` | 1140 | 55.2% |
| `application_process_text` | 655 | 31.7% |
| `eligibility_text` | 531 | 25.7% |
| `scheme_name` | 72 | 3.5% |

Clusters exactly where you'd expect: `benefits_text` is worst because it's the field most likely
to quote a ₹ amount; `eligibility_text` is comparatively cleanest since criteria language uses
fewer curly quotes/currency symbols. `scheme_name` is nearly clean (3.5%) since most scheme names
don't contain special punctuation.

**Important**: numeric digits themselves are never affected — only the surrounding
symbol/punctuation glyphs. A ₹ amount like "₹6.25 lakhs" renders as "â‚¹6.25 lakhs" (garbled
symbol, correct number), not as a corrupted numeral.

## 3. Other data-quality issues found

- **Length distributions are healthy overall** (chars, populated values only):

  | Field | min | p10 | median | p90 | max |
  |---|---|---|---|---|---|
  | `scheme_name` | 5 | 22 | 46 | 93 | 246 |
  | `description` | 19 | 349 | 668 | 1832 | 8611 |
  | `eligibility_text` | 3 | 164 | 502 | 1531 | 11294 |
  | `benefits_text` | 8 | 82 | 359 | 1483 | 16927 |
  | `application_process_text` | 7 | 315 | 960 | 2184 | 11479 |

  Only 2 records (out of 2066×5 ≈ 10,330 field values) fall under a 15-character "suspiciously
  short" threshold — see examples below. This is a real, small edge case, not a systematic gap.

- **Eligibility text can end up empty despite the scheme genuinely being described elsewhere.**
  One concrete case (`cmacs`, see below): `eligibility_text` is just a bare BOM artifact, while
  the actual eligibility criteria (Rajasthan resident, SC/ST/OBC/MBC/EWS categories) sit inside
  `description` instead. This looks like a real authoring inconsistency on myScheme's own page for
  this scheme (content in the wrong tab), not a parser miss — the anchor-based section split is
  working correctly, the source page's own content placement is just inconsistent for this one.

- **No duplicate-looking-but-distinct entries survived the content-hash dedup.** Checked by
  grouping records with identical `scheme_name` across different slugs — zero collisions. The
  content-hash dedup step (described in the module docstring) appears to have fully eliminated the
  file-naming-variant duplicates found in the raw HF repo.

- **Official links check out.** `official_link` is constructed from the filename slug
  (`https://www.myscheme.gov.in/schemes/{slug}`), not literally present in the captured page text
  — this is a derived field, not scraped. Spot-checked 20 (5 hand-picked + 15 random) live via
  HTTP: **20/20 returned 200 OK.** Caveat: myScheme is a single-page app, so a 200 doesn't
  strictly guarantee the page renders the right scheme client-side (vs. a generic shell) — not
  checked at that depth, but the consistent 100% hit rate across a random sample is a good sign
  the slug-to-URL mapping is correct.

- **`Exclusions` tab presence (412/2066, 19.9%) is a real signal, not a parsing gap** — most
  schemes genuinely don't have a distinct automatic-exclusion list on myScheme; this isn't a case
  of the parser failing to find a section that's actually there (confirmed via the sample
  inspection during development: schemes without the tab in the nav-label list also don't have
  exclusion content anywhere in the body text).

## 4. Example records

**Good (central, clean of the `â` pattern, minor BOM artifacts only)** — `acandabc`, Agri-Clinics
And Agri-Business Centres Scheme, Ministry of Agriculture and Farmers' Welfare:
- `eligibility_text` (502 chars): "The age of the applicant must be between 18 and 60 years. The
  applicant must qualify as one of the following - Graduates in agriculture and allied subjects
  from SAUs/ Central Agricultural Universities... [full list of 6 qualification categories]"
- `benefits_text`: full description of Agri-Clinics and Agri-Business Centres services, financial
  support structure, project activity list.
- Clean, complete, well-separated — represents the parser working as intended.

**Typical/representative (state, includes the common mojibake pattern — shown as-is, not
cherry-picked clean, since ~97% of records look like this)** — `25-ciss`, 25% Capital Investment
Subsidy Scheme, Lakshadweep:
- `eligibility_text`: "Any individual above 18 years of age including Women, ex-servicemen &
  physically handicapped is eligible to apply under the scheme... Micro Enterprises/Units, where
  the investment in Plant & Machinery and Building below **â‚¹**25.00 Lakhs is only eligible..."
  — note the garbled ₹ symbol, everything else intact and usable.
- Has a genuine Negative List of Activities section folded into eligibility (SC/ST-style
  exclusion-adjacent content).

**Bad — empty eligibility despite real criteria existing** — `cmacs`, CM Anuprati Coaching Scheme
(Rajasthan):
- `eligibility_text`: `"﻿"` (literally just the BOM artifact — empty).
- `description` (has the real eligibility info instead): "...The scheme is open to students who
  are residents of Rajasthan and belong to SC, ST, OBC, MBC, and EWS categories. The eligibility
  criteria may vary based on the exam for which coaching is sought."
- A real gap: a naive consumer reading only `eligibility_text` would think this scheme has no
  stated eligibility criteria at all.

**Short but not broken** — `ltas`, Labor Tool Assistance Scheme (Chhattisgarh): `benefits_text` is
simply `"Tool kit"` — terse, but genuine, matching the scheme's actual (small) benefit.

## 5. Recommendation

**Not presentable to an end user as-is.** The mojibake prevalence (96.8% combined) is the blocker
— not because the underlying information is wrong, but because a scheme description or benefits
line reading "**â‚¹**6.25 lakhs" or "the â€œNo industrial Areaâ€​" reads as broken/untrustworthy to
a real user, even though every fact in it is intact. For an internal discovery/demo layer
(scheme name + description + benefits) this would need a cleanup pass first.

**The cleanup itself looks cheap, though not risk-free.** Both corruption patterns are
mechanical and highly consistent (same handful of codepoint sequences recur across records, not
one-off randomness), so a regex/lookup-table pass mapping the known broken sequences back to their
intended characters (curly quotes, em-dash, ₹, BOM-strip) should recover the large majority of
cases without needing OCR or a different PDF library. Rough estimate: **a few hours** — build a
small mapping table from a sample of ~30-50 observed sequences (already have several confirmed:
`â€œ`/`â€​`-family → curly quotes, `â‚¹` → ₹, `ï»¿` → strip), apply it across all fields, then spot-check
a random sample of ~50 records post-cleanup to confirm no new corruption was introduced. Did not
attempt this now — out of scope for this pass per the "low/no-cost, don't fix, just characterize"
instruction — but it's a bounded, well-understood task for whenever the silver set is actually
wired into a user-facing layer, not an open-ended research problem.

Everything else (field completeness, section-boundary accuracy, link validity) is already in good
shape and wouldn't need rework alongside a mojibake cleanup pass.
