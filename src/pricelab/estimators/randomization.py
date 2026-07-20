"""Randomization (permutation) inference for switchback block designs.

Design-agnostic cross-check of the analytic clustered intervals (Phase 2c).
The unit of exchangeability is the randomized *block*: under the sharp null
``Y_b(1) = Y_b(0) + tau0`` for every block ``b``, block-mean outcomes with the
hypothesized effect removed are exchangeable, so re-drawing balanced treated
labels gives the exact finite-sample null distribution of the block-mean
difference statistic — no normality, no variance estimate.

Honest scope note: the project's default assignment is *strict alternation
with a random start*, whose true randomization distribution has only two
support points. Permutation over all balanced block labelings therefore tests
block exchangeability (the standard super-population reading), not the exact
alternation design. Reported as such in the Phase-2c writeup.

Both entry points are pure NumPy on block-level summaries and deterministic
given ``seed``.
"""

from __future__ import annotations

import numpy as np


def _permutation_stats(
    block_means: np.ndarray,
    block_treat: np.ndarray,
    n_permutations: int,
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Per-permutation coefficients (A_k, B_k) of the linear map tau0 -> stat.

    Removing a hypothesized effect gives ``y0 = means - tau0 * treat``. For a
    permuted labeling with treated index set T_k, the diff-in-means statistic
    is linear in tau0::

        stat_k(tau0) = mean(y0[T_k]) - mean(y0[C_k]) = A_k - tau0 * B_k

    where A_k uses the raw means and B_k is the (share of originally-treated
    blocks in T_k) minus (share in C_k). Computing (A, B) once lets a CI
    inversion sweep a tau0 grid at no extra permutation cost.
    """
    means = np.asarray(block_means, dtype=float)
    treat = np.asarray(block_treat, dtype=int)
    n_t = int(treat.sum())
    n_c = int(treat.size - n_t)
    if n_t < 2 or n_c < 2:
        raise ValueError("need at least two treated and two control blocks")
    rng = np.random.default_rng(seed)
    # (n_permutations, n_blocks) matrix of permuted block orderings.
    perms = np.argsort(rng.random((n_permutations, treat.size)), axis=1)
    t_idx, c_idx = perms[:, :n_t], perms[:, n_t:]
    a = means[t_idx].mean(axis=1) - means[c_idx].mean(axis=1)
    b = treat[t_idx].mean(axis=1) - treat[c_idx].mean(axis=1)
    return a, b


def block_permutation_pvalue(
    block_means: np.ndarray,
    block_treat: np.ndarray,
    *,
    tau0: float = 0.0,
    n_permutations: int = 2000,
    seed: int = 0,
) -> float:
    """Two-sided permutation p-value for H0: tau = tau0 on block means.

    Statistic: difference of treated/control block-mean averages after
    removing ``tau0`` from treated blocks. Includes the identity permutation
    (add-one correction), so p is in (0, 1].
    """
    means = np.asarray(block_means, dtype=float)
    treat = np.asarray(block_treat, dtype=int)
    a, b = _permutation_stats(means, treat, n_permutations, seed)
    point = means[treat == 1].mean() - means[treat == 0].mean()
    obs = point - tau0
    perm = a - tau0 * b
    return float((1 + np.sum(np.abs(perm) >= abs(obs))) / (1 + n_permutations))


def block_permutation_ci(
    block_means: np.ndarray,
    block_treat: np.ndarray,
    *,
    n_permutations: int = 2000,
    seed: int = 0,
    alpha: float = 0.05,
    grid_halfwidth: float | None = None,
    grid_points: int = 401,
) -> tuple[float, float]:
    """(1 - alpha) randomization CI by test inversion on a tau0 grid.

    Returns the min/max tau0 whose two-sided permutation p-value is >= alpha.
    The grid is centered on the point estimate with halfwidth
    ``grid_halfwidth`` (default: 8 x the Welch block-level SE). Raises if the
    accepted region touches the grid edge, so a too-narrow grid cannot
    silently truncate the interval.
    """
    means = np.asarray(block_means, dtype=float)
    treat = np.asarray(block_treat, dtype=int)
    treated = means[treat == 1]
    control = means[treat == 0]
    point = float(treated.mean() - control.mean())
    if grid_halfwidth is None:
        se = float(np.sqrt(treated.var(ddof=1) / treated.size + control.var(ddof=1) / control.size))
        grid_halfwidth = 8.0 * max(se, 1e-9)
    grid = np.linspace(point - grid_halfwidth, point + grid_halfwidth, grid_points)

    a, b = _permutation_stats(means, treat, n_permutations, seed)
    # (n_permutations, grid_points) broadcast; both dims are small.
    perm = np.abs(a[:, None] - b[:, None] * grid[None, :])
    obs = np.abs(point - grid)[None, :]
    pvals = (1 + (perm >= obs).sum(axis=0)) / (1 + n_permutations)
    accepted = grid[pvals >= alpha]
    if accepted.size == 0:
        raise ValueError("no tau0 accepted — grid or permutation count too small")
    lo, hi = float(accepted.min()), float(accepted.max())
    if lo <= grid[0] or hi >= grid[-1]:
        raise ValueError("randomization CI hit the tau0 grid edge; widen grid_halfwidth")
    return lo, hi
