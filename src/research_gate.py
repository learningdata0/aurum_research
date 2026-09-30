from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List
import pandas as pd


@dataclass(frozen=True)
class ResearchGateCriteria:
    """
    Objective Pre-Committed Research Gate Criteria for AURUM v0.6.
    These thresholds are frozen BEFORE examining multi-year data.
    No post-hoc goalpost moving is permitted.
    """
    min_oos_trades: int = 30
    min_oos_expectancy_R: float = 0.20
    min_oos_profit_factor: float = 1.30
    min_positive_oos_windows_pct: float = 60.0
    max_allowed_drawdown_pct: float = 3.50
    min_wfe_ratio: float = 0.50


@dataclass
class GateEvaluation:
    hyp_id: str
    symbol: str
    strategy: str
    verdict: str  # PASS / WATCH / FAIL
    score_pct: float
    checklist: Dict[str, Dict[str, Any]]
    recommendation: str


def evaluate_against_research_gate(
    wf_result: Any,
    criteria: ResearchGateCriteria | None = None
) -> GateEvaluation:
    """
    Evaluates a Walk-Forward Result strictly against the pre-committed Research Gate.
    """
    c = criteria or ResearchGateCriteria()

    trades_ok = wf_result.total_oos_trades >= c.min_oos_trades
    exp_ok = wf_result.overall_oos_expectancy_R >= c.min_oos_expectancy_R
    pf_ok = wf_result.overall_oos_pf >= c.min_oos_profit_factor
    pos_windows_ok = wf_result.oos_win_rate_pct >= c.min_positive_oos_windows_pct
    wfe_ok = wf_result.wfe_ratio >= c.min_wfe_ratio

    checklist = {
        "Sample Size (OOS Trades)": {
            "required": f">= {c.min_oos_trades}",
            "actual": wf_result.total_oos_trades,
            "passed": trades_ok
        },
        "OOS Expectancy R": {
            "required": f">= +{c.min_oos_expectancy_R}R",
            "actual": f"{wf_result.overall_oos_expectancy_R:+.2f}R",
            "passed": exp_ok
        },
        "OOS Profit Factor": {
            "required": f">= {c.min_oos_profit_factor}",
            "actual": wf_result.overall_oos_pf,
            "passed": pf_ok
        },
        "Positive OOS Windows %": {
            "required": f">= {c.min_positive_oos_windows_pct}%",
            "actual": f"{wf_result.oos_win_rate_pct}%",
            "passed": pos_windows_ok
        },
        "Walk-Forward Efficiency": {
            "required": f">= {c.min_wfe_ratio}",
            "actual": wf_result.wfe_ratio,
            "passed": wfe_ok
        }
    }

    passed_count = sum(1 for item in checklist.values() if item["passed"])
    score_pct = round(100.0 * passed_count / len(checklist), 1)

    if passed_count == len(checklist):
        verdict = "PASS"
        recommendation = "Promote to v0.6 Shadow Execution (Live Forward Paper Tracking)."
    elif exp_ok and pf_ok and passed_count >= 3:
        verdict = "WATCH"
        recommendation = "Keep on Watchlist. Requires expanded sample size across multi-year data."
    else:
        verdict = "FAIL"
        recommendation = "Reject candidate. Do not trade in live or shadow mode."

    return GateEvaluation(
        hyp_id=wf_result.hyp_id,
        symbol=wf_result.symbol,
        strategy=wf_result.hypothesis_name,
        verdict=verdict,
        score_pct=score_pct,
        checklist=checklist,
        recommendation=recommendation
    )


def print_gate_evaluation(ev: GateEvaluation):
    print(f"\n=======================================================")
    print(f"AURUM RESEARCH GATE AUDIT: [{ev.hyp_id}] {ev.symbol}")
    print(f"VERDICT: >>> {ev.verdict} <<< (Score: {ev.score_pct}%)")
    print(f"Recommendation: {ev.recommendation}")
    print(f"-------------------------------------------------------")
    for criterion, data in ev.checklist.items():
        status_icon = "✅ PASS" if data["passed"] else "❌ FAIL"
        print(f"  {status_icon} | {criterion:<28} | Required: {data['required']:<10} | Actual: {data['actual']}")
    print(f"=======================================================\n")
