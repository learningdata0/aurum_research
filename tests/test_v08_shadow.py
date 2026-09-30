import os
from pathlib import Path
import tempfile
import pandas as pd
import pytest

from src.config import Settings
from src.htf_levels import DailyHTFContext
from src.hypotheses_v08 import HypothesisV08, evaluate_v08_signal
from src.shadow_daemon import ShadowTradingDaemon


def test_h17_hypothesis_definition():
    h = HypothesisV08(
        id="H17",
        name="London Sweep (Range >= 140pts + Swing Target)",
        target_rr=1.8,
        min_london_range=140.0,
        target_mode="swing"
    )
    assert h.id == "H17"
    assert h.min_london_range == 140.0
    assert h.target_mode == "swing"


def test_h17_filter_and_trigger():
    settings = Settings()
    h17 = HypothesisV08(
        id="H17",
        name="London Sweep (Range >= 140pts + Swing Target)",
        target_rr=1.8,
        min_london_range=140.0,
        target_mode="swing"
    )

    # 1. Below 140 points range -> MUST FILTER OUT
    ctx_small = DailyHTFContext(
        day="2026-01-02",
        pdh=30000.0, pdl=29800.0, pdc=29900.0, pdo=29850.0, pdr=200.0,
        pd_mid=29900.0, pd_upper_quartile=29950.0, pd_lower_quartile=29850.0,
        open_at_ny=29900.0, open_quartile="MID_UPPER", htf_trend="RANGE",
        pdr_atr_ratio=1.0, volatility_regime="NORMAL",
        london_high=30050.0, london_low=30000.0, # Range = 50.0 < 140.0
        asia_high=None, asia_low=None
    )
    row = pd.Series({
        "time": "2026-01-02 09:35:00",
        "open": 30040.0, "high": 30060.0, "low": 30030.0, "close": 30035.0,
        "atr": 20.0, "local_minute": 575
    })
    sig = evaluate_v08_signal(row, ctx_small, h17, settings)
    assert sig is None, "Should filter out when London range < 140"

    # 2. Above 140 points range -> MUST TRIGGER
    ctx_qualified = DailyHTFContext(
        day="2026-01-02",
        pdh=30000.0, pdl=29800.0, pdc=29900.0, pdo=29850.0, pdr=200.0,
        pd_mid=29900.0, pd_upper_quartile=29950.0, pd_lower_quartile=29850.0,
        open_at_ny=29900.0, open_quartile="MID_UPPER", htf_trend="RANGE",
        pdr_atr_ratio=1.0, volatility_regime="NORMAL",
        london_high=30150.0, london_low=29950.0, # Range = 200.0 >= 140.0
        asia_high=None, asia_low=None
    )
    # Bearish sweep of London High (high penetrates 30150, closes back at 30140)
    row_sweep = pd.Series({
        "time": "2026-01-02 09:35:00",
        "open": 30148.0, "high": 30155.0, "low": 30130.0, "close": 30140.0,
        "atr": 20.0, "local_minute": 575
    })
    sig_sweep = evaluate_v08_signal(row_sweep, ctx_qualified, h17, settings)
    assert sig_sweep is not None
    direction, entry, sl, tp, setup = sig_sweep
    assert direction == "SELL"
    assert entry == 30140.0
    assert sl > entry
    assert tp == 30050.0 # London Midpoint: (30150 + 29950) / 2
    assert "bearish_sweep" in setup


def test_shadow_daemon_lifecycle(tmp_path):
    log_dir = tmp_path / "reports"
    daemon = ShadowTradingDaemon(
        symbol="US100",
        data_file="data/UT100Roll_M1.csv",
        log_dir=str(log_dir),
        initial_balance=10000.0
    )

    ctx = DailyHTFContext(
        day="2026-01-02",
        pdh=30000.0, pdl=29800.0, pdc=29900.0, pdo=29850.0, pdr=200.0,
        pd_mid=29900.0, pd_upper_quartile=29950.0, pd_lower_quartile=29850.0,
        open_at_ny=29900.0, open_quartile="MID_UPPER", htf_trend="RANGE",
        pdr_atr_ratio=1.0, volatility_regime="NORMAL",
        london_high=30150.0, london_low=29950.0,
        asia_high=None, asia_low=None
    )

    # 1. Open order
    row_entry = pd.Series({
        "time": "2026-01-02 09:35:00",
        "open": 30148.0, "high": 30155.0, "low": 30130.0, "close": 30140.0
    })
    daemon._open_order(
        row_entry, pos=10, direction="SELL",
        entry=30140.0, sl=30160.0, tp=30050.0,
        setup="H17_bearish_sweep", ctx=ctx
    )
    assert daemon.active_order is not None
    assert daemon.active_order["ticket"] == 1001

    # 2. Touch TP
    row_tp = pd.Series({
        "time": "2026-01-02 09:45:00",
        "open": 30080.0, "high": 30085.0, "low": 30045.0, "close": 30050.0
    })
    daemon._update_position(row_tp, pos=20)
    assert daemon.active_order is None
    assert len(daemon.closed_trades) == 1
    t = daemon.closed_trades[0]
    assert t["exit_reason"] == "TP"
    assert t["pnl_cash"] > 0
    assert daemon.balance > 10000.0


