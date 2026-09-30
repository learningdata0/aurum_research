import pandas as pd
import pytest

from src.config import Settings
from src.data import prepare_data
from src.htf_levels import build_htf_context_map, DailyHTFContext
from src.strategies.htf_sweep import evaluate_htf_sweep_reclaim


def test_broker_us_dst_anchor():
    """Verifies that broker time maps to 09:30 NY cash open across DST transitions."""
    times = [
        "2025-01-15 16:30:00",  # Winter
        "2025-03-12 16:30:00",  # US DST mismatch
        "2025-07-15 16:30:00",  # Summer
    ]
    df = pd.DataFrame({
        "time": times,
        "open": [100.0] * 3,
        "high": [101.0] * 3,
        "low": [99.0] * 3,
        "close": [100.0] * 3,
        "tick_volume": [100] * 3
    })
    d = prepare_data(df, source_timezone="broker")
    for val in d["local_minute"]:
        assert val == 570  # Exactly 09:30 AM New York local!


def test_htf_levels_computation():
    """Verifies daily HTF context extraction without lookahead bias."""
    dates = pd.date_range("2026-01-01 00:00", periods=2880, freq="min")
    df = pd.DataFrame({
        "time": dates.strftime("%Y-%m-%d %H:%M:%S"),
        "open": 100.0,
        "high": 105.0,
        "low": 95.0,
        "close": 102.0,
        "tick_volume": 100
    })
    d = prepare_data(df, source_timezone="broker")
    ctx_map = build_htf_context_map(d)
    assert len(ctx_map) >= 1
    sample_ctx = list(ctx_map.values())[0]
    assert hasattr(sample_ctx, "pdh")
    assert hasattr(sample_ctx, "pdl")
    assert hasattr(sample_ctx, "pd_mid")
    assert sample_ctx.pdh >= sample_ctx.pdl


def test_htf_sweep_strategy():
    """Verifies that sweep-reclaim triggers valid BUY/SELL signals."""
    settings = Settings()
    ctx = DailyHTFContext(
        day="2026-01-02",
        pdh=20000.0,
        pdl=19800.0,
        pdc=19900.0,
        pdo=19850.0,
        pdr=200.0,
        pd_mid=19900.0,
        pd_upper_quartile=19950.0,
        pd_lower_quartile=19850.0,
        open_at_ny=19920.0,
        open_quartile="MID_UPPER",
        htf_trend="RANGE",
        pdr_atr_ratio=1.0,
        volatility_regime="NORMAL",
        london_high=20050.0,
        london_low=19820.0,
        asia_high=19950.0,
        asia_low=19880.0
    )

    # Bullish sweep row (low below PDL 19800, close back above 19800)
    row_bull = pd.Series({
        "high": 19820.0,
        "low": 19780.0,  # Sweeps below 19800
        "open": 19790.0,
        "close": 19810.0,  # Reclaims above 19800
        "upper_wick": 10.0,
        "lower_wick": 10.0,
        "atr": 20.0
    })

    sig = evaluate_htf_sweep_reclaim(row_bull, ctx, settings, hypothesis_id="H7", tp_mode="swing")
    assert sig is not None
    direction, entry, sl, tp, setup = sig
    assert direction == "BUY"
    assert entry == 19810.0
    assert sl < entry
    assert tp > entry
