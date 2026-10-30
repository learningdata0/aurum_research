"""
AURUM Research - Order Flow Delta & Cumulative Volume Delta (CVD) Proxy
========================================================================
Constructs tick-level order flow proxies from OHLCV market data:
1. Intrabar Volume Delta:
   - Uses candle spread dynamics and close position:
     ratio = (Close - Low) / (High - Low)
     Delta = Volume * (2 * ratio - 1)
2. Cumulative Volume Delta (CVD):
   - Continuous integration of delta to measure institutional accumulation vs distribution.
3. Delta Absorption & Divergence:
   - Pinpoints hidden absorption at liquidity sweeps before the next bar unfolds.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Tuple
import numpy as np
import pandas as pd


@dataclass
class OrderFlowSignal:
    timestamp: any
    signal_type: str  # "BULLISH_ABSORPTION", "BEARISH_ABSORPTION", "BUYING_CLIMAX", "SELLING_CLIMAX", "DELTA_DIVERGENCE"
    bar_delta: float
    cvd_slope: float
    strength: float  # 0 to 100
    description: str


def calculate_intrabar_delta(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes bar-by-bar estimated Volume Delta and Cumulative Volume Delta (CVD).
    """
    out = df.copy()
    highs = out["high"].values
    lows = out["low"].values
    closes = out["close"].values
    opens = out["open"].values
    vols = out["volume"].values if "volume" in out else np.ones(len(out))

    ranges = highs - lows
    # Avoid zero division
    safe_ranges = np.where(ranges > 1e-6, ranges, 1e-6)

    # Position of close within the range: 0.0 (at low) to 1.0 (at high)
    close_pos = (closes - lows) / safe_ranges
    
    # Intrabar Delta: scaled from -Volume to +Volume
    # Weight close position (70%) and open-to-close directional body (30%)
    body_dir = np.sign(closes - opens)
    body_ratio = np.abs(closes - opens) / safe_ranges
    
    delta_est = vols * (2.0 * close_pos - 1.0) * 0.7 + vols * (body_dir * body_ratio) * 0.3
    out["bar_delta"] = np.round(delta_est, 2)
    out["cvd"] = np.round(np.cumsum(delta_est), 2)
    
    # 20-period Delta Moving Average
    out["cvd_ema"] = out["cvd"].ewm(span=20, adjust=False).mean()
    return out


def detect_orderflow_anomalies(
    df_with_delta: pd.DataFrame,
    lookback: int = 20
) -> List[OrderFlowSignal]:
    """
    Detects institutional absorption, exhaustion, and delta divergence over the recent slice.
    """
    signals: List[OrderFlowSignal] = []
    if len(df_with_delta) < lookback + 2:
        return signals

    recent = df_with_delta.iloc[-lookback:]
    curr = recent.iloc[-1]
    prev = recent.iloc[-2]

    curr_time = curr["time"] if "time" in curr else None
    curr_delta = float(curr["bar_delta"])
    curr_vol = float(curr["volume"]) if "volume" in curr else 1.0
    mean_vol = float(recent["volume"].mean()) if "volume" in recent else 1.0
    rvol = curr_vol / max(1.0, mean_vol)

    cvd_slope = float(curr["cvd"] - recent["cvd"].iloc[0])

    # 1. Bearish Absorption (Whale selling into buyer breakout)
    # Price makes higher high, but bar delta is strongly negative or fails to expand
    if curr["high"] > prev["high"] and curr_delta < 0 and rvol >= 1.3:
        strength = min(100.0, 50.0 + rvol * 20.0)
        signals.append(OrderFlowSignal(
            timestamp=curr_time,
            signal_type="BEARISH_ABSORPTION",
            bar_delta=curr_delta,
            cvd_slope=cvd_slope,
            strength=strength,
            description=f"Bearish Absorption: New High tested on heavy negative delta ({curr_delta:.1f}, RVOL {rvol:.1f}x)"
        ))

    # 2. Bullish Absorption (Whale buying into seller breakdown)
    # Price makes lower low, but bar delta is strongly positive
    if curr["low"] < prev["low"] and curr_delta > 0 and rvol >= 1.3:
        strength = min(100.0, 50.0 + rvol * 20.0)
        signals.append(OrderFlowSignal(
            timestamp=curr_time,
            signal_type="BULLISH_ABSORPTION",
            bar_delta=curr_delta,
            cvd_slope=cvd_slope,
            strength=strength,
            description=f"Bullish Absorption: New Low tested on heavy positive delta ({curr_delta:.1f}, RVOL {rvol:.1f}x)"
        ))

    # 3. CVD Divergence (Price vs Cumulative Delta over lookback)
    price_high_idx = recent["high"].idxmax()
    cvd_high_idx = recent["cvd"].idxmax()
    if price_high_idx == recent.index[-1] and cvd_high_idx != recent.index[-1] and curr["close"] < curr["open"]:
        signals.append(OrderFlowSignal(
            timestamp=curr_time,
            signal_type="DELTA_DIVERGENCE",
            bar_delta=curr_delta,
            cvd_slope=cvd_slope,
            strength=75.0,
            description="Bearish CVD Divergence: Price peaked but institutional cumulative delta lagged"
        ))

    price_low_idx = recent["low"].idxmin()
    cvd_low_idx = recent["cvd"].idxmin()
    if price_low_idx == recent.index[-1] and cvd_low_idx != recent.index[-1] and curr["close"] > curr["open"]:
        signals.append(OrderFlowSignal(
            timestamp=curr_time,
            signal_type="DELTA_DIVERGENCE",
            bar_delta=curr_delta,
            cvd_slope=cvd_slope,
            strength=75.0,
            description="Bullish CVD Divergence: Price troughed but institutional cumulative delta held higher"
        ))

    return signals
