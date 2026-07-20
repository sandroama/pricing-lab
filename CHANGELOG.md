# Changelog

All notable changes to **pricing-lab** will be documented here.

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Fixed — truth estimand + walk-forward year-boundary firewall — 2026-07-15

- **Root-caused the 50–55% Phase-2b coverage** (supersedes the coverage caveat
  in the entry below): the clustered intervals were calibrated all along — the
  *truth reference* was noisy. The old `_compute_true_ate` randomized
  assignment and took a diff-in-means whose Monte Carlo SE (≈4.8 at the
  Phase-2b config) exceeded the estimators' own SE (≈2.0; empirical SD of the
  Hájek point estimate over 60 replicates was 2.018 vs mean analytic SE 2.027).
  Rewrote the truth as the paired mean of `Y(1) − Y(0)` under **common random
  numbers** (both prices on the same noise draw, vectorized, 32 resamples,
  MC SE ≈ 0.12, ~3 ms). Re-measured Phase 2b: **95% empirical coverage for
  both estimators**, RMSE 1.945, median SE ratio 0.987 unchanged.
- Regenerated Phases 1–3 against the corrected truth (71.87 vs 70.65,
  within the old truth's MC error): naive sweep bias 15.9% → 82.5%,
  switchback constant **3.9%** (was misread as 2.2% against the noisy truth),
  Phase-3 aliasing spike **358.7%** (was 366.5%); 12.57/71.87 = **17.5%** of
  the true ATE recovered at heavy spillover. All README/docs/dashboard prose
  reconciled to the regenerated JSONs.
- Fixed a wrong test assertion exposed by the corrected truth:
  `test_phase1_naive_ab_runs_and_returns_finite_estimate` asserted
  `true_ate > 0`, but seed 0 draws three of four zones below −1
  (elasticities [−1.97, −1.93, −1.57, −0.98], mean −1.61), so the price rise
  *lowers* revenue in aggregate (paired truth ≈ −19.8). The old assertion
  passed only because the old truth at that 192-cell config was Monte Carlo
  noise (MC SE ≈ 15).
- **Fixed a temporal-firewall leak in `pricelab/realdata.py`**: `week` used
  bare ISO week numbers, so on data spanning a year boundary (Dec 29–31 can be
  ISO week 1 of the *next* year) walk-forward folds trained on future trips
  (verified: 2/4 folds contaminated on a synthetic Dec–Jan frame). `week` is
  now year-qualified (`iso_year*100 + iso_week`, e.g. 202436). Phase 6
  regenerated: fold labels change, all pooled numbers identical (+0.533 min
  naive-vs-adjusted disagreement unchanged).
- Guards against silent NaN: `naive_effect` now rejects folds with <2 trips of
  either bike type; `simulate_continuous_price` rejects a non-positive diurnal
  pattern (large `diurnal_amplitude` used to fill log-quantity with NaN).
- **Tests 35 → 39**: truth stability across resample counts (fails under the
  old assignment-randomized truth), walk-forward year-boundary firewall,
  degenerate-fold guard, non-positive-diurnal guard.
- Reconciled `docs/DEVELOPMENT.md`, missed by the prose sweep above: stale
  test count (26 → 39) and suite timing (~1s → ~4s), dashboard tab count
  (4 → 8), `src/pricelab` tree missing `estimators/dml.py` and `realdata.py`,
  and a contributor step pointing at `_simulate_no_truth` — the rollout helper
  deleted by the truth rewrite. It now points at `_compute_true_ate` and warns
  that a new DGP knob must enter both potential-outcome legs.

### Added — cluster-aware regression-adjusted switchback — 2026-07-15

- Added `regression_adjusted_switchback_ate`: centered covariates plus treatment
  interactions, CR1 sandwich clustered at the randomized block, and a
  small-sample `t(n_blocks-2)` interval.
- Added `make phase2-adjusted` and deterministic 20-seed JSON/Markdown results.
  Honest verdict: median SE ratio 0.987, identical RMSE, and only 50–55%
  empirical coverage; daily zone/hour adjustment is not a material power gain.
- Added dashboard presentation and regression tests for precision, minimum
  cluster counts, finite-block inference metadata, and the Phase-4 estimator ID.
- Corrected “one-eighth” to the measured ratio: 12.57 / 70.65 = 17.8%.

### Added — dashboard tabs for Phases 4–6 — 2026-07-15

- `dashboard/app.py` grew three tabs that read **verbatim** from the committed
  results JSONs (no recomputation): **Phase 4** — per-replicate OLS-vs-DML
  bias strip plot (`st.scatter_chart`) + bias summary table from
  `phase4_dml.json`; **Phase 5** — per-replicate uplift distribution vs the
  oracle ceiling (`st.bar_chart`, grouped) + policy comparison table from
  `phase5_hetero.json`; **Phase 6** — per-fold naive vs walk-forward points
  with ±1.96·SE CIs + composition-diagnostics table from
  `phase6_realdata.json`. Each tab keeps the source file cited in its caption
  and carries the honest caveats from the corresponding `docs/results/*.md`.
- `load_results_json` now accepts dict-shaped results files (phases 4–6) in
  addition to list-shaped ones (phases 1–2); a missing/corrupt JSON degrades
  to an empty state pointing at the right `make phaseN` target.
- Stale About-tab text ("Phases 4–6 scheduled but not yet shipped") corrected.
- **Tests 26 → 31** (`tests/test_dashboard.py`): full-app health check via
  `streamlit.testing.v1.AppTest` (asserts no exception, so every tab renders
  against the committed JSONs), one direct run of each tab-builder function
  on its committed JSON, and a missing-file → `None` empty-state guard.
  Skips cleanly without the `[ui]` extra.
- HF Space unchanged by construction — `hf_space/app.py` star-imports
  `dashboard.app`; its README tagline reconciled to the committed Phase-2
  numbers (previous "28%" was untraceable to any results file).

### Added — Phases 4–6 (Double ML · heterogeneous pricing · real data) — 2026-07-12

- **Phase 4** — `simulate_continuous_price` (continuous log-price DGP, price
  confounded by zone × hour; binary designs untouched), `estimators/dml.py`
  (naive OLS vs `EconML.LinearDML`, linear nuisances, cv=3),
  `scripts/run_phase4_dml.py` + `make phase4` →
  `docs/results/phase4_dml.{json,md}`. **Measured (20 replicates, synthetic):**
  naive OLS estimated a *positive* elasticity in 20/20 replicates (mean bias
  +3.31, RMSE 3.31); DML mean bias −0.003, RMSE 0.027. EconML 0.16.0 was
  installed into the project venv (no fallback needed). RF nuisances were
  tried and attenuated the estimate on this n — noted in the module.
- **Phase 5** — `segment_elasticities` (`CausalForestDML`, zone one-hot X,
  hour controls) + bounded `scipy.optimize` revenue optimizer,
  `scripts/run_phase5_hetero.py` + `make phase5` →
  `docs/results/phase5_hetero.{json,md}`. **Measured (20 replicates,
  synthetic, ±30% price band):** segment-specific pricing recovers **+5.83%
  revenue [95% t-CI +4.32%, +7.33%]** over the best uniform price, vs a
  +6.00% oracle ceiling; per-zone elasticity MAE 0.066. Policies decided on
  estimates, scored on the true revenue surface.
- **Phase 6** — real data: `JC-202409-citibike-tripdata.csv.zip` (~4 MB,
  official Citi Bike S3 bucket; the full-NYC month file is ~414 MB, over the
  repo's 300 MB download cap) into gitignored `data/`.
  `src/pricelab/realdata.py` (walk-forward partialling-out: nuisances fit on
  past weeks only) + `scripts/run_phase6_realdata.py` + `make phase6` →
  `docs/results/phase6_realdata.{json,md}`. **Measured (115,201 trips,
  5 folds):** naive e-bike duration effect −1.61 min vs adjusted −2.15 min —
  a 0.53 min disagreement explained by member/casual composition (69.0% vs
  80.8% member share; members ride 7.9 min vs casuals 13.0 min). No price in
  the public feed → no elasticity claimed.
- **Tests 22 → 26** — one drift guard per new runner: continuous-DGP
  determinism, DML-beats-OLS (`requires_econml`), segment ≥ uniform revenue
  on the truth surface (`requires_econml`), walk-forward fold firewall +
  planted-effect recovery (tiny synthetic frame, no download needed).
- README: Phase 4/5/6 headline rows + "Why causal inference" section; badges
  updated (26 tests, phases 1–6).

### Added — Phase 3 (block-size sensitivity, RQ-P3 measured)

- `scripts/run_phase3_block_size.py` + `make phase3` — sweep
  `switchback_block_hours ∈ {1, 2, 4, 8, 24}` at fixed heavy spillover →
  `docs/results/phase3_block_size.{json,md}`. Deterministic, CPU, seconds.
- **Result overturned the pre-registered hypothesis:** bias vs. block size is
  *non-monotone* (`{1h: 5.5%, 2h: 2.4%, 4h: 366.5%, 8h: 1.3%, 24h: 2.2%}`) — a
  diurnal-**aliasing spike at `block_hours=4`**, not a graceful collapse toward
  naive A/B. RQ-P3 verdict, README, EVALUATION_REPORT, research_questions, and
  the dashboard Methodology tab all updated to report this honestly.

### Fixed — consistency / lint

- Reconciled stale numbers in `BUILD_PLAN.md`, `CHANGELOG.md`, and
  `CITATION.cff` to the committed `docs/results/*.json` (naive 14.4%→82.2%,
  switchback constant 2.2%, gap to −80pp; test count 17; version 0.1.0).
- Removed 3 unused imports flagged by ruff (`numpy` in `estimators/ate.py`,
  `field` in `simulation/marketplace.py`, `EstimatorComparison` in `api/main.py`).
- Dashboard Live-demo `switchback_block_hours` default 4 → 24 (4 aliases and
  shows ~509% switchback bias on a first click); added an explanatory caption.
- Corrected the wrong "use a divisor of 24" debug advice in `DEVELOPMENT.md`.

### Added — tests

- +5 fast tests (17 → 22): AB-log rejection by `switchback_ate(block_hours=24)`,
  `AteResult.ci95` = point ± 1.96·SE, true-ATE invariance to spillover,
  strict-alternation of `_assign_switchback`, naive-bias monotonicity in
  spillover. All assert structural/relational properties, not published values.

### Documentation (2026-05-05, same-day follow-up)

- `docs/architecture.md` — system diagram (ASCII + Mermaid: 3 diagrams covering two-design comparison, spillover mechanism, bias-vs-spillover headline).
- `docs/USAGE.md` — practical cookbook (smoke, sweeps, all 4 endpoints with curl examples, programmatic usage).
- `docs/API.md` — human-readable companion to `openapi.json` covering `ConfigOverrides`, all four endpoints, error model, env vars.
- `docs/DEVELOPMENT.md` — repo layout, estimator + DGP extension contracts, common debug paths.
- `docs/research_questions.md` — 5 pre-registered RQs with binary success criteria (P1/P2 measured; P3/P4/P5 planned).
- `docs/EVALUATION_REPORT.md` — TL;DR table + per-phase results + cross-method takeaway.
- README link bar updated with all the new docs.

---

## [0.1.0] — 2026-05-05 — Phases 1 & 2 shipped

### Added — simulation

- `simulation/marketplace.py` — synthetic two-sided marketplace DGP with
  heterogeneous elasticity by zone, diurnal demand multiplier, capacity
  caps, log-normal noise, and a tunable spillover-strength knob.
- A/B random and switchback assignment strategies.
- Closed-form true ATE for evaluation.

### Added — estimators

- `estimators/ate.py` — `naive_ab_ate` (difference-in-means) and
  `switchback_ate` (cluster-weighted Hájek with block-level SE).
- `AteResult` with point estimate, analytic SE, 95% CI, and bias helpers.

### Added — evaluation

- `evaluation/compare.py` — Phase-1 / Phase-2 head-to-head harness.
- `EstimatorComparison` dataclass for side-by-side reporting.

### Added — service

- `api/main.py` — FastAPI service: `/health`, `/v1/simulate`,
  `/v1/estimate/naive`, `/v1/estimate/switchback`, `/v1/compare`.
- `dashboard/app.py` — Streamlit demo (4 tabs).

### Added — measurement

- `scripts/run_phase1_naive_ab.py` — naive A/B sweep over spillover →
  `docs/results/phase1_naive_ab.{json,md}`.
- `scripts/run_phase2_switchback_compare.py` — switchback vs. naive
  head-to-head sweep → `docs/results/phase2_switchback_vs_naive.{json,md}`.
- `scripts/run_pricing_smoke.py` — end-to-end smoke with assertion.

### Tests

- 17 fast tests across simulation, estimators, evaluation harness, imports.

### Headline measured numbers

- Naive A/B bias scales **monotonically with spillover** — from 14.4% (no
  spillover) to 82.2% (`spillover_strength=0.70`).
- Switchback Hájek bias stays **constant at 2.2%** across the full spillover
  sweep.
- Gap at moderate spillover (`0.35`): **−49.1pp** (51.4% naive bias →
  2.2% switchback bias).

### Infrastructure

- `pyproject.toml` (`[dev]`, `[ui]`, `[causal]` extras), `.python-version`,
  `Makefile`, `LICENSE` (MIT), HF Spaces config, deployment doc.
