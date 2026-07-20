# Phase 4 — Double ML for continuous-price elasticity (RQ-P4)

**Synthetic** continuous-price DGP, price confounded by zone × hour-of-day (the platform charges more when demand is high). 20 replicates, independent seeds (elasticities redrawn per seed; mean truth ≈ -1.18), 8 zones × 336 hourly buckets = 2688 rows per replicate. No spillover / capacity cap in this variant — Phase 4 isolates *confounding* bias (Phases 1–3 covered interference).

| Estimator | Mean bias | RMSE | 95% t-CI on bias |
|---|---:|---:|---:|
| Naive OLS (log-log, no controls) | +3.310 | 3.313 | [+3.235, +3.384] |
| LinearDML (EconML, hour+zone controls) | -0.003 | 0.027 | [-0.016, +0.010] |

## Verdict — measured

Naive OLS doesn't just miss the elasticity — it got the **sign wrong in 20/20 replicates** (estimated demand sloping *upward* in price), because the pricing policy raises prices exactly when demand is high. Cross-fitted DML with hour + zone controls recovers the truth with mean bias -0.003 and RMSE 0.027 (elasticity units, truth ≈ -1.18).

Honest caveats: linear nuisance models are *correctly specified* for this DGP (additive in hour/zone dummies) — real data won't be that kind. Random-forest nuisances were tried first and attenuated the estimate on this small n; that trade-off is noted in `estimators/dml.py`.

Per-replicate raw estimates: [`phase4_dml.json`](phase4_dml.json). Regenerate: `make phase4` (CPU, deterministic, seconds).
