# Phase 2 — switchback vs. naive A/B

| Spillover | Estimator | Point | True ATE | Bias % | Covers truth |
|---|---|---|---|---|---|
| 0.00 | `naive_ab_diff_in_means` | 60.45 | 71.87 | 15.9% | ✅ |
| 0.00 | `switchback_hajek` | 69.06 | 71.87 | 3.9% | ✅ |
| 0.15 | `naive_ab_diff_in_means` | 48.80 | 71.87 | 32.1% | ✅ |
| 0.15 | `switchback_hajek` | 69.06 | 71.87 | 3.9% | ✅ |
| 0.35 | `naive_ab_diff_in_means` | 34.34 | 71.87 | 52.2% | ❌ |
| 0.35 | `switchback_hajek` | 69.06 | 71.87 | 3.9% | ✅ |
| 0.50 | `naive_ab_diff_in_means` | 24.46 | 71.87 | 66.0% | ❌ |
| 0.50 | `switchback_hajek` | 69.06 | 71.87 | 3.9% | ✅ |
| 0.70 | `naive_ab_diff_in_means` | 12.57 | 71.87 | 82.5% | ❌ |
| 0.70 | `switchback_hajek` | 69.06 | 71.87 | 3.9% | ✅ |
