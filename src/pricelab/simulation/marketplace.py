"""Synthetic two-sided marketplace data-generating process (DGP).

Designed to *break* naive A/B pricing experiments in a way that's auditable:

  - **Heterogeneous true elasticity by zone.** Some zones are price-sensitive
    (commuters, easy substitutes), others are inelastic (premium / late-night).
  - **Spillover (network effects).** Raising price in zone A shifts demand to
    nearby zone B. SUTVA — the assumption underlying naive A/B — is violated
    by construction. The strength of spillover is a knob.
  - **Time-of-day demand pattern.** Rush-hour multipliers create heteroscedastic
    confounding when an experiment is unbalanced across time.
  - **Capacity caps.** Demand can exceed supply at peak; observed quantity =
    min(demand, capacity).

This module produces a long-format `SimulationLog` with per-(time, zone) rows:
  ``timestamp, zone, price, true_demand, observed_quantity, revenue, treatment``

Two assignment strategies are supported:

  1. **A/B random**: each (time, zone) cell is independently assigned T or C.
     Spillover means treated demand leaks into control cells in the *same time
     bucket*, biasing the naive ATE estimator.
  2. **Switchback**: time is partitioned into blocks; the *whole platform*
     gets one treatment for the duration of a block. SUTVA holds across
     time blocks, eliminating cross-zone spillover bias.

The default config produces ~10K rows and runs in <1s on a Mac.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

DesignKind = Literal["ab_random", "switchback"]


@dataclass
class MarketplaceConfig:
    """All knobs of the synthetic marketplace DGP."""

    n_zones: int = 8
    n_time_buckets: int = 168          # one week of hourly buckets
    base_demand: float = 100.0
    # Per-zone elasticity. -2.0 = elastic, -0.4 = inelastic.
    # The DGP regenerates `n_zones` values from this seed band if not provided.
    elasticities: tuple[float, ...] | None = None
    elasticity_seed_band: tuple[float, float] = (-2.0, -0.4)
    # Diurnal demand multiplier sampled from a bimodal pattern (rush hours).
    diurnal_amplitude: float = 0.6
    # Spillover strength: when zone A is treated (high price), this fraction
    # of A's lost demand transfers to its nearest neighbor in the same hour.
    spillover_strength: float = 0.35
    # Capacity cap = base_demand × this multiplier.
    capacity_multiplier: float = 1.5
    # Multiplicative log-normal demand noise.
    noise_sigma: float = 0.10
    # Switchback block size in time-buckets. Default = one full day so that
    # each block spans an integer number of diurnal cycles. Sub-day blocks
    # (e.g. 4h) introduce aliasing with the diurnal pattern unless the
    # estimator stratifies on hour-of-day — which Phase 3 will explore.
    switchback_block_hours: int = 24
    # How switchback blocks are assigned to T/C:
    #   "alternating"      — strict T/C/T/C with a random start (industry default;
    #                        aliases with the diurnal cycle at some sub-day sizes,
    #                        measured in Phase 3).
    #   "iid"              — independent fair coin per block.
    #   "stratified_daily" — within each 24h day, a random balanced permutation of
    #                        T/C over that day's blocks (hour-of-day stratified
    #                        randomization; requires block_hours to divide 24).
    switchback_randomization: Literal["alternating", "iid", "stratified_daily"] = "alternating"
    # Two test prices.
    price_control: float = 10.0
    price_treatment: float = 12.0
    # Reproducibility.
    seed: int = 42


@dataclass
class SimulationLog:
    """Long-format event log + the true ground-truth ATE for evaluation."""

    df: pd.DataFrame
    true_ate_revenue: float          # ground-truth ATE on revenue per cell
    config: MarketplaceConfig

    def head(self, n: int = 5) -> pd.DataFrame:
        return self.df.head(n)


# --------------------------------------------------------------------------- #
# Demand model
# --------------------------------------------------------------------------- #


def spillover_aware_demand(
    base: float,
    price: float,
    price_ref: float,
    elasticity: float,
    diurnal: float,
    spillover_in: float,
    noise: float,
) -> float:
    """Constant-elasticity demand with diurnal multiplier + spillover-in.

    ``demand = base * diurnal * (price / price_ref) ** elasticity + spillover_in``
    multiplied by a log-normal noise term ``exp(noise)``.
    """
    # constant-elasticity in log-price
    base_d = base * diurnal * (price / max(price_ref, 1e-9)) ** elasticity
    return float(max(0.0, (base_d + spillover_in) * np.exp(noise)))


# --------------------------------------------------------------------------- #
# Simulator
# --------------------------------------------------------------------------- #


class MarketplaceSimulator:
    """Roll out the marketplace DGP under a chosen treatment assignment."""

    def __init__(self, config: MarketplaceConfig | None = None):
        self.cfg = config or MarketplaceConfig()
        self._rng = np.random.default_rng(self.cfg.seed)
        self._elasticities = self._build_elasticities()
        self._diurnal = self._build_diurnal()

    # ── construction helpers ────────────────────────────────────────────────

    def _build_elasticities(self) -> np.ndarray:
        if self.cfg.elasticities is not None:
            arr = np.asarray(self.cfg.elasticities, dtype=np.float64)
            if arr.shape[0] != self.cfg.n_zones:
                raise ValueError(
                    f"elasticities has {arr.shape[0]} entries; expected n_zones={self.cfg.n_zones}"
                )
            return arr
        lo, hi = self.cfg.elasticity_seed_band
        # Sorted so zone 0 is most elastic, zone n-1 is most inelastic — useful
        # for interpretation, doesn't affect any estimator.
        return np.sort(self._rng.uniform(lo, hi, size=self.cfg.n_zones))

    def _build_diurnal(self) -> np.ndarray:
        # Bimodal: morning + evening rush. Period = 24 hours.
        t = np.arange(self.cfg.n_time_buckets) % 24
        morning = np.exp(-((t - 8) ** 2) / (2 * 2.0**2))
        evening = np.exp(-((t - 18) ** 2) / (2 * 2.0**2))
        peak = morning + evening
        # Normalize to mean 1, scale by amplitude knob
        peak = (peak - peak.mean()) / max(peak.std(), 1e-9)
        return np.asarray(1.0 + self.cfg.diurnal_amplitude * peak)

    # ── treatment assignment ────────────────────────────────────────────────

    def _assign_ab_random(self) -> np.ndarray:
        """Per-cell independent T/C. Returns (n_time, n_zones) of {0, 1}."""
        return self._rng.integers(0, 2, size=(self.cfg.n_time_buckets, self.cfg.n_zones))

    def _assign_switchback(self) -> np.ndarray:
        """Block-level switchback: every `switchback_block_hours` hours, the
        whole platform flips treatment together. The T/C schedule over blocks
        follows ``cfg.switchback_randomization``:

        - ``"alternating"`` — strict T/C/T/C from a random start. Industry
          practice (Doordash, Uber, Lyft) for full-cycle blocks; balances
          exposure across diurnal cycles when the block spans a full cycle,
          but *aliases* with the diurnal pattern at some sub-day block sizes
          (Phase 3's `block_hours=4` spike).
        - ``"iid"`` — independent fair coin per block. No aliasing, but no
          balance guarantee either.
        - ``"stratified_daily"`` — random balanced T/C permutation within each
          24-hour day (hour-of-day stratified randomization, the Phase-3b fix).
        """
        block = self.cfg.switchback_block_hours
        n_blocks = (self.cfg.n_time_buckets + block - 1) // block
        mode = self.cfg.switchback_randomization
        if mode == "alternating":
            # Random starting offset (T or C) but strict alternation thereafter.
            start = int(self._rng.integers(0, 2))
            per_block = (np.arange(n_blocks) + start) % 2
        elif mode == "iid":
            per_block = self._rng.integers(0, 2, size=n_blocks)
        elif mode == "stratified_daily":
            per_day, rem = divmod(24, block)
            if rem != 0 or per_day < 2:
                raise ValueError(
                    "stratified_daily randomization needs switchback_block_hours to "
                    f"divide 24 with >=2 blocks/day; got block_hours={block}"
                )
            half = per_day // 2
            # Balanced within each day (odd per_day → off by one, randomized side).
            n_days = (n_blocks + per_day - 1) // per_day
            days = [
                self._rng.permutation(np.array([1] * half + [0] * (per_day - half)))
                for _ in range(n_days)
            ]
            per_block = np.concatenate(days)[:n_blocks]
        else:
            raise ValueError(f"unknown switchback_randomization: {mode!r}")
        per_time = np.repeat(per_block, block)[: self.cfg.n_time_buckets]
        return np.broadcast_to(per_time[:, None], (self.cfg.n_time_buckets, self.cfg.n_zones)).copy()

    # ── main rollout ────────────────────────────────────────────────────────

    def simulate(self, design: DesignKind = "ab_random") -> SimulationLog:
        """Roll out the marketplace; return per-(time, zone) rows + ground-truth ATE."""
        if design == "ab_random":
            T = self._assign_ab_random()
        elif design == "switchback":
            T = self._assign_switchback()
        else:
            raise ValueError(f"unknown design: {design}")

        prices = np.where(T == 1, self.cfg.price_treatment, self.cfg.price_control).astype(float)
        # Build per-(time, zone) demand with spillover-in computed per-time bucket.
        rows: list[dict[str, float | int]] = []
        capacity = self.cfg.base_demand * self.cfg.capacity_multiplier
        n_z = self.cfg.n_zones

        for t in range(self.cfg.n_time_buckets):
            # Compute baseline (no-spillover) demand for this hour
            base_demand_t = np.empty(n_z)
            for z in range(n_z):
                noise = self._rng.normal(0.0, self.cfg.noise_sigma)
                base_demand_t[z] = spillover_aware_demand(
                    base=self.cfg.base_demand,
                    price=prices[t, z],
                    price_ref=self.cfg.price_control,
                    elasticity=self._elasticities[z],
                    diurnal=self._diurnal[t],
                    spillover_in=0.0,
                    noise=noise,
                )

            # Spillover flows only when there's a *price differential* between
            # neighboring zones — customers substitute from the higher-priced
            # zone to the lower-priced one. Under switchback (uniform prices
            # within a block), prices match across all neighbors, so spillover
            # is zero by construction. Under A/B random, ~50% of neighbor
            # pairs have a differential, causing the naive estimator to
            # overcount control revenue.
            spill = np.zeros(n_z)
            for z in range(n_z):
                nbr = (z + 1) % n_z
                if prices[t, z] > prices[t, nbr]:
                    high, low = z, nbr
                elif prices[t, nbr] > prices[t, z]:
                    high, low = nbr, z
                else:
                    continue  # uniform prices — no substitution
                cf_high_demand = (
                    self.cfg.base_demand * self._diurnal[t]
                )  # demand at the reference (control) price
                lost = max(0.0, cf_high_demand - base_demand_t[high])
                spill[low] += self.cfg.spillover_strength * lost

            # Final demand = base + spillover-in, capped at capacity
            for z in range(n_z):
                final_demand = base_demand_t[z] + spill[z]
                observed = min(final_demand, capacity)
                rows.append(
                    {
                        "timestamp": t,
                        "zone": z,
                        "treatment": int(T[t, z]),
                        "price": float(prices[t, z]),
                        "true_demand": float(final_demand),
                        "observed_quantity": float(observed),
                        "revenue": float(observed * prices[t, z]),
                        "diurnal": float(self._diurnal[t]),
                        "elasticity_true": float(self._elasticities[z]),
                    }
                )

        df = pd.DataFrame(rows)
        true_ate = self._compute_true_ate()
        return SimulationLog(df=df, true_ate_revenue=true_ate, config=self.cfg)

    # ── ground truth ────────────────────────────────────────────────────────

    def _compute_true_ate(self, n_noise_resamples: int = 32) -> float:
        """Empirical "true" ATE: mean per-cell revenue difference between the
        two potential outcomes under ``spillover_strength=0`` (SUTVA holds),
        holding elasticities and the diurnal pattern fixed.

        Both prices are evaluated on the *same* noise draw per cell (common
        random numbers), so this is the paired mean of ``Y(1) - Y(0)`` — no
        treatment-assignment randomness enters. The earlier implementation
        randomized assignment and took a diff-in-means, whose Monte Carlo SE
        (~4.8 at the Phase-2b config) exceeded the estimators' own SE (~2.0)
        and mechanically depressed measured CI coverage to ~50%. The paired
        version's MC SE is ~0.12 at 32 resamples (vectorized, ~3 ms).
        Includes capacity binding + log-normal noise (Jensen) effects.
        """
        cfg = self.cfg
        capacity = cfg.base_demand * cfg.capacity_multiplier
        # (n_t, n_z) baseline demand at each price, no spillover.
        base = cfg.base_demand * self._diurnal[:, None]  # (n_t, 1)
        ratio_t = (cfg.price_treatment / max(cfg.price_control, 1e-9)) ** self._elasticities
        shape = (cfg.n_time_buckets, cfg.n_zones)

        diffs: list[float] = []
        for s in range(n_noise_resamples):
            rng = np.random.default_rng(cfg.seed + 1000 + s)
            noise = np.exp(rng.normal(0.0, cfg.noise_sigma, size=shape))
            demand_c = np.maximum(0.0, base * noise)                    # control price
            demand_t = np.maximum(0.0, base * ratio_t[None, :] * noise)  # treatment price
            rev_c = np.minimum(demand_c, capacity) * cfg.price_control
            rev_t = np.minimum(demand_t, capacity) * cfg.price_treatment
            diffs.append(float((rev_t - rev_c).mean()))
        return float(np.mean(diffs)) if diffs else 0.0


# --------------------------------------------------------------------------- #
# Phase 4+ — continuous-price DGP with zone × time confounding
# --------------------------------------------------------------------------- #


def simulate_continuous_price(
    config: MarketplaceConfig | None = None,
    *,
    confound_strength: float = 0.8,
    price_noise_sigma: float = 0.08,
    zone_pop_effect: float = 0.30,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Continuous log-price DGP where price is *confounded* by zone × time.

    A revenue-managed platform sets higher prices exactly when/where demand is
    high (rush hours, popular zones). Naive OLS of log-quantity on log-price
    therefore mixes the demand curve with the pricing policy and is biased
    upward (toward zero / positive) by construction. Controlling for
    hour-of-day + zone (DML) removes the confounding; the residual price
    variation (``price_noise_sigma``) identifies the elasticity.

    Structural model (all logs natural):

        log p  = log p_ref + confound·(0.15·z_diurnal + 0.15·zone_pop) + ε_p
        log q  = log base + log diurnal + zone_pop_effect·zone_pop
                 + e_z·(log p − log p_ref) + ε_q

    ``e_z`` is the per-zone elasticity (reused from the binary DGP band).
    No spillover and no capacity cap in this variant — this phase isolates
    *confounding* bias, not interference; stated in the Phase 4 writeup.

    Returns ``(df, truth)`` where ``truth`` carries everything needed to
    score estimators and to evaluate counterfactual revenue exactly:
    per-zone true elasticities, per-zone demand scales, and the mean
    elasticity (the estimand of a homogeneous log-log model under this
    balanced design).
    """
    cfg = config or MarketplaceConfig()
    sim = MarketplaceSimulator(cfg)  # reuse elasticity + diurnal construction
    rng = np.random.default_rng(cfg.seed + 500_000)  # separate stream from binary sim

    n_t, n_z = cfg.n_time_buckets, cfg.n_zones
    diurnal = sim._diurnal                       # (n_t,), mean 1
    if np.any(diurnal <= 0):
        # log(diurnal) below would silently fill log-quantity with NaN.
        raise ValueError(
            "simulate_continuous_price needs a strictly positive diurnal pattern; "
            f"diurnal_amplitude={cfg.diurnal_amplitude} drives it to "
            f"{float(diurnal.min()):.3f}. Lower diurnal_amplitude."
        )
    elast = sim._elasticities                    # (n_z,)
    zone_pop = rng.normal(0.0, 1.0, size=n_z)    # zone popularity (confounder)

    z_diurnal = (diurnal - diurnal.mean()) / max(diurnal.std(), 1e-9)
    log_p_ref = np.log(cfg.price_control)

    t_idx = np.repeat(np.arange(n_t), n_z)
    z_idx = np.tile(np.arange(n_z), n_t)

    log_price = (
        log_p_ref
        + confound_strength * (0.15 * z_diurnal[t_idx] + 0.15 * zone_pop[z_idx])
        + rng.normal(0.0, price_noise_sigma, size=n_t * n_z)
    )
    log_q = (
        np.log(cfg.base_demand)
        + np.log(diurnal[t_idx])
        + zone_pop_effect * zone_pop[z_idx]
        + elast[z_idx] * (log_price - log_p_ref)
        + rng.normal(0.0, cfg.noise_sigma, size=n_t * n_z)
    )

    df = pd.DataFrame(
        {
            "timestamp": t_idx,
            "hour": t_idx % 24,
            "zone": z_idx,
            "log_price": log_price,
            "log_quantity": log_q,
            "price": np.exp(log_price),
            "quantity": np.exp(log_q),
            "elasticity_true": elast[z_idx],
        }
    )
    truth = {
        "elasticities": elast.tolist(),
        "mean_elasticity": float(elast.mean()),
        "zone_pop": zone_pop.tolist(),
        # Expected demand scale of each zone at the reference price
        # (E[exp(ε_q)] correction is a common factor, irrelevant to uplift %).
        "zone_scale": (cfg.base_demand * np.exp(zone_pop_effect * zone_pop)).tolist(),
        "price_ref": float(cfg.price_control),
        "confound_strength": float(confound_strength),
        "price_noise_sigma": float(price_noise_sigma),
    }
    return df, truth
