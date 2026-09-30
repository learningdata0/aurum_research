from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from .config import Settings
from .data import prepare_data
from .htf_levels import build_htf_context_map, DailyHTFContext


@dataclass(frozen=True)
class HypothesisV08:
    id: str
    name: str
    target_rr: float               # e.g. 1.25, 1.50, 1.75, 2.0
    min_london_range: float         # 0.0 for unfiltered, 100.0 (25th pct), 140.0 (50th pct)
    is_hybrid: bool = False         # True for 50% @ 1.0R + BE + 50% @ 2.0R
    target_mode: str = "fixed_rr"   # "fixed_rr", "swing", "hybrid"
    description: str = ""


FROZEN_V08_HYPOTHESES: List[HypothesisV08] = [
    HypothesisV08(
        id="H8a_BENCHMARK",
        name="London Sweep (v0.7 Swing Benchmark)",
        target_rr=1.80,
        min_london_range=0.0,
        target_mode="swing",
        description="Unmodified baseline targeting London Midpoint."
    ),
    HypothesisV08(
        id="H12_TP125",
        name="London Sweep (Fixed TP 1.25R, Unfiltered)",
        target_rr=1.25,
        min_london_range=0.0,
        target_mode="fixed_rr",
        description="Intermediate target 1.25R without session range filter."
    ),
    HypothesisV08(
        id="H13_TP150",
        name="London Sweep (Fixed TP 1.50R, Unfiltered)",
        target_rr=1.50,
        min_london_range=0.0,
        target_mode="fixed_rr",
        description="Intermediate target 1.50R without session range filter."
    ),
    HypothesisV08(
        id="H14_TP175",
        name="London Sweep (Fixed TP 1.75R, Unfiltered)",
        target_rr=1.75,
        min_london_range=0.0,
        target_mode="fixed_rr",
        description="Intermediate target 1.75R without session range filter."
    ),
    HypothesisV08(
        id="H15a_EXP_TP125",
        name="London Sweep (Range >= 100pts + TP 1.25R)",
        target_rr=1.25,
        min_london_range=100.0,
        target_mode="fixed_rr",
        description="Filters for institutional London range (>= 100pts) with 1.25R target."
    ),
    HypothesisV08(
        id="H15b_EXP_TP150",
        name="London Sweep (Range >= 100pts + TP 1.50R)",
        target_rr=1.50,
        min_london_range=100.0,
        target_mode="fixed_rr",
        description="Filters for institutional London range (>= 100pts) with 1.50R target."
    ),
    HypothesisV08(
        id="H15c_EXP_TP175",
        name="London Sweep (Range >= 100pts + TP 1.75R)",
        target_rr=1.75,
        min_london_range=100.0,
        target_mode="fixed_rr",
        description="Filters for institutional London range (>= 100pts) with 1.75R target."
    ),
    HypothesisV08(
        id="H15d_MED_TP150",
        name="London Sweep (Range >= 140pts + TP 1.50R)",
        target_rr=1.50,
        min_london_range=140.0,
        target_mode="fixed_rr",
        description="Median expansion filter (>= 140pts) with 1.50R target."
    ),
    HypothesisV08(
        id="H16_HYBRID",
        name="London Sweep (Range >= 100pts + Hybrid 1R/2R)",
        target_rr=2.0,
        min_london_range=100.0,
        is_hybrid=True,
        target_mode="hybrid",
        description="50% exit at 1.0R with Stop moved to BE; 50% exit at 2.0R."
    ),
]


