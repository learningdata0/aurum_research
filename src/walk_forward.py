from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple
import pandas as pd

from .config import Settings
from .determinism import create_execution_signature
from .engine import run_backtest
from .hypotheses import Hypothesis, create_hypothesis_settings, FROZEN_HYPOTHESES


@dataclass
class WalkForwardResult:
    hyp_id: str
    symbol: str
    hypothesis_name: str
    total_windows: int
    positive_oos_windows: int
    oos_win_rate_pct: float
    total_is_trades: int
    total_oos_trades: int
    overall_is_pf: float
    overall_oos_pf: float
    overall_is_expectancy_R: float
    overall_oos_expectancy_R: float
    wfe_ratio: float
    verdict: str  # PASS / WATCH / FAIL
    windows_df: pd.DataFrame


def run_walk_forward_validation(
    df: pd.DataFrame,
    hyp: Hypothesis,
    base_settings: Settings | None = None,
    train_days: int = 20,
    test_days: int = 10,
    min_oos_trades_per_window: int = 2
) -> WalkForwardResult:
    """
    AURUM v0.5 Out-of-Sample Walk-Forward Engine:
    Executes chronological TRAIN -> LOCK -> OOS -> NEXT WINDOW evaluation.
    Parameters are FROZEN during OOS. No curve-fitting or parameter readjustment.
    """
    base = base_settings or Settings()
    s = create_hypothesis_settings(base, hyp)

    d_clean = df.copy()
    d_clean["time"] = pd.to_datetime(d_clean["time"], errors="coerce")
    days = sorted(d_clean["time"].dt.date.dropna().unique())

    windows = []
    window_idx = 1
    start_pos = 0

    # If dataset has fewer days than train + test, use a single 60/40 chronological split
    if len(days) < (train_days + test_days):
        split_point = int(len(days) * 0.60)
        tr_days = set(days[:split_point])
        te_days = set(days[split_point:])

        df_train = df[d_clean["time"].dt.date.isin(tr_days)]
        df_test = df[d_clean["time"].dt.date.isin(te_days)]

        _, stats_is = run_backtest(df_train, hyp.symbol, s, hyp.strategy)
        _, stats_oos = run_backtest(df_test, hyp.symbol, s, hyp.strategy)

        is_exp = stats_is["expectancy_R"]
        oos_exp = stats_oos["expectancy_R"]
        wfe = round(oos_exp / is_exp, 2) if is_exp > 0 else 0.0

        if oos_exp > 0.10 and stats_oos["profit_factor"] >= 1.15:
            win_verdict = "PASS"
        elif oos_exp >= -0.05:
            win_verdict = "WATCH"
        else:
            win_verdict = "FAIL"

        win_record = {
            "window": 1,
            "train_period": f"{min(tr_days)} to {max(tr_days)} ({len(tr_days)}d)",
            "oos_period": f"{min(te_days)} to {max(te_days)} ({len(te_days)}d)",
            "is_trades": stats_is["trades"],
            "is_pf": stats_is["profit_factor"],
            "is_exp_R": is_exp,
            "oos_trades": stats_oos["trades"],
            "oos_pf": stats_oos["profit_factor"],
            "oos_exp_R": oos_exp,
            "wfe": wfe,
            "verdict": win_verdict
        }
        windows_df = pd.DataFrame([win_record])
        return WalkForwardResult(
            hyp_id=hyp.id,
            symbol=hyp.symbol,
            hypothesis_name=hyp.name,
            total_windows=1,
            positive_oos_windows=1 if oos_exp > 0 else 0,
            oos_win_rate_pct=100.0 if oos_exp > 0 else 0.0,
            total_is_trades=stats_is["trades"],
            total_oos_trades=stats_oos["trades"],
            overall_is_pf=stats_is["profit_factor"],
            overall_oos_pf=stats_oos["profit_factor"],
            overall_is_expectancy_R=is_exp,
            overall_oos_expectancy_R=oos_exp,
            wfe_ratio=wfe,
            verdict=win_verdict,
            windows_df=windows_df
        )

    # Rolling window loop
    while start_pos + train_days + test_days <= len(days):
        tr_days = set(days[start_pos:start_pos + train_days])
        te_days = set(days[start_pos + train_days:start_pos + train_days + test_days])

        df_train = df[d_clean["time"].dt.date.isin(tr_days)]
        df_test = df[d_clean["time"].dt.date.isin(te_days)]

        _, stats_is = run_backtest(df_train, hyp.symbol, s, hyp.strategy)
        _, stats_oos = run_backtest(df_test, hyp.symbol, s, hyp.strategy)

        is_exp = stats_is["expectancy_R"]
        oos_exp = stats_oos["expectancy_R"]
        wfe = round(oos_exp / is_exp, 2) if is_exp > 0 else 0.0

        if stats_oos["trades"] >= min_oos_trades_per_window:
            if oos_exp > 0.05 and stats_oos["profit_factor"] >= 1.10:
                verdict = "PASS"
            elif oos_exp >= -0.05:
                verdict = "WATCH"
            else:
                verdict = "FAIL"
        else:
            verdict = "INSUFFICIENT_N"

        windows.append({
            "window": window_idx,
            "train_period": f"{min(tr_days)} to {max(tr_days)} ({len(tr_days)}d)",
            "oos_period": f"{min(te_days)} to {max(te_days)} ({len(te_days)}d)",
            "is_trades": stats_is["trades"],
            "is_pf": stats_is["profit_factor"],
            "is_exp_R": is_exp,
            "oos_trades": stats_oos["trades"],
            "oos_pf": stats_oos["profit_factor"],
            "oos_exp_R": oos_exp,
            "wfe": wfe,
            "verdict": verdict
        })

        start_pos += test_days
        window_idx += 1

    win_df = pd.DataFrame(windows)

    # Aggregate evaluation
    valid_oos = win_df[win_df["verdict"] != "INSUFFICIENT_N"]
    pos_windows = len(valid_oos[valid_oos["oos_exp_R"] > 0])
    total_valid = max(1, len(valid_oos))
    pos_rate = round(100.0 * pos_windows / total_valid, 1)

    avg_is_pf = round(win_df["is_pf"].mean(), 2)
    avg_oos_pf = round(win_df["oos_pf"].mean(), 2)
    avg_is_exp = round(win_df["is_exp_R"].mean(), 2)
    avg_oos_exp = round(win_df["oos_exp_R"].mean(), 2)
    overall_wfe = round(avg_oos_exp / avg_is_exp, 2) if avg_is_exp > 0 else 0.0

    if pos_rate >= 60.0 and avg_oos_exp > 0.05:
        overall_verdict = "PASS"
    elif pos_rate >= 40.0 and avg_oos_exp >= -0.05:
        overall_verdict = "WATCH"
    else:
        overall_verdict = "FAIL"

    return WalkForwardResult(
        hyp_id=hyp.id,
        symbol=hyp.symbol,
        hypothesis_name=hyp.name,
        total_windows=len(windows),
        positive_oos_windows=pos_windows,
        oos_win_rate_pct=pos_rate,
        total_is_trades=int(win_df["is_trades"].sum()),
        total_oos_trades=int(win_df["oos_trades"].sum()),
        overall_is_pf=avg_is_pf,
        overall_oos_pf=avg_oos_pf,
        overall_is_expectancy_R=avg_is_exp,
        overall_oos_expectancy_R=avg_oos_exp,
        wfe_ratio=overall_wfe,
        verdict=overall_verdict,
        windows_df=win_df
    )
