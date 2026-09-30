import hashlib
import pandas as pd
import pytest

from src.config import Settings
from src.integrity import compute_dataset_fingerprint
from src.determinism import (
    compute_parameter_hash,
    compute_file_hash,
    create_execution_signature,
    SIGNAL_VERSION,
    EXECUTION_VERSION
)
from src.monte_carlo import run_monte_carlo
from src.hypotheses import FROZEN_HYPOTHESES
from src.walk_forward import run_walk_forward_validation


def test_determinism_parameter_hash():
    s1 = Settings(range_minutes=30, risk_per_trade=0.0025)
    s2 = Settings(range_minutes=30, risk_per_trade=0.0025)
    s3 = Settings(range_minutes=15, risk_per_trade=0.0025)

    h1 = compute_parameter_hash(s1)
    h2 = compute_parameter_hash(s2)
    h3 = compute_parameter_hash(s3)

    assert h1 == h2  # Deterministic!
    assert h1 != h3  # Changes when parameter changes!


def test_execution_signature():
    sig = create_execution_signature("data/US100_M1.csv", Settings())
    assert sig.signal_version == SIGNAL_VERSION
    assert sig.execution_version == EXECUTION_VERSION
    assert len(sig.dataset_hash) == 64
    assert len(sig.parameter_hash) == 64
    assert ":" in sig.short_signature()


def test_analytical_worst_case_monte_carlo():
    trades = pd.DataFrame({
        "pnl_cash": [25.0, -25.0, -25.0, -25.0, -25.0],
        "r_multiple": [1.0, -1.0, -1.0, -1.0, -1.0]
    })
    mc = run_monte_carlo(trades, initial_balance=10000.0, iterations=100, risk_per_trade=0.0025)
    # 4 losses out of 5 trades.
    # Analytical worst-case: 1 - (1 - 0.0025)^4 = 1 - 0.990037 = 0.996% (approx 1%)
    assert mc["loss_trades_count"] == 4
    assert round(mc["analytical_worst_case_dd_pct"], 2) == 1.0
    assert "governance_note" in mc
    assert "Does NOT predict" in mc["governance_note"]


def test_walk_forward_engine():
    # Mock 40 days of data to test 20 train / 10 test rolling windows
    dates = pd.date_range("2026-01-01 14:30", periods=40, freq="D", tz="UTC")
    rows = []
    for d in dates:
        for m in range(60):
            t = d + pd.Timedelta(minutes=m)
            rows.append({
                "time": t,
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
                "tick_volume": 100
            })
    df_mock = pd.DataFrame(rows)
    h = FROZEN_HYPOTHESES[0]
    res = run_walk_forward_validation(df_mock, h, train_days=20, test_days=10)
    assert res.total_windows >= 1
    assert res.verdict in ("PASS", "WATCH", "FAIL", "INSUFFICIENT_N")
    assert isinstance(res.windows_df, pd.DataFrame)
