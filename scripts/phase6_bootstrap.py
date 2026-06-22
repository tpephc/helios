# scripts/phase6_bootstrap.py
"""Phase 6 Step 3E — Stationary block bootstrap on Δ_Sharpe.

Implements bootstrap_delta_sharpe per SPEC §5.4:
    B = 5000 replications
    L = max(5, h) where h is the candidate's effective horizon
    NAV-level aligned bootstrap: challenger and ARM_B resampled with
    the same block indices to preserve common market calendar structure.
    Statistic: Δ_Sharpe = Sharpe(challenger) - Sharpe(ARM_B)

Key design decisions (Step 3E lock):
    1. Alignment first: inner join on date before bootstrap.
    2. Common index: same block indices applied to both series per
       replication. Preserves common market shocks.
    3. NOT position-level paired (excluded per SPEC §5.4 rationale:
       adaptive exits change slot timing, breaking paired structure).
    4. NOT independent bootstrap (would lose common calendar structure).
    5. L = max(5, h) per SPEC exact wording. Callers must supply
       block_length; do not substitute mean_holding_days.
    6. Supplementary output only — not a gate criterion.

Reference: Lo (2002) "The Statistics of Sharpe Ratios."
    Stationary block bootstrap: Politis & Romano (1994).
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


# =====================================================================
# Helper 1 — NAV return alignment
# =====================================================================


def _align_nav_returns(
    challenger_nav: pd.DataFrame,
    arm_b_nav: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Inner-join challenger and ARM_B NAV on date; return aligned returns.

    Drops the first row of each series (daily_log_return = 0.0 by
    construction in the NAV builder) and any rows with non-finite values.

    Returns:
        (c_rets, a_rets, n_obs)
        c_rets: challenger log returns, shape (n_obs,)
        a_rets: ARM_B log returns, shape (n_obs,)
        n_obs: number of aligned observations
    """
    c = challenger_nav[["date", "daily_log_return"]].copy()
    a = arm_b_nav[["date", "daily_log_return"]].copy()

    merged = c.merge(a, on="date", suffixes=("_c", "_a"))

    # Drop construction row (row 0: daily_log_return = 0.0 by NAV builder
    # convention). iloc[1:] is safe because inner join preserves row order
    # and both series start on the same date after alignment.
    merged = merged.iloc[1:]

    # Drop non-finite
    finite_mask = (
        np.isfinite(merged["daily_log_return_c"]) &
        np.isfinite(merged["daily_log_return_a"])
    )
    merged = merged[finite_mask]

    c_rets = merged["daily_log_return_c"].to_numpy(dtype=float)
    a_rets = merged["daily_log_return_a"].to_numpy(dtype=float)
    return c_rets, a_rets, len(c_rets)


# =====================================================================
# Helper 2 — stationary block index generator
# =====================================================================


