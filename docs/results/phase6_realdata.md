# Phase 6 — real data: Citi Bike walk-forward naive vs adjusted (RQ-P6)

**Real data** (not synthetic): 115,201 trips, Citi Bike **Jersey City** file, September 2024, from the official open-data bucket (full-NYC month is ~414 MB, over the repo's download cap; the JC file is the same system's official data at ~4 MB). 357 trips outside the 1–120 min band dropped.

**No price exists in this data**, so no elasticity is identifiable — claiming one would be fabrication. The transferable question is the project's core one: does a naive group comparison survive real temporal/composition confounding? Target: e-bike vs classic effect on trip duration.

| Estimator | Effect (min) | 95% t-CI over 5 walk-forward folds |
|---|---:|---:|
| Naive diff-in-means | -1.612 | [-2.220, -1.005] |
| Walk-forward partialled-out (hour+weekday+member) | -2.145 | [-2.702, -1.587] |

Per-fold estimates and composition diagnostics: [`phase6_realdata.json`](phase6_realdata.json).

## What the estimators say — and why they differ

Naive and adjusted estimates disagree by **+0.533 minutes** (naive -1.612 vs adjusted -2.145). Composition diagnostics measured from the data:

- member share: 69.0% of e-bike trips vs 80.8% of classic trips, and members ride much shorter (7.9 vs 13.0 min) — e-bikes carry a casual-heavy, long-trip mix, which drags the naive estimate toward zero;
- weekend share: 26.8% (e-bike) vs 26.1% (classic);
- mean start hour: 14.1 vs 13.9.

## Honest limits

- **Selection on unobservables is uncontrolled**: riders *choose* e-bikes, and trip-purpose/distance are not in the controls, so the adjusted number is a *covariate-adjusted association*, not a clean causal effect. On real data the deliverable is the size of the naive-vs-adjusted gap and its explanation, not a causal victory lap.
- Jersey City subset (n=115,201), one month, 5-fold walk-forward — CIs over folds are wide by construction.
- Duration is the outcome only because it is what the public feed contains; with price data the same walk-forward partialling-out plumbing would target elasticity directly (that is exactly Phase 4's estimator).

Regenerate: `make phase6` (download command in the script header; ~4 MB, official source, `data/` is gitignored).
