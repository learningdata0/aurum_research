from __future__ import annotations

import copy
from typing import List, Tuple
import pandas as pd
from .config import Settings
from .engine import run_backtest


def run_window_matrix(
    df: pd.DataFrame,
    symbol: str,
    base_settings: Settings,
    strategy: str,
    range_minutes_list: List[int] = [5, 10, 15, 20, 30, 45, 60],
    session_duration_minutes: List[int] = [30, 60, 90, 120, 150]
) -> pd.DataFrame:
    """
    Evaluates the parameter spectrum across Opening Range durations and trading session
    windows to check for coherent parameter plateaus vs isolated curve-fit spikes.
    """
    records = []

    print(f"\n--- Running Parameter Matrix for {symbol} ({strategy}) ---")

    for rm in range_minutes_list:
        for dur in session_duration_minutes:
            if dur <= rm:
                continue

            s = copy.deepcopy(base_settings)
            s.range_minutes = rm

            # Local NY start is 09:30 = 570 min
            start_m = 9 * 60 + 30
            end_m = start_m + dur
            end_h = end_m // 60
            end_min = end_m % 60
            s.session_end_local = f"{end_h:02d}:{end_min:02d}"

            trades, stats = run_backtest(df, symbol, s, strategy)

            records.append({
                "symbol": symbol,
                "strategy": strategy,
                "opening_range_min": rm,
                "session_window_min": dur,
                "trading_window_min": dur - rm,
                "trades": stats["trades"],
                "win_rate_pct": stats["win_rate_pct"],
                "profit_factor": stats["profit_factor"],
                "expectancy_R": stats["expectancy_R"],
                "net_pnl": stats["net_pnl"],
                "max_drawdown_pct": stats["max_drawdown_pct"],
            })

    res_df = pd.DataFrame(records)
    return res_df
