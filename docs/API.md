# API Reference — pricing-lab

OpenAPI 3.1 spec at [`openapi.json`](openapi.json) and live at
`http://localhost:8000/openapi.json`. Swagger UI:
`http://localhost:8000/docs`.

**Base URL**: `http://localhost:8000`.
**Auth**: none in dev.
**State**: pure stateless. Each request rebuilds the simulator from
config overrides.

---

## `GET /health` · meta

Liveness probe.

**Response 200** — `HealthResponse`
```json
{"status": "ok", "version": "0.1.0"}
```

---

## Shared schema — `ConfigOverrides`

Every estimation endpoint accepts the same partial overrides body. Any
field omitted falls back to `MarketplaceConfig`'s default.

| Field | Type | Range | Effect |
|---|---|---|---|
| `n_zones` | int | `[2, 64]` | Number of marketplace zones (spatial cells). |
| `n_time_buckets` | int | `[24, 720]` | Hours of simulated history. |
| `spillover_strength` | float | `[0.0, 1.0]` | Fraction of lost demand that leaks to a lower-priced neighbor. |
| `price_control` | float | `> 0` | Control-arm price. |
| `price_treatment` | float | `> 0` | Treatment-arm price. |
| `switchback_block_hours` | int | `[1, 72]` | Block size for switchback design. |
| `seed` | int | any | RNG seed. |

---

## `POST /v1/simulate` · simulation

Run the marketplace DGP under one design, return per-row count + summary
stats + the Monte-Carlo true ATE.

**Request** — `SimulateRequest`
| Field | Type | Required | Notes |
|---|---|---|---|
| `design` | string | ✓ | `"ab_random"` or `"switchback"` |
| `overrides` | `ConfigOverrides` | — | Partial config |

**Response 200** — `SimulateResponse`
| Field | Type | Notes |
|---|---|---|
| `n_rows` | int | `n_zones × n_time_buckets` |
| `true_ate_revenue` | float | The truth to recover. |
| `cfg` | dict | Resolved config (all knobs, including defaults). |
| `summary` | dict | `{n_treatment, n_control, mean_revenue_treatment, mean_revenue_control}` |

**Errors** — `422` if `design` is not in `{"ab_random", "switchback"}`.

---

## `POST /v1/estimate/naive` · estimation

Simulate the marketplace under **A/B random** assignment, then estimate
ATE via difference-in-means. The bias-vs-truth fields tell the headline
story (positive `bias_pct` = under-estimating the true ATE).

**Request** — `EstimateRequest`
```json
{"overrides": {"spillover_strength": 0.50}}
```

**Response 200**
```json
{
  "estimator": "naive_ab_diff_in_means",
  "point_estimate": 24.46,
  "standard_error": 14.16,
  "ci95_low": -3.30,
  "ci95_high": 52.22,
  "n_treatment": 2691,
  "n_control": 2685,
  "true_ate": 71.87,
  "bias": -47.41,
  "bias_pct": 0.660
}
```

---

## `POST /v1/estimate/switchback` · estimation

Simulate the marketplace under **switchback** assignment (balanced
alternation with `block_hours` block size), then estimate ATE via
clustered Hájek. Returns the same schema as `/v1/estimate/naive`.

**Response 200**
```json
{
  "estimator": "switchback_hajek",
  "point_estimate": 69.06,
  "standard_error": 2.03,
  "ci95_low": 65.08,
  "ci95_high": 73.04,
  "n_treatment": 14,
  "n_control": 14,
  "true_ate": 71.87,
  "bias": -2.80,
  "bias_pct": 0.039
}
```

`n_treatment` / `n_control` here are **block counts**, not cell counts —
the Hájek estimator collapses each block to one observation.

---

## `POST /v1/compare` · estimation

End-to-end Phase-2 head-to-head in one call. Runs both designs, both
estimators, returns the truth + both bias measurements.

**Response 200** — `CompareResponse`
| Field | Type | Notes |
|---|---|---|
| `true_ate` | float | Truth (paired potential-outcome Monte Carlo, common random numbers). |
| `estimators` | array | One row per estimator with point, SE, CI, bias, `covers_truth`. |
| `cfg` | dict | Resolved config. |

Example response with `spillover_strength=0.70`:
```json
{
  "true_ate": 71.87,
  "estimators": [
    {"estimator": "naive_ab_diff_in_means", "point_estimate": 12.57,
     "bias_pct": 0.825, "covers_truth": false, ...},
    {"estimator": "switchback_hajek", "point_estimate": 69.06,
     "bias_pct": 0.039, "covers_truth": true, ...}
  ],
  "cfg": {...}
}
```

---

## Error model

Standard FastAPI envelope:
```json
{"detail": "unknown design: ..."}
```

| Status | Meaning |
|---|---|
| `200` | Success |
| `422` | Pydantic validation failure (e.g. unknown design, out-of-range knob) |
| `500` | Internal pipeline error |

---

## Regenerating this file

```bash
# from projects/
make openapi   # writes openapi.json for all FastAPI services including pricing-lab
```
