"""Phase 2b — precision audit for regression-adjusted switchback inference.

Compare the original block-mean Hájek estimator with a centered Lin-style
outcome regression using zone and hour fixed effects. Both methods respect the
randomized block as the independent unit.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from pricelab.estimators.ate import (
    regression_adjusted_switchback_ate,
    switchback_ate,
)
from pricelab.simulation.marketplace import MarketplaceConfig, MarketplaceSimulator

REPO = Path(__file__).resolve().parent.parent
RESULTS = REPO / "docs" / "results"
SEEDS = list(range(200, 220))


def _summary(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=float)
    return {
        "mean": float(array.mean()),
        "median": float(np.median(array)),
        "min": float(array.min()),
        "max": float(array.max()),
    }


def main() -> int:
    rows: list[dict[str, Any]] = []
    print("\n── Phase 2b: regression-adjusted switchback precision audit\n")
    for seed in SEEDS:
        cfg = MarketplaceConfig(
            n_zones=8,
            n_time_buckets=24 * 28,
            spillover_strength=0.70,
            switchback_block_hours=24,
            seed=seed,
        )
        log = MarketplaceSimulator(cfg).simulate(design="switchback")
        hajek = switchback_ate(log.df, block_hours=24)
        adjusted = regression_adjusted_switchback_ate(log.df, block_hours=24)
        truth = log.true_ate_revenue
        rows.append(
            {
                "seed": seed,
                "true_ate": truth,
                "hajek": hajek.as_dict(),
                "adjusted": adjusted.as_dict(),
                "hajek_bias": hajek.bias_vs(truth),
                "adjusted_bias": adjusted.bias_vs(truth),
                "hajek_covers_truth": hajek.ci95[0] <= truth <= hajek.ci95[1],
                "adjusted_covers_truth": adjusted.ci95[0] <= truth <= adjusted.ci95[1],
                "se_ratio_adjusted_to_hajek": adjusted.standard_error / hajek.standard_error,
            }
        )

    ratios = [float(row["se_ratio_adjusted_to_hajek"]) for row in rows]
    hajek_se = [float(row["hajek"]["standard_error"]) for row in rows]
    adjusted_se = [float(row["adjusted"]["standard_error"]) for row in rows]
    hajek_bias = [float(row["hajek_bias"]) for row in rows]
    adjusted_bias = [float(row["adjusted_bias"]) for row in rows]
    median_ratio = float(np.median(ratios))
    hajek_se_summary = _summary(hajek_se)
    adjusted_se_summary = _summary(adjusted_se)
    ratio_summary = _summary(ratios)
    hajek_rmse = math.sqrt(float(np.mean(np.square(hajek_bias))))
    adjusted_rmse = math.sqrt(float(np.mean(np.square(adjusted_bias))))
    hajek_coverage = float(np.mean([row["hajek_covers_truth"] for row in rows]))
    adjusted_coverage = float(np.mean([row["adjusted_covers_truth"] for row in rows]))
    verdict = (
        "Adjustment produced a material clustered-SE reduction."
        if median_ratio <= 0.95
        else "Zone/hour adjustment did not materially improve precision for daily blocks."
    )
    artifact = {
        "phase": "2b",
        "design": "24-hour switchback; 28 randomized blocks; 8 zones",
        "n_replicates": len(rows),
        "estimators": ["switchback_hajek", "switchback_regression_adjusted"],
        "adjustment": "centered zone/hour fixed effects with treatment interactions",
        "uncertainty": "CR1 block-clustered sandwich; t(n_blocks-2) interval",
        "hajek_se": hajek_se_summary,
        "adjusted_se": adjusted_se_summary,
        "se_ratio_adjusted_to_hajek": ratio_summary,
        "hajek_rmse": hajek_rmse,
        "adjusted_rmse": adjusted_rmse,
        "hajek_coverage": hajek_coverage,
        "adjusted_coverage": adjusted_coverage,
        "verdict": verdict,
        "replicates": rows,
    }

    RESULTS.mkdir(parents=True, exist_ok=True)
    json_path = RESULTS / "phase2_regression_adjusted.json"
    md_path = RESULTS / "phase2_regression_adjusted.md"
    json_path.write_text(json.dumps(artifact, indent=2) + "\n")
    md_path.write_text(
        "\n".join(
            [
                "# Phase 2b — regression-adjusted switchback precision audit",
                "",
                "**Synthetic, deterministic, CPU-only.** Twenty independent 4-week "
                "switchback simulations; 28 daily randomized blocks and eight zones each.",
                "",
                "| Estimator | Mean clustered SE | RMSE | Empirical 95% coverage |",
                "|---|---:|---:|---:|",
                f"| Block-mean Hájek | {hajek_se_summary['mean']:.3f} | "
                f"{hajek_rmse:.3f} | {hajek_coverage:.1%} |",
                f"| Regression-adjusted | {adjusted_se_summary['mean']:.3f} | "
                f"{adjusted_rmse:.3f} | {adjusted_coverage:.1%} |",
                "",
                f"Median adjusted/Hájek SE ratio: **{median_ratio:.3f}**. {verdict}",
                "",
                "The adjusted model uses centered zone/hour fixed effects and treatment "
                "interactions. Its CR1 sandwich clusters at the randomized block and its "
                "95% interval uses `t(n_blocks-2)`, so cell count is not mistaken for "
                "independent experimental units.",
                "",
                "**Interpretation boundary.** Adjustment is a precision tool, not a repair "
                "for a biased assignment schedule. It cannot fix Phase 3's 4-hour diurnal "
                "aliasing; that requires stratified randomization or full-cycle blocks.",
                "",
            ]
        )
    )
    print(f"  median adjusted/Hájek SE ratio: {median_ratio:.3f}")
    print(f"  {verdict}")
    print(f"  → {json_path.relative_to(REPO.parent)}")
    print(f"  → {md_path.relative_to(REPO.parent)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