def test_shadow_daemon_mt5_sync(tmp_path):
    log_dir = tmp_path / "reports"
    mt5_file = tmp_path / "aurum_shadow_trades.csv"

    # Create mock MT5 file
    df = pd.DataFrame([
        {
            "ticket": 5001, "time": "2026-09-28 10:00:00", "action": "OPEN",
            "symbol": "UT100Roll", "direction": "SELL", "entry": 30100.0,
            "sl": 30120.0, "tp": 30000.0, "pnl": 0.0, "r_mult": 0.0,
            "reason": "", "balance": 10000.0
        },
        {
            "ticket": 5001, "time": "2026-09-28 10:30:00", "action": "CLOSED",
            "symbol": "UT100Roll", "direction": "SELL", "entry": 30100.0,
            "sl": 30120.0, "tp": 30000.0, "pnl": 125.50, "r_mult": 2.50,
            "reason": "TP", "balance": 10125.50
        }
    ])
    df.to_csv(mt5_file, index=False)

    daemon = ShadowTradingDaemon(
        symbol="US100",
        log_dir=str(log_dir)
    )
    synced = daemon.sync_from_mt5(str(mt5_file))
    assert synced is True
    assert daemon.dashboard_file.exists()
    content = daemon.dashboard_file.read_text()
    assert "10,125.50" in content
    assert "Ticket" in content


def test_gold_h17_setup():
    settings = Settings()
    gold_hypo = HypothesisV08(
        id="XAU_H17",
        name="Gold Sweep (Range >= 55pts + Swing Target)",
        target_rr=1.8,
        min_london_range=55.0,
        target_mode="swing"
    )

    # 1. Gold below 55 points range -> FILTERED
    ctx_small = DailyHTFContext(
        day="2026-06-20",
        pdh=4350.0, pdl=4300.0, pdc=4320.0, pdo=4310.0, pdr=50.0,
        pd_mid=4325.0, pd_upper_quartile=4337.5, pd_lower_quartile=4312.5,
        open_at_ny=4320.0, open_quartile="MID_UPPER", htf_trend="RANGE",
        pdr_atr_ratio=1.0, volatility_regime="NORMAL",
        london_high=4330.0, london_low=4300.0,  # Range = 30.0 < 55.0
        asia_high=None, asia_low=None
    )
    row_small = pd.Series({
        "time": "2026-06-20 09:35:00",
        "open": 4331.0, "high": 4335.0, "low": 4328.0, "close": 4329.0,
        "atr": 3.0, "local_minute": 575
    })
    assert evaluate_v08_signal(row_small, ctx_small, gold_hypo, settings) is None

    # 2. Gold above 55 points range -> TRIGGERS
    ctx_qual = DailyHTFContext(
        day="2026-06-20",
        pdh=4350.0, pdl=4250.0, pdc=4300.0, pdo=4280.0, pdr=100.0,
        pd_mid=4300.0, pd_upper_quartile=4325.0, pd_lower_quartile=4275.0,
        open_at_ny=4300.0, open_quartile="MID_UPPER", htf_trend="RANGE",
        pdr_atr_ratio=1.0, volatility_regime="NORMAL",
        london_high=4360.0, london_low=4290.0,  # Range = 70.0 >= 55.0
        asia_high=None, asia_low=None
    )
    # Bearish sweep of London High
    row_sweep = pd.Series({
        "time": "2026-06-20 09:35:00",
        "open": 4358.0, "high": 4363.0, "low": 4350.0, "close": 4355.0,
        "atr": 4.0, "local_minute": 575
    })
    sig = evaluate_v08_signal(row_sweep, ctx_qual, gold_hypo, settings)
    assert sig is not None
    direction, entry, sl, tp, setup = sig
    assert direction == "SELL"
    assert entry == 4355.0
    assert sl > entry
    assert tp == 4325.0  # London midpoint (4360 + 4290) / 2

