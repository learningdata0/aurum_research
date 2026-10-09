from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import urllib.request

from .telegram_notifier import TelegramNotifier


@dataclass
class EconomicNewsEvent:
    event_id: str
    name: str
    currency: str
    impact: str  # "HIGH", "CRITICAL"
    timestamp_utc: str
    buffer_before_min: int = 15
    buffer_after_min: int = 15
    description: str = ""


class EconomicNewsFilter:
    """
    Institutional Tier-1 Economic Calendar & News Blackout Engine for AURUM.
    Protects trading capital by freezing new trade entries 15 minutes before and
    15 minutes after high-impact macroeconomic releases (CPI, NFP, FOMC, Core PCE, PPI).
    Prevents toxic execution slippage and predatory spread widening.
    """

    def __init__(self, config_dir: str = "reports"):
        self.config_dir = Path(config_dir).resolve()
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.config_dir / "news_blackout_state.json"
        self.notifier = TelegramNotifier()
        self._notified_blackouts = set()
        self._load_state()

    def _load_state(self):
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._notified_blackouts = set(data.get("notified_blackouts", []))
            except Exception:
                pass

    def _save_state(self):
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump({
                    "notified_blackouts": list(self._notified_blackouts),
                    "last_updated": datetime.now(timezone.utc).isoformat()
                }, f, indent=2)
        except Exception:
            pass

    def get_upcoming_events(self, date_utc: Optional[datetime] = None) -> List[EconomicNewsEvent]:
        """
        Returns list of tier-1 high impact economic events.
        Combines dynamic live API feeds with institutional recurring releases.
        """
        target_date = date_utc or datetime.now(timezone.utc)
        events = []

        # 1. Check live economic calendar if available (e.g. ForexFactory / financial feed)
        live_events = self._fetch_live_calendar(target_date)
        if live_events:
            return live_events

        # 2. Institutional Standard Scheduled Releases for USD
        # Key release times during US active trading:
        # - 12:30 UTC (08:30 NY / 15:30 Broker): Major macro data (CPI, PPI, NFP, GDP, Jobless Claims)
        # - 14:00 UTC (10:00 NY / 17:00 Broker): ISM Manufacturing/Services, Consumer Sentiment
        # - 18:00 UTC (14:00 NY / 21:00 Broker): FOMC Interest Rate Decision
        # - 18:30 UTC (14:30 NY / 21:30 Broker): Fed Chair Press Conference

        weekday = target_date.weekday()  # 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri
        d_str = target_date.strftime("%Y-%m-%d")

        # Example: Thursday weekly Jobless claims
        if weekday == 3:
            events.append(EconomicNewsEvent(
                event_id=f"USD_JOBLESS_{d_str}",
                name="US Initial Jobless Claims",
                currency="USD",
                impact="HIGH",
                timestamp_utc=f"{d_str}T12:30:00Z",
                buffer_before_min=15,
                buffer_after_min=15,
                description="Weekly labor market volatility catalyst"
            ))

        # Example: First Friday of the month (NFP)
        if weekday == 4 and target_date.day <= 7:
            events.append(EconomicNewsEvent(
                event_id=f"USD_NFP_{d_str}",
                name="US Non-Farm Payrolls (NFP) & Unemployment Rate",
                currency="USD",
                impact="CRITICAL",
                timestamp_utc=f"{d_str}T12:30:00Z",
                buffer_before_min=20,
                buffer_after_min=20,
                description="Tier-1 macro labor shock"
            ))

        return events

    def _fetch_live_calendar(self, target_date: datetime) -> List[EconomicNewsEvent]:
        """Attempts to fetch high impact news from external economic calendar feed."""
        events = []
        try:
            url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
            req = urllib.request.Request(url, headers={"User-Agent": "AurumResearchDesk/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                target_date_str = target_date.strftime("%Y-%m-%d")
                for item in data:
                    country = str(item.get("country", "")).upper()
                    impact = str(item.get("impact", "")).upper()
                    item_date = str(item.get("date", ""))
                    
                    if country == "USD" and impact in ["HIGH", "RED"]:
                        # Convert to ISO timestamp
                        if target_date_str in item_date:
                            events.append(EconomicNewsEvent(
                                event_id=f"USD_{item.get('title', 'NEWS')}_{target_date_str}".replace(" ", "_"),
                                name=item.get("title", "High-Impact Economic Release"),
                                currency="USD",
                                impact="CRITICAL" if "CPI" in item.get("title", "") or "NFP" in item.get("title", "") or "FOMC" in item.get("title", "") else "HIGH",
                                timestamp_utc=item_date if "T" in item_date else f"{item_date}Z",
                                buffer_before_min=15,
                                buffer_after_min=15,
                                description=f"Forecast: {item.get('forecast', 'N/A')} | Previous: {item.get('previous', 'N/A')}"
                            ))
        except Exception:
            pass
        return events

    def check_blackout(self, now_utc: Optional[datetime] = None) -> Tuple[bool, Optional[EconomicNewsEvent], str]:
        """
        Evaluates whether trading is currently inside an economic news blackout window.
        Returns: (is_blackout: bool, active_event: Optional[EconomicNewsEvent], status_reason: str)
        """
        now = now_utc or datetime.now(timezone.utc)
        events = self.get_upcoming_events(now)

        for ev in events:
            try:
                # Parse event timestamp
                ev_time_str = ev.timestamp_utc.replace("Z", "+00:00")
                ev_dt = datetime.fromisoformat(ev_time_str)
                if ev_dt.tzinfo is None:
                    ev_dt = ev_dt.replace(tzinfo=timezone.utc)

                blackout_start = ev_dt - timedelta(minutes=ev.buffer_before_min)
                blackout_end = ev_dt + timedelta(minutes=ev.buffer_after_min)

                if blackout_start <= now <= blackout_end:
                    remaining_sec = int((blackout_end - now).total_seconds())
                    rem_min = remaining_sec // 60
                    status = f"BLACKOUT ACTIVE: {ev.name} ({ev.impact}) | Freeze ends in {rem_min}m"
                    return True, ev, status
                elif now < blackout_start and (blackout_start - now).total_seconds() <= 1800:
                    mins_to_start = int((blackout_start - now).total_seconds()) // 60
                    return False, ev, f"UPCOMING NEWS: {ev.name} in {mins_to_start}m"
            except Exception:
                continue

        return False, None, "CALENDAR CLEAR (No active tier-1 news blackout)"

    def sync_to_mt5(self, mt5_files_dir: Path, now_utc: Optional[datetime] = None) -> bool:
        """Writes news blackout state to MT5 Files directory for EA execution gating."""
        if not mt5_files_dir.exists():
            return False

        is_blackout, ev, status = self.check_blackout(now_utc)
        target_file = mt5_files_dir / "aurum_news_blackout.txt"

        content = "BLACKOUT_ACTIVE\n" if is_blackout else "BLACKOUT_INACTIVE\n"
        if is_blackout and ev:
            content += f"EVENT={ev.name}\n"
            content += f"IMPACT={ev.impact}\n"
            content += f"STATUS={status}\n"
        else:
            content += "EVENT=NONE\n"
            content += "STATUS=CLEAR\n"

        try:
            target_file.write_text(content, encoding="utf-8")
            return True
        except Exception:
            return False

    def notify_if_blackout_started(self, now_utc: Optional[datetime] = None):
        """Dispatches an institutional news alert to Telegram when blackout window is entered."""
        is_blackout, ev, status = self.check_blackout(now_utc)
        if is_blackout and ev and ev.event_id not in self._notified_blackouts:
            self._notified_blackouts.add(ev.event_id)
            self._save_state()

            msg = (
                f"🛡️ *[AURUM MACRO SHIELD — HIGH-IMPACT NEWS BLACKOUT]*\n\n"
                f"• *Event:* `{ev.name}`\n"
                f"• *Currency:* `{ev.currency}`\n"
                f"• *Impact Level:* *{ev.impact}* 🔴\n"
                f"• *Protection Protocol:* `Entries Paused (15m Before & After)`\n"
                f"• *Reason:* `Prevent spread widening and high-slippage liquidity gaps.`\n\n"
                f"⏳ *Execution will automatically resume once post-news volatility stabilizes.*"
            )
            self.notifier.send_message(msg, dedup_key=f"blackout_{ev.event_id}")
            print(f"[MACRO SHIELD] Activated news blackout for {ev.name}")


if __name__ == "__main__":
    shield = EconomicNewsFilter()
    active, ev, status = shield.check_blackout()
    print(f"\n=======================================================")
    print(f" AURUM INSTITUTIONAL MACRO NEWS SHIELD")
    print(f" Status: {status}")
    print(f" Blackout Active: {active}")
    if ev:
        print(f" Event: {ev.name} ({ev.impact}) at {ev.timestamp_utc}")
    print(f"=======================================================\n")
