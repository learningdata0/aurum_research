from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Dict, Optional
import urllib.parse
import urllib.request


class TelegramNotifier:
    """
    Lightweight, institutional Telegram Notification Engine for AURUM.
    Dispatches instant alerts for trade executions, stop-loss / take-profit hits,
    session milestones, and portfolio equity updates directly to mobile devices.
    Includes persistent deduplication and rate-limiting to prevent repeat alerts.
    """

    def __init__(self, config_path: str = "config/telegram.json", dedup_cache_path: str = "reports/.telegram_dedup_cache.json"):
        self.config_file = Path(config_path)
        self.dedup_cache_file = Path(dedup_cache_path)
        self.bot_token: Optional[str] = os.environ.get("AURUM_TELEGRAM_BOT_TOKEN")
        self.chat_id: Optional[str] = os.environ.get("AURUM_TELEGRAM_CHAT_ID")
        self._dedup_cache: Dict[str, float] = {}
        self._load_config()
        self._load_dedup_cache()

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

    def _load_dedup_cache(self):
        if self.dedup_cache_file.exists():
            try:
                with open(self.dedup_cache_file, "r", encoding="utf-8") as f:
                    self._dedup_cache = json.load(f)
            except Exception:
                self._dedup_cache = {}

    def _save_dedup_cache(self):
        try:
            self.dedup_cache_file.parent.mkdir(parents=True, exist_ok=True)
            # Prune cache entries older than 24 hours
            now = time.time()
            clean_cache = {k: v for k, v in self._dedup_cache.items() if (now - v) < 86400}
            with open(self.dedup_cache_file, "w", encoding="utf-8") as f:
                json.dump(clean_cache, f, indent=2)
            self._dedup_cache = clean_cache
        except Exception:
            pass

    def is_configured(self) -> bool:
        if not self.bot_token or not self.chat_id or "YOUR_" in str(self.bot_token) or self.chat_id == "None":
            self._load_config()
        return bool(self.bot_token and self.chat_id and "YOUR_" not in str(self.bot_token) and self.chat_id != "None")

    def send_message(self, text: str, dedup_key: Optional[str] = None, cooldown_seconds: int = 1800) -> bool:
        """Sends a markdown-formatted message to the configured Telegram chat with deduplication."""
        if not self.is_configured():
            print(f"[TELEGRAM STANDBY] Not configured yet. Alert queued:\n{text}")
            return False

        now = time.time()
        # 1. Check explicit dedup_key cooldown
        if dedup_key:
            last_sent = self._dedup_cache.get(dedup_key, 0.0)
            if (now - last_sent) < cooldown_seconds:
                print(f"[TELEGRAM DEDUP] Suppressed duplicate alert: {dedup_key} (cooldown {cooldown_seconds}s)")
                return False

        # 2. Check content hash cooldown (prevent identical text sent repeatedly)
        content_hash = "hash_" + hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:16]
        last_sent_hash = self._dedup_cache.get(content_hash, 0.0)
        if (now - last_sent_hash) < cooldown_seconds:
            print(f"[TELEGRAM DEDUP] Suppressed duplicate message text (cooldown {cooldown_seconds}s)")
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
                ok = result.get("ok", False)
                if ok:
                    if dedup_key:
                        self._dedup_cache[dedup_key] = now
                    self._dedup_cache[content_hash] = now
                    self._save_dedup_cache()
                return ok
        except Exception as e:
            print(f"[TELEGRAM ERROR] Failed to send alert: {e}")
            return False

    def send_pre_entry_analysis(
        self,
        asset: str,
        direction: str,
        timeframe: str = "PERIOD_M1",
        setup: str = "London Sweep & Reclaim (H17)",
        trigger_level: float = 0.0,
        est_entry: float = 0.0,
        est_sl: float = 0.0,
        tp1: float = 0.0,
        tp2: float = 0.0,
        tp3: float = 0.0,
        tp4: float = 0.0,
        risk_pct: float = 0.25,
        risk_cash: float = 25.0,
        dedup_key: Optional[str] = None,
        cooldown_seconds: int = 2700
    ):
        is_gold = "XAU" in asset.upper()
        mult = 10.0 if is_gold else 1.0
        unit_label = "pip" if is_gold else "pt"

        sl_dist = abs(est_entry - est_sl)
        sl_units = sl_dist * mult
        tp1_dist = abs(tp1 - est_entry) * mult
        tp2_dist = abs(tp2 - est_entry) * mult
        tp3_dist = abs(tp3 - est_entry) * mult
        tp4_dist = abs(tp4 - est_entry) * mult
        rr_ratio = (abs(tp3 - est_entry) / sl_dist) if sl_dist > 0 else 0.0

        dir_str = direction.upper()
        emoji = "🟢" if dir_str == "BUY" else "🔴"

        msg = (
            f"🔍 *[{asset} RADAR — PRE-ENTRY DEAL ANALYSIS]*\n\n"
            f"*Setup:* `{setup}`\n"
            f"*Market Bias:* *{dir_str}* {emoji}\n"
            f"*Timeframe:* `{timeframe}`\n\n"
            f"• *Trigger Level:* `{trigger_level:,.2f}` (Liquidity Sweep)\n"
            f"• *Projected Entry:* `{est_entry:,.2f}`\n"
            f"• *Anchor SL:* `{est_sl:,.2f}` ({sl_units:.0f} {unit_label})\n"
            f"• *TP1 Level:* `{tp1:,.2f}` ({tp1_dist:.0f} {unit_label}) — 50% Bank + BE\n"
            f"• *TP2 Level:* `{tp2:,.2f}` ({tp2_dist:.0f} {unit_label}) — Trail Lock 1\n"
            f"• *TP3 Target:* `{tp3:,.2f}` ({tp3_dist:.0f} {unit_label}) — London Midpoint\n"
            f"• *TP4 Runner:* `{tp4:,.2f}` ({tp4_dist:.0f} {unit_label}) — Opposing Pool\n"
            f"• *Projected R:R:* `1 : {rr_ratio:.2f}R`\n"
            f"• *Risk Allocation:* `{risk_pct:.2f}% (${risk_cash:.2f})`\n\n"
            f"⏳ *Bar confirmation in progress — Awaiting clean execution trigger...*"
        )
        key = dedup_key or f"radar_{asset}_{dir_str}"
        return self.send_message(msg, dedup_key=key, cooldown_seconds=cooldown_seconds)

    def send_trade_open_alert(
        self,
        asset: str,
        direction: str,
        ticket: int,
        entry: float,
        sl: float,
        tp1: float,
        tp2: float,
        tp3: float,
        tp4: float,
        units: float = 0.09,
        risk_cash: float = 25.0,
        risk_pct: float = 0.25,
        timeframe: str = "PERIOD_M1",
        mode: str = "Single Entry Multi-TP",
        dedup_key: Optional[str] = None
    ):
        dir_str = direction.upper()
        header = f"🔴 *SELL OPENED*" if dir_str == "SELL" else f"🟢 *BUY OPENED*"

        is_gold = "XAU" in asset.upper()
        mult = 10.0 if is_gold else 1.0
        unit_label = "pip" if is_gold else "pt"

        sl_pts = abs(entry - sl)
        sl_units = sl_pts * mult
        tp1_units = abs(tp1 - entry) * mult
        tp2_units = abs(tp2 - entry) * mult
        tp3_units = abs(tp3 - entry) * mult
        tp4_units = abs(tp4 - entry) * mult

        msg = (
            f"{header}\n\n"
            f"*Symbol:* `{asset}`\n"
            f"*Timeframe:* `{timeframe}`\n"
            f"*Ticket:* `#{ticket}`\n\n"
            f"*Lot / Units:* `{units:.2f}`\n"
            f"*Entry:* `{entry:,.3f}`\n"
            f"*Stop Loss:* `{sl:,.3f}` ({sl_units:.0f} {unit_label})\n"
            f"*TP1 Level:* `{tp1:,.3f}` ({tp1_units:.0f} {unit_label})\n"
            f"*TP2 Level:* `{tp2:,.3f}` ({tp2_units:.0f} {unit_label})\n"
            f"*TP3 Target:* `{tp3:,.3f}` ({tp3_units:.0f} {unit_label})\n"
            f"*TP4 Runner:* `{tp4:,.3f}` ({tp4_units:.0f} {unit_label})\n"
            f"*Risk:* `{risk_pct:.2f}%` (`${risk_cash:.2f}`)\n"
            f"*Mode:* `{mode}`\n"
            f"*TP1 Management:* `Bank 50% Profit + Move SL to Breakeven`\n"
            f"*TP2 Management:* `Dynamic ATR Multi-Stage Trailing Stop`"
        )
        key = dedup_key or f"open_{asset}_{ticket}"
        return self.send_message(msg, dedup_key=key, cooldown_seconds=86400)

    def send_trade_close_alert(
        self,
        asset: str,
        ticket: int,
        direction: str,
        pnl: float,
        r_mult: float,
        reason: str,
        balance: float,
        dedup_key: Optional[str] = None
    ):
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
        key = dedup_key or f"close_{asset}_{ticket}_{reason}"
        return self.send_message(msg, dedup_key=key, cooldown_seconds=86400)

    def send_session_summary(self, session_title: str, summary_text: str):
        msg = f"⏱️ *[AURUM DESK SESSION UPDATE]*\n*{session_title}*\n\n{summary_text}"
        return self.send_message(msg)

    @classmethod
    def fetch_updates(cls, bot_token: str) -> list:
        url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AurumDesk/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("result", [])
        except Exception as e:
            print(f"[TELEGRAM ERROR] getUpdates failed: {e}")
            return []

    @classmethod
    def discover_and_save(cls, bot_token: str, timeout_sec: int = 60) -> Optional[str]:
        print(f"[AURUM TELEGRAM] Polling for /start message on token {bot_token[:10]}... (Timeout {timeout_sec}s)")
        print("[AURUM TELEGRAM] Please open the bot in Telegram and press START or send any message.")
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            updates = cls.fetch_updates(bot_token)
            if updates:
                last_update = updates[-1]
                chat = last_update.get("message", {}).get("chat", {}) or last_update.get("my_chat_member", {}).get("chat", {})
                chat_id = str(chat.get("id"))
                user_first = chat.get("first_name", "Trader")
                if chat_id:
                    print(f"✅ [AURUM TELEGRAM] Detected Chat ID: {chat_id} (User: {user_first})")
                    cfg_dir = Path("config")
                    cfg_dir.mkdir(exist_ok=True)
                    with open(cfg_dir / "telegram.json", "w", encoding="utf-8") as f:
                        json.dump({"bot_token": bot_token, "chat_id": chat_id}, f, indent=2)
                    notifier = cls()
                    notifier.send_message(
                        f"🚀 *[AURUM QUANT DESK CONNECTED]*\n\n"
                        f"أهلاً بك يا {user_first}! تم ربط نظام أوروم للتداول الكمي بنجاح.\n"
                        f"ستصلك هنا إشعارات فورية بكل الصفقات المفتوحة والمغلقة، ونسب الأرباح، وتحديثات الجلسات لحظة بلحظة.\n\n"
                        f"• *Symbol Focus:* `US100 (UT100Roll)` & `XAUUSD`\n"
                        f"• *Execution Mode:* `v1.1 Shadow Engine (Virtual Risk=0)`\n"
                        f"• *Status:* `ONLINE & ACTIVE`"
                    )
                    return chat_id
            time.sleep(2)
        print("❌ [AURUM TELEGRAM] Timeout reached without receiving any message.")
        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AURUM Telegram Notifier")
    parser.add_argument("--test", action="store_true", help="Send test message")
    parser.add_argument("--setup", nargs=2, metavar=("BOT_TOKEN", "CHAT_ID"), help="Configure credentials")
    parser.add_argument("--discover", type=str, metavar="BOT_TOKEN", help="Poll and auto-discover chat ID from incoming message")
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

    if args.discover:
        found_id = TelegramNotifier.discover_and_save(args.discover, timeout_sec=90)
        if found_id:
            print(f"[DISCOVER SUCCESS] Saved chat_id: {found_id}")
        else:
            print("[DISCOVER FAILED] No message received.")

    if args.test:
        if notifier.is_configured():
            ok = notifier.send_message("🚀 *[AURUM TEST]* Telegram Alert Bot connected and operational!")
            print(f"[TEST] Alert sent result: {ok}")
        else:
            print("[TEST] Notifier is not configured yet. Run with --setup <BOT_TOKEN> <CHAT_ID> or --discover <BOT_TOKEN>")

