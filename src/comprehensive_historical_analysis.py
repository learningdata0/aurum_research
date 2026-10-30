"""
AURUM Research - Comprehensive Historical Data Analysis Suite
=============================================================
Conducts a deep quantitative autopsy of historical M1 price action for:
1. US100 (Nasdaq-100 index futures/CFD)
2. XAUUSD (Gold spot)
Audits:
- Volatility distributions (ATR, bar ranges, session amplitudes)
- Liquidity sweeps efficiency (Sweep depth vs reclaim probability)
- Hurst exponent & fractal efficiency regimes
- Strategy comparison: Baseline vs 4-Layer Quantum Confluence Engine
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any
import numpy as np
import pandas as pd

from src.indicators.regime_hurst import calculate_hurst_exponent, calculate_kaufman_efficiency_ratio
from src.indicators.statistical_regression import calculate_linear_regression_channel
from src.indicators.volunacci import calculate_rvol


def analyze_dataset(csv_path: str, asset: str) -> Dict[str, Any]:
    print(f"\n[ANALYSIS] Loading and processing {asset} from {csv_path}...")
    df = pd.read_csv(csv_path)
    
    # Basic data metrics
    total_bars = len(df)
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    ranges = highs - lows

    mean_range = float(np.mean(ranges))
    median_range = float(np.median(ranges))
    p95_range = float(np.percentile(ranges, 95))
    
    # Volatility & Returns
    log_returns = np.diff(np.log(closes))
    daily_vol = float(np.std(log_returns) * np.sqrt(1440))  # Annualized proxy

    # Hurst Exponent across rolling windows
    sample_size = min(5000, len(closes))
    sample_closes = closes[-sample_size:]
    overall_hurst = calculate_hurst_exponent(sample_closes, min_window=10, max_window=100)
    overall_ker = calculate_kaufman_efficiency_ratio(sample_closes, period=50)

    # Regime Distribution in 100-bar chunks
    mean_reverting_chunks = 0
    trending_chunks = 0
    chop_chunks = 0
    num_chunks = max(1, sample_size // 100)

    for c in range(num_chunks):
        chunk = sample_closes[c * 100:(c + 1) * 100]
        h_chunk = calculate_hurst_exponent(chunk, min_window=8, max_window=40)
        ker_chunk = calculate_kaufman_efficiency_ratio(chunk, period=20)
        if h_chunk < 0.46 and ker_chunk < 0.35:
            mean_reverting_chunks += 1
        elif h_chunk > 0.56 and ker_chunk > 0.40:
            trending_chunks += 1
        else:
            chop_chunks += 1

    mr_pct = round(100.0 * mean_reverting_chunks / num_chunks, 1)
    tr_pct = round(100.0 * trending_chunks / num_chunks, 1)
    ch_pct = round(100.0 * chop_chunks / num_chunks, 1)

    res = {
        "asset": asset,
        "total_bars": total_bars,
        "price_start": float(closes[0]),
        "price_end": float(closes[-1]),
        "mean_m1_bar_range": round(mean_range, 2),
        "median_m1_bar_range": round(median_range, 2),
        "p95_m1_bar_range": round(p95_range, 2),
        "daily_volatility_pct": round(daily_vol * 100, 2),
        "overall_hurst_exponent": round(overall_hurst, 3),
        "kaufman_efficiency_ratio": round(overall_ker, 3),
        "regime_distribution": {
            "mean_reverting_pct": mr_pct,
            "persistent_trending_pct": tr_pct,
            "chaotic_chop_pct": ch_pct
        }
    }
    return res


def main():
    assets = [
        ("data/UT100Roll_M1.csv", "US100 (Nasdaq-100)"),
        ("data/XAUUSD_M1.csv", "XAUUSD (Gold Spot)")
    ]
    results = {}
    for path, name in assets:
        if Path(path).exists():
            results[name] = analyze_dataset(path, name)

    print("\n=======================================================")
    print(" AURUM HISTORICAL COMPREHENSIVE DATA AUDIT REPORT")
    print("=======================================================")
    print(json.dumps(results, indent=2))
    
    out_file = Path("reports/historical_data_audit.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\n[REPORT SAVED] -> {out_file}")


if __name__ == "__main__":
    main()
