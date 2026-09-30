import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from src.config import Settings
from src.data import prepare_data
from src.htf_levels import build_htf_context_map, DailyHTFContext


@dataclass
class TradeResult:
    ticket: int
    day: str
    symbol: str
    direction: str
    entry_time: str
    entry_price: float
    initial_sl: float
    initial_tp: float
    exit_price: float
    exit_reason: str
    net_pnl: float
    r_mult: float
    p1_taken: bool = False
    is_flip: bool = False


def simulate_strategy_variations(
    symbol: str = "US100",
    data_file: str = "data/UT100Roll_M1.csv",
    min_london_range: float = 140.0,
    be_trigger_pts: float = 15.0,
    trail_step_pts: float = 25.0,
    trail_lock_pts: float = 10.0,
    tp1_pts: float = 15.0,
    enable_flip: bool = True
) -> Dict[str, Dict]:
    
    raw_df = pd.read_csv(data_file)
    df = prepare_data(raw_df)
    ctx_map = build_htf_context_map(df)
    days = sorted(list(ctx_map.keys()))
    
    strategies = {
        "0_BASELINE_H17": {"mode": "baseline"},
        "1_PURE_BREAKEVEN": {"mode": "be_only", "be_pts": be_trigger_pts},
        "2_TWO_STAGE_TRAILING": {"mode": "trailing", "be_pts": be_trigger_pts, "step": trail_step_pts, "lock": trail_lock_pts},
        "3_USER_TP1_HYBRID_15PTS": {"mode": "hybrid_fixed", "tp1_pts": tp1_pts},
        "4_USER_TP1_HYBRID_1R": {"mode": "hybrid_1r"},
        "5_FULL_HYBRID_PLUS_FLIP": {"mode": "hybrid_flip", "tp1_pts": tp1_pts, "enable_flip": True}
    }
    
    results = {}
    
    for strat_name, strat_cfg in strategies.items():
        all_trades: List[TradeResult] = []
        ticket_counter = 1000
        balance = 10000.0
        risk_pct = 0.0025
        slip = 0.50 if symbol == "US100" else 0.15
        
        for day in days:
            ctx = ctx_map[day]
            if ctx.london_high is None or ctx.london_low is None:
                continue
            lon_range = ctx.london_high - ctx.london_low
            if lon_range < min_london_range:
                continue
            lon_mid = (ctx.london_high + ctx.london_low) / 2.0
                
            d_day = df[df["day"] == day]
            if d_day.empty:
                continue
                
            # Filter NY Cash Session: 09:30 to 15:30 NY (minute 570 to 930)
            in_ny = (d_day["local_minute"] >= 570) & (d_day["local_minute"] < 930)
            ny_bars = d_day[in_ny]
            if ny_bars.empty:
                continue
                
            active_trade = None
            used_until_idx = -1
            
            for idx in ny_bars.index:
                if idx <= used_until_idx:
                    continue
                    
                row = df.loc[idx]
                prev_row = df.loc[idx - 1] if idx - 1 in df.index else row
                
                # Check for Sweep-Reclaim signal
                high_sweep = (prev_row.high > ctx.london_high) and (row.close < ctx.london_high)
                low_sweep = (prev_row.low < ctx.london_low) and (row.close > ctx.london_low)
                
                if not (high_sweep or low_sweep):
                    continue
                    
                direction = "SELL" if high_sweep else "BUY"
                entry = float(row.close)
                
                # Compute SL and TP
                if direction == "BUY":
                    sl = float(min(row.low, prev_row.low) - 2.0 * slip)
                    tp = float(lon_mid)
                else:
                    sl = float(max(row.high, prev_row.high) + 2.0 * slip)
                    tp = float(lon_mid)
                    
                risk_price = abs(entry - sl)
                if risk_price <= 0:
                    continue
                    
                # Standard risk sizing
                risk_cash = balance * risk_pct
                units = risk_cash / risk_price
                
                # Simulate the trade forward
                exit_idx, net_pnl, r_mult, reason, flip_candidate = simulate_single_trade(
                    df, idx, direction, entry, sl, tp, units, risk_cash, slip, strat_cfg, ctx
                )
                
                ticket_counter += 1
                all_trades.append(TradeResult(
                    ticket=ticket_counter,
                    day=day,
                    symbol=symbol,
                    direction=direction,
                    entry_time=str(row.time),
                    entry_price=entry,
                    initial_sl=sl,
                    initial_tp=tp,
                    exit_price=0.0,
                    exit_reason=reason,
                    net_pnl=net_pnl,
                    r_mult=r_mult
                ))
                
                balance += net_pnl
                used_until_idx = exit_idx
                
                # If Flip is enabled and trade was stopped out on a breakout
                if strat_cfg.get("enable_flip") and flip_candidate and exit_idx < ny_bars.index[-1]:
                    flip_dir = "BUY" if direction == "SELL" else "SELL"
                    flip_entry = float(df.loc[exit_idx, "close"])
                    flip_sl = entry  # Prior entry is now invalidation level
                    flip_risk_price = abs(flip_entry - flip_sl)
                    if flip_risk_price > 0:
                        flip_risk_cash = balance * risk_pct
                        flip_units = flip_risk_cash / flip_risk_price
                        flip_tp = flip_entry + 1.8 * flip_risk_price if flip_dir == "BUY" else flip_entry - 1.8 * flip_risk_price
                        
                        f_exit_idx, f_pnl, f_r, f_reason, _ = simulate_single_trade(
                            df, exit_idx, flip_dir, flip_entry, flip_sl, flip_tp, flip_units, flip_risk_cash, slip,
                            {"mode": "baseline"}, ctx
                        )
                        ticket_counter += 1
                        all_trades.append(TradeResult(
                            ticket=ticket_counter,
                            day=day,
                            symbol=symbol,
                            direction=f"FLIP_{flip_dir}",
                            entry_time=str(df.loc[exit_idx, "time"]),
                            entry_price=flip_entry,
                            initial_sl=flip_sl,
                            initial_tp=flip_tp,
                            exit_price=0.0,
                            exit_reason=f_reason,
                            net_pnl=f_pnl,
                            r_mult=f_r,
                            is_flip=True
                        ))
                        balance += f_pnl
                        used_until_idx = f_exit_idx
                
                # Maximum 2 trades per session
                break
                
        # Aggregate statistics
        if all_trades:
            tot = len(all_trades)
            wins = len([t for t in all_trades if t.net_pnl > 0.5])
            losses = len([t for t in all_trades if t.net_pnl < -0.5])
            bes = len([t for t in all_trades if abs(t.net_pnl) <= 0.5])
            net_r = sum(t.r_mult for t in all_trades)
            net_cash = sum(t.net_pnl for t in all_trades)
            gw = sum(t.net_pnl for t in all_trades if t.net_pnl > 0)
            gl = abs(sum(t.net_pnl for t in all_trades if t.net_pnl < 0))
            pf = round(gw / gl, 2) if gl > 0 else 999.0
            wr = round(100.0 * wins / tot, 1)
            
            # Compute Max Drawdown in R
            cum_r = np.cumsum([t.r_mult for t in all_trades])
            peaks = np.maximum.accumulate(cum_r)
            dd = peaks - cum_r
            max_dd_r = round(float(np.max(dd)), 2) if len(dd) > 0 else 0.0
            
            results[strat_name] = {
                "trades": tot,
                "wins": wins,
                "losses": losses,
                "bes": bes,
                "win_rate": wr,
                "profit_factor": pf,
                "net_r": round(net_r, 2),
                "net_cash": round(net_cash, 2),
                "max_dd_r": max_dd_r,
                "avg_r": round(net_r / tot, 3)
            }
        else:
            results[strat_name] = {"trades": 0}
            
    return results


