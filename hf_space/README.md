---
title: pricing-lab
emoji: 📈
colorFrom: indigo
colorTo: pink
sdk: streamlit
sdk_version: 1.39.0
app_file: app.py
pinned: false
license: mit
---

# pricing-lab

Causal-first dynamic pricing — under spillover, naive A/B bias climbs from
15.9% to 82.5% while a switchback Hájek design stays at 3.9%
(`docs/results/phase2_switchback_vs_naive.json`).

Seven tabs: a live naive-vs-switchback demo, the Phase-2 spillover sweep,
and Phase 4 (Double ML) / Phase 5 (segment pricing) / Phase 6 (real Citi
Bike data) results read verbatim from the committed `docs/results/*.json`.

[GitHub](https://github.com/sandroama/pricing-lab)
