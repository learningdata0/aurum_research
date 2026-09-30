# 🏛️ AURUM Institutional Quantitative Desk

> **«عقل يبحث ويحاكي بسرعة البرق في المختبر، ويد تتداول بتمهل صياد محترف في السوق المباشر»**

Welcome to the institutional knowledge base and operational documentation for the **AURUM Dual-Asset Quantitative Desk**.

---

### Executive Mandate
- **Core Asset Universe:** **`US100` (`UT100Roll`)** and **`XAUUSD` (Spot Gold)**.
- **US30 Mandate:** Strictly paused for 30 days to ensure 100% focused empirical development on Gold and Nasdaq.
- **Current Operational Phase:** **Gate 2 (Forward Shadow Trading Validation)**:
    - Target: **30 consecutive verified forward paper trades** executed live via MetaTrader 5 Expert Advisors (`AurumH17ShadowEA` and `AurumGoldH17ShadowEA`).
    - Current Progress: **2 / 30 trades completed** | **Portfolio Balance: $10,166.50 (+1.66% / +6.66R net)** | **Profit Factor: 7.66**.
    - Risk Mode: **100% Virtual Riskless Forward Execution** (`InpVirtualMode = true`).

---

### Core Tenets of the AURUM Desk
1. **Zero Emotional Bias:** Decisions are governed strictly by empirical liquidity laws and historical microstructures verified over 800,000+ M1 bars.
2. **Mathematical Risk Asymmetry:** We risk $1.00R$ to target $2.5R$ to $8.0R$+. A 50% win rate yields dominant double-digit portfolio expansion.
3. **Episodic Causal Memory:** The system remembers why the market moved, tracking geopolitical catalysts (Trump trade policies, Iran / Strait of Hormuz conflict, oil price spikes, Federal Reserve interest rates) and connecting them to institutional flow.
4. **Intraday Temporal Discipline:** We strictly respect the 5 sub-sessions of the day, accumulating London High and Low from 10:00 to 16:00, and unleashing sweep-reclaim entries during the New York session (16:30 to 22:30).

---

### Documentation Sections
- [**System Architecture**](architecture/overview.md): Full end-to-end software pipeline and MQL5-Python bridge.
- [**H17 London Sweep & Reclaim**](strategies/h17_london_sweep.md): Structural mechanics of the liquidity trap strategy.
- [**Intraday Market Clock**](strategies/market_clock.md): Quantitative profile across the 5 daily sub-sessions.
- [**Institutional Research Report**](research/institutional_lab.md): Walk-forward, Monte Carlo, and stress tests.
- [**Causal Macro Journal**](memory/journal.md): Persistent market memory and daily trade post-mortems.
- [**Forward Shadow Ledger**](live/gate2_ledger.md): Live log of all Gate 2 forward paper executions.
