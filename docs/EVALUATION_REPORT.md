# pricing-lab — Evaluation Report

> Consolidated results across all phases, captured on a CPU-only macOS dev
> box. Every number is reproducible from `make smoke` and `make phase1` …
> `make phase6` (phases 4–5 need `pip install -e ".[causal]"`; phase 6 needs
> the ~4 MB Citi Bike file — download command in its script header).

---

## TL;DR

| RQ | Verdict |
|---|---|
| **RQ-P1** — Does naive A/B bias scale predictably with spillover? | ✅ **Yes — monotonically.** Bias scales 15.9% → 32.1% → 52.2% → 66.0% → **82.5%** across `spillover_strength ∈ {0.0, 0.15, 0.35, 0.5, 0.7}`. |
| **RQ-P2** — Does switchback Hájek reduce bias below 10% across the spillover sweep? | ✅ **Yes — constant 3.9%.** Bias does not move with spillover; the residual is capacity-binding noise. Gap to naive at strong spillover: **−78.6 pp**. |
| **RQ-P3** — Does block-size shrinkage collapse switchback toward naive A/B? | ⚠️ **Measured — hypothesis falsified.** Bias vs. block size is **non-monotone**: a diurnal-**aliasing spike at `block_hours=4` (359%)**, not a graceful collapse. See Phase 3 below. |
| **RQ-P4** — DML vs OLS under confounding? | ⚠️ **Measured — criteria met, hypothesized direction wrong.** Naive OLS didn't *over*-estimate elasticity magnitude — it **flipped the sign in 20/20 replicates** (mean bias +3.31); `LinearDML` mean bias −0.003, RMSE 0.027. Synthetic, 20 seeds. [`phase4_dml.md`](results/phase4_dml.md). |
| **RQ-P5** — Heterogeneous pricing revenue lift? | ✅ **Yes — point estimate clears the ≥5% bar.** Segment-specific pricing +5.83% revenue [95% t-CI +4.32%, +7.33%] vs best uniform (oracle ceiling +6.00%); CI's lower half sits below 5%, reported as-is. Synthetic, 20 seeds. [`phase5_hetero.md`](results/phase5_hetero.md). |
| **RQ-P6** — Does the methodology survive real data? | ⚠️ **Measured — no elasticity identifiable (no price in the feed); honest deliverable is the naive-vs-adjusted gap.** On 115,201 Citi Bike trips (JC 2024-09), naive −1.61 vs walk-forward-adjusted −2.15 min e-bike duration effect: **0.53 min disagreement**, explained by member/casual composition. [`phase6_realdata.md`](results/phase6_realdata.md). |

---

## Phase 1 — naive A/B under varying spillover (RQ-P1)

> Source: [`docs/results/phase1_naive_ab.md`](results/phase1_naive_ab.md)
> · regenerate with `make phase1`.

**Setup.** 4-week horizon (`n_time_buckets=672`), 8 zones,
heterogeneous elasticity band `(-2.0, -0.4)`, diurnal amplitude 0.6,
capacity multiplier 1.5, log-normal noise σ=0.10, `seed=42`.

| Spillover | Estimator | Point | True ATE | Bias | Bias % | Covers truth |
|---|---|---|---|---|---|---|
| 0.00 | naive A/B | 60.45 | 71.87 | −11.41 | 15.9% | ✅ |
| 0.15 | naive A/B | 48.80 | 71.87 | −23.06 | 32.1% | ✅ |
| 0.35 | naive A/B | 34.34 | 71.87 | −37.52 | 52.2% | ❌ |
| 0.50 | naive A/B | 24.46 | 71.87 | −47.41 | 66.0% | ❌ |
| 0.70 | naive A/B | 12.57 | 71.87 | −59.29 | 82.5% | ❌ |

> **Headline:** strictly monotone bias growth in spillover. At
> `spillover=0.70`, naive A/B reports only **17.5% of the true ATE**
> — and the 95% CI does **not** contain the truth from
> `spillover=0.35` upward.

---

## Phase 2 — switchback Hájek head-to-head (RQ-P2)

> Source: [`docs/results/phase2_switchback_vs_naive.md`](results/phase2_switchback_vs_naive.md)
> · regenerate with `make phase2`.

Same setup as Phase 1, plus `switchback_block_hours=24` (one full
diurnal cycle per block).

| Spillover | Naive bias % | Switchback bias % | Gap |
|---|---|---|---|
| 0.00 | 15.9% | 3.9% | **−12.0 pp** |
| 0.15 | 32.1% | 3.9% | **−28.2 pp** |
| 0.35 | 52.2% | 3.9% | **−48.3 pp** |
| 0.50 | 66.0% | 3.9% | **−62.1 pp** |
| 0.70 | 82.5% | 3.9% | **−78.6 pp** |

> **Headline:** switchback bias is **constant at 3.9%** across the entire
> spillover sweep. The variation that *does* exist comes from capacity
> binding, not from spillover — exactly what the methodology promises.

### Why switchback works here

- **SUTVA holds across blocks.** A treatment block has uniform price
  across all zones, so no within-block spillover can leak between
  treatment and control.
