# pricing-lab — Build Plan

Phased milestones. Each phase produces a measurable artifact under
`docs/results/` and either a JSON for the portfolio aggregator or a
markdown writeup.

---

## Phase 1 — naive A/B baseline ✅ shipped (2026-05-05)

**Question (RQ-P1):** Does naive A/B bias on revenue scale with spillover
strength?

**Deliverables:**
- ✅ Synthetic marketplace DGP (`src/pricelab/simulation/marketplace.py`)
  with knobs for n_zones, n_time_buckets, elasticity band, diurnal
  amplitude, **spillover_strength**, capacity, noise.
- ✅ Naive A/B difference-in-means estimator (`estimators/ate.py`).
- ✅ Sweep runner across `spillover_strength ∈ {0.0, 0.15, 0.35, 0.50, 0.70}`
  → `docs/results/phase1_naive_ab.{json,md}`.
- ✅ Tests: simulator shape + reproducibility + capacity cap + estimator
  unbiasedness sanity check.

**Result:** naive A/B bias scales **monotonically** with spillover
strength, from 15.9% (no spillover) to 82.5% (`spillover_strength=0.70`).

---

## Phase 2 — switchback vs. naive head-to-head ✅ shipped (2026-05-05)

**Question (RQ-P2):** Does switchback Hájek bring bias below 10% across
the spillover sweep?

**Deliverables:**
- ✅ Block-randomized switchback assignment (`MarketplaceSimulator.simulate(design="switchback")`).
- ✅ Switchback Hájek estimator with cluster-level SE (`switchback_ate`).
- ✅ Phase-2 head-to-head harness (`evaluation/compare.py`).
- ✅ Sweep runner across the same spillover grid → `docs/results/phase2_switchback_vs_naive.{json,md}`.
- ✅ Test: switchback bias < naive bias under spillover (the headline assertion).

**Result:** switchback bias stays **constant at 3.9% across all spillover strengths**;
the gap to naive grows from −12.0pp (no spillover) to **−78.6pp** (heavy spillover).

### Phase 2b — regression-adjusted precision audit ✅ measured (2026-07-15)

- ✅ Centered Lin-style regression adjustment with zone/hour fixed effects and
  treatment interactions.
- ✅ CR1 sandwich uncertainty clustered at the randomized block; 95% interval
  uses `t(n_blocks-2)` rather than pretending cells are independent.
- ✅ Twenty-seed deterministic audit via `make phase2-adjusted`.

**Result:** adjusted/Hájek median SE ratio **0.987** (only 1.3% narrower),
identical RMSE (1.945), and empirical 95% coverage of **95% for both**
estimators once the truth was recomputed as a paired potential-outcome
contrast under common random numbers (the earlier 50–55% "coverage" was an
artifact of a noisy assignment-randomized truth whose MC SE ≈ 4.8 exceeded
the estimators' own SE ≈ 2.0). Daily blocks already contain every zone/hour
cell, so adjustment did **not materially improve precision**. This is a
rigorous negative result, not a claimed power win.

---

## Phase 3 — block-size sensitivity ✅ shipped (measured)

**Question (RQ-P3):** Does shrinking block size collapse switchback back
toward naive A/B?

**Deliverables:**
- ✅ Sweep `switchback_block_hours ∈ {1, 2, 4, 8, 24}` at fixed heavy
  spillover (`scripts/run_phase3_block_size.py`, `make phase3`) →
  `docs/results/phase3_block_size.{json,md}`.
- ✅ Per-block point / bias% / clustered-SE / CI-coverage recorded.

**Result (hypothesis falsified):** the bias-vs-block-size curve is
**non-monotone** — `{1h: 3.7%, 2h: 4.1%, 4h: 358.7%, 8h: 3.0%, 24h: 3.9%}`
at `spillover=0.70`. Instead of a graceful collapse toward naive A/B, there
is a sharp **diurnal-aliasing spike at `block_hours=4`** (strict T/C
alternation lands treatment on a fixed phase of the 24h cycle: mean diurnal
1.18 under treatment vs 0.82 under control). The daily (24h) block is both
unbiased and tightest-SE. Sub-day blocks would need hour-of-day
stratification. See `docs/results/phase3_block_size.md`.

---

## Phase 4 — Double ML for continuous-price elasticity (done ✓, 2026-07-12)

- ✅ Continuous-price DGP `simulate_continuous_price` (price confounded by
  zone × hour-of-day; binary designs untouched).
- ✅ `estimators/dml.py`: naive log-log OLS vs `EconML.LinearDML`
  (linear nuisances, cv=3), `make phase4` → `docs/results/phase4_dml.{json,md}`.

**Result (measured, 20 replicates, synthetic):** the pre-registered direction
("OLS *over-estimates* elasticity magnitude") was **wrong** — because the
platform prices *into* demand, OLS is biased upward hard enough to estimate a
**positive** elasticity in 20/20 replicates (mean bias +3.31 vs truth ≈ −1.2).
DML: mean bias −0.003, RMSE 0.027. Both binary success criteria still met
(OLS bias ≥20% ✓, DML within 10% ✓), but the honest verdict is a sign-flip,
not an over-estimate. See `docs/results/phase4_dml.md`.

---

## Phase 5 — heterogeneous elasticity + revenue optimizer (done ✓, 2026-07-12)

- ✅ `CausalForestDML` per-zone elasticities (zone one-hot X, hour controls);
  per-zone elasticity MAE 0.066.
- ✅ Bounded `scipy.optimize` revenue optimizer (±30% price band); policies
  decided on estimates, scored on the true revenue surface.
  `make phase5` → `docs/results/phase5_hetero.{json,md}`.

**Result (measured, 20 replicates, synthetic):** segment-specific pricing
recovers **+5.83% revenue [95% t-CI +4.32%, +7.33%]** over the best uniform
price, essentially at the oracle ceiling (+6.00%). Point estimate clears the
pre-registered ≥5% bar; the CI's lower half does not — reported as-is. The
"$X/hour" framing was dropped: the DGP's revenue units are synthetic, so only
the percentage is honest.

---

## Phase 6 — real public dataset (done ✓, 2026-07-12)

- ✅ One month of official **Citi Bike** data: `JC-202409` (~4 MB; the
  full-NYC month file is ~414 MB, over the repo's 300 MB download cap),
  cached under gitignored `data/`.
- ✅ Walk-forward partialling-out (`src/pricelab/realdata.py`, nuisances fit
  on past weeks only) vs naive diff-in-means.
  `make phase6` → `docs/results/phase6_realdata.{json,md}`.

**Result (measured, 115,201 trips, 5 folds):** the original headline target
("recovers elasticity within X% of the literature") was **not achievable —
the public feed contains no price**, so no elasticity is identifiable and
none is claimed. The honest deliverable: naive (−1.61 min) and adjusted
(−2.15 min) estimates of the e-bike duration effect **disagree by 0.53 min**,
explained by measured member/casual composition differences. Real
confounding, real disagreement, mechanism shown.

---

## Out of scope (explicit)

- Multi-armed bandit or RL pricing — different methodology.
- Real-time serving at >100 QPS — that's an infra project, not a
  causal-inference one.
- Beating SOTA on any specific dataset — the contribution is methodology
  rigor, not a leaderboard win.
