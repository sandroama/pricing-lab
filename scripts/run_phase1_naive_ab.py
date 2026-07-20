"""Phase 1 — naive A/B baseline against a spillover-rich DGP.

Headline: even moderate spillover causes naive A/B to systematically
under-estimate the true ATE. We sweep spillover_strength and write a
JSON for the portfolio aggregator.
"""

from __future__ import annotations

import json
from pathlib import Path

from pricelab.evaluation.compare import run_phase1_naive_ab
from pricelab.simulation.marketplace import MarketplaceConfig

REPO = Path(__file__).resolve().parent.parent
RESULTS = REPO / "docs" / "results"


SPILLOVER_GRID = [0.0, 0.15, 0.35, 0.50, 0.70]


def main() -> int:
    rows: list[dict] = []
    print("\n── Phase 1: naive A/B under varying spillover\n")
    for s in SPILLOVER_GRID:
        cfg = MarketplaceConfig(
            n_zones=8,
            n_time_buckets=24 * 28,         # 4 weeks
            spillover_strength=s,
            seed=42,
        )
        cmp_ = run_phase1_naive_ab(cfg)
        for r in cmp_.as_rows():
            r["spillover_strength"] = s
            rows.append(r)
            print(
                f"  spillover={s:.2f}  estimator={r['estimator']:<24} "
                f"point={r['point_estimate']:>8.2f}  true={r['true_ate']:>8.2f}  "
                f"bias_pct={r['bias_pct'] * 100:>5.1f}%"
            )

    RESULTS.mkdir(parents=True, exist_ok=True)
    out_json = RESULTS / "phase1_naive_ab.json"
    out_md = RESULTS / "phase1_naive_ab.md"
    out_json.write_text(json.dumps(rows, indent=2) + "\n")

    md = ["# Phase 1 — naive A/B under spillover\n",
          "| Spillover | Estimator | Point | True ATE | Bias | Bias % | Covers truth |",
          "|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(
            f"| {r['spillover_strength']:.2f} | `{r['estimator']}` | "
            f"{r['point_estimate']:.2f} | {r['true_ate']:.2f} | "
            f"{r['bias']:+.2f} | {r['bias_pct'] * 100:.1f}% | "
            f"{'✅' if r['covers_truth'] else '❌'} |"
        )
    out_md.write_text("\n".join(md) + "\n")

    print(f"\n  → {out_json.relative_to(REPO.parent)}")
    print(f"  → {out_md.relative_to(REPO.parent)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
