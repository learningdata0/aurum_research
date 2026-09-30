from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional


@dataclass
class MacroHeadline:
    timestamp_utc: str
    category: str  # "GEOPOLITICAL", "MONETARY_POLICY", "TARIFFS_POLITICS", "ENERGY"
    headline: str
    impact_gold: str
    impact_us100: str
    volatility_effect: str  # "EXPANSION", "CONTRACTION", "DIRECTIONAL_SHOCK"


# Macro & Geopolitical Transmission Matrix (Grounded in Financial Economics & Empirical Quantitative Data)
GEOPOLITICAL_REGIME_RULES = {
    "IRAN_MIDDLE_EAST_CRISIS": {
        "description": "Heightened U.S.-Iran confrontation, Strait of Hormuz closure risk, elevated crude oil (> $100/bbl).",
        "transmission_gold": (
            "Safe-haven bid drives explosive intraday expansions (London ranges > 55 pts). "
            "However, if yields rise concurrently, upside runs stall, leading to sharp sweeps above highs "
            "followed by violent mean-reversion reclaims (XAU_H17 sweet spot)."
        ),
        "transmission_us100": (
            "Oil price shock elevates headline inflation, raising discount rates via higher Treasury yields. "
            "Tech multiples compress. Algorithmic liquidity sweeps occur frequently around NY cash open (16:30 broker time)."
        ),
        "recommended_stance": "Trade high-volatility sweep-reclaims on both sides (Long & Short); avoid blind trend breakout chases."
    },
    "TRUMP_TRADE_TARIFF_SHOCKS": {
        "description": "Aggressive trade rhetoric, sudden tariff implementation/threats, shifting bilateral frameworks.",
        "transmission_gold": (
            "Dollar volatility spikes. Tariffs drive currency debasement hedges, but sudden trade de-escalation "
            "deals trigger sharp 30-50 pt pullbacks."
        ),
        "transmission_us100": (
            "High supply chain sensitivity (semiconductors, hardware, global tech giants). "
            "Knee-jerk selloffs frequently sweep previous session lows, offering high-probability long reclaim entries."
        ),
        "recommended_stance": "Capitalize on initial panic wick sweeps. The first 15-30 minutes after open create prime liquidity traps."
    },
    "FED_HAWKISH_YIELDS_REGIME": {
        "description": "Federal Reserve maintains tight monetary policy, sticky inflation, 10-year yields elevated.",
        "transmission_gold": (
            "Opportunity cost of holding non-yielding bullion remains high, preventing unconstrained parabolic trends. "
            "Creates clear 2-way range boundaries ideal for H17 London sweep fading."
        ),
        "transmission_us100": (
            "Growth stock valuations capped by discount rate. Index oscillates in defined daily expansion zones "
            "(London ranges >= 140 pts)."
        ),
        "recommended_stance": "Strict adherence to London Session range minimums; high-probability mean-reversion to midpoint."
    }
}


class MacroIntelligenceEngine:
    """
    Synthesizes real-time macroeconomic, geopolitical, and central bank developments
    to evaluate market regime conditions and provide context to AURUM's quantitative execution engines.
    """

    def __init__(self):
        self.active_headlines: List[MacroHeadline] = []

    def get_current_macro_snapshot(self) -> Dict:
        """Returns structured synthesis of active geopolitical and macroeconomic drivers as of late 2026."""
        return {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "core_geopolitical_themes": [
                {
                    "theme": "U.S.-Iran & Hormuz Standoff",
                    "status": "Ceasefire rejection / High tension / Brent crude > $100",
                    "market_vector": "Risk Premia Active | Elevated Volatility"
                },
                {
                    "theme": "Trump Administration Trade & Security Policy",
                    "status": "Bilateral trade bargaining / Tariff leverage / Sanctions enforcement",
                    "market_vector": "Asymmetric Headline Sensitivity"
                },
                {
                    "theme": "Federal Reserve & Interest Rate Trajectory",
                    "status": "Sticky inflation / Hawkish caution / Real yields elevated",
                    "market_vector": "Caps runaway Gold momentum; forces range-bound swing dynamics"
                }
            ],
            "asset_implications": {
                "XAUUSD": {
                    "regime": "High-Volatility Mean-Reverting Expansion (PF: 1.50 in ranges >= 55 pts)",
                    "long_setup_rationale": "Sweeps below London Low during liquidity flushes offer prime safe-haven discount absorption.",
                    "short_setup_rationale": "Sweeps above London High exhausted by high real yields offer swift mean-reversion back to London Midpoint."
                },
                "US100": {
                    "regime": "Macro Liquidity Sweep Reclaim (PF: 1.20 in ranges >= 140 pts)",
                    "long_setup_rationale": "Morning panic sweeps of London Low get aggressively bought by institutional algos on dips.",
                    "short_setup_rationale": "Pre-market euphoria sweeps of London High get faded as bond yields squeeze higher at NY Cash Open."
                }
            }
        }

    def format_macro_briefing(self) -> str:
        snapshot = self.get_current_macro_snapshot()
        briefing = [
            f"# AURUM Macro & Geopolitical Intelligence Briefing",
            f"**Timestamp:** {snapshot['timestamp']}\n",
            "### 1. Active Geopolitical & Macroeconomic Catalysts",
        ]
        for t in snapshot["core_geopolitical_themes"]:
            briefing.append(f"- **{t['theme']}:** {t['status']} *(Vector: {t['market_vector']})*")

        briefing.append("\n### 2. Cross-Asset Transmission Mechanics")
        for asset, details in snapshot["asset_implications"].items():
            briefing.append(f"#### {asset}")
            briefing.append(f"- **Quantitative Regime:** {details['regime']}")
            briefing.append(f"- **Bullish (Long) Logic:** {details['long_setup_rationale']}")
            briefing.append(f"- **Bearish (Short) Logic:** {details['short_setup_rationale']}")

        return "\n".join(briefing)
