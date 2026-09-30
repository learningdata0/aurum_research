from __future__ import annotations

from pathlib import Path
import pytest
from src.temporal_profiler import TemporalProfiler, INTRADAY_WINDOWS


def test_temporal_profiler():
    p = TemporalProfiler("data/UT100Roll_M1.csv", "US100")
    assert len(INTRADAY_WINDOWS) == 5
    res = p.analyze_windows()
    assert res["symbol"] == "US100"
    assert "windows" in res
    assert len(res["windows"]) >= 3
    assert "avg_range_pts" in res["windows"][0]
