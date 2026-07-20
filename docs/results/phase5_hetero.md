# Phase 5 — heterogeneous elasticity + revenue optimization (RQ-P5)

**Synthetic** continuous-price DGP (8 zones with heterogeneous true elasticities, 336 hourly buckets, 20 replicates). Per-zone elasticities estimated with `CausalForestDML`; a bounded scipy optimizer picks prices in [7, 13] (±30% band). Policies are chosen on *estimates* and scored on the *true* expected-revenue surface.

| Policy | Revenue uplift vs uniform | 95% t-CI |
|---|---:|---:|
| Segment-specific (estimated elasticities) | **+5.83%** | [+4.32%, +7.33%] |
| Oracle segment (true elasticities — ceiling) | +6.00% | [+4.50%, +7.50%] |

## Verdict — measured

Segment-specific pricing recovers **+5.83%** revenue [95% CI +4.32%, +7.33%] over the best uniform price in this simulation (n=20 replicates), essentially matching the oracle ceiling of +6.00% — because CausalForestDML's per-zone elasticity MAE is only 0.066 on this DGP.

Honest caveats: **synthetic**; the uplift magnitude is a function of the ±30% price band and the elasticity spread knob — wider bands or wider elasticity heterogeneity mechanically increase it. The transferable claim is the *pipeline* (heterogeneous causal estimates → constrained optimizer → counterfactual scoring), not the specific percentage.

Per-replicate raw values: [`phase5_hetero.json`](phase5_hetero.json). Regenerate: `make phase5` (CPU, deterministic, seconds).
