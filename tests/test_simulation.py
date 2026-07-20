"""Tests for the marketplace simulator."""

from __future__ import annotations

import numpy as np
import pandas as pd

from pricelab.simulation.marketplace import (
    MarketplaceConfig,
    MarketplaceSimulator,
    spillover_aware_demand,
)


def test_spillover_aware_demand_monotone_in_price():
    """For elastic goods (negative elasticity), demand falls as price rises."""
    base = 100.0
    high = spillover_aware_demand(
        base, price=10, price_ref=10, elasticity=-1.5, diurnal=1.0, spillover_in=0.0, noise=0.0
    )
    low = spillover_aware_demand(
        base, price=15, price_ref=10, elasticity=-1.5, diurnal=1.0, spillover_in=0.0, noise=0.0
    )
    assert low < high, "raising price should reduce demand for elastic goods"


def test_spillover_in_adds_demand():
    base = 100.0
    no_spill = spillover_aware_demand(base, 10, 10, -1.5, 1.0, 0.0, 0.0)
    with_spill = spillover_aware_demand(base, 10, 10, -1.5, 1.0, 20.0, 0.0)
    assert with_spill > no_spill


def test_simulate_ab_random_shapes():
    cfg = MarketplaceConfig(n_zones=4, n_time_buckets=24, seed=0)
    sim = MarketplaceSimulator(cfg)
    log = sim.simulate(design="ab_random")
    assert isinstance(log.df, pd.DataFrame)
    assert len(log.df) == 4 * 24
    expected_cols = {
        "timestamp",
        "zone",
        "treatment",
        "price",
        "true_demand",
        "observed_quantity",
        "revenue",
        "diurnal",
        "elasticity_true",
    }
    assert expected_cols.issubset(set(log.df.columns))
    # treatment values are 0/1
    assert set(log.df["treatment"].unique()).issubset({0, 1})


def test_simulate_switchback_block_treatment_uniform():
    """Within a switchback block, every (time, zone) cell shares the same treatment."""
    cfg = MarketplaceConfig(n_zones=4, n_time_buckets=48, switchback_block_hours=4, seed=1)
    sim = MarketplaceSimulator(cfg)
    log = sim.simulate(design="switchback")
    df = log.df.copy()
    df["block"] = df["timestamp"] // cfg.switchback_block_hours
    per_block = df.groupby("block")["treatment"].nunique()
    # Each block should have exactly 1 unique treatment value
    assert (per_block == 1).all(), f"some blocks had mixed treatment: {per_block.value_counts()}"


def test_true_ate_revenue_is_positive_for_treatment_above_control_with_inelastic():
    """If raising price doesn't crush demand much, revenue ATE should be positive
    (price effect dominates)."""
    cfg = MarketplaceConfig(
        n_zones=4,
        n_time_buckets=24,
        # all-inelastic so the (price/ref)^elasticity term stays close to 1
        elasticities=(-0.4, -0.4, -0.4, -0.4),
        price_control=10.0,
        price_treatment=12.0,
        seed=0,
    )
    sim = MarketplaceSimulator(cfg)
    log = sim.simulate(design="ab_random")
    assert log.true_ate_revenue > 0


def test_seed_reproducibility():
    cfg = MarketplaceConfig(n_zones=4, n_time_buckets=24, seed=7)
    a = MarketplaceSimulator(cfg).simulate(design="ab_random").df
    b = MarketplaceSimulator(cfg).simulate(design="ab_random").df
    pd.testing.assert_frame_equal(a, b)


def test_capacity_caps_observed_quantity():
    cfg = MarketplaceConfig(
        n_zones=4,
        n_time_buckets=24,
        base_demand=100.0,
        capacity_multiplier=1.0,  # strict cap
        elasticities=(-0.1, -0.1, -0.1, -0.1),  # near-rigid demand
        diurnal_amplitude=2.0,  # wild swings to push past cap
        seed=0,
    )
    sim = MarketplaceSimulator(cfg)
    log = sim.simulate(design="ab_random")
    cap = cfg.base_demand * cfg.capacity_multiplier
    assert log.df["observed_quantity"].max() <= cap + 1e-6


