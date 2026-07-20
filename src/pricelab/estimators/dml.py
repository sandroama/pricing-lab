"""Price-elasticity estimators for the continuous-price DGP (Phases 4–5).

Two estimators, same contrast as Phases 1–2 but for a *continuous* treatment:

1. **Naive OLS (`ols_elasticity`)** — regress log-quantity on log-price with
   no controls. Under zone × time confounded pricing (platform charges more
   when demand is high) this is biased toward zero / positive by construction.
2. **Double ML (`dml_elasticity`)** — `econml.dml.LinearDML` with linear
   nuisance models, cross-fitted, controlling for hour-of-day + zone dummies.
   Orthogonalization removes the confounding; the residual exogenous price
   noise identifies the elasticity.

Phase 5 adds `segment_elasticities` — `econml.dml.CausalForestDML` with the
zone one-hot as the heterogeneity feature — returning one elasticity per zone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats


@dataclass(frozen=True)
class ElasticityResult:
    """A single elasticity estimate with its standard error."""

    estimator: str
    point_estimate: float
    standard_error: float
    n: int

    @property
    def ci95(self) -> tuple[float, float]:
        z = 1.96
        return (
            self.point_estimate - z * self.standard_error,
            self.point_estimate + z * self.standard_error,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "estimator": self.estimator,
            "point_estimate": float(self.point_estimate),
            "standard_error": float(self.standard_error),
            "ci95_low": float(self.ci95[0]),
            "ci95_high": float(self.ci95[1]),
            "n": int(self.n),
        }


def ols_elasticity(df: pd.DataFrame) -> ElasticityResult:
    """Naive OLS of log-quantity on log-price, no controls. Biased under
    confounded pricing — this is the strawman most dashboards compute."""
    res = stats.linregress(df["log_price"].to_numpy(), df["log_quantity"].to_numpy())
    return ElasticityResult(
        estimator="naive_ols_loglog",
        point_estimate=float(res.slope),
        standard_error=float(res.stderr),
        n=len(df),
    )


def _controls(df: pd.DataFrame) -> np.ndarray:
    """Hour-of-day + zone one-hot control matrix (the confounders)."""
    return np.asarray(
        pd.get_dummies(df[["hour", "zone"]].astype("category"), dtype=float).to_numpy()
    )


def _nuisance() -> Any:
    from sklearn.linear_model import LinearRegression

    # ponytail: the DGP is exactly additive in hour + zone dummies, so linear
    # first stages are correctly specified. RF nuisances were tried first and
    # attenuated the estimate (overfit T|W eats the exogenous price noise) —
    # swap in gradient boosting here if the DGP ever goes non-additive.
    return LinearRegression()


def dml_elasticity(df: pd.DataFrame, *, seed: int = 0) -> ElasticityResult:
    """Cross-fitted LinearDML elasticity controlling for hour + zone."""
    from econml.dml import LinearDML

    W = _controls(df)
    est = LinearDML(model_y=_nuisance(), model_t=_nuisance(), cv=3, random_state=seed)
    est.fit(df["log_quantity"].to_numpy(), df["log_price"].to_numpy(), X=None, W=W)
    inf = est.ate_inference()
    return ElasticityResult(
        estimator="linear_dml",
        point_estimate=float(inf.mean_point),
        standard_error=float(inf.stderr_mean),
        n=len(df),
    )


def segment_elasticities(df: pd.DataFrame, *, seed: int = 0) -> dict[int, float]:
    """Per-zone elasticity via CausalForestDML (zone one-hot as X, hour as W).

    Returns ``{zone: elasticity_hat}``.
    """
    from econml.dml import CausalForestDML

    zones = np.sort(df["zone"].unique())
    X = pd.get_dummies(df["zone"].astype("category"), dtype=float).to_numpy()
    W = pd.get_dummies(df["hour"].astype("category"), dtype=float).to_numpy()
    est = CausalForestDML(
        model_y=_nuisance(),
        model_t=_nuisance(),
        cv=3,
        n_estimators=500,
        min_samples_leaf=20,
        random_state=seed,
    )
    est.fit(df["log_quantity"].to_numpy(), df["log_price"].to_numpy(), X=X, W=W)
    eye = np.eye(len(zones))
    effects = est.effect(eye)
    return {int(z): float(e) for z, e in zip(zones, effects)}
