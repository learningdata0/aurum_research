from __future__ import annotations

import math
from typing import Optional, Tuple
import pandas as pd
from ..config import Settings
from ..regime import RegimeState


def evaluate_breakout(
    row: pd.Series,
    rh: float,
    rl: float,
    settings: Settings,
    regime_state: RegimeState
) -> Optional[Tuple[str, float, float, float, str]]:
    """
    Hypothesis 4: Immediate Momentum Breakout.
    Requires decisive close outside the Opening Range with strong candle body
    and sufficient ATR buffer to avoid false tick breakouts.
    """
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

    buffer = settings.breakout_buffer_atr * atr
    c_range = max(row.high - row.low, 1e-12)
    body = abs(row.close - row.open)
    body_ratio = body / c_range

    # 1. Bullish Breakout
    if row.close > rh + buffer and row.close > row.open:
        # Requires body strength (not an exhaustion wick with tiny body)
        if body_ratio >= settings.breakout_min_body_ratio and row.upper_wick <= 0.30 * c_range:
            entry = float(row.close)
            sl = float(rh - 0.35 * atr)
            tp = float(entry + max(entry - rh, 0.50 * atr) * 1.5)
            if (tp - entry) / (entry - sl) >= settings.min_rr:
                return ("BUY", entry, sl, tp, "breakout")

    # 2. Bearish Breakout
    if row.close < rl - buffer and row.close < row.open:
        if body_ratio >= settings.breakout_min_body_ratio and row.lower_wick <= 0.30 * c_range:
            entry = float(row.close)
            sl = float(rl + 0.35 * atr)
            tp = float(entry - max(rl - entry, 0.50 * atr) * 1.5)
            if (entry - tp) / (sl - entry) >= settings.min_rr:
                return ("SELL", entry, sl, tp, "breakout")

    return None
