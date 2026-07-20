# Phase 3 — switchback block-size sensitivity (RQ-P3)

Fixed regime: `spillover_strength=0.7`, `n_zones=8`, `n_time_buckets=672` (4 weeks), `seed=42`. True ATE = **71.87**. Naive A/B reference (block-insensitive) bias = **82.5%**.

| Block hours | Switchback point | Bias % | SE | # blocks (T/C) | Covers truth |
|---:|---:|---:|---:|---:|:--:|
| 1 | 74.52 | 3.7% | 39.23 | 336/336 | ✅ |
| 2 | 68.92 | 4.1% | 54.41 | 168/168 | ✅ |
| 4 | 329.61 | 358.7% | 67.35 | 84/84 | ❌ |
| 8 | 69.70 | 3.0% | 42.60 | 42/42 | ✅ |
| 24 | 69.06 | 3.9% | 2.03 | 14/14 | ✅ |

## Verdict — measured, NOT a clean monotone collapse

The pre-registered RQ-P3 hypothesis was that shrinking the block size
would monotonically collapse switchback bias toward the naive A/B
line. **The data falsifies that.** The bias-vs-block-size curve is
**non-monotone**: the spike is at `block_hours=4` (359% bias), while neighbouring block sizes
(1, 2, 8, 24) all stay within a few percent of the truth.

### Why `block_hours=4` blows up — diurnal aliasing

Treatment alternates strictly `T C T C …` across blocks. With a
4-hour block and a 24-hour diurnal (rush-hour) demand cycle, the 6
blocks per day fall into a fixed even/odd pattern, so treatment lands
on the *same phase* of the diurnal cycle every day. Empirically the
mean diurnal multiplier is **1.18 under treatment vs 0.82 under**
**control** at `block_hours=4` — treatment is systematically exposed
to busier hours, which the estimator misreads as a treatment effect.
At `block_hours=24` the same alternation balances perfectly (mean
diurnal 1.00 under both arms), which is exactly why the daily block
is unbiased and has the tightest SE.

### Practitioner takeaway

Block size is **not** a smooth bias/power dial. A block that is a
divisor of the diurnal period but not a full cycle can alias and
produce *worse* bias than a coarser block. Sub-day switchback blocks
need hour-of-day stratification; otherwise prefer a full-cycle
(24-hour) block. This refines — and partly overturns — the naive
RQ-P3 intuition.

Regenerate: `make phase3` (deterministic, CPU, seconds).
