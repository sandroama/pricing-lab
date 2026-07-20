# Phase 2b — regression-adjusted switchback precision audit

**Synthetic, deterministic, CPU-only.** Twenty independent 4-week switchback simulations; 28 daily randomized blocks and eight zones each.

| Estimator | Mean clustered SE | RMSE | Empirical 95% coverage |
|---|---:|---:|---:|
| Block-mean Hájek | 2.021 | 1.945 | 95.0% |
| Regression-adjusted | 1.994 | 1.945 | 95.0% |

Median adjusted/Hájek SE ratio: **0.987**. Zone/hour adjustment did not materially improve precision for daily blocks.

The adjusted model uses centered zone/hour fixed effects and treatment interactions. Its CR1 sandwich clusters at the randomized block and its 95% interval uses `t(n_blocks-2)`, so cell count is not mistaken for independent experimental units.

**Interpretation boundary.** Adjustment is a precision tool, not a repair for a biased assignment schedule. It cannot fix Phase 3's 4-hour diurnal aliasing; that requires stratified randomization or full-cycle blocks.