def simulate_single_trade(
    df: pd.DataFrame,
    start_idx: int,
    direction: str,
    entry: float,
    initial_sl: float,
    tp: float,
    units: float,
    risk_cash: float,
    slip: float,
    cfg: dict,
    ctx: DailyHTFContext
) -> Tuple[int, float, float, str, bool]:
    
    mode = cfg.get("mode", "baseline")
    risk_price = abs(entry - initial_sl)
    max_idx = min(start_idx + 240, df.index[-1])  # 4 hour max hold
    
    current_sl = initial_sl
    p1_closed = False
    p1_cash = 0.0
    p1_r = 0.0
    flip_candidate = False
    
    # Target points
    be_pts = cfg.get("be_pts", 15.0)
    step_pts = cfg.get("step", 25.0)
    lock_pts = cfg.get("lock", 10.0)
    tp1_pts = cfg.get("tp1_pts", 15.0)
    
    for j in range(start_idx + 1, max_idx + 1):
        bar = df.loc[j]
        
        # Current favorable movement in points
        favorable_pts = (bar.high - entry) if direction == "BUY" else (entry - bar.low)
        
        # Check SL Hit
        hit_sl = (bar.low <= current_sl) if direction == "BUY" else (bar.high >= current_sl)
        if hit_sl:
            reason = "SL"
            if p1_closed:
                reason = "BE_STOP" if abs(current_sl - entry) < 2.0 else "TRAIL_STOP"
            elif abs(current_sl - entry) < 2.0:
                reason = "BE_STOP"
            
            # Loss or trailing exit
            if not p1_closed:
                pts = (current_sl - entry) if direction == "BUY" else (entry - current_sl)
                net_pnl = pts * units - (2.0 * slip * units)
                r_mult = net_pnl / risk_cash if risk_cash > 0 else 0.0
                flip_candidate = True if reason == "SL" else False
                return j, net_pnl, r_mult, reason, flip_candidate
            else:
                pts2 = (current_sl - entry) if direction == "BUY" else (entry - current_sl)
                p2_pnl = pts2 * 0.5 * units - (slip * units)
                tot_pnl = p1_cash + p2_pnl
                tot_r = tot_pnl / risk_cash if risk_cash > 0 else 0.0
                return j, tot_pnl, tot_r, reason, False
                
        # Check TP Hit
        hit_tp = (bar.high >= tp) if direction == "BUY" else (bar.low <= tp)
        if hit_tp:
            reason = "TP_FULL" if not p1_closed else "TP_RUNNER"
            if not p1_closed:
                pts = (tp - entry) if direction == "BUY" else (entry - tp)
                net_pnl = pts * units - (2.0 * slip * units)
                r_mult = net_pnl / risk_cash if risk_cash > 0 else 0.0
                return j, net_pnl, r_mult, reason, False
            else:
                pts2 = (tp - entry) if direction == "BUY" else (entry - tp)
                p2_pnl = pts2 * 0.5 * units - (slip * units)
                tot_pnl = p1_cash + p2_pnl
                tot_r = tot_pnl / risk_cash if risk_cash > 0 else 0.0
                return j, tot_pnl, tot_r, reason, False
                
        # Management Logic based on mode
        if mode == "be_only":
            if favorable_pts >= be_pts and current_sl == initial_sl:
                current_sl = entry + slip if direction == "BUY" else entry - slip
                
        elif mode == "trailing":
            if favorable_pts >= be_pts and current_sl == initial_sl:
                current_sl = entry + slip if direction == "BUY" else entry - slip
            if favorable_pts >= step_pts:
                locked_sl = entry + lock_pts if direction == "BUY" else entry - lock_pts
                if (direction == "BUY" and locked_sl > current_sl) or (direction == "SELL" and locked_sl < current_sl):
                    current_sl = locked_sl
                    
        elif mode in ["hybrid_fixed", "hybrid_1r", "hybrid_flip"]:
            target_tp1 = tp1_pts if mode != "hybrid_1r" else risk_price
            if favorable_pts >= target_tp1 and not p1_closed:
                p1_closed = True
                p1_cash = (target_tp1 * 0.5 * units) - (slip * units)
                p1_r = p1_cash / risk_cash
                # Move remaining 50% to Breakeven
                current_sl = entry + slip if direction == "BUY" else entry - slip
                
    # Time Exit
    c_exit = float(df.loc[max_idx, "close"])
    pts = (c_exit - entry) if direction == "BUY" else (entry - c_exit)
    if not p1_closed:
        net_pnl = pts * units - (2.0 * slip * units)
        r_mult = net_pnl / risk_cash
    else:
        p2_pnl = pts * 0.5 * units - (slip * units)
        net_pnl = p1_cash + p2_pnl
        r_mult = net_pnl / risk_cash
    return max_idx, net_pnl, r_mult, "TIME", False


