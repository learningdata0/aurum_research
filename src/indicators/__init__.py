"""
AURUM Research - Quantum Orthogonal Indicator Suite
===================================================
A non-conflicting 4-layer quantitative framework:
1. Structural SMC & Fractality (Where liquidity sits)
2. Volume Spread & Volunacci (Who is entering - Institutional backing)
3. Statistical Linear Regression & Fair Value (Valuation & Mean Reversion)
4. Multi-Oscillator Qualified Divergence (When momentum exhausts)
"""

from .smc_fractals import (
    detect_fractals,
    detect_fair_value_gaps,
    detect_market_structure_shifts,
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
    calculate_zscore_bands,
    LinearRegressionChannel
)
from .divergence_engine import (
    detect_rsi_divergences,
    detect_macd_divergences,
    DivergenceSignal
)
from .regime_hurst import (
    calculate_hurst_exponent,
    calculate_kaufman_efficiency_ratio,
    classify_market_regime,
    MarketRegime
)
from .orderflow_delta import (
    calculate_intrabar_delta,
    detect_orderflow_anomalies,
    OrderFlowSignal
)
from .quantum_confluence import (
    QuantumConfluenceEngine,
    QuantumSetup,
    evaluate_quantum_signal
)

__all__ = [
    "detect_fractals",
    "detect_fair_value_gaps",
    "detect_market_structure_shifts",
    "detect_liquidity_sweeps",
    "FairValueGap",
    "FractalPivot",
    "calculate_rvol",
    "detect_volume_spread_anomalies",
    "calculate_volunacci_levels",
    "VolunacciGrid",
    "calculate_linear_regression_channel",
    "calculate_zscore_bands",
    "LinearRegressionChannel",
    "detect_rsi_divergences",
    "detect_macd_divergences",
    "DivergenceSignal",
    "calculate_hurst_exponent",
    "calculate_kaufman_efficiency_ratio",
    "classify_market_regime",
    "MarketRegime",
    "calculate_intrabar_delta",
    "detect_orderflow_anomalies",
    "OrderFlowSignal",
    "QuantumConfluenceEngine",
    "QuantumSetup",
    "evaluate_quantum_signal"
]
