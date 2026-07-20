# Usage — pricing-lab

Practical cookbook. For *what is this* see [`README.md`](../README.md);
for *how is it built* see [`architecture.md`](architecture.md); for
*what was measured* see [`EVALUATION_REPORT.md`](EVALUATION_REPORT.md).

## Setup (one-time)

```bash
git clone https://github.com/sandroama/pricing-lab.git && cd pricing-lab
python3.12 -m venv .venv && source .venv/bin/activate
make install-dev
```

CPU-only, no model downloads. Whole thing runs in <2 seconds for the
default config.

## Common workflows

### 1. Run the smoke test (≤2s, asserts the headline)

```bash
make smoke
```

Runs Phase 1 (naive A/B baseline) and Phase 2 (switchback head-to-head)
at the strong-spillover regime (4 weeks × 0.80 spillover) and **asserts
switchback bias < naive bias**. Exits non-zero if the headline ever
regresses.

### 2. Run the spillover sweep

```bash
make phase1     # writes docs/results/phase1_naive_ab.{json,md}
make phase2     # writes docs/results/phase2_switchback_vs_naive.{json,md}
make phase3     # writes docs/results/phase3_block_size.{json,md}
```

Phase 1 isolates naive A/B; Phase 2 runs both estimators side-by-side;
Phase 3 sweeps the switchback block size at fixed heavy spillover. Each
writes its results into `docs/results/`.

### 3. Live demo

```bash
make api     # FastAPI on http://localhost:8000/docs
make ui      # Streamlit on http://localhost:8501
```

The dashboard has 4 tabs:
- **Live demo** — set knobs (spillover, zones, time, block hours), run a
  head-to-head, see bias per estimator with 95% CIs.
- **Phase-2 sweep** — load the JSON written by `make phase2`, plot
  bias-vs-spillover curves.
- **Methodology** — short prose with the SUTVA / switchback story.
- **About** — project context within the portfolio.

### 4. Simulate a marketplace

```bash
curl -X POST http://localhost:8000/v1/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "design": "switchback",
    "overrides": {"spillover_strength": 0.50, "n_time_buckets": 672}
  }'
```

Returns:
```json
{
  "n_rows": 5376,
  "true_ate_revenue": 71.87,
  "cfg": {...},
  "summary": {
    "n_treatment": 2688,
    "n_control": 2688,
    "mean_revenue_treatment": 1023.4,
    "mean_revenue_control": 954.3
  }
}
```

### 5. Estimate ATE under each design

```bash
# Naive A/B on a fresh sim — biased by spillover
curl -X POST http://localhost:8000/v1/estimate/naive \
  -H "Content-Type: application/json" \
  -d '{"overrides": {"spillover_strength": 0.50}}'

# Switchback Hájek on a fresh sim — ~unbiased
curl -X POST http://localhost:8000/v1/estimate/switchback \
  -H "Content-Type: application/json" -d '{}'
```

### 6. Run the head-to-head in one call

```bash
curl -X POST http://localhost:8000/v1/compare \
  -H "Content-Type: application/json" \
  -d '{"overrides": {"spillover_strength": 0.80, "n_time_buckets": 672}}'
```

Returns both estimator results plus the truth — exactly what the
dashboard's "Live demo" tab calls under the hood.

### 7. Programmatic usage

```python
from pricelab.simulation import MarketplaceConfig, MarketplaceSimulator
from pricelab.estimators import naive_ab_ate, switchback_ate

cfg = MarketplaceConfig(spillover_strength=0.50, seed=42)
sim = MarketplaceSimulator(cfg)
log_ab = sim.simulate(design="ab_random")
log_sb = MarketplaceSimulator(cfg).simulate(design="switchback")

print(f"true ATE = {log_ab.true_ate_revenue:.2f}")
print(naive_ab_ate(log_ab.df))
print(switchback_ate(log_sb.df, block_hours=cfg.switchback_block_hours))
```

## Tips

- **Strong spillover + long horizon is the regime where the win is real.**
  At `n_time_buckets=168` (1 week) you only get 7 switchback blocks and
  finite-sample variance can dominate. The defaults use 4 weeks (168 ×
  4 = 672 buckets).
- **Switchback `block_hours=24` is intentional**, not arbitrary. Each
  block spans an integer number of diurnal cycles so block-mean revenue
  isn't biased by which hours fell in the treatment block. Phase 3
  (`make phase3`) swept block size and found the trade-off is *not* a
  smooth dial: a sub-day block like `block_hours=4` aliases with the
  diurnal cycle and blows bias up to ~359% — see
  [`results/phase3_block_size.md`](results/phase3_block_size.md).
- **The "true ATE" is a paired potential-outcome contrast** — both prices
  evaluated on the same noise draws (common random numbers), no spillover,
  elasticities held fixed (`_compute_true_ate`, MC SE ≈ 0.12). That's the treatment
  effect an unbiased estimator should recover; it includes capacity-
  binding noise but excludes the SUTVA violation.
- **Both designs share the seed.** Naive A/B and switchback runs aren't
  identical samples — they assign treatment differently — but they share
  the *same* DGP parameters, so the comparison is structurally clean.
- **`AteResult.bias_pct(true_ate)`** is the canonical metric; the
  marketing claims (16%, 82%, 3.9%) all come from this.
