# Self-consistency confidence (k samples) vs self-reported confidence

*Generated 2026-10-07T09:18:29 by `scripts/analyze_self_consistency.py` from code `d1a9b07`, against frozen gold `gold-v2`. Small sample: 7 schemes, k samples each; rank correlations over so few schemes are indicative only. Agreement is over a scheme's VALID samples (a sample that failed schema validation produced no predicates and is listed, not counted); a scheme needs at least 2 valid samples to be scored.*

| Scheme | Valid samples | Predicates per sample | Mean agreement | Unanimous | Self-reported (per sample) | Structural F1 (per sample) | Outcome agreement (mean) |
|---|---|---|---|---|---|---|---|
| AB-PMJAY | 3/3 | [17, 13, 20] | 0.88 | 0.72 | [0.95, 0.96, 0.95] | [0.68, 0.565, 0.679] | 0.758 |
| IGNOAPS | 3/3 | [6, 6, 6] | 0.778 | 0.5 | [0.9, 0.6, 0.9] | [0.5, 0.333, 0.5] | 0.722 |
| MH-LADKI-BAHIN | 2/3 | [15, 17] | 0.906 | 0.812 | [0.95, 0.95] | [0.857, 0.867] | 0.75 |
| PM-KISAN | 3/3 | [10, 10, 10] | 1.0 | 1.0 | [0.95, 0.95, 0.95] | [0.952, 0.952, 0.952] | 0.917 |
| PM-UJJWALA-2.0 | 3/3 | [13, 13, 13] | 0.966 | 0.923 | [0.95, 0.95, 0.95] | [0.923, 1.0, 1.0] | 1.0 |
| PMAY-G | 3/3 | [12, 18, 13] | 0.643 | 0.279 | [0.85, 0.85, 0.95] | [0.296, 0.667, 0.929] | 0.548 |
| PMMVY | 3/3 | [14, 5, 13] | 0.667 | 0.094 | [0.97, 0.95, 0.95] | [0.839, 0.182, 0.8] | 0.417 |

## Predicate-level calibration (n = 244 predicates)

Correct = an identical predicate exists in the frozen gold.

- Agreement confidence: ECE **0.0806**
- Self-reported confidence: ECE **0.0923**

| Signal | Bin | n | Mean confidence | Accuracy |
|---|---|---|---|---|
| agreement | [0.0, 0.34] | 26 | 0.333 | 0.154 |
| agreement | [0.35, 0.67] | 66 | 0.652 | 0.803 |
| agreement | [0.68, 1.0] | 152 | 1.0 | 0.967 |
| self_reported | [0.0, 0.5] | 0 | None | None |
| self_reported | [0.51, 0.7] | 6 | 0.6 | 0.333 |
| self_reported | [0.71, 0.85] | 30 | 0.85 | 0.5 |
| self_reported | [0.86, 1.0] | 208 | 0.949 | 0.899 |

## Scheme ranking (Spearman, n = 7)

| | vs structural F1 | vs outcome agreement |
|---|---|---|
| Agreement confidence | 0.821 | 0.893 |
| Self-reported confidence | 0.185 | 0.0 |

## A collapsed extraction with no gold (silver)

pmksypdmc's AI-Checked extraction once collapsed a ~3,900-character scheme to one predicate at a self-reported 0.95 (KNOWN_ISSUES). Does agreement flag it when the collapse repeats?

| Scheme | Valid samples | Predicates per sample | Fields | Self-reported (per sample) | Mean agreement |
|---|---|---|---|---|---|
| pmksypdmc | 2/2 | [1, 2] | [['is_indian_citizen'], ['is_farmer', 'is_indian_citizen']] | [0.95, 0.95] | 0.833 |

A collapse that repeats gets HIGH agreement: its one rule is produced every time. Agreement measures consistency, not completeness, so it does not catch this case. Predicate count against source length (the AI-Checked tier's structural check) does.
