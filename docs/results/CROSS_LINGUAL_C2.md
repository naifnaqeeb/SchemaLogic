# Cross-lingual case study (C2)

*Generated 2026-10-06 by `scripts/analyze_cross_lingual.py` (offline). Gold tag gold-v2; 10 frozen test profiles; Groq `openai/gpt-oss-120b` extractions.*

**Small sample** (k=3 per language, one scheme). **Not a clean translation pair**: the English input is a compilation of the GRs and official secondary sources, not a translation; the Marathi input is the original GR plus two amending GRs, so the extractor must also apply the amendment (see the temporal case study).

## Each draft against gold

| Draft | Language | Structural F1 | Outcome agreement | False eligible | False not eligible | Other |
|---|---|---|---|---|---|---|
| mr:sample_1 | mr | 0.600 | 60.0% | 0.0% | 0.0% | 40.0% |
| mr:sample_2 | mr | 0.690 | 60.0% | 0.0% | 0.0% | 40.0% |
| mr:sample_3 | mr | 0.733 | 60.0% | 0.0% | 0.0% | 40.0% |
| en:sample_1 | en | extraction failed | | | | |
| en:sample_2 | en | 0.857 | 80.0% | 0.0% | 0.0% | 20.0% |
| en:sample_3 | en | 0.867 | 70.0% | 0.0% | 0.0% | 30.0% |

## Drafts against each other (same profiles)

| Pair kind | Pairs | Mean verdict agreement |
|---|---|---|
| en-en | 1 | 90.0% |
| mr-mr | 3 | 100.0% |
| mr-en | 6 | 85.0% |

en-en and mr-mr are the noise baseline: two samples of the same text.

### Pairs

- en:sample_2 vs en:sample_3: 90.0% — differ on govt_employee_family_member
- en:sample_2 vs mr:sample_1: 80.0% — differ on govt_employee_family_member, other_govt_scheme_benefit_at_threshold
- en:sample_2 vs mr:sample_2: 80.0% — differ on govt_employee_family_member, other_govt_scheme_benefit_at_threshold
- en:sample_2 vs mr:sample_3: 80.0% — differ on govt_employee_family_member, other_govt_scheme_benefit_at_threshold
- en:sample_3 vs mr:sample_1: 90.0% — differ on other_govt_scheme_benefit_at_threshold
- en:sample_3 vs mr:sample_2: 90.0% — differ on other_govt_scheme_benefit_at_threshold
- en:sample_3 vs mr:sample_3: 90.0% — differ on other_govt_scheme_benefit_at_threshold
- mr:sample_1 vs mr:sample_2: 100.0%
- mr:sample_1 vs mr:sample_3: 100.0%
- mr:sample_2 vs mr:sample_3: 100.0%

## Not run

- PM-KISAN (Hindi/English): pmkisan.gov.in has a 2019 scheme summary in English and in Hindi (kept locally as PM-KISAN_summary_english_2019.pdf / PM-KISAN_summary_hindi_2019.pdf). The Hindi PDF uses a legacy non-Unicode font: its extracted text is corrupted (e.g. निधि comes out as ननधध), so an extraction from it would test the PDF's font encoding, not the language. Not run; would need OCR.
- No other gold scheme's sources include an official parallel text in two languages.
