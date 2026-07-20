"""End-to-end Phase-1 / Phase-2 comparison harnesses.

Each function:
- Builds the simulator with a given config.
- Runs each estimator against the simulated data.
- Returns an `EstimatorComparison` with bias, SE, and bias-percent for each
  estimator vs. the simulator's known true ATE.
- The comparison is deterministic given a config seed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pricelab.estimators.ate import AteResult, naive_ab_ate, switchback_ate
from pricelab.simulation.marketplace import MarketplaceConfig, MarketplaceSimulator


@dataclass
class EstimatorComparison:
    """Side-by-side estimator results against a known true ATE."""

    true_ate: float
    results: list[AteResult] = field(default_factory=list)
    config: MarketplaceConfig = field(default_factory=MarketplaceConfig)

    def as_rows(self) -> list[dict[str, float | int | str | bool]]:
        rows = []
        for r in self.results:
            rows.append({
                **r.as_dict(),
                "true_ate": float(self.true_ate),
                "bias": float(r.bias_vs(self.true_ate)),
                "bias_pct": float(r.bias_pct(self.true_ate)),
                "covers_truth": bool(r.ci95[0] <= self.true_ate <= r.ci95[1]),
            })
        return rows

    def headline(self) -> str:
        lines = [f"true ATE = {self.true_ate:.2f}"]
        for r in self.results:
            bias_pct = r.bias_pct(self.true_ate) * 100
            lines.append(
                f"  {r.estimator:<28} {r.point_estimate:>8.2f}  "
                f"bias={r.bias_vs(self.true_ate):>+7.2f}  ({bias_pct:5.1f}%)  "
                f"SE={r.standard_error:.2f}"
            )
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Phase 1: naive A/B baseline against a spillover-rich DGP.
# --------------------------------------------------------------------------- #


def run_phase1_naive_ab(config: MarketplaceConfig | None = None) -> EstimatorComparison:
    """Naive A/B on a marketplace with non-trivial spillover.

    Headline: even on a moderate spillover (default `spillover_strength=0.35`),
    the naive A/B estimator under-estimates the true ATE by a measurable margin
    because treated demand leaks into control cells in the same hour.
    """
    sim = MarketplaceSimulator(config)
    log = sim.simulate(design="ab_random")
    naive = naive_ab_ate(log.df, outcome="revenue")
    return EstimatorComparison(true_ate=log.true_ate_revenue, results=[naive], config=sim.cfg)


# --------------------------------------------------------------------------- #
# Phase 2: switchback head-to-head against naive A/B on the same DGP.
# --------------------------------------------------------------------------- #


def run_phase2_switchback_vs_naive(config: MarketplaceConfig | None = None) -> EstimatorComparison:
    """Compare switchback (clustered Hájek) against naive A/B on identical DGP.

    The marketplace is simulated *twice* — once under each design — because the
    designs differ in how they assign treatment to (time, zone) cells. The
    same underlying DGP parameters are used so the true ATE is identical.

    Returns both estimator results in one comparison so the dashboard / report
    can show "naive bias = X%, switchback bias = Y%, gap = Z%".
    """
    cfg = config or MarketplaceConfig()
    sim_ab = MarketplaceSimulator(cfg)
    sim_sb = MarketplaceSimulator(cfg)

    log_ab = sim_ab.simulate(design="ab_random")
    log_sb = sim_sb.simulate(design="switchback")

    naive = naive_ab_ate(log_ab.df, outcome="revenue")
    sb = switchback_ate(log_sb.df, outcome="revenue", block_hours=cfg.switchback_block_hours)

    # Both designs share the same true_ate from the DGP, so either is fine.
    return EstimatorComparison(
        true_ate=log_ab.true_ate_revenue,
        results=[naive, sb],
        config=cfg,
    )
