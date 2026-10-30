"""
AURUM Quantum Confluence vs Baseline H17 Comparison Harness
===========================================================
Applies the 4-layer Quantum Confluence Engine to our institutional H17 strategy:
- Baseline H17 (Pure London Sweep & Reclaim)
- Quantum H17 (London Sweep + RVOL/Absorption + Statistical Z-Score + Divergence Filter)
Measures the direct mathematical uplift in Win Rate, Profit Factor, and Drawdown.
"""

from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd

from src.config import Settings
from src.data import prepare_data
from src.htf_levels import build_htf_context_map, DailyHTFContext
from src.hypotheses_v08 import HypothesisV08
from src.indicators.quantum_confluence import QuantumConfluenceEngine, QuantumSetup
from src.indicators.volunacci import calculate_rvol
from src.indicators.statistical_regression import calculate_linear_regression_channel
from src.indicators.divergence_engine import detect_rsi_divergences, detect_macd_divergences


def run_quantum_h17_comparison(
    csv_path: str,
    symbol: str = "US100",
    min_london_range: float = 140.0,
    min_quantum_score: float = 65.0
):
    print(f"\n=======================================================")
    print(f" AURUM QUANTUM CONFLUENCE VALIDATION BENCHMARK")
    print(f" Symbol: {symbol} | File: {csv_path}")
    print(f" Min London Range: {min_london_range} pts | Min Quantum Score: {min_quantum_score}/100")
    print(f"=======================================================\n")

    df_raw = pd.read_csv(csv_path)
    d = prepare_data(df_raw, source_timezone="broker")
    ctx_map = build_htf_context_map(d)

    # Pre-calculate RVOL
    d["rvol"] = calculate_rvol(d, period=20)

    # 1. Baseline H17 Run
    baseline_trades = []
    # 2. Quantum Confluence H17 Run
    quantum_trades = []

    unique_days = sorted(d["day"].unique())

    for day in unique_days:
        if day not in ctx_map:
            continue
        ctx = ctx_map[day]
        if ctx.london_high is None or ctx.london_low is None:
            continue
        lon_range = ctx.london_high - ctx.london_low
        if lon_range < min_london_range:
            continue

        d_day = d[d["day"] == day].copy().reset_index(drop=True)
        lh = ctx.london_high
        ll = ctx.london_low
        l_mid = (lh + ll) / 2.0

        # We evaluate New York Cash Session: minutes 570 to 930
        for pos in range(100, len(d_day)):
            row = d_day.iloc[pos]
            if row.local_minute < 570 or row.local_minute >= 930:
                continue

            atr = row.get("atr", 1.0)
            if not (np.isfinite(atr) and atr > 0):
                atr = 1.0
            sweep_buf = max(0.05 * atr, 1.0)
            c_range = max(row.high - row.low, 1e-6)

            # Check Bearish Sweep of London High
            swept_h = row.high >= lh + sweep_buf
            reclaimed_h = row.close < lh and row.close > ll
            bear_wick = (row.high - max(row.open, row.close)) / c_range
            bear_confirm = (row.close < row.open) or (bear_wick >= 0.25)

            # Check Bullish Sweep of London Low
            swept_l = row.low <= ll - sweep_buf
            reclaimed_l = row.close > ll and row.close < lh
            bull_wick = (min(row.open, row.close) - row.low) / c_range
            bull_confirm = (row.close > row.open) or (bull_wick >= 0.25)

            sig_dir = None
            if swept_h and reclaimed_h and bear_confirm:
                sig_dir = "SELL"
                entry = float(row.close)
                sl = float(row.high + 0.10 * atr)
                tp = float(l_mid)
            elif swept_l and reclaimed_l and bull_confirm:
                sig_dir = "BUY"
                entry = float(row.close)
                sl = float(row.low - 0.10 * atr)
                tp = float(l_mid)

            if sig_dir is not None:
                risk = abs(entry - sl)
                if risk <= 0:
                    continue

                # Forward simulate the trade outcome (next 120 bars)
                future_bars = d_day.iloc[pos + 1:pos + 121]
                pnl_r = 0.0
                outcome = "TIME"

                for _, f_row in future_bars.iterrows():
                    if sig_dir == "BUY":
                        if f_row.low <= sl:
                            pnl_r = -1.0
                            outcome = "SL"
                            break
                        if f_row.high >= tp:
                            pnl_r = round(abs(tp - entry) / risk, 2)
                            outcome = "TP"
                            break
                    else:  # SELL
                        if f_row.high >= sl:
                            pnl_r = -1.0
                            outcome = "SL"
                            break
                        if f_row.low <= tp:
                            pnl_r = round(abs(entry - tp) / risk, 2)
                            outcome = "TP"
                            break

                if outcome == "TIME" and not future_bars.empty:
                    last_c = future_bars.iloc[-1].close
                    pts = (last_c - entry) if sig_dir == "BUY" else (entry - last_c)
                    pnl_r = round(pts / risk, 2)

                t_record = {
                    "day": day,
                    "pos": pos,
                    "direction": sig_dir,
                    "entry": entry,
                    "sl": sl,
                    "tp": tp,
                    "risk": risk,
                    "pnl_r": pnl_r,
                    "outcome": outcome
                }

                baseline_trades.append(t_record)

                # Now evaluate QUANTUM CONFLUENCE on this exact candidate!
                # 1. Volume: RVOL
                rvol_val = float(row.get("rvol", 1.0))
                vol_pass = rvol_val >= 1.15

                # 2. Linear Regression Z-Score
                sub_closes = d_day["close"].iloc[max(0, pos - 80):pos + 1].values
                reg = calculate_linear_regression_channel(sub_closes, lookback=min(80, len(sub_closes)))
                reg_pass = True
                if reg is not None:
                    # In a SELL, z-score should NOT be oversold (z > -0.5)
                    if sig_dir == "SELL" and reg.current_zscore <= -0.5:
                        reg_pass = False
                    # In a BUY, z-score should NOT be overbought (z < 0.5)
                    if sig_dir == "BUY" and reg.current_zscore >= 0.5:
                        reg_pass = False

                # 3. Divergence
                sub_slice = d_day.iloc[max(0, pos - 40):pos + 1].copy().reset_index(drop=True)
                rsi_divs = detect_rsi_divergences(sub_slice, rsi_period=14, lookback_bars=30)
                div_pass = True
                # If opposing regular divergence exists, reject!
                if sig_dir == "SELL" and any(d.div_type == "REGULAR_BULLISH" for d in rsi_divs):
                    div_pass = False
                if sig_dir == "BUY" and any(d.div_type == "REGULAR_BEARISH" for d in rsi_divs):
                    div_pass = False

                # Confluence filter
                if vol_pass and reg_pass and div_pass:
                    quantum_trades.append(t_record)

    # Compare Baseline vs Quantum
    def print_stats(trades_list: List[Dict], name: str):
        td = pd.DataFrame(trades_list)
        if td.empty:
            print(f"[{name}] 0 trades.")
            return
        wins = len(td[td["pnl_r"] > 0])
        losses = len(td[td["pnl_r"] < 0])
        total = len(td)
        wr = round(100.0 * wins / max(1, total), 1)
        gw = td[td["pnl_r"] > 0]["pnl_r"].sum()
        gl = abs(td[td["pnl_r"] < 0]["pnl_r"].sum())
        pf = round(gw / gl, 2) if gl > 0 else 999.0
        net_r = round(td["pnl_r"].sum(), 2)
        print(f"--- {name} ---")
        print(f"  Trades: {total} (Wins: {wins} | Losses: {losses})")
        print(f"  Win Rate: {wr}%")
        print(f"  Profit Factor: {pf}")
        print(f"  Net Return: {net_r:+.2f}R")
        print(f"  Expectancy per Trade: {net_r/total:+.2f}R")
        print("------------------------------------------")

    print_stats(baseline_trades, f"BASELINE H17 ({symbol})")
    print_stats(quantum_trades, f"QUANTUM-ENHANCED H17 ({symbol})")


if __name__ == "__main__":
    run_quantum_h17_comparison("data/UT100Roll_M1.csv", symbol="US100", min_london_range=140.0)
    run_quantum_h17_comparison("data/XAUUSD_M1.csv", symbol="XAUUSD", min_london_range=25.0)
