# 🏗️ AURUM System Architecture

```mermaid
flowchart TD
    subgraph Market [Live Market Feeds]
        MT5["MetaTrader 5 Terminal<br/>(Wine / macOS / Windows)"]
    end

    subgraph MQL5_Engine [MQL5 Native Shadow Execution]
        EA_US100["AurumH17ShadowEA.mq5<br/>(UT100Roll M1)"]
        EA_GOLD["AurumGoldH17ShadowEA.mq5<br/>(XAUUSD M1)"]
        CSV_LOGS["Files/aurum_shadow_trades.csv<br/>Files/aurum_gold_shadow_trades.csv"]
    end

    subgraph Python_Desk [Python Institutional Intelligence]
        DAEMON["src/shadow_daemon.py<br/>(Live Poller & Watcher)"]
        MEMORY["src/market_memory.py<br/>(Episodic Memory Engine)"]
        MACRO["src/macro_intel.py<br/>(Geopolitical Engine)"]
        TEMPORAL["src/temporal_profiler.py<br/>(Sub-session Profiler)"]
        LAB["src/institutional_lab.py<br/>(Backtest & Stress Engine)"]
    end

    subgraph UI_Cloud [Web & Cloud Presentation Layer]
        STREAMLIT["Streamlit Operations Hub<br/>(app.py)"]
        MKDOCS["MkDocs Material Portal<br/>(GitHub Pages)"]
        TELEGRAM["Telegram Alert Bot<br/>(src/telegram_notifier.py)"]
    end

    MT5 --> EA_US100 & EA_GOLD
    EA_US100 & EA_GOLD --> CSV_LOGS
    CSV_LOGS --> DAEMON
    DAEMON --> STREAMLIT
    DAEMON --> TELEGRAM
    MEMORY & MACRO & TEMPORAL & LAB --> MKDOCS
    MEMORY --> STREAMLIT
```

---

### Component Overview
1. **MetaTrader 5 Client:**
   - Runs `AurumH17ShadowEA` on `UT100Roll, M1` and `AurumGoldH17ShadowEA` on `XAUUSD, M1`.
   - Accumulates session extremes on every tick, locking London High, Low, and Midpoint at 16:00 broker time.
   - Evaluates false breakouts during NY Cash Open (16:30 - 22:30).
   - Writes tickets, entries, SL, TP, and outcomes to tab-delimited CSV logs with sub-millisecond precision.

2. **Python Institutional Daemon (`shadow_daemon.py`):**
   - Polls MT5 files every 15 seconds.
   - Generates consolidated Markdown dashboards (`reports/shadow_dashboard.md`).
   - Syncs active trade events directly to the Streamlit app and Telegram Notifier.

3. **Presentation & Cloud Infrastructure:**
   - **Streamlit Cloud (`app.py`):** Interactive web dashboard displaying equity curves, live trade tables, intraday sub-session matrix, and macro memory.
   - **MkDocs Material Portal:** Institutional documentation site ready for deployment on GitHub Pages.
   - **Telegram Notifier:** Real-time push notification bot sending alerts directly to mobile devices.
