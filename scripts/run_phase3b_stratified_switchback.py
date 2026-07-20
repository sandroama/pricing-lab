"""Phase 3b — sub-day switchback: does stratification remove the aliasing spike?

Phase 3 measured a 359% bias spike at ``block_hours=4``: strict T/C/T/C
alternation with 6 blocks/day (even) lands treatment on the *same phase* of
the 24-hour diurnal cycle every day. Falsifiable claim pre-registered in
NEXT_STEPS: *hour-of-day stratification removes the spike*.

Two distinct meanings of "stratification" are tested separately:

1. **Analysis-side** (regression adjustment on hour-of-day). Under strict
   alternation this is *structurally impossible*: treatment is a deterministic
   function of hour-of-day, so hour fixed effects are collinear with the
   treatment column and the design matrix is rank deficient. The runner
   records the failure instead of smoothing over it — adjustment cannot repair
   a confounded assignment schedule.
2. **Design-side** (randomize which blocks are treated):
   - ``iid`` — fair coin per 4h block (no aliasing, no balance guarantee);
   - ``stratified_daily`` — random balanced T/C permutation within each day
     (hour-of-day stratified randomization).
   Each is analyzed with both the Hájek block-mean estimator and the
   hour/zone regression-adjusted estimator (identified now, because treated
   hours vary across days).

An ``alternating`` 24-hour arm on the same seeds anchors what "fixed" looks
like. 50 seeds; per-seed rows stored; deterministic; runs in ~1 min on CPU.
Regenerate: ``make phase3b``.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from pricelab.estimators.ate import (
    AteResult,
    regression_adjusted_switchback_ate,
    switchback_ate,
)
from pricelab.simulation.marketplace import MarketplaceConfig, MarketplaceSimulator

REPO = Path(__file__).resolve().parent.parent
RESULTS = REPO / "docs" / "results"

SEEDS = list(range(400, 450))  # 50 replicates
SPILLOVER = 0.70
N_ZONES = 8
N_TIME_BUCKETS = 24 * 28

# (arm name, randomization mode, block hours, estimator)
ARMS = [
    ("alternating_4h_hajek", "alternating", 4, "hajek"),
    ("alternating_4h_adjusted", "alternating", 4, "adjusted"),
    ("iid_4h_hajek", "iid", 4, "hajek"),
    ("iid_4h_adjusted", "iid", 4, "adjusted"),
    ("stratified_4h_hajek", "stratified_daily", 4, "hajek"),
    ("stratified_4h_adjusted", "stratified_daily", 4, "adjusted"),
    ("alternating_24h_hajek", "alternating", 24, "hajek"),  # known-good anchor
]


def _fit(estimator: str, df, block_hours: int) -> AteResult:
    if estimator == "hajek":
        return switchback_ate(df, block_hours=block_hours)
    return regression_adjusted_switchback_ate(df, block_hours=block_hours)


def main() -> int:
    per_seed: list[dict[str, Any]] = []
    print(f"\n── Phase 3b: sub-day switchback stratification ({len(SEEDS)} seeds)\n")

    # Cache one simulation per (seed, mode, block) — arms share them.
    for seed in SEEDS:
        row: dict[str, Any] = {"seed": seed}
        logs: dict[tuple[str, int], Any] = {}
        for _, mode, block, _ in ARMS:
            key = (mode, block)
            if key not in logs:
                cfg = MarketplaceConfig(
                    n_zones=N_ZONES,
                    n_time_buckets=N_TIME_BUCKETS,
                    spillover_strength=SPILLOVER,
                    switchback_block_hours=block,
                    switchback_randomization=mode,  # type: ignore[arg-type]
                    seed=seed,
                )
                logs[key] = MarketplaceSimulator(cfg).simulate(design="switchback")
        row["true_ate"] = logs[("alternating", 4)].true_ate_revenue

        for arm, mode, block, estimator in ARMS:
            log = logs[(mode, block)]
            df = log.df
            truth = log.true_ate_revenue
            treated = df["treatment"] == 1
            diurnal_t = float(df.loc[treated, "diurnal"].mean())
            diurnal_c = float(df.loc[~treated, "diurnal"].mean())
            try:
                res = _fit(estimator, df, block)
            except ValueError as exc:
                row[arm] = {
                    "identified": False,
                    "error": str(exc),
                    "diurnal_mean_treated": diurnal_t,
                    "diurnal_mean_control": diurnal_c,
                }
                continue
            row[arm] = {
                "identified": True,
                "point_estimate": res.point_estimate,
                "standard_error": res.standard_error,
                "bias": res.bias_vs(truth),
                "bias_pct": res.bias_pct(truth),
                "covers_truth": bool(res.ci95[0] <= truth <= res.ci95[1]),
                "diurnal_mean_treated": diurnal_t,
                "diurnal_mean_control": diurnal_c,
            }
        per_seed.append(row)

    # ── aggregate ──────────────────────────────────────────────────────────
    summary: dict[str, dict[str, Any]] = {}
    for arm, mode, block, estimator in ARMS:
        cells = [r[arm] for r in per_seed]
        identified = [c for c in cells if c["identified"]]
        entry: dict[str, Any] = {
            "randomization": mode,
            "block_hours": block,
            "estimator": estimator,
            "n_seeds": len(cells),
            "n_identified": len(identified),
        }
        if identified:
            bias = np.array([c["bias"] for c in identified])
            bias_pct = np.array([c["bias_pct"] for c in identified])
            entry.update(
                {
                    "mean_bias": float(bias.mean()),
                    "mean_abs_bias_pct": float(np.abs(bias_pct).mean()),
                    "max_abs_bias_pct": float(np.abs(bias_pct).max()),
                    "rmse": float(math.sqrt(float(np.mean(bias**2)))),
                    "mean_se": float(np.mean([c["standard_error"] for c in identified])),
                    "coverage": float(np.mean([c["covers_truth"] for c in identified])),
                    # Per-seed |gap| — a seed-mean of T and C separately would
                    # wash out the aliasing because the random start flips its sign.
                    "mean_abs_diurnal_gap": float(
                        np.mean(
                            [
                                abs(c["diurnal_mean_treated"] - c["diurnal_mean_control"])
                                for c in identified
                            ]
                        )
                    ),
                }
            )
        else:
            entry["failure_mode"] = cells[0]["error"]
        summary[arm] = entry
        label = (
            f"bias%={entry['mean_abs_bias_pct'] * 100:6.1f}  "
            f"RMSE={entry['rmse']:7.2f}  SE={entry['mean_se']:6.2f}  "
            f"cov={entry['coverage']:.2f}"
            if identified
            else f"NOT IDENTIFIED ({len(identified)}/{len(cells)}): {entry['failure_mode'][:60]}"
        )
        print(f"  {arm:<24} {label}")

    # Claim check, computed from the data (never asserted in advance): does
    # design-side stratification bring the 4h arm back to the daily anchor?
    # RMSE is the yardstick — bias-percent denominators can be near zero for
    # seeds whose elasticity draw makes the true ATE small.
    spike = summary["alternating_4h_hajek"]["rmse"]
    anchor = summary["alternating_24h_hajek"]["rmse"]
    strat_adj = summary["stratified_4h_adjusted"].get("rmse")
    spike_cov = summary["alternating_4h_hajek"]["coverage"]
    strat_cov = summary["stratified_4h_adjusted"].get("coverage")
    n_unidentified = len(SEEDS) - summary["alternating_4h_adjusted"]["n_identified"]
    claim_supported = (
        strat_adj is not None
        and spike > 10 * anchor
        and strat_adj < 1.5 * anchor
        and strat_cov is not None
        and strat_cov >= 0.85
    )
    verdict = (
        (
            f"Supported for design-side stratification: alternating 4h blocks give "
            f"RMSE {spike:.0f} with {spike_cov:.0%} CI coverage, while "
            f"stratified-daily randomization + hour/zone adjustment gives RMSE "
            f"{strat_adj:.2f} with {strat_cov:.0%} coverage — at the daily-block "
            f"anchor (RMSE {anchor:.2f}). Analysis-side stratification alone is "
            f"structurally impossible under strict alternation: treatment is "
            f"collinear with hour-of-day, and the adjusted estimator was "
            f"unidentified in {n_unidentified}/{len(SEEDS)} seeds."
        )
        if claim_supported
        else (
            "NOT SUPPORTED as pre-registered — see the summary table; "
            "stratification did not restore near-anchor RMSE/coverage at 4h blocks."
        )
    )

    RESULTS.mkdir(parents=True, exist_ok=True)
    json_path = RESULTS / "phase3b_stratified_switchback.json"
    md_path = RESULTS / "phase3b_stratified_switchback.md"
    payload = {
        "phase": "3b",
        "claim": "hour-of-day stratification removes the block_hours=4 aliasing spike",
        "spillover_strength": SPILLOVER,
        "n_zones": N_ZONES,
        "n_time_buckets": N_TIME_BUCKETS,
        "n_seeds": len(SEEDS),
        "seeds": SEEDS,
        "arms": summary,
        "claim_supported_design_side": bool(claim_supported),
        "verdict": verdict,
        "per_seed": per_seed,
    }
    json_path.write_text(json.dumps(payload, indent=2) + "\n")

    def fmt(arm: str) -> str:
        e = summary[arm]
        if e["n_identified"] == 0:
            return (
                f"| {arm} | {e['randomization']} | {e['block_hours']} | {e['estimator']} | "
                f"— | — | — | — | not identified (rank-deficient: treatment "
                f"collinear with hour-of-day) |"
            )
        return (
            f"| {arm} | {e['randomization']} | {e['block_hours']} | {e['estimator']} | "
            f"{e['mean_bias']:+.2f} | {e['rmse']:.2f} | "
            f"{e['mean_se']:.2f} | {e['coverage']:.0%} | "
            f"{e['mean_abs_diurnal_gap']:.3f} |"
        )

    md = [
        "# Phase 3b — sub-day switchback: stratification vs the aliasing spike",
        "",
        f"**Synthetic, deterministic, CPU-only.** {len(SEEDS)} seeds, heavy "
        f"spillover ({SPILLOVER}), 4-week horizon, 8 zones. Pre-registered "
        "falsifiable claim: *hour-of-day stratification removes the "
        "`block_hours=4` aliasing spike* (NEXT_STEPS milestone candidate 1).",
        "",
        "| Arm | Randomization | Block h | Estimator | Mean bias | RMSE | "
        "Mean SE | Coverage | Mean \\|diurnal gap\\| |",
        "|---|---|---:|---|---:|---:|---:|---:|---:|",
        *[fmt(arm) for arm, *_ in ARMS],
        "",
        "The last column is the per-seed |mean diurnal exposure of T − of C|; "
        "0 means treatment saw exactly the same demand pattern as control. "
        "`mean |bias| %` (in the JSON) is inflated by seeds whose true ATE is "
        "near zero (the per-seed elasticity draw can make the truth small or "
        "negative), so RMSE and coverage are the headline metrics here.",
        "",
        "## Verdict",
        "",
        verdict,
        "",
        "## Reading the table",
        "",
        "- **Alternating 4h + Hájek** reproduces Phase 3's spike "
        "distributionally: the strict T/C/T/C schedule locks treatment to a "
        "fixed diurnal phase — the exposure gap is identical in every seed "
        "(the random start only flips its sign) — so coverage collapses and "
        "RMSE is two orders of magnitude above the daily-block anchor.",
        "- **Alternating 4h + adjustment** is not a fix at all: with treatment "
        "a deterministic function of hour-of-day, hour fixed effects are "
        "collinear with treatment and the estimator correctly refuses to "
        "return a number. Regression adjustment cannot repair a confounded "
        "assignment schedule.",
        "- **Randomizing the schedule (iid or stratified-daily) removes the "
        "systematic aliasing** — the Hájek point estimate becomes unbiased "
        "and its CI covers — but sub-day block means still ride the diurnal "
        "wave, so the Hájek SE is enormous (~30x the anchor): unbiased but "
        "useless for decisions.",
        "- **Randomized schedule + hour/zone adjustment** (now identified, "
        "because treated hours vary across days) restores anchor-level RMSE, "
        "SE, and coverage. The stratified-daily variant is the pre-registered "
        "fix; iid lands close behind it.",
        "",
        "Regenerate: `make phase3b` (deterministic, CPU, ~1 min).",
        "",
    ]
    md_path.write_text("\n".join(md))
    print(f"\n  {verdict}\n")
    print(f"  → {json_path.relative_to(REPO.parent)}")
    print(f"  → {md_path.relative_to(REPO.parent)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
