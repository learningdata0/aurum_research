from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from .config import Settings
from .data import prepare_data
from .htf_levels import build_htf_context_map, DailyHTFContext
from .strategies.htf_sweep import evaluate_htf_sweep_reclaim


@dataclass(frozen=True)
class HypothesisV07:
    id: str
    name: str
    description: str
    target_mode: str  # "swing" or "scalp"


FROZEN_V07_HYPOTHESES: List[HypothesisV07] = [
    # Swing Mode Hypotheses (Structural TP to Midpoint / Opposite Level)
    HypothesisV07(
        id="H7_SWING",
        name="PDH/PDL Sweep-Reclaim (Swing Target)",
        description="Neutral context sweep-reclaim of Previous Day High/Low targeting Day Midpoint.",
        target_mode="swing"
    ),
    HypothesisV07(
        id="H7_SCALP",
        name="PDH/PDL Sweep-Reclaim (Scalp Target 1.0R)",
        description="High-frequency scalp taking quick 1.0R profits at PDH/PDL sweeps.",
        target_mode="scalp"
    ),
    HypothesisV07(
        id="H8a_SWING",
        name="London Session Sweep-Reclaim (Swing Target)",
        description="Sweep-reclaim of London High/Low (03:00-09:00 NY) during NY Open.",
        target_mode="swing"
    ),
    HypothesisV07(
        id="H8b_SWING",
        name="Asia Session Sweep-Reclaim (Swing Target)",
        description="Sweep-reclaim of Asia/Globex High/Low during NY Open.",
        target_mode="swing"
    ),
    HypothesisV07(
        id="H9_REGIME",
        name="PDH/PDL + HTF Regime (Trend Continuation / Range Reversal)",
        description="Fades PDH/PDL in Range; trades with-trend breakouts in Trend.",
        target_mode="swing"
    ),
    HypothesisV07(
        id="H10_QUARTILE",
        name="PDH/PDL + Open Quartile Position",
        description="Only longs lower quartile open; only shorts upper quartile open.",
        target_mode="swing"
    ),
    HypothesisV07(
        id="H11_VOLATILITY",
        name="PDH/PDL + Volatility Regime (Skip Compression)",
        description="Only trades sweep-reclaims in Normal/Expanded volatility regimes.",
        target_mode="swing"
    ),
]


