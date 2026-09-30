from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
import urllib.parse
import urllib.request


class TelegramNotifier:
    """
    Lightweight, institutional Telegram Notification Engine for AURUM.
    Dispatches instant alerts for trade executions, stop-loss / take-profit hits,
    session milestones, and portfolio equity updates directly to mobile devices.
    """

    def __init__(self, config_path: str = "config/telegram.json"):
        self.config_file = Path(config_path)
        self.bot_token: Optional[str] = os.environ.get("AURUM_TELEGRAM_BOT_TOKEN")
        self.chat_id: Optional[str] = os.environ.get("AURUM_TELEGRAM_CHAT_ID")
        self._load_config()

    def _load_config(self):
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    if not self.bot_token:
                        self.bot_token = cfg.get("bot_token")
                    if not self.chat_id:
                        self.chat_id = str(cfg.get("chat_id"))
            except Exception:
                pass

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id and "YOUR_" not in self.bot_token)

    def send_message(self, text: str) -> bool:
        """Sends a markdown-formatted message to the configured Telegram chat."""
        if not self.is_configured():
            print(f"[TELEGRAM STANDBY] Not configured yet. Alert queued:\n{text}")
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result.get("ok", False)
        except Exception as e:
            print(f"[TELEGRAM ERROR] Failed to send alert: {e}")
            return False

    def send_trade_open_alert(self, asset: str, direction: str, ticket: int, entry: float, sl: float, tp: float, risk_cash: float = 25.0):
        emoji = "🟢" if direction.upper() == "BUY" else "🔴"
        r_points = abs(entry - sl)
        tp_points = abs(tp - entry)
        rr_ratio = (tp_points / r_points) if r_points > 0 else 0.0

        msg = (
            f"{emoji} *[AURUM TRADE ALERT — NEW EXECUTION]*\n\n"
            f"• *Asset:* `{asset}`\n"
            f"• *Direction:* *{direction.upper()}*\n"
            f"• *Ticket:* `#{ticket}`\n"
            f"• *Entry Price:* `{entry:,.2f}`\n"
            f"• *Stop Loss:* `{sl:,.2f}`\n"
            f"• *Take Profit:* `{tp:,.2f}` (London Midpoint)\n"
            f"• *Risk Capped:* `${risk_cash:.2f} (1.00R / 0.25%)`\n"
            f"• *Target R:R:* `1 : {rr_ratio:.2f}R`\n\n"
            f"⚡ *Institutional Liquidity Sweep-Reclaim Triggered.*"
        )
        return self.send_message(msg)

    def send_trade_close_alert(self, asset: str, ticket: int, direction: str, pnl: float, r_mult: float, reason: str, balance: float):
        if pnl > 0:
            header = f"🎯 *[AURUM TAKE PROFIT HIT — WIN!]*"
            pnl_str = f"+${pnl:,.2f} (+{r_mult:.2f}R)"
        else:
            header = f"🛡️ *[AURUM STOP LOSS HIT — CONTROLLED RISK]*"
            pnl_str = f"-${abs(pnl):,.2f} ({r_mult:.2f}R)"

        msg = (
            f"{header}\n\n"
            f"• *Asset:* `{asset}`\n"
            f"• *Ticket:* `#{ticket}` ({direction.upper()})\n"
            f"• *Realized PnL:* `{pnl_str}`\n"
            f"• *Exit Reason:* `{reason}`\n"
            f"• *Updated Portfolio Equity:* `${balance:,.2f}`\n\n"
            f"📈 *Gate 2 Forward Paper Execution Validated.*"
        )
        return self.send_message(msg)

    def send_session_summary(self, session_title: str, summary_text: str):
        msg = f"⏱️ *[AURUM DESK SESSION UPDATE]*\n*{session_title}*\n\n{summary_text}"
        return self.send_message(msg)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AURUM Telegram Notifier")
    parser.add_argument("--test", action="store_true", help="Send test message")
    parser.add_argument("--setup", nargs=2, metavar=("BOT_TOKEN", "CHAT_ID"), help="Configure credentials")
    args = parser.parse_args()

    notifier = TelegramNotifier()

    if args.setup:
        token, chat = args.setup
        cfg_dir = Path("config")
        cfg_dir.mkdir(exist_ok=True)
        with open("config/telegram.json", "w", encoding="utf-8") as f:
            json.dump({"bot_token": token, "chat_id": chat}, f, indent=2)
        print(f"[SETUP] Telegram configuration saved to config/telegram.json")
        notifier = TelegramNotifier()

    if args.test:
        if notifier.is_configured():
            ok = notifier.send_message("🚀 *[AURUM TEST]* Telegram Alert Bot connected and operational!")
            print(f"[TEST] Alert sent result: {ok}")
        else:
            print("[TEST] Notifier is not configured yet. Run with --setup <BOT_TOKEN> <CHAT_ID>")
