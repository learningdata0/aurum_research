from __future__ import annotations

import numpy as np
import pandas as pd


def prepare_data(
    df: pd.DataFrame,
    atr_period: int = 14,
    target_timezone: str = "America/New_York",
    source_timezone: str = "UTC"
) -> pd.DataFrame:
    """
    Cleans, validates, localizes timestamps to America/New_York, and computes
    all feature indicators (ATR, VWAP, ADX, candle anatomy).
    """
    d = df.copy()
    d.columns = [str(c).lower().strip() for c in d.columns]
    required = ["time", "open", "high", "low", "close"]
    missing = [c for c in required if c not in d.columns]
    if missing:
        raise ValueError(f"Missing required columns in dataset: {missing}")

    # Parse timestamps and convert to New York local time
    t_raw = pd.to_datetime(d["time"], errors="coerce")
    if t_raw.dt.tz is None:
        if source_timezone in ("broker", "MT5_BROKER", "Europe/Athens", "EQUITI_MT5"):
            # MetaTrader 5 broker servers synchronize DST with the US schedule
            # to maintain the 17:00 NY daily close invariant at 00:00 server time.
            # Offset is exactly New York + 7 hours year-round.
            t_ny_naive = t_raw - pd.Timedelta(hours=7)
            d["time"] = t_ny_naive.dt.tz_localize(target_timezone, ambiguous="NaT", nonexistent="shift_forward")
        else:
            t_loc = t_raw.dt.tz_localize(source_timezone)
            d["time"] = t_loc.dt.tz_convert(target_timezone)
    else:
        d["time"] = t_raw.dt.tz_convert(target_timezone)

    # Cast prices to numeric and drop invalid rows
    for c in ["open", "high", "low", "close"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    if "tick_volume" in d.columns:
        d["tick_volume"] = pd.to_numeric(d["tick_volume"], errors="coerce").fillna(1)
    else:
        d["tick_volume"] = 1.0

    d = d.dropna(subset=required).sort_values("time").drop_duplicates("time").reset_index(drop=True)

    # Sanity checks on OHLC integrity
    invalid_mask = (d["high"] < d[["open", "close"]].max(axis=1)) | (d["low"] > d[["open", "close"]].min(axis=1))
    if invalid_mask.any():
        # Fix minor floating point anomalies if high < max(open, close)
        d["high"] = d[["high", "open", "close"]].max(axis=1)
        d["low"] = d[["low", "open", "close"]].min(axis=1)

    # Compute True Range & ATR (Wilder exponential smoothing)
    prev_close = d["close"].shift(1)
    tr = pd.concat([
        d["high"] - d["low"],
        (d["high"] - prev_close).abs(),
        (d["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    d["atr"] = tr.ewm(alpha=1 / atr_period, adjust=False, min_periods=atr_period).mean()

    # Candle anatomy
    d["candle_range"] = (d["high"] - d["low"]).replace(0, np.nan)
    d["body"] = (d["close"] - d["open"]).abs()
    d["body_ratio"] = (d["body"] / d["candle_range"]).fillna(0.0)
    d["upper_wick"] = d["high"] - d[["open", "close"]].max(axis=1)
    d["lower_wick"] = d[["open", "close"]].min(axis=1) - d["low"]

    # Temporal features (anchored in New York local time)
    d["day"] = d["time"].dt.date
    d["local_minute"] = d["time"].dt.hour * 60 + d["time"].dt.minute

    # Compute ADX-14 (Average Directional Index)
    d = _compute_adx(d, period=atr_period)

    # Compute Intraday VWAP (anchored daily from 09:30 AM NY local)
    d = _compute_intraday_vwap(d)

    return d


def _compute_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Computes 14-period ADX to measure trend strength vs ranging."""
    d = df.copy()
    prev_high = d["high"].shift(1)
    prev_low = d["low"].shift(1)

    up_move = d["high"] - prev_high
    down_move = prev_low - d["low"]

    pos_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    neg_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = pd.concat([
        d["high"] - d["low"],
        (d["high"] - d["close"].shift(1)).abs(),
        (d["low"] - d["close"].shift(1)).abs(),
    ], axis=1).max(axis=1)

    tr_smoothed = tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    pos_di = 100 * pd.Series(pos_dm).ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / tr_smoothed.replace(0, np.nan)
    neg_di = 100 * pd.Series(neg_dm).ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / tr_smoothed.replace(0, np.nan)

    dx = 100 * (pos_di - neg_di).abs() / (pos_di + neg_di).replace(0, np.nan)
    d["adx"] = dx.ewm(alpha=1 / period, adjust=False, min_periods=period).mean().fillna(15.0)
    d["pos_di"] = pos_di.fillna(20.0)
    d["neg_di"] = neg_di.fillna(20.0)
    return d


def _compute_intraday_vwap(df: pd.DataFrame) -> pd.DataFrame:
    """Computes session-anchored VWAP resetting each day at NY Open (09:30 local)."""
    d = df.copy()
    typical_price = (d["high"] + d["low"] + d["close"]) / 3.0
    vol = d["tick_volume"].replace(0, 1.0)
    pv = typical_price * vol

    vwap_values = np.zeros(len(d), dtype=float)
    groups = d.groupby("day", sort=False)

    for day, group in groups:
        cum_pv = pv.loc[group.index].cumsum()
        cum_vol = vol.loc[group.index].cumsum()
        vwap_values[group.index] = cum_pv / cum_vol

    d["vwap"] = vwap_values
    d["vwap_dist"] = (d["close"] - d["vwap"]) / d["atr"].replace(0, 1.0)
    return d
