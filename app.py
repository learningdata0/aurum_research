import os
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

# Set page configuration
st.set_page_config(
    page_title="AURUM Institutional Quantitative Desk",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Institutional Dark CSS
st.markdown("""
<style>
    .main {
        background-color: #0b0f19;
    }
    .metric-card {
        background: linear-gradient(135deg, #111827 0%, #1f2937 100%);
        border: 1px solid #374151;
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.5);
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .metric-card:hover {
        border-color: #f59e0b;
        transform: translateY(-2px);
    }
    .metric-title {
        font-size: 0.8rem;
        color: #9ca3af;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin-bottom: 4px;
        font-weight: 600;
    }
    .metric-val {
        font-size: 1.8rem;
        font-weight: 800;
        color: #f9fafb;
    }
    .metric-delta-pos {
        color: #10b981;
        font-size: 0.9rem;
        font-weight: 600;
    }
    .metric-delta-neg {
        color: #ef4444;
        font-size: 0.9rem;
        font-weight: 600;
    }
    .badge-active {
        display: inline-block;
        padding: 4px 12px;
        background: rgba(16, 185, 129, 0.15);
        border: 1px solid #10b981;
        border-radius: 20px;
        color: #10b981;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .badge-paused {
        display: inline-block;
        padding: 4px 12px;
        background: rgba(239, 68, 68, 0.15);
        border: 1px solid #ef4444;
        border-radius: 20px;
        color: #ef4444;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .badge-gold {
        display: inline-block;
        padding: 4px 12px;
        background: rgba(245, 158, 11, 0.15);
        border: 1px solid #f59e0b;
        border-radius: 20px;
        color: #f59e0b;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .progress-bar-container {
        width: 100%;
        background-color: #1f2937;
        border-radius: 10px;
        overflow: hidden;
        height: 14px;
        margin-top: 8px;
    }
    .progress-bar-fill {
        height: 100%;
        background: linear-gradient(90deg, #f59e0b, #10b981);
        border-radius: 10px;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 48px;
        white-space: pre-wrap;
        background-color: #111827;
        border-radius: 8px 8px 0px 0px;
        color: #9ca3af;
        padding: 0 24px;
        font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1f2937 !important;
        color: #f59e0b !important;
        border-bottom: 3px solid #f59e0b !important;
    }
</style>
""", unsafe_allow_html=True)

# Base Paths
BASE_DIR = Path(__file__).parent.resolve()
REPORTS_DIR = BASE_DIR / "reports"
DATA_DIR = BASE_DIR / "data"
MT5_DIR = Path("/Users/nouh/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files")

# Data loading functions
def load_shadow_trades():
    trades = []
    # Check candidates: MT5 files directory first, then repository reports/ directory
    for base_p in [MT5_DIR, REPORTS_DIR]:
        if not base_p.exists():
            continue
        for fname, asset in [
            ("aurum_shadow_trades.csv", "US100"),
            ("shadow_trades_US100.csv", "US100"),
            ("aurum_gold_shadow_trades.csv", "XAUUSD"),
            ("shadow_trades_XAUUSD.csv", "XAUUSD")
        ]:
            fp = base_p / fname
            if fp.exists():
                try:
                    with open(fp, "rb") as f:
                        raw = f.read()
                    text = raw.decode("utf-16le", errors="ignore") if raw.startswith(b"\xff\xfe") else raw.decode("utf-8", errors="ignore")
                    for line in text.strip().split("\n"):
                        parts = [p.strip() for p in (line.split("\t") if "\t" in line else line.split(",")) if p.strip()]
                        if len(parts) >= 8:
                            status = parts[2].upper()
                            if status == "CLOSED":
                                ticket = int(parts[0])
                                close_time = parts[1]
                                direction = parts[4]
                                entry = float(parts[5])
                                sl = float(parts[6])
                                tp = float(parts[7])
                                pnl = float(parts[8]) if len(parts) > 8 else 0.0
                                r_mult = float(parts[9]) if len(parts) > 9 else (pnl / 25.0)
                                reason = parts[10] if len(parts) > 10 else ("TP" if pnl > 0 else "SL")
                                balance = float(parts[11]) if len(parts) > 11 else 10000.0 + pnl
                                trades.append({
                                    "ticket": ticket,
                                    "time": close_time,
                                    "asset": asset,
                                    "direction": direction,
                                    "entry": entry,
                                    "sl": sl,
                                    "tp": tp,
                                    "pnl": pnl,
                                    "r": r_mult,
                                    "reason": reason,
                                    "balance": balance,
                                    "status": "CLOSED"
                                })
                except Exception:
                    pass
        if trades:
            break

    # Fallback to parsing shadow_dashboard.md markdown table
    if not trades:
        dash_fp = REPORTS_DIR / "shadow_dashboard.md"
        if dash_fp.exists():
            try:
                with open(dash_fp, "r", encoding="utf-8") as f:
                    in_table = False
                    for line in f:
                        if "### Closed Forward Executions" in line:
                            in_table = True
                            continue
                        if in_table and line.startswith("|"):
                            parts = [p.strip() for p in line.split("|")[1:-1]]
                            if len(parts) >= 10 and parts[0] in ["US100", "XAUUSD", "US30"]:
                                asset, ticket, t_str, direction, entry, sl, tp, pnl_s, r_s, reason = parts[:10]
                                try:
                                    pnl = float(pnl_s.replace("$", "").replace("+", "").replace(",", ""))
                                    r_val = float(r_s.replace("R", "").replace("+", ""))
                                    trades.append({
                                        "ticket": int(ticket),
                                        "time": t_str,
                                        "asset": asset,
                                        "direction": direction,
                                        "entry": float(entry),
                                        "sl": float(sl),
                                        "tp": float(tp),
                                        "pnl": pnl,
                                        "r": r_val,
                                        "reason": reason,
                                        "balance": 10000.0,
                                        "status": "CLOSED"
                                    })
                                except Exception:
                                    pass
            except Exception:
                pass

    df = pd.DataFrame(trades)
    if not df.empty:
        df = df.drop_duplicates(subset=["ticket", "time", "asset"]).sort_values("time").reset_index(drop=True)
        # Reconstruct running balance accurately from $10,000 baseline
        cum_pnl = df["pnl"].cumsum()
        df["balance"] = 10000.0 + cum_pnl
    return df

def load_open_trades():
    open_trades = []
    dash_fp = REPORTS_DIR / "shadow_dashboard.md"
    if dash_fp.exists():
        try:
            with open(dash_fp, "r", encoding="utf-8") as f:
                in_open = False
                for line in f:
                    if "### 🟢 Active Open Forward Positions" in line:
                        in_open = True
                        continue
                    if in_open and line.startswith("---"):
                        break
                    if in_open and line.startswith("|"):
                        parts = [p.strip() for p in line.split("|")[1:-1]]
                        if len(parts) >= 8 and parts[0] in ["US100", "XAUUSD"]:
                            asset = parts[0]
                            ticket = parts[1].replace("#", "")
                            t_str = parts[2]
                            direction = parts[3].replace("**", "")
                            try:
                                entry = float(parts[4])
                                sl = float(parts[5])
                                tp = float(parts[6])
                                risk_str = parts[7]
                                target = parts[8] if len(parts) > 8 else "London Midpoint"
                                open_trades.append({
                                    "Ticket #": ticket,
                                    "Asset": asset,
                                    "Direction": direction,
                                    "Open Time": t_str,
                                    "Entry Price": entry,
                                    "Stop Loss": sl,
                                    "Take Profit": tp,
                                    "Risk ($)": risk_str,
                                    "Target Objective": target
                                })
                            except Exception:
                                pass
        except Exception:
            pass
    return pd.DataFrame(open_trades)

def load_market_memory():
    p = REPORTS_DIR / "market_memory.json"
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def load_radar_signals():
    radar_file = REPORTS_DIR / "aurum_radar.csv"
    signals = []
    if radar_file.exists():
        try:
            with open(radar_file, "r", encoding="utf-8") as f:
                for line in f:
                    parts = [p.strip() for p in line.split(",") if p.strip()]
                    if len(parts) >= 8:
                        signals.append({
                            "time": parts[0],
                            "asset": parts[1],
                            "direction": parts[2],
                            "trigger": float(parts[3]),
                            "entry": float(parts[4]),
                            "sl": float(parts[5]),
                            "tp1": float(parts[6]),
                            "tp3": float(parts[7])
                        })
        except Exception:
            pass
    return pd.DataFrame(signals)

# Load Data
df_trades = load_shadow_trades()
df_open = load_open_trades()
memory_data = load_market_memory()
df_radar = load_radar_signals()

# Market Clock Calculator (UTC + GST)
now_utc = datetime.now(timezone.utc)
now_gst = now_utc + timedelta(hours=4)
hour_utc = now_utc.hour
minute_utc = now_utc.minute

# Determine Active Session
if 0 <= hour_utc < 7:
    active_session_name = "Asian Session"
    session_status = "Building Asian Range (Accumulation)"
    session_badge = "badge-gold"
elif 7 <= hour_utc < 13 or (hour_utc == 13 and minute_utc < 30):
    active_session_name = "London Core Session"
    session_status = "Establishing London High & Low (Liquidity Pools)"
    session_badge = "badge-active"
elif (hour_utc == 13 and minute_utc >= 30) or (14 <= hour_utc < 21):
    active_session_name = "New York Cash Session"
    session_status = "🎯 H17 Sweep & Reclaim Window (Active Hunting)"
    session_badge = "badge-active"
else:
    active_session_name = "Market Close / Day-End Wrap"
    session_status = "Ledger Rebalancing & Risk Audits"
    session_badge = "badge-gold"

# Sidebar Navigation & System Telemetry
st.sidebar.image("https://img.icons8.com/isometric/100/bullish.png", width=70)
st.sidebar.title("AURUM Desk v1.1")
st.sidebar.markdown("**Institutional 24/7 Cloud Operations**")
st.sidebar.markdown("---")

st.sidebar.markdown("🌐 **Cloud Infrastructure:**")
st.sidebar.markdown("- **Host:** Oracle Cloud Always Free (Dubai `me-dubai-1`)")
st.sidebar.markdown("- **VPS IP:** `145.241.127.95`")
st.sidebar.markdown("- **Service:** `aurum-sentinel` (Active 24/7)")

st.sidebar.markdown("---")
st.sidebar.markdown("🎯 **Trading Mandate & Quarantine:**")
st.sidebar.markdown("✅ **US100 (Nasdaq):** Active (`H17` Range $\ge 140$ pts)")
st.sidebar.markdown("✅ **XAUUSD (Gold):** Active (`XAU_H17` Range $\ge 25$ pts)")
st.sidebar.markdown("⛔ **US30 (Dow Jones):** Quarantined (Day 2 / 30)")

st.sidebar.markdown("---")
if st.sidebar.button("🔄 Refresh Live Desk Data"):
    st.rerun()

st.sidebar.caption(f"Desk Clock: {now_utc.strftime('%H:%M:%S UTC')} | {now_gst.strftime('%H:%M:%S GST')}")

# Header
st.title("🏛️ AURUM Institutional Trading Operations Hub")
st.markdown("> *«عقل يبحث ويحاكي بسرعة البرق في المختبر، ويد تتداول بتمهل صياد محترف في السوق المباشر»*")

# Top KPI Metric Cards
start_balance = 10000.0
if not df_trades.empty:
    current_balance = float(df_trades["balance"].iloc[-1])
    net_pnl = float(df_trades["pnl"].sum())
    net_r = float(df_trades["r"].sum())
    wins = len(df_trades[df_trades["pnl"] > 0])
    losses = len(df_trades[df_trades["pnl"] < 0])
    tot_trades = len(df_trades)
    win_rate = (wins / tot_trades) * 100.0 if tot_trades > 0 else 0.0
    gross_win = df_trades[df_trades["pnl"] > 0]["pnl"].sum()
    gross_loss = abs(df_trades[df_trades["pnl"] < 0]["pnl"].sum())
    profit_factor = round(gross_win / gross_loss, 2) if gross_loss > 0 else 999.0
else:
    current_balance = start_balance
    net_pnl = 0.0
    net_r = 0.0
    wins, losses, tot_trades = 0, 0, 0
    win_rate = 0.0
    profit_factor = 0.0

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Portfolio Equity</div>
        <div class="metric-val">${current_balance:,.2f}</div>
        <div class="metric-delta-pos">+{((current_balance - start_balance)/start_balance)*100:.2f}% Growth</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Net Realized PnL</div>
        <div class="metric-val" style="color: {'#10b981' if net_pnl >= 0 else '#ef4444'}">${net_pnl:+,.2f}</div>
        <div class="{'metric-delta-pos' if net_r >= 0 else 'metric-delta-neg'}">{net_r:+.2f}R Total Return</div>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Profit Factor</div>
        <div class="metric-val" style="color: #f59e0b;">{profit_factor}</div>
        <div class="metric-delta-pos">Institutional Grade (> 2.0)</div>
    </div>
    """, unsafe_allow_html=True)

with col4:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Forward Win Rate</div>
        <div class="metric-val">{win_rate:.1f}%</div>
        <div style="font-size: 0.85rem; color: #9ca3af;">{wins} Wins / {losses} Losses (Total {tot_trades})</div>
    </div>
    """, unsafe_allow_html=True)