def evaluate_v08_signal(
    row: pd.Series,
    ctx: DailyHTFContext,
    hyp: HypothesisV08,
    settings: Settings
) -> Optional[Tuple[str, float, float, float, str]]:
    """
    Evaluates London sweep-reclaim with configurable TP and London range filter.
    """
    if ctx.london_high is None or ctx.london_low is None:
        return None

    lon_range = ctx.london_high - ctx.london_low
    if lon_range < hyp.min_london_range:
        return None

    atr = row["atr"]
    if not (np.isfinite(atr) and atr > 0):
        return None

    c_range = max(row["high"] - row["low"], 1e-12)
    sweep_buffer = max(0.05 * atr, 1.0)
    lh = ctx.london_high
    ll = ctx.london_low
    l_mid = (lh + ll) / 2.0

    # 1. Bearish Sweep of London High
    swept_high = row["high"] >= lh + sweep_buffer
    reclaimed_high = row["close"] < lh and row["close"] > ll
    bearish_confirm = (row["close"] < row["open"]) or (row["upper_wick"] >= 0.25 * c_range)

    if swept_high and reclaimed_high and bearish_confirm:
        entry = float(row["close"])
        sl = float(row["high"] + 0.10 * atr)
        risk = sl - entry
        if risk > 0:
            if hyp.target_mode == "swing":
                raw_tp = l_mid if l_mid < entry else entry - 1.5 * risk
                tp = float(min(raw_tp, entry - 1.25 * risk))
            elif hyp.target_mode in ("fixed_rr", "hybrid"):
                tp = float(entry - hyp.target_rr * risk)
            else:
                tp = float(entry - 1.0 * risk)

            if tp < entry:
                return ("SELL", entry, sl, tp, f"{hyp.id}_bearish_sweep")

    # 2. Bullish Sweep of London Low
    swept_low = row["low"] <= ll - sweep_buffer
    reclaimed_low = row["close"] > ll and row["close"] < lh
    bullish_confirm = (row["close"] > row["open"]) or (row["lower_wick"] >= 0.25 * c_range)

    if swept_low and reclaimed_low and bullish_confirm:
        entry = float(row["close"])
        sl = float(row["low"] - 0.10 * atr)
        risk = entry - sl
        if risk > 0:
            if hyp.target_mode == "swing":
                raw_tp = l_mid if l_mid > entry else entry + 1.5 * risk
                tp = float(max(raw_tp, entry + 1.25 * risk))
            elif hyp.target_mode in ("fixed_rr", "hybrid"):
                tp = float(entry + hyp.target_rr * risk)
            else:
                tp = float(entry + 1.0 * risk)

            if tp > entry:
                return ("BUY", entry, sl, tp, f"{hyp.id}_bullish_sweep")

    return None


