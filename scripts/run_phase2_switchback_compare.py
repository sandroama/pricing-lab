"""Phase 2 — switchback vs. naive A/B head-to-head, swept over spillover.

Headline: switchback design recovers true ATE within ~5% across all
spillover strengths; naive A/B bias scales with spillover strength.
"""

from __future__ import annotations

import json
from pathlib import Path

from pricelab.evaluation.compare import run_phase2_switchback_vs_naive
from pricelab.simulation.marketplace import MarketplaceConfig

REPO = Path(__file__).resolve().parent.parent
RESULTS = REPO / "docs" / "results"

SPILLOVER_GRID = [0.0, 0.15, 0.35, 0.50, 0.70]


def main() -> int:
    rows: list[dict] = []
    print("\n── Phase 2: switchback vs. naive A/B under varying spillover\n")
    for s in SPILLOVER_GRID:
        cfg = MarketplaceConfig(
            n_zones=8,
            n_time_buckets=24 * 28,         # 4 weeks → 28 switchback blocks
            spillover_strength=s,
            seed=42,
        )
        cmp_ = run_phase2_switchback_vs_naive(cfg)
        for r in cmp_.as_rows():
            r["spillover_strength"] = s
            rows.append(r)
        # console summary
        naive = next(r for r in cmp_.as_rows() if "naive" in r["estimator"])
        sb = next(r for r in cmp_.as_rows() if "switchback" in r["estimator"])
        print(
            f"  spillover={s:.2f}  "
            f"naive bias={naive['bias_pct'] * 100:>5.1f}%  "
            f"switchback bias={sb['bias_pct'] * 100:>5.1f}%  "
            f"gap={(naive['bias_pct'] - sb['bias_pct']) * 100:>+5.1f}pp"
        )

    RESULTS.mkdir(parents=True, exist_ok=True)
    out_json = RESULTS / "phase2_switchback_vs_naive.json"
    out_md = RESULTS / "phase2_switchback_vs_naive.md"
    out_json.write_text(json.dumps(rows, indent=2) + "\n")

    md = [
        "# Phase 2 — switchback vs. naive A/B\n",
        "| Spillover | Estimator | Point | True ATE | Bias % | Covers truth |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        md.append(
            f"| {r['spillover_strength']:.2f} | `{r['estimator']}` | "
            f"{r['point_estimate']:.2f} | {r['true_ate']:.2f} | "
            f"{r['bias_pct'] * 100:.1f}% | {'✅' if r['covers_truth'] else '❌'} |"
        )
    out_md.write_text("\n".join(md) + "\n")

    print(f"\n  → {out_json.relative_to(REPO.parent)}")
    print(f"  → {out_md.relative_to(REPO.parent)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
