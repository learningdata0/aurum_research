import json
from unittest.mock import MagicMock, patch
import pandas as pd
import pytest

from src.config import Settings
from src.hypotheses import FROZEN_HYPOTHESES, create_hypothesis_settings, run_single_hypothesis
from src.twelvedata_fetcher import TwelveDataFetcher, SYMBOL_MAP


def test_frozen_hypotheses_definitions():
    assert len(FROZEN_HYPOTHESES) == 6
    ids = [h.id for h in FROZEN_HYPOTHESES]
    assert ids == ["H1", "H2", "H3", "H4", "H5", "H6"]

    h1 = FROZEN_HYPOTHESES[0]
    assert h1.symbol == "US100"
    assert h1.strategy == "composite_regime"
    assert h1.range_minutes == 30
    assert h1.session_duration_minutes == 120

    s = create_hypothesis_settings(Settings(), h1)
    assert s.range_minutes == 30
    assert s.session_end_local == "11:30"


def test_twelvedata_symbol_mapping():
    fetcher = TwelveDataFetcher(api_key="mock_key")
    assert fetcher.get_mapped_symbol("US100") == "QQQ"
    assert fetcher.get_mapped_symbol("US30") == "DIA"
    assert fetcher.get_mapped_symbol("XAUUSD") == "XAU/USD"
    assert fetcher.get_mapped_symbol("AAPL") == "AAPL"


def test_twelvedata_missing_key_raises():
    fetcher = TwelveDataFetcher(api_key="")
    fetcher.api_key = ""
    with pytest.raises(ValueError, match="Missing Twelve Data API Key"):
        fetcher.fetch_price("US100")


def test_twelvedata_parse_time_series():
    mock_response = {
        "status": "ok",
        "meta": {"symbol": "QQQ"},
        "values": [
            {
                "datetime": "2026-09-28 09:31:00",
                "open": "500.10",
                "high": "500.50",
                "low": "500.00",
                "close": "500.40",
                "volume": "12000"
            },
            {
                "datetime": "2026-09-28 09:30:00",
                "open": "500.00",
                "high": "500.20",
                "low": "499.80",
                "close": "500.10",
                "volume": "15000"
            }
        ]
    }

    fetcher = TwelveDataFetcher(api_key="test_key")
    with patch.object(fetcher, "_request", return_value=mock_response):
        df = fetcher.fetch_time_series("US100", interval="1min")
        assert len(df) == 2
        assert list(df.columns) == ["time", "open", "high", "low", "close", "tick_volume"]
        # Ensure chronological order (oldest first)
        assert df["time"].iloc[0] < df["time"].iloc[1]
        assert df["close"].iloc[0] == 500.10
        assert df["close"].iloc[1] == 500.40


def test_run_hypothesis_on_mock_data():
    t = pd.date_range("2026-01-05 14:30", periods=120, freq="min", tz="UTC")
    df = pd.DataFrame({
        "time": t,
        "open": 100.0,
        "high": 100.5,
        "low": 99.5,
        "close": 100.0,
        "tick_volume": 100
    })
    h = FROZEN_HYPOTHESES[0]
    trades, stats = run_single_hypothesis(h, df)
    assert isinstance(trades, pd.DataFrame)
    assert "trades" in stats