def run_v08_backtest(
    d: pd.DataFrame,
    ctx_map: Dict[any, DailyHTFContext],
    hyp: HypothesisV08,
    settings: Settings,
    symbol: str = "US100"
) -> Tuple[pd.DataFrame, dict]:
    """
    Executes backtest for a v0.8 hypothesis, supporting hybrid multi-tier exits.
    """
    balance = settings.initial_balance
    trades = []
    daily_start = {}
    daily_pnl = {}
    trades_per_day = {}
    consecutive_losses = 0
    used_until = -1
    last_day = None

    for pos in range(len(d)):
        if pos <= used_until:
            continue

        row = d.iloc[pos]
        day = row.day

        if day not in ctx_map:
            continue

        local_min = row.local_minute
        if local_min < 570 or local_min >= 930:  # 09:30 to 15:30 NY
            continue

        if day != last_day:
            last_day = day
            consecutive_losses = 0

        daily_start.setdefault(day, balance)
        daily_pnl.setdefault(day, 0.0)

        # Risk guards
        if daily_pnl[day] <= -settings.max_daily_loss * daily_start[day]:
            continue
        if consecutive_losses >= settings.max_consecutive_losses:
            continue
        if trades_per_day.get(day, 0) >= settings.max_trades_per_day:
            continue

        ctx = ctx_map[day]
        sig = evaluate_v08_signal(row, ctx, hyp, settings)
        if not sig:
            continue

        direction, entry, sl, tp, setup = sig
        risk_price = abs(entry - sl)
        if risk_price <= 0:
            continue

        risk_cash = balance * settings.risk_per_trade
        units = risk_cash / risk_price

        # Simulation
        max_hold = 120 if hyp.is_hybrid else (180 if hyp.target_mode == "swing" else 90)
        max_idx = min(len(d) - 1, pos + max_hold)
        slip = settings.slippage_points

        if not hyp.is_hybrid:
            exit_price, exit_reason, exit_idx = None, None, None
            for j in range(pos + 1, max_idx + 1):
                r = d.iloc[j]
                hit_sl = r.low <= sl if direction == "BUY" else r.high >= sl
                hit_tp = r.high >= tp if direction == "BUY" else r.low <= tp

                if hit_sl:
                    exit_price, exit_reason, exit_idx = sl, "SL", j
                    break
                if hit_tp:
                    exit_price, exit_reason, exit_idx = tp, "TP", j
                    break

            if exit_price is None:
                exit_idx = max_idx
                exit_price = float(d.iloc[max_idx]["close"])
                exit_reason = "TIME"

            actual_entry = entry + slip if direction == "BUY" else entry - slip
            actual_exit = exit_price - slip if direction == "BUY" else exit_price + slip
            pts_signed = (actual_exit - actual_entry) if direction == "BUY" else (actual_entry - actual_exit)
            gross_pnl = pts_signed * units
            comm_cash = 2.0 * settings.commission_per_unit * units
            net_pnl = gross_pnl - comm_cash
            r_mult = net_pnl / risk_cash if risk_cash > 0 else 0.0

        else:
            # Hybrid Mode: 50% at 1.0R with SL moved to BE; 50% at 2.0R
            tp1 = entry + 1.0 * risk_price if direction == "BUY" else entry - 1.0 * risk_price
            tp2 = tp
            current_sl = sl
            p1_closed = False
            p1_exit_price = None
            p2_exit_price = None
            exit_idx = None
            exit_reason = None

            for j in range(pos + 1, max_idx + 1):
                r = d.iloc[j]

                # Check SL
                hit_sl = r.low <= current_sl if direction == "BUY" else r.high >= current_sl
                if hit_sl:
                    if not p1_closed:
                        p1_exit_price = current_sl
                        p2_exit_price = current_sl
                        exit_reason = "SL"
                    else:
                        p2_exit_price = current_sl
                        exit_reason = "BE_STOP"
                    exit_idx = j
                    break

                # Check TP1
                if not p1_closed:
                    hit_tp1 = r.high >= tp1 if direction == "BUY" else r.low <= tp1
                    if hit_tp1:
                        p1_closed = True
                        p1_exit_price = tp1
                        # Move stop to breakeven (covering friction)
                        current_sl = entry + slip if direction == "BUY" else entry - slip

                # Check TP2
                hit_tp2 = r.high >= tp2 if direction == "BUY" else r.low <= tp2
                if hit_tp2:
                    p2_exit_price = tp2
                    exit_reason = "TP2_RUNNER" if p1_closed else "TP2_DIRECT"
                    if not p1_closed:
                        p1_exit_price = tp2
                    exit_idx = j
                    break

            if exit_idx is None:
                exit_idx = max_idx
                c_exit = float(d.iloc[max_idx]["close"])
                exit_reason = "TIME"
                if not p1_closed:
                    p1_exit_price = c_exit
                p2_exit_price = c_exit

            # Net PnL of 50% leg 1 + 50% leg 2
            act_entry = entry + slip if direction == "BUY" else entry - slip
            act_ex1 = p1_exit_price - slip if direction == "BUY" else p1_exit_price + slip
            act_ex2 = p2_exit_price - slip if direction == "BUY" else p2_exit_price + slip

            pts1 = (act_ex1 - act_entry) if direction == "BUY" else (act_entry - act_ex1)
            pts2 = (act_ex2 - act_entry) if direction == "BUY" else (act_entry - act_ex2)

            net_pnl = (pts1 * 0.5 * units) + (pts2 * 0.5 * units)
            r_mult = net_pnl / risk_cash if risk_cash > 0 else 0.0
            actual_entry = act_entry
            actual_exit = (act_ex1 + act_ex2) / 2.0
            pts_signed = (pts1 + pts2) / 2.0
            comm_cash = 2.0 * settings.commission_per_unit * units

        balance += net_pnl
        daily_pnl[day] += net_pnl
        consecutive_losses = consecutive_losses + 1 if net_pnl < 0 else 0
        used_until = exit_idx
        trades_per_day[day] = trades_per_day.get(day, 0) + 1

        trades.append({
            "symbol": symbol,
            "hypothesis": hyp.id,
            "setup": setup,
            "direction": direction,
            "entry_time": str(row.time),
            "exit_time": str(d.iloc[exit_idx].time),
            "entry": float(actual_entry),
            "sl": float(sl),
            "tp": float(tp),
            "exit": float(actual_exit),
            "risk_price": float(risk_price),
            "pnl_points": float(pts_signed),
            "r_multiple": float(r_mult),
            "pnl_cash": float(net_pnl),
            "commission": float(comm_cash),
            "exit_reason": exit_reason,
            "day": str(day)
        })

    td = pd.DataFrame(trades)
    n = len(td)
    if n == 0:
        return td, {
            "trades": 0, "win_rate_pct": 0.0, "profit_factor": 0.0,
            "expectancy_R": 0.0, "net_pnl": 0.0, "max_drawdown_pct": 0.0,
            "final_balance": balance, "concentration_ratio": 0.0,
            "positive_months": 0, "total_months": 0, "monthly_win_rate_pct": 0.0
        }

    wins = td[td["pnl_cash"] > 0]
    losses = td[td["pnl_cash"] < 0]
    wr = round(100.0 * len(wins) / n, 2)
    gw = wins["pnl_cash"].sum()
    gl = abs(losses["pnl_cash"].sum())
    pf = round(gw / gl, 2) if gl > 0 else 999.0
    exp_r = round(float(td["r_multiple"].mean()), 2)
    net_cash = round(float(td["pnl_cash"].sum()), 2)

    equity = settings.initial_balance + td["pnl_cash"].cumsum()
    peak = equity.cummax()
    dd_pct = round(float(((peak - equity) / peak).max() * 100.0), 2)

    td["dt"] = pd.to_datetime(td["entry_time"], utc=True)
    td["ym"] = td["dt"].dt.strftime("%Y-%m")
    m_grp = td.groupby("ym")["r_multiple"].sum()
    pos_m = m_grp[m_grp > 0].sort_values(ascending=False)
    conc_ratio = round(float(pos_m.iloc[:2].sum() / pos_m.sum()), 2) if len(pos_m) >= 2 and pos_m.sum() > 0 else 1.0

    stats = {
        "trades": n,
        "win_rate_pct": wr,
        "profit_factor": pf,
        "expectancy_R": exp_r,
        "net_pnl": net_cash,
        "max_drawdown_pct": dd_pct,
        "final_balance": round(balance, 2),
        "concentration_ratio": conc_ratio,
        "positive_months": int((m_grp > 0).sum()),
        "total_months": len(m_grp),
        "monthly_win_rate_pct": round(100.0 * (m_grp > 0).sum() / max(1, len(m_grp)), 1)
    }

    return td, stats