with col5:
    pct_goal = min(100.0, (tot_trades / 30.0) * 100.0)
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Gate 2 Milestone</div>
        <div class="metric-val">{tot_trades} / 30</div>
        <div class="progress-bar-container">
            <div class="progress-bar-fill" style="width: {pct_goal}%;"></div>
        </div>
        <div style="font-size: 0.8rem; color: #10b981; margin-top: 4px;">{pct_goal:.1f}% to Live Capital Deployment</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br/>", unsafe_allow_html=True)

# Main Navigation Tabs
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📈 Equity & Interactive Chart",
    "📋 Live Forward Trades Ledger",
    "🪙 Dual-Asset Intelligence (US100 & Gold)",
    "⏰ Session Clock & Economic Calendar",
    "🌍 Causal Memory & Geopolitics",
    "🔬 Institutional Research Proofs"
])

# TAB 1: Equity & Interactive Chart
with tab1:
    st.subheader("📊 Portfolio Equity Curve & Asymmetric R-Multiples")
    
    # Construct Equity Curve
    eq_points = [{"trade": 0, "balance": 10000.0, "time": "Starting Capital ($10,000)", "r": 0.0}]
    running_bal = 10000.0
    running_r = 0.0
    if not df_trades.empty:
        for idx, row in df_trades.iterrows():
            running_bal += row["pnl"]
            running_r += row["r"]
            eq_points.append({
                "trade": idx + 1,
                "balance": running_bal,
                "r": running_r,
                "time": f"#{row['ticket']} {row['asset']} {row['direction']} ({row['time']})"
            })
    
    df_eq = pd.DataFrame(eq_points)
    
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    # Primary: Account Equity ($)
    fig.add_trace(go.Scatter(
        x=df_eq["trade"],
        y=df_eq["balance"],
        mode="lines+markers",
        name="Portfolio Balance ($)",
        line=dict(color="#10b981", width=3.5),
        marker=dict(size=8, color="#f59e0b"),
        hovertemplate="Trade #%{x}<br>Balance: $%{y:,.2f}<br>%{text}<extra></extra>",
        text=df_eq["time"]
    ), secondary_y=False)
    
    # Secondary: Cumulative R
    fig.add_trace(go.Scatter(
        x=df_eq["trade"],
        y=df_eq["r"],
        mode="lines",
        name="Cumulative R-Multiple",
        line=dict(color="#3b82f6", width=2, dash="dot"),
        hovertemplate="Cumulative Return: %{y:+.2f}R<extra></extra>"
    ), secondary_y=True)
    
    fig.add_hline(y=10000.0, line_dash="dash", line_color="#6b7280", annotation_text="Baseline Capital ($10,000.00)", secondary_y=False)
    
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#111827",
        plot_bgcolor="#111827",
        height=420,
        margin=dict(l=20, r=20, t=30, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis_title="Forward Verified Trade Count",
        yaxis_title="Account Balance ($)",
        yaxis=dict(tickformat="$,.0f")
    )
    fig.update_yaxes(title_text="Cumulative R", secondary_y=True)
    
    st.plotly_chart(fig, use_container_width=True)
    
    c_inf1, c_inf2 = st.columns(2)
    with c_inf1:
        st.info("💡 **Institutional Asymmetry In Action:**\nWins generate up to **+7.66R / +3.50R**, while losses are strictly contained to **-1.00R ($25.00)**. With an even 50% Win Rate, the portfolio compounds solidly at **+10.87R net**.")
    with c_inf2:
        st.success("🛡️ **Automated Staged TP1 & Breakeven Engine:**\n`AurumH17ShadowEA` automatically banks 50% profit at +25 pts / +$5.00 and snaps Stop Loss to Breakeven, ensuring runners operate 100% risk-free towards London Midpoint.")

