from __future__ import annotations

import math
from typing import Optional, Tuple
import pandas as pd
from ..config import Settings
from ..regime import MarketRegime, RegimeState


def evaluate_boundary_reversion(
    row: pd.Series,
    rh: float,
    rl: float,
    settings: Settings,
    regime_state: RegimeState
) -> Optional[Tuple[str, float, float, float, str]]:
    """
    Hypothesis 1: True Boundary Reversion.
    Strictly enters near the boundary when price tests and rejects the level.
    Never enters if price is far away from the range.
    """
    # Regime filter: Only permitted in HEALTHY_RANGE
    if regime_state.regime != MarketRegime.HEALTHY_RANGE:
        return None

    atr = row.atr
    if not (math.isfinite(atr) and atr > 0):
        return None

    width = rh - rl
    if width <= 0:
        return None

    # Volatility bounds on opening range width
    expected_atr = atr * math.sqrt(settings.range_minutes) if settings.range_minutes > 1 else atr
    ratio = width / expected_atr
    if ratio < settings.atr_min_multiple or ratio > settings.atr_max_multiple:
        return None

    zone = max(settings.zone_atr * atr, width * 0.10)
    mid = (rh + rl) / 2.0
    c_range = max(row.high - row.low, 1e-12)

    # Rejection wick criteria
    bull_reject = row.close > row.open and row.lower_wick >= settings.rejection_wick_ratio * c_range
    bear_reject = row.close < row.open and row.upper_wick >= settings.rejection_wick_ratio * c_range

    # 1. Buy Boundary Reversion (Near Range Low, strictly staying inside/at boundary)
    # Price touched near RL, closed inside range, and not far above zone
    if row.low <= rl + zone and row.close >= rl - 0.10 * atr and row.close <= rl + 2.0 * zone and bull_reject:
        entry = float(row.close)
        sl = float(min(row.low, rl) - 0.10 * atr)
        tp = float(mid if mid > entry else rh - 0.10 * atr)
        if tp > entry and (tp - entry) / (entry - sl) >= settings.min_rr:
            return ("BUY", entry, sl, tp, "boundary_reversion")

    # 2. Sell Boundary Reversion (Near Range High, strictly staying inside/at boundary)
    if row.high >= rh - zone and row.close <= rh + 0.10 * atr and row.close >= rh - 2.0 * zone and bear_reject:
        entry = float(row.close)
        sl = float(max(row.high, rh) + 0.10 * atr)
        tp = float(mid if mid < entry else rl + 0.10 * atr)
        if tp < entry and (entry - tp) / (sl - entry) >= settings.min_rr:
            return ("SELL", entry, sl, tp, "boundary_reversion")

    return None
