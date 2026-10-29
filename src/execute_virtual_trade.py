from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys
import pandas as pd

from src.telegram_notifier import TelegramNotifier


def open_virtual_trade(
    asset: str = "XAUUSD",
    symbol: str = "XAUUSD",
    direction: str = "SELL",
    entry_price: float = 4030.00,
    sl: float = 4038.00,
    tp: float = 4018.00,
    ticket: int = 2001,
    balance: float = 10162.71,
    risk_cash: float = 25.0
):
    repo_reports_dir = Path("reports").resolve()
    repo_reports_dir.mkdir(parents=True, exist_ok=True)
    
    time_str = datetime.now(timezone.utc).strftime("%Y.%m.%d %H:%M")
    
    # 1. Standard CSV log
    csv_log_fp = repo_reports_dir / f"shadow_trades_{asset}.csv"
    row_data = {
        "ticket": ticket,
        "time": time_str,
        "action": "OPEN",
        "symbol": symbol,
        "direction": direction,
        "entry": f"{entry_price:.2f}",
        "sl": f"{sl:.2f}",
        "tp": f"{tp:.2f}",
        "pnl": "0.00",
        "r_mult": "0.00",
        "reason": "SIGNAL_ENTRY",
        "balance": f"{balance:.2f}"
    }
    df_row = pd.DataFrame([row_data])
    if csv_log_fp.exists():
        try:
            df_existing = pd.read_csv(csv_log_fp)
            df_combined = pd.concat([df_existing, df_row], ignore_index=True)
        except Exception:
            df_combined = df_row
    else:
        df_combined = df_row
    df_combined.to_csv(csv_log_fp, index=False)
    
    # 2. MT5-format tab-separated file for shadow_daemon live sync
    ea_filename = "aurum_gold_shadow_trades.csv" if asset == "XAUUSD" else "aurum_shadow_trades.csv"
    ea_fp = repo_reports_dir / ea_filename
    line_tab = f"{ticket}\t{time_str}\tOPEN\t{symbol}\t{direction}\t{entry_price:.2f}\t{sl:.2f}\t{tp:.2f}\t0.00\t0.00\tSIGNAL_ENTRY\t{balance:.2f}\n"
    
    with open(ea_fp, "a", encoding="utf-8") as f:
        f.write(line_tab)
        
    print(f"✅ [VIRTUAL TRADE LOGGED] {asset} {direction} @ {entry_price:.2f} | SL: {sl:.2f} | TP: {tp:.2f} | Ticket #{ticket}")
    
    # 3. Dispatch Telegram Alert
    notifier = TelegramNotifier()
    msg = (
        f"🎯 <b>AURUM VIRTUAL SHADOW ORDER OPENED</b>\n\n"
        f"• <b>Asset:</b> {asset} ({symbol})\n"
        f"• <b>Ticket:</b> #{ticket}\n"
        f"• <b>Direction:</b> 🔴 {direction}\n"
        f"• <b>Entry Price:</b> ${entry_price:,.2f}\n"
        f"• <b>Stop Loss:</b> ${sl:,.2f} ({abs(entry_price - sl):.2f} pts)\n"
        f"• <b>Take Profit (TP1):</b> ${tp:,.2f} ({abs(entry_price - tp):.2f} pts)\n"
        f"• <b>Risk Model:</b> 1R (${risk_cash:.2f})\n"
        f"• <b>Timestamp:</b> {time_str} UTC\n\n"
        f"<i>Mode: Virtual Forward Paper Execution (Gate 2 Active)</i>"
    )
    notifier.send_message(msg)
    return row_data


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Open virtual trade")
    p.add_argument("--asset", default="XAUUSD")
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--direction", default="SELL")
    p.add_argument("--entry", type=float, default=4030.00)
    p.add_argument("--sl", type=float, default=4038.00)
    p.add_argument("--tp", type=float, default=4018.00)
    p.add_argument("--ticket", type=int, default=2001)
    args = p.parse_args()
    
    open_virtual_trade(
        asset=args.asset,
        symbol=args.symbol,
        direction=args.direction,
        entry_price=args.entry,
        sl=args.sl,
        tp=args.tp,
        ticket=args.ticket
    )
