# 🎯 H17 London Sweep & Reclaim Strategy Specification

### 1. Structural Concept: The Institutional Liquidity Trap
Retail traders are systematically conditioned to buy breakouts above daily highs and sell breakdowns below daily lows. Major liquidity providers and institutional algorithmic desks exploit this behavior by pushing prices just beyond key session boundaries (London High / Low) to trigger stop orders and breakout market orders, absorbing that liquidity, and driving prices back toward fair value.

```
       [London High] ------------------------------- Swept by New York Open
                            /\                      (Liquidity Hunt / Bull Trap)
                           /  \
                          /    \===============> Entry: Reclaim below High
                         /      \                Stop Loss: High Wick + Spread
                        /        \
                       /          \
[London Midpoint] ----/------------\------------ Target (Fair Value / Mean Reversion)
                     /              \
                    /                \
[London Low] ------/                  \--------- Accumulation Boundary
```

---

### 2. Strategy Rules & Mathematical Parameters

| Parameter | US100 (`UT100Roll`) | XAUUSD (Spot Gold) | Rationale |
|---|---|---|---|
| **Accumulation Session** | 10:00 - 16:00 Broker | 10:00 - 16:00 Broker | 6-hour London Session builds statistically valid High & Low boundaries |
| **Execution Window** | 16:30 - 22:30 Broker | 16:30 - 22:30 Broker | New York Cash Open to Late NY Session |
| **Minimum London Range** | **$\ge 140.0$ points** | **$\ge 55.0$ points** | Eliminates low-volatility dead chop days |
| **Trigger Condition** | Price sweeps High/Low then M1 closes back inside | Price sweeps High/Low then M1 closes back inside | Confirmation of false breakout rejection |
| **Stop Loss** | Extreme wick $\pm$ buffer (ATR) | Extreme wick $\pm$ buffer (ATR) | Capped strictly to $1.00R$ ($25.00 cash on $10k account) |
| **Take Profit** | **London Midpoint** $\left(\frac{\text{High} + \text{Low}}{2}\right)$ | **London Midpoint** $\left(\frac{\text{High} + \text{Low}}{2}\right)$ | Objective equilibrium target |
| **Risk per Trade** | 0.25% of equity ($25.00) | 0.25% of equity ($25.00) | Institutional capital preservation standard |

---

### 3. Empirical Results from Gate 2 Forward Shadow Execution

1. **Trade #1000 (US100 BUY at 2026.09.29 21:00):**
   - Entry: `30,250.30` | SL: `30,238.26` | TP: `30,342.50`
   - Outcome: Hit TP at 21:23:01.
   - Profit: **+$191.50 (+7.66R / +1.92% portfolio growth)**.

2. **Trade #1001 (US100 SELL at 2026.09.30 16:33):**
   - Entry: `30,484.62` | SL: `30,536.44` | TP: `30,371.46`
   - Outcome: Hit SL at 16:59:00.
   - PnL: **-$25.00 (-1.00R / -0.24% portfolio loss)**.

**Combined Performance:** Net **+$166.50 (+6.66R)** | Balance **$10,166.50** | Profit Factor **7.66** | Win Rate **50%**.
