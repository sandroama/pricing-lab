# pricing-lab — Next Steps

A copy-pasteable runbook to take this project to its next milestone. Hand it to
future-you and execute cold.

---

## Current blocker

**None — and that is the point.** pricing-lab is a pure-CPU study. Phases 1–6
are all measured and committed under [`docs/results/`](docs/results/): the
binary switchback story (1–3), the continuous-price Double ML story (4–5), and
a real-data walk-forward comparison (6). No GPU, no API key; the only external
artifact is a ~4 MB public Citi Bike file (download command in
`scripts/run_phase6_realdata.py`, `data/` is gitignored).

Status of the pre-registered RQs:

1. **Phase 3 — DONE (RQ-P3 measured).** Bias vs. block size is *non-monotone*
   with a diurnal-aliasing spike at `block_hours=4` (359%) —
   [`phase3_block_size.md`](docs/results/phase3_block_size.md).
2. **Phase 4 — DONE (RQ-P4 measured).** Continuous price confounded by
   zone × hour: naive OLS got the elasticity **sign wrong in 20/20
   replicates** (mean bias +3.31); `EconML.LinearDML` mean bias −0.003, RMSE
   0.027 — [`phase4_dml.md`](docs/results/phase4_dml.md).
3. **Phase 5 — DONE (RQ-P5 measured).** `CausalForestDML` per-zone
   elasticities + bounded scipy optimizer: segment-specific pricing recovers
   **+5.83% revenue [95% CI +4.32%, +7.33%]** over the best uniform price
   (oracle ceiling +6.00%) — [`phase5_hetero.md`](docs/results/phase5_hetero.md).
4. **Phase 6 — DONE (real data).** 115,201 Citi Bike trips (JC, Sep 2024),
   walk-forward naive vs adjusted on the e-bike duration effect: **estimators
   disagree by 0.53 min**, explained by member/casual composition. No price in
   the public feed → no elasticity claimed —
   [`phase6_realdata.md`](docs/results/phase6_realdata.md).
5. **Test depth — 49 tests** (26 → 31: dashboard health check + per-tab-builder
   smoke tests, skip without `[ui]`; 31 → 35: regression-adjusted switchback
   guards; 35 → 39: truth-stability, walk-forward year-boundary firewall,
   degenerate-fold guard, non-positive-diurnal guard; 39 → 49: switchback
   randomization modes, permutation-inference determinism/agreement, and the
   Phase-3b rank-deficiency structural guard).

---

## Phase 4–6 milestone — DONE (2026-07-12)

- [x] `scripts/run_phase4_dml.py` runs via `make phase4` and writes
      `docs/results/phase4_dml.{json,md}` (per-replicate raws in the JSON).
- [x] Continuous-price DGP with `zone × diurnal` confounding added
      (`simulate_continuous_price`; binary designs preserved).
- [x] `EconML.LinearDML` estimator + OLS baseline in `estimators/dml.py`; DML
      recovers the elasticity, OLS sign-flips. Honest note kept: linear
      nuisances are correctly specified for this DGP; RF nuisances attenuated.
- [x] `scripts/run_phase5_hetero.py` (`make phase5`) — CausalForestDML
      segments + bounded revenue optimizer, uplift with 95% t-CI over 20
      replicates, oracle ceiling reported.
- [x] `scripts/run_phase6_realdata.py` (`make phase6`) — Citi Bike JC 2024-09
      (~4 MB official file; the full-NYC month is 414 MB, over the repo's
      300 MB download cap), walk-forward partialling-out vs naive,
      composition diagnostics.
- [x] RQ-P4/P5 flipped from "planned" to measured verdicts in README +
      EVALUATION_REPORT; `requires_econml` tests skip cleanly without the
      `[causal]` extra.

---

## Dashboard catch-up milestone — DONE (2026-07-15)

- [x] Three new Streamlit tabs reading **verbatim** from the committed JSONs
      (no recomputation): Phase 4 per-replicate OLS-vs-DML strip plot + bias
      table; Phase 5 uplift distribution vs oracle + policy comparison;
      Phase 6 per-fold naive vs walk-forward (±1.96·SE CIs) + composition
      diagnostics. Missing JSON → empty state pointing at `make phaseN`.
- [x] `tests/test_dashboard.py` (26 → 31 tests): AppTest full-app health
      check + per-tab-builder smoke on the committed JSONs.
- [x] HF Space inherits automatically (`hf_space/app.py` star-imports
      `dashboard.app`); Space README tagline reconciled to committed numbers.

