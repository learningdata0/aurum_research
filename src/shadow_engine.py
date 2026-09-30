from __future__ import annotations

from dataclasses import dataclass, asdict
import json
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd

from .config import Settings
from .determinism import create_execution_signature
from .engine import SessionEngine, Trade
from .regime import MarketRegime, RegimeState


@dataclass
class ShadowOrder:
    ticket_id: int
    symbol: str
    strategy: str
    setup: str
    direction: str
    entry_time: str
    entry_price: float
    sl: float
    tp: float
    units: float
    risk_cash: float
    r_point_value: float
    regime_state: str
    health_score: float
    status: str  # OPEN, CLOSED_TP, CLOSED_SL, CLOSED_TIME
    exit_time: Optional[str] = None
    exit_price: Optional[float] = None
    pnl_cash: Optional[float] = None
    r_multiple: Optional[float] = None
    commission_cash: float = 0.0
    slippage_points: float = 0.0
    execution_sig: str = ""


class ShadowExecutionEngine:
    """
    AURUM v0.6 Shadow Execution Engine:
    Performs forward paper execution against live or streamed broker M1 data.
    Enforces identical risk management (0.25% 1R, 1.5% daily loss lock) without financial risk.
    """

    def __init__(
        self,
        symbol: str,
        settings: Settings,
        strategy: str,
        log_dir: str = "reports"
    ):
        self.symbol = symbol
        self.settings = settings
        self.strategy = strategy
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.engine = SessionEngine(settings, strategy)
        self.balance = settings.initial_balance
        self.ticket_counter = 1000

        self.open_orders: List[ShadowOrder] = []
        self.closed_orders: List[ShadowOrder] = []

        self.daily_start_balance: Dict[str, float] = {}
        self.daily_pnl: Dict[str, float] = {}
        self.daily_trade_count: Dict[str, int] = {}
        self.consecutive_losses = 0

    def process_candle(
        self,
        row: pd.Series,
        pos: int,
        meta_row: Optional[pd.Series],
        recent_window: pd.DataFrame
    ) -> Optional[ShadowOrder]:
        """Processes a single incoming M1 bar."""
        day = str(row.day)
        self.daily_start_balance.setdefault(day, self.balance)
        self.daily_pnl.setdefault(day, 0.0)
        self.daily_trade_count.setdefault(day, 0)

        # 1. Update Open Shadow Positions
        self._update_open_positions(row, pos)

        # 2. Check Daily Risk Guards
        if self.daily_pnl[day] <= -self.settings.max_daily_loss * self.daily_start_balance[day]:
            return None  # Daily loss locked!
        if self.consecutive_losses >= self.settings.max_consecutive_losses:
            return None  # Circuit breaker active!
        if self.daily_trade_count[day] >= self.settings.max_trades_per_day:
            return None  # Max trades reached!
        if len(self.open_orders) > 0:
            return None  # Only 1 concurrent trade per asset

        if meta_row is None:
            return None

        rh = float(meta_row["range_high"])
        rl = float(meta_row["range_low"])

        # 3. Evaluate Signal
        regime_state = self.engine.regime_detector.evaluate(row, rh, rl, recent_window)
        sig = None

        if self.strategy in ("H17", "H17_EXP_SWING", "london_sweep"):
            from .hypotheses_v08 import HypothesisV08, evaluate_v08_signal
            hyp17 = HypothesisV08(
                id="H17",
                name="London Range >= 140pts + Swing Target",
                target_rr=1.8,
                min_london_range=140.0,
                target_mode="swing"
            )
            ctx = getattr(self, "current_ctx", None)
            if ctx is not None:
                sig = evaluate_v08_signal(row, ctx, hyp17, self.settings)
        elif self.strategy == "sweep_reclaim":
            from .strategies.sweep_reclaim import evaluate_sweep_reclaim
            sig = evaluate_sweep_reclaim(row, rh, rl, self.settings, regime_state, recent_window)
        elif self.strategy in ("composite_regime", "hybrid"):
            # Regime Engine 2.0 routing
            from .strategies.sweep_reclaim import evaluate_sweep_reclaim
            from .strategies.breakout_retest import evaluate_breakout_retest
            from .strategies.breakout import evaluate_breakout
            from .strategies.boundary_reversion import evaluate_boundary_reversion

            if regime_state.regime in (MarketRegime.HEALTHY_RANGE, MarketRegime.WEAK_RANGE):
                sig = evaluate_sweep_reclaim(row, rh, rl, self.settings, regime_state, recent_window)
                if not sig and regime_state.regime == MarketRegime.HEALTHY_RANGE:
                    sig = evaluate_boundary_reversion(row, rh, rl, self.settings, regime_state)
            elif regime_state.is_trend() or regime_state.regime == MarketRegime.BROKEN_RANGE:
                sig = evaluate_breakout_retest(row, rh, rl, recent_window, self.settings, regime_state)

        if not sig:
            return None

        direction, entry, sl, tp, setup = sig
        risk_points = abs(entry - sl)
        if risk_points <= 0:
            return None

        # Position Sizing
        risk_cash = self.balance * self.settings.risk_per_trade
        units = risk_cash / risk_points

        # Apply slippage friction at entry fill
        actual_entry = entry + self.settings.slippage_points if direction == "BUY" else entry - self.settings.slippage_points

        order = ShadowOrder(
            ticket_id=self.ticket_counter,
            symbol=self.symbol,
            strategy=self.strategy,
            setup=setup,
            direction=direction,
            entry_time=str(row.time),
            entry_price=float(actual_entry),
            sl=float(sl),
            tp=float(tp),
            units=float(units),
            risk_cash=float(risk_cash),
            r_point_value=float(risk_points),
            regime_state=regime_state.regime.value,
            health_score=float(regime_state.score),
            status="OPEN",
            slippage_points=self.settings.slippage_points,
            commission_cash=float(2.0 * self.settings.commission_per_unit * units),
            execution_sig=f"{self.symbol}:{self.strategy}:{row.time}"
        )

        self.ticket_counter += 1
        self.open_orders.append(order)
        self.daily_trade_count[day] += 1
        return order

    def _update_open_positions(self, row: pd.Series, pos: int):
        still_open = []
        for o in self.open_orders:
            hit_sl = row.low <= o.sl if o.direction == "BUY" else row.high >= o.sl
            hit_tp = row.high >= o.tp if o.direction == "BUY" else row.low <= o.tp

            exit_price = None
            status = None

            # Conservative collision: SL wins if both touched in same bar
            if hit_sl:
                exit_price = o.sl
                status = "CLOSED_SL"
            elif hit_tp:
                exit_price = o.tp
                status = "CLOSED_TP"

            if exit_price is not None:
                # Apply slippage on exit
                actual_exit = exit_price - o.slippage_points if o.direction == "BUY" else exit_price + o.slippage_points
                points_signed = (actual_exit - o.entry_price) if o.direction == "BUY" else (o.entry_price - actual_exit)
                gross_pnl = points_signed * o.units
                net_pnl = gross_pnl - o.commission_cash
                r_mult = net_pnl / o.risk_cash if o.risk_cash > 0 else 0.0

                o.exit_time = str(row.time)
                o.exit_price = float(actual_exit)
                o.pnl_cash = float(round(net_pnl, 2))
                o.r_multiple = float(round(r_mult, 2))
                o.status = status

                self.balance += net_pnl
                day = str(row.day)
                self.daily_pnl[day] += net_pnl
                self.consecutive_losses = self.consecutive_losses + 1 if net_pnl < 0 else 0

                self.closed_orders.append(o)
                self._log_trade(o)
            else:
                still_open.append(o)

        self.open_orders = still_open

    def _log_trade(self, o: ShadowOrder):
        csv_file = self.log_dir / f"shadow_trades_{self.symbol}.csv"
        df_row = pd.DataFrame([asdict(o)])
        if not csv_file.exists():
            df_row.to_csv(csv_file, index=False)
        else:
            df_row.to_csv(csv_file, mode="a", header=False, index=False)

    def get_summary(self) -> dict:
        td = pd.DataFrame([asdict(o) for o in self.closed_orders])
        if td.empty:
            return {"trades": 0, "final_balance": self.balance, "net_pnl": 0.0}
        wins = td[td["pnl_cash"] > 0]
        losses = td[td["pnl_cash"] < 0]
        gross_win = float(wins["pnl_cash"].sum()) if not wins.empty else 0.0
        gross_loss = float(-losses["pnl_cash"].sum()) if not losses.empty else 0.0
        return {
            "trades": len(td),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": round(100.0 * len(wins) / len(td), 1),
            "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else 0.0,
            "net_pnl": round(float(td["pnl_cash"].sum()), 2),
            "expectancy_R": round(float(td["r_multiple"].mean()), 2),
            "final_balance": round(self.balance, 2)
        }
