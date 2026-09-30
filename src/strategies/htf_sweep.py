from __future__ import annotations

import math
from typing import Optional, Tuple
import pandas as pd

from ..config import Settings
from ..htf_levels import DailyHTFContext


def evaluate_htf_sweep_reclaim(
    row: pd.Series,
    ctx: DailyHTFContext,
    settings: Settings,
    hypothesis_id: str = "H7",
    recent_bars: pd.DataFrame | None = None,
    tp_mode: str = "swing"  # "swing" or "scalp"
) -> Optional[Tuple[str, float, float, float, str]]:
    """
    Evaluates Higher Timeframe (HTF) Liquidity Sweep-Reclaim setups.
    
    hypotheses:
      H7:  PDH / PDL Sweep-Reclaim (Neutral Context)
      H8a: London Session Extremes Sweep-Reclaim
      H8b: Asia Session Extremes Sweep-Reclaim
      H9:  PDH / PDL + HTF Regime (Trend Continuation vs Range Reversal)
      H10: PDH / PDL Conditioned on Opening Range Quartile
      H11: PDH / PDL Conditioned on Ex-Ante Volatility Regime (Skip Compressed)
    """
    atr = row["atr"]
    if not (math.isfinite(atr) and atr > 0):
        return None

    c_range = max(row["high"] - row["low"], 1e-12)
    sweep_buffer = max(0.05 * atr, 1.0)  # Min 0.05 ATR penetration

    # Select target levels based on hypothesis
    if hypothesis_id in ("H7", "H9", "H10", "H11"):
        high_level = ctx.pdh
        low_level = ctx.pdl
        mid_level = ctx.pd_mid
    elif hypothesis_id == "H8a":  # London
        if ctx.london_high is None or ctx.london_low is None:
            return None
        high_level = ctx.london_high
        low_level = ctx.london_low
        mid_level = (high_level + low_level) / 2.0
    elif hypothesis_id == "H8b":  # Asia
        if ctx.asia_high is None or ctx.asia_low is None:
            return None
        high_level = ctx.asia_high
        low_level = ctx.asia_low
        mid_level = (high_level + low_level) / 2.0
    else:
        high_level = ctx.pdh
        low_level = ctx.pdl
        mid_level = ctx.pd_mid

    # Filter for H10: Quartile Position Conditioning
    if hypothesis_id == "H10":
        # Only allow short if open was near high (UPPER_25 or ABOVE_PDH)
        # Only allow long if open was near low (LOWER_25 or BELOW_PDL)
        allow_short_h10 = ctx.open_quartile in ("UPPER_25", "ABOVE_PDH")
        allow_long_h10 = ctx.open_quartile in ("LOWER_25", "BELOW_PDL")
    else:
        allow_short_h10 = True
        allow_long_h10 = True

    # Filter for H11: Volatility Regime Conditioning
    if hypothesis_id == "H11":
        # Mean reversion is strictly forbidden on COMPRESSED volatility days
        # (compression leads to breakout expansion)
        if ctx.volatility_regime == "COMPRESSED":
            return None

    # Filter for H9: HTF Regime (Trend vs Range)
    # In TREND_UP: forbid fading PDH short; allow PDL dip buy or PDH breakout continuation
    # In TREND_DOWN: forbid fading PDL long; allow PDH rally fade or PDL breakout continuation
    allow_short_h9 = True
    allow_long_h9 = True
    if hypothesis_id == "H9":
        if ctx.htf_trend == "TREND_UP":
            allow_short_h9 = False  # Don't short against strong daily uptrend
        elif ctx.htf_trend == "TREND_DOWN":
            allow_long_h9 = False   # Don't long against strong daily downtrend

    # -------------------------------------------------------------
    # 1. Bearish Liquidity Sweep (High Level: PDH or Session High)
    # -------------------------------------------------------------
    if allow_short_h10 and allow_short_h9:
        # Check sweep: penetrated above level
        swept_high = row["high"] >= high_level + sweep_buffer
        # Check reclaim: closed back below level
        reclaimed_high = row["close"] < high_level and row["close"] > low_level
        # Confirmation: bearish candle or rejection upper wick
        bearish_confirm = (row["close"] < row["open"]) or (row["upper_wick"] >= 0.25 * c_range)

        if swept_high and reclaimed_high and bearish_confirm:
            entry = float(row["close"])
            sl = float(row["high"] + 0.10 * atr)
            risk = sl - entry
            if risk > 0:
                if tp_mode == "scalp":
                    # Scalp Mode: Quick fixed 1.0R target
                    tp = float(entry - 1.0 * risk)
                else:
                    # Swing Mode: Target Day Midpoint or 1.5R minimum
                    raw_tp = mid_level if mid_level < entry else entry - 1.5 * risk
                    tp = float(min(raw_tp, entry - 1.25 * risk))

                if tp < entry and (entry - tp) / risk >= (1.0 if tp_mode == "scalp" else settings.min_rr):
                    return ("SELL", entry, sl, tp, f"{hypothesis_id}_bearish_sweep")

    # -------------------------------------------------------------
    # 2. Bullish Liquidity Sweep (Low Level: PDL or Session Low)
    # -------------------------------------------------------------
    if allow_long_h10 and allow_long_h9:
        swept_low = row["low"] <= low_level - sweep_buffer
        reclaimed_low = row["close"] > low_level and row["close"] < high_level
        bullish_confirm = (row["close"] > row["open"]) or (row["lower_wick"] >= 0.25 * c_range)

        if swept_low and reclaimed_low and bullish_confirm:
            entry = float(row["close"])
            sl = float(row["low"] - 0.10 * atr)
            risk = entry - sl
            if risk > 0:
                if tp_mode == "scalp":
                    tp = float(entry + 1.0 * risk)
                else:
                    raw_tp = mid_level if mid_level > entry else entry + 1.5 * risk
                    tp = float(max(raw_tp, entry + 1.25 * risk))

                if tp > entry and (tp - entry) / risk >= (1.0 if tp_mode == "scalp" else settings.min_rr):
                    return ("BUY", entry, sl, tp, f"{hypothesis_id}_bullish_sweep")

    # -------------------------------------------------------------
    # 3. H9 Trend Continuation (When HTF trend is present)
    # -------------------------------------------------------------
    if hypothesis_id == "H9":
        # Up-trend continuation: Price breaks PDH and closes strongly above
        if ctx.htf_trend == "TREND_UP":
            broke_pdh = row["close"] > high_level + 0.15 * atr
            strong_body = (row["close"] - row["open"]) >= 0.50 * c_range
            if broke_pdh and strong_body:
                entry = float(row["close"])
                sl = float(high_level - 0.10 * atr)
                risk = entry - sl
                if risk > 0:
                    tp = float(entry + (1.0 * risk if tp_mode == "scalp" else 1.5 * risk))
                    return ("BUY", entry, sl, tp, "H9_trend_continuation_buy")

        # Down-trend continuation: Price breaks PDL and closes strongly below
        elif ctx.htf_trend == "TREND_DOWN":
            broke_pdl = row["close"] < low_level - 0.15 * atr
            strong_body = (row["open"] - row["close"]) >= 0.50 * c_range
            if broke_pdl and strong_body:
                entry = float(row["close"])
                sl = float(low_level + 0.10 * atr)
                risk = sl - entry
                if risk > 0:
                    tp = float(entry - (1.0 * risk if tp_mode == "scalp" else 1.5 * risk))
                    return ("SELL", entry, sl, tp, "H9_trend_continuation_sell")

    return None
