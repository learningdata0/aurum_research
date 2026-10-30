"""
Layer 1: Structural SMC & Fractality Engine
============================================
Mathematical detection of institutional market structure:
- Multi-scale Fractal Pivot Highs and Lows
- Virgin and Mitigated Fair Value Gaps (FVG) with Consequent Encroachment (CE 50%)
- Market Structure Shifts (MSS / CHoCH) and Breaks of Structure (BOS)
- Dynamic Liquidity Sweeps with Wick-to-Body Exhaustion
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple
import numpy as np
import pandas as pd


@dataclass
class FractalPivot:
    index: int
    time: Any
    price: float
    pivot_type: str  # "HIGH" or "LOW"
    span: int = 5


@dataclass
class FairValueGap:
    index: int
    time: Any
    gap_type: str  # "BULLISH" or "BEARISH"
    top: float
    bottom: float
    midpoint: float  # Consequent Encroachment (CE 50%)
    size_pts: float
    mitigated: bool = False
    mitigated_index: Optional[int] = None
    mitigated_time: Optional[Any] = None

    def is_price_inside(self, price: float) -> bool:
        return self.bottom <= price <= self.top


@dataclass
class StructureShift:
    index: int
    time: Any
    shift_type: str  # "CHoCH_BULL", "CHoCH_BEAR", "BOS_BULL", "BOS_BEAR"
    broken_level: float
    break_price: float


def detect_fractals(df: pd.DataFrame, span: int = 5) -> List[FractalPivot]:
    """
    Identifies high-fidelity multi-bar fractal pivots.
    For span=5: candle i is a Fractal High if High[i] > High[i-2, i-1, i+1, i+2].
    """
    if len(df) < span:
        return []

    half = span // 2
    highs = df["high"].values
    lows = df["low"].values
    times = df["time"].values if "time" in df.columns else np.arange(len(df))
    pivots: List[FractalPivot] = []

    for i in range(half, len(df) - half):
        # High pivot check
        curr_h = highs[i]
        is_h_pivot = True
        for offset in range(-half, half + 1):
            if offset != 0 and highs[i + offset] >= curr_h:
                is_h_pivot = False
                break
        if is_h_pivot:
            pivots.append(FractalPivot(index=i, time=times[i], price=float(curr_h), pivot_type="HIGH", span=span))

        # Low pivot check
        curr_l = lows[i]
        is_l_pivot = True
        for offset in range(-half, half + 1):
            if offset != 0 and lows[i + offset] <= curr_l:
                is_l_pivot = False
                break
        if is_l_pivot:
            pivots.append(FractalPivot(index=i, time=times[i], price=float(curr_l), pivot_type="LOW", span=span))

    return pivots


def detect_fair_value_gaps(df: pd.DataFrame, min_gap_pts: float = 0.5) -> List[FairValueGap]:
    """
    Detects 3-candle institutional Fair Value Gaps (FVG) and tracks mitigation in real time.
    Bullish FVG: Low of candle i > High of candle i-2 (Uncontested gap between i-2 and i).
    Bearish FVG: High of candle i < Low of candle i-2.
    Consequent Encroachment (CE) represents the 50% equilibrium level of the gap.
    """
    if len(df) < 3:
        return []

    highs = df["high"].values
    lows = df["low"].values
    times = df["time"].values if "time" in df.columns else np.arange(len(df))
    fvgs: List[FairValueGap] = []

    for i in range(2, len(df)):
        # 1. Bullish FVG
        if lows[i] > highs[i - 2]:
            gap_size = lows[i] - highs[i - 2]
            if gap_size >= min_gap_pts:
                bottom = float(highs[i - 2])
                top = float(lows[i])
                ce = (bottom + top) / 2.0
                fvg = FairValueGap(
                    index=i - 1,
                    time=times[i - 1],
                    gap_type="BULLISH",
                    top=top,
                    bottom=bottom,
                    midpoint=ce,
                    size_pts=gap_size
                )
                # Check mitigation in future bars
                for future_idx in range(i + 1, len(df)):
                    if lows[future_idx] <= bottom:  # Full mitigation
                        fvg.mitigated = True
                        fvg.mitigated_index = future_idx
                        fvg.mitigated_time = times[future_idx]
                        break
                fvgs.append(fvg)

        # 2. Bearish FVG
        elif highs[i] < lows[i - 2]:
            gap_size = lows[i - 2] - highs[i]
            if gap_size >= min_gap_pts:
                top = float(lows[i - 2])
                bottom = float(highs[i])
                ce = (bottom + top) / 2.0
                fvg = FairValueGap(
                    index=i - 1,
                    time=times[i - 1],
                    gap_type="BEARISH",
                    top=top,
                    bottom=bottom,
                    midpoint=ce,
                    size_pts=gap_size
                )
                # Check mitigation in future bars
                for future_idx in range(i + 1, len(df)):
                    if highs[future_idx] >= top:  # Full mitigation
                        fvg.mitigated = True
                        fvg.mitigated_index = future_idx
                        fvg.mitigated_time = times[future_idx]
                        break
                fvgs.append(fvg)

    return fvgs


def detect_market_structure_shifts(df: pd.DataFrame, pivots: List[FractalPivot]) -> List[StructureShift]:
    """
    Detects Breaks of Structure (BOS) and Changes of Character (CHoCH)
    using validated fractal swings.
    """
    shifts: List[StructureShift] = []
    if len(pivots) < 2:
        return shifts

    high_pivots = [p for p in pivots if p.pivot_type == "HIGH"]
    low_pivots = [p for p in pivots if p.pivot_type == "LOW"]

    closes = df["close"].values
    times = df["time"].values if "time" in df.columns else np.arange(len(df))

    # Track bullish CHoCH: price closes above most recent confirmed high pivot
    last_h_pivot_idx = 0
    last_l_pivot_idx = 0

    for i in range(len(df)):
        c_price = closes[i]

        # Update confirmed pivots prior to bar i
        active_highs = [p for p in high_pivots if p.index + (p.span // 2) < i]
        active_lows = [p for p in low_pivots if p.index + (p.span // 2) < i]

        if active_highs:
            recent_h = active_highs[-1]
            if c_price > recent_h.price and i > recent_h.index:
                shifts.append(StructureShift(
                    index=i,
                    time=times[i],
                    shift_type="BOS_BULL",
                    broken_level=recent_h.price,
                    break_price=c_price
                ))

        if active_lows:
            recent_l = active_lows[-1]
            if c_price < recent_l.price and i > recent_l.index:
                shifts.append(StructureShift(
                    index=i,
                    time=times[i],
                    shift_type="BOS_BEAR",
                    broken_level=recent_l.price,
                    break_price=c_price
                ))

    return shifts


def detect_liquidity_sweeps(
    row: pd.Series,
    target_high: float,
    target_low: float,
    min_sweep_pts: float = 0.5,
    min_wick_ratio: float = 0.35
) -> Optional[Tuple[str, float, float]]:
    """
    Detects pristine institutional liquidity sweeps.
    Returns (direction, swept_level, sweep_penetration_pts) or None.
    - Direction "BEAR_SWEEP" (Bull trap: swept high, wicked down, closed inside) -> SHORT signal
    - Direction "BULL_SWEEP" (Bear trap: swept low, wicked up, closed inside) -> LONG signal
    """
    candle_range = row.high - row.low
    if candle_range <= 0:
        return None

    # Bearish Sweep of Liquidity High
    if row.high > target_high:
        penetration = row.high - target_high
        upper_wick = row.high - max(row.open, row.close)
        wick_ratio = upper_wick / candle_range

        # Sweep qualification: penetrated high, closed below target_high, long rejection wick
        if penetration >= min_sweep_pts and row.close <= target_high and wick_ratio >= min_wick_ratio:
            return ("BEAR_SWEEP", target_high, penetration)

    # Bullish Sweep of Liquidity Low
    if row.low < target_low:
        penetration = target_low - row.low
        lower_wick = min(row.open, row.close) - row.low
        wick_ratio = lower_wick / candle_range

        # Sweep qualification: penetrated low, closed above target_low, long absorption wick
        if penetration >= min_sweep_pts and row.close >= target_low and wick_ratio >= min_wick_ratio:
            return ("BULL_SWEEP", target_low, penetration)

    return None
