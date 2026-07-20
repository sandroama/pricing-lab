"""FastAPI service for the pricing-lab.

Endpoints:
    GET  /health
    POST /v1/simulate          - run the marketplace DGP, return summary stats
    POST /v1/estimate/naive    - naive A/B ATE on the supplied design
    POST /v1/estimate/switchback - switchback Hájek ATE
    POST /v1/compare           - end-to-end Phase-2 head-to-head
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from pricelab import __version__
from pricelab.evaluation.compare import run_phase2_switchback_vs_naive
from pricelab.simulation.marketplace import MarketplaceConfig, MarketplaceSimulator
from pricelab.estimators.ate import naive_ab_ate, switchback_ate

app = FastAPI(
    title="pricing-lab",
    description="Causal-first dynamic pricing lab — switchback designs, ATE estimators.",
    version=__version__,
)


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #


class HealthResponse(BaseModel):
    status: str
    version: str


class ConfigOverrides(BaseModel):
    """Subset of MarketplaceConfig knobs exposed via the API.

    Anything omitted falls back to the dataclass default.
    """

    n_zones: int | None = Field(None, ge=2, le=64)
    n_time_buckets: int | None = Field(None, ge=24, le=24 * 30)
    spillover_strength: float | None = Field(None, ge=0.0, le=1.0)
    price_control: float | None = Field(None, gt=0.0)
    price_treatment: float | None = Field(None, gt=0.0)
    switchback_block_hours: int | None = Field(None, ge=1, le=72)
    seed: int | None = None


class SimulateRequest(BaseModel):
    design: str = Field("ab_random", description="`ab_random` or `switchback`")
    overrides: ConfigOverrides | None = None


class SimulateResponse(BaseModel):
    n_rows: int
    true_ate_revenue: float
    cfg: dict[str, Any]
    summary: dict[str, Any]


class EstimateRequest(BaseModel):
    overrides: ConfigOverrides | None = None


class CompareResponse(BaseModel):
    true_ate: float
    estimators: list[dict[str, Any]]
    cfg: dict[str, Any]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _resolve_config(o: ConfigOverrides | None) -> MarketplaceConfig:
    cfg = MarketplaceConfig()
    if o is None:
        return cfg
    for field_name, value in o.model_dump(exclude_none=True).items():
        setattr(cfg, field_name, value)
    return cfg


def _summarize_log(df: pd.DataFrame) -> dict[str, Any]:
    rev_t = df.loc[df["treatment"] == 1, "revenue"]
    rev_c = df.loc[df["treatment"] == 0, "revenue"]
    return {
        "n_treatment": int(rev_t.size),
        "n_control": int(rev_c.size),
        "mean_revenue_treatment": float(rev_t.mean()) if rev_t.size else 0.0,
        "mean_revenue_control": float(rev_c.mean()) if rev_c.size else 0.0,
    }


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)


@app.post("/v1/simulate", response_model=SimulateResponse, tags=["simulation"])
def simulate(req: SimulateRequest) -> SimulateResponse:
    cfg = _resolve_config(req.overrides)
    sim = MarketplaceSimulator(cfg)
    if req.design not in {"ab_random", "switchback"}:
        raise HTTPException(status_code=422, detail=f"unknown design: {req.design}")
    log = sim.simulate(design=req.design)  # type: ignore[arg-type]
    return SimulateResponse(
        n_rows=int(len(log.df)),
        true_ate_revenue=float(log.true_ate_revenue),
        cfg=cfg.__dict__,
        summary=_summarize_log(log.df),
    )


@app.post("/v1/estimate/naive", tags=["estimation"])
def estimate_naive(req: EstimateRequest) -> dict[str, Any]:
    cfg = _resolve_config(req.overrides)
    sim = MarketplaceSimulator(cfg)
    log = sim.simulate(design="ab_random")
    res = naive_ab_ate(log.df, outcome="revenue")
    return {**res.as_dict(), "true_ate": float(log.true_ate_revenue),
            "bias": float(res.bias_vs(log.true_ate_revenue)),
            "bias_pct": float(res.bias_pct(log.true_ate_revenue))}


@app.post("/v1/estimate/switchback", tags=["estimation"])
def estimate_switchback(req: EstimateRequest) -> dict[str, Any]:
    cfg = _resolve_config(req.overrides)
    sim = MarketplaceSimulator(cfg)
    log = sim.simulate(design="switchback")
    res = switchback_ate(log.df, outcome="revenue", block_hours=cfg.switchback_block_hours)
    return {**res.as_dict(), "true_ate": float(log.true_ate_revenue),
            "bias": float(res.bias_vs(log.true_ate_revenue)),
            "bias_pct": float(res.bias_pct(log.true_ate_revenue))}


@app.post("/v1/compare", response_model=CompareResponse, tags=["estimation"])
def compare(req: EstimateRequest) -> CompareResponse:
    cfg = _resolve_config(req.overrides)
    cmp_ = run_phase2_switchback_vs_naive(cfg)
    return CompareResponse(
        true_ate=float(cmp_.true_ate),
        estimators=cmp_.as_rows(),
        cfg=cfg.__dict__,
    )