def test_true_ate_is_invariant_to_spillover_strength():
    """The ground-truth ATE is computed at ``spillover_strength=0`` (SUTVA
    holds), so changing the spillover knob must NOT move the truth — only the
    *naive estimate* should respond to spillover. This is the invariant that
    makes the bias-vs-spillover sweep a fair comparison: every row is measured
    against the same target. Elasticities + seed are pinned so the only
    difference between the two configs is the spillover knob."""
    elasticities = (-1.5, -1.0, -0.6, -0.4)
    truth_no_spill = MarketplaceSimulator(
        MarketplaceConfig(
            n_zones=4,
            n_time_buckets=48,
            elasticities=elasticities,
            spillover_strength=0.0,
            seed=11,
        )
    )._compute_true_ate()
    truth_heavy_spill = MarketplaceSimulator(
        MarketplaceConfig(
            n_zones=4,
            n_time_buckets=48,
            elasticities=elasticities,
            spillover_strength=0.70,
            seed=11,
        )
    )._compute_true_ate()
    assert abs(truth_no_spill - truth_heavy_spill) < 1e-9, (
        f"truth moved with spillover: {truth_no_spill} vs {truth_heavy_spill}"
    )


def test_true_ate_is_stable_across_resample_counts():
    """The truth is the paired mean of Y(1)-Y(0) under common random numbers,
    so its Monte Carlo error must be small relative to the estimators' SE
    (~2.0 at this config). The pre-fix assignment-randomized truth had an MC
    SE of ~4.8 and moved by several units between resample counts — that is
    what depressed Phase-2b's measured CI coverage to ~50%. This test fails
    under that implementation and passes under the paired one."""
    cfg = MarketplaceConfig(
        n_zones=8, n_time_buckets=24 * 28, spillover_strength=0.70, seed=200
    )
    sim = MarketplaceSimulator(cfg)
    truth_lo = sim._compute_true_ate(n_noise_resamples=8)
    truth_hi = sim._compute_true_ate(n_noise_resamples=64)
    assert abs(truth_lo - truth_hi) < 0.5, (
        f"truth unstable across resample counts: {truth_lo:.3f} vs {truth_hi:.3f}"
    )


def test_switchback_assignment_strictly_alternates_per_block():
    """`_assign_switchback` must produce strict T/C/T/C alternation across
    blocks (no two consecutive blocks share a treatment) and an
    ``(n_time, n_zones)`` array with uniform treatment within each row-block.
    Strict alternation is what guarantees balanced exposure across the diurnal
    cycle at ``block_hours=24`` — a plain per-block coin flip would not."""
    block = 4
    cfg = MarketplaceConfig(n_zones=4, n_time_buckets=48, switchback_block_hours=block, seed=5)
    T = MarketplaceSimulator(cfg)._assign_switchback()
    assert T.shape == (48, 4)
    # all zones share the assignment within a time bucket
    assert (T == T[:, [0]]).all()
    per_block = T[::block, 0]
    assert np.all(np.abs(np.diff(per_block)) == 1), (
        f"blocks not strictly alternating: {per_block.tolist()}"
    )
    # block_hours=1 → every time bucket is its own block, still alternating
    cfg1 = MarketplaceConfig(n_zones=3, n_time_buckets=10, switchback_block_hours=1, seed=5)
    T1 = MarketplaceSimulator(cfg1)._assign_switchback()
    per_block1 = T1[:, 0]
    assert per_block1.size == 10
    assert np.all(np.abs(np.diff(per_block1)) == 1)


def test_naive_ab_bias_is_nondecreasing_in_spillover():
    """RQ-P1 at unit scale: holding seed/config fixed, the absolute bias of
    naive A/B must be non-decreasing as ``spillover_strength`` rises. Asserts
    the *ordering* (a structural property of the DGP) rather than any specific
    published bias percentage."""
    from pricelab.evaluation.compare import run_phase1_naive_ab

    biases = []
    for s in (0.0, 0.35, 0.70):
        cmp_ = run_phase1_naive_ab(
            MarketplaceConfig(n_zones=4, n_time_buckets=24 * 7, spillover_strength=s, seed=42)
        )
        biases.append(cmp_.results[0].bias_pct(cmp_.true_ate))
    assert biases[0] <= biases[1] <= biases[2], (
        f"naive bias not non-decreasing in spillover: {biases}"
    )
