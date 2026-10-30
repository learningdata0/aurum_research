"""
Layer 3: Statistical Bounds & Linear Regression Engine
======================================================
Mathematical modeling of price dispersion and statistical equilibrium:
- Dynamic Rolling Linear Regression Channel (Slope, Pearson's R, Residual Std Dev)
- Standard Deviation Envelope Bands (+/- 1.0 SD, +/- 2.0 SD, +/- 2.5 SD)
- Real-time Z-Score computation for mean reversion probability
- Fair Value Gap deviation scoring
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Tuple
import numpy as np
import pandas as pd


@dataclass
class LinearRegressionChannel:
    slope: float
    intercept: float
    r_squared: float
    midline_price: float
    std_dev: float
    upper_1sd: float
    lower_1sd: float
    upper_2sd: float
    lower_2sd: float
    upper_2_5sd: float
    lower_2_5sd: float
    current_zscore: float

    def is_overbought(self, threshold_z: float = 2.0) -> bool:
        return self.current_zscore >= threshold_z

    def is_oversold(self, threshold_z: float = -2.0) -> bool:
        return self.current_zscore <= -threshold_z


def calculate_linear_regression_channel(
    prices: np.ndarray,
    lookback: int = 100
) -> Optional[LinearRegressionChannel]:
    """
    Computes dynamic linear regression channel over the trailing lookback window.
    Calculates least-squares slope, intercept, residual standard deviation, and Z-Score.
    """
    n = len(prices)
    if n < max(20, lookback):
        return None

    y = prices[-lookback:].astype(float)
    x = np.arange(lookback, dtype=float)

    # Fast least-squares
    x_mean = np.mean(x)
    y_mean = np.mean(y)
    numerator = np.sum((x - x_mean) * (y - y_mean))
    denominator = np.sum((x - x_mean) ** 2)

    if denominator == 0:
        return None

    slope = numerator / denominator
    intercept = y_mean - slope * x_mean

    # Fitted values and residuals
    y_fitted = slope * x + intercept
    residuals = y - y_fitted
    std_dev = np.std(residuals)
    if std_dev == 0:
        std_dev = 1e-6

    # Pearson R^2
    ss_tot = np.sum((y - y_mean) ** 2)
    ss_res = np.sum(residuals ** 2)
    r_squared = 1.0 - (ss_res / (ss_tot + 1e-9)) if ss_tot > 0 else 0.0

    # Current bar parameters (at x = lookback - 1)
    curr_midline = float(y_fitted[-1])
    curr_price = float(y[-1])
    curr_zscore = float((curr_price - curr_midline) / std_dev)

    return LinearRegressionChannel(
        slope=float(slope),
        intercept=float(intercept),
        r_squared=float(r_squared),
        midline_price=curr_midline,
        std_dev=float(std_dev),
        upper_1sd=curr_midline + 1.0 * std_dev,
        lower_1sd=curr_midline - 1.0 * std_dev,
        upper_2sd=curr_midline + 2.0 * std_dev,
        lower_2sd=curr_midline - 2.0 * std_dev,
        upper_2_5sd=curr_midline + 2.5 * std_dev,
        lower_2_5sd=curr_midline - 2.5 * std_dev,
        current_zscore=curr_zscore
    )


def calculate_zscore_bands(df: pd.DataFrame, lookback: int = 60) -> pd.Series:
    """
    Returns rolling series of price Z-scores relative to rolling SMA and StdDev.
    """
    closes = df["close"]
    sma = closes.rolling(lookback, min_periods=10).mean()
    std = closes.rolling(lookback, min_periods=10).std()
    zscore = (closes - sma) / (std + 1e-9)
    return zscore.fillna(0.0)