- **Daily blocks eliminate diurnal aliasing.** A 24-hour block spans an
  integer number of diurnal cycles, so block-mean revenue isn't biased
  by which hours fell in the block.
- **Balanced alternation** (`T C T C T C ...`) guarantees equal exposure
  to all days of the week, eliminating day-of-week confounding too.

### Honest caveat

The Hájek estimator clusters at the block level. With four weeks of data and
24-hour blocks, there are only 28 randomized units. A new 20-seed Phase 2b
audit compared it with centered zone/hour regression adjustment using
treatment interactions and a CR1 block-clustered, small-sample t interval.
The result was a **0.987 median adjusted/Hájek SE ratio** (only 1.3% narrower),
identical RMSE (1.945), and **95% empirical coverage for both estimators**.
(An earlier read reported 50–55% coverage; that was an artifact of the old
assignment-randomized truth, whose Monte Carlo SE ≈ 4.8 exceeded the
estimators' own SE ≈ 2.0. The truth is now a paired potential-outcome
contrast under common random numbers, MC SE ≈ 0.12.) Daily blocks already
contain every zone and hour, so this adjustment is not a
meaningful power gain. See [`phase2_regression_adjusted.md`](results/phase2_regression_adjusted.md).

---

## Phase 3 — switchback block-size sensitivity (RQ-P3)

> Source: [`docs/results/phase3_block_size.md`](results/phase3_block_size.md)
> · regenerate with `make phase3`.

Fixed heavy spillover (`spillover_strength=0.70`), 4-week horizon, 8 zones,
`seed=42`. True ATE = 71.87. Naive A/B (block-insensitive) bias = 82.5%.

| Block hours | Switchback point | Bias % | SE | # blocks (T/C) | Covers truth |
|---:|---:|---:|---:|---:|:--:|
| 1 | 74.52 | 3.7% | 39.23 | 336/336 | ✅ |
| 2 | 68.92 | 4.1% | 54.41 | 168/168 | ✅ |
| 4 | 329.61 | **358.7%** | 67.35 | 84/84 | ❌ |
| 8 | 69.70 | 3.0% | 42.60 | 42/42 | ✅ |
| 24 | 69.06 | 3.9% | 2.03 | 14/14 | ✅ |

> **Headline (hypothesis falsified):** the pre-registered RQ-P3 expected a
> *monotone collapse* of switchback toward naive A/B as blocks shrink. The
> measured curve is **non-monotone** — a sharp **aliasing spike at**
> **`block_hours=4` (359% bias)**, while 1h/2h/8h/24h all stay within ~5% of
> the truth. We report the spike rather than smoothing it.

### Why `block_hours=4` aliases

Treatment alternates strictly `T C T C …`. A 4-hour block packs 6 blocks per
day into a fixed even/odd pattern, so treatment lands on the **same phase** of
the 24-hour diurnal (rush-hour) cycle every day. Measured: mean diurnal
multiplier **1.18 under treatment vs 0.82 under control** at `block_hours=4` —
treatment is systematically over-exposed to busy hours, which the estimator
misreads as a treatment effect. At `block_hours=24` the same alternation
balances perfectly (mean diurnal 1.00 in both arms): hence the daily block is
both unbiased *and* has the tightest SE (2.03 vs 40–67 for sub-day blocks,
which have fewer, noisier clusters).

### Takeaway

Block size is **not** a smooth bias/power dial, and "use a divisor of 24" is
**not** sufficient (4 divides 24 yet fails). A sub-day block that does not span
a full diurnal cycle can alias and produce *worse* bias than a coarser block;
it would need explicit hour-of-day stratification. Prefer a full-cycle
(24-hour) block. This **refines and partly overturns** the naive RQ-P3
intuition — a more honest result than the clean monotone curve we hypothesized.

---

## Cross-method takeaway

> **For a marketplace experiment with non-trivial network effects:
> never trust a naive A/B difference-in-means. Switchback recovers the
> truth; naive A/B does not.**

This is the headline that fits the *causal inference* identity addition
to the portfolio. Phases 4–6 extend it: under confounded *continuous*
pricing, naive OLS points the demand curve the wrong way while DML
recovers it (Phase 4); the heterogeneous estimates are accurate enough
to price segments at the oracle revenue ceiling (Phase 5); and on real
Citi Bike data the naive-vs-adjusted gap is measurable and explainable,
with the honest admission that no price — and hence no elasticity —
exists in the public feed (Phase 6). Full details in
[`results/phase4_dml.md`](results/phase4_dml.md),
[`results/phase5_hetero.md`](results/phase5_hetero.md),
[`results/phase6_realdata.md`](results/phase6_realdata.md).

---

## Reproducing

```bash
cd pricing-lab
make install-dev
make smoke         # asserts the headline at strong spillover
make phase1        # writes docs/results/phase1_naive_ab.{json,md}
make phase2        # writes docs/results/phase2_switchback_vs_naive.{json,md}
pip install -e ".[causal]" && make phase4 && make phase5   # DML phases
make phase6        # after the ~4 MB Citi Bike download (see script header)
```
