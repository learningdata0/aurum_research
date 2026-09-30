from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple
import numpy as np
import pandas as pd


@dataclass
class DailyHTFContext:
    day: Any
    pdh: float
    pdl: float
    pdc: float
    pdo: float
    pdr: float
    pd_mid: float
    pd_upper_quartile: float
    pd_lower_quartile: float
    open_at_ny: float
    open_quartile: str  # "UPPER_25", "MID_UPPER", "MID_LOWER", "LOWER_25", "ABOVE_PDH", "BELOW_PDL"
    htf_trend: str      # "TREND_UP", "TREND_DOWN", "RANGE"
    pdr_atr_ratio: float
    volatility_regime: str  # "COMPRESSED", "NORMAL", "EXPANDED"
    london_high: Optional[float]
    london_low: Optional[float]
    asia_high: Optional[float]
    asia_low: Optional[float]


def build_htf_context_map(d: pd.DataFrame) -> Dict[Any, DailyHTFContext]:
    """
    Computes daily Higher Timeframe (HTF) levels and session metrics for each day in d.
    Strictly causal: Day T uses data completed prior to Day T's NY Open (09:30).
    """
    df = d.copy()
    days = sorted(df["day"].unique())
    daily_stats = []

    # 1. First pass: compute completed daily bars
    for day in days:
        day_bars = df[df["day"] == day]
        if len(day_bars) < 60:
            continue
        daily_stats.append({
            "day": day,
            "high": float(day_bars["high"].max()),
            "low": float(day_bars["low"].min()),
            "open": float(day_bars["open"].iloc[0]),
            "close": float(day_bars["close"].iloc[-1]),
            "volume": float(day_bars["tick_volume"].sum()),
            "atr_mean": float(day_bars["atr"].mean()) if "atr" in day_bars.columns else 20.0,
        })

    daily_df = pd.DataFrame(daily_stats)
    if len(daily_df) < 2:
        return {}

    # Shift by 1 to guarantee zero lookahead bias
    daily_df["pdh"] = daily_df["high"].shift(1)
    daily_df["pdl"] = daily_df["low"].shift(1)
    daily_df["pdc"] = daily_df["close"].shift(1)
    daily_df["pdo"] = daily_df["open"].shift(1)
    daily_df["pdr"] = daily_df["pdh"] - daily_df["pdl"]
    daily_df["pd_mid"] = (daily_df["pdh"] + daily_df["pdl"]) / 2.0
    daily_df["pd_upper_quartile"] = daily_df["pdh"] - 0.25 * daily_df["pdr"]
    daily_df["pd_lower_quartile"] = daily_df["pdl"] + 0.25 * daily_df["pdr"]

    # HTF Trend: 20-day SMA vs 5-day SMA on prior completed daily closes
    daily_df["sma20"] = daily_df["close"].shift(1).rolling(20, min_periods=5).mean()
    daily_df["sma5"] = daily_df["close"].shift(1).rolling(5, min_periods=3).mean()

    def get_trend(row):
        c, s20, s5 = row["pdc"], row["sma20"], row["sma5"]
        if pd.isna(s20) or pd.isna(s5):
            return "RANGE"
        if c > s20 and c > s5:
            return "TREND_UP"
        if c < s20 and c < s5:
            return "TREND_DOWN"
        return "RANGE"

    daily_df["htf_trend"] = daily_df.apply(get_trend, axis=1)

    # Volatility Regime: PDR relative to 20-day rolling average PDR
    daily_df["rolling_pdr_avg"] = daily_df["pdr"].rolling(20, min_periods=5).mean()
    daily_df["pdr_ratio"] = daily_df["pdr"] / daily_df["rolling_pdr_avg"].replace(0, np.nan)

    def get_vol_regime(ratio):
        if pd.isna(ratio):
            return "NORMAL"
        if ratio < 0.75:
            return "COMPRESSED"
        if ratio > 1.35:
            return "EXPANDED"
        return "NORMAL"

    daily_df["volatility_regime"] = daily_df["pdr_ratio"].apply(get_vol_regime)

    # 2. Second pass: compute London & Asia session extremes for each trading day
    # London: 03:00 to 09:00 NY (minutes 180 to 540)
    # Early Asia / Globex: 00:00 to 03:00 NY (minutes 0 to 180)
    session_map: Dict[Any, DailyHTFContext] = {}

    for _, row in daily_df.iterrows():
        day = row["day"]
        if pd.isna(row["pdh"]):
            continue

        day_bars = df[df["day"] == day]
        # Open price at NY cash open (09:30 = minute 570)
        ny_open_bars = day_bars[day_bars["local_minute"] >= 570]
        if ny_open_bars.empty:
            continue
        ny_open_price = float(ny_open_bars["open"].iloc[0])

        # Classify opening quartile relative to prior day's range
        pdh = float(row["pdh"])
        pdl = float(row["pdl"])
        pdr = float(row["pdr"])
        pd_mid = float(row["pd_mid"])
        u_q = float(row["pd_upper_quartile"])
        l_q = float(row["pd_lower_quartile"])

        if ny_open_price > pdh:
            quartile = "ABOVE_PDH"
        elif ny_open_price >= u_q:
            quartile = "UPPER_25"
        elif ny_open_price >= pd_mid:
            quartile = "MID_UPPER"
        elif ny_open_price >= l_q:
            quartile = "MID_LOWER"
        elif ny_open_price >= pdl:
            quartile = "LOWER_25"
        else:
            quartile = "BELOW_PDL"

        # London Session Extremes (03:00 to 09:00 NY)
        lon_bars = day_bars[(day_bars["local_minute"] >= 180) & (day_bars["local_minute"] < 540)]
        lon_h = float(lon_bars["high"].max()) if len(lon_bars) >= 10 else None
        lon_l = float(lon_bars["low"].min()) if len(lon_bars) >= 10 else None

        # Asia / Globex Session Extremes (00:00 to 03:00 NY)
        asia_bars = day_bars[(day_bars["local_minute"] >= 0) & (day_bars["local_minute"] < 180)]
        asia_h = float(asia_bars["high"].max()) if len(asia_bars) >= 10 else None
        asia_l = float(asia_bars["low"].min()) if len(asia_bars) >= 10 else None

        session_map[day] = DailyHTFContext(
            day=day,
            pdh=pdh,
            pdl=pdl,
            pdc=float(row["pdc"]),
            pdo=float(row["pdo"]),
            pdr=pdr,
            pd_mid=pd_mid,
            pd_upper_quartile=u_q,
            pd_lower_quartile=l_q,
            open_at_ny=ny_open_price,
            open_quartile=quartile,
            htf_trend=str(row["htf_trend"]),
            pdr_atr_ratio=float(row["pdr_ratio"]) if not pd.isna(row["pdr_ratio"]) else 1.0,
            volatility_regime=str(row["volatility_regime"]),
            london_high=lon_h,
            london_low=lon_l,
            asia_high=asia_h,
            asia_low=asia_l
        )

    return session_map
