from __future__ import annotations

from typing import Dict
import numpy as np
import pandas as pd


def run_monte_carlo(
    trades_df: pd.DataFrame,
    initial_balance: float = 10000.0,
    iterations: int = 1000,
    risk_per_trade: float = 0.0025,
    seed: int = 42
) -> Dict[str, float | str]:
    """
    Trade-Order Sequence Sensitivity & Loss Clustering Analysis:
    Evaluates how sensitive the strategy performance is to the sequential order of trades
    (e.g., if losing trades cluster together).

    GOVERNANCE COMPLIANCE:
    - This analysis does NOT infer or predict future market profitability.
    - Bootstrap resampling evaluates permutation sensitivity of the observed sample.
    - Analytical Worst-Case calculates the exact drawdown if all observed losses cluster sequentially.
    """
    if trades_df.empty or len(trades_df) < 3:
        return {
            "iterations": 0,
            "sample_trades": len(trades_df),
            "mean_expectancy_R": 0.0,
            "ci_95_lower_R": 0.0,
            "ci_95_upper_R": 0.0,
            "median_resampled_dd_pct": 0.0,
            "dd_95th_percentile_pct": 0.0,
            "worst_resampled_dd_pct": 0.0,
            "analytical_worst_case_dd_pct": 0.0,
            "loss_trades_count": 0,
            "prob_dd_over_5pct": 0.0,
            "prob_dd_over_10pct": 0.0,
            "bootstrap_positive_finish_pct": 0.0,
            "governance_note": "Insufficient sample size (N < 3) for sensitivity analysis."
        }

    pnl_series = trades_df["pnl_cash"].values
    r_series = trades_df["r_multiple"].values
    n = len(pnl_series)
    losses_count = int(np.sum(pnl_series < 0))

    # 1. Analytical Worst-Case Loss Clustering:
    # If all L observed losses occur consecutively from inception
    analytical_worst_dd = (1.0 - (1.0 - risk_per_trade) ** losses_count) * 100.0

    # 2. Bootstrap Resampling (Trade-Order Permutation Sensitivity)
    np.random.seed(seed)
    sim_expectancies = []
    sim_max_dds = []
    sim_finals = []

    for _ in range(iterations):
        sample_indices = np.random.choice(n, size=n, replace=True)
        sampled_pnl = pnl_series[sample_indices]
        sampled_r = r_series[sample_indices]

        equity = initial_balance + np.cumsum(sampled_pnl)
        peaks = np.maximum.accumulate(equity)
        drawdowns = (equity - peaks) / peaks
        max_dd = -np.min(drawdowns) * 100.0

        sim_expectancies.append(np.mean(sampled_r))
        sim_max_dds.append(max_dd)
        sim_finals.append(equity[-1])

    sim_expectancies = np.array(sim_expectancies)
    sim_max_dds = np.array(sim_max_dds)
    sim_finals = np.array(sim_finals)

    return {
        "iterations": iterations,
        "sample_trades": n,
        "loss_trades_count": losses_count,
        "mean_expectancy_R": float(round(np.mean(sim_expectancies), 2)),
        "ci_95_lower_R": float(round(np.percentile(sim_expectancies, 2.5), 2)),
        "ci_95_upper_R": float(round(np.percentile(sim_expectancies, 97.5), 2)),
        "median_resampled_dd_pct": float(round(np.median(sim_max_dds), 2)),
        "dd_95th_percentile_pct": float(round(np.percentile(sim_max_dds, 95), 2)),
        "worst_resampled_dd_pct": float(round(np.max(sim_max_dds), 2)),
        "analytical_worst_case_dd_pct": float(round(analytical_worst_dd, 2)),
        "prob_dd_over_5pct": float(round(np.mean(sim_max_dds > 5.0) * 100.0, 1)),
        "prob_dd_over_10pct": float(round(np.mean(sim_max_dds > 10.0) * 100.0, 1)),
        "bootstrap_positive_finish_pct": float(round(np.mean(sim_finals > initial_balance) * 100.0, 1)),
        "governance_note": "Trade-order sensitivity only. Does NOT predict future profitability."
    }
