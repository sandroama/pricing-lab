# Architecture — pricing-lab

```
            ┌────────────────────────────────────────┐
            │  FastAPI service                       │
            │  /v1/simulate  /v1/estimate/*  /v1/compare │
            └────────────────┬───────────────────────┘
                             │
                             ▼
            ┌────────────────────────────────────────┐
            │  evaluation/compare.py                 │
            │  Phase-1 / Phase-2 head-to-head harness│
            └──────────┬─────────────────────┬───────┘
                       │                     │
                       ▼                     ▼
          ┌────────────────────┐   ┌──────────────────────┐
          │ simulation/        │   │ estimators/ate.py    │
          │ marketplace.py     │   │                      │
          │                    │   │  naive_ab_ate        │
          │  • heterogeneous   │   │  switchback_ate      │
          │    elasticity      │   │  AteResult           │
          │  • diurnal demand  │   │                      │
          │  • spillover       │   │  (clustered SE,      │
          │  • capacity caps   │   │   95% CI, bias %)    │
          │  • log-normal noise│   │                      │
          │                    │   │                      │
          │  designs:          │   └──────────────────────┘
          │    ab_random       │
          │    switchback      │
          │      (balanced     │
          │       alternation)  │
          └──────────┬─────────┘
                     │
                     ▼
          ┌─────────────────────┐
          │ SimulationLog       │
          │   .df               │
          │   .true_ate_revenue │
          └─────────────────────┘
                     │
                     ▼
          ┌─────────────────────────────────┐
          │ docs/results/                   │
          │   phase1_naive_ab.{json, md}    │
          │   phase2_switchback_vs_naive.{json, md} │
          └─────────────────────────────────┘
```

## Layered design

Four layers, each independently testable and ablatable:

1. **Simulation** — synthetic two-sided marketplace with controlled SUTVA
   violations. The DGP is *the lab*: its knobs (`spillover_strength`,
   `n_zones`, `n_time_buckets`, `switchback_block_hours`) are what produce
   the experimental conditions.
2. **Estimators** — pure functions on `pandas.DataFrame`. No side effects,
   no model state. Each estimator owns its own analytic SE.
3. **Evaluation** — Phase-1 / Phase-2 head-to-head harness. Holds the
   *truth* (closed-form analytic + Monte Carlo at spillover=0) and the
   estimator results in one comparison.
4. **Service** — FastAPI thin wrapper. The dashboard reuses the same
   `run_phase2_switchback_vs_naive` entry point, so anything in the UI is
   directly callable over HTTP.

## Why this layout

- **DGP-first.** Most pricing demos start from a regression model and call
  the simulated data "synthetic." Here the DGP is the deliverable — every
  paper-worthy claim is "switchback recovers the truth that *this DGP*
  encodes."
- **Pure estimators.** `naive_ab_ate` and `switchback_ate` take a
  `DataFrame` and return an `AteResult`. They don't know what generated
  the data. This makes adding new estimators (DML, causal forest in Phase
  4) a drop-in.
- **Reproducible.** All sweeps live in `scripts/`, write to
  `docs/results/`, and are picked up by the portfolio aggregator.
- **Honest.** The result tables published in the README report **both**
  estimators on **every** spillover level, with bias signed. No
  cherry-picking.

---

## Visual diagrams (Mermaid)

These render natively on GitHub. The ASCII diagram above is the portable
plain-text version.

### Two-design comparison

```mermaid
flowchart LR
    DGP[MarketplaceSimulator<br/>n_zones × n_time_buckets cells<br/>spillover_strength knob]

    DGP -->|design = ab_random| ABLOG[A/B random log<br/>per-cell T/C]
    DGP -->|design = switchback<br/>balanced alternation| SBLOG[Switchback log<br/>per-block T/C]

    ABLOG --> NAIVE[naive_ab_ate<br/>diff-in-means]
    SBLOG --> SB[switchback_ate<br/>Hájek + clustered SE]

    NAIVE -. biased by spillover .-> CMP[(EstimatorComparison)]
    SB -. ~unbiased (SUTVA holds) .-> CMP

    classDef biased fill:#fee2e2,stroke:#b91c1c
    classDef unbiased fill:#dcfce7,stroke:#15803d
    class NAIVE biased
    class SB unbiased
```

### Spillover mechanism (why naive A/B fails)

```mermaid
flowchart LR
    Z0[Zone A: T<br/>price=12] -- lost demand --> Z1[Zone B: C<br/>price=10<br/>+spillover_in]
    Z1 -- "no spillover<br/>(same price)" --> Z2[Zone C: C<br/>price=10]
    Z2 -- "no spillover<br/>(same price)" --> Z3[Zone D: T<br/>price=12]
    Z3 -- lost demand --> Z0

    classDef T fill:#fef3c7,stroke:#a16207
    classDef C fill:#dbeafe,stroke:#1d4ed8
    class Z0,Z3 T
    class Z1,Z2 C
```

Under switchback, *all zones in a block share the same price*, so no
price differential exists between neighbors → no spillover → SUTVA holds.

### Bias vs. spillover (the headline)

```mermaid
flowchart LR
    S0["spillover=0.00"] -->|naive| N0["15.9% bias"]
    S1["spillover=0.15"] -->|naive| N1["32.1% bias"]
    S2["spillover=0.35"] -->|naive| N2["52.2% bias"]
    S3["spillover=0.50"] -->|naive| N3["66.0% bias"]
    S4["spillover=0.70"] -->|naive| N4["82.5% bias"]

    S0 -->|switchback| SB0["3.9%"]
    S1 -->|switchback| SB1["3.9%"]
    S2 -->|switchback| SB2["3.9%"]
    S3 -->|switchback| SB3["3.9%"]
    S4 -->|switchback| SB4["3.9%"]

    classDef bad fill:#fee2e2,stroke:#b91c1c
    classDef good fill:#dcfce7,stroke:#15803d
    class N0,N1,N2,N3,N4 bad
    class SB0,SB1,SB2,SB3,SB4 good
```
