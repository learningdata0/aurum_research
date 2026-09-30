from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple
import pandas as pd

from .config import Settings, load_settings
from .engine import run_backtest


@dataclass(frozen=True)
class Hypothesis:
    id: str
    symbol: str
    name: str
    strategy: str
    range_minutes: int
    session_duration_minutes: int
    description: str


# AURUM v0.4 Hypothesis Lock: 6 Frozen Hypotheses
# No infinite optimization or p-hacking; these 6 hypotheses are frozen for out-of-sample benchmarking.
FROZEN_HYPOTHESES: List[Hypothesis] = [
    Hypothesis(
        id="H1",
        symbol="US100",
        name="US100 Composite Regime (30m OR / 120m Session)",
        strategy="composite_regime",
        range_minutes=30,
        session_duration_minutes=120,
        description="Dynamic state machine routing between Sweep-Reclaim and Breakout-Retest."
    ),
    Hypothesis(
        id="H2",
        symbol="US100",
        name="US100 Sweep → Reclaim (30m OR / 90m Session)",
        strategy="sweep_reclaim",
        range_minutes=30,
        session_duration_minutes=90,
        description="Liquidity absorption at Opening Range boundaries after false expansion."
    ),
    Hypothesis(
        id="H3",
        symbol="US100",
        name="US100 Breakout → Retest (30m OR / 120m Session)",
        strategy="breakout_retest",
        range_minutes=30,
        session_duration_minutes=120,
        description="Patient trend continuation entering only after pullback retest holds."
    ),
    Hypothesis(
        id="H4",
        symbol="XAUUSD",
        name="XAUUSD Short OR Boundary Reversion (5m OR / 60m Session)",
        strategy="boundary_reversion",
        range_minutes=5,
        session_duration_minutes=60,
        description="Fast opening range boundary bounce during early Gold NY liquidity."
    ),
    Hypothesis(
        id="H5",
        symbol="XAUUSD",
        name="XAUUSD Short OR Composite Regime (5m OR / 60m Session)",
        strategy="composite_regime",
        range_minutes=5,
        session_duration_minutes=60,
        description="Fast opening range composite regime dynamic routing for Gold."
    ),
    Hypothesis(
        id="H6",
        symbol="US30",
        name="US30 Broad OR Sweep → Reclaim (60m OR / 120m Session)",
        strategy="sweep_reclaim",
        range_minutes=60,
        session_duration_minutes=120,
        description="Institutional sweep-reclaim after 60m Dow price discovery."
    ),
]


def create_hypothesis_settings(base_settings: Settings, hyp: Hypothesis) -> Settings:
    s = copy.deepcopy(base_settings)
    s.range_minutes = hyp.range_minutes
    start_m = 9 * 60 + 30
    end_m = start_m + hyp.session_duration_minutes
    end_h = end_m // 60
    end_min = end_m % 60
    s.session_end_local = f"{end_h:02d}:{end_min:02d}"
    return s


def run_single_hypothesis(
    hyp: Hypothesis,
    df: pd.DataFrame,
    base_settings: Settings | None = None
) -> Tuple[pd.DataFrame, dict]:
    s = create_hypothesis_settings(base_settings or Settings(), hyp)
    trades, stats = run_backtest(df, hyp.symbol, s, hyp.strategy)
    return trades, stats


def run_all_locked_hypotheses(
    data_dir: str = "data",
    base_settings: Settings | None = None
) -> Tuple[pd.DataFrame, Dict[str, pd.DataFrame]]:
    """
    Runs all 6 locked hypotheses against available CSV datasets in data_dir.
    Returns:
      (summary_df, {hyp_id: trades_df})
    """
    base = base_settings or Settings()
    results = []
    trades_dict = {}

    for hyp in FROZEN_HYPOTHESES:
        csv_path = Path(data_dir) / f"{hyp.symbol}_M1.csv"
        if not csv_path.exists():
            aliases = {
                "US100": ["UT100Roll_M1.csv", "USTECRoll_M1.csv"],
                "US30": ["US30Roll_M1.csv"],
                "XAUUSD": ["XAUUSD_M1.csv"]
            }
            found = False
            for alt in aliases.get(hyp.symbol, []):
                alt_p = Path(data_dir) / alt
                if alt_p.exists():
                    csv_path = alt_p
                    found = True
                    break
            if not found:
                print(f"Warning: {csv_path} not found. Skipping {hyp.id} ({hyp.symbol}).")
                continue

        df = pd.read_csv(csv_path)
        trades, stats = run_single_hypothesis(hyp, df, base)
        trades_dict[hyp.id] = trades

        results.append({
            "hyp_id": hyp.id,
            "symbol": hyp.symbol,
            "name": hyp.name,
            "strategy": hyp.strategy,
            "or_min": hyp.range_minutes,
            "session_min": hyp.session_duration_minutes,
            "trades": stats["trades"],
            "win_rate_pct": stats["win_rate_pct"],
            "profit_factor": stats["profit_factor"],
            "expectancy_R": stats["expectancy_R"],
            "net_pnl": stats["net_pnl"],
            "max_drawdown_pct": stats["max_drawdown_pct"],
            "final_balance": stats["final_balance"]
        })

    summary_df = pd.DataFrame(results)
    return summary_df, trades_dict


if __name__ == "__main__":
    summary, _ = run_all_locked_hypotheses()
    print("\n=== AURUM v0.4 HYPOTHESIS LOCK RESULTS ===")
    print(summary.to_string(index=False))
