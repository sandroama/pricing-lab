"""Real-data (Citi Bike) walk-forward naive-vs-adjusted comparison (Phase 6).

Citi Bike publishes trips, not prices, so a price elasticity is **not
identifiable** from this data. The honest transfer of the project's question
("does a naive comparison survive real temporal confounding?") is:

    causal target: effect of an electric bike (vs classic) on trip duration.

E-bike usage is confounded by *when* people ride (hour, weekday) and *who*
rides (member vs casual), so the naive difference-in-means and an adjusted
estimate can disagree — the size and direction of that disagreement is the
Phase 6 deliverable.

The adjusted estimator is hand-rolled **walk-forward partialling-out** (the
Robinson / DML residual-on-residual form): nuisance models E[Y|W] and E[T|W]
are fit on *past* weeks only, then the treatment effect is the OLS slope of
the residualized outcome on the residualized treatment in the *current* week.
EconML's internal cross-fitting shuffles time, so it is not used here;
walk-forward residualization keeps the temporal firewall the project's other
phases insist on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats


@dataclass(frozen=True)
class FoldEstimate:
    """Naive and adjusted effect estimates for one walk-forward fold."""

    fold: int
    n_train: int
    n_test: int
    naive_point: float
    naive_se: float
    adjusted_point: float
    adjusted_se: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "fold": self.fold,
            "n_train": self.n_train,
            "n_test": self.n_test,
            "naive_point": float(self.naive_point),
            "naive_se": float(self.naive_se),
            "adjusted_point": float(self.adjusted_point),
            "adjusted_se": float(self.adjusted_se),
        }


def prepare_trips(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Clean raw Citi Bike trips → analysis frame + a drop-accounting dict.

    Keeps trips with duration in [1, 120] minutes (standard Citi Bike
    cleaning band: sub-minute re-docks and >2h outliers/lost bikes removed).
    """
    df = raw.copy()
    started = pd.to_datetime(df["started_at"])
    ended = pd.to_datetime(df["ended_at"])
    df["duration_min"] = (ended - started).dt.total_seconds() / 60.0
    df["hour"] = started.dt.hour
    df["weekday"] = started.dt.dayofweek
    # Year-qualified ISO week (e.g. 202436): a bare week number breaks the
    # walk-forward temporal firewall across year boundaries (Dec 29-31 can be
    # ISO week 1 of the NEXT year, sorting "earlier" than week 52 and leaking
    # future trips into the training folds).
    iso = started.dt.isocalendar()
    df["week"] = (iso.year.astype(int) * 100 + iso.week.astype(int)).astype(int)
    df["ebike"] = (df["rideable_type"] == "electric_bike").astype(int)
    df["member"] = (df["member_casual"] == "member").astype(int)

    n_raw = len(df)
    keep = df["duration_min"].between(1.0, 120.0)
    dropped = int((~keep).sum())
    df = df.loc[keep].reset_index(drop=True)
    accounting = {"n_raw": n_raw, "n_kept": len(df), "n_dropped_duration": dropped}
    return df, accounting


def _control_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Hour + weekday one-hot + member dummy — the observed confounders."""
    X = pd.get_dummies(df[["hour", "weekday"]].astype("category"), dtype=float)
    X["member"] = df["member"].astype(float)
    return X


def naive_effect(df: pd.DataFrame) -> tuple[float, float]:
    """Difference in mean duration, e-bike minus classic, Welch SE."""
    t = df.loc[df["ebike"] == 1, "duration_min"].to_numpy()
    c = df.loc[df["ebike"] == 0, "duration_min"].to_numpy()
    if t.size < 2 or c.size < 2:
        # Without this, an all-classic (or all-ebike) fold writes NaN into the
        # results JSON silently.
        raise ValueError(
            f"naive_effect: need >=2 e-bike and >=2 classic trips, got {t.size}/{c.size}"
        )
    point = float(t.mean() - c.mean())
    se = float(np.sqrt(t.var(ddof=1) / t.size + c.var(ddof=1) / c.size))
    return point, se


def walk_forward_folds(df: pd.DataFrame, min_train_weeks: int = 1) -> list[tuple[int, pd.Index, pd.Index]]:
    """Yield (week, train_idx, test_idx): train on all strictly-earlier weeks."""
    weeks = sorted(df["week"].unique())
    folds = []
    for i, w in enumerate(weeks):
        if i < min_train_weeks:
            continue
        train = df.index[df["week"] < w]
        test = df.index[df["week"] == w]
        if len(test) and len(train):
            folds.append((int(w), train, test))
    return folds


def estimate_fold(df: pd.DataFrame, train: pd.Index, test: pd.Index) -> FoldEstimate:
    """One walk-forward fold: naive diff-in-means + partialled-out slope."""
    from sklearn.linear_model import LinearRegression

    Xcols = _control_matrix(df)
    Xtr, Xte = Xcols.loc[train].to_numpy(), Xcols.loc[test].to_numpy()
    y_tr, y_te = df.loc[train, "duration_min"].to_numpy(), df.loc[test, "duration_min"].to_numpy()
    t_tr, t_te = df.loc[train, "ebike"].to_numpy(float), df.loc[test, "ebike"].to_numpy(float)

    my = LinearRegression().fit(Xtr, y_tr)
    mt = LinearRegression().fit(Xtr, t_tr)
    y_res = y_te - my.predict(Xte)
    t_res = t_te - mt.predict(Xte)

    reg = stats.linregress(t_res, y_res)
    naive_pt, naive_se = naive_effect(df.loc[test])
    return FoldEstimate(
        fold=int(df.loc[test, "week"].iloc[0]),
        n_train=len(train),
        n_test=len(test),
        naive_point=naive_pt,
        naive_se=naive_se,
        adjusted_point=float(reg.slope),
        adjusted_se=float(reg.stderr),
    )
