"""End-to-end smoke pipeline.

Runs both Phase 1 + Phase 2 with default config, prints a summary, and
asserts the headline claim (switchback bias < naive bias under spillover).
Used by `make smoke` and CI.
"""

from __future__ import annotations

import sys

from pricelab.evaluation.compare import (
    run_phase1_naive_ab,
    run_phase2_switchback_vs_naive,
)
from pricelab.simulation.marketplace import MarketplaceConfig


def main() -> int:
    print("\n── pricing-lab smoke")

    # Use a 4-week horizon so switchback has 28 blocks (statistical power
    # dominates over diurnal-aliasing variance) and a strong-spillover regime
    # where the SUTVA violation in naive A/B is large enough to detect.
    cfg = MarketplaceConfig(
        n_zones=8,
        n_time_buckets=24 * 28,
        spillover_strength=0.80,
        seed=42,
    )

    # Phase 1 — naive A/B baseline
    p1 = run_phase1_naive_ab(cfg)
    print(f"\n[Phase 1] {p1.headline()}")

    # Phase 2 — switchback head-to-head
    p2 = run_phase2_switchback_vs_naive(cfg)
    print(f"\n[Phase 2] {p2.headline()}")

    naive = next(r for r in p2.results if "naive" in r.estimator)
    sb = next(r for r in p2.results if "switchback" in r.estimator)
    if abs(sb.bias_vs(p2.true_ate)) >= abs(naive.bias_vs(p2.true_ate)):
        print("\n❌ Smoke FAIL: switchback should beat naive under spillover.")
        return 1

    print("\n✅ Smoke OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