def run_htf_backtest(
    d: pd.DataFrame,
    ctx_map: Dict[any, DailyHTFContext],
    hyp: HypothesisV07,
    settings: Settings,
    symbol: str = "US100",
    max_ny_minute: int = 930  # NY session trade window: 09:30 to 15:30 (minute 570 to 930)
) -> Tuple[pd.DataFrame, dict]:
    """
    Executes an event-driven backtest for Higher Timeframe (HTF) hypotheses.
    Includes friction, slippage, and intraday circuit breakers.
    """
    balance = settings.initial_balance
    trades = []
    daily_start = {}
    daily_pnl = {}
    trades_per_day = {}
    consecutive_losses = 0
    used_until = -1
    last_day = None

    hyp_base_id = hyp.id.split("_")[0]  # "H7", "H8a", "H8b", "H9", "H10", "H11"

    for pos in range(len(d)):
        if pos <= used_until:
            continue

        row = d.iloc[pos]
        day = row.day

        # Must have completed HTF context for this day
        if day not in ctx_map:
            continue

        # Trading window: NY Cash session (09:30 - 15:30 NY)
        local_min = row.local_minute
        if local_min < 570 or local_min >= max_ny_minute:
            continue

        # Reset daily circuit breaker counter on new trading day
        if day != last_day:
            last_day = day
            consecutive_losses = 0

        daily_start.setdefault(day, balance)
        daily_pnl.setdefault(day, 0.0)

        # Risk Guards
        if daily_pnl[day] <= -settings.max_daily_loss * daily_start[day]:
            continue
        if consecutive_losses >= settings.max_consecutive_losses:
            continue
        if trades_per_day.get(day, 0) >= settings.max_trades_per_day:
            continue

        ctx = ctx_map[day]
        sig = evaluate_htf_sweep_reclaim(
            row=row,
            ctx=ctx,
            settings=settings,
            hypothesis_id=hyp_base_id,
            tp_mode=hyp.target_mode
        )
        if not sig:
            continue

        direction, entry, sl, tp, setup = sig
        risk_price = abs(entry - sl)
        if risk_price <= 0:
            continue

        # Position Sizing: 1R = balance * risk_per_trade
        risk_cash = balance * settings.risk_per_trade
        units = risk_cash / risk_price

        # Next-candle fill & simulation loop
        exit_price = None
        exit_reason = None
        exit_idx = None
        # Max hold time: 60 mins for scalp, 180 mins for swing
        max_hold = 60 if hyp.target_mode == "scalp" else 180
        max_idx = min(len(d) - 1, pos + max_hold)

        for j in range(pos + 1, max_idx + 1):
            r = d.iloc[j]
            hit_sl = r.low <= sl if direction == "BUY" else r.high >= sl
            hit_tp = r.high >= tp if direction == "BUY" else r.low <= tp

            # Conservative collision rule: if both touched in same bar, SL wins
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

        # Apply slippage friction
        slip = settings.slippage_points
        actual_entry = entry + slip if direction == "BUY" else entry - slip
        actual_exit = exit_price - slip if direction == "BUY" else exit_price + slip
        points_signed = (actual_exit - actual_entry) if direction == "BUY" else (actual_entry - actual_exit)

        gross_pnl = points_signed * units
        comm_cash = 2.0 * settings.commission_per_unit * units
        net_pnl = gross_pnl - comm_cash
        r_mult = net_pnl / risk_cash if risk_cash > 0 else 0.0

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
            "pnl_points": float(points_signed),
            "r_multiple": float(r_mult),
            "pnl_cash": float(net_pnl),
            "commission": float(comm_cash),
            "slippage": float(slip * 2.0),
            "exit_reason": exit_reason,
            "day": str(day),
            "htf_trend": ctx.htf_trend,
            "open_quartile": ctx.open_quartile,
            "volatility_regime": ctx.volatility_regime,
            "pdh": ctx.pdh,
            "pdl": ctx.pdl
        })

    td = pd.DataFrame(trades)
    n = len(td)
    if n == 0:
        return td, {
            "trades": 0, "win_rate_pct": 0.0, "profit_factor": 0.0,
            "expectancy_R": 0.0, "net_pnl": 0.0, "max_drawdown_pct": 0.0,
            "final_balance": balance, "concentration_ratio": 0.0
        }

    wins = td[td["pnl_cash"] > 0]
    losses = td[td["pnl_cash"] < 0]
    wr = round(100.0 * len(wins) / n, 2)
    gw = wins["pnl_cash"].sum()
    gl = abs(losses["pnl_cash"].sum())
    pf = round(gw / gl, 2) if gl > 0 else 999.0
    exp_r = round(float(td["r_multiple"].mean()), 2)
    net_cash = round(float(td["pnl_cash"].sum()), 2)

    # Max Drawdown %
    equity = settings.initial_balance + td["pnl_cash"].cumsum()
    peak = equity.cummax()
    dd_pct = round(float(((peak - equity) / peak).max() * 100.0), 2)

    # Monthly breakdown & Concentration Ratio
    td["dt"] = pd.to_datetime(td["entry_time"], utc=True)
    td["ym"] = td["dt"].dt.strftime("%Y-%m")
    m_grp = td.groupby("ym")["r_multiple"].sum()
    pos_m = m_grp[m_grp > 0].sort_values(ascending=False)
    if len(pos_m) >= 2 and pos_m.sum() > 0:
        conc_ratio = round(float(pos_m.iloc[:2].sum() / pos_m.sum()), 2)
    else:
        conc_ratio = 1.0

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


def run_all_v07_hypotheses(csv_path: str = "data/UT100Roll_M1.csv") -> Tuple[pd.DataFrame, Dict[str, pd.DataFrame]]:
    """
    Runs all 7 v0.7 hypotheses across the multi-year dataset.
    """
    df_raw = pd.read_csv(csv_path)
    d = prepare_data(df_raw, source_timezone="broker")
    ctx_map = build_htf_context_map(d)
    settings = Settings()

    summary_rows = []
    trades_dict = {}

    for hyp in FROZEN_V07_HYPOTHESES:
        trades_df, stats = run_htf_backtest(d, ctx_map, hyp, settings, symbol="US100")
        trades_dict[hyp.id] = trades_df

        summary_rows.append({
            "id": hyp.id,
            "name": hyp.name,
            "mode": hyp.target_mode,
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
    summary, _ = run_all_v07_hypotheses()
    print("\n=== AURUM v0.7 HTF LIQUIDITY RESEARCH BENCHMARK ===")
    print(summary.to_string(index=False))
