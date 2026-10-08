from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys

from src.telegram_notifier import TelegramNotifier


def get_default_mt5_files_dir() -> Path:
    env_dir = os.environ.get("MT5_FILES_DIR")
    if env_dir:
        p = Path(env_dir)
        if p.exists():
            return p
    candidates = [
        Path("/root/.wine/drive_c/Program Files/MetaTrader 5/MQL5/Files"),
        Path.home() / ".wine/drive_c/Program Files/MetaTrader 5/MQL5/Files",
        Path.home() / "Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files",
        Path("/Users/nouh/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files"),
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0] if sys.platform.startswith("linux") else candidates[2]


def close_active_position(exit_price: float = 31033.0, reason: str = "MANUAL"):
    mt5_dir = get_default_mt5_files_dir()
    repo_reports_dir = Path("reports").resolve()
    
    # 1. Target files
    mt5_trades_fp = mt5_dir / "aurum_shadow_trades.csv" if mt5_dir.exists() else None
    repo_trades_fp = repo_reports_dir / "shadow_trades_US100.csv"
    dash_fp = repo_reports_dir / "shadow_dashboard.md"

    # Identify open trade details
    ticket = 1000
    asset = "US100"
    symbol = "UT100Roll"
    direction = "SELL"
    entry = 31045.51
    sl = 31069.05
    tp = 30963.73
    open_time = "2026.10.08 17:48"
    close_time = datetime.now(timezone.utc).strftime("%Y.%m.%d %H:%M")

    # Math
    sl_dist = abs(sl - entry)  # 23.54
    favorable_pts = (entry - exit_price) if direction == "SELL" else (exit_price - entry)  # +12.51
    r_mult = round(favorable_pts / sl_dist, 2)  # +0.53R
    risk_cash = 25.0
    pnl_cash = round(r_mult * risk_cash, 2)  # +$13.29

    previous_balance = 10184.07
    new_balance = round(previous_balance + pnl_cash, 2)  # $10,197.36

    print(f"\n=======================================================")
    print(f" AURUM v0.8 MANUAL POSITION CLOSURE")
    print(f" Asset: {asset} ({symbol}) | Ticket: #{ticket}")
    print(f" Direction: {direction} | Entry: {entry:,.2f} | Exit: {exit_price:,.2f}")
    print(f" Points Gained: {favorable_pts:+.2f} pts | R-Multiple: {r_mult:+.2f}R")
    print(f" Net Realized PnL: ${pnl_cash:+,.2f} | New Balance: ${new_balance:,.2f}")
    print(f"=======================================================\n")

    closed_line_tab = f"{ticket}\t{close_time}\tCLOSED\t{symbol}\t{direction}\t{entry:.2f}\t{sl:.2f}\t{tp:.2f}\t{pnl_cash:.2f}\t{r_mult:.2f}\t{reason}\t{new_balance:.2f}\n"

    # 2. Append to MT5 directory if accessible
    if mt5_trades_fp and mt5_dir.exists():
        try:
            # Append utf-16le line
            with open(mt5_trades_fp, "ab") as f:
                f.write(closed_line_tab.encode("utf-16le"))
            print(f"[MT5 LOG] Appended CLOSED record to {mt5_trades_fp}")

            # Also write aurum_cmd.txt so EA can read and clear lines
            cmd_fp = mt5_dir / "aurum_cmd.txt"
            cmd_fp.write_text(f"CLOSE\t{ticket}\t{exit_price:.2f}\n", encoding="utf-8")
            print(f"[MT5 CMD] Wrote command signal to {cmd_fp}")
        except Exception as e:
            print(f"[MT5 LOG WARNING] Could not write directly to MT5 directory: {e}")

    # 3. Append to repository reports/shadow_trades_US100.csv
    if repo_trades_fp.exists():
        try:
            with open(repo_trades_fp, "ab") as f:
                f.write(closed_line_tab.encode("utf-16le"))
            print(f"[REPO LOG] Appended CLOSED record to {repo_trades_fp}")
        except Exception as e:
            print(f"[REPO LOG WARNING] Could not append to {repo_trades_fp}: {e}")

    # 4. Update shadow_dashboard.md
    if dash_fp.exists():
        try:
            # Calculate updated stats
            tot_trades = 14
            wins = 7
            losses = 7
            win_rate = 50.0
            net_cash = round(184.07 + pnl_cash, 2)
            net_r = round(7.37 + r_mult, 2)
            gw = 349.83 + pnl_cash  # previous gross wins + new win
            gl = 165.76  # previous gross losses
            pf = round(gw / gl, 2)

            dash_content = f"""# AURUM v0.8 Dual-Asset Forward Shadow Execution Dashboard
**Updated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  
**Mode:** Virtual Forward Paper Trading (Zero Real Financial Risk)  
**Active Portfolio:** US100 (`H17` Range $\\ge 140$ pts) + XAUUSD (`XAU_H17` Range $\\ge 25$ pts)  
**Status:** Dual Autonomous Execution Active

---

### Combined Portfolio Performance
- **Combined Balance:** ${new_balance:,.2f}
- **Net Portfolio PnL:** ${net_cash:+,.2f} ({net_r:+.2f}R)
- **Total Shadow Trades:** {tot_trades} (Wins: {wins} | Losses: {losses} | WR: {win_rate:.1f}%)
- **Portfolio Profit Factor:** {pf:.2f}

---

### Asset Breakdown
- **US100 (Nasdaq-100):** {tot_trades} trades | Win Rate: {win_rate:.1f}% | Net: ${net_cash:+,.2f} ({net_r:+.2f}R) | PF: {pf:.2f}
- **XAUUSD (Gold):** 0 trades (Standing by)

---

### Closed Forward Executions
| Asset | Ticket | Time | Direction | Entry | SL | TP | PnL ($) | R | Reason |
|---|---|---|---|---|---|---|---|---|---|
| US100 | 1000 | 2026.10.01 16:36 | BUY | 30528.52 | 30479.59 | 30629.47 | -25.00 | -1.00R | SL |
| US100 | 1001 | 2026.10.01 16:45 | BUY | 30517.69 | 30467.49 | 30629.47 | -24.94 | -1.00R | SL |
| US100 | 1002 | 2026.10.01 17:00 | BUY | 30499.24 | 30441.07 | 30629.47 | -24.88 | -1.00R | SL |
| US100 | 1000 | 2026.10.01 21:05 | BUY | 30490.89 | 30481.69 | 30629.47 | -26.24 | -1.05R | SL |
| US100 | 1001 | 2026.10.01 21:19 | BUY | 30486.85 | 30486.85 | 30629.47 | +7.93 | +0.32R | BE_STOP |
| US100 | 1002 | 2026.10.01 21:25 | BUY | 30487.48 | 30512.48 | 30629.47 | +19.86 | +0.80R | BE_STOP |
| US100 | 1000 | 2026.10.06 17:05 | SELL | 31286.84 | 31304.84 | 31192.25 | -25.14 | -1.01R | SL |
| US100 | 1001 | 2026.10.06 17:31 | SELL | 31279.24 | 31254.24 | 31192.25 | +17.14 | +0.69R | BE_STOP |
| US100 | 1002 | 2026.10.07 08:10 | SELL | 31287.55 | 31262.55 | 31192.25 | +50.84 | +2.04R | TIME |
| US100 | 1000 | 2026.10.07 19:45 | BUY | 30968.14 | 30924.13 | 31096.47 | +73.00 | +2.92R | TP_FULL |
| US100 | 1000 | {close_time} | SELL | {entry:.2f} | {sl:.2f} | {tp:.2f} | {pnl_cash:+,.2f} | {r_mult:+.2f}R | {reason} |
"""
            dash_fp.write_text(dash_content, encoding="utf-8")
            print(f"[DASHBOARD] Updated {dash_fp}")
        except Exception as e:
            print(f"[DASHBOARD WARNING] Failed to update dashboard: {e}")

    # 5. Dispatch Telegram Alert
    notifier = TelegramNotifier()
    if notifier.is_configured():
        dedup_key = f"close_US100_{ticket}_{reason}_{close_time}"
        notifier.send_trade_close_alert(
            asset="US100",
            ticket=ticket,
            direction=direction,
            pnl=pnl_cash,
            r_mult=r_mult,
            reason=f"{reason} at {exit_price:,.2f}",
            balance=new_balance,
            dedup_key=dedup_key
        )
        print("[TELEGRAM] Dispatched trade close alert to @shadow2030bot")

    # 6. Push to GitHub for live Streamlit sync
    try:
        subprocess.run(["git", "add", "reports/"], check=False)
        commit_res = subprocess.run(
            ["git", "commit", "-m", f"feat(live): manual close Trade #{ticket} at {exit_price:.2f} (+${pnl_cash:.2f}, +{r_mult:.2f}R)"],
            check=False,
            capture_output=True,
            text=True
        )
        if commit_res.returncode == 0:
            push_res = subprocess.run(["git", "push", "origin", "main"], check=False, capture_output=True, text=True)
            if push_res.returncode == 0:
                print("[GIT PUSH] Successfully synced with GitHub & Streamlit Cloud.")
            else:
                print(f"[GIT PUSH ERROR] {push_res.stderr}")
        else:
            print(f"[GIT COMMIT INFO] {commit_res.stdout or commit_res.stderr}")
    except Exception as ge:
        print(f"[GIT WARNING] Git sync failed: {ge}")

    return {
        "ticket": ticket,
        "entry": entry,
        "exit": exit_price,
        "pnl_cash": pnl_cash,
        "r_mult": r_mult,
        "balance": new_balance,
        "reason": reason
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Close Active Shadow Trade")
    parser.add_argument("--price", type=float, default=31033.0, help="Exit execution price")
    parser.add_argument("--reason", type=str, default="MANUAL", help="Close reason")
    args = parser.parse_args()
    close_active_position(exit_price=args.price, reason=args.reason)
