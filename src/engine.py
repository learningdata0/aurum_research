from __future__ import annotations

from dataclasses import dataclass, asdict
import math
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from .config import Settings, load_settings
from .data import prepare_data
from .regime import MarketRegime, MarketRegimeDetector, RegimeState
from .strategies.boundary_reversion import evaluate_boundary_reversion
from .strategies.sweep_reclaim import evaluate_sweep_reclaim
from .strategies.micro_range import evaluate_micro_range
from .strategies.breakout import evaluate_breakout
from .strategies.breakout_retest import evaluate_breakout_retest


def hhmm(s: str) -> int:
    h, m = map(int, s.split(":"))
    return h * 60 + m


@dataclass
class Trade:
    symbol: str
    strategy: str
    setup: str
    direction: str
    entry_time: str
    exit_time: str
    entry: float
    sl: float
    tp: float
    exit: float
    risk_price: float
    pnl_points: float
    r_multiple: float
    pnl_cash: float
    commission: float
    slippage: float
    exit_reason: str
    regime: str
    health_score: float
    range_high: float
    range_low: float
    range_width: float


class SessionEngine:
    def __init__(self, settings: Settings, strategy: str):
        self.s = settings
        self.strategy = strategy
        self.regime_detector = MarketRegimeDetector(
            min_healthy_score=settings.min_range_health_score,
            min_unstable_score=40.0
        )

    def build_sessions(self, d: pd.DataFrame) -> pd.DataFrame:
        sm = hhmm(self.s.session_start_local)
        em = hhmm(self.s.session_end_local)
        out = []

        for day, g in d.groupby("day", sort=True):
            rg = g[(g["local_minute"] >= sm) & (g["local_minute"] < sm + self.s.range_minutes)]
            # Ensure at least 60% of expected bars in opening range exist (deterministic threshold)
            min_bars = max(2, int(self.s.range_minutes * 0.60))
            if len(rg) < min_bars:
                continue

            rh = float(rg["high"].max())
            rl = float(rg["low"].min())
            w = rh - rl
            if w <= 0:
                continue

            after = g[(g["local_minute"] >= sm + self.s.range_minutes) & (g["local_minute"] < em)]
            for idx in after.index:
                out.append((idx, day, rh, rl, w))

        if not out:
            return pd.DataFrame(columns=["day", "range_high", "range_low", "range_width"])
        return pd.DataFrame(out, columns=["idx", "day", "range_high", "range_low", "range_width"]).set_index("idx")

    def evaluate_signal(
        self,
        d: pd.DataFrame,
        pos: int,
        rh: float,
        rl: float
    ) -> Optional[Tuple[str, float, float, float, str, RegimeState]]:
        row = d.iloc[pos]
        recent_window = d.iloc[max(0, pos - 20):pos + 1]
        regime_state = self.regime_detector.evaluate(row, rh, rl, recent_window)

        sig = None

        if self.strategy == "boundary_reversion":
            sig = evaluate_boundary_reversion(row, rh, rl, self.s, regime_state)
        elif self.strategy == "sweep_reclaim":
            sig = evaluate_sweep_reclaim(row, rh, rl, self.s, regime_state, recent_window)
        elif self.strategy == "micro_range":
            sig = evaluate_micro_range(row, recent_window, self.s, regime_state)
        elif self.strategy == "breakout":
            sig = evaluate_breakout(row, rh, rl, self.s, regime_state)
        elif self.strategy == "breakout_retest":
            sig = evaluate_breakout_retest(row, rh, rl, recent_window, self.s, regime_state)
        elif self.strategy in ("composite_regime", "hybrid"):
            # Regime Engine 2.0 State Machine Gating:
            # 1. HEALTHY_RANGE: Permits Sweep-Reclaim and Boundary Reversion
            if regime_state.regime == MarketRegime.HEALTHY_RANGE:
                sig = evaluate_sweep_reclaim(row, rh, rl, self.s, regime_state, recent_window)
                if not sig:
                    sig = evaluate_boundary_reversion(row, rh, rl, self.s, regime_state)
            # 2. WEAK_RANGE: Permits only high-conviction Sweep-Reclaim (mean reversion restricted)
            elif regime_state.regime == MarketRegime.WEAK_RANGE:
                sig = evaluate_sweep_reclaim(row, rh, rl, self.s, regime_state, recent_window)
            # 3. BROKEN_RANGE: Mean reversion strictly forbidden; only patient breakout-retest
            elif regime_state.regime == MarketRegime.BROKEN_RANGE:
                sig = evaluate_breakout_retest(row, rh, rl, recent_window, self.s, regime_state)
            # 4. TREND (TREND_UP / TREND_DOWN): Only breakout and breakout-retest in trend direction
            elif regime_state.is_trend():
                sig = evaluate_breakout_retest(row, rh, rl, recent_window, self.s, regime_state)
                if not sig:
                    sig = evaluate_breakout(row, rh, rl, self.s, regime_state)

        if sig:
            direction, entry, sl, tp, setup = sig
            return (direction, entry, sl, tp, setup, regime_state)
        return None


