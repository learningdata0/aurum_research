import numpy as np
import pandas as pd
import pytest

from src.config import Settings
from src.data import prepare_data
from src.research_gate import ResearchGateCriteria, evaluate_against_research_gate
from src.shadow_engine import ShadowExecutionEngine, ShadowOrder
from src.walk_forward import WalkForwardResult


def test_research_gate_evaluation():
    # Mock a passing WalkForwardResult
    wf_pass = WalkForwardResult(
        hyp_id="H2",
        symbol="US100",
        hypothesis_name="US100 Sweep Reclaim",
        total_windows=10,
        positive_oos_windows=7,
        oos_win_rate_pct=70.0,
        total_is_trades=60,
        total_oos_trades=45,
        overall_is_pf=2.1,
        overall_oos_pf=1.85,
        overall_is_expectancy_R=0.75,
        overall_oos_expectancy_R=0.65,
        wfe_ratio=0.87,
        verdict="PASS",
        windows_df=pd.DataFrame()
    )

    ev_pass = evaluate_against_research_gate(wf_pass)
    assert ev_pass.verdict == "PASS"
    assert ev_pass.score_pct == 100.0

    # Mock a failing result (too few trades, negative expectancy)
    wf_fail = WalkForwardResult(
        hyp_id="H6",
        symbol="US30",
        hypothesis_name="US30 Broad OR",
        total_windows=4,
        positive_oos_windows=1,
        oos_win_rate_pct=25.0,
        total_is_trades=30,
        total_oos_trades=13,
        overall_is_pf=1.0,
        overall_oos_pf=0.85,
        overall_is_expectancy_R=0.10,
        overall_oos_expectancy_R=-0.08,
        wfe_ratio=0.0,
        verdict="FAIL",
        windows_df=pd.DataFrame()
    )

    ev_fail = evaluate_against_research_gate(wf_fail)
    assert ev_fail.verdict == "FAIL"


def test_shadow_execution_engine(tmp_path):
    settings = Settings(session_start_local="09:30", session_end_local="11:30", range_minutes=30)
    shadow = ShadowExecutionEngine("TEST", settings, "sweep_reclaim", log_dir=str(tmp_path))

    # Generate 150 bars of mock session data
    t = pd.date_range("2026-01-05 14:00", periods=150, freq="min", tz="UTC")
    base = 100.0 + np.sin(np.linspace(0, 10, 150)) * 2.0
    df = pd.DataFrame({
        "time": t,
        "open": base,
        "high": base + 0.30,
        "low": base - 0.30,
        "close": base,
        "tick_volume": 100
    })
    d = prepare_data(df, settings.atr_period, settings.timezone)
    meta = shadow.engine.build_sessions(d)

    for pos in range(len(d)):
        row = d.iloc[pos]
        recent = d.iloc[max(0, pos - 20):pos + 1]
        meta_row = meta.loc[pos] if pos in meta.index else None
        shadow.process_candle(row, pos, meta_row, recent)

    summary = shadow.get_summary()
    assert "trades" in summary
    assert "final_balance" in summary
    assert summary["final_balance"] > 0
