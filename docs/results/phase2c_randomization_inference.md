# Phase 2c — randomization-inference audit of the clustered CIs

**Synthetic, deterministic, CPU-only.** 100 independent 4-week switchback simulations (Phase-2b config: 28 daily blocks, 8 zones, spillover 0.70). Cross-checks the analytic clustered intervals against permutation inference on block means — no normality, no variance estimator.

| Interval | Empirical coverage of the paired-CRN truth |
|---|---|
| Hájek + Welch clustered CI | 95.0% (Wilson 95%: 88.8%–97.8%) |
| Regression-adjusted + CR1 t CI | 97.0% (Wilson 95%: 91.5%–99.0%) |
| Hájek randomization CI (inversion, 2000 perms) | 97.0% (Wilson 95%: 91.5%–99.0%) |

Randomization-CI width / Welch-CI width: mean 1.042, median 1.041.

**P-value calibration at the truth** (should be Uniform(0,1) if the inference is exact):

| Estimator | KS statistic | KS p-value |
|---|---:|---:|
| Hájek (2000 perms) | 0.095 | 0.305 |
| Regression-adjusted (199 refit perms) | 0.110 | 0.165 |

## Interpretation

Round 2 diagnosed the earlier ~50% 'coverage' as a noisy truth reference (assignment-randomized diff-in-means, MC SE ~4.8), not a broken interval; the paired common-random-numbers truth (MC SE ~0.12) resolved it. The permutation intervals agree with the analytic clustered intervals in coverage and width, and the truth-null p-values are consistent with uniformity: the round-2 diagnosis (noisy truth reference, not broken intervals) is confirmed by a design-agnostic method on 5x the seeds.

**Scope caveat (stated, not hidden).** The deployed schedule is strict alternation with a random start, whose exact randomization distribution has only two support points. The permutation test treats blocks as exchangeable — the standard super-population reading — so this is a calibration audit under exchangeability, not an exact design-based test of the alternation schedule.

Regenerate: `make phase2-ri` (deterministic, CPU, ~10 min).
