# Research Questions — pricing-lab

Pre-registered. Each question has a falsifiable success criterion and
a phase that owns it.

---

## RQ-P1 — Does naive A/B bias scale predictably with spillover strength?

**Hypothesis.** On the marketplace DGP, naive A/B
difference-in-means under-estimates the true revenue ATE *monotonically*
as `spillover_strength` grows, with the bias going from ~10% at no
spillover (capacity-binding floor) to ≥80% at heavy spillover (≥0.70).

**Success criterion (binary).**
- `bias_naive(spillover=0.70) > bias_naive(spillover=0.00)` by ≥ 50pp.
- `bias_naive(s)` is non-decreasing in `s` across `s ∈ {0.00, 0.15, 0.35, 0.50, 0.70}`.

**Owns this RQ.** Phase 1.

**Result.** ✅ Bias scales 15.9% → 32.1% → 52.2% → 66.0% → 82.5% across
the sweep. Strictly monotone. See
[`docs/results/phase1_naive_ab.md`](results/phase1_naive_ab.md).

---

## RQ-P2 — Does switchback Hájek reduce bias below 10% across the spillover sweep?

**Hypothesis.** The switchback design with daily blocks (`block_hours=24`)
holds SUTVA across time blocks, so the Hájek estimator should be
approximately unbiased — bias < 10% of the true ATE at every spillover
level.

**Success criterion (binary).**
- `bias_switchback(s) < 0.10 × true_ate` for **every** `s` in the sweep.

**Owns this RQ.** Phase 2.

**Result.** ✅ Switchback bias is a **constant 3.9%** across the entire
sweep (0.0 → 0.70). The residual is dominated by capacity-binding noise,
not spillover. See
[`docs/results/phase2_switchback_vs_naive.md`](results/phase2_switchback_vs_naive.md).

---

## RQ-P3 — Does shrinking the switchback block size collapse the estimator back toward naive A/B?

**Hypothesis.** As `switchback_block_hours` shrinks from 24 → 1, the
block-randomization aliases more strongly with the diurnal cycle.
Below some critical block size, switchback bias should approach naive
A/B bias.

**Success criterion (binary).**
- `bias_switchback(block_hours=1) ≥ 0.50 × bias_naive(same DGP)`.
- A monotone (or at least U-shaped) bias-vs-block-size curve.

**Owns this RQ.** Phase 3.

**Result.** ⚠️ **Measured — hypothesis falsified.** The curve is **NOT** a
monotone collapse toward naive A/B. At fixed `spillover=0.70`, switchback bias
by block size is `{1h: 3.7%, 2h: 4.1%, 4h: 358.7%, 8h: 3.0%, 24h: 3.9%}` —
**non-monotone**, with a sharp aliasing **spike at `block_hours=4`** rather than
at the smallest block. The cause is diurnal aliasing: strict `T C T C`
alternation at a 4-hour cadence lands treatment on a fixed phase of the 24-hour
demand cycle (mean diurnal 1.18 under treatment vs 0.82 under control), which
the estimator misreads as a treatment effect. The criterion's `block_hours=1`
prediction also fails — at 1h the bias is only 3.7%, not ≥50% of naive. So both
binary conditions are **rejected**; the real finding is the aliasing pathology,
not a graceful degradation. See
[`docs/results/phase3_block_size.md`](results/phase3_block_size.md)
(regenerate with `make phase3`).

---

## RQ-P4 — Does Double ML for continuous price elasticity beat OLS under zone × time confounding?

**Hypothesis.** When the DGP has confounding (zone × time-of-day drives
both price and demand), OLS regression of log-demand on log-price
**over-estimates the magnitude** of elasticity. Double ML with
zone-fixed-effects + time-of-day controls should recover elasticity
within 10% of the true band.

**Success criterion (binary).**
- OLS elasticity estimate is biased by ≥ 20% from the band-mean truth.
- DML estimate is within 10% of the truth.

**Owns this RQ.** Phase 4 — **measured 2026-07-12** (`make phase4`,
[`results/phase4_dml.md`](results/phase4_dml.md)). Both binary criteria
met: OLS bias far above 20% (mean bias +3.31 over 20 replicates) and DML
within 10% (mean bias −0.003, RMSE 0.027). **But the hypothesized
direction was wrong:** OLS did not *over-estimate the magnitude* — the
platform prices into demand, so OLS was biased upward past zero and
estimated a **positive** elasticity in 20/20 replicates. Recorded as a
direction-falsified, criteria-met result.

---

## RQ-P5 — Does segment-specific pricing recover revenue that uniform pricing leaves on the table?

**Hypothesis.** Heterogeneous elasticity by zone (`-2.0` → `-0.4` band)
means the revenue-maximizing price differs by ≥ 20% across segments.
A causal forest estimator + constrained optimizer should recover
≥ 5% additional revenue per cell vs. a uniform-price baseline in
counterfactual simulation.

**Success criterion (binary).**
- `revenue(segment-priced) ≥ 1.05 × revenue(uniform-priced)` averaged
  over zones, in counterfactual simulation with held-out test cells.

**Owns this RQ.** Phase 5 — **measured 2026-07-12** (`make phase5`,
[`results/phase5_hetero.md`](results/phase5_hetero.md)). Segment-specific
pricing recovered **+5.83%** revenue [95% t-CI +4.32%, +7.33%] vs the
best uniform price over 20 replicates (oracle ceiling +6.00%). The point
estimate clears the pre-registered 1.05× bar; the CI's lower half does
not — reported as-is, criterion judged on the point estimate as
pre-registered.

---

## Out of scope (explicit)

- Multi-armed bandit / online RL pricing — different methodology, would
  dilute the causal-inference focus.
- Beating SOTA on any specific real-world dataset — the contribution is
  *methodology rigor*, not a leaderboard win.
- Real-time serving at >100 QPS — that's an infra project, not a causal-
  inference one.
- General time-series forecasting — Phase 6 (measured: Citi Bike,
  [`results/phase6_realdata.md`](results/phase6_realdata.md)) introduced
  real data with walk-forward eval; the headline claim is the *causal*
  naive-vs-adjusted gap, not forecast accuracy. No price exists in the
  public feed, so no elasticity was claimed.

---

## How to verify any RQ result

```bash
make smoke                       # asserts P1 + P2 headline at 0.80 spillover
make phase1 && make phase2       # produces docs/results JSONs for the sweep
```

Every measured number in this document is reproducible from a fixed seed.