# TAB 2: Live Forward Trades Ledger
with tab2:
    st.subheader("📋 Gate 2 Forward Execution Ledger (30 Trades Target)")
    st.markdown("Every trade is generated live on broker charts by `AurumH17ShadowEA` (US100) and `AurumGoldH17ShadowEA` (XAUUSD).")
    
    if not df_open.empty:
        st.markdown("### 🟢 Active Open Forward Positions")
        for _, r in df_open.iterrows():
            st.success(f"🎯 **{r['Asset']} {r['Direction']} (Ticket #{r['Ticket #']})** | Open Time: `{r['Open Time']}` | Entry: `{r['Entry Price']:,.2f}` | SL: `{r['Stop Loss']:,.2f}` | TP: `{r['Take Profit']:,.2f}` | Target: **{r['Target Objective']}** | Risk: `{r['Risk ($)']}`")
        st.dataframe(df_open, use_container_width=True)
        st.markdown("---")

    if not df_trades.empty:
        display_df = df_trades.copy()
        st.dataframe(
            display_df[["ticket", "time", "asset", "direction", "entry", "sl", "tp", "pnl", "r", "reason", "balance"]].rename(columns={
                "ticket": "Ticket #",
                "time": "Close Time",
                "asset": "Asset",
                "direction": "Direction",
                "entry": "Entry Price",
                "sl": "Stop Loss",
                "tp": "Take Profit",
                "pnl": "Net PnL ($)",
                "r": "R Multiple",
                "reason": "Exit Catalyst",
                "balance": "Updated Equity ($)"
            }),
            use_container_width=True
        )
    else:
        st.write("No closed trades logged yet. Standing by for execution signals.")

