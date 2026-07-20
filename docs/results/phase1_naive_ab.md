# Phase 1 — naive A/B under spillover

| Spillover | Estimator | Point | True ATE | Bias | Bias % | Covers truth |
|---|---|---|---|---|---|---|
| 0.00 | `naive_ab_diff_in_means` | 60.45 | 71.87 | -11.41 | 15.9% | ✅ |
| 0.15 | `naive_ab_diff_in_means` | 48.80 | 71.87 | -23.06 | 32.1% | ✅ |
| 0.35 | `naive_ab_diff_in_means` | 34.34 | 71.87 | -37.52 | 52.2% | ❌ |
| 0.50 | `naive_ab_diff_in_means` | 24.46 | 71.87 | -47.41 | 66.0% | ❌ |
| 0.70 | `naive_ab_diff_in_means` | 12.57 | 71.87 | -59.29 | 82.5% | ❌ |
