from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
import json
from pathlib import Path
from typing import Optional


@dataclass
class Settings:
    # Portfolio & Risk Limits
    initial_balance: float = 10000.0
    risk_per_trade: float = 0.0025          # 0.25% of balance = 1R
    max_daily_loss: float = 0.015           # 1.5% max daily loss lock
    max_consecutive_losses: int = 4         # Circuit breaker
    max_trades_per_day: int = 12            # Max trades per day
    max_hold_minutes: int = 120             # Max hold time exit

    # Session & Timing (Anchored in America/New_York)
    timezone: str = "America/New_York"
    source_timezone: str = "Europe/Athens"  # MetaTrader 5 broker time (EET/EEST)
    session_start_local: str = "09:30"      # Local NY Open
    session_end_local: str = "12:00"        # Local NY session end
    range_minutes: int = 30                 # Opening Range length: 5, 10, 15, 20, 30, 45, 60

    # Volatility & ATR Configuration
    atr_period: int = 14
    atr_min_multiple: float = 0.35          # Min normalized range ratio (width / (atr * sqrt(range_minutes)))
    atr_max_multiple: float = 2.50          # Max normalized range ratio

    # Reversion Parameters
    zone_atr: float = 0.20                  # Max distance from boundary for Boundary Reversion
    sweep_atr: float = 0.10                 # Min penetration for Sweep Reclaim
    rejection_wick_ratio: float = 0.35      # Min wick ratio for rejection candles
    micro_range_lookback: int = 15          # Lookback bars for intraday micro-ranges
    min_range_health_score: float = 60.0    # Min score to allow mean reversion

    # Breakout Parameters
    breakout_buffer_atr: float = 0.10       # Buffer beyond boundary for Breakout
    breakout_min_body_ratio: float = 0.50   # Min body ratio for momentum breakout
    breakout_retest_tolerance_atr: float = 0.15 # Retest touch tolerance

    # Execution & Targets
    min_rr: float = 1.25                    # Minimum Reward-to-Risk ratio
    tp_mode: str = "mid_or_opposite_edge"
    partial_at_1r: float = 0.50
    commission_per_unit: float = 0.0        # Round-turn commission per unit
    slippage_points: float = 0.0            # Slippage in points per trade


def load_settings(path: str | Path) -> Settings:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
        valid_keys = {k for k in Settings.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return Settings(**filtered)


def save_settings(settings: Settings, path: str | Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(asdict(settings), f, indent=2)
