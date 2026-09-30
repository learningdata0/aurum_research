# AURUM Research v0.8: Operational Playbook & Forward Shadow Trading Manual

**Author:** AURUM Quantitative Research Engine  
**Version:** v0.8 (Post-Breakthrough Forward Validation Phase)  
**Target Assets:** `UT100Roll / US100` (Nasdaq-100) & `XAUUSD` (Spot Gold)  
**Active Strategies:**  
- `H17` — London Session Liquidity Sweep-Reclaim (Range $\ge 140$ pts, Target = Midpoint)  
- `XAU_H17` — Gold London Liquidity Sweep (Range $\ge 55$ pts, Target = Midpoint)  
**Status:** **DUAL-ASSET ACTIVE VIRTUAL / FORWARD PAPER EXECUTION (ZERO REAL FINANCIAL RISK)**  

---

## 1. Executive Summary & Core Edge

Following the empirical failure of legacy Opening Range breakout/boundary models (H1–H6) when subjected to multi-year walk-forward testing (704,347 bars across 2024–2026), the research engine redesigned the market question around **Higher Timeframe (HTF) institutional liquidity dynamics**.

### The Breakthrough Setups:
1. **US100 (`H17`):**
   - **Expansion Filter:** London Range $\ge 140.0$ pts (2-year median: 146.4 pts).
   - **Target:** London Session Midpoint.
   - **Performance:** $PF = 1.20$ Full Period / $1.46$ OOS, Net $+168.4R$ (+$4,711), Max DD $9.82\%$, 83.3% positive months.
2. **Gold (`XAU_H17`):**
   - **Expansion Filter:** London Range $\ge 55.0$ pts ($\approx 75$th percentile volatility regime).
   - **Target:** London Session Midpoint.
   - **Performance:** $PF = 1.50$, Net $+15.03R$ (+$375.84), Expectancy $+0.42R$, Max DD only $3.17\%$.

---

## 2. Asset Allocation & Specialization Mandate

Per executive research directive, the portfolio focus for the next 30 days is **strictly confined to US100 and Gold**:

| Asset Class | Instrument | Active Strategy | Volatility Filter | Validated PF | Status |
|---|---|---|---|---|---|
| **Tech Index** | **US100** | `H17` Sweep-Reclaim | London Range $\ge 140$ pts | **1.20** | **ACTIVE FORWARD SHADOW** |
| **Precious Metals** | **XAUUSD** | `XAU_H17` Sweep-Reclaim | London Range $\ge 55$ pts | **1.50** | **ACTIVE FORWARD SHADOW** |
| **Industrial Index** | US30 (Dow) | N/A (Trend Engine) | N/A | 0.86 | ⏸️ **PAUSED FOR 30 DAYS** |

### Strategic Rationales:
- **US100 & Gold Synergy:** Nasdaq represents tech growth equities; Gold represents macro currency & geopolitical hedging. Their liquidity sweeps occur at different structural times and exhibit near-zero correlation, creating a resilient dual-asset portfolio.
- **US30 Pause:** Dow Jones requires trend-following breakout momentum rather than mean-reversion. Research on US30 is officially paused for 30 days while US100 and Gold forward shadow validation completes.

---

## 3. Architecture of the Forward Shadow Environment

The Forward Shadow environment runs dual synchronized layers to guarantee zero capital loss while collecting genuine broker tick metrics:

