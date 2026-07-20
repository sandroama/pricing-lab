"""Phase 4 — Double ML for continuous-price elasticity (RQ-P4).

Continuous-price DGP where the platform's pricing policy is confounded by
zone × time-of-day demand (higher prices exactly when/where demand is high).
Compares naive OLS log-log elasticity against cross-fitted LinearDML
(EconML, linear nuisances on hour + zone dummies) across N_REPLICATES
independent seeds. Per-seed elasticities are redrawn, so the replicate
spread covers DGP variation, not just noise.

Reported per estimator: mean bias, RMSE, and a 95% t-CI over replicates.
Everything is synthetic, deterministic given the seed list, CPU-only,
seconds to run. Regenerate with ``make phase4``.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy import stats

from pricelab.estimators.dml import dml_elasticity, ols_elasticity
from pricelab.simulation.marketplace import MarketplaceConfig, simulate_continuous_price

REPO = Path(__file__).resolve().parent.parent
RESULTS = REPO / "docs" / "results"

N_REPLICATES = 20
N_ZONES = 8
N_TIME_BUCKETS = 24 * 14  # 2 weeks of hourly buckets → 2 688 rows per replicate
SEEDS = list(range(100, 100 + N_REPLICATES))


def t_ci(values: np.ndarray, alpha: float = 0.05) -> tuple[float, float]:
    """95% t-interval for the mean of `values`."""
    n = len(values)
    m = float(values.mean())
    half = float(stats.t.ppf(1 - alpha / 2, n - 1) * values.std(ddof=1) / np.sqrt(n))
    return (m - half, m + half)


def summarize(biases: np.ndarray) -> dict:
    lo, hi = t_ci(biases)
    return {
        "mean_bias": float(biases.mean()),
        "rmse": float(np.sqrt((biases**2).mean())),
        "bias_ci95_low": lo,
        "bias_ci95_high": hi,
        "n_replicates": len(biases),
    }


def main() -> int:
    print(f"\n── Phase 4: naive OLS vs LinearDML elasticity, {N_REPLICATES} replicates\n")
    replicates: list[dict] = []
    for seed in SEEDS:
        cfg = MarketplaceConfig(n_zones=N_ZONES, n_time_buckets=N_TIME_BUCKETS, seed=seed)
        df, truth = simulate_continuous_price(cfg)
        ols = ols_elasticity(df)
        dml = dml_elasticity(df, seed=seed)
        rep = {
            "seed": seed,
            "true_mean_elasticity": truth["mean_elasticity"],
            "ols": ols.as_dict(),
            "dml": dml.as_dict(),
            "ols_bias": ols.point_estimate - truth["mean_elasticity"],
            "dml_bias": dml.point_estimate - truth["mean_elasticity"],
        }
        replicates.append(rep)
        print(
            f"  seed={seed}  truth={truth['mean_elasticity']:+.3f}  "
            f"ols={ols.point_estimate:+.3f} (bias {rep['ols_bias']:+.3f})  "
            f"dml={dml.point_estimate:+.3f} (bias {rep['dml_bias']:+.3f})"
        )

    ols_b = np.array([r["ols_bias"] for r in replicates])
    dml_b = np.array([r["dml_bias"] for r in replicates])
    ols_s, dml_s = summarize(ols_b), summarize(dml_b)
    sign_flips = int(sum(r["ols"]["point_estimate"] > 0 for r in replicates))

    print(
        f"\n  OLS : mean bias {ols_s['mean_bias']:+.3f}  RMSE {ols_s['rmse']:.3f}  "
        f"CI [{ols_s['bias_ci95_low']:+.3f}, {ols_s['bias_ci95_high']:+.3f}]"
    )
    print(
        f"  DML : mean bias {dml_s['mean_bias']:+.3f}  RMSE {dml_s['rmse']:.3f}  "
        f"CI [{dml_s['bias_ci95_low']:+.3f}, {dml_s['bias_ci95_high']:+.3f}]"
    )
    print(f"  OLS estimated a POSITIVE elasticity in {sign_flips}/{N_REPLICATES} replicates\n")

    RESULTS.mkdir(parents=True, exist_ok=True)
    payload = {
        "phase": 4,
        "estimand": "mean log-log price elasticity (per-zone mean)",
        "n_replicates": N_REPLICATES,
        "n_zones": N_ZONES,
        "n_time_buckets": N_TIME_BUCKETS,
        "rows_per_replicate": N_ZONES * N_TIME_BUCKETS,
        "seeds": SEEDS,
        "dml_library": "econml.dml.LinearDML (linear nuisances, cv=3)",
        "dml_estimator_id": "linear_dml",
        "dml_nuisance_models": "sklearn.linear_model.LinearRegression",
        "ols_summary": ols_s,
        "dml_summary": dml_s,
        "ols_positive_sign_count": sign_flips,
        "replicates": replicates,
    }
    out_json = RESULTS / "phase4_dml.json"
    out_json.write_text(json.dumps(payload, indent=2) + "\n")

    mean_truth = float(np.mean([r["true_mean_elasticity"] for r in replicates]))
    md = [
        "# Phase 4 — Double ML for continuous-price elasticity (RQ-P4)\n",
        f"**Synthetic** continuous-price DGP, price confounded by zone × hour-of-day "
        f"(the platform charges more when demand is high). {N_REPLICATES} replicates, "
        f"independent seeds (elasticities redrawn per seed; mean truth ≈ {mean_truth:.2f}), "
        f"{N_ZONES} zones × {N_TIME_BUCKETS} hourly buckets = "
        f"{N_ZONES * N_TIME_BUCKETS} rows per replicate. "
        "No spillover / capacity cap in this variant — Phase 4 isolates *confounding* "
        "bias (Phases 1–3 covered interference).\n",
        "| Estimator | Mean bias | RMSE | 95% t-CI on bias |",
        "|---|---:|---:|---:|",
        f"| Naive OLS (log-log, no controls) | {ols_s['mean_bias']:+.3f} | {ols_s['rmse']:.3f} | "
        f"[{ols_s['bias_ci95_low']:+.3f}, {ols_s['bias_ci95_high']:+.3f}] |",
        f"| LinearDML (EconML, hour+zone controls) | {dml_s['mean_bias']:+.3f} | {dml_s['rmse']:.3f} | "
        f"[{dml_s['bias_ci95_low']:+.3f}, {dml_s['bias_ci95_high']:+.3f}] |",
        "",
        "## Verdict — measured",
        "",
        f"Naive OLS doesn't just miss the elasticity — it got the **sign wrong in "
        f"{sign_flips}/{N_REPLICATES} replicates** (estimated demand sloping *upward* in "
        "price), because the pricing policy raises prices exactly when demand is high. "
        f"Cross-fitted DML with hour + zone controls recovers the truth with mean bias "
        f"{dml_s['mean_bias']:+.3f} and RMSE {dml_s['rmse']:.3f} (elasticity units, "
        f"truth ≈ {mean_truth:.2f}).",
        "",
        "Honest caveats: linear nuisance models are *correctly specified* for this DGP "
        "(additive in hour/zone dummies) — real data won't be that kind. Random-forest "
        "nuisances were tried first and attenuated the estimate on this small n; that "
        "trade-off is noted in `estimators/dml.py`.",
        "",
        "Per-replicate raw estimates: [`phase4_dml.json`](phase4_dml.json). "
        "Regenerate: `make phase4` (CPU, deterministic, seconds).",
    ]
    (RESULTS / "phase4_dml.md").write_text("\n".join(md) + "\n")

    print(f"  → {out_json.relative_to(REPO.parent)}")
    print(f"  → {(RESULTS / 'phase4_dml.md').relative_to(REPO.parent)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
