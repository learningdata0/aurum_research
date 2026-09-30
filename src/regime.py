from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import numpy as np
import pandas as pd


class MarketRegime(str, Enum):
    PRE_SESSION = "PRE_SESSION"
    OPENING_RANGE = "OPENING_RANGE"
    HEALTHY_RANGE = "HEALTHY_RANGE"
    WEAK_RANGE = "WEAK_RANGE"
    BROKEN_RANGE = "BROKEN_RANGE"
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"


@dataclass
class RegimeState:
    score: float
    regime: MarketRegime
    adx: float
    pos_di: float
    neg_di: float
    vwap_dist_atr: float
    is_expanding: bool
    trend_direction: Optional[str] = None

    def allows_mean_reversion(self) -> bool:
        """Only healthy ranges allow standard mean reversion."""
        return self.regime == MarketRegime.HEALTHY_RANGE

    def allows_sweep_reclaim(self) -> bool:
        """Healthy and weak ranges allow sweep-reclaim (with strict confirmation in weak)."""
        return self.regime in (MarketRegime.HEALTHY_RANGE, MarketRegime.WEAK_RANGE)

    def allows_breakout(self, direction: str) -> bool:
        """Breakouts allowed in trending states matching direction or broken range."""
        if self.regime == MarketRegime.TREND_UP and direction == "BUY":
            return True
        if self.regime == MarketRegime.TREND_DOWN and direction == "SELL":
            return True
        if self.regime == MarketRegime.BROKEN_RANGE:
            return True
        return False

    def is_trend(self) -> bool:
        return self.regime in (MarketRegime.TREND_UP, MarketRegime.TREND_DOWN)


class MarketRegimeDetector:
    """
    AURUM Regime Engine 2.0:
    State Machine:
      PRE_SESSION
           ↓
      OPENING_RANGE
           ↓
      ┌───────────────────────────┐
      │                           │
      RANGE                   TREND_UP
      │                           │
      ├── HEALTHY_RANGE       TREND_DOWN
      ├── WEAK_RANGE
      └── BROKEN_RANGE
    """

    def __init__(self, min_healthy_score: float = 65.0, min_unstable_score: float = 40.0):
        self.min_healthy_score = min_healthy_score
        self.min_unstable_score = min_unstable_score

    def evaluate(
        self,
        row: pd.Series,
        range_high: float,
        range_low: float,
        prev_bars: pd.DataFrame | None = None
    ) -> RegimeState:
        atr = row.atr if np.isfinite(row.atr) and row.atr > 0 else 1.0
        adx = float(getattr(row, "adx", 20.0))
        pos_di = float(getattr(row, "pos_di", 20.0))
        neg_di = float(getattr(row, "neg_di", 20.0))
        vwap_dist = float(getattr(row, "vwap_dist", 0.0))
        candle_range = float(getattr(row, "candle_range", atr))

        width = range_high - range_low
        close = float(getattr(row, "close", (range_high + range_low) / 2.0))
        mid = (range_high + range_low) / 2.0 if width > 0 else close
        is_expanding = False
        recent_width = width
        if prev_bars is not None and len(prev_bars) >= 5 and width > 0:
            recent_high = float(prev_bars["high"].max())
            recent_low = float(prev_bars["low"].min())
            recent_width = recent_high - recent_low
            if recent_width > width * 1.30:
                is_expanding = True

        # Check Trend conditions:
        # 1. ADX >= 25 indicates strong directional movement
        # 2. Closes breaking significantly outside the range (> 0.50 ATR beyond boundary)
        is_strong_adx = adx >= 25.0
        is_bullish_flow = pos_di > neg_di and (close > mid or vwap_dist > 0.5)
        is_bearish_flow = neg_di > pos_di and (close < mid or vwap_dist < -0.5)

        is_outside_high = close > (range_high + 0.35 * atr)
        is_outside_low = close < (range_low - 0.35 * atr)

        if (is_strong_adx and is_bullish_flow and close > mid) or (is_outside_high and is_bullish_flow):
            return RegimeState(
                score=15.0,
                regime=MarketRegime.TREND_UP,
                adx=round(adx, 1),
                pos_di=round(pos_di, 1),
                neg_di=round(neg_di, 1),
                vwap_dist_atr=round(vwap_dist, 2),
                is_expanding=is_expanding,
                trend_direction="UP"
            )

        if (is_strong_adx and is_bearish_flow and close < mid) or (is_outside_low and is_bearish_flow):
            return RegimeState(
                score=15.0,
                regime=MarketRegime.TREND_DOWN,
                adx=round(adx, 1),
                pos_di=round(pos_di, 1),
                neg_di=round(neg_di, 1),
                vwap_dist_atr=round(vwap_dist, 2),
                is_expanding=is_expanding,
                trend_direction="DOWN"
            )

        # If not pure Trend, calculate Range Health Score (0 - 100)
        score = 0.0

        # 1. ADX Component (Max 30 pts) - Lower ADX = Healthier Range
        if adx < 18.0:
            score += 30.0
        elif adx < 22.0:
            score += 22.0
        elif adx < 26.0:
            score += 12.0
        else:
            score += 0.0

        # 2. VWAP Deviation Component (Max 25 pts)
        abs_vwap = abs(vwap_dist)
        if abs_vwap <= 1.0:
            score += 25.0
        elif abs_vwap <= 1.8:
            score += 15.0
        elif abs_vwap <= 2.5:
            score += 5.0
        else:
            score += 0.0

        # 3. ATR Volatility Stability Component (Max 25 pts)
        if candle_range <= 1.4 * atr:
            score += 25.0
        elif candle_range <= 2.2 * atr:
            score += 15.0
        else:
            score += 0.0

        # 4. Boundary Stability Component (Max 20 pts)
        if not is_expanding:
            score += 20.0
        else:
            score += 0.0

        score = max(0.0, min(100.0, score))

        # Classify sub-range:
        # BROKEN_RANGE requires either massive boundary expansion (> 2.0x width) or low health score (< 40)
        is_massive_expansion = recent_width > width * 2.0 if width > 0 else False
        if is_massive_expansion or score < self.min_unstable_score:
            regime = MarketRegime.BROKEN_RANGE
        elif score >= self.min_healthy_score:
            regime = MarketRegime.HEALTHY_RANGE
        else:
            regime = MarketRegime.WEAK_RANGE

        return RegimeState(
            score=round(score, 1),
            regime=regime,
            adx=round(adx, 1),
            pos_di=round(pos_di, 1),
            neg_di=round(neg_di, 1),
            vwap_dist_atr=round(vwap_dist, 2),
            is_expanding=is_expanding,
            trend_direction=None
        )
