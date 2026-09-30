from __future__ import annotations

from pathlib import Path
import pytest
from src.macro_intel import MacroIntelligenceEngine
from src.market_memory import MarketMemoryEngine


def test_macro_intelligence_engine():
    engine = MacroIntelligenceEngine()
    snapshot = engine.get_current_macro_snapshot()
    assert "timestamp" in snapshot
    assert len(snapshot["core_geopolitical_themes"]) >= 3
    assert "XAUUSD" in snapshot["asset_implications"]
    assert "US100" in snapshot["asset_implications"]

    briefing = engine.format_macro_briefing()
    assert "AURUM Macro & Geopolitical Intelligence Briefing" in briefing
    assert "XAUUSD" in briefing


def test_market_memory_engine(tmp_path: Path):
    mem_file = tmp_path / "test_memory.json"
    journal_file = tmp_path / "test_journal.md"

    engine = MarketMemoryEngine(memory_file=str(mem_file), journal_file=str(journal_file))
    assert len(engine.events) == 0

    engine.record_day(
        date="2026-09-29",
        geopolitical_narrative="Test narrative",
        macro_catalysts=["Test catalyst 1"],
        us100_data={"london_range": 190.0, "qualified": True},
        gold_data={"london_range": 60.0, "qualified": True},
        causal_retrospective="Test retrospective",
        actionable_lessons=["Lesson 1"]
    )

    assert len(engine.events) == 1
    assert mem_file.exists()
    assert journal_file.exists()

    latest = engine.get_latest()
    assert latest is not None
    assert latest["date"] == "2026-09-29"

    # Reload from disk
    engine2 = MarketMemoryEngine(memory_file=str(mem_file), journal_file=str(journal_file))
    assert len(engine2.events) == 1
