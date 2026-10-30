"""
AURUM Research - Fractal Market Regime & Hurst Exponent Classifier
==================================================================
Classifies the underlying physical process of the market:
1. Mean-Reverting Process (Hurst < 0.45, Low Efficiency):
   - Fades, FVG fills, Regression +/-2SD reversals are mathematically favorable.
2. Persistent Trending Process (Hurst > 0.55, High Efficiency):
   - Breakouts, BOS continuations, and momentum runs are favored.
   - Counter-trend fades are strictly VETOED.
3. Chaotic White Noise (0.45 <= Hurst <= 0.55):
   - High entropy, lack of edge. Stand aside to preserve capital.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Tuple
import numpy as np
import pandas as pd


@dataclass
class MarketRegime:
    regime_type: str  # "MEAN_REVERTING", "TRENDING_BULLISH", "TRENDING_BEARISH", "CHAOTIC_CHOP"
    hurst_exponent: float
    efficiency_ratio: float
    volatility_atr: float
    allow_counter_trend_fades: bool
    allow_trend_continuations: bool
    description: str


def calculate_hurst_exponent(series: np.ndarray, min_window: int = 10, max_window: int = 80) -> float:
    """
    Estimates the Hurst Exponent (H) using Rescaled Range (R/S) analysis.
    H < 0.5  -> Mean reverting (anti-persistent)
    H == 0.5 -> Random Walk (Brownian motion)
    H > 0.5  -> Persistent (trending)
    """
    n = len(series)
    if n < max_window:
        return 0.50  # Neutral fallback

    # Use log-spaced window sizes
    windows = np.unique(np.linspace(min_window, min(max_window, n // 2), num=6).astype(int))
    rs_values = []
    tau_values = []

    for w in windows:
        if w < 4:
            continue
        # Split series into non-overlapping sub-series of length w
        num_splits = n // w
        if num_splits < 1:
            continue
        
        rs_sub = []
        for i in range(num_splits):
            sub = series[i * w:(i + 1) * w]
            std = np.std(sub)
            if std <= 1e-8:
                continue
            mean = np.mean(sub)
            # Mean-adjusted cumulative deviations
            cum_dev = np.cumsum(sub - mean)
            r = np.max(cum_dev) - np.min(cum_dev)
            rs_sub.append(r / std)

        if rs_sub:
            rs_values.append(np.mean(rs_sub))
            tau_values.append(w)

    if len(tau_values) < 3 or len(rs_values) < 3:
        return 0.50

    # Linear fit in log-log space: log(R/S) = c + H * log(tau)
    log_tau = np.log(tau_values)
    log_rs = np.log(rs_values)
    poly = np.polyfit(log_tau, log_rs, 1)
    h = float(poly[0])

    # Bound H between 0.05 and 0.95
    return float(np.clip(h, 0.05, 0.95))


def calculate_kaufman_efficiency_ratio(closes: np.ndarray, period: int = 20) -> float:
    """
    Computes Kaufman Efficiency Ratio (KER).
    KER = |Price[t] - Price[t-n]| / sum(|Price[i] - Price[i-1]|)
    Values range from 0.0 (maximum noise / choppy) to 1.0 (pure directional trend).
    """
    if len(closes) < period + 1:
        return 0.50

    net_change = abs(closes[-1] - closes[-period - 1])
    diffs = np.abs(np.diff(closes[-period - 1:]))
    total_movement = np.sum(diffs)

    if total_movement <= 1e-8:
        return 0.0

    return float(np.clip(net_change / total_movement, 0.0, 1.0))


def classify_market_regime(
    df: pd.DataFrame,
    lookback: int = 80,
    ker_period: int = 20
) -> MarketRegime:
    """
    Classifies the market state using joint Hurst Exponent, Kaufman Efficiency, and Trend Vector.
    """
    if len(df) < lookback:
        return MarketRegime(
            regime_type="CHAOTIC_CHOP",
            hurst_exponent=0.50,
            efficiency_ratio=0.30,
            volatility_atr=1.0,
            allow_counter_trend_fades=True,
            allow_trend_continuations=True,
            description="Insufficient data for regime classification"
        )

    closes = df["close"].values[-lookback:]
    h = calculate_hurst_exponent(closes, min_window=8, max_window=lookback // 2)
    ker = calculate_kaufman_efficiency_ratio(closes, period=ker_period)

    # Directional slope over the lookback
    slope = (closes[-1] - closes[0]) / len(closes)

    # ATR calculation
    highs = df["high"].values[-14:]
    lows = df["low"].values[-14:]
    atr = float(np.mean(highs - lows)) if len(highs) > 0 else 1.0

    # Decision Matrix:
    # 1. Strong Persistent Trend: H > 0.56 and KER > 0.45
    if h > 0.56 and ker > 0.40:
        if slope > 0:
            regime = "TRENDING_BULLISH"
            allow_fades = False  # DO NOT fade bullish momentum!
            allow_cont = True
            desc = f"Strong Bullish Trend (H={h:.2f}, KER={ker:.2f}) -> Counter-trend shorts strictly vetoed"
        else:
            regime = "TRENDING_BEARISH"
            allow_fades = False  # DO NOT fade bearish momentum!
            allow_cont = True
            desc = f"Strong Bearish Trend (H={h:.2f}, KER={ker:.2f}) -> Counter-trend longs strictly vetoed"
    # 2. Mean Reverting: H < 0.46 and KER < 0.35
    elif h < 0.46 and ker < 0.35:
        regime = "MEAN_REVERTING"
        allow_fades = True   # Fades & regression bounds have highest mathematical expectancy
        allow_cont = False  # Breakouts will likely fail
        desc = f"Mean-Reverting Oscillation (H={h:.2f}, KER={ker:.2f}) -> Reversal sweeps & FVG fills favored"
    # 3. Random Walk / Noise
    else:
        regime = "CHAOTIC_CHOP"
        allow_fades = False  # High risk of random wicks
        allow_cont = False
        desc = f"Chaotic Noise / Indecision (H={h:.2f}, KER={ker:.2f}) -> Capital preservation; stand aside"

    return MarketRegime(
        regime_type=regime,
        hurst_exponent=round(h, 3),
        efficiency_ratio=round(ker, 3),
        volatility_atr=round(atr, 2),
        allow_counter_trend_fades=allow_fades,
        allow_trend_continuations=allow_cont,
        description=desc
    )
