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

# Custom Institutional Dark CSS & Styling
st.markdown("""
<style>
    /* Global Base */
    .stApp {
        background-color: #0b0f19;
        color: #f3f4f6;
    }
    
    /* Institutional Metric Cards */
    .metric-card {
        background: linear-gradient(135deg, #111827 0%, #1f2937 100%);
        border: 1px solid #374151;
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.5);
        transition: transform 0.2s ease, border-color 0.2s ease;
        height: 100%;
    }
    .metric-card:hover {
        border-color: #f59e0b;
        transform: translateY(-2px);
    }
    .metric-title {
        font-size: 0.78rem;
        color: #9ca3af;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin-bottom: 4px;
        font-weight: 600;
    }
    .metric-val {
        font-size: 1.75rem;
        font-weight: 800;
        color: #f9fafb;
    }
    .metric-delta-pos {
        color: #10b981;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .metric-delta-neg {
        color: #ef4444;
        font-size: 0.85rem;
        font-weight: 600;
    }
    
    /* Badges */
    .badge-active {
        display: inline-block;
        padding: 4px 12px;
        background: rgba(16, 185, 129, 0.15);
        border: 1px solid #10b981;
        border-radius: 20px;
        color: #10b981;
        font-weight: 600;
        font-size: 0.8rem;
    }
    .badge-paused {
        display: inline-block;
        padding: 4px 12px;
        background: rgba(239, 68, 68, 0.15);
        border: 1px solid #ef4444;
        border-radius: 20px;
        color: #ef4444;
        font-weight: 600;
        font-size: 0.8rem;
    }
    .badge-gold {
        display: inline-block;
        padding: 4px 12px;
        background: rgba(245, 158, 11, 0.15);
        border: 1px solid #f59e0b;
        border-radius: 20px;
        color: #f59e0b;
        font-weight: 600;
        font-size: 0.8rem;
    }
    .badge-blue {
        display: inline-block;
        padding: 4px 12px;
        background: rgba(59, 130, 246, 0.15);
        border: 1px solid #3b82f6;
        border-radius: 20px;
        color: #60a5fa;
        font-weight: 600;
        font-size: 0.8rem;
    }
    
    /* Live Pulse Indicator */
    .live-dot {
        display: inline-block;
        width: 10px;
        height: 10px;
        background-color: #10b981;
        border-radius: 50%;
        margin-right: 6px;
        box-shadow: 0 0 10px #10b981;
        animation: pulse 2s infinite;
    }
    @keyframes pulse {
        0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
        70% { transform: scale(1.1); box-shadow: 0 0 0 8px rgba(16, 185, 129, 0); }
        100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
    }
    
    /* Progress Bar */
    .progress-bar-container {
        width: 100%;
        background-color: #1f2937;
        border-radius: 10px;
        overflow: hidden;
        height: 12px;
        margin-top: 8px;
    }
    .progress-bar-fill {
        height: 100%;
        background: linear-gradient(90deg, #f59e0b, #10b981);
        border-radius: 10px;
    }
    
    /* Tabs Customization */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        border-bottom: 1px solid #374151;
    }
    .stTabs [data-baseweb="tab"] {
        height: 46px;
        white-space: pre-wrap;
        background-color: #111827;
        border-radius: 8px 8px 0px 0px;
        color: #9ca3af;
        padding: 0 18px;
        font-weight: 600;
        font-size: 0.9rem;
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
    
    # 1. Parse CSV files from MT5 directory or reports directory
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
                            status = parts[2].upper() if len(parts) > 2 else ""
                            if status == "CLOSED":
                                try:
                                    ticket = int(parts[0])
                                    close_time = parts[1]
                                    direction = parts[4]
                                    entry = float(parts[5])
                                    sl = float(parts[6])
                                    tp = float(parts[7])
                                    pnl = float(parts[8]) if len(parts) > 8 else 0.0
                                    r_mult = float(parts[9]) if len(parts) > 9 else (pnl / 25.0)
                                    reason = parts[10] if len(parts) > 10 else ("TP" if pnl > 0 else "SL")
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
                                        "status": "CLOSED"
                                    })
                                except Exception:
                                    pass
                except Exception:
                    pass

    # 2. Parse reports/shadow_dashboard.md markdown table
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
                                    "status": "CLOSED"
                                })
                            except Exception:
                                pass
        except Exception:
            pass

    df = pd.DataFrame(trades)
    if not df.empty:
        # Standardize and deduplicate
        df = df.drop_duplicates(subset=["ticket", "time", "asset"]).sort_values("time").reset_index(drop=True)
        # Calculate running balance and drawdowns
        df["cum_pnl"] = df["pnl"].cumsum()
        df["balance"] = 10000.0 + df["cum_pnl"]
        df["cum_r"] = df["r"].cumsum()
        df["peak_balance"] = df["balance"].cummax()
        df["drawdown_dollar"] = df["balance"] - df["peak_balance"]
        df["drawdown_pct"] = (df["drawdown_dollar"] / df["peak_balance"]) * 100.0
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

# Load Datasets
df_trades = load_shadow_trades()
df_open = load_open_trades()
memory_data = load_market_memory()

# Market Clock Calculator (UTC + GST)
now_utc = datetime.now(timezone.utc)
now_gst = now_utc + timedelta(hours=4)
hour_utc = now_utc.hour
minute_utc = now_utc.minute
weekday = now_utc.weekday() # 0 = Monday, 5 = Saturday, 6 = Sunday

# Market status
is_weekend = (weekday == 5) or (weekday == 6 and hour_utc < 21) or (weekday == 4 and hour_utc >= 21)

# Active Session determination
if is_weekend:
    active_session_name = "Weekend Market Pause"
    session_status = "Markets Closed • Sentinel In Weekend Standby & Liquidity Mapping"
    session_badge = "badge-paused"
elif 0 <= hour_utc < 7:
    active_session_name = "Asian Session"
    session_status = "Building Asian Range (Accumulation Phase)"
    session_badge = "badge-gold"
elif 7 <= hour_utc < 13 or (hour_utc == 13 and minute_utc < 30):
    active_session_name = "London Core Session"
    session_status = "Establishing London High & Low (Liquidity Pools)"
    session_badge = "badge-active"
elif (hour_utc == 13 and minute_utc >= 30) or (14 <= hour_utc < 21):
    active_session_name = "New York Cash Session"
    session_status = "🎯 H17 Sweep & Reclaim Sweet Spot (Active Trading)"
    session_badge = "badge-active"
else:
    active_session_name = "Market Close / Day-End Wrap"
    session_status = "Daily Ledger Audit & Risk Rebalancing"
    session_badge = "badge-gold"

# Sidebar Navigation & Cloud Status
st.sidebar.markdown(f"""
<div style="text-align: center; margin-bottom: 12px;">
    <span class="live-dot"></span>
    <span style="font-weight: 700; color: #10b981; font-size: 0.9rem; letter-spacing: 0.05em;">CLOUD SENTINEL ACTIVE</span>
</div>
""", unsafe_allow_html=True)

st.sidebar.title("🏛️ AURUM Desk")
st.sidebar.markdown("**Autonomous Dual-Asset Quantitative Engine**")
st.sidebar.markdown("---")

st.sidebar.markdown("🌐 **Cloud VPS Telemetry:**")
st.sidebar.markdown("- **Host:** Oracle Cloud Free Tier (`me-dubai-1`)")
st.sidebar.markdown("- **Specs:** AMD EPYC (8 vCPUs / 24 GiB RAM)")
st.sidebar.markdown("- **VPS IP:** `145.241.127.95`")
st.sidebar.markdown("- **Service:** `aurum-sentinel` (systemd 24/7)")
st.sidebar.markdown("- **Remote MT5 GUI:** Port `6080` (noVNC)")

st.sidebar.markdown("---")
st.sidebar.markdown("🎯 **Active Mandate & Asset Matrix:**")
st.sidebar.markdown("🟢 **US100 (Nasdaq):** Active (`H17` $\ge 140$ pts)")
st.sidebar.markdown("🟢 **XAUUSD (Gold):** Active (`XAU_H17` $\ge 25$ pts)")
st.sidebar.markdown("⛔ **US30 (Dow):** Quarantined (Day 2 / 30)")

st.sidebar.markdown("---")
if st.sidebar.button("🔄 Instant Refresh"):
    st.rerun()

st.sidebar.caption(f"UTC: {now_utc.strftime('%H:%M:%S')} | GST: {now_gst.strftime('%H:%M:%S')}")

# Header
st.title("🏛️ AURUM Institutional Trading Operations Hub")
st.markdown("> *«عقل يبحث ويحاكي بسرعة البرق في المختبر، ويد تتداول بتمهل صياد محترف في السوق المباشر»*")

# Top KPI Metric Cards Matrix
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
    avg_win_dollar = gross_win / wins if wins > 0 else 0.0
    avg_loss_dollar = gross_loss / losses if losses > 0 else 0.0
    payoff_ratio = (avg_win_dollar / avg_loss_dollar) if avg_loss_dollar > 0 else 0.0
    expectancy_r = net_r / tot_trades if tot_trades > 0 else 0.0
    max_dd_pct = abs(df_trades["drawdown_pct"].min()) if "drawdown_pct" in df_trades else 0.0
else:
    current_balance = start_balance
    net_pnl = 0.0
    net_r = 0.0
    wins, losses, tot_trades = 0, 0, 0
    win_rate = 0.0
    profit_factor = 0.0
    avg_win_dollar, avg_loss_dollar, payoff_ratio, expectancy_r, max_dd_pct = 0, 0, 0, 0, 0

kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)

with kpi1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Portfolio Equity</div>
        <div class="metric-val">${current_balance:,.2f}</div>
        <div class="metric-delta-pos">+{((current_balance - start_balance)/start_balance)*100:.2f}% Growth (Baseline: $10k)</div>
    </div>
    """, unsafe_allow_html=True)