def run_backtest(
    df: pd.DataFrame,
    symbol: str,
    settings: Settings,
    strategy: str
) -> Tuple[pd.DataFrame, dict]:
    # 1. Clean, localize to America/New_York and engineer features
    d = prepare_data(df, settings.atr_period, settings.timezone, source_timezone=getattr(settings, "source_timezone", "Europe/Athens"))
    engine = SessionEngine(settings, strategy)
    meta = engine.build_sessions(d)

    balance = settings.initial_balance
    trades = []
    consecutive_losses = 0
    daily_start = {}
    daily_pnl = {}
    trades_per_day = {}
    used_until = -1
    last_day = None

    for pos in range(len(d)):
        if pos <= used_until or pos not in meta.index:
            continue

        row = d.iloc[pos]
        day = row.day

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

        m = meta.loc[pos]
        sig = engine.evaluate_signal(d, pos, float(m["range_high"]), float(m["range_low"]))
        if not sig:
            continue

        direction, entry, sl, tp, setup, regime_state = sig
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
        max_idx = min(len(d) - 1, pos + settings.max_hold_minutes)

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

        trades.append(asdict(Trade(
            symbol=symbol,
            strategy=strategy,
            setup=setup,
            direction=direction,
            entry_time=str(row.time),
            exit_time=str(d.iloc[exit_idx].time),
            entry=float(actual_entry),
            sl=float(sl),
            tp=float(tp),
            exit=float(actual_exit),
            risk_price=float(risk_price),
            pnl_points=float(points_signed),
            r_multiple=float(r_mult),
            pnl_cash=float(net_pnl),
            commission=float(comm_cash),
            slippage=float(slip * 2.0),
            exit_reason=exit_reason,
            regime=regime_state.regime.value,
            health_score=float(regime_state.score),
            range_high=float(m["range_high"]),
            range_low=float(m["range_low"]),
            range_width=float(m["range_width"]),
        )))

    td = pd.DataFrame(trades)
    return td, summarize(td, settings.initial_balance)


def summarize(td: pd.DataFrame, initial: float) -> dict:
    if td.empty:
        return {
            "trades": 0, "wins": 0, "losses": 0, "win_rate_pct": 0.0,
            "profit_factor": 0.0, "net_pnl": 0.0, "expectancy_R": 0.0,
            "avg_win_R": 0.0, "avg_loss_R": 0.0, "max_drawdown_pct": 0.0,
            "final_balance": float(initial)
        }
    wins = td[td["pnl_cash"] > 0]
    losses = td[td["pnl_cash"] < 0]
    gross_win = float(wins["pnl_cash"].sum()) if not wins.empty else 0.0
    gross_loss = float(-losses["pnl_cash"].sum()) if not losses.empty else 0.0
    eq = initial + td["pnl_cash"].cumsum()
    dd = (eq / eq.cummax() - 1.0).min()

    return {
        "trades": int(len(td)),
        "wins": int(len(wins)),
        "losses": int(len(losses)),
        "win_rate_pct": float(round(100.0 * len(wins) / len(td), 2)),
        "profit_factor": float(round(gross_win / gross_loss, 2)) if gross_loss > 0 else (math.inf if gross_win > 0 else 0.0),
        "net_pnl": float(round(td["pnl_cash"].sum(), 2)),
        "expectancy_R": float(round(td["r_multiple"].mean(), 2)),
        "avg_win_R": float(round(wins["r_multiple"].mean(), 2)) if not wins.empty else 0.0,
        "avg_loss_R": float(round(losses["r_multiple"].mean(), 2)) if not losses.empty else 0.0,
        "max_drawdown_pct": float(round(-dd * 100.0, 2)),
        "final_balance": float(round(eq.iloc[-1], 2))
    }