---

## Coverage-calibration milestone — DONE (2026-07-15)

The former candidate "calibrate switchback coverage" is resolved, root cause
measured: the intervals were fine, the *truth reference* was noisy. The old
`_compute_true_ate` randomized assignment and took a diff-in-means; its Monte
Carlo SE (≈4.8 at the Phase-2b config) exceeded the estimators' own SE (≈2.0),
so "coverage vs a moving target" read 50–55%. The truth is now the paired mean
of `Y(1) − Y(0)` under common random numbers (vectorized, MC SE ≈ 0.12 at 32
resamples). Re-measured Phase 2b: **95% empirical coverage for both Hájek and
regression-adjusted intervals** (20 seeds), identical RMSE 1.945, median SE
ratio 0.987 unchanged. Phases 1–3 regenerated against the corrected truth
(71.87 vs 70.65): naive sweep 15.9→82.5%, switchback constant 3.9%, Phase-3
spike 358.7%. All prose reconciled to the regenerated JSONs.

---

## Round-3 milestone — DONE (2026-07-18)

- [x] **Phase 3b — sub-day stratification experiment** (`make phase3b`,
      `docs/results/phase3b_stratified_switchback.{json,md}`, 50 seeds).
      Falsifiable claim *supported, with a sharp split*: analysis-side
      stratification alone is impossible under strict alternation (hour
      collinear with treatment, unidentified 50/50 seeds); design-side
      daily-stratified randomization + hour/zone adjustment restores the
      daily-block anchor (RMSE 1.86 vs 261, coverage 94% vs 0%). The simulator
      gained `switchback_randomization ∈ {alternating, iid, stratified_daily}`.
- [x] **Phase 2c — randomization-inference CI audit** (`make phase2-ri`,
      `docs/results/phase2c_randomization_inference.{json,md}`, 100 seeds,
      permutation CIs by test inversion + truth-null p-value uniformity).
      Verdict is computed from the measurements inside the JSON.
- [x] **HF Space hardening** — `hf_space/requirements.txt` created (June-audit
      gap); `hf_space/app.py` now runs the dashboard via `sys.path` without
      requiring `pip install -e .`; DEPLOYMENT.md upload steps corrected.
- [x] Tests 39 → 49 (randomization modes + permutation inference + the
      rank-deficiency structural guard).

## Next milestone candidates (pick one, none blocking)

1. **Full-NYC month for Phase 6** (~414 MB download, ~2 M trips). Same
   runner, bigger n → tighter fold CIs and borough-level heterogeneity.
   Requires raising the repo's self-imposed 300 MB download cap.
2. **Real marketplace price/exposure data** for an actual elasticity study —
   external gate: Citi Bike publishes no prices; needs a dataset that does.

---

## Expected outputs (already realized)

| Milestone | Generates | Fills in README / report |
|---|---|---|
| **Phase 3** (done ✓) | `docs/results/phase3_block_size.{json,md}` | Non-monotone bias curve; aliasing spike at `block_hours=4` |
| **Phase 3b** (done ✓) | `docs/results/phase3b_stratified_switchback.{json,md}` | Stratified randomization + hour adjustment restores anchor RMSE/coverage at 4h blocks |
| **Phase 2c** (done ✓) | `docs/results/phase2c_randomization_inference.{json,md}` | Randomization-inference audit of the clustered CIs (100 seeds) |
| **Phase 4** (done ✓) | `docs/results/phase4_dml.{json,md}` | "OLS sign-flips 20/20; DML mean bias −0.003" headline |
| **Phase 5** (done ✓) | `docs/results/phase5_hetero.{json,md}` | "+5.83% revenue [CI +4.32, +7.33] from segment pricing" headline |
| **Phase 6** (done ✓) | `docs/results/phase6_realdata.{json,md}` | "naive vs adjusted disagree by 0.53 min on real data, explained" headline |

---

## Environment (one-time, ≤2 min)

```bash
cd pricing-lab
python3.12 -m venv .venv && source .venv/bin/activate
make install-dev
pip install -e ".[causal]"   # EconML — phases 4–5
make smoke && make test      # 39 tests
make phase4 && make phase5   # seconds each, deterministic
# phase 6 needs the data file once (official source, ~4 MB):
curl -o data/JC-202409-citibike-tripdata.csv.zip \
  https://s3.amazonaws.com/tripdata/JC-202409-citibike-tripdata.csv.zip
make phase6
```