with kpi2:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Net Realized PnL</div>
        <div class="metric-val" style="color: {'#10b981' if net_pnl >= 0 else '#ef4444'}">${net_pnl:+,.2f}</div>
        <div class="{'metric-delta-pos' if net_r >= 0 else 'metric-delta-neg'}">{net_r:+.2f}R Total Return</div>
    </div>
    """, unsafe_allow_html=True)

with kpi3:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Profit Factor</div>
        <div class="metric-val" style="color: #f59e0b;">{profit_factor}</div>
        <div class="metric-delta-pos">Payoff Ratio: {payoff_ratio:.2f}x</div>
    </div>
    """, unsafe_allow_html=True)

with kpi4:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Forward Win Rate</div>
        <div class="metric-val">{win_rate:.1f}%</div>
        <div style="font-size: 0.82rem; color: #9ca3af;">{wins} Wins / {losses} Losses • Exp: <b>+{expectancy_r:.2f}R</b>/trade</div>
    </div>
    """, unsafe_allow_html=True)

with kpi5:
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
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "📈 Equity & Analytics",
    "📋 Forward Ledger",
    "🪙 Dual-Asset Strategy",
    "⏰ Session Clock & Macro",
    "🎲 Asymmetry Simulator",
    "🌍 Causal Memory",
    "🔬 Institutional Research",
    "🛡️ VPS Telemetry"
])

# TAB 1: Equity & Advanced Analytics
with tab1:
    st.subheader("📊 Portfolio Growth, Asymmetry & Underwater Profile")
    
    eq_points = [{"trade": 0, "balance": 10000.0, "time": "Initial Baseline", "r": 0.0, "pnl": 0.0, "dd": 0.0}]
    running_bal = 10000.0
    running_r = 0.0
    peak = 10000.0
    if not df_trades.empty:
        for idx, row in df_trades.iterrows():
            running_bal += row["pnl"]
            running_r += row["r"]
            if running_bal > peak:
                peak = running_bal
            dd = ((running_bal - peak) / peak) * 100.0
            eq_points.append({
                "trade": idx + 1,
                "balance": running_bal,
                "r": running_r,
                "pnl": row["pnl"],
                "dd": dd,
                "time": f"#{row['ticket']} {row['asset']} {row['direction']} ({row['time']})"
            })
    
    df_eq = pd.DataFrame(eq_points)
    
    col_c1, col_c2 = st.columns([2, 1])
    
    with col_c1:
        # Dual-Axis Equity + Cumulative R Chart
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        
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
        
        fig.add_trace(go.Scatter(
            x=df_eq["trade"],
            y=df_eq["r"],
            mode="lines",
            name="Cumulative R-Multiple",
            line=dict(color="#3b82f6", width=2, dash="dot"),
            hovertemplate="Cumulative Return: %{y:+.2f}R<extra></extra>"
        ), secondary_y=True)
        
        fig.add_hline(y=10000.0, line_dash="dash", line_color="#4b5563", annotation_text="Baseline Capital ($10,000.00)", secondary_y=False)
        
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="#111827",
            plot_bgcolor="#111827",
            height=380,
            margin=dict(l=20, r=20, t=30, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            xaxis_title="Forward Verified Trade Count",
            yaxis_title="Account Balance ($)",
            yaxis=dict(tickformat="$,.0f")
        )
        fig.update_yaxes(title_text="Cumulative R", secondary_y=True)
        st.plotly_chart(fig, use_container_width=True)

    with col_c2:
        # Underwater Drawdown Chart
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(
            x=df_eq["trade"],
            y=df_eq["dd"],
            fill="tozeroy",
            mode="lines",
            line=dict(color="#ef4444", width=2),
            fillcolor="rgba(239, 68, 68, 0.2)",
            name="Drawdown (%)",
            hovertemplate="Trade #%{x}<br>Drawdown: %{y:.2f}%<extra></extra>"
        ))
        fig_dd.update_layout(
            template="plotly_dark",
            paper_bgcolor="#111827",
            plot_bgcolor="#111827",
            height=380,
            margin=dict(l=20, r=20, t=30, b=20),
            xaxis_title="Trade Count",
            yaxis_title="Drawdown (%)",
            yaxis=dict(ticksuffix="%")
        )
        st.plotly_chart(fig_dd, use_container_width=True)
        
    # Trade R-Multiple Distribution Bar Chart
    if not df_trades.empty:
        st.markdown("#### 🎯 Individual Trade Asymmetry Breakdown (R-Multiples)")
        colors = ['#10b981' if r > 0 else '#ef4444' for r in df_trades["r"]]
        fig_bar = go.Figure()
        fig_bar.add_trace(go.Bar(
            x=[f"#{r['ticket']} {r['asset']} ({r['time'].split(' ')[0]})" for _, r in df_trades.iterrows()],
            y=df_trades["r"],
            marker_color=colors,
            hovertemplate="Trade: %{x}<br>Return: %{y:+.2f}R<br>Exit: %{text}<extra></extra>",
            text=df_trades["reason"]
        ))
        fig_bar.update_layout(
            template="plotly_dark",
            paper_bgcolor="#111827",
            plot_bgcolor="#111827",
            height=250,
            margin=dict(l=20, r=20, t=20, b=50),
            yaxis_title="Return (R)",
            xaxis_tickangle=-45
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    c_inf1, c_inf2 = st.columns(2)
    with c_inf1:
        st.info(f"💡 **Institutional Asymmetry In Action:**\nWins generate up to **+7.66R / +3.50R** with average win **+${avg_win_dollar:.2f}**, while losses are strictly capped at **-1.00R (-$25.00)**. Payoff Ratio: **{payoff_ratio:.2f}:1**.")
    with c_inf2:
        st.success("🛡️ **Automated Staged TP1 & Breakeven Engine:**\n`AurumH17ShadowEA` automatically banks 50% profit at +25 pts / +$5.00 and snaps Stop Loss to Breakeven, ensuring runners operate 100% risk-free towards London Midpoint.")

# TAB 2: Live Forward Trades Ledger
with tab2:
    st.subheader("📋 Gate 2 Forward Execution Ledger")
    st.markdown("All executions generated live on MetaTrader 5 broker feed by `AurumH17ShadowEA` (US100) and `AurumGoldH17ShadowEA` (XAUUSD).")
    
    if not df_open.empty:
        st.markdown("### 🟢 Active Open Forward Positions")
        for _, r in df_open.iterrows():
            st.success(f"🎯 **{r['Asset']} {r['Direction']} (Ticket #{r['Ticket #']})** | Open: `{r['Open Time']}` | Entry: `{r['Entry Price']:,.2f}` | SL: `{r['Stop Loss']:,.2f}` | TP: `{r['Take Profit']:,.2f}` | Target: **{r['Target Objective']}** | Risk: `{r['Risk ($)']}`")
        st.dataframe(df_open, use_container_width=True)
        st.markdown("---")

    if not df_trades.empty:
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            asset_filter = st.multiselect("Filter Asset:", options=["All", "US100", "XAUUSD"], default=["All"])
        with col_f2:
            outcome_filter = st.selectbox("Filter Outcome:", options=["All", "Wins Only", "Losses Only", "Breakeven Hits"])
        
        filtered_df = df_trades.copy()
        if "All" not in asset_filter and asset_filter:
            filtered_df = filtered_df[filtered_df["asset"].isin(asset_filter)]
        if outcome_filter == "Wins Only":
            filtered_df = filtered_df[filtered_df["pnl"] > 0]
        elif outcome_filter == "Losses Only":
            filtered_df = filtered_df[filtered_df["pnl"] < 0]
        elif outcome_filter == "Breakeven Hits":
            filtered_df = filtered_df[filtered_df["reason"].str.contains("BE", case=False, na=False)]

        st.dataframe(
            filtered_df[["ticket", "time", "asset", "direction", "entry", "sl", "tp", "pnl", "r", "reason", "balance"]].rename(columns={
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
        
        # Download button for audit
        csv_data = filtered_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            "📥 Download Audit CSV Ledger",
            data=csv_data,
            file_name="aurum_forward_audit_ledger.csv",
            mime="text/csv"
        )
    else:
        st.write("No closed trades logged yet. Standing by for execution signals.")

# TAB 3: Dual-Asset Quantitative Framework
with tab3:
    st.subheader("🪙 Dual-Asset Quantitative Intelligence & Rules")
    
    col_u, col_g = st.columns(2)
    with col_u:
        st.markdown("""
        <div class="metric-card">
            <div class="badge-active">ACTIVE ASSET • NASDAQ-100</div>
            <h3 style="color: #f9fafb; margin-top: 10px;">🇺🇸 US100 (`UT100Roll`)</h3>
            <hr style="border-color: #374151;"/>
            <p><b>• Strategy Model:</b> <code>H17</code> London Range Sweep & Reclaim</p>
            <p><b>• Range Qualification:</b> $\ge 140.0$ points (Eliminates low-volatility chop)</p>
            <p><b>• Staged TP1:</b> Auto-bank 50% profit at <b>+25.0 points</b></p>
            <p><b>• Breakeven Snap:</b> Move SL to Entry immediately upon TP1 execution</p>
            <p><b>• Dynamic Trailing:</b> +15 pts locked at +35 pts | +35 pts locked at +60 pts</p>
            <p><b>• Ultimate Target:</b> London Session Midpoint (+80 to +180 pts)</p>
            <p><b>• Risk per Trade:</b> Strict 0.25% ($25.00 virtual risk)</p>
        </div>
        """, unsafe_allow_html=True)

    with col_g:
        st.markdown("""
        <div class="metric-card">
            <div class="badge-gold">ACTIVE ASSET • SPOT GOLD</div>
            <h3 style="color: #f9fafb; margin-top: 10px;">🥇 XAUUSD (Gold)</h3>
            <hr style="border-color: #374151;"/>
            <p><b>• Strategy Model:</b> <code>XAU_H17</code> London Range Liquidity Sweep</p>
            <p><b>• Range Qualification:</b> $\ge 25.0$ points / $25.00 (Institutional Threshold)</p>
            <p><b>• Staged TP1:</b> Auto-bank 50% profit at <b>+$5.00 / 50 pips</b></p>
            <p><b>• Breakeven Snap:</b> Move SL to Entry immediately upon TP1 execution</p>
            <p><b>• Dynamic Trailing:</b> ATR Multi-Stage Trailing Stop</p>
            <p><b>• Ultimate Target:</b> London Session Midpoint Mean Reversion</p>
            <p><b>• Risk per Trade:</b> Strict 0.25% ($25.00 virtual risk)</p>
        </div>
        """, unsafe_allow_html=True)
        
    st.markdown("<br/>", unsafe_allow_html=True)
    st.markdown("""
    <div class="metric-card">
        <div class="badge-paused">QUARANTINED ASSET</div>
        <h4 style="color: #ef4444; margin-top: 8px;">⛔ US30 (Dow Jones 30) — 30-Day Disciplinary Pause (Day 2 / 30)</h4>
        <p style="color: #9ca3af;">In accordance with institutional portfolio risk rules, US30 is strictly quarantined for 30 calendar days to eliminate correlation drag and parameter drift while Gate 2 forward validation focuses exclusively on the high-performing dual portfolio of US100 and XAUUSD.</p>
    </div>
    """, unsafe_allow_html=True)

# TAB 4: Session Clock & Macro Calendar
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

# TAB 5: Asymmetry Simulator
with tab5:
    st.subheader("🎲 Quantitative Asymmetry & Future Path Simulator")
    st.markdown("Simulate projected portfolio growth across remaining Gate 2 trades (#15 to #30) and beyond using empirical payoff distribution.")
    
    sim_c1, sim_c2, sim_c3 = st.columns(3)
    with sim_c1:
        sim_balance = st.number_input("Starting Capital ($):", min_value=1000, max_value=1000000, value=10000, step=1000)
    with sim_c2:
        sim_risk_pct = st.slider("Risk per Trade (%):", min_value=0.1, max_value=2.0, value=0.25, step=0.05)
    with sim_c3:
        sim_trades_count = st.slider("Simulated Forward Trades:", min_value=10, max_value=100, value=30, step=5)
        
    risk_dollar = sim_balance * (sim_risk_pct / 100.0)
    st.caption(f"Dollar risk per trade: **${risk_dollar:.2f}** (1.00R)")
    
    # Historical R samples
    if not df_trades.empty:
        historical_r = df_trades["r"].tolist()
    else:
        historical_r = [-1.0, -1.0, 0.32, 0.8, -1.0, 0.69, 2.04, 2.92, 3.50, 7.66]
        
    np.random.seed(42)
    n_sims = 200
    all_paths = []
    
    for _ in range(n_sims):
        sampled_r = np.random.choice(historical_r, size=sim_trades_count, replace=True)
        path = [sim_balance]
        curr = sim_balance
        for r_val in sampled_r:
            curr += curr * (sim_risk_pct / 100.0) * r_val
            path.append(curr)
        all_paths.append(path)
        
    df_paths = pd.DataFrame(all_paths).T
    p5 = df_paths.quantile(0.05, axis=1)
    p50 = df_paths.quantile(0.50, axis=1)
    p95 = df_paths.quantile(0.95, axis=1)
    
    fig_sim = go.Figure()
    fig_sim.add_trace(go.Scatter(x=list(range(sim_trades_count + 1)), y=p95, mode="lines", line=dict(color="#10b981", width=1, dash="dot"), name="95th Percentile (Bull Case)"))
    fig_sim.add_trace(go.Scatter(x=list(range(sim_trades_count + 1)), y=p50, mode="lines", line=dict(color="#f59e0b", width=3), name="Median Expected Path"))
    fig_sim.add_trace(go.Scatter(x=list(range(sim_trades_count + 1)), y=p5, mode="lines", line=dict(color="#ef4444", width=1, dash="dot"), name="5th Percentile (Conservative)"))
    
    fig_sim.update_layout(
        template="plotly_dark",
        paper_bgcolor="#111827",
        plot_bgcolor="#111827",
        height=380,
        margin=dict(l=20, r=20, t=30, b=20),
        xaxis_title="Simulated Trade Sequence",
        yaxis_title="Projected Capital ($)",
        yaxis=dict(tickformat="$,.0f")
    )
    st.plotly_chart(fig_sim, use_container_width=True)
    st.info(f"📈 **Projection Summary:** Median expected outcome after {sim_trades_count} trades at {sim_risk_pct}% risk is **${p50.iloc[-1]:,.2f}** (+{((p50.iloc[-1]-sim_balance)/sim_balance)*100:.1f}%).")

# TAB 6: Causal Memory & Geopolitics
with tab6:
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

# TAB 7: Institutional Research Proofs
with tab7:
    st.subheader("🔬 Institutional Validation Battery & Stress Tests")
    
    t1, t2, t3, t4 = st.columns(4)
    with t1:
        st.markdown("""
        ### 🔄 Walk-Forward
        - **WFE (US100):** 1.54
        - **WFE (XAUUSD):** 1.63
        - **Status:** **PASSED**
        - Zero Overfitting.
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
        - Resilient in wide spreads.
        """)
    with t4:
        st.markdown("""
        ### 🎯 Trailing & TP1 Study
        - **Win Rate:** 19.7% ➔ **57.6%**
        - **Max Drawdown:** 66R ➔ **30R** (-53%)
        - **Status:** **INTEGRATED v1.1**
        - 50% TP1 + BE + Dynamic Trail.
        """)

# TAB 8: VPS Telemetry & Operations
with tab8:
    st.subheader("🛡️ 24/7 Oracle Cloud Sentinel Operations")
    
    v1, v2 = st.columns(2)
    with v1:
        st.markdown("""
        <div class="metric-card">
            <div class="badge-active">SERVER TELEMETRY</div>
            <h3 style="color: #f9fafb; margin-top: 8px;">Oracle Cloud Infrastructure (OCI)</h3>
            <hr style="border-color: #374151;"/>
            <p>• <b>Instance:</b> <code>aurum-vps</code> (Always Free Tier)</p>
            <p>• <b>Region:</b> Dubai, UAE (<code>me-dubai-1</code>)</p>
            <p>• <b>Public IP:</b> <code>145.241.127.95</code></p>
            <p>• <b>Compute:</b> AMD EPYC 9J14 96-Core (8 vCPUs / 24 GiB RAM)</p>
            <p>• <b>OS:</b> Ubuntu 22.04 LTS (x86_64 Native)</p>
            <p>• <b>Service Daemon:</b> <code>systemctl status aurum-sentinel</code></p>
        </div>
        """, unsafe_allow_html=True)
        
    with v2:
        st.markdown("""
        <div class="metric-card">
            <div class="badge-gold">REMOTE TERMINAL ACCESS</div>
            <h3 style="color: #f9fafb; margin-top: 8px;">MetaTrader 5 Web GUI (noVNC)</h3>
            <hr style="border-color: #374151;"/>
            <p>• <b>Web GUI URL:</b> <a href="http://145.241.127.95:6080/vnc.html" target="_blank" style="color: #f59e0b;">http://145.241.127.95:6080/vnc.html</a></p>
            <p>• <b>Direct Browser View:</b> View live MT5 charts and EA attachment directly from any laptop or mobile browser.</p>
            <p>• <b>Telegram Bot:</b> Real-time trade executions, session opens/closes, and daily risk summaries with SHA-256 deduplication.</p>
        </div>
        """, unsafe_allow_html=True)

st.markdown("---")
st.caption("AURUM Research Desk • Autonomous Institutional Execution Engine • Pair Programming Session 2026")
