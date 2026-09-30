from __future__ import annotations

import math
from typing import Optional, Tuple
import pandas as pd
from ..config import Settings
from ..regime import MarketRegime, RegimeState


def evaluate_micro_range(
    row: pd.Series,
    recent_bars: pd.DataFrame,
    settings: Settings,
    regime_state: RegimeState
) -> Optional[Tuple[str, float, float, float, str]]:
    """
    Hypothesis 3: Dynamic Intraday Micro-Range Reversion.
    Identifies oscillating local swing levels inside the active session.
    Trades between local edges with tight risk.
    """
    # Guard: requires healthy range and minimum health score
    if regime_state.regime != MarketRegime.HEALTHY_RANGE or regime_state.score < settings.min_range_health_score:
        return None
    if regime_state.is_expanding:
        return None

    if len(recent_bars) < settings.micro_range_lookback:
        return None

    lookback_window = recent_bars.tail(settings.micro_range_lookback)
    micro_rh = float(lookback_window["high"].max())
    micro_rl = float(lookback_window["low"].min())
    micro_width = micro_rh - micro_rl

    atr = row.atr
    if not (math.isfinite(atr) and atr > 0 and micro_width > 0):
        return None

    # Micro-range must be bounded in volatility
    if micro_width < 0.75 * atr or micro_width > 4.0 * atr:
        return None

    micro_zone = max(0.15 * atr, micro_width * 0.15)
    c_range = max(row.high - row.low, 1e-12)

    # Buy near micro low
    if row.low <= micro_rl + micro_zone and row.close >= micro_rl and row.close > row.open:
        if row.lower_wick >= 0.25 * c_range:
            entry = float(row.close)
            sl = float(micro_rl - 0.15 * atr)
            tp = float(micro_rh - 0.10 * atr)
            if tp > entry and (tp - entry) / (entry - sl) >= settings.min_rr:
                return ("BUY", entry, sl, tp, "micro_range")

    # Sell near micro high
    if row.high >= micro_rh - micro_zone and row.close <= micro_rh and row.close < row.open:
        if row.upper_wick >= 0.25 * c_range:
            entry = float(row.close)
            sl = float(micro_rh + 0.15 * atr)
            tp = float(micro_rl + 0.10 * atr)
            if tp < entry and (entry - tp) / (sl - entry) >= settings.min_rr:
                return ("SELL", entry, sl, tp, "micro_range")

    return None
