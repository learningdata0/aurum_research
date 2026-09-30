from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from typing import Dict, List, Optional
import pandas as pd

from .config import Settings
from .data import prepare_data
from .htf_levels import build_htf_context_map, DailyHTFContext
from .hypotheses_v08 import HypothesisV08, evaluate_v08_signal
from .telegram_notifier import TelegramNotifier


class ShadowTradingDaemon:
    """
    AURUM v0.8 Autonomous Virtual Shadow Trading Daemon.
    Monitors live incoming broker bars, tracks London Session liquidity pools,
    executes virtual forward paper trades on H17 without risking financial capital,
    and maintains real-time markdown and terminal dashboards.
    """

    def __init__(
        self,
        symbol: str = "US100",
        data_file: str = "data/UT100Roll_M1.csv",
        log_dir: str = "reports",
        initial_balance: float = 10000.0,
        risk_pct: float = 0.0025,
        min_london_range: float = 140.0,
        slippage_pts: float = 0.50
    ):
        self.symbol = symbol
        self.data_file = Path(data_file)
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.csv_log = self.log_dir / f"shadow_trades_{self.symbol}.csv"
        self.dashboard_file = self.log_dir / "shadow_dashboard.md"

        self.settings = Settings(
            initial_balance=initial_balance,
            risk_per_trade=risk_pct,
            slippage_points=slippage_pts
        )
        self.hypothesis = HypothesisV08(
            id="H17",
            name="London Sweep (Range >= 140pts + Swing Target)",
            target_rr=1.8,
            min_london_range=min_london_range,
            target_mode="swing"
        )

        self.balance = initial_balance
        self.ticket_counter = 1001
        self.active_order: Optional[dict] = None
        self.closed_trades: List[dict] = []
        self.consecutive_losses = 0
        self.last_day = None
        self.daily_pnl = 0.0

        self.notifier = TelegramNotifier()
        self._notified_open_tickets = set()
        self._notified_closed_tickets = set()

        # Load existing trades if any
        if self.csv_log.exists():
            try:
                existing = pd.read_csv(self.csv_log)
                if not existing.empty and "pnl_cash" in existing.columns:
                    self.balance += float(existing["pnl_cash"].sum())
                    self.ticket_counter += len(existing)
            except Exception:
                pass

    def run_replay(self, recent_days: int = 14):
        """Replays recent completed trading days to demonstrate active shadow tracking."""
        print(f"\n=======================================================")
        print(f" AURUM v0.8 SHADOW VIRTUAL TRADING ENGINE")
        print(f" Strategy: H17 (London Sweep + Range >= {self.hypothesis.min_london_range}pts)")
        print(f" Symbol: {self.symbol} | Virtual Account: ${self.balance:,.2f}")
        print(f" Mode: FORWARD PAPER SIMULATION (Replaying last {recent_days} days)")
        print(f"=======================================================\n")

        df_raw = pd.read_csv(self.data_file)
        d = prepare_data(df_raw, source_timezone="broker")
        ctx_map = build_htf_context_map(d)

        unique_days = sorted(d["day"].unique())
        test_days = unique_days[-recent_days:]
        d_sub = d[d["day"].isin(test_days)].copy().reset_index(drop=True)

        for pos in range(len(d_sub)):
            row = d_sub.iloc[pos]
            day = row.day

            if day not in ctx_map:
                continue

            ctx = ctx_map[day]

            # 1. Update open position
            self._update_position(row, pos)

            # 2. Check trading window (NY Cash Session: 09:30 - 15:30 NY = minute 570 - 930)
            if row.local_minute < 570 or row.local_minute >= 930:
                continue

            if day != self.last_day:
                self.last_day = day
                self.daily_pnl = 0.0
                self.consecutive_losses = 0

            # Circuit breaker
            if self.consecutive_losses >= self.settings.max_consecutive_losses:
                continue
            if self.daily_pnl <= -self.settings.max_daily_loss * self.balance:
                continue
            if self.active_order is not None:
                continue

            # 3. Evaluate Signal
            sig = evaluate_v08_signal(row, ctx, self.hypothesis, self.settings)
            if not sig:
                continue

            direction, entry, sl, tp, setup = sig
            self._open_order(row, pos, direction, entry, sl, tp, setup, ctx)

        latest_ctx = ctx_map.get(test_days[-1])
        if latest_ctx is None:
            avail = [ctx_map[k] for k in test_days if k in ctx_map]
            latest_ctx = avail[-1] if avail else list(ctx_map.values())[-1]
        self._render_dashboard(latest_ctx, d_sub.iloc[-1])
        self._print_terminal_summary()

    def _open_order(self, row: pd.Series, pos: int, direction: str, entry: float, sl: float, tp: float, setup: str, ctx: DailyHTFContext):
        risk_price = abs(entry - sl)
        if risk_price <= 0:
            return

        risk_cash = self.balance * self.settings.risk_per_trade
        units = risk_cash / risk_price
        slip = self.settings.slippage_points
        actual_entry = entry + slip if direction == "BUY" else entry - slip

        order = {
            "ticket": self.ticket_counter,
            "symbol": self.symbol,
            "hypothesis": self.hypothesis.id,
            "setup": setup,
            "direction": direction,
            "entry_time": str(row.time),
            "entry_price": float(actual_entry),
            "sl": float(sl),
            "tp": float(tp),
            "units": float(units),
            "risk_cash": float(risk_cash),
            "risk_price": float(risk_price),
            "entry_pos": pos,
            "max_pos": pos + 120,
            "status": "OPEN",
            "london_range": ctx.london_high - ctx.london_low if ctx.london_high else 0.0
        }
        self.ticket_counter += 1
        self.active_order = order

        print(f" [VIRTUAL ORDER OPEN] Ticket #{order['ticket']} | {direction} @ {actual_entry:.2f} | SL: {sl:.2f} | TP: {tp:.2f} | Risk: ${risk_cash:.2f} (1R)")

    def _update_position(self, row: pd.Series, pos: int):
        if self.active_order is None:
            return

        o = self.active_order
        direction = o["direction"]
        sl = o["sl"]
        tp = o["tp"]

        hit_sl = row.low <= sl if direction == "BUY" else row.high >= sl
        hit_tp = row.high >= tp if direction == "BUY" else row.low <= tp

        exit_price = None
        exit_reason = None

        if hit_sl:
            exit_price = sl
            exit_reason = "SL"
        elif hit_tp:
            exit_price = tp
            exit_reason = "TP"
        elif pos >= o["max_pos"]:
            exit_price = float(row.close)
            exit_reason = "TIME"

        if exit_price is not None:
            slip = self.settings.slippage_points
            actual_exit = exit_price - slip if direction == "BUY" else exit_price + slip
            pts = (actual_exit - o["entry_price"]) if direction == "BUY" else (o["entry_price"] - actual_exit)
            net_pnl = pts * o["units"]
            r_mult = net_pnl / o["risk_cash"] if o["risk_cash"] > 0 else 0.0

            self.balance += net_pnl
            self.daily_pnl += net_pnl
            self.consecutive_losses = self.consecutive_losses + 1 if net_pnl < 0 else 0

            closed_record = {
                **o,
                "exit_time": str(row.time),
                "exit_price": float(actual_exit),
                "pnl_cash": round(net_pnl, 2),
                "r_multiple": round(r_mult, 2),
                "exit_reason": exit_reason,
                "status": f"CLOSED_{exit_reason}",
                "final_balance": round(self.balance, 2)
            }
            self.closed_trades.append(closed_record)
            self.active_order = None
            self._log_trade(closed_record)

            color_tag = "WIN  +" if net_pnl > 0 else "LOSS -"
            print(f" [VIRTUAL ORDER CLOSED] Ticket #{o['ticket']} by {exit_reason:<4} | {color_tag}${abs(net_pnl):.2f} ({r_mult:+.2f}R) | Balance: ${self.balance:,.2f}")

    def _log_trade(self, t: dict):
        df_row = pd.DataFrame([t])
        if not self.csv_log.exists():
            df_row.to_csv(self.csv_log, index=False)
        else:
            df_row.to_csv(self.csv_log, mode="a", header=False, index=False)

    def _render_dashboard(self, ctx: DailyHTFContext, latest_row: pd.Series):
        td = pd.DataFrame(self.closed_trades)
        wins = len(td[td["pnl_cash"] > 0]) if not td.empty else 0
        losses = len(td[td["pnl_cash"] < 0]) if not td.empty else 0
        total_t = len(td)
        net_cash = round(float(td["pnl_cash"].sum()), 2) if not td.empty else 0.0
        net_r = round(float(td["r_multiple"].sum()), 2) if not td.empty else 0.0
        gw = td[td["pnl_cash"] > 0]["pnl_cash"].sum() if not td.empty else 0.0
        gl = abs(td[td["pnl_cash"] < 0]["pnl_cash"].sum()) if not td.empty else 0.0
        pf = round(gw / gl, 2) if gl > 0 else 999.0

        lon_range = (ctx.london_high - ctx.london_low) if (ctx.london_high is not None and ctx.london_low is not None) else 0.0
        lon_mid = (ctx.london_high + ctx.london_low) / 2.0 if (ctx.london_high is not None and ctx.london_low is not None) else None
        q_status = "QUALIFIED (>= 140 pts)" if lon_range >= self.hypothesis.min_london_range else "UNQUALIFIED (< 140 pts)"

        active_str = "None (Standing by)"
        if self.active_order:
            o = self.active_order
            active_str = f"Ticket #{o['ticket']} | {o['direction']} @ {o['entry_price']:.2f} | SL: {o['sl']:.2f} | TP: {o['tp']:.2f}"

        lh_str = f"{ctx.london_high:.2f}" if ctx.london_high is not None else "N/A"
        ll_str = f"{ctx.london_low:.2f}" if ctx.london_low is not None else "N/A"
        lmid_str = f"{lon_mid:.2f}" if lon_mid is not None else "N/A"

        dash = rf"""# AURUM v0.8 Forward Shadow Execution Dashboard
**Updated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  
**Mode:** Virtual Forward Paper Trading (Zero Real Financial Risk)  
**Strategy Core:** `H17` London Session Sweep-Reclaim + Median Expansion ($\ge 140$ pts)  

---

### Account & Performance Status
- **Virtual Balance:** ${self.balance:,.2f}
- **Net Virtual PnL:** ${net_cash:+,.2f} ({net_r:+.2f}R)
- **Total Shadow Trades:** {total_t} (Wins: {wins} | Losses: {losses} | WR: {round(100.0 * wins / max(1, total_t), 1)}%)
- **Profit Factor:** {pf}
- **Active Position:** `{active_str}`

---

### Today's Market & Liquidity Context ({ctx.day})
- **Previous Day High (PDH):** {ctx.pdh:.2f} | **Previous Day Low (PDL):** {ctx.pdl:.2f}
- **London Session High:** {lh_str} | **London Session Low:** {ll_str}
- **London Session Range:** {lon_range:.2f} points — **{q_status}**
- **London Midpoint Target:** {lmid_str}
- **Last Market Bar:** {latest_row.time} | Close: {latest_row.close:.2f}
"""
        with open(self.dashboard_file, "w", encoding="utf-8") as f:
            f.write(dash)

    def _print_terminal_summary(self):
        td = pd.DataFrame(self.closed_trades)
        print("\n=======================================================")
        print(" AURUM v0.8 SHADOW TRADING AUDIT SUMMARY")
        print("=======================================================")
        print(f" Closed Shadow Trades: {len(td)}")
        if not td.empty:
            wins = len(td[td['pnl_cash'] > 0])
            wr = round(100.0 * wins / len(td), 1)
            gw = td[td['pnl_cash'] > 0]['pnl_cash'].sum()
            gl = abs(td[td['pnl_cash'] < 0]['pnl_cash'].sum())
            pf = round(gw / gl, 2) if gl > 0 else 999.0
            print(f" Win Rate: {wr}% ({wins} wins / {len(td) - wins} losses)")
            print(f" Profit Factor: {pf}")
            print(f" Total Net PnL: ${td['pnl_cash'].sum():+,.2f} ({td['r_multiple'].sum():+.2f}R)")
            print(f" Final Virtual Balance: ${self.balance:,.2f}")
        print(f" Dashboard File: {self.dashboard_file}")
        print(f" Trades Audit Log: {self.csv_log}")
        print("=======================================================\n")

    def _read_mt5_csv(self, file_path: Path) -> Optional[pd.DataFrame]:
        if not file_path.exists() or file_path.stat().st_size <= 4:
            return None
        standard_cols = ["ticket", "time", "action", "symbol", "direction", "entry", "sl", "tp", "pnl", "r_mult", "reason", "balance"]
        for enc in ["utf-16", "utf-8", "cp1252"]:
            for sep in ["\t", ","]:
                try:
                    df = pd.read_csv(file_path, encoding=enc, sep=sep, on_bad_lines="skip")
                    if df is not None and not df.empty and "action" in df.columns:
                        if df["action"].dropna().astype(str).str.upper().isin(["OPEN", "CLOSED"]).any():
                            return df.copy()
                    df_no_hdr = pd.read_csv(file_path, encoding=enc, sep=sep, header=None, on_bad_lines="skip")
                    if df_no_hdr is not None and not df_no_hdr.empty and len(df_no_hdr.columns) >= 6:
                        df_no_hdr.columns = standard_cols[:len(df_no_hdr.columns)]
                        if df_no_hdr["action"].dropna().astype(str).str.upper().isin(["OPEN", "CLOSED"]).any():
                            return df_no_hdr.copy()
                except Exception:
                    continue
        return None

    def sync_from_mt5(self, path_or_dir: Optional[str] = None):
        """
        Reads trade logs produced by both US100 and Gold EAs in MT5 and updates the research dashboard.
        Supports passing either the MQL5/Files folder or a specific CSV file.
        """
        if path_or_dir is None:
            path_or_dir = "/Users/nouh/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files"

        p = Path(path_or_dir)
        df_us100 = None
        df_gold = None

        if p.is_file():
            df = self._read_mt5_csv(p)
            if "gold" in p.name.lower():
                df_gold = df
            else:
                df_us100 = df
        else:
            df_us100 = self._read_mt5_csv(p / "aurum_shadow_trades.csv")
            df_gold = self._read_mt5_csv(p / "aurum_gold_shadow_trades.csv")

        if (df_us100 is None or df_us100.empty) and (df_gold is None or df_gold.empty):
            return False

        all_trades = []
        if df_us100 is not None and not df_us100.empty:
            df_us100["asset"] = "US100"
            all_trades.append(df_us100)
        if df_gold is not None and not df_gold.empty:
            df_gold["asset"] = "XAUUSD"
            all_trades.append(df_gold)

        portfolio_df = pd.concat(all_trades, ignore_index=True)
        portfolio_df["pnl"] = pd.to_numeric(portfolio_df["pnl"], errors="coerce").fillna(0.0)
        portfolio_df["r_mult"] = pd.to_numeric(portfolio_df["r_mult"], errors="coerce").fillna(0.0)

        closed_trades = portfolio_df[portfolio_df["action"] == "CLOSED"].copy()
        closed_tickets = set(closed_trades["ticket"].dropna().unique())
        open_trades = portfolio_df[(portfolio_df["action"] == "OPEN") & (~portfolio_df["ticket"].isin(closed_tickets))].copy()

        tot_trades = len(closed_trades)
        wins = len(closed_trades[closed_trades["pnl"] > 0])
        losses = len(closed_trades[closed_trades["pnl"] < 0])
        net_cash = float(closed_trades["pnl"].sum())
        net_r = float(closed_trades["r_mult"].sum())
        gw = closed_trades[closed_trades["pnl"] > 0]["pnl"].sum()
        gl = abs(closed_trades[closed_trades["pnl"] < 0]["pnl"].sum())
        pf = round(gw / gl, 2) if gl > 0 else 999.0
        tot_bal = 10000.0 + net_cash

        # Asset metrics
        def asset_summary(df_a: Optional[pd.DataFrame], name: str):
            if df_a is None or df_a.empty:
                return f"- **{name}:** 0 trades (Standing by)"
            w = len(df_a[df_a["pnl"] > 0])
            n = len(df_a)
            nc = df_a["pnl"].sum()
            nr = df_a["r_mult"].sum()
            g_w = df_a[df_a["pnl"] > 0]["pnl"].sum()
            g_l = abs(df_a[df_a["pnl"] < 0]["pnl"].sum())
            p_f = round(g_w / g_l, 2) if g_l > 0 else 999.0
            return f"- **{name}:** {n} trades | Win Rate: {round(100.0*w/n, 1)}% | Net: ${nc:+,.2f} ({nr:+.2f}R) | PF: {p_f}"

        dash = rf"""# AURUM v0.8 Dual-Asset Forward Shadow Execution Dashboard
**Updated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  
**Mode:** Virtual Forward Paper Trading (Zero Real Financial Risk)  
**Active Portfolio:** US100 (`H17` Range $\ge 140$ pts) + XAUUSD (`XAU_H17` Range $\ge 55$ pts)  
**Status:** Dual Autonomous Execution Active

---

### Combined Portfolio Performance
- **Combined Balance:** ${tot_bal:,.2f}
- **Net Portfolio PnL:** ${net_cash:+,.2f} ({net_r:+.2f}R)
- **Total Shadow Trades:** {tot_trades} (Wins: {wins} | Losses: {losses} | WR: {round(100.0 * wins / max(1, tot_trades), 1)}%)
- **Portfolio Profit Factor:** {pf}

---

### Asset Breakdown
{asset_summary(df_us100, "US100 (Nasdaq-100)")}
{asset_summary(df_gold, "XAUUSD (Gold)")}
"""

        if not open_trades.empty:
            dash += "\n---\n\n### 🟢 Active Open Forward Positions\n"
            dash += "| Asset | Ticket | Open Time | Direction | Entry | SL | TP | Risk ($) | Target |\n"
            dash += "|---|---|---|---|---|---|---|---|---|\n"
            for _, r in open_trades.iterrows():
                risk_cash = 25.0
                dash += f"| {r.get('asset', 'US100')} | #{r.ticket} | {r.time} | **{r.direction}** | {r.entry} | {r.sl} | {r.tp} | ${risk_cash:.2f} | London Midpoint |\n"
                t_id = int(r.ticket)
                if t_id not in self._notified_open_tickets:
                    self._notified_open_tickets.add(t_id)
                    self.notifier.send_trade_open_alert(
                        asset=r.get("asset", "US100"),
                        direction=str(r.direction),
                        ticket=t_id,
                        entry=float(r.entry),
                        sl=float(r.sl),
                        tp=float(r.tp),
                        risk_cash=risk_cash
                    )

        dash += """\n---\n\n### Closed Forward Executions
| Asset | Ticket | Time | Direction | Entry | SL | TP | PnL ($) | R | Reason |
|---|---|---|---|---|---|---|---|---|---|
"""
        for _, r in closed_trades.tail(10).iterrows():
            dash += f"| {r.get('asset', 'US100')} | {r.ticket} | {r.time} | {r.direction} | {r.entry} | {r.sl} | {r.tp} | {r.pnl:+,.2f} | {r.r_mult:+.2f}R | {r.reason} |\n"
            t_id = int(r.ticket)
            if t_id not in self._notified_closed_tickets:
                self._notified_closed_tickets.add(t_id)
                self.notifier.send_trade_close_alert(
                    asset=r.get("asset", "US100"),
                    ticket=t_id,
                    direction=str(r.direction),
                    pnl=float(r.pnl),
                    r_mult=float(r.r_mult),
                    reason=str(r.reason),
                    balance=float(tot_bal)
                )

        if closed_trades.empty:
            dash += "| Standing by | - | - | - | - | - | - | $0.00 | +0.00R | Live trading active |\n"

        with open(self.dashboard_file, "w", encoding="utf-8") as f:
            f.write(dash)
        return True

    def run_watch(self, poll_interval: int = 15):
        print(f"[AURUM WATCH] Monitoring Dual-Asset MT5 Shadow Execution every {poll_interval}s...")
        base_dir = "/Users/nouh/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files"
        p_base = Path(base_dir)
        last_mtimes = {}

        while True:
            try:
                changed = False
                for fname in ["aurum_shadow_trades.csv", "aurum_gold_shadow_trades.csv"]:
                    fp = p_base / fname
                    if fp.exists():
                        mt = fp.stat().st_mtime
                        if mt != last_mtimes.get(fname, 0.0):
                            last_mtimes[fname] = mt
                            changed = True

                if changed:
                    synced = self.sync_from_mt5(base_dir)
                    if synced:
                        print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}] Synced live trades from MT5 EAs. Dashboard updated.")
                time.sleep(poll_interval)
            except KeyboardInterrupt:
                print("\n[AURUM WATCH] Stopped.")
                break
            except Exception:
                time.sleep(poll_interval)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="AURUM v0.8 Shadow Trading Daemon")
    p.add_argument("--mode", choices=["replay", "sync", "watch"], default="replay", help="Operational mode")
    p.add_argument("--days", type=int, default=14, help="Replay days for shadow demonstration")
    p.add_argument("--reset", action="store_true", help="Reset prior shadow trade history before running")
    p.add_argument("--interval", type=int, default=15, help="Poll interval in seconds for watch mode")
    a = p.parse_args()

    daemon = ShadowTradingDaemon()
    if a.reset and daemon.csv_log.exists():
        daemon.csv_log.unlink()
        print(f"[RESET] Cleared previous trade log at {daemon.csv_log}")

    if a.mode == "replay":
        daemon.run_replay(recent_days=a.days)
    elif a.mode == "sync":
        if daemon.sync_from_mt5():
            print("[SYNC] Dashboard updated from MT5.")
        else:
            print("[SYNC] No new trades or MT5 file not yet populated.")
    elif a.mode == "watch":
        daemon.run_watch(poll_interval=a.interval)
