from __future__ import annotations

import math
from typing import Optional, Tuple
import pandas as pd
from ..config import Settings
from ..regime import MarketRegime, RegimeState


def evaluate_sweep_reclaim(
    row: pd.Series,
    rh: float,
    rl: float,
    settings: Settings,
    regime_state: RegimeState,
    prev_bars: pd.DataFrame | None = None
) -> Optional[Tuple[str, float, float, float, str]]:
    """
    Hypothesis 2 / Behavioral Execution:
    Sequence: APPROACH -> SWEEP -> RECLAIM -> CONFIRMATION -> EXECUTE.
    Trades the behavior of liquidity absorption at range boundaries rather than fixed price levels.
    """
    # Regime filter: Mean reversion strictly forbidden in BROKEN_RANGE or TREND
    if not regime_state.allows_sweep_reclaim():
        return None

    atr = row.atr
    if not (math.isfinite(atr) and atr > 0):
        return None

    width = rh - rl
    if width <= 0:
        return None

    expected_atr = atr * math.sqrt(settings.range_minutes) if settings.range_minutes > 1 else atr
    ratio = width / expected_atr
    if ratio < settings.atr_min_multiple or ratio > settings.atr_max_multiple:
        return None

    sweep_buffer = settings.sweep_atr * atr
    mid = (rh + rl) / 2.0
    c_range = max(row.high - row.low, 1e-12)

    # 1. Bearish Liquidity Sweep (HIGH -> APPROACH -> SWEEP -> RECLAIM -> CONFIRMATION)
    # Approach: Prior bars were inside range approaching the boundary
    approach_high = True
    if prev_bars is not None and len(prev_bars) >= 2:
        recent = prev_bars.iloc[-3:]
        # Approach: price came from below or near RH
        approach_high = any(recent["close"] >= rh - 0.75 * atr) and all(recent["close"] <= rh + 1.0 * atr)

    swept_high = row.high >= rh + sweep_buffer
    reclaimed_high = row.close <= rh and row.close > rl

    # Confirmation tier based on Regime
    if regime_state.regime == MarketRegime.HEALTHY_RANGE:
        bearish_confirm = (row.close < row.open) or (row.upper_wick >= 0.25 * c_range)
    elif regime_state.regime == MarketRegime.WEAK_RANGE:
        # Higher bar in weak regime: require both or large rejection wick
        bearish_confirm = (row.upper_wick >= 0.35 * c_range) or (row.close < row.open and row.upper_wick >= 0.20 * c_range)
    else:
        bearish_confirm = False

    if approach_high and swept_high and reclaimed_high and bearish_confirm:
        entry = float(row.close)
        sl = float(row.high + 0.10 * atr)
        tp = float(mid if mid < entry else rl + 0.10 * atr)
        if tp < entry and (entry - tp) / (sl - entry) >= settings.min_rr:
            return ("SELL", entry, sl, tp, "sweep_reclaim")

    # 2. Bullish Liquidity Sweep (LOW -> APPROACH -> SWEEP -> RECLAIM -> CONFIRMATION)
    approach_low = True
    if prev_bars is not None and len(prev_bars) >= 2:
        recent = prev_bars.iloc[-3:]
        approach_low = any(recent["close"] <= rl + 0.75 * atr) and all(recent["close"] >= rl - 1.0 * atr)

    swept_low = row.low <= rl - sweep_buffer
    reclaimed_low = row.close >= rl and row.close < rh

    if regime_state.regime == MarketRegime.HEALTHY_RANGE:
        bullish_confirm = (row.close > row.open) or (row.lower_wick >= 0.25 * c_range)
    elif regime_state.regime == MarketRegime.WEAK_RANGE:
        bullish_confirm = (row.lower_wick >= 0.35 * c_range) or (row.close > row.open and row.lower_wick >= 0.20 * c_range)
    else:
        bullish_confirm = False

    if approach_low and swept_low and reclaimed_low and bullish_confirm:
        entry = float(row.close)
        sl = float(row.low - 0.10 * atr)
        tp = float(mid if mid > entry else rh - 0.10 * atr)
        if tp > entry and (tp - entry) / (entry - sl) >= settings.min_rr:
            return ("BUY", entry, sl, tp, "sweep_reclaim")

    return None