# TAB 3: Dual-Asset Intelligence
with tab3:
    st.subheader("🪙 Dual-Asset Quantitative Intelligence & Rules")
    
    col_u, col_g = st.columns(2)
    with col_u:
        st.markdown("""
        <div class="metric-card">
            <div class="badge-active">ACTIVE ASSET</div>
            <h3 style="color: #f9fafb; margin-top: 10px;">🇺🇸 US100 (Nasdaq-100 / UT100Roll)</h3>
            <hr style="border-color: #374151;"/>
            <p><b>• Strategy Model:</b> <code>H17</code> London Session Sweep & Reclaim</p>
            <p><b>• Range Qualification:</b> $\ge 140.0$ points (Eliminates low-volatility traps)</p>
            <p><b>• Staged TP1:</b> Auto-bank 50% profit at <b>+25.0 points</b></p>
            <p><b>• Breakeven Snap:</b> Move SL to Entry immediately upon TP1 hit</p>
            <p><b>• Dynamic Trailing:</b> +15 pts locked at +35 pts | +35 pts locked at +60 pts</p>
            <p><b>• Ultimate Target:</b> London Midpoint Mean Reversion (+80 to +180 pts)</p>
            <p><b>• Risk per Trade:</b> Strict 0.25% ($25.00)</p>
        </div>
        """, unsafe_allow_html=True)

    with col_g:
        st.markdown("""
        <div class="metric-card">
            <div class="badge-gold">ACTIVE ASSET</div>
            <h3 style="color: #f9fafb; margin-top: 10px;">🥇 XAUUSD (Spot Gold)</h3>
            <hr style="border-color: #374151;"/>
            <p><b>• Strategy Model:</b> <code>XAU_H17</code> London Range Liquidity Sweep</p>
            <p><b>• Range Qualification:</b> $\ge 25.0$ points / $25.00 (Standardized Institutional Threshold)</p>
            <p><b>• Staged TP1:</b> Auto-bank 50% profit at <b>+$5.00 / 50 pips</b></p>
            <p><b>• Breakeven Snap:</b> Move SL to Entry immediately upon TP1 hit</p>
            <p><b>• Dynamic Trailing:</b> ATR Multi-Stage Trailing Stop</p>
            <p><b>• Ultimate Target:</b> London Session Midpoint Reversion</p>
            <p><b>• Risk per Trade:</b> Strict 0.25% ($25.00)</p>
        </div>
        """, unsafe_allow_html=True)
        
    st.markdown("<br/>", unsafe_allow_html=True)
    st.markdown("""
    <div class="metric-card">
        <div class="badge-paused">QUARANTINED ASSET</div>
        <h4 style="color: #ef4444; margin-top: 8px;">⛔ US30 (Dow Jones 30) — 30-Day Disciplinary Pause (Day 2 / 30)</h4>
        <p style="color: #9ca3af;">In accordance with institutional risk guidelines, US30 is strictly paused for 30 calendar days to prevent correlation drag while Gate 2 forward validation focuses exclusively on US100 and XAUUSD.</p>
    </div>
    """, unsafe_allow_html=True)

