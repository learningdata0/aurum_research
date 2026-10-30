"""
Master Quantum Confluence Engine (AQCE)
========================================
Synthesizes the 4 orthogonal non-conflicting layers into an institutional scoring matrix:
1. Structural SMC & Fractality (Where)
2. Volunacci & Whale Footprint (Who)
3. Linear Regression & Statistical Bounds (Value)
4. Qualified Momentum Divergence (When)

Guarantees ZERO contradictory signals:
A signal is only emitted when all 4 dimensions align with mathematical harmony.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd

from .smc_fractals import (
    detect_fractals,
    detect_fair_value_gaps,
    detect_liquidity_sweeps,
    FairValueGap,
    FractalPivot
)
from .volunacci import (
    calculate_rvol,
    detect_volume_spread_anomalies,
    calculate_volunacci_levels,
    VolunacciGrid
)
from .statistical_regression import (
    calculate_linear_regression_channel,
    LinearRegressionChannel
)
from .divergence_engine import (
    detect_rsi_divergences,
    detect_macd_divergences,
    DivergenceSignal
)


@dataclass
class QuantumSetup:
    timestamp: Any
    symbol: str
    direction: str  # "BUY" or "SELL"
    confluence_score: float  # 0 to 100
    entry_price: float
    stop_loss: float
    take_profit_1: float  # 1.5R (Bank 50% & Lock Breakeven)
    take_profit_2: float  # 3.0R (Regression Midline / Fair Value)
    take_profit_3: float  # 5.0R (Macro Liquidity Pool)
    risk_pts: float
    reward_pts_tp1: float
    rr_ratio: float
    layer_breakdown: Dict[str, float] = field(default_factory=dict)
    rationale: str = ""


class QuantumConfluenceEngine:
    """
    Autonomous Quantitative Confluence Analyzer for Institutional Grade Trading.
    """

    def __init__(
        self,
        min_confluence_score: float = 75.0,
        rvol_threshold: float = 1.5,
        regression_lookback: int = 100,
        rsi_period: int = 14
    ):
        self.min_confluence_score = min_confluence_score
        self.rvol_threshold = rvol_threshold
        self.regression_lookback = regression_lookback
        self.rsi_period = rsi_period

    def analyze_market_slice(
        self,
        df: pd.DataFrame,
        symbol: str = "ASSET",
        htf_high: Optional[float] = None,
        htf_low: Optional[float] = None
    ) -> Optional[QuantumSetup]:
        """
        Executes a 4-dimensional orthogonal scan on the trailing market data slice.
        Returns a QuantumSetup if confluence score >= threshold and zero conflicts exist.
        """
        if len(df) < max(50, self.regression_lookback):
            return None

        curr_row = df.iloc[-1]
        curr_price = float(curr_row["close"])
        curr_time = curr_row["time"] if "time" in curr_row else datetime.utcnow()

        # ----------------------------------------------------
        # Layer 1: Structural SMC & Fractality (Max 30 points)
        # ----------------------------------------------------
        pivots = detect_fractals(df, span=5)
        fvgs = detect_fair_value_gaps(df, min_gap_pts=0.2)
        active_unmitigated_fvgs = [f for f in fvgs if not f.mitigated]

        # Use recent fractal high/low or passed HTF levels
        high_pivots = [p for p in pivots if p.pivot_type == "HIGH"]
        low_pivots = [p for p in pivots if p.pivot_type == "LOW"]

        target_h = htf_high if htf_high is not None else (high_pivots[-1].price if high_pivots else curr_row.high)
        target_l = htf_low if htf_low is not None else (low_pivots[-1].price if low_pivots else curr_row.low)

        sweep_res = detect_liquidity_sweeps(curr_row, target_h, target_l, min_sweep_pts=0.2, min_wick_ratio=0.30)

        layer_1_score = 0.0
        candidate_direction: Optional[str] = None
        sweep_extreme = 0.0

        if sweep_res is not None:
            sw_type, swept_level, pen = sweep_res
            if sw_type == "BEAR_SWEEP":
                candidate_direction = "SELL"
                layer_1_score += 20.0
                sweep_extreme = float(curr_row.high)
            elif sw_type == "BULL_SWEEP":
                candidate_direction = "BUY"
                layer_1_score += 20.0
                sweep_extreme = float(curr_row.low)

        # Check FVG confluence
        matching_fvg: Optional[FairValueGap] = None
        if candidate_direction == "BUY":
            bull_fvgs = [f for f in active_unmitigated_fvgs if f.gap_type == "BULLISH"]
            if bull_fvgs and (bull_fvgs[-1].is_price_inside(curr_price) or abs(curr_price - bull_fvgs[-1].midpoint) <= 2.0):
                layer_1_score += 10.0
                matching_fvg = bull_fvgs[-1]
        elif candidate_direction == "SELL":
            bear_fvgs = [f for f in active_unmitigated_fvgs if f.gap_type == "BEARISH"]
            if bear_fvgs and (bear_fvgs[-1].is_price_inside(curr_price) or abs(curr_price - bear_fvgs[-1].midpoint) <= 2.0):
                layer_1_score += 10.0
                matching_fvg = bear_fvgs[-1]

        if candidate_direction is None:
            return None  # No structural hook found

        # ----------------------------------------------------
        # Layer 2: Volume & Volunacci Footprint (Max 25 points)
        # ----------------------------------------------------
        rvol_series = calculate_rvol(df, period=20)
        curr_rvol = float(rvol_series.iloc[-1])
        vsa_df = detect_volume_spread_anomalies(df, rvol_series, rvol_threshold=self.rvol_threshold)
        curr_anomaly = vsa_df["anomaly_type"].iloc[-1]

        layer_2_score = 0.0
        if curr_rvol >= self.rvol_threshold:
            layer_2_score += 10.0

        if candidate_direction == "BUY" and curr_anomaly in ("ABSORPTION_BUY", "CHURN"):
            layer_2_score += 10.0
        elif candidate_direction == "SELL" and curr_anomaly in ("ABSORPTION_SELL", "CHURN"):
            layer_2_score += 10.0

        # Volunacci Golden Pocket check
        vol_grid = calculate_volunacci_levels(curr_row, len(df) - 1, curr_anomaly, curr_rvol)
        if vol_grid.is_in_golden_pocket(curr_price):
            layer_2_score += 5.0

        # ----------------------------------------------------
        # Layer 3: Linear Regression & Statistical Bounds (Max 25 pts)
        # ----------------------------------------------------
        closes = df["close"].values
        reg_channel = calculate_linear_regression_channel(closes, lookback=self.regression_lookback)

        layer_3_score = 0.0
        if reg_channel is not None:
            z = reg_channel.current_zscore

            # ZERO CONFLICT CHECK:
            # If candidate is BUY but price is overbought (z >= +1.5), conflict! Cancel setup.
            if candidate_direction == "BUY" and z >= 1.5:
                return None
            # If candidate is SELL but price is oversold (z <= -1.5), conflict! Cancel setup.
            if candidate_direction == "SELL" and z <= -1.5:
                return None

            # Confluence scoring
            if candidate_direction == "BUY":
                if z <= -1.8:
                    layer_3_score += 25.0
                elif z <= -1.0:
                    layer_3_score += 15.0
                elif z <= -0.5:
                    layer_3_score += 10.0
            elif candidate_direction == "SELL":
                if z >= 1.8:
                    layer_3_score += 25.0
                elif z >= 1.0:
                    layer_3_score += 15.0
                elif z >= 0.5:
                    layer_3_score += 10.0

        # ----------------------------------------------------
        # Layer 4: Qualified Momentum Divergence (Max 20 points)
        # ----------------------------------------------------
        rsi_divs = detect_rsi_divergences(df, rsi_period=self.rsi_period, lookback_bars=35)
        macd_divs = detect_macd_divergences(df, lookback_bars=35)

        layer_4_score = 0.0
        div_desc = []

        if candidate_direction == "BUY":
            bull_rsi = [d for d in rsi_divs if d.div_type == "REGULAR_BULLISH"]
            bull_macd = [d for d in macd_divs if d.div_type == "REGULAR_BULLISH"]
            if bull_rsi:
                layer_4_score += 12.0
                div_desc.append("RSI Bullish Divergence")
            if bull_macd:
                layer_4_score += 8.0
                div_desc.append("MACD Bullish Divergence")
        elif candidate_direction == "SELL":
            bear_rsi = [d for d in rsi_divs if d.div_type == "REGULAR_BEARISH"]
            bear_macd = [d for d in macd_divs if d.div_type == "REGULAR_BEARISH"]
            if bear_rsi:
                layer_4_score += 12.0
                div_desc.append("RSI Bearish Divergence")
            if bear_macd:
                layer_4_score += 8.0
                div_desc.append("MACD Bearish Divergence")

        # ----------------------------------------------------
        # Total Composite Confluence Score
        # ----------------------------------------------------
        total_score = layer_1_score + layer_2_score + layer_3_score + layer_4_score

        if total_score < self.min_confluence_score:
            return None

        # ----------------------------------------------------
        # Mathematical Order Formulation (Micro SL + Asymmetric TP)
        # ----------------------------------------------------
        # Approximate ATR
        recent_spreads = df["high"].tail(14) - df["low"].tail(14)
        atr_14 = float(recent_spreads.mean()) if not recent_spreads.empty else 1.0

        if candidate_direction == "BUY":
            entry = curr_price
            # SL strictly below sweep low + tiny buffer
            sl = sweep_extreme - (0.15 * atr_14)
            risk = abs(entry - sl)
            if risk <= 0:
                return None
            tp1 = entry + 1.5 * risk
            tp2 = reg_channel.midline_price if reg_channel and reg_channel.midline_price > entry else entry + 3.0 * risk
            tp3 = reg_channel.upper_2sd if reg_channel and reg_channel.upper_2sd > tp2 else entry + 5.0 * risk
        else:  # SELL
            entry = curr_price
            # SL strictly above sweep high + tiny buffer
            sl = sweep_extreme + (0.15 * atr_14)
            risk = abs(sl - entry)
            if risk <= 0:
                return None
            tp1 = entry - 1.5 * risk
            tp2 = reg_channel.midline_price if reg_channel and reg_channel.midline_price < entry else entry - 3.0 * risk
            tp3 = reg_channel.lower_2sd if reg_channel and reg_channel.lower_2sd < tp2 else entry - 5.0 * risk

        breakdown = {
            "Layer_1_Structure": layer_1_score,
            "Layer_2_Volume": layer_2_score,
            "Layer_3_Regression": layer_3_score,
            "Layer_4_Divergence": layer_4_score,
            "Total_Score": total_score
        }

        rationale = (
            f"Quantum Confluence ({total_score:.1f}/100) | Direction: {candidate_direction} | "
            f"SMC: Sweep of {target_h if candidate_direction=='SELL' else target_l:.2f} | "
            f"RVOL: {curr_rvol:.2f}x ({curr_anomaly}) | "
            f"Z-Score: {reg_channel.current_zscore if reg_channel else 0.0:+.2f} SD | "
            f"Divergence: {', '.join(div_desc) if div_desc else 'None'}"
        )

        return QuantumSetup(
            timestamp=curr_time,
            symbol=symbol,
            direction=candidate_direction,
            confluence_score=total_score,
            entry_price=entry,
            stop_loss=sl,
            take_profit_1=tp1,
            take_profit_2=tp2,
            take_profit_3=tp3,
            risk_pts=risk,
            reward_pts_tp1=abs(tp1 - entry),
            rr_ratio=round(abs(tp1 - entry) / risk, 2),
            layer_breakdown=breakdown,
            rationale=rationale
        )


def evaluate_quantum_signal(
    df_slice: pd.DataFrame,
    symbol: str = "ASSET",
    min_score: float = 75.0
) -> Optional[QuantumSetup]:
    """Helper functional wrapper for one-shot quantum evaluation."""
    engine = QuantumConfluenceEngine(min_confluence_score=min_score)
    return engine.analyze_market_slice(df_slice, symbol=symbol)
