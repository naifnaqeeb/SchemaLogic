# Self-consistency confidence (k samples) vs self-reported confidence

*Generated 2026-10-05T14:37:34 by `scripts/analyze_self_consistency.py` from code `14d17f9`, against frozen gold `gold-v2`. Small sample: 6 schemes, k samples each; rank correlations over so few schemes are indicative only. Agreement is over a scheme's VALID samples (a sample that failed schema validation produced no predicates and is listed, not counted); a scheme needs at least 2 valid samples to be scored.*

| Scheme | Valid samples | Predicates per sample | Mean agreement | Unanimous | Self-reported (per sample) | Structural F1 (per sample) | Outcome agreement (mean) |
|---|---|---|---|---|---|---|---|
| AB-PMJAY | 3/3 | [17, 13, 20] | 0.88 | 0.72 | [0.95, 0.96, 0.95] | [0.68, 0.565, 0.679] | 0.758 |
| IGNOAPS | 3/3 | [6, 6, 6] | 0.778 | 0.5 | [0.9, 0.6, 0.9] | [0.5, 0.333, 0.5] | 0.722 |
| MH-LADKI-BAHIN | 2/3 | [15, 17] | 0.906 | 0.812 | [0.95, 0.95] | [0.857, 0.867] | 0.75 |
| PM-KISAN | 3/3 | [10, 10, 10] | 1.0 | 1.0 | [0.95, 0.95, 0.95] | [0.952, 0.952, 0.952] | 0.917 |
| PM-UJJWALA-2.0 | 3/3 | [13, 13, 13] | 0.966 | 0.923 | [0.95, 0.95, 0.95] | [0.923, 1.0, 1.0] | 1.0 |
| PMAY-G | 3/3 | [12, 18, 13] | 0.643 | 0.279 | [0.85, 0.85, 0.95] | [0.296, 0.667, 0.929] | 0.548 |
| PMMVY | 1/1 | — | — | — | — | — | — | *(fewer than 2 valid samples so far)*

## Predicate-level calibration (n = 212 predicates)

Correct = an identical predicate exists in the frozen gold.

- Agreement confidence: ECE **0.0566**
- Self-reported confidence: ECE **0.0888**

| Signal | Bin | n | Mean confidence | Accuracy |
|---|---|---|---|---|
| agreement | [0.0, 0.34] | 23 | 0.333 | 0.174 |
| agreement | [0.35, 0.67] | 40 | 0.642 | 0.725 |
| agreement | [0.68, 1.0] | 149 | 1.0 | 0.966 |
| self_reported | [0.0, 0.5] | 0 | None | None |
| self_reported | [0.51, 0.7] | 6 | 0.6 | 0.333 |
| self_reported | [0.71, 0.85] | 30 | 0.85 | 0.5 |
| self_reported | [0.86, 1.0] | 176 | 0.947 | 0.909 |

## Scheme ranking (Spearman, n = 6)

| | vs structural F1 | vs outcome agreement |
|---|---|---|
| Agreement confidence | 0.886 | 0.886 |
| Self-reported confidence | 0.577 | 0.638 |
