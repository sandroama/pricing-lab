"""Tests for switchback randomization modes + permutation inference (2c/3b)."""

from __future__ import annotations

import numpy as np
import pytest

from pricelab.estimators.ate import regression_adjusted_switchback_ate, switchback_ate
from pricelab.estimators.randomization import (
    block_permutation_ci,
    block_permutation_pvalue,
)
from pricelab.simulation.marketplace import MarketplaceConfig, MarketplaceSimulator


def _switchback_log(**overrides):
    cfg = MarketplaceConfig(
        n_zones=4,
        n_time_buckets=24 * 14,
        seed=7,
        **overrides,
    )
    return MarketplaceSimulator(cfg).simulate(design="switchback")


# ── randomization modes ─────────────────────────────────────────────────────


def test_stratified_daily_balances_treatment_within_every_day():
    log = _switchback_log(switchback_block_hours=4, switchback_randomization="stratified_daily")
    daily_share = log.df.groupby(log.df["timestamp"] // 24)["treatment"].mean()
    assert (daily_share == 0.5).all(), "3 of 6 four-hour blocks per day must be treated"


def test_iid_randomization_keeps_blocks_internally_uniform():
    log = _switchback_log(switchback_block_hours=4, switchback_randomization="iid")
    per_block = log.df.groupby(log.df["timestamp"] // 4)["treatment"].nunique()
    assert (per_block == 1).all()


def test_stratified_daily_rejects_block_not_dividing_24():
    with pytest.raises(ValueError, match="divide 24"):
        _switchback_log(switchback_block_hours=5, switchback_randomization="stratified_daily")


def test_unknown_randomization_mode_raises():
    with pytest.raises(ValueError, match="unknown switchback_randomization"):
        _switchback_log(switchback_randomization="bogus")


def test_alternating_4h_hour_adjustment_is_rank_deficient():
    """The Phase-3b structural result: strict alternation at 4h blocks makes
    treatment a deterministic function of hour-of-day, so hour fixed effects
    are collinear with treatment and adjustment must refuse to fit."""
    log = _switchback_log(switchback_block_hours=4)  # alternating default
    with pytest.raises(ValueError, match="rank deficient"):
        regression_adjusted_switchback_ate(log.df, block_hours=4)


def test_stratified_daily_4h_hour_adjustment_is_identified():
    log = _switchback_log(switchback_block_hours=4, switchback_randomization="stratified_daily")
    result = regression_adjusted_switchback_ate(log.df, block_hours=4)
    assert np.isfinite(result.point_estimate)
    assert result.standard_error > 0


# ── permutation inference ───────────────────────────────────────────────────


def _block_summaries(df, block_hours=24):
    grouped = df.groupby(df["timestamp"] // block_hours)
    return grouped["revenue"].mean().to_numpy(), grouped["treatment"].first().to_numpy()


def test_permutation_pvalue_is_large_at_point_estimate_and_small_far_away():
    log = _switchback_log(spillover_strength=0.5)
    means, treat = _block_summaries(log.df)
    point = float(means[treat == 1].mean() - means[treat == 0].mean())
    assert block_permutation_pvalue(means, treat, tau0=point, seed=1) > 0.9
    assert block_permutation_pvalue(means, treat, tau0=point + 100.0, seed=1) < 0.01


def test_permutation_ci_contains_point_and_is_deterministic():
    log = _switchback_log(spillover_strength=0.5)
    means, treat = _block_summaries(log.df)
    point = float(means[treat == 1].mean() - means[treat == 0].mean())
    lo1, hi1 = block_permutation_ci(means, treat, seed=3)
    lo2, hi2 = block_permutation_ci(means, treat, seed=3)
    assert (lo1, hi1) == (lo2, hi2)
    assert lo1 < point < hi1


def test_permutation_ci_agrees_with_welch_ci_within_a_third():
    """RI and analytic clustered intervals should be the same order of width —
    the Phase-2c calibration claim in miniature."""
    log = _switchback_log(spillover_strength=0.5)
    means, treat = _block_summaries(log.df)
    lo, hi = block_permutation_ci(means, treat, seed=3)
    welch = switchback_ate(log.df, block_hours=24)
    welch_width = welch.ci95[1] - welch.ci95[0]
    assert abs((hi - lo) - welch_width) / welch_width < 1 / 3


def test_permutation_requires_two_blocks_per_arm():
    with pytest.raises(ValueError, match="two treated and two control"):
        block_permutation_pvalue(np.array([1.0, 2.0, 3.0]), np.array([1, 0, 0]))
