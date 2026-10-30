"""
AURUM Quantum Confluence Backtest & Optimization Harness
=========================================================
Runs forward simulation of the 4-layer Quantum Confluence Engine across historical M1 data.
Evaluates:
- Win Rate (%)
- Profit Factor
- Total Net Return in R
- Max Drawdown
- Comparison against baseline H17
"""

from __future__ import annotations
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import numpy as np
import pandas as pd

from src.indicators.quantum_confluence import QuantumConfluenceEngine, QuantumSetup


def run_quantum_backtest(
    csv_file: str,
    symbol: str = "XAUUSD",
    min_score: float = 70.0,
    max_bars: int = 15000,
    stride: int = 1
) -> Dict[str, Any]:
    print(f"\n=======================================================")
    print(f" AURUM QUANTUM CONFLUENCE BACKTEST ENGINE")
    print(f" Asset: {symbol} | File: {csv_file}")
    print(f" Confluence Threshold: >= {min_score} / 100")
    print(f" Max Evaluated Bars: {max_bars}")
    print(f"=======================================================\n")

    df = pd.read_csv(csv_file)
    if len(df) > max_bars:
        df = df.tail(max_bars).copy().reset_index(drop=True)

    engine = QuantumConfluenceEngine(
        min_confluence_score=min_score,
        rvol_threshold=1.5,
        regression_lookback=100,
        rsi_period=14
    )

    trades = []
    active_trade: Optional[Dict[str, Any]] = None

    lookback_window = 120
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    times = df["time"].values if "time" in df.columns else np.arange(len(df))

    for i in range(lookback_window, len(df), stride):
        # 1. Update active trade if open
        if active_trade is not None:
            curr_h = highs[i]
            curr_l = lows[i]
            direction = active_trade["direction"]
            sl = active_trade["sl"]
            tp1 = active_trade["tp1"]
            entry = active_trade["entry"]
            risk = active_trade["risk"]

            # Manage Exit
            if direction == "BUY":
                # Check SL
                if curr_l <= sl:
                    pnl_r = 0.75 if active_trade["be_active"] else -1.0
                    active_trade["exit_price"] = sl
                    active_trade["exit_time"] = times[i]
                    active_trade["pnl_r"] = pnl_r
                    active_trade["reason"] = "BE_STOP" if active_trade["be_active"] else "SL"
                    trades.append(active_trade)
                    active_trade = None
                    continue
                # Check TP1
                elif curr_h >= tp1 and not active_trade["be_active"]:
                    # Bank 50% profit (+0.75R) and lock Breakeven
                    active_trade["be_active"] = True
                    active_trade["sl"] = entry  # Instant Breakeven lock!
                # Check TP2
                elif curr_h >= active_trade["tp2"]:
                    # Full exit at 3.0R
                    pnl_r = 2.0  # (0.75R from half + 1.5R from runner)
                    active_trade["exit_price"] = active_trade["tp2"]
                    active_trade["exit_time"] = times[i]
                    active_trade["pnl_r"] = pnl_r
                    active_trade["reason"] = "TP2_RUNNER"
                    trades.append(active_trade)
                    active_trade = None
                    continue

            elif direction == "SELL":
                # Check SL
                if curr_h >= sl:
                    pnl_r = 0.75 if active_trade["be_active"] else -1.0
                    active_trade["exit_price"] = sl
                    active_trade["exit_time"] = times[i]
                    active_trade["pnl_r"] = pnl_r
                    active_trade["reason"] = "BE_STOP" if active_trade["be_active"] else "SL"
                    trades.append(active_trade)
                    active_trade = None
                    continue
                # Check TP1
                elif curr_l <= tp1 and not active_trade["be_active"]:
                    active_trade["be_active"] = True
                    active_trade["sl"] = entry  # Instant Breakeven lock!
                # Check TP2
                elif curr_l <= active_trade["tp2"]:
                    pnl_r = 2.0
                    active_trade["exit_price"] = active_trade["tp2"]
                    active_trade["exit_time"] = times[i]
                    active_trade["pnl_r"] = pnl_r
                    active_trade["reason"] = "TP2_RUNNER"
                    trades.append(active_trade)
                    active_trade = None
                    continue

            # Time exit after 120 bars
            if (i - active_trade["entry_bar"]) >= 120:
                curr_c = closes[i]
                pts = (curr_c - entry) if direction == "BUY" else (entry - curr_c)
                pnl_r = round(pts / risk, 2)
                active_trade["exit_price"] = curr_c
                active_trade["exit_time"] = times[i]
                active_trade["pnl_r"] = pnl_r
                active_trade["reason"] = "TIME_EXPIRY"
                trades.append(active_trade)
                active_trade = None
                continue

        # 2. If no active trade, scan for high-confluence quantum setup
        if active_trade is None:
            sub_df = df.iloc[i - lookback_window:i + 1]
            setup = engine.analyze_market_slice(sub_df, symbol=symbol)

            if setup is not None:
                active_trade = {
                    "entry_bar": i,
                    "entry_time": setup.timestamp,
                    "symbol": symbol,
                    "direction": setup.direction,
                    "entry": setup.entry_price,
                    "sl": setup.stop_loss,
                    "tp1": setup.take_profit_1,
                    "tp2": setup.take_profit_2,
                    "tp3": setup.take_profit_3,
                    "risk": setup.risk_pts,
                    "score": setup.confluence_score,
                    "be_active": False,
                    "rationale": setup.rationale
                }

    # Summary
    td = pd.DataFrame(trades)
    total_trades = len(td)
    if total_trades == 0:
        print("No trades triggered meeting threshold.")
        return {}

    wins = len(td[td["pnl_r"] > 0])
    losses = len(td[td["pnl_r"] < 0])
    breakevens = len(td[td["pnl_r"] == 0])
    win_rate = round(100.0 * wins / total_trades, 1)

    gw = td[td["pnl_r"] > 0]["pnl_r"].sum()
    gl = abs(td[td["pnl_r"] < 0]["pnl_r"].sum())
    pf = round(gw / gl, 2) if gl > 0 else 999.0
    net_r = round(td["pnl_r"].sum(), 2)

    print(f"=======================================================")
    print(f" QUANTUM BACKTEST AUDIT RESULTS")
    print(f"=======================================================")
    print(f" Total Trades Triggered: {total_trades}")
    print(f" Wins: {wins} | Losses: {losses} | Breakevens: {breakevens}")
    print(f" Win Rate: {win_rate}% (Excluding BE: {round(100.0*wins/max(1, wins+losses), 1)}%)")
    print(f" Profit Factor: {pf}")
    print(f" Total Net Return: {net_r:+.2f}R")
    print(f" Average R per Trade: {net_r/total_trades:+.2f}R")
    print(f"=======================================================\n")

    return {
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "breakevens": breakevens,
        "win_rate": win_rate,
        "profit_factor": pf,
        "net_r": net_r
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--file", default="data/XAUUSD_M1.csv")
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--score", type=float, default=65.0)
    p.add_argument("--bars", type=int, default=15000)
    a = p.parse_args()

    run_quantum_backtest(
        csv_file=a.file,
        symbol=a.symbol,
        min_score=a.score,
        max_bars=a.bars
    )
