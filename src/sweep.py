from __future__ import annotations

import argparse
import copy
import os
from pathlib import Path
import pandas as pd
from .config import load_settings, Settings
from .engine import run_backtest


VALID_STRATEGIES = [
    "boundary_reversion",
    "sweep_reclaim",
    "micro_range",
    "breakout",
    "breakout_retest",
    "composite_regime",
    "hybrid"
]


def run_parameter_sweep(
    csv_path: str,
    symbol: str,
    strategy: str = "boundary_reversion",
    config_path: str = "config/default.json",
    out_dir: str = "reports"
) -> pd.DataFrame:
    base_settings = load_settings(config_path) if os.path.exists(config_path) else Settings()
    df = pd.read_csv(csv_path)

    # In-sample (70%) vs Out-of-sample (30%) chronological split
    split_idx = int(len(df) * 0.70)
    df_train = df.iloc[:split_idx].copy()
    df_test = df.iloc[split_idx:].copy()

    # Parameter grid for robust exploration
    range_minutes_options = [5, 10, 15, 20, 30]
    min_rr_options = [1.0, 1.25, 1.5]
    wick_ratio_options = [0.25, 0.35]
    zone_options = [0.15, 0.20]

    results = []

    print(f"\n=======================================================")
    print(f" AURUM v0.3 Parameter Sweep: {symbol} ({strategy})")
    print(f" Total bars: {len(df):,} | Train: {len(df_train):,} | Test: {len(df_test):,}")
    print(f"=======================================================\n")

    for rm in range_minutes_options:
        for mrr in min_rr_options:
            for wr in wick_ratio_options:
                for zo in zone_options:
                    s = copy.deepcopy(base_settings)
                    s.range_minutes = rm
                    s.min_rr = mrr
                    s.rejection_wick_ratio = wr
                    s.zone_atr = zo

                    # In-sample test
                    trades_is, stats_is = run_backtest(df_train, symbol, s, strategy)
                    # Out-of-sample test
                    trades_oos, stats_oos = run_backtest(df_test, symbol, s, strategy)

                    results.append({
                        "symbol": symbol,
                        "strategy": strategy,
                        "range_minutes": rm,
                        "min_rr": mrr,
                        "wick_ratio": wr,
                        "zone_atr": zo,
                        "is_trades": stats_is["trades"],
                        "is_win_rate": stats_is["win_rate_pct"],
                        "is_profit_factor": stats_is["profit_factor"],
                        "is_expectancy_R": stats_is["expectancy_R"],
                        "is_net_pnl": stats_is["net_pnl"],
                        "oos_trades": stats_oos["trades"],
                        "oos_win_rate": stats_oos["win_rate_pct"],
                        "oos_profit_factor": stats_oos["profit_factor"],
                        "oos_expectancy_R": stats_oos["expectancy_R"],
                        "oos_net_pnl": stats_oos["net_pnl"],
                        "oos_max_dd": stats_oos["max_drawdown_pct"],
                    })

    res_df = pd.DataFrame(results)
    # Sort primarily by Out-of-sample Expectancy R and In-sample Expectancy R
    res_df = res_df.sort_values(by=["oos_expectancy_R", "is_expectancy_R"], ascending=[False, False]).reset_index(drop=True)

    os.makedirs(out_dir, exist_ok=True)
    out_file = Path(out_dir) / f"{symbol}_{strategy}_sweep.csv"
    res_df.to_csv(out_file, index=False)

    print(f"Top 5 parameter configurations by Out-Of-Sample Expectancy R:")
    display_cols = [
        "range_minutes", "min_rr", "wick_ratio", "zone_atr",
        "is_trades", "is_expectancy_R", "is_profit_factor",
        "oos_trades", "oos_expectancy_R", "oos_profit_factor"
    ]
    print(res_df[display_cols].head(5).to_string(index=False))
    print(f"\nFull sweep saved -> {out_file}\n")
    return res_df


def main():
    p = argparse.ArgumentParser(description="Sweep hyperparameters with train/test validation.")
    p.add_argument("--csv", required=True, help="Path to M1 CSV dataset")
    p.add_argument("--symbol", required=True, help="Symbol name (e.g., XAUUSD)")
    p.add_argument("--strategy", choices=VALID_STRATEGIES, default="boundary_reversion")
    p.add_argument("--config", default="config/default.json")
    p.add_argument("--out", default="reports")
    a = p.parse_args()

    run_parameter_sweep(a.csv, a.symbol, a.strategy, a.config, a.out)


if __name__ == "__main__":
    main()
