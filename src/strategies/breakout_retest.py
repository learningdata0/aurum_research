from __future__ import annotations

import math
from typing import Optional, Tuple
import pandas as pd
from ..config import Settings
from ..regime import RegimeState


def evaluate_breakout_retest(
    row: pd.Series,
    rh: float,
    rl: float,
    recent_bars: pd.DataFrame,
    settings: Settings,
    regime_state: RegimeState
) -> Optional[Tuple[str, float, float, float, str]]:
    """
    Hypothesis 5: Breakout -> Retest (Patience Continuation).
    Waits for an initial breakout, then enters only when price pulls back to retest
    the broken boundary (RH as support, RL as resistance) and prints a confirmed bounce.
    """
    if len(recent_bars) < 3:
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

    tolerance = settings.breakout_retest_tolerance_atr * atr
    prior_window = recent_bars.iloc[:-1].tail(10)

    # 1. Bullish Breakout + Retest
    # Step 1: Prior bars had a breakout above RH
    had_breakout_up = (prior_window["close"] > rh + 0.05 * atr).any()
    # Step 2 & 3: Current bar retests RH from above, holds above RH - 0.10*atr, and bounces green
    retested_support = row.low <= rh + tolerance and row.close >= rh - 0.05 * atr
    bullish_continuation = row.close > row.open and row.close > rh

    if had_breakout_up and retested_support and bullish_continuation:
        entry = float(row.close)
        sl = float(rh - 0.25 * atr)
        tp = float(entry + max(entry - rh, 0.50 * atr) * 1.5)
        if (tp - entry) / (entry - sl) >= settings.min_rr:
            return ("BUY", entry, sl, tp, "breakout_retest")

    # 2. Bearish Breakout + Retest
    had_breakout_down = (prior_window["close"] < rl - 0.05 * atr).any()
    retested_resistance = row.high >= rl - tolerance and row.close <= rl + 0.05 * atr
    bearish_continuation = row.close < row.open and row.close < rl

    if had_breakout_down and retested_resistance and bearish_continuation:
        entry = float(row.close)
        sl = float(rl + 0.25 * atr)
        tp = float(entry - max(rl - entry, 0.50 * atr) * 1.5)
        if (entry - tp) / (sl - entry) >= settings.min_rr:
            return ("SELL", entry, sl, tp, "breakout_retest")

    return None