def _stationary_block_indices(
    n_obs: int,
    block_length: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Generate one set of stationary block bootstrap indices.

    Politis & Romano (1994) stationary block bootstrap:
        - Block start positions: uniform on [0, n_obs)
        - Block lengths: geometric with mean = block_length
        - Wrap-around (circular) at series end
        - Output length = n_obs

    Returns:
        indices: int array of shape (n_obs,) with values in [0, n_obs)
    """
    p = 1.0 / block_length
    indices = np.empty(n_obs, dtype=np.intp)
    idx = 0
    while idx < n_obs:
        start = int(rng.integers(0, n_obs))
        length = int(rng.geometric(p))
        for k in range(length):
            if idx >= n_obs:
                break
            indices[idx] = (start + k) % n_obs
            idx += 1
    return indices


# =====================================================================
# Helper 3 — Sharpe from log returns
# =====================================================================


def _sharpe_from_log_returns(log_rets: np.ndarray) -> float:
    """Annualised Sharpe from daily log returns (252 trading days).

    Sharpe = mean(r) / std(r, ddof=1) * sqrt(252)
    Returns nan if n < 2 or std == 0.
    """
    if len(log_rets) < 2:
        return float("nan")
    mu = np.mean(log_rets)
    sd = np.std(log_rets, ddof=1)
    if sd == 0.0:
        return float("nan")
    return float(mu / sd * np.sqrt(252))


# =====================================================================
# Main bootstrap function
# =====================================================================


def bootstrap_delta_sharpe(
    challenger_nav: pd.DataFrame,
    arm_b_nav: pd.DataFrame,
    block_length: int,
    n_bootstrap: int = 5000,
    seed: int = 0,
) -> dict[str, float | int]:
    """Stationary block bootstrap on Δ_Sharpe = Sharpe(challenger) - Sharpe(ARM_B).

    Per SPEC §5.4. Supplementary output, not a gate criterion.

    Bootstrap uses common block indices for challenger and ARM_B per
    replication (NAV-level aligned bootstrap), preserving the common
    market calendar structure. This differs from independent bootstrap
    and from position-level paired bootstrap (excluded per SPEC §5.4).

    Args:
        challenger_nav: DataFrame [date, nav, daily_log_return].
            Output of evaluate_candidate or evaluate_candidate_adaptive.
        arm_b_nav: Same format, ARM_B canonical path.
        block_length: L = max(5, h) per SPEC §5.4. Do NOT substitute
            mean_holding_days without SPEC amendment.
        n_bootstrap: B replications. SPEC default = 5000.
        seed: Deterministic RNG seed (--bootstrap-seed CLI value).

    Returns dict with keys:
        observed_delta_sharpe:      float — Sharpe(challenger) - Sharpe(ARM_B)
        challenger_sharpe:          float — observed challenger Sharpe
        arm_b_sharpe:               float — observed ARM_B Sharpe
        ci_025:                     float — 2.5th percentile of bootstrap Δ
        ci_500:                     float — 50th percentile (bootstrap median)
        ci_975:                     float — 97.5th percentile of bootstrap Δ
        ci_050:                     float — 5th percentile (90% CI lower)
        ci_950:                     float — 95th percentile (90% CI upper)
        bootstrap_prob_delta_le_zero: float — P(Δ_boot ≤ 0) under bootstrap dist
                                      (NOT a formal H0 p-value)
        n_obs:                      int — aligned observation count
        block_length:               int — L used
        n_bootstrap:                int — B used
        n_bootstrap_valid:          int — replications with finite Δ
        seed:                       int — seed used
    """
    # ── Align series on date ─────────────────────────────────────────
    c_rets, a_rets, n_obs = _align_nav_returns(challenger_nav, arm_b_nav)

    if n_obs < block_length:
        log.warning(
            "bootstrap_delta_sharpe: n_obs=%d < block_length=%d. "
            "Returning nan.",
            n_obs, block_length,
        )
        nan = float("nan")
        return {
            "observed_delta_sharpe":         nan,
            "challenger_sharpe":             nan,
            "arm_b_sharpe":                  nan,
            "ci_025":                        nan,
            "ci_500":                        nan,
            "ci_975":                        nan,
            "ci_050":                        nan,
            "ci_950":                        nan,
            "bootstrap_prob_delta_le_zero":  nan,
            "n_obs":                         n_obs,
            "block_length":                  block_length,
            "n_bootstrap":                   n_bootstrap,
            "n_bootstrap_valid":             0,
            "seed":                          seed,
        }

    # ── Observed statistics ───────────────────────────────────────────
    sharpe_c_obs = _sharpe_from_log_returns(c_rets)
    sharpe_a_obs = _sharpe_from_log_returns(a_rets)
    delta_obs    = sharpe_c_obs - sharpe_a_obs

    log.info(
        "bootstrap_delta_sharpe: n_obs=%d block_length=%d "
        "challenger_sharpe=%.4f arm_b_sharpe=%.4f delta=%.4f",
        n_obs, block_length, sharpe_c_obs, sharpe_a_obs, delta_obs,
    )

    # ── Bootstrap with common index ───────────────────────────────────
    rng = np.random.default_rng(seed)
    delta_boot = np.empty(n_bootstrap, dtype=float)

    for b in range(n_bootstrap):
        # Same indices applied to both series — preserves calendar structure.
        idx = _stationary_block_indices(n_obs, block_length, rng)
        s_c = _sharpe_from_log_returns(c_rets[idx])
        s_a = _sharpe_from_log_returns(a_rets[idx])
        delta_boot[b] = s_c - s_a

    # ── Summarise ─────────────────────────────────────────────────────
    valid_mask = np.isfinite(delta_boot)
    n_valid    = int(valid_mask.sum())

    if n_valid < n_bootstrap * 0.9:
        log.warning(
            "bootstrap_delta_sharpe: %d / %d replications produced "
            "non-finite Δ_Sharpe. CIs may be unreliable.",
            n_bootstrap - n_valid, n_bootstrap,
        )

    delta_valid = delta_boot[valid_mask]

    ci_025 = float(np.percentile(delta_valid, 2.5))
    ci_500 = float(np.percentile(delta_valid, 50.0))
    ci_975 = float(np.percentile(delta_valid, 97.5))
    ci_050 = float(np.percentile(delta_valid, 5.0))
    ci_950 = float(np.percentile(delta_valid, 95.0))
    prob_le_zero = float(np.mean(delta_valid <= 0.0))

    log.info(
        "bootstrap_delta_sharpe: 95%% CI [%.4f, %.4f] "
        "prob_delta_le_zero=%.4f (B=%d valid=%d seed=%d)",
        ci_025, ci_975, prob_le_zero, n_bootstrap, n_valid, seed,
    )

    return {
        "observed_delta_sharpe":         float(delta_obs),
        "challenger_sharpe":             float(sharpe_c_obs),
        "arm_b_sharpe":                  float(sharpe_a_obs),
        "ci_025":                        ci_025,
        "ci_500":                        ci_500,
        "ci_975":                        ci_975,
        "ci_050":                        ci_050,
        "ci_950":                        ci_950,
        "bootstrap_prob_delta_le_zero":  prob_le_zero,
        "n_obs":                         n_obs,
        "block_length":                  block_length,
        "n_bootstrap":                   n_bootstrap,
        "n_bootstrap_valid":             n_valid,
        "seed":                          seed,
    }
