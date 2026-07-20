"""ATE estimators for the pricing-lab marketplace simulator.

Two estimators that get compared head-to-head:

1. **Naive A/B (`naive_ab_ate`)** — difference-in-means on per-cell revenue.
   This is what most product analysts compute. It is **biased** under
   spillover because demand from treated cells leaks into control cells in
   the same time bucket. The bias scales with the spillover strength of the
   underlying DGP.

2. **Switchback Hájek (`switchback_ate`)** — clusters the experiment by
   time-block (the unit at which treatment was actually assigned in the
   switchback design), then computes the difference of cluster-means
   weighted by cluster size. SUTVA holds across time blocks, so the
   estimate is approximately unbiased (the residual bias scales with
   noise + capacity binding, not spillover).

Both estimators return an `AteResult` with a point estimate, an analytic
SE, and a 95% normal-approximation CI. Significance is intentionally not
flagged — the recruiter-facing point is bias, not p-values.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats


@dataclass(frozen=True)
class AteResult:
    """A single ATE estimate with its analytic standard error."""

    estimator: str
    point_estimate: float
    standard_error: float
    n_treatment: int
    n_control: int
    critical_value: float = 1.96
    degrees_of_freedom: int | None = None
    uncertainty_method: str | None = None

    @property
    def ci95(self) -> tuple[float, float]:
        return (
            self.point_estimate - self.critical_value * self.standard_error,
            self.point_estimate + self.critical_value * self.standard_error,
        )

    def bias_vs(self, true_ate: float) -> float:
        """Signed bias relative to the true ATE."""
        return self.point_estimate - true_ate

    def bias_pct(self, true_ate: float) -> float:
        """Absolute bias as a fraction of the true ATE magnitude."""
        if abs(true_ate) < 1e-12:
            return float("nan")
        return abs(self.point_estimate - true_ate) / abs(true_ate)

    def as_dict(self) -> dict[str, float | int | str]:
        result: dict[str, float | int | str] = {
            "estimator": self.estimator,
            "point_estimate": float(self.point_estimate),
            "standard_error": float(self.standard_error),
            "ci95_low": float(self.ci95[0]),
            "ci95_high": float(self.ci95[1]),
            "n_treatment": int(self.n_treatment),
            "n_control": int(self.n_control),
        }
        if self.degrees_of_freedom is not None:
            result["degrees_of_freedom"] = int(self.degrees_of_freedom)
            result["critical_value"] = float(self.critical_value)
        if self.uncertainty_method is not None:
            result["uncertainty_method"] = self.uncertainty_method
        return result


# --------------------------------------------------------------------------- #
# Estimators
# --------------------------------------------------------------------------- #


def naive_ab_ate(df: pd.DataFrame, *, outcome: str = "revenue") -> AteResult:
    """Difference-in-means on per-cell outcome. Biased under spillover.

    Expects columns: ``treatment ∈ {0, 1}``, ``outcome``.
    SE = sqrt(var_t/n_t + var_c/n_c) (Welch).
    """
    _validate_df(df, outcome)
    t = df.loc[df["treatment"] == 1, outcome].to_numpy()
    c = df.loc[df["treatment"] == 0, outcome].to_numpy()
    if t.size == 0 or c.size == 0:
        raise ValueError("naive_ab_ate: empty treatment or control group")

    point = float(t.mean() - c.mean())
    var_t = float(t.var(ddof=1)) if t.size > 1 else 0.0
    var_c = float(c.var(ddof=1)) if c.size > 1 else 0.0
    se = math.sqrt(var_t / t.size + var_c / c.size)

    return AteResult(
        estimator="naive_ab_diff_in_means",
        point_estimate=point,
        standard_error=se,
        n_treatment=int(t.size),
        n_control=int(c.size),
    )


def switchback_ate(
    df: pd.DataFrame,
    *,
    outcome: str = "revenue",
    block_col: str = "switchback_block",
    block_hours: int | None = None,
) -> AteResult:
    """Cluster-weighted ATE using time-blocks as clusters.

    Two ways to identify blocks:
      - Pass ``block_col`` already in df (preferred).
      - Pass ``block_hours``; we'll compute ``df["timestamp"] // block_hours``.

    The estimator:
        ATE_hat = mean_over_treated_blocks(block_mean) - mean_over_control_blocks(block_mean)
    where each block contributes one observation (the within-block mean of
    ``outcome``). SE uses the between-block variance — clustered SE.

    This is the Hájek estimator with cluster-level weights. Under switchback
    randomization, blocks are i.i.d. → SUTVA holds → ~unbiased.
    """
    _validate_df(df, outcome)
    df = df.copy()
    if block_col not in df.columns:
        if block_hours is None or block_hours <= 0:
            raise ValueError(
                f"switchback_ate: column '{block_col}' missing and block_hours not provided"
            )
        if "timestamp" not in df.columns:
            raise ValueError("switchback_ate: cannot derive blocks without 'timestamp' column")
        df[block_col] = df["timestamp"] // block_hours

    # Within-block treatment must be uniform for switchback to apply.
    block_treat = df.groupby(block_col)["treatment"].nunique()
    if (block_treat > 1).any():
        raise ValueError(
            "switchback_ate: each block must have a single treatment value; "
            "use the switchback design when simulating."
        )

    block_mean = df.groupby(block_col)[outcome].mean()
    block_t = df.groupby(block_col)["treatment"].first()
    treated = block_mean[block_t == 1].to_numpy()
    control = block_mean[block_t == 0].to_numpy()

    if treated.size == 0 or control.size == 0:
        raise ValueError("switchback_ate: empty treated or control block set")

    point = float(treated.mean() - control.mean())
    var_t = float(treated.var(ddof=1)) if treated.size > 1 else 0.0
    var_c = float(control.var(ddof=1)) if control.size > 1 else 0.0
    se = math.sqrt(var_t / treated.size + var_c / control.size)

    return AteResult(
        estimator="switchback_hajek",
        point_estimate=point,
        standard_error=se,
        n_treatment=int(treated.size),
        n_control=int(control.size),
    )


def regression_adjusted_switchback_ate(
    df: pd.DataFrame,
    *,
    outcome: str = "revenue",
    block_col: str = "switchback_block",
    block_hours: int | None = None,
    covariates: tuple[str, ...] = ("zone", "hour"),
    categorical_covariates: tuple[str, ...] = ("zone", "hour"),
    period_hours: int = 24,
) -> AteResult:
    """Lin-style switchback ATE with block-clustered CR1 uncertainty.

    The outcome regression includes centered pre-treatment covariates and
    treatment-by-covariate interactions. Centering makes the treatment
    coefficient the sample-average treatment effect rather than the effect at
    an arbitrary reference category. Uncertainty uses a CR1 sandwich clustered
    at the randomized switchback block, with a small-sample
    ``t(n_blocks - 2)`` critical value.

    ``hour`` is derived as ``timestamp % period_hours`` when requested but not
    present. The default adjustment uses zone and hour-of-day fixed effects;
    callers can pass continuous pre-treatment features such as lagged demand.
    """
    _validate_df(df, outcome)
    work = df.copy()
    if block_col not in work.columns:
        if block_hours is None or block_hours <= 0:
            raise ValueError(
                f"regression_adjusted_switchback_ate: column '{block_col}' missing "
                "and block_hours not provided"
            )
        if "timestamp" not in work.columns:
            raise ValueError(
                "regression_adjusted_switchback_ate: cannot derive blocks without "
                "'timestamp' column"
            )
        work[block_col] = work["timestamp"] // block_hours

    block_treatment = work.groupby(block_col, observed=True)["treatment"].nunique()
    if (block_treatment > 1).any():
        raise ValueError(
            "regression_adjusted_switchback_ate: each block must have one treatment value"
        )

    if "hour" in covariates and "hour" not in work.columns:
        if "timestamp" not in work.columns or period_hours <= 0:
            raise ValueError("cannot derive hour without timestamp and a positive period_hours")
        work["hour"] = work["timestamp"] % period_hours

    missing = [name for name in covariates if name not in work.columns]
    if missing:
        raise ValueError(f"missing adjustment covariates: {missing}")
    required = [outcome, "treatment", block_col, *covariates]
    if work[required].isna().any().any():
        raise ValueError("regression_adjusted_switchback_ate does not accept missing values")

    block_first = work.groupby(block_col, observed=True)["treatment"].first()
    n_treatment = int((block_first == 1).sum())
    n_control = int((block_first == 0).sum())
    n_clusters = n_treatment + n_control
    if n_treatment < 2 or n_control < 2:
        raise ValueError("at least two treated and two control blocks are required")

    encoded_parts: list[pd.DataFrame] = []
    categorical = set(categorical_covariates)
    for name in covariates:
        if name in categorical or not pd.api.types.is_numeric_dtype(work[name]):
            part = pd.get_dummies(
                work[name].astype("category"), prefix=name, drop_first=True, dtype=float
            )
        else:
            part = work[[name]].astype(float)
        encoded_parts.append(part)

    if encoded_parts:
        adjustment = pd.concat(encoded_parts, axis=1)
        adjustment = adjustment.loc[:, adjustment.nunique(dropna=False) > 1]
        adjustment_matrix = adjustment.to_numpy(dtype=float, copy=True)
        adjustment_matrix -= adjustment_matrix.mean(axis=0, keepdims=True)
    else:
        adjustment_matrix = np.empty((len(work), 0), dtype=float)

    treatment = work["treatment"].to_numpy(dtype=float)
    design = np.column_stack(
        (
            np.ones(len(work), dtype=float),
            treatment,
            adjustment_matrix,
            treatment[:, None] * adjustment_matrix,
        )
    )
    outcome_values = work[outcome].to_numpy(dtype=float)
    rank = int(np.linalg.matrix_rank(design))
    if rank != design.shape[1]:
        raise ValueError("regression-adjustment design matrix is rank deficient")
    if len(work) <= rank:
        raise ValueError("not enough observations for regression adjustment")

    coefficients, *_ = np.linalg.lstsq(design, outcome_values, rcond=None)
    residuals = outcome_values - design @ coefficients
    bread = np.linalg.inv(design.T @ design)
    meat = np.zeros((design.shape[1], design.shape[1]), dtype=float)
    cluster_ids = work[block_col].to_numpy()
    for cluster in pd.unique(cluster_ids):
        mask = cluster_ids == cluster
        score = design[mask].T @ residuals[mask]
        meat += np.outer(score, score)

    # CR1 finite-sample correction. The randomized block, not the cell, is the
    # independent unit; duplicating cell rows must not create fake precision.
    correction = (n_clusters / (n_clusters - 1)) * ((len(work) - 1) / (len(work) - rank))
    covariance = correction * (bread @ meat @ bread)
    treatment_variance = max(float(covariance[1, 1]), 0.0)
    standard_error = math.sqrt(treatment_variance)
    degrees_of_freedom = n_clusters - 2
    critical_value = float(stats.t.ppf(0.975, df=degrees_of_freedom))

    return AteResult(
        estimator="switchback_regression_adjusted",
        point_estimate=float(coefficients[1]),
        standard_error=standard_error,
        n_treatment=n_treatment,
        n_control=n_control,
        critical_value=critical_value,
        degrees_of_freedom=degrees_of_freedom,
        uncertainty_method="CR1 block-clustered sandwich with small-sample t interval",
    )


def _validate_df(df: pd.DataFrame, outcome: str) -> None:
    for col in ("treatment", outcome):
        if col not in df.columns:
            raise ValueError(f"missing required column: '{col}'")
    if not set(df["treatment"].unique()).issubset({0, 1}):
        raise ValueError(f"'treatment' must be 0/1; got values: {sorted(df['treatment'].unique())}")
