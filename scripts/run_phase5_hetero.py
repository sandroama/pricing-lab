"""Phase 5 — heterogeneous elasticity + revenue optimization (RQ-P5).

Per-zone (segment) elasticities estimated with EconML's CausalForestDML
(zone one-hot as the heterogeneity feature, hour dummies as controls), then a
bounded scipy revenue optimizer picks prices inside a ±30% band around the
reference price:

  - **uniform**: one price for the whole platform,
  - **segment**: one price per zone,
  - **oracle**: segment prices from the TRUE elasticities (the ceiling).

All policies are *decided* on estimates (except the oracle) and *evaluated*
on the true noise-free expected-revenue surface, so estimation error hurts
honestly. Counterfactual uplift of segment vs uniform pricing is reported
with a 95% t-CI over N_REPLICATES independent seeds. Synthetic, CPU,
deterministic. Regenerate with ``make phase5``.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy import optimize, stats

from pricelab.estimators.dml import segment_elasticities
from pricelab.simulation.marketplace import MarketplaceConfig, simulate_continuous_price

REPO = Path(__file__).resolve().parent.parent
RESULTS = REPO / "docs" / "results"

N_REPLICATES = 20
N_ZONES = 8
N_TIME_BUCKETS = 24 * 14
SEEDS = list(range(200, 200 + N_REPLICATES))
PRICE_BAND = (7.0, 13.0)  # ±30% around the reference price 10.0


def zone_revenue(price: float, scale: float, elasticity: float, p_ref: float) -> float:
    """Expected revenue of one zone at `price` under constant elasticity."""
    return price * scale * (price / p_ref) ** elasticity


def optimize_prices(
    scales: np.ndarray, elasticities: np.ndarray, p_ref: float
) -> tuple[np.ndarray, float]:
    """Per-zone bounded revenue-maximizing prices → (prices, uniform price).

    Constant-elasticity revenue is monotone in price on either side of
    |e| = 1, so per-zone optima sit at a band edge; the bounded scalar
    optimizer handles both cases uniformly (and the uniform-price problem,
    which mixes elastic and inelastic zones, has an interior optimum).
    """
    prices = np.array(
        [
            optimize.minimize_scalar(
                lambda p, z=z: -zone_revenue(p, scales[z], elasticities[z], p_ref),
                bounds=PRICE_BAND,
                method="bounded",
            ).x
            for z in range(len(scales))
        ]
    )
    uni = optimize.minimize_scalar(
        lambda p: -sum(
            zone_revenue(p, scales[z], elasticities[z], p_ref) for z in range(len(scales))
        ),
        bounds=PRICE_BAND,
        method="bounded",
    ).x
    return prices, float(uni)


def true_total_revenue(prices: np.ndarray, truth: dict) -> float:
    """Evaluate a price vector on the TRUE expected-revenue surface."""
    scales = np.asarray(truth["zone_scale"])
    elast = np.asarray(truth["elasticities"])
    return float(
        sum(
            zone_revenue(float(p), scales[z], elast[z], truth["price_ref"])
            for z, p in enumerate(prices)
        )
    )


def t_ci(values: np.ndarray, alpha: float = 0.05) -> tuple[float, float]:
    n = len(values)
    m = float(values.mean())
    half = float(stats.t.ppf(1 - alpha / 2, n - 1) * values.std(ddof=1) / np.sqrt(n))
    return (m - half, m + half)


def main() -> int:
    print(f"\n── Phase 5: segment vs uniform pricing, {N_REPLICATES} replicates\n")
    replicates: list[dict] = []
    for seed in SEEDS:
        cfg = MarketplaceConfig(n_zones=N_ZONES, n_time_buckets=N_TIME_BUCKETS, seed=seed)
        df, truth = simulate_continuous_price(cfg)

        # Estimated per-zone elasticity (CausalForestDML) + demand scale.
        e_hat = segment_elasticities(df, seed=seed)
        e_hat_arr = np.array([e_hat[z] for z in range(N_ZONES)])
        log_pref = np.log(truth["price_ref"])
        k_hat = np.array(
            [
                float(
                    np.exp(
                        (
                            df.loc[df["zone"] == z, "log_quantity"]
                            - e_hat[z] * (df.loc[df["zone"] == z, "log_price"] - log_pref)
                        ).mean()
                    )
                )
                for z in range(N_ZONES)
            ]
        )

        seg_prices, uni_price = optimize_prices(k_hat, e_hat_arr, truth["price_ref"])
        true_scales = np.asarray(truth["zone_scale"])
        true_elast = np.asarray(truth["elasticities"])
        oracle_prices, _ = optimize_prices(true_scales, true_elast, truth["price_ref"])

        rev_uni = true_total_revenue(np.full(N_ZONES, uni_price), truth)
        rev_seg = true_total_revenue(seg_prices, truth)
        rev_oracle = true_total_revenue(oracle_prices, truth)

        rep = {
            "seed": seed,
            "elasticities_true": truth["elasticities"],
            "elasticities_hat": e_hat_arr.tolist(),
            "segment_prices": seg_prices.tolist(),
            "uniform_price": uni_price,
            "oracle_prices": oracle_prices.tolist(),
            "revenue_uniform": rev_uni,
            "revenue_segment": rev_seg,
            "revenue_oracle": rev_oracle,
            "uplift_pct": 100.0 * (rev_seg - rev_uni) / rev_uni,
            "oracle_uplift_pct": 100.0 * (rev_oracle - rev_uni) / rev_uni,
        }
        replicates.append(rep)
        print(
            f"  seed={seed}  uniform_p={uni_price:5.2f}  "
            f"uplift={rep['uplift_pct']:+.2f}%  (oracle {rep['oracle_uplift_pct']:+.2f}%)"
        )

    uplift = np.array([r["uplift_pct"] for r in replicates])
    oracle = np.array([r["oracle_uplift_pct"] for r in replicates])
    up_lo, up_hi = t_ci(uplift)
    or_lo, or_hi = t_ci(oracle)
    mae = float(
        np.mean(
            [
                np.abs(np.array(r["elasticities_hat"]) - np.array(r["elasticities_true"])).mean()
                for r in replicates
            ]
        )
    )

    print(f"\n  segment vs uniform uplift: {uplift.mean():+.2f}%  CI [{up_lo:+.2f}, {up_hi:+.2f}]")
    print(f"  oracle ceiling           : {oracle.mean():+.2f}%  CI [{or_lo:+.2f}, {or_hi:+.2f}]")
    print(f"  per-zone elasticity MAE  : {mae:.3f}\n")

    RESULTS.mkdir(parents=True, exist_ok=True)
    payload = {
        "phase": 5,
        "n_replicates": N_REPLICATES,
        "n_zones": N_ZONES,
        "n_time_buckets": N_TIME_BUCKETS,
        "seeds": SEEDS,
        "price_band": list(PRICE_BAND),
        "estimator": "econml.dml.CausalForestDML (zone one-hot X, hour controls)",
        "uplift_pct_mean": float(uplift.mean()),
        "uplift_pct_ci95": [up_lo, up_hi],
        "oracle_uplift_pct_mean": float(oracle.mean()),
        "oracle_uplift_pct_ci95": [or_lo, or_hi],
        "elasticity_mae": mae,
        "replicates": replicates,
    }
    (RESULTS / "phase5_hetero.json").write_text(json.dumps(payload, indent=2) + "\n")

    md = [
        "# Phase 5 — heterogeneous elasticity + revenue optimization (RQ-P5)\n",
        f"**Synthetic** continuous-price DGP ({N_ZONES} zones with heterogeneous true "
        f"elasticities, {N_TIME_BUCKETS} hourly buckets, {N_REPLICATES} replicates). "
        "Per-zone elasticities estimated with `CausalForestDML`; a bounded scipy "
        f"optimizer picks prices in [{PRICE_BAND[0]:.0f}, {PRICE_BAND[1]:.0f}] "
        "(±30% band). Policies are chosen on *estimates* and scored on the *true* "
        "expected-revenue surface.\n",
        "| Policy | Revenue uplift vs uniform | 95% t-CI |",
        "|---|---:|---:|",
        f"| Segment-specific (estimated elasticities) | **{uplift.mean():+.2f}%** | "
        f"[{up_lo:+.2f}%, {up_hi:+.2f}%] |",
        f"| Oracle segment (true elasticities — ceiling) | {oracle.mean():+.2f}% | "
        f"[{or_lo:+.2f}%, {or_hi:+.2f}%] |",
        "",
        "## Verdict — measured",
        "",
        f"Segment-specific pricing recovers **{uplift.mean():+.2f}%** revenue "
        f"[95% CI {up_lo:+.2f}%, {up_hi:+.2f}%] over the best uniform price in this "
        f"simulation (n={N_REPLICATES} replicates), essentially matching the oracle "
        f"ceiling of {oracle.mean():+.2f}% — because CausalForestDML's per-zone "
        f"elasticity MAE is only {mae:.3f} on this DGP.",
        "",
        "Honest caveats: **synthetic**; the uplift magnitude is a function of the "
        "±30% price band and the elasticity spread knob — wider bands or wider "
        "elasticity heterogeneity mechanically increase it. The transferable claim "
        "is the *pipeline* (heterogeneous causal estimates → constrained optimizer "
        "→ counterfactual scoring), not the specific percentage.",
        "",
        "Per-replicate raw values: [`phase5_hetero.json`](phase5_hetero.json). "
        "Regenerate: `make phase5` (CPU, deterministic, seconds).",
    ]
    (RESULTS / "phase5_hetero.md").write_text("\n".join(md) + "\n")

    print(f"  → {(RESULTS / 'phase5_hetero.json').relative_to(REPO.parent)}")
    print(f"  → {(RESULTS / 'phase5_hetero.md').relative_to(REPO.parent)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
