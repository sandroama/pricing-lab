# Phase 3b — sub-day switchback: stratification vs the aliasing spike

**Synthetic, deterministic, CPU-only.** 50 seeds, heavy spillover (0.7), 4-week horizon, 8 zones. Pre-registered falsifiable claim: *hour-of-day stratification removes the `block_hours=4` aliasing spike* (NEXT_STEPS milestone candidate 1).

| Arm | Randomization | Block h | Estimator | Mean bias | RMSE | Mean SE | Coverage | Mean \|diurnal gap\| |
|---|---|---:|---|---:|---:|---:|---:|---:|
| alternating_4h_hajek | alternating | 4 | hajek | +31.46 | 261.20 | 63.50 | 0% | 0.355 |
| alternating_4h_adjusted | alternating | 4 | adjusted | — | — | — | — | not identified (rank-deficient: treatment collinear with hour-of-day) |
| iid_4h_hajek | iid | 4 | hajek | -6.36 | 65.19 | 66.57 | 96% | 0.063 |
| iid_4h_adjusted | iid | 4 | adjusted | +0.58 | 2.19 | 2.03 | 90% | 0.063 |
| stratified_4h_hajek | stratified_daily | 4 | hajek | -8.21 | 81.59 | 66.17 | 86% | 0.076 |
| stratified_4h_adjusted | stratified_daily | 4 | adjusted | -0.15 | 1.86 | 2.01 | 94% | 0.076 |
| alternating_24h_hajek | alternating | 24 | hajek | -0.09 | 2.03 | 2.04 | 94% | 0.000 |

The last column is the per-seed |mean diurnal exposure of T − of C|; 0 means treatment saw exactly the same demand pattern as control. `mean |bias| %` (in the JSON) is inflated by seeds whose true ATE is near zero (the per-seed elasticity draw can make the truth small or negative), so RMSE and coverage are the headline metrics here.

## Verdict

Supported for design-side stratification: alternating 4h blocks give RMSE 261 with 0% CI coverage, while stratified-daily randomization + hour/zone adjustment gives RMSE 1.86 with 94% coverage — at the daily-block anchor (RMSE 2.03). Analysis-side stratification alone is structurally impossible under strict alternation: treatment is collinear with hour-of-day, and the adjusted estimator was unidentified in 50/50 seeds.

## Reading the table

- **Alternating 4h + Hájek** reproduces Phase 3's spike distributionally: the strict T/C/T/C schedule locks treatment to a fixed diurnal phase — the exposure gap is identical in every seed (the random start only flips its sign) — so coverage collapses and RMSE is two orders of magnitude above the daily-block anchor.
- **Alternating 4h + adjustment** is not a fix at all: with treatment a deterministic function of hour-of-day, hour fixed effects are collinear with treatment and the estimator correctly refuses to return a number. Regression adjustment cannot repair a confounded assignment schedule.
- **Randomizing the schedule (iid or stratified-daily) removes the systematic aliasing** — the Hájek point estimate becomes unbiased and its CI covers — but sub-day block means still ride the diurnal wave, so the Hájek SE is enormous (~30x the anchor): unbiased but useless for decisions.
- **Randomized schedule + hour/zone adjustment** (now identified, because treated hours vary across days) restores anchor-level RMSE, SE, and coverage. The stratified-daily variant is the pre-registered fix; iid lands close behind it.

Regenerate: `make phase3b` (deterministic, CPU, ~1 min).
