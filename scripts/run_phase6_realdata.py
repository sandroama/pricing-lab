"""Phase 6 — real data: Citi Bike walk-forward naive-vs-adjusted (RQ-P6).

Data: ONE month of official Citi Bike system data — the Jersey City file
``JC-202409-citibike-tripdata.csv.zip`` (~4 MB) from the official open-data
bucket ``https://s3.amazonaws.com/tripdata/``. The full-NYC month file is
~414 MB (over this repo's 300 MB download cap), so the JC subset of the same
system is used; n is reported and labeled.

Citi Bike has no price variation, so **no elasticity is identifiable** — the
honest real-data transfer of this project's question is: does the naive
difference-in-means survive real temporal/composition confounding? Target:
e-bike (vs classic) effect on trip duration, naive vs walk-forward
partialled-out adjustment (hour + weekday + membership controls, nuisances
fit on past weeks only). See ``pricelab/realdata.py``.

Deterministic given the data file. Regenerate with ``make phase6`` after:

    curl -o data/JC-202409-citibike-tripdata.csv.zip \
        https://s3.amazonaws.com/tripdata/JC-202409-citibike-tripdata.csv.zip
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from pricelab.realdata import estimate_fold, naive_effect, prepare_trips, walk_forward_folds

REPO = Path(__file__).resolve().parent.parent
RESULTS = REPO / "docs" / "results"
DATA_ZIP = REPO / "data" / "JC-202409-citibike-tripdata.csv.zip"
DATA_URL = "https://s3.amazonaws.com/tripdata/JC-202409-citibike-tripdata.csv.zip"


def load_trips() -> pd.DataFrame:
    if not DATA_ZIP.exists():
        raise SystemExit(
            f"data file missing: {DATA_ZIP}\nDownload it (≈4 MB, official source):\n"
            f"  curl -o {DATA_ZIP} {DATA_URL}"
        )
    z = zipfile.ZipFile(DATA_ZIP)
    name = next(
        n for n in z.namelist() if n.endswith(".csv") and not n.startswith("__MACOSX")
    )
    return pd.read_csv(z.open(name))


def main() -> int:
    raw = load_trips()
    df, accounting = prepare_trips(raw)
    print(f"\n── Phase 6: Citi Bike JC 2024-09 — {accounting['n_kept']} trips "
          f"({accounting['n_dropped_duration']} dropped outside 1–120 min)\n")

    # Composition diagnostics — the *why* behind any naive/adjusted gap.
    comp = {
        "member_share_ebike": float(df.loc[df["ebike"] == 1, "member"].mean()),
        "member_share_classic": float(df.loc[df["ebike"] == 0, "member"].mean()),
        "weekend_share_ebike": float((df.loc[df["ebike"] == 1, "weekday"] >= 5).mean()),
        "weekend_share_classic": float((df.loc[df["ebike"] == 0, "weekday"] >= 5).mean()),
        "mean_hour_ebike": float(df.loc[df["ebike"] == 1, "hour"].mean()),
        "mean_hour_classic": float(df.loc[df["ebike"] == 0, "hour"].mean()),
        "ebike_share": float(df["ebike"].mean()),
        "mean_duration_member": float(df.loc[df["member"] == 1, "duration_min"].mean()),
        "mean_duration_casual": float(df.loc[df["member"] == 0, "duration_min"].mean()),
    }

    folds = walk_forward_folds(df)
    estimates = [estimate_fold(df, tr, te) for _, tr, te in folds]
    for e in estimates:
        print(f"  week={e.fold}  n_test={e.n_test}  "
              f"naive={e.naive_point:+.3f}±{e.naive_se:.3f}  "
              f"adjusted={e.adjusted_point:+.3f}±{e.adjusted_se:.3f}  (minutes)")

    naive_pts = np.array([e.naive_point for e in estimates])
    adj_pts = np.array([e.adjusted_point for e in estimates])
    n_folds = len(estimates)

    def fold_ci(vals: np.ndarray) -> tuple[float, float]:
        half = float(
            stats.t.ppf(0.975, n_folds - 1) * vals.std(ddof=1) / np.sqrt(n_folds)
        )
        return (float(vals.mean()) - half, float(vals.mean()) + half)

    naive_ci, adj_ci = fold_ci(naive_pts), fold_ci(adj_pts)
    gap = float(naive_pts.mean() - adj_pts.mean())
    full_naive_pt, full_naive_se = naive_effect(df)

    print(f"\n  pooled naive    : {naive_pts.mean():+.3f} min  "
          f"t-CI over {n_folds} folds [{naive_ci[0]:+.3f}, {naive_ci[1]:+.3f}]")
    print(f"  pooled adjusted : {adj_pts.mean():+.3f} min  "
          f"t-CI over {n_folds} folds [{adj_ci[0]:+.3f}, {adj_ci[1]:+.3f}]")
    print(f"  disagreement    : {gap:+.3f} min\n")

    RESULTS.mkdir(parents=True, exist_ok=True)
    payload = {
        "phase": 6,
        "dataset": "Citi Bike system data, Jersey City file, 2024-09 (official S3 bucket)",
        "data_url": DATA_URL,
        "causal_target": "electric-bike (vs classic) effect on trip duration, minutes",
        "accounting": accounting,
        "composition": comp,
        "full_month_naive": {"point": full_naive_pt, "se": full_naive_se},
        "n_folds": n_folds,
        "folds": [e.as_dict() for e in estimates],
        "pooled_naive_mean": float(naive_pts.mean()),
        "pooled_naive_ci95_over_folds": list(naive_ci),
        "pooled_adjusted_mean": float(adj_pts.mean()),
        "pooled_adjusted_ci95_over_folds": list(adj_ci),
        "naive_minus_adjusted": gap,
    }
    (RESULTS / "phase6_realdata.json").write_text(json.dumps(payload, indent=2) + "\n")

    md = [
        "# Phase 6 — real data: Citi Bike walk-forward naive vs adjusted (RQ-P6)\n",
        f"**Real data** (not synthetic): {accounting['n_kept']:,} trips, Citi Bike "
        "**Jersey City** file, September 2024, from the official open-data bucket "
        f"(full-NYC month is ~414 MB, over the repo's download cap; the JC file is the "
        f"same system's official data at ~4 MB). "
        f"{accounting['n_dropped_duration']:,} trips outside the 1–120 min band dropped.\n",
        "**No price exists in this data**, so no elasticity is identifiable — claiming one "
        "would be fabrication. The transferable question is the project's core one: does a "
        "naive group comparison survive real temporal/composition confounding? Target: "
        "e-bike vs classic effect on trip duration.\n",
        f"| Estimator | Effect (min) | 95% t-CI over {n_folds} walk-forward folds |",
        "|---|---:|---:|",
        f"| Naive diff-in-means | {naive_pts.mean():+.3f} | "
        f"[{naive_ci[0]:+.3f}, {naive_ci[1]:+.3f}] |",
        f"| Walk-forward partialled-out (hour+weekday+member) | {adj_pts.mean():+.3f} | "
        f"[{adj_ci[0]:+.3f}, {adj_ci[1]:+.3f}] |",
        "",
        "Per-fold estimates and composition diagnostics: "
        "[`phase6_realdata.json`](phase6_realdata.json).",
        "",
        "## What the estimators say — and why they differ",
        "",
        f"Naive and adjusted estimates disagree by **{gap:+.3f} minutes** "
        f"(naive {naive_pts.mean():+.3f} vs adjusted {adj_pts.mean():+.3f}). "
        "Composition diagnostics measured from the data:",
        "",
        f"- member share: {comp['member_share_ebike']:.1%} of e-bike trips vs "
        f"{comp['member_share_classic']:.1%} of classic trips, and members ride much "
        f"shorter ({comp['mean_duration_member']:.1f} vs {comp['mean_duration_casual']:.1f} "
        "min) — e-bikes carry a casual-heavy, long-trip mix, which drags the naive "
        "estimate toward zero;",
        f"- weekend share: {comp['weekend_share_ebike']:.1%} (e-bike) vs "
        f"{comp['weekend_share_classic']:.1%} (classic);",
        f"- mean start hour: {comp['mean_hour_ebike']:.1f} vs {comp['mean_hour_classic']:.1f}.",
        "",
        "## Honest limits",
        "",
        "- **Selection on unobservables is uncontrolled**: riders *choose* e-bikes, and "
        "trip-purpose/distance are not in the controls, so the adjusted number is a "
        "*covariate-adjusted association*, not a clean causal effect. On real data the "
        "deliverable is the size of the naive-vs-adjusted gap and its explanation, not a "
        "causal victory lap.",
        f"- Jersey City subset (n={accounting['n_kept']:,}), one month, "
        f"{n_folds}-fold walk-forward — CIs over folds are wide by construction.",
        "- Duration is the outcome only because it is what the public feed contains; "
        "with price data the same walk-forward partialling-out plumbing would target "
        "elasticity directly (that is exactly Phase 4's estimator).",
        "",
        "Regenerate: `make phase6` (download command in the script header; ~4 MB, "
        "official source, `data/` is gitignored).",
    ]
    (RESULTS / "phase6_realdata.md").write_text("\n".join(md) + "\n")

    print(f"  → {(RESULTS / 'phase6_realdata.json').relative_to(REPO.parent)}")
    print(f"  → {(RESULTS / 'phase6_realdata.md').relative_to(REPO.parent)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
