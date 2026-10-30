"""
Layer 2: Volume Flow, Whale Footprint & Volunacci Engine
=========================================================
Merges Volume Spread Analysis (VSA) with dynamic Fibonacci Golden Pockets:
- Relative Volume (RVOL) against rolling institutional baseline
- Institutional Absorption & Climax Volume anomaly detection
- Volunacci Grid: Dynamic Fibonacci Retracements & Extensions (0.382, 0.50, 0.618, 0.705, 0.786, 1.272, 1.618)
  anchored strictly to high-volume institutional footprints.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd


@dataclass
class VolunacciGrid:
    anchor_index: int
    anchor_time: Any
    anchor_type: str  # "BULLISH_CLIMAX", "BEARISH_CLIMAX", "ABSORPTION_LOW", "ABSORPTION_HIGH"
    anchor_high: float
    anchor_low: float
    anchor_rvol: float
    levels: Dict[str, float] = field(default_factory=dict)

    def is_in_golden_pocket(self, price: float) -> bool:
        """Checks if price is within the 0.618 - 0.786 Golden Pocket zone."""
        p_min = min(self.levels.get("fib_0.618", 0.0), self.levels.get("fib_0.786", 0.0))
        p_max = max(self.levels.get("fib_0.618", 0.0), self.levels.get("fib_0.786", 0.0))
        return p_min <= price <= p_max


def calculate_rvol(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """
    Computes Relative Volume (RVOL) = current_volume / SMA(volume, period).
    RVOL > 1.5 indicates significant institutional market interest.
    RVOL > 2.0 indicates an ultra-high volume institutional climax.
    """
    vol_col = "tick_volume" if "tick_volume" in df.columns else ("volume" if "volume" in df.columns else None)
    if vol_col is None or df[vol_col].sum() == 0:
        return pd.Series(1.0, index=df.index)

    vol = df[vol_col].astype(float)
    rolling_vol = vol.rolling(window=period, min_periods=5).mean()
    rvol = vol / (rolling_vol + 1e-9)
    return rvol.fillna(1.0)


def detect_volume_spread_anomalies(
    df: pd.DataFrame,
    rvol_series: pd.Series,
    rvol_threshold: float = 1.60
) -> pd.DataFrame:
    """
    Categorizes institutional volume footprints:
    - ABSORPTION_BUY: High volume on candle with large lower wick (stopping sellers)
    - ABSORPTION_SELL: High volume on candle with large upper wick (stopping buyers)
    - CLIMAX_BUY: Ultra-high volume thrust upwards
    - CLIMAX_SELL: Ultra-high volume thrust downwards
    - CHURN: Ultra-high volume with tiny spread (hidden institutional battle)
    """
    anomalies = pd.DataFrame(index=df.index)
    anomalies["anomaly_type"] = "NORMAL"
    anomalies["rvol"] = rvol_series

    spread = df["high"] - df["low"]
    avg_spread = spread.rolling(20, min_periods=5).mean()
    body = (df["close"] - df["open"]).abs()
    upper_wick = df["high"] - df[["open", "close"]].max(axis=1)
    lower_wick = df[["open", "close"]].min(axis=1) - df["low"]

    for i in range(len(df)):
        rv = rvol_series.iloc[i]
        if rv < rvol_threshold:
            continue

        sp = spread.iloc[i]
        asp = avg_spread.iloc[i] if not np.isnan(avg_spread.iloc[i]) else sp
        bd = body.iloc[i]
        uw = upper_wick.iloc[i]
        lw = lower_wick.iloc[i]

        # Absorption criteria: Wick >= 40% of spread + high volume
        if sp > 0:
            if lw / sp >= 0.40 and df["close"].iloc[i] >= df["open"].iloc[i]:
                anomalies.iloc[i, 0] = "ABSORPTION_BUY"
            elif uw / sp >= 0.40 and df["close"].iloc[i] <= df["open"].iloc[i]:
                anomalies.iloc[i, 0] = "ABSORPTION_SELL"
            elif bd / sp >= 0.65 and df["close"].iloc[i] > df["open"].iloc[i]:
                anomalies.iloc[i, 0] = "CLIMAX_BUY"
            elif bd / sp >= 0.65 and df["close"].iloc[i] < df["open"].iloc[i]:
                anomalies.iloc[i, 0] = "CLIMAX_SELL"
            elif sp <= 0.60 * asp:
                anomalies.iloc[i, 0] = "CHURN"

    return anomalies


def calculate_volunacci_levels(
    anchor_row: pd.Series,
    anchor_index: int,
    anchor_type: str,
    rvol_val: float
) -> VolunacciGrid:
    """
    Constructs an institutional Volunacci Fibonacci Grid anchored on a high-volume candle.
    Ratios:
    - 0.000: Anchor Low
    - 0.382: Shallow pullback
    - 0.500: Equilibrium / Fair Value
    - 0.618: Golden Ratio lower boundary
    - 0.705: Optimal Trade Entry (OTE)
    - 0.786: Golden Ratio upper boundary
    - 1.000: Anchor High
    - 1.272: Extension 1 (Initial take profit)
    - 1.618: Extension 2 (Golden extension)
    """
    h = float(anchor_row.high)
    l = float(anchor_row.low)
    rng = h - l if h > l else 1.0
    t = anchor_row.time if "time" in anchor_row else anchor_index

    # Base grid
    levels = {
        "fib_0.000": l,
        "fib_0.236": l + 0.236 * rng,
        "fib_0.382": l + 0.382 * rng,
        "fib_0.500": l + 0.500 * rng,
        "fib_0.618": l + 0.618 * rng,
        "fib_0.705": l + 0.705 * rng,
        "fib_0.786": l + 0.786 * rng,
        "fib_1.000": h,
        "fib_1.272": l + 1.272 * rng,
        "fib_1.618": l + 1.618 * rng
    }

    return VolunacciGrid(
        anchor_index=anchor_index,
        anchor_time=t,
        anchor_type=anchor_type,
        anchor_high=h,
        anchor_low=l,
        anchor_rvol=rvol_val,
        levels=levels
    )