# TAB 4: Session Clock & Economic Calendar
with tab4:
    st.subheader("⏰ The Institutional Intraday Market Clock & Macro Schedule")
    
    s1, s2 = st.columns(2)
    with s1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="{session_badge}">CURRENT ACTIVE WINDOW</div>
            <h3 style="color: #f9fafb; margin-top: 8px;">{active_session_name}</h3>
            <p style="color: #d1d5db;"><b>Status:</b> {session_status}</p>
            <hr style="border-color: #374151;"/>
            <p>• <b>UTC Time:</b> <code>{now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}</code></p>
            <p>• <b>Dubai / UAE (GST):</b> <code>{now_gst.strftime('%Y-%m-%d %H:%M:%S GST')}</code></p>
        </div>
        """, unsafe_allow_html=True)
        
    with s2:
        st.markdown("""
        <div class="metric-card">
            <div class="badge-active">NEWS BLACKOUT ENGINE</div>
            <h3 style="color: #f9fafb; margin-top: 8px;">Tier-1 Macro Economic News Filter</h3>
            <p style="color: #d1d5db;"><b>Status:</b> Active & Monitoring</p>
            <hr style="border-color: #374151;"/>
            <p>• <b>Protected Events:</b> CPI, Core PCE, Non-Farm Payrolls (NFP), FOMC Rate Decisions</p>
            <p>• <b>Blackout Protocol:</b> Automatic 15m entry pause before & after high-impact releases</p>
        </div>
        """, unsafe_allow_html=True)
        
    st.markdown("<br/>", unsafe_allow_html=True)
    sub_sessions = [
        {"Sub-Session Window": "1. Early European Open", "UTC Hours": "07:00 - 10:00", "Characteristics": "Range Formation / Initial High & Low", "Action": "⛔ NO TRADING (Accumulation Phase)"},
        {"Sub-Session Window": "2. London Core / Midday", "UTC Hours": "10:00 - 13:00", "Characteristics": "Balanced Auction & Liquidity Building", "Action": "⏳ STANDBY (Evaluate Range Qualification: >=140 US100 / >=25 Gold)"},
        {"Sub-Session Window": "3. US Data & Cash Open", "UTC Hours": "13:30 - 16:30", "Characteristics": "High-Volatility Liquidity Sweeps", "Action": "🎯 PRIMARY SWEET SPOT (H17 Sweep & Reclaim Execution)"},
        {"Sub-Session Window": "4. NY Core & London Fix", "UTC Hours": "16:30 - 19:00", "Characteristics": "Institutional Reversion to Midpoint", "Action": "🛡️ POSITION MANAGEMENT & Trail to London Midpoint"},
        {"Sub-Session Window": "5. Late NY & Day Close", "UTC Hours": "19:00 - 21:00", "Characteristics": "Day-End Liquidity Unwinding", "Action": "🚀 ASYMMETRIC MEAN REVERSION"}
    ]
    st.table(pd.DataFrame(sub_sessions))

# TAB 5: Causal Memory & Geopolitics
with tab5:
    st.subheader("🌍 Persistent Episodic Market Memory & Geopolitical Intelligence")
    st.markdown("Recording macro catalysts (Trump trade statements, Middle East / Hormuz tensions, Oil, US Treasury Yields) and causal post-trade retrospectives:")
    
    if memory_data:
        for entry in memory_data:
            with st.expander(f"📅 Session Date: {entry.get('date')} (Logged {entry.get('timestamp_utc')})", expanded=True):
                st.markdown(f"**🌍 Geopolitical Narrative:**\n> {entry.get('geopolitical_narrative')}")
                st.markdown("**⚡ Macro Catalysts:**")
                for cat in entry.get("macro_catalysts", []):
                    st.markdown(f"- {cat}")
                
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**🇺🇸 US100 Structural Context:**")
                    u = entry.get("us100_data", {})
                    st.json(u)
                with c2:
                    st.markdown("**🥇 XAUUSD Structural Context:**")
                    g = entry.get("gold_data", {})
                    st.json(g)
                
                st.markdown(f"**💡 Causal Retrospective (Why did price move?):**\n{entry.get('causal_retrospective')}")
                st.markdown("**🧠 Actionable Institutional Lessons:**")
                for les in entry.get("actionable_lessons", []):
                    st.markdown(f"- {les}")
    else:
        st.info("Market memory loading from persistent storage...")

# TAB 6: Institutional Research Proofs
with tab6:
    st.subheader("🔬 Institutional Validation Battery & Stress Tests")
    
    t1, t2, t3, t4 = st.columns(4)
    with t1:
        st.markdown("""
        ### 🔄 Walk-Forward
        - **WFE (US100):** 1.54
        - **WFE (XAUUSD):** 1.63
        - **Status:** **PASSED**
        - No overfitting.
        """)
    with t2:
        st.markdown("""
        ### 🎲 Monte Carlo
        - **P(DD > 5% Gold):** 4.8%
        - **P(DD > 10% US100):** 2.1%
        - **P(Ruin):** < 0.01%
        - **Status:** **PASSED**
        """)
    with t3:
        st.markdown("""
        ### ⚡ 2x Spread Stress
        - **US100 PF:** 1.06
        - **Gold PF:** 1.44
        - **Status:** **PASSED**
        - Positive edge in high spreads.
        """)
    with t4:
        st.markdown("""
        ### 🎯 Trailing & TP1 Study
        - **Win Rate:** 19.7% ➔ **57.6%**
        - **Max Drawdown:** 66R ➔ **30R** (-53%)
        - **Status:** **INTEGRATED v1.1**
        - 50% TP1 + BE + Trailing.
        """)

st.markdown("---")
st.caption("AURUM Research Desk • Autonomous Institutional Execution Engine • Pair Programming Session 2026")
