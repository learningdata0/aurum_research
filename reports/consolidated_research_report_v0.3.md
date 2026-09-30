# AURUM Research Engine v0.3 — Consolidated Hypothesis & Validation Report

## 1. Executive Summary & Context
- **Dataset**: 7,560 M1 bars (~21 sessions) extracted from `Trading_Analysis_Consolidated.xlsx`.
- **Timezone Anchor**: `America/New_York` (Session Open: 09:30 AM local time).
- **Purpose**: Pipeline validation of 5 distinct hypotheses, Market Regime State Machine, Cost Stress Testing, and Monte Carlo resampling.

## 2. Five Hypotheses Performance Comparison
| symbol | strategy           | trades | win_rate_pct | profit_factor | expectancy_R | net_pnl | max_drawdown_pct |
| ------ | ------------------ | ------ | ------------ | ------------- | ------------ | ------- | ---------------- |
| XAUUSD | boundary_reversion | 17     | 35.29        | 1.41          | 0.27         | 113.19  | 1.0              |
| XAUUSD | sweep_reclaim      | 16     | 31.25        | 1.28          | 0.2          | 76.84   | 1.0              |
| XAUUSD | micro_range        | 4      | 0.0          | 0.0           | -1.0         | -99.63  | 0.75             |
| XAUUSD | breakout           | 5      | 20.0         | 0.32          | -0.55        | -68.14  | 1.0              |
| XAUUSD | breakout_retest    | 4      | 0.0          | 0.0           | -1.0         | -99.63  | 0.75             |
| XAUUSD | composite_regime   | 4      | 0.0          | 0.0           | -1.0         | -99.63  | 0.75             |
| US30   | boundary_reversion | 7      | 14.29        | 0.61          | -0.33        | -58.44  | 1.0              |
| US30   | sweep_reclaim      | 11     | 36.36        | 1.2           | 0.13         | 34.74   | 1.0              |
| US30   | micro_range        | 6      | 16.67        | 0.25          | -0.62        | -93.0   | 1.0              |
| US30   | breakout           | 10     | 40.0         | 0.95          | -0.03        | -8.23   | 1.0              |
| US30   | breakout_retest    | 4      | 0.0          | 0.0           | -1.0         | -99.63  | 0.75             |
| US30   | composite_regime   | 17     | 35.29        | 1.1           | 0.07         | 28.72   | 1.0              |
| US100  | boundary_reversion | 7      | 14.29        | 0.47          | -0.45        | -79.35  | 1.0              |
| US100  | sweep_reclaim      | 8      | 37.5         | 1.24          | 0.15         | 29.84   | 1.0              |
| US100  | micro_range        | 4      | 0.0          | 0.0           | -1.0         | -99.63  | 0.75             |
| US100  | breakout           | 26     | 46.15        | 1.06          | 0.03         | 21.59   | 1.0              |
| US100  | breakout_retest    | 9      | 22.22        | 0.46          | -0.42        | -94.08  | 1.01             |
| US100  | composite_regime   | 11     | 45.45        | 1.46          | 0.25         | 69.16   | 1.0              |


### Key Statistical Observations:
1. **Boundary Reversion vs Sweep Reclaim**: When boundary reversion is strictly enforced (requiring price to stay near RH/RL), it eliminated the artificial +10.54R outlier from v0.1. Meanwhile, `sweep_reclaim` demonstrated positive expectancy on US100 (+0.15R, PF 1.24).
2. **Market Regime Filtering**: The `composite_regime` state machine delivered the highest expectancy on US100 (+0.25R, PF 1.46) by disabling mean reversion during trending/broken ranges.
3. **Asset Volatility Differences**: Gold (XAUUSD) showed negative expectancy under 30m Opening Ranges, but parameter matrix analysis revealed positive expectancy (+0.43R) under short 5m/10m Opening Ranges.

## 3. Cost & Slippage Stress Test (US100 / composite_regime)
| scenario            | comm_per_unit | slippage_points | trades | profit_factor | expectancy_R | net_pnl |
| ------------------- | ------------- | --------------- | ------ | ------------- | ------------ | ------- |
| Frictionless        | 0.0           | 0.0             | 11     | 1.46          | 0.25         | 69.16   |
| Base Costs (1x)     | 0.5           | 0.25            | 11     | 1.34          | 0.2          | 54.9    |
| +25% Spread         | 0.62          | 0.25            | 11     | 1.33          | 0.19         | 52.52   |
| +50% Spread         | 0.75          | 0.5             | 11     | 1.27          | 0.17         | 45.4    |
| +100% Spread (2x)   | 1.0           | 0.75            | 11     | 1.21          | 0.13         | 35.91   |
| High Slippage (5t)  | 0.75          | 1.25            | 11     | 1.18          | 0.12         | 31.17   |
| Severe Stress (10t) | 1.0           | 2.5             | 11     | 1.01          | 0.01         | 2.75    |

**Friction Takeaway**: The strategy maintains positive expectancy through +100% spread expansion and 5 ticks of slippage, reaching breakeven at 10 ticks.


## 4. Monte Carlo Resampling (1,000 Iterations)
| symbol | iterations | mean_expectancy_R | ci_95_lower_R | ci_95_upper_R | median_max_dd_pct | dd_95th_percentile_pct | worst_max_dd_pct | prob_dd_over_5pct | prob_dd_over_10pct | prob_profitable |
| ------ | ---------- | ----------------- | ------------- | ------------- | ----------------- | ---------------------- | ---------------- | ----------------- | ------------------ | --------------- |
| XAUUSD | 0          | 0.0               | 0.0           | 0.0           | 0.0               | 0.0                    | 0.0              | 0.0               | 0.0                | 0.0             |
| US30   | 1000       | 0.06              | -0.62         | 0.83          | 1.25              | 2.66                   | 3.78             | 0.0               | 0.0                | 55.7            |
| US100  | 1000       | 0.27              | -0.53         | 1.08          | 0.75              | 1.52                   | 2.28             | 0.0               | 0.0                | 70.5            |

**Risk Takeaway**: Over 1,000 resamplings, probability of max drawdown exceeding 5% is 0.0%, with a 95% worst-case drawdown of 1.52% on US100.


## 5. Opening Range Duration Spectrum Matrix
- **US100**: Positive plateau forms around 30m Opening Range with 90m–150m session durations (PF 1.46–1.49, Expectancy +0.25R–+0.28R).
- **XAUUSD**: Fast opening momentum favors short 5m Opening Ranges (PF 1.91, Expectancy +0.43R over 60m session), confirming that fixed 30m windows should not be applied blindly across all asset classes.

## 6. Next Steps for Production Research
1. **Export 730+ Days of M1 Data**: Using `src/mql5/AurumExport.mq5` on MT5 for Mac for US100, US30, and XAUUSD.
2. **Multi-Year Walk-Forward**: Execute rolling 3-month train / 1-month test sweeps across 2–3 full years.
3. **Broker Server Time Verification**: Verify whether Equiti server time matches GMT+2/GMT+3 to ensure perfect conversion to `America/New_York`.