def run_all_v08_hypotheses(csv_path: str = "data/UT100Roll_M1.csv") -> Tuple[pd.DataFrame, Dict[str, pd.DataFrame]]:
    df_raw = pd.read_csv(csv_path)
    d = prepare_data(df_raw, source_timezone="broker")
    ctx_map = build_htf_context_map(d)
    settings = Settings()

    summary_rows = []
    trades_dict = {}

    for hyp in FROZEN_V08_HYPOTHESES:
        trades_df, stats = run_v08_backtest(d, ctx_map, hyp, settings, symbol="US100")
        trades_dict[hyp.id] = trades_df

        summary_rows.append({
            "id": hyp.id,
            "name": hyp.name,
            "target": f"{hyp.target_rr}R" if hyp.target_mode != "swing" else "Swing",
            "filter": f">={hyp.min_london_range}pts" if hyp.min_london_range > 0 else "None",
            "trades": stats["trades"],
            "win_rate_pct": stats["win_rate_pct"],
            "profit_factor": stats["profit_factor"],
            "expectancy_R": stats["expectancy_R"],
            "net_pnl": stats["net_pnl"],
            "max_dd_pct": stats["max_drawdown_pct"],
            "pos_months_pct": stats.get("monthly_win_rate_pct", 0.0),
            "concentration": stats.get("concentration_ratio", 0.0)
        })

    summary_df = pd.DataFrame(summary_rows)
    return summary_df, trades_dict


if __name__ == "__main__":
    summary, _ = run_all_v08_hypotheses()
    print("\n=== AURUM v0.8 LIQUIDITY & INTERMEDIATE TARGET BENCHMARK ===")
    print(summary.to_string(index=False))
