from __future__ import annotations

import copy
from typing import Dict, List
import pandas as pd
from .config import Settings
from .engine import run_backtest


def run_cost_stress_test(
    df: pd.DataFrame,
    symbol: str,
    base_settings: Settings,
    strategy: str,
    base_commission: float = 0.50,
    base_slippage: float = 0.25
) -> pd.DataFrame:
    """
    Stress tests strategy profitability across elevated transaction costs:
    - Spread/commission multipliers: x1.0, x1.25, x1.50, x2.0
    - Slippage levels: 0, 1, 2, 5, 10 ticks
    """
    cost_scenarios = [
        {"name": "Frictionless", "comm_mult": 0.0, "slip_ticks": 0},
        {"name": "Base Costs (1x)", "comm_mult": 1.0, "slip_ticks": 1},
        {"name": "+25% Spread", "comm_mult": 1.25, "slip_ticks": 1},
        {"name": "+50% Spread", "comm_mult": 1.50, "slip_ticks": 2},
        {"name": "+100% Spread (2x)", "comm_mult": 2.0, "slip_ticks": 3},
        {"name": "High Slippage (5t)", "comm_mult": 1.50, "slip_ticks": 5},
        {"name": "Severe Stress (10t)", "comm_mult": 2.0, "slip_ticks": 10},
    ]

    results = []

    for sc in cost_scenarios:
        s = copy.deepcopy(base_settings)
        s.commission_per_unit = base_commission * sc["comm_mult"]
        s.slippage_points = base_slippage * sc["slip_ticks"]

        trades, stats = run_backtest(df, symbol, s, strategy)

        results.append({
            "scenario": sc["name"],
            "comm_per_unit": round(s.commission_per_unit, 2),
            "slippage_points": round(s.slippage_points, 2),
            "trades": stats["trades"],
            "win_rate_pct": stats["win_rate_pct"],
            "profit_factor": stats["profit_factor"],
            "expectancy_R": stats["expectancy_R"],
            "net_pnl": stats["net_pnl"],
            "max_drawdown_pct": stats["max_drawdown_pct"],
            "final_balance": stats["final_balance"],
        })

    res_df = pd.DataFrame(results)
    return res_df
