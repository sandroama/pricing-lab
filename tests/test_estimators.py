"""Tests for the ATE estimators + the Phase-2 head-to-head harness."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pricelab.estimators.ate import (
    naive_ab_ate,
    regression_adjusted_switchback_ate,
    switchback_ate,
)
from pricelab.evaluation.compare import (
    run_phase1_naive_ab,
    run_phase2_switchback_vs_naive,
)
from pricelab.simulation.marketplace import MarketplaceConfig


# ── unit tests on synthetic toy data ────────────────────────────────────────


def test_naive_ab_recovers_ate_when_no_spillover_and_no_noise():
    """Sanity check: difference-in-means is unbiased on i.i.d. data."""
    rng = np.random.default_rng(0)
    n = 1000
    df = pd.DataFrame(
        {
            "treatment": rng.integers(0, 2, size=n),
            "revenue": np.zeros(n),
        }
    )
    # Make treatment effect = +5 deterministically
    df.loc[df["treatment"] == 1, "revenue"] = 105.0
    df.loc[df["treatment"] == 0, "revenue"] = 100.0
    res = naive_ab_ate(df)
    assert abs(res.point_estimate - 5.0) < 1e-9
    assert res.standard_error == 0.0  # zero variance


def test_naive_ab_rejects_bad_treatment_values():
    df = pd.DataFrame({"treatment": [0, 1, 2], "revenue": [1.0, 2.0, 3.0]})
    with pytest.raises(ValueError):
        naive_ab_ate(df)


def test_naive_ab_rejects_missing_columns():
    df = pd.DataFrame({"foo": [1, 2, 3]})
    with pytest.raises(ValueError):
        naive_ab_ate(df)


def test_switchback_recovers_ate_when_blocks_are_clean():
    """Two blocks: block 0 control, block 1 treatment, with constant outcomes."""
    df = pd.DataFrame(
        {
            "timestamp": [0, 0, 1, 1, 2, 2, 3, 3],  # blocks of size 1
            "treatment": [0, 0, 1, 1, 0, 0, 1, 1],
            "revenue": [10.0, 12.0, 14.0, 16.0, 9.0, 11.0, 15.0, 17.0],
        }
    )
    res = switchback_ate(df, block_hours=1)
    # Block means: t=0 -> 11, t=2 -> 10 (control); t=1 -> 15, t=3 -> 16 (treatment)
    # ATE = mean(15, 16) - mean(11, 10) = 15.5 - 10.5 = 5.0
    assert abs(res.point_estimate - 5.0) < 1e-9


def test_switchback_rejects_mixed_within_block_treatment():
    df = pd.DataFrame(
        {
            "timestamp": [0, 0, 0, 0],
            "treatment": [0, 1, 0, 1],  # mixed within block 0
            "revenue": [10.0, 12.0, 14.0, 16.0],
        }
    )
    with pytest.raises(ValueError):
        switchback_ate(df, block_hours=1)


def test_switchback_rejects_ab_random_log_at_block_hours_24():
    """An A/B-random log has per-cell coin-flip treatment, so a 24h block
    contains both T and C cells. The Hájek estimator must refuse it rather
    than silently returning a meaningless number — this is the guardrail
    that forces callers to use the switchback design."""
    from pricelab.simulation.marketplace import MarketplaceSimulator

    cfg = MarketplaceConfig(n_zones=4, n_time_buckets=48, seed=3)
    log = MarketplaceSimulator(cfg).simulate(design="ab_random")
    with pytest.raises(ValueError):
        switchback_ate(log.df, block_hours=24)


def test_regression_adjusted_switchback_removes_predictable_block_noise():
    """A pre-treatment block covariate can improve switchback precision."""
    rng = np.random.default_rng(7)
    n_blocks, cells_per_block = 20, 12
    block = np.repeat(np.arange(n_blocks), cells_per_block)
    treatment_by_block = np.arange(n_blocks) % 2
    treatment = np.repeat(treatment_by_block, cells_per_block)
    baseline_by_block = rng.normal(size=n_blocks) + 0.35 * treatment_by_block
    baseline = np.repeat(baseline_by_block, cells_per_block)
    outcome = 3.0 * treatment + 12.0 * baseline + rng.normal(0.0, 0.25, len(block))
    df = pd.DataFrame(
        {
            "switchback_block": block,
            "treatment": treatment,
            "pre_metric": baseline,
            "revenue": outcome,
        }
    )

    unadjusted = switchback_ate(df)
    adjusted = regression_adjusted_switchback_ate(
        df,
        covariates=("pre_metric",),
        categorical_covariates=(),
    )

    assert adjusted.point_estimate == pytest.approx(3.0, abs=0.15)
    assert adjusted.standard_error < unadjusted.standard_error * 0.2
    assert adjusted.degrees_of_freedom == n_blocks - 2
    assert adjusted.critical_value > 1.96
    assert "block-clustered" in (adjusted.uncertainty_method or "")


def test_regression_adjusted_switchback_runs_on_marketplace_defaults():
    from pricelab.simulation.marketplace import MarketplaceSimulator

    cfg = MarketplaceConfig(n_zones=4, n_time_buckets=24 * 8, seed=9)
    log = MarketplaceSimulator(cfg).simulate(design="switchback")
    result = regression_adjusted_switchback_ate(log.df, block_hours=24)

    assert np.isfinite(result.point_estimate)
    assert np.isfinite(result.standard_error)
    assert result.n_treatment == result.n_control == 4
    assert result.as_dict()["degrees_of_freedom"] == 6


def test_regression_adjusted_switchback_rejects_too_few_clusters():
    df = pd.DataFrame(
        {
            "switchback_block": np.repeat(np.arange(3), 2),
            "treatment": np.repeat([0, 1, 0], 2),
            "pre_metric": np.arange(6),
            "revenue": np.arange(6, dtype=float),
        }
    )
    with pytest.raises(ValueError, match="two treated and two control"):
        regression_adjusted_switchback_ate(
            df,
            covariates=("pre_metric",),
            categorical_covariates=(),
        )


def test_ate_result_ci95_brackets_point_estimate_at_1p96_se():
    """The 95% normal-approximation CI must be exactly point ± 1.96·SE and
    must straddle the point estimate symmetrically."""
    from pricelab.estimators.ate import AteResult

    res = AteResult(
        estimator="toy",
        point_estimate=70.0,
        standard_error=3.0,
        n_treatment=20,
        n_control=20,
    )
    lo, hi = res.ci95
    assert lo < res.point_estimate < hi
    assert abs(lo - (70.0 - 1.96 * 3.0)) < 1e-12
    assert abs(hi - (70.0 + 1.96 * 3.0)) < 1e-12
    # symmetric about the point estimate
    assert abs((hi - res.point_estimate) - (res.point_estimate - lo)) < 1e-12


# ── integration: the headline finding ──────────────────────────────────────


def test_phase1_naive_ab_runs_and_returns_finite_estimate():
    cmp_ = run_phase1_naive_ab(MarketplaceConfig(n_zones=4, n_time_buckets=48, seed=0))
    assert len(cmp_.results) == 1
    assert np.isfinite(cmp_.results[0].point_estimate)
    # Seed 0 draws elasticities [-1.97, -1.93, -1.57, -0.98] (mean -1.61): three
    # of the four zones sit below -1, the revenue-decreasing region, so the
    # 10 -> 12 price rise must LOWER expected revenue in aggregate. The paired
    # common-random-numbers truth is ~-19.8; the earlier `> 0` assertion passed
    # only because the old assignment-randomized truth was dominated by Monte
    # Carlo noise (MC SE ~15 at this 192-cell config).
    assert cmp_.true_ate < 0


def test_phase2_switchback_beats_naive_under_strong_spillover():
    """The headline claim: under STRONG spillover, switchback recovers true
    ATE more accurately than naive A/B. We use a long horizon (4 weeks)
    so switchback has enough blocks for statistical power to dominate
    finite-sample variance."""
    cfg = MarketplaceConfig(
        n_zones=8,
        n_time_buckets=24 * 28,  # 4 weeks → 28 switchback blocks
        spillover_strength=0.80,  # strong spillover so the bias gap is visible
        seed=42,
    )
    cmp_ = run_phase2_switchback_vs_naive(cfg)
    naive = next(r for r in cmp_.results if "naive" in r.estimator)
    sb = next(r for r in cmp_.results if "switchback" in r.estimator)

    bias_naive = abs(naive.bias_vs(cmp_.true_ate))
    bias_sb = abs(sb.bias_vs(cmp_.true_ate))

    assert bias_sb < bias_naive, (
        f"expected switchback bias < naive bias; got naive={bias_naive:.2f}, sb={bias_sb:.2f}, "
        f"true_ate={cmp_.true_ate:.2f}"
    )


def test_phase2_switchback_bias_within_25pct_of_true_ate_under_spillover():
    """At a 4-week horizon and moderate spillover, switchback should keep
    its bias under ~25% of true ATE. Loose threshold reflects the finite-block
    variance of the Hájek estimator on weekly data."""
    cmp_ = run_phase2_switchback_vs_naive(
        MarketplaceConfig(
            n_zones=8,
            n_time_buckets=24 * 28,
            spillover_strength=0.50,
            seed=42,
        )
    )
    sb = next(r for r in cmp_.results if "switchback" in r.estimator)
    assert sb.bias_pct(cmp_.true_ate) < 0.25, (
        f"switchback bias was {sb.bias_pct(cmp_.true_ate) * 100:.1f}% of true ATE "
        f"({sb.point_estimate:.2f} vs {cmp_.true_ate:.2f})"
    )
