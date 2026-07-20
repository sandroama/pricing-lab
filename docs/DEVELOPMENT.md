# Development — pricing-lab

Targeted at: a contributor reading the repo cold, or future-me coming back
after a month.

## Repository layout

```
pricing-lab/
├── src/pricelab/
│   ├── simulation/marketplace.py    # MarketplaceConfig · MarketplaceSimulator · SimulationLog · simulate_continuous_price
│   ├── estimators/ate.py            # naive_ab_ate · switchback_ate · regression_adjusted_switchback_ate · AteResult
│   ├── estimators/dml.py            # Phase-4/5 naive OLS + EconML DML elasticity
│   ├── evaluation/compare.py        # Phase-1 / Phase-2 head-to-head harness
│   ├── realdata.py                  # Phase-6 Citi Bike walk-forward partialling-out
│   └── api/main.py                  # FastAPI service
├── dashboard/app.py                 # Streamlit demo (8 tabs)
├── scripts/                         # smoke + phase runners
├── tests/                           # pytest (39 fast tests)
├── configs/                         # (reserved for Phase-3 Hydra configs)
└── docs/                            # this folder
```

Import direction is enforced:
**simulation → estimators → evaluation → api/dashboard**. No back-edges.

## Running tests

```bash
make test                       # full suite, 39 tests (~4s on CPU)
pytest tests/ -v
pytest tests/test_estimators.py::test_phase2_switchback_beats_naive_under_strong_spillover -v
```

Markers:
- `slow` — anything that takes >2s; currently none.
- `requires_econml` — Phase 4 will introduce these.

## Adding a new estimator

The contract is simple — return an `AteResult`:

```python
from pricelab.estimators.ate import AteResult

def my_dml_estimator(df, *, outcome="revenue", confounders=("zone", "diurnal")) -> AteResult:
    # ...your math here...
    return AteResult(
        estimator="dml",
        point_estimate=float(point),
        standard_error=float(se),
        n_treatment=int(n_t),
        n_control=int(n_c),
    )
```

Then:
1. Add unit tests under `tests/test_estimators.py` exercising:
   - Recovery on a synthetic dataset where you know the truth.
   - Behavior on the rejected-input cases (bad columns, all-same
     treatment).
2. Wire into `evaluation/compare.py` if you want it in the
   head-to-head harness.
3. Add a runner script `scripts/run_phaseN_my_estimator.py` that emits
   `docs/results/phaseN_my_estimator.{json,md}`.

## Adding a new DGP feature

The simulator is centralized in `simulation/marketplace.py`. To add
something like cross-zone elasticity or weekly seasonality:

1. Extend `MarketplaceConfig` with the new knob.
2. Update `_build_*` helpers if it needs precomputation.
3. Update `_compute_true_ate` so the ground truth stays consistent. It
   evaluates both potential outcomes on one noise draw (common random
   numbers), so a new knob must be added to *both* the `demand_c` and
   `demand_t` legs or the paired difference will silently misstate the truth.
4. Add a unit test in `tests/test_simulation.py` that asserts the new
   knob has the expected qualitative effect (e.g., raising it should
   raise / lower X).

## Common debug paths

| Symptom | Likely cause | Fix |
|---|---|---|
| `make smoke` fails the assertion | Switchback under-powered for the regime | Raise `n_time_buckets` (more blocks) or `spillover_strength` (bigger naive bias) |
| Naive A/B bias seems too small | Spillover is too weak to detect at this sample size | Use `n_time_buckets ≥ 24 × 14` (2+ weeks) |
| Switchback bias seems too large | Sub-day block aliases with the 24h diurnal cycle | Being a divisor of 24 is **not** sufficient — `block_hours=4` is a divisor yet blows up (>360% bias) because strict `T C T C` alternation lands treatment on a fixed phase of the diurnal cycle (verified: mean diurnal 1.177 under T vs 0.823 under C at block=4), confounding the estimate. Keep `block_hours=24` (a full diurnal cycle) for unbiasedness; sub-day blocks would need hour-of-day stratification (the Phase 3 topic, `docs/results/phase3_block_size.md`) |
| `true_ate` is hugely different from `naive_estimate` *without* spillover | Capacity binding is unequal between T and C | Loosen `capacity_multiplier` |
| `switchback_ate` errors "mixed within-block treatment" | Block size doesn't divide `n_time_buckets` evenly OR you fed it an A/B random log | Use the switchback design log, not the A/B random one |
| `/v1/estimate/switchback` returns identical numbers across requests | Config is deterministic given `seed` | Vary the `seed` knob in overrides |
| Streamlit "Phase-2 sweep" tab is empty | `phase2_switchback_vs_naive.json` not generated | `make phase2` first |

## State-store scope note

The FastAPI service is **stateless**. Every request rebuilds the simulator
and runs from scratch. For production-style replay or experiment-tracking,
you'd add a thin store layer:

1. `experiments/store.py` — `save_run(cfg, results)`, `load_run(run_id)`.
2. Implementations: `InMemoryStore`, `SQLiteStore`, `MLflowStore`.
3. Add `/v1/runs` endpoints (list, get, replay) backed by the store.

This is intentionally scoped out of Phase 1–2 because the deliverable is
the *methodology*, not the experiment-tracking infra.

## Coding standards

- `ruff format` + `ruff check` (line length 100, target Python 3.11+).
- `mypy --strict` on `src/`.
- All cross-stage data uses Pydantic / `@dataclass(frozen=True)` for
  immutability where it costs nothing.
- `loguru.logger`; no `print()` in library code (scripts can print
  freely — they're terminal-facing).
- All randomness threaded through `numpy.random.default_rng(seed)` —
  never the global RNG.

## CI

`.github/workflows/ci.yml` runs:
1. `pip install -e ".[dev]"`
2. `ruff check src tests scripts dashboard`
3. `pytest tests/ -v`
4. `python scripts/run_pricing_smoke.py`

CI fails if the headline assertion (switchback bias < naive bias under
strong spillover) regresses.

## Where to look first when debugging a regression

1. `tests/test_estimators.py::test_phase2_switchback_beats_naive_under_strong_spillover` — the canary.
2. `docs/results/phase2_switchback_vs_naive.json` — has the bias gap
   shrunk vs. the last commit?
3. `MarketplaceSimulator._compute_true_ate` — did someone change the DGP
   in a way that moved the truth without updating the test thresholds?
4. `evaluation/compare.py` — both designs should share the same `cfg`;
   if one is using stale parameters, the comparison is meaningless.
