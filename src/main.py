from __future__ import annotations

import argparse
import os
from pathlib import Path
import openpyxl
import pandas as pd

from .config import Settings, load_settings
from .engine import run_backtest
from .stress_test import run_cost_stress_test
from .monte_carlo import run_monte_carlo
from .matrix_runner import run_window_matrix
from .walk_forward import run_walk_forward


ALL_STRATEGIES = [
    "boundary_reversion",
    "sweep_reclaim",
    "micro_range",
    "breakout",
    "breakout_retest",
    "composite_regime"
]


def load_dataset(csv_path: str | None = None, xlsx_path: str | None = None, symbol: str = "US100") -> pd.DataFrame:
    if csv_path and os.path.exists(csv_path):
        return pd.read_csv(csv_path)

    if xlsx_path and os.path.exists(xlsx_path):
        wb = openpyxl.load_workbook(xlsx_path, data_only=True)
        sheet_candidates = [f"{symbol}_M1", f"{symbol.upper()}_M1", symbol, symbol.upper()]
        for sc in sheet_candidates:
            if sc in wb.sheetnames:
                rows = list(wb[sc].values)
                if len(rows) > 1:
                    header = [str(c).lower().strip() for c in rows[0]]
                    df = pd.DataFrame(rows[1:], columns=header)
                    return df
        raise ValueError(f"Sheet for symbol {symbol} not found in {xlsx_path}. Available: {wb.sheetnames}")

    raise FileNotFoundError(f"Neither CSV nor Excel dataset found for {symbol}.")


def main():
    p = argparse.ArgumentParser(description="AURUM Research Engine v0.3 — Quantitative Session Research Framework")
    p.add_argument("--csv", default=None, help="Path to M1 CSV file")
    p.add_argument("--xlsx", default="Trading_Analysis_Consolidated.xlsx", help="Path to Excel workbook with M1 sheets")
    p.add_argument("--symbol", default="US100", choices=["US100", "XAUUSD", "US30"], help="Instrument to test")
    p.add_argument("--strategy", default="all", choices=ALL_STRATEGIES + ["all"], help="Strategy hypothesis to test")
    p.add_argument("--config", default="config/default.json", help="Path to configuration JSON")
    p.add_argument("--out", default="reports", help="Output directory for reports and trade logs")
    p.add_argument("--stress-test", action="store_true", help="Run transaction cost & slippage stress test")
    p.add_argument("--monte-carlo", action="store_true", help="Run 1,000-run Monte Carlo bootstrap simulation")
    p.add_argument("--matrix", action="store_true", help="Run Opening Range duration & session window matrix")
    p.add_argument("--walk-forward", action="store_true", help="Run rolling Walk-Forward validation")
    p.add_argument("--full-suite", action="store_true", help="Run full quantitative research suite")

    a = p.parse_args()
    os.makedirs(a.out, exist_ok=True)
    settings = load_settings(a.config) if os.path.exists(a.config) else Settings()

    # Determine data source
    csv_file = a.csv or (f"data/{a.symbol}_M1.csv" if os.path.exists(f"data/{a.symbol}_M1.csv") else None)
    df = load_dataset(csv_path=csv_file, xlsx_path=a.xlsx, symbol=a.symbol)
    print(f"\n=======================================================")
    print(f" AURUM Research Engine v0.3 — {a.symbol}")
    print(f" Dataset: {len(df):,} bars | Local Timezone: {settings.timezone}")
    print(f" Session: {settings.session_start_local} - {settings.session_end_local} (NY Local Time)")
    print(f"=======================================================\n")

    strategies_to_test = ALL_STRATEGIES if a.strategy == "all" else [a.strategy]
    comparison_rows = []
    trade_logs = {}

    for strat in strategies_to_test:
        trades, stats = run_backtest(df, a.symbol, settings, strat)
        trade_logs[strat] = trades
        stats["symbol"] = a.symbol
        stats["strategy"] = strat

        # Save trade log
        if not trades.empty:
            trades_path = os.path.join(a.out, f"{a.symbol}_{strat}_trades.csv")
            trades.to_csv(trades_path, index=False)

        comparison_rows.append(stats)

    report_df = pd.DataFrame(comparison_rows)
    comp_path = os.path.join(a.out, f"{a.symbol}_comparison_v0.3.csv")
    report_df.to_csv(comp_path, index=False)

    print("--- 5 Hypotheses Performance Comparison ---")
    display_cols = ["strategy", "trades", "win_rate_pct", "profit_factor", "expectancy_R", "net_pnl", "max_drawdown_pct"]
    print(report_df[display_cols].to_string(index=False))
    print(f"\nSaved comparison -> {comp_path}\n")

    # Optional Research Modules
    target_strat = strategies_to_test[0] if len(strategies_to_test) == 1 else "composite_regime"

    if a.stress_test or a.full_suite:
        print(f"--- Running Cost Stress Test ({a.symbol} / {target_strat}) ---")
        stress_df = run_cost_stress_test(df, a.symbol, settings, target_strat)
        stress_path = os.path.join(a.out, f"{a.symbol}_{target_strat}_stress_test.csv")
        stress_df.to_csv(stress_path, index=False)
        print(stress_df[["scenario", "trades", "profit_factor", "expectancy_R", "net_pnl"]].to_string(index=False))
        print(f"Saved stress test -> {stress_path}\n")

    if a.monte_carlo or a.full_suite:
        # Use trades from the strategy or composite
        strat_trades = trade_logs.get(target_strat, pd.DataFrame())
        if not strat_trades.empty:
            print(f"--- Running Monte Carlo Resampling (1,000 iterations: {a.symbol} / {target_strat}) ---")
            mc_stats = run_monte_carlo(strat_trades, settings.initial_balance, iterations=1000)
            mc_df = pd.DataFrame([mc_stats])
            mc_path = os.path.join(a.out, f"{a.symbol}_{target_strat}_monte_carlo.csv")
            mc_df.to_csv(mc_path, index=False)
            for k, v in mc_stats.items():
                print(f"  {k:25s}: {v}")
            print(f"Saved Monte Carlo -> {mc_path}\n")

    if a.matrix or a.full_suite:
        print(f"--- Running Parameter Spectrum Matrix ({a.symbol} / {target_strat}) ---")
        matrix_df = run_window_matrix(df, a.symbol, settings, target_strat)
        matrix_path = os.path.join(a.out, f"{a.symbol}_{target_strat}_param_matrix.csv")
        matrix_df.to_csv(matrix_path, index=False)
        print(matrix_df[["opening_range_min", "session_window_min", "trades", "profit_factor", "expectancy_R"]].to_string(index=False))
        print(f"Saved parameter matrix -> {matrix_path}\n")

    if a.walk_forward or a.full_suite:
        print(f"--- Running Rolling Walk-Forward Validation ({a.symbol} / {target_strat}) ---")
        wf_df = run_walk_forward(df, a.symbol, settings, target_strat)
        wf_path = os.path.join(a.out, f"{a.symbol}_{target_strat}_walk_forward.csv")
        wf_df.to_csv(wf_path, index=False)
        print(wf_df.to_string(index=False))
        print(f"Saved walk forward -> {wf_path}\n")


if __name__ == "__main__":
    main()
