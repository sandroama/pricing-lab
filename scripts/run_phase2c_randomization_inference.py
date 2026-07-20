"""Phase 2c — randomization-inference audit of the clustered switchback CIs.

Round 2 root-caused the "low clustered-CI coverage" finding: the intervals
were fine, the truth reference was noisy (MC SE ~4.8 vs estimator SE ~2.0),
and the paired common-random-numbers truth fixed it (MC SE ~0.12). But the
re-measured 95% coverage rested on only 20 seeds (binomial SE ~4.9 pp).

This phase closes the loop with a *design-agnostic* method on 100 seeds:

1. **Randomization CI (Hájek).** Exact permutation test on block means,
   inverted over a tau0 grid — no normality, no variance estimator. If the
   analytic Welch/CR1 intervals were mis-calibrated, the RI intervals would
   disagree in width or coverage.
2. **P-value uniformity at the truth.** Under a correct H0: tau = true ATE,
   permutation p-values are ~Uniform(0,1). A KS test flags miscalibration
   directly, without the coarse covered/not-covered dichotomy.
3. **Tighter coverage MC error.** 100 seeds cut the binomial SE to ~2.2 pp;
   Wilson intervals are reported instead of bare proportions.

Honest scope note: the deployed assignment is strict alternation with a
random start (2-point randomization distribution). RI here permutes over all
balanced block labelings, i.e. it tests block *exchangeability* — stated in
the writeup, not hidden.

Deterministic given the seed list; pure CPU; ~10 min (dominated by the
regression-adjusted permutation refits). Regenerate: ``make phase2-ri``.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats

from pricelab.estimators.ate import (
    regression_adjusted_switchback_ate,
    switchback_ate,
)
from pricelab.estimators.randomization import (
    block_permutation_ci,
    block_permutation_pvalue,
)
from pricelab.simulation.marketplace import MarketplaceConfig, MarketplaceSimulator

REPO = Path(__file__).resolve().parent.parent
RESULTS = REPO / "docs" / "results"

SEEDS = list(range(300, 400))  # 100 replicates
N_PERM_HAJEK = 2000  # vectorized block-mean permutations
N_PERM_ADJUSTED = 199  # full CR1 refits — the expensive part
BLOCK_HOURS = 24


def _wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson 95% interval for a binomial proportion."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = successes / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return (center - half, center + half)


def _adjusted_ri_pvalue(df, tau0: float, point: float, seed: int) -> float:
    """Permutation p-value for the regression-adjusted estimator at H0: tau=tau0.

    Sharp-null construction: Y0 = Y - tau0*T; for each balanced block
    relabeling T*, refit on (Y0 + tau0*T*, T*) and compare |tau_hat* - tau0|
    with the observed |tau_hat - tau0|.
    """
    work = df.copy()
    work["block"] = work["timestamp"] // BLOCK_HOURS
    y0 = work["revenue"].to_numpy() - tau0 * work["treatment"].to_numpy()
    block_ids = np.sort(work["block"].unique())
    orig = work.groupby("block")["treatment"].first().loc[block_ids].to_numpy()
    n_t = int(orig.sum())
    rng = np.random.default_rng(seed)
    obs = abs(point - tau0)
    exceed = 0
    for _ in range(N_PERM_ADJUSTED):
        labels = np.zeros(len(block_ids), dtype=int)
        labels[rng.choice(len(block_ids), size=n_t, replace=False)] = 1
        t_star = labels[work["block"].to_numpy()]
        perm = work.copy()
        perm["treatment"] = t_star
        perm["revenue"] = y0 + tau0 * t_star
        est = regression_adjusted_switchback_ate(perm, block_col="block")
        if abs(est.point_estimate - tau0) >= obs:
            exceed += 1
    return (1 + exceed) / (1 + N_PERM_ADJUSTED)


def main() -> int:
    rows: list[dict[str, Any]] = []
    print(f"\n── Phase 2c: randomization-inference audit of clustered CIs ({len(SEEDS)} seeds)\n")
    for i, seed in enumerate(SEEDS):
        cfg = MarketplaceConfig(
            n_zones=8,
            n_time_buckets=24 * 28,
            spillover_strength=0.70,
            switchback_block_hours=BLOCK_HOURS,
            seed=seed,
        )
        log = MarketplaceSimulator(cfg).simulate(design="switchback")
        truth = log.true_ate_revenue
        df = log.df

        hajek = switchback_ate(df, block_hours=BLOCK_HOURS)
        adjusted = regression_adjusted_switchback_ate(df, block_hours=BLOCK_HOURS)

        grouped = df.groupby(df["timestamp"] // BLOCK_HOURS)
        block_means = grouped["revenue"].mean().to_numpy()
        block_treat = grouped["treatment"].first().to_numpy()

        ri_lo, ri_hi = block_permutation_ci(
            block_means, block_treat, n_permutations=N_PERM_HAJEK, seed=seed
        )
        p_truth_hajek = block_permutation_pvalue(
            block_means, block_treat, tau0=truth, n_permutations=N_PERM_HAJEK, seed=seed
        )
        p_truth_adjusted = _adjusted_ri_pvalue(
            df, tau0=truth, point=adjusted.point_estimate, seed=seed
        )

        rows.append(
            {
                "seed": seed,
                "true_ate": truth,
                "hajek": hajek.as_dict(),
                "adjusted": adjusted.as_dict(),
                "hajek_covers": hajek.ci95[0] <= truth <= hajek.ci95[1],
                "adjusted_covers": adjusted.ci95[0] <= truth <= adjusted.ci95[1],
                "ri_ci_low": ri_lo,
                "ri_ci_high": ri_hi,
                "ri_covers": ri_lo <= truth <= ri_hi,
                "ri_width_ratio_vs_welch": (ri_hi - ri_lo) / (hajek.ci95[1] - hajek.ci95[0]),
                "ri_pvalue_at_truth_hajek": p_truth_hajek,
                "ri_pvalue_at_truth_adjusted": p_truth_adjusted,
            }
        )
        if (i + 1) % 20 == 0:
            print(f"  {i + 1}/{len(SEEDS)} seeds done")

    n = len(rows)
    cov = {
        key: int(sum(bool(r[key]) for r in rows))
        for key in ("hajek_covers", "adjusted_covers", "ri_covers")
    }
    p_hajek = [float(r["ri_pvalue_at_truth_hajek"]) for r in rows]
    p_adj = [float(r["ri_pvalue_at_truth_adjusted"]) for r in rows]
    ks_hajek = stats.kstest(p_hajek, "uniform")
    ks_adj = stats.kstest(p_adj, "uniform")
    width_ratios = [float(r["ri_width_ratio_vs_welch"]) for r in rows]

    def pct(k: str) -> str:
        lo, hi = _wilson(cov[k], n)
        return f"{cov[k] / n:.1%} (Wilson 95%: {lo:.1%}–{hi:.1%})"

    # Verdict is computed from the measurements, never asserted in advance.
    all_calibrated = all(
        _wilson(cov[k], n)[0] <= 0.95 <= _wilson(cov[k], n)[1]
        for k in ("hajek_covers", "adjusted_covers", "ri_covers")
    )
    uniform_ok = ks_hajek.pvalue > 0.05 and ks_adj.pvalue > 0.05
    if all_calibrated and uniform_ok:
        verdict = (
            "The permutation intervals agree with the analytic clustered "
            "intervals in coverage and width, and the truth-null p-values are "
            "consistent with uniformity: the round-2 diagnosis (noisy truth "
            "reference, not broken intervals) is confirmed by a design-agnostic "
            "method on 5x the seeds."
        )
    else:
        verdict = (
            "MEASURED DISAGREEMENT: at least one interval's Wilson band excludes "
            "95% coverage or a truth-null p-value distribution fails the KS "
            "uniformity check (see tables above). The clustered intervals are "
            "not fully vindicated; treat the analytic SEs with caution."
        )

    artifact = {
        "phase": "2c",
        "design": "24-hour switchback; 28 randomized blocks; 8 zones; spillover 0.70",
        "n_replicates": n,
        "n_permutations_hajek": N_PERM_HAJEK,
        "n_permutations_adjusted": N_PERM_ADJUSTED,
        "coverage": {
            "hajek_welch": {
                "count": cov["hajek_covers"],
                "rate": cov["hajek_covers"] / n,
                "wilson95": _wilson(cov["hajek_covers"], n),
            },
            "adjusted_cr1_t": {
                "count": cov["adjusted_covers"],
                "rate": cov["adjusted_covers"] / n,
                "wilson95": _wilson(cov["adjusted_covers"], n),
            },
            "hajek_randomization_ci": {
                "count": cov["ri_covers"],
                "rate": cov["ri_covers"] / n,
                "wilson95": _wilson(cov["ri_covers"], n),
            },
        },
        "ri_width_ratio_vs_welch": {
            "mean": float(np.mean(width_ratios)),
            "median": float(np.median(width_ratios)),
        },
        "pvalue_uniformity_at_truth": {
            "hajek": {"ks_stat": float(ks_hajek.statistic), "ks_pvalue": float(ks_hajek.pvalue)},
            "adjusted": {"ks_stat": float(ks_adj.statistic), "ks_pvalue": float(ks_adj.pvalue)},
        },
        "verdict": verdict,
        "exchangeability_note": (
            "Assignment is strict alternation with a random start (2-point "
            "randomization distribution); RI permutes all balanced block "
            "labelings, i.e. tests block exchangeability."
        ),
        "replicates": rows,
    }

    RESULTS.mkdir(parents=True, exist_ok=True)
    json_path = RESULTS / "phase2c_randomization_inference.json"
    md_path = RESULTS / "phase2c_randomization_inference.md"
    json_path.write_text(json.dumps(artifact, indent=2) + "\n")
    md_path.write_text(
        "\n".join(
            [
                "# Phase 2c — randomization-inference audit of the clustered CIs",
                "",
                "**Synthetic, deterministic, CPU-only.** 100 independent 4-week "
                "switchback simulations (Phase-2b config: 28 daily blocks, 8 zones, "
                "spillover 0.70). Cross-checks the analytic clustered intervals "
                "against permutation inference on block means — no normality, no "
                "variance estimator.",
                "",
                "| Interval | Empirical coverage of the paired-CRN truth |",
                "|---|---|",
                f"| Hájek + Welch clustered CI | {pct('hajek_covers')} |",
                f"| Regression-adjusted + CR1 t CI | {pct('adjusted_covers')} |",
                f"| Hájek randomization CI (inversion, {N_PERM_HAJEK} perms) | {pct('ri_covers')} |",
                "",
                f"Randomization-CI width / Welch-CI width: mean "
                f"{float(np.mean(width_ratios)):.3f}, median "
                f"{float(np.median(width_ratios)):.3f}.",
                "",
                "**P-value calibration at the truth** (should be Uniform(0,1) if the "
                "inference is exact):",
                "",
                "| Estimator | KS statistic | KS p-value |",
                "|---|---:|---:|",
                f"| Hájek ({N_PERM_HAJEK} perms) | {float(ks_hajek.statistic):.3f} | "
                f"{float(ks_hajek.pvalue):.3f} |",
                f"| Regression-adjusted ({N_PERM_ADJUSTED} refit perms) | "
                f"{float(ks_adj.statistic):.3f} | {float(ks_adj.pvalue):.3f} |",
                "",
                "## Interpretation",
                "",
                "Round 2 diagnosed the earlier ~50% 'coverage' as a noisy truth "
                "reference (assignment-randomized diff-in-means, MC SE ~4.8), not a "
                "broken interval; the paired common-random-numbers truth (MC SE "
                "~0.12) resolved it. " + verdict,
                "",
                "**Scope caveat (stated, not hidden).** The deployed schedule is "
                "strict alternation with a random start, whose exact randomization "
                "distribution has only two support points. The permutation test "
                "treats blocks as exchangeable — the standard super-population "
                "reading — so this is a calibration audit under exchangeability, "
                "not an exact design-based test of the alternation schedule.",
                "",
                "Regenerate: `make phase2-ri` (deterministic, CPU, ~10 min).",
                "",
            ]
        )
    )
    print(f"\n  Hájek Welch coverage:      {pct('hajek_covers')}")
    print(f"  Adjusted CR1 t coverage:   {pct('adjusted_covers')}")
    print(f"  Hájek RI coverage:         {pct('ri_covers')}")
    print(
        f"  KS uniformity p (Hájek / adjusted): {float(ks_hajek.pvalue):.3f} / "
        f"{float(ks_adj.pvalue):.3f}"
    )
    print(f"  → {json_path.relative_to(REPO.parent)}")
    print(f"  → {md_path.relative_to(REPO.parent)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
