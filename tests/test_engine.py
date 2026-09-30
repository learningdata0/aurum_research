import numpy as np
import pandas as pd
from src.config import Settings
from src.data import prepare_data
from src.regime import MarketRegime, MarketRegimeDetector
from src.engine import SessionEngine, run_backtest
from src.monte_carlo import run_monte_carlo


def test_prepare_data_ny_timezone():
    n = 100
    t = pd.date_range("2026-01-05 14:00", periods=n, freq="min", tz="UTC")
    close = 100.0 + pd.Series(range(n)) * 0.05
    df = pd.DataFrame({
        "time": t,
        "open": close,
        "high": close + 0.10,
        "low": close - 0.10,
        "close": close,
        "tick_volume": 100
    })
    d = prepare_data(df, atr_period=14, target_timezone="America/New_York")
    assert "atr" in d.columns
    assert "adx" in d.columns
    assert "vwap" in d.columns
    assert "local_minute" in d.columns
    assert str(d["time"].dt.tz) == "America/New_York"
    # 14:00 UTC on Jan 5 is 09:00 EST (New York) -> local_minute = 9 * 60 = 540
    assert d["local_minute"].iloc[0] == 540


def test_regime_detector():
    detector = MarketRegimeDetector(min_healthy_score=65.0, min_unstable_score=40.0)
    # Mock ranging bar: low ADX, close near VWAP, normal candle range
    row_range = pd.Series({
        "atr": 10.0,
        "adx": 16.0,
        "vwap_dist": 0.5,
        "candle_range": 12.0,
        "close": 90.0,
    })
    state_range = detector.evaluate(row_range, range_high=100.0, range_low=80.0)
    assert state_range.regime == MarketRegime.HEALTHY_RANGE
    assert state_range.score >= 65.0
    assert state_range.allows_mean_reversion() is True
    assert state_range.allows_sweep_reclaim() is True

    # Mock trending bar: high ADX, large distance from VWAP, huge candle range
    row_trend = pd.Series({
        "atr": 10.0,
        "adx": 38.0,
        "pos_di": 30.0,
        "neg_di": 10.0,
        "vwap_dist": 3.5,
        "candle_range": 35.0,
        "close": 115.0,
    })
    state_trend = detector.evaluate(row_trend, range_high=100.0, range_low=80.0)
    assert state_trend.regime == MarketRegime.TREND_UP
    assert state_trend.is_trend() is True
    assert state_trend.allows_mean_reversion() is False
    assert state_trend.allows_breakout("BUY") is True
    assert state_trend.allows_breakout("SELL") is False


def test_boundary_reversion_no_runaway_entry():
    """
    Ensures that Boundary Reversion NEVER enters if price is far away from Range High
    (fixing the bug where a SELL entered 216 points above Range High).
    """
    settings = Settings(session_start_local="09:30", session_end_local="12:00", range_minutes=30)
    engine = SessionEngine(settings, "boundary_reversion")

    # Range High = 100, Range Low = 90 (Width = 10, ATR = 2)
    # Candle is at 120 (20 points above RH, way outside zone)
    row_runaway = pd.Series({
        "open": 121.0,
        "high": 122.0,
        "low": 119.5,
        "close": 120.0,
        "atr": 2.0,
        "adx": 18.0,
        "vwap_dist": 0.5,
        "candle_range": 2.5,
        "upper_wick": 1.0,
        "lower_wick": 0.5,
    })
    d_mock = pd.DataFrame([row_runaway])
    sig = engine.evaluate_signal(d_mock, pos=0, rh=100.0, rl=90.0)
    assert sig is None  # Must reject runaway entry!


def test_monte_carlo():
    trades = pd.DataFrame({
        "pnl_cash": [25.0, -25.0, 30.0, -25.0, 50.0, -25.0],
        "r_multiple": [1.0, -1.0, 1.2, -1.0, 2.0, -1.0]
    })
    mc = run_monte_carlo(trades, initial_balance=10000.0, iterations=100)
    assert mc["iterations"] == 100
    assert "mean_expectancy_R" in mc
    assert "median_resampled_dd_pct" in mc
    assert "analytical_worst_case_dd_pct" in mc
    assert mc["bootstrap_positive_finish_pct"] > 0


def test_full_backtest_composite_regime():
    # Generate 180 bars of NY session (09:00 to 12:00 local time)
    t = pd.date_range("2026-01-05 14:00", periods=180, freq="min", tz="UTC")
    base = 100.0 + np.sin(np.linspace(0, 10, 180)) * 2.0
    df = pd.DataFrame({
        "time": t,
        "open": base,
        "high": base + 0.30,
        "low": base - 0.30,
        "close": base,
        "tick_volume": 100
    })
    trades, stats = run_backtest(df, "TEST", Settings(), "composite_regime")
    assert stats["final_balance"] >= 0
    assert isinstance(trades, pd.DataFrame)
