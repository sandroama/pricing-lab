"""Drift guards for the Phase 4/5/6 runners — small n, fixed seed, seconds."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pricelab.realdata import estimate_fold, prepare_trips, walk_forward_folds
from pricelab.simulation.marketplace import MarketplaceConfig, simulate_continuous_price

econml_missing = importlib.util.find_spec("econml") is None
SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _small_cfg(seed: int = 42) -> MarketplaceConfig:
    return MarketplaceConfig(n_zones=4, n_time_buckets=24 * 7, seed=seed)


# ── Phase 4: continuous-price DGP + OLS-vs-DML contrast ────────────────────


def test_continuous_dgp_shape_and_determinism():
    df1, truth1 = simulate_continuous_price(_small_cfg())
    df2, truth2 = simulate_continuous_price(_small_cfg())
    assert len(df1) == 4 * 24 * 7
    assert truth1["mean_elasticity"] == truth2["mean_elasticity"]
    pd.testing.assert_frame_equal(df1, df2)
    # elasticities negative, confounded price varies
    assert all(e < 0 for e in truth1["elasticities"])
    assert df1["log_price"].std() > 0


@pytest.mark.requires_econml
@pytest.mark.skipif(econml_missing, reason="needs pip install -e '.[causal]'")
def test_phase4_dml_beats_naive_ols():
    from pricelab.estimators.dml import dml_elasticity, ols_elasticity

    df, truth = simulate_continuous_price(_small_cfg())
    e_true = truth["mean_elasticity"]
    ols_bias = abs(ols_elasticity(df).point_estimate - e_true)
    dml_bias = abs(dml_elasticity(df, seed=42).point_estimate - e_true)
    assert ols_bias > 1.0  # confounding makes naive OLS badly wrong
    assert dml_bias < 0.15  # DML recovers the elasticity
    assert dml_bias < ols_bias


def test_phase4_metadata_matches_linear_nuisance_implementation():
    """Guard against relabeling the linear-nuisance artifact as RF DML."""
    artifact = json.loads((Path(__file__).parents[1] / "docs/results/phase4_dml.json").read_text())
    assert artifact["dml_estimator_id"] == "linear_dml"
    assert artifact["dml_nuisance_models"] == "sklearn.linear_model.LinearRegression"
    assert {row["dml"]["estimator"] for row in artifact["replicates"]} == {"linear_dml"}


# ── Phase 5: segment estimates + revenue optimizer ──────────────────────────


@pytest.mark.requires_econml
@pytest.mark.skipif(econml_missing, reason="needs pip install -e '.[causal]'")
def test_phase5_segment_pricing_beats_uniform_on_truth():
    sys.path.insert(0, str(SCRIPTS))
    try:
        p5 = importlib.import_module("run_phase5_hetero")
    finally:
        sys.path.pop(0)

    _, truth = simulate_continuous_price(_small_cfg())
    scales = np.asarray(truth["zone_scale"])
    elast = np.asarray(truth["elasticities"])
    seg_prices, uni_price = p5.optimize_prices(scales, elast, truth["price_ref"])
    rev_seg = p5.true_total_revenue(seg_prices, truth)
    rev_uni = p5.true_total_revenue(np.full(len(scales), uni_price), truth)
    # per-zone optimum dominates any single price by construction
    assert rev_seg >= rev_uni
    assert all(p5.PRICE_BAND[0] - 1e-6 <= p <= p5.PRICE_BAND[1] + 1e-6 for p in seg_prices)


# ── Phase 6: real-data plumbing on a tiny synthetic frame (no download) ─────


def _fake_trips(n: int = 2000, seed: int = 0) -> pd.DataFrame:
    """Citi-Bike-shaped frame with a planted -2 min e-bike effect, no confounding."""
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2024-09-01") + pd.to_timedelta(
        rng.integers(0, 28 * 24 * 60, size=n), unit="m"
    )
    ebike = rng.integers(0, 2, size=n)
    duration = 10.0 - 2.0 * ebike + rng.normal(0, 1.0, size=n)
    return pd.DataFrame(
        {
            "started_at": start.astype(str),
            "ended_at": (start + pd.to_timedelta(duration, unit="m")).astype(str),
            "rideable_type": np.where(ebike == 1, "electric_bike", "classic_bike"),
            "member_casual": np.where(rng.integers(0, 2, size=n) == 1, "member", "casual"),
        }
    )


def test_phase6_walkforward_recovers_planted_effect():
    df, accounting = prepare_trips(_fake_trips())
    assert accounting["n_kept"] + accounting["n_dropped_duration"] == accounting["n_raw"]

    folds = walk_forward_folds(df)
    assert len(folds) >= 2
    # train indices strictly precede the test week
    for week, train, test in folds:
        assert (df.loc[train, "week"] < week).all()
        assert (df.loc[test, "week"] == week).all()

    est = estimate_fold(df, *folds[-1][1:])
    assert abs(est.naive_point - (-2.0)) < 0.3
    assert abs(est.adjusted_point - (-2.0)) < 0.3


def test_walkforward_temporal_firewall_survives_year_boundary():
    """Dec 30 2024 is ISO week 1 of 2025. With bare ISO week numbers the fold
    ordering sorts it BEFORE week 52, so 'train on earlier weeks' silently
    trains on future trips. The year-qualified week key must keep every
    training trip strictly before every test trip in wall-clock time."""
    rng = np.random.default_rng(1)
    n = 1200
    # 2024-12-16 .. 2025-01-12: spans ISO weeks 2024-51..52 and 2025-01..02.
    start = pd.Timestamp("2024-12-16") + pd.to_timedelta(
        rng.integers(0, 28 * 24 * 60, size=n), unit="m"
    )
    ebike = rng.integers(0, 2, size=n)
    duration = 10.0 - 2.0 * ebike + rng.normal(0, 1.0, size=n)
    raw = pd.DataFrame(
        {
            "started_at": start.astype(str),
            "ended_at": (start + pd.to_timedelta(duration, unit="m")).astype(str),
            "rideable_type": np.where(ebike == 1, "electric_bike", "classic_bike"),
            "member_casual": np.where(rng.integers(0, 2, size=n) == 1, "member", "casual"),
        }
    )
    df, _ = prepare_trips(raw)
    started = pd.to_datetime(df["started_at"])
    folds = walk_forward_folds(df)
    assert len(folds) >= 3
    for _, train, test in folds:
        assert started.loc[train].max() < started.loc[test].min(), (
            "training fold contains trips later than the test fold"
        )


def test_naive_effect_rejects_single_type_fold():
    from pricelab.realdata import naive_effect

    df, _ = prepare_trips(_fake_trips(n=200))
    with pytest.raises(ValueError, match="naive_effect"):
        naive_effect(df.loc[df["ebike"] == 1])


def test_continuous_dgp_rejects_nonpositive_diurnal():
    """diurnal_amplitude large enough to push the pattern <= 0 must raise
    instead of silently writing NaN into log-quantity."""
    with pytest.raises(ValueError, match="diurnal"):
        simulate_continuous_price(MarketplaceConfig(diurnal_amplitude=3.0, seed=0))