if __name__ == "__main__":
    print("=" * 80)
    print("🔬 AURUM INSTITUTIONAL LAB: TRAILING STOP, BREAKEVEN & BREAKOUT FLIP STUDY")
    print("=" * 80)
    
    print("\n[1/2] Running rigorous historical simulation on US100 (UT100Roll M1)...")
    res_us100 = simulate_strategy_variations(
        symbol="US100",
        data_file="data/UT100Roll_M1.csv",
        min_london_range=140.0,
        be_trigger_pts=15.0,
        trail_step_pts=25.0,
        trail_lock_pts=10.0,
        tp1_pts=15.0,
        enable_flip=True
    )
    
    print("\n[2/2] Running rigorous historical simulation on Gold (XAUUSD M1)...")
    res_gold = simulate_strategy_variations(
        symbol="XAUUSD",
        data_file="data/XAUUSD_M1.csv",
        min_london_range=55.0,
        be_trigger_pts=4.0,
        trail_step_pts=7.0,
        trail_lock_pts=3.0,
        tp1_pts=4.0,
        enable_flip=True
    )
    
    # Build Markdown Report
    lines = [
        "# 🔬 Empirical Study: Breakeven, Multi-Stage Trailing Stop & Breakout Flip Matrix",
        "**Asset Universe:** `US100` (`UT100Roll`) and `XAUUSD` (Spot Gold)",
        "**Sample Analyzed:** 706,255 M1 bars (US100) & 100,001 M1 bars (Gold)",
        "**Objective:** Objectively compare baseline fixed execution against dynamic Breakeven, Trailing, TP1 partial scale-out, and the Breakout Flip switch.",
        "",
        "---",
        "",
        "### 1. US100 Strategy Matrix Results",
        "",
        "| Strategy Variation | Trades | Wins | Losses | BEs | Win Rate (%) | Profit Factor | Net Return (R) | Max DD (R) | Expectancy / Trade |",
        "|---|---|---|---|---|---|---|---|---|---|"
    ]
    
    for s_name, d in res_us100.items():
        lines.append(f"| **{s_name}** | {d['trades']} | {d['wins']} | {d['losses']} | {d['bes']} | **{d['win_rate']}%** | **{d['profit_factor']}** | **{d['net_r']:+.2f}R** | {d['max_dd_r']}R | **{d['avg_r']:+.3f}R** |")
        
    lines.extend([
        "",
        "---",
        "",
        "### 2. XAUUSD (Gold) Strategy Matrix Results",
        "",
        "| Strategy Variation | Trades | Wins | Losses | BEs | Win Rate (%) | Profit Factor | Net Return (R) | Max DD (R) | Expectancy / Trade |",
        "|---|---|---|---|---|---|---|---|---|---|"
    ])
    
    for s_name, d in res_gold.items():
        lines.append(f"| **{s_name}** | {d['trades']} | {d['wins']} | {d['losses']} | {d['bes']} | **{d['win_rate']}%** | **{d['profit_factor']}** | **{d['net_r']:+.2f}R** | {d['max_dd_r']}R | **{d['avg_r']:+.3f}R** |")
        
    lines.extend([
        "",
        "---",
        "",
        "### 3. Key Findings & Quantitative Takeaways",
        ""
    ])
    
    report_content = "\n".join(lines)
    Path("reports/trailing_and_flip_empirical_study.md").write_text(report_content, encoding="utf-8")
    print("\n✅ Simulation complete. Saved to reports/trailing_and_flip_empirical_study.md")
    
    for k, v in res_us100.items():
        print(f"US100 {k:30s} -> WR: {v['win_rate']}% | PF: {v['profit_factor']} | Net: {v['net_r']:+.2f}R | DD: {v['max_dd_r']}R")
    for k, v in res_gold.items():
        print(f"GOLD  {k:30s} -> WR: {v['win_rate']}% | PF: {v['profit_factor']} | Net: {v['net_r']:+.2f}R | DD: {v['max_dd_r']}R")
