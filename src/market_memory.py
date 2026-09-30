from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class MarketSessionMemory:
    date: str  # YYYY-MM-DD
    timestamp_utc: str
    geopolitical_narrative: str
    macro_catalysts: List[str]
    us100_data: Dict[str, Any]
    gold_data: Dict[str, Any]
    causal_retrospective: str
    actionable_lessons: List[str]


class MarketMemoryEngine:
    """
    Persistent Episodic Market Memory for AURUM.
    Records daily macroeconomic context, geopolitical catalysts, session liquidity structures,
    and causal post-trade autopsies so the system retains institutional learning across time.
    """

    def __init__(self, memory_file: str = "reports/market_memory.json", journal_file: str = "reports/market_memory_journal.md"):
        self.memory_path = Path(memory_file)
        self.journal_path = Path(journal_file)
        self.memory_path.parent.mkdir(parents=True, exist_ok=True)
        self.events: List[Dict[str, Any]] = self._load()

    def _load(self) -> List[Dict[str, Any]]:
        if self.memory_path.exists():
            try:
                with open(self.memory_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def save(self):
        with open(self.memory_path, "w", encoding="utf-8") as f:
            json.dump(self.events, f, indent=2, ensure_ascii=False)
        self.generate_journal()

    def record_day(
        self,
        date: str,
        geopolitical_narrative: str,
        macro_catalysts: List[str],
        us100_data: Dict[str, Any],
        gold_data: Dict[str, Any],
        causal_retrospective: str,
        actionable_lessons: List[str]
    ):
        """Appends or updates memory for a given trading day."""
        mem = MarketSessionMemory(
            date=date,
            timestamp_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            geopolitical_narrative=geopolitical_narrative,
            macro_catalysts=macro_catalysts,
            us100_data=us100_data,
            gold_data=gold_data,
            causal_retrospective=causal_retrospective,
            actionable_lessons=actionable_lessons
        )

        # Update if existing, else append
        updated = False
        for i, ev in enumerate(self.events):
            if ev.get("date") == date:
                self.events[i] = asdict(mem)
                updated = True
                break
        if not updated:
            self.events.append(asdict(mem))

        self.save()

    def get_latest(self) -> Optional[Dict[str, Any]]:
        return self.events[-1] if self.events else None

    def generate_journal(self):
        """Generates a human-readable and agent-accessible Markdown journal of market memory."""
        md = [
            "# AURUM Institutional Market Memory & Causal Journal",
            "**Purpose:** Persistent archive recording geopolitical catalysts, session liquidity structures, and empirical market learnings.\n",
            "---"
        ]

        for ev in reversed(self.events):
            md.append(f"## 📅 Date: {ev['date']} (Logged: {ev['timestamp_utc']})")
            md.append(f"### 🌍 Geopolitical Narrative & Macro Catalysts")
            md.append(f"> {ev['geopolitical_narrative']}\n")
            for c in ev.get("macro_catalysts", []):
                md.append(f"- **Catalyst:** {c}")

            md.append(f"\n### 📊 Asset Structural Analysis")
            u = ev.get("us100_data", {})
            md.append(f"#### US100 (Nasdaq-100 `UT100Roll`)")
            md.append(f"- **London Range:** {u.get('london_range', 'N/A')} pts (High: {u.get('london_high', 'N/A')}, Low: {u.get('london_low', 'N/A')}, Mid: {u.get('london_mid', 'N/A')})")
            md.append(f"- **Range Qualified ($\ge 140$ pts):** {u.get('qualified', False)}")
            md.append(f"- **NY Session Action:** {u.get('ny_action', 'N/A')}")
            md.append(f"- **Trade Execution / Outcome:** {u.get('trade_outcome', 'N/A')}")

            g = ev.get("gold_data", {})
            md.append(f"\n#### XAUUSD (Gold)")
            md.append(f"- **London Range:** {g.get('london_range', 'N/A')} pts (High: {g.get('london_high', 'N/A')}, Low: {g.get('london_low', 'N/A')}, Mid: {g.get('london_mid', 'N/A')})")
            md.append(f"- **Range Qualified ($\ge 55$ pts):** {g.get('qualified', False)}")
            md.append(f"- **NY Session Action:** {g.get('ny_action', 'N/A')}")
            md.append(f"- **Trade Execution / Outcome:** {g.get('trade_outcome', 'N/A')}")

            md.append(f"\n### 💡 Causal Retrospective (Why did the market move?)")
            md.append(f"{ev.get('causal_retrospective', 'N/A')}\n")

            md.append(f"### 🧠 Institutional Takeaways & Future Adaptations")
            for lesson in ev.get("actionable_lessons", []):
                md.append(f"- ✅ {lesson}")

            md.append("\n---\n")

        with open(self.journal_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md))


if __name__ == "__main__":
    mem_engine = MarketMemoryEngine()
    print(f"Loaded {len(mem_engine.events)} memory entries.")