```
[ Equiti Broker Server (EEST/EET) ]
         │ (Live M1 Ticks)
         ▼
┌─────────────────────────────────────────────────────────────┐
│ MetaTrader 5: Dual Native EAs                               │
│ 1. AurumH17ShadowEA.mq5     -> Chart: UT100Roll, M1         │
│ 2. AurumGoldH17ShadowEA.mq5 -> Chart: XAUUSD, M1            │
│ - Virtual Mode = true (No real orders sent to broker)       │
│ - Live Bid/Ask tick exit matching                           │
│ - Writes to aurum_shadow_trades.csv & aurum_gold_shadow...  │
└──────────────────────────────┬──────────────────────────────┘
                               │ (File I/O Sync)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ Python Autonomous Engine: src/shadow_daemon.py              │
│ - Real-time dual-asset trade auditor and portfolio tracker  │
│ - Automatic 15-second multi-asset file watcher              │
│ - Live Unified Dashboard: reports/shadow_dashboard.md       │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Operator Guide: Running the Forward Shadow System

### Step 1: Launch MetaTrader 5 Expert Advisor
1. In **MetaTrader 5**, press `F4` to open **MetaEditor**.
2. In the Navigator tree under `Experts/Advisors/`, double-click [`AurumH17ShadowEA.mq5`](file:///Users/nouh/Library/Application%20Support/net.metaquotes.wine.metatrader5/drive_c/Program%20Files/MetaTrader%205/MQL5/Experts/Advisors/AurumH17ShadowEA.mq5).
3. Press `F7` to Compile. Confirm output shows `0 errors, 0 warnings`.
4. Open the `UT100Roll` M1 chart in MT5.
5. Drag `AurumH17ShadowEA` onto the chart:
   - In **Inputs**, confirm:
     - `InpVirtualMode = true`
     - `InpRiskPercent = 0.25`
     - `InpMinLondonRange = 140.0`
   - In **Common**, check `Allow Algo Trading`.
6. Verify the on-chart HUD comment appears in the top-left corner displaying:
   - London High, London Low, London Range.
   - Qualification status (`QUALIFIED` or `UNQUALIFIED`).
   - Virtual Account Balance.

### Step 2: Run the Python Shadow Daemon
To continuously monitor and update the research dashboard in real time, run from the project root:

```bash
# Continuous Watch Mode (re-checks every 15 seconds)
PYTHONPATH=. .venv/bin/python -m src.shadow_daemon --mode watch --interval 15
```

To manually synchronize with MT5 at any time:
```bash
PYTHONPATH=. .venv/bin/python -m src.shadow_daemon --mode sync
```

To run a clean replay audit over the last 14 trading days:
```bash
PYTHONPATH=. .venv/bin/python -m src.shadow_daemon --mode replay --days 14 --reset
```

---

## 5. Research Gate Protocol: Advancing to Demo & Live

To prevent emotional or premature capital allocation, progression between stages is governed by rigid mathematical criteria:

| Milestone Gate | Target Criteria | Current Status | Next Action |
|---|---|---|---|
| **Gate 1: Multi-Year Backtest** | $N \ge 300$, $PF \ge 1.15$, $DD < 15\%$, WFE $> 0.70$ | **PASS** ($N=976$, $PF=1.20$, $DD=9.8\%$) | Proceed to Forward Shadow |
| **Gate 2: Forward Shadow (Virtual)** | **$N \ge 30$ live forward trades**, $PF \ge 1.20$, $DD \le 10\%$, real slippage $\le 0.75$ pts | **IN PROGRESS** (18 shadow trades initialized) | Accumulate 30 live forward executions |
| **Gate 3: Demo Trading (Broker)** | $N \ge 50$ broker demo trades, zero order reject errors, positive expectancy | **LOCKED** (Awaiting Gate 2 PASS) | Prohibited until Gate 2 completes |
| **Gate 4: Live Micro-Capital** | Max $0.10\%$ risk per trade, hard daily loss limit $1.0\%$ | **LOCKED** | Prohibited until Gate 3 completes |

---

## 6. Risk Controls & Circuit Breakers

1. **Daily Loss Cutoff:** Trading for the day terminates automatically if cumulative daily loss reaches $-1.00\%$ of equity (4 consecutive $1R losses).
2. **Consecutive Loss Breaker:** If 3 consecutive trades hit SL on a single day, the engine halts further entries until the next trading day.
3. **Session Hard Filter:** Zero entries are permitted outside 09:30–15:30 New York time.
4. **Range Hard Filter:** Zero entries are permitted if the London Session range is $< 140.0$ points.
