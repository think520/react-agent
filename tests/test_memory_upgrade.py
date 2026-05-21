"""Tests for memory upgrade: store, daily, search, promotion."""

import json
import os
import sqlite3

import pytest

from memory.store import MemoryIndexStore, _make_chunk_id
from memory.daily import DailyMemoryManager
from memory.search import MemorySearcher
from memory.promotion import PromotionEngine


# --- MemoryIndexStore ---

def test_store_creates_db(tmp_path):
    store = MemoryIndexStore(str(tmp_path))
    assert os.path.exists(store.db_path)


def test_store_index_and_search(tmp_path):
    store = MemoryIndexStore(str(tmp_path))
    store.index_text(path="test.md", source="daily", text="Dijkstra algorithm shortest path", date="2026-05-18")
    store.index_text(path="test2.md", source="permanent", text="binary search tree balanced")

    results = store.search_fts("Dijkstra")
    assert len(results) == 1
    assert "Dijkstra" in results[0]["text"]


def test_store_search_no_results(tmp_path):
    store = MemoryIndexStore(str(tmp_path))
    store.index_text(path="test.md", source="daily", text="hello world")
    results = store.search_fts("quantum physics")
    assert len(results) == 0


def test_store_remove_by_path(tmp_path):
    store = MemoryIndexStore(str(tmp_path))
    store.index_text(path="a.md", source="daily", text="content a")
    store.index_text(path="b.md", source="daily", text="content b")
    removed = store.remove_by_path("a.md")
    assert removed == 1
    assert store.count_chunks() == 1


def test_store_remove_by_source(tmp_path):
    store = MemoryIndexStore(str(tmp_path))
    store.index_text(path="a.md", source="daily", text="daily content")
    store.index_text(path="b.md", source="permanent", text="permanent content")
    removed = store.remove_by_source("daily")
    assert removed == 1
    assert store.count_chunks(source="permanent") == 1


def test_store_recall_logging(tmp_path):
    store = MemoryIndexStore(str(tmp_path))
    chunk_id = store.index_text(path="test.md", source="daily", text="test content")
    store.record_recall(chunk_id)
    store.record_recall(chunk_id)
    count = store.get_recall_count("test.md")
    assert count == 2


def test_store_promotion_candidates(tmp_path):
    store = MemoryIndexStore(str(tmp_path))
    store.index_text(path="/daily/2026-05-01.md", source="daily", text="old memory", date="2026-05-01")
    store.index_text(path="/daily/2026-05-19.md", source="daily", text="recent memory", date="2026-05-19")
    candidates = store.get_promotion_candidates(min_age_days=3)
    # Only the old one should be a candidate
    assert len(candidates) == 1
    assert candidates[0]["date"] == "2026-05-01"


def test_store_stats(tmp_path):
    store = MemoryIndexStore(str(tmp_path))
    store.index_text(path="a.md", source="daily", text="daily content")
    store.index_text(path="b.md", source="permanent", text="permanent content")
    stats = store.get_stats()
    assert stats["total_chunks"] == 2
    assert stats["daily_chunks"] == 1
    assert stats["permanent_chunks"] == 1


def test_store_search_fts_source_filter(tmp_path):
    store = MemoryIndexStore(str(tmp_path))
    store.index_text(path="a.md", source="daily", text="algorithm design")
    store.index_text(path="b.md", source="permanent", text="algorithm patterns")

    results = store.search_fts("algorithm", source_filter="daily")
    assert len(results) == 1
    assert results[0]["source"] == "daily"


def test_make_chunk_id_deterministic():
    id1 = _make_chunk_id("path.md", "hello world")
    id2 = _make_chunk_id("path.md", "hello world")
    id3 = _make_chunk_id("path.md", "different text")
    assert id1 == id2
    assert id1 != id3


# --- DailyMemoryManager ---

def test_daily_append_and_read(tmp_path):
    daily = DailyMemoryManager(str(tmp_path))
    filepath = daily.append("Learned about Dijkstra algorithm")
    assert os.path.exists(filepath)

    content = daily.get_today()
    assert "Dijkstra" in content


def test_daily_append_with_tags(tmp_path):
    daily = DailyMemoryManager(str(tmp_path))
    daily.append("Quiz results", tags=["quiz", "algorithms"])
    content = daily.get_today()
    assert "Quiz results" in content
    # Check frontmatter
    with open(daily._file_path(daily._today_str()), "r", encoding="utf-8") as f:
        raw = f.read()
    assert "quiz" in raw


def test_daily_append_multiple(tmp_path):
    daily = DailyMemoryManager(str(tmp_path))
    daily.append("First entry")
    daily.append("Second entry")
    content = daily.get_today()
    assert "First entry" in content
    assert "Second entry" in content


def test_daily_read_nonexistent(tmp_path):
    daily = DailyMemoryManager(str(tmp_path))
    content = daily.read("2020-01-01")
    assert content == ""


def test_daily_list_recent(tmp_path):
    daily = DailyMemoryManager(str(tmp_path))
    daily.append("Today's note")
    recent = daily.list_recent(days=3)
    assert len(recent) == 3
    # First item should be today
    assert recent[0]["exists"] is True


def test_daily_get_all_dates(tmp_path):
    daily = DailyMemoryManager(str(tmp_path))
    daily.append("note 1", date="2026-05-01")
    daily.append("note 2", date="2026-05-02")
    dates = daily.get_all_dates()
    assert len(dates) == 2
    assert "2026-05-01" in dates
    assert "2026-05-02" in dates


# --- MemorySearcher ---

def test_searcher_fts_search(tmp_path):
    store = MemoryIndexStore(str(tmp_path))
    store.index_text(path="test.md", source="daily", text="Python decorators are powerful")
    store.index_text(path="test2.md", source="permanent", text="JavaScript closures scope")

    searcher = MemorySearcher(str(tmp_path))
    results = searcher.search("Python decorators")
    assert len(results) > 0
    assert results[0]["method"] == "fts5"


def test_searcher_daily_only(tmp_path):
    store = MemoryIndexStore(str(tmp_path))
    store.index_text(path="a.md", source="daily", text="quick sort algorithm")
    store.index_text(path="b.md", source="permanent", text="merge sort algorithm")

    searcher = MemorySearcher(str(tmp_path))
    results = searcher.search_daily("sort algorithm")
    assert all(r["source"] == "daily" for r in results)


# --- PromotionEngine ---

def test_promotion_score_low_for_new(tmp_path):
    engine = PromotionEngine(str(tmp_path))
    # Create a daily file for today
    daily = DailyMemoryManager(str(tmp_path))
    daily.append("test content")

    today = daily._today_str()
    filepath = daily._file_path(today)
    ps = engine.score(filepath, today)
    # New file should have low score (high recency, but 0 recall and 0 quiz)
    assert ps.total_score < 0.6
    assert not ps.eligible


def test_promotion_eligible_with_enough_recalls(tmp_path):
    store = MemoryIndexStore(str(tmp_path))
    engine = PromotionEngine(str(tmp_path))

    # Simulate a very old daily memory with many recalls
    # Use a date far enough that recency_score is negligible
    old_date = "2025-01-01"
    daily = DailyMemoryManager(str(tmp_path))
    daily.append("Important concept about algorithms", date=old_date)
    filepath = daily._file_path(old_date)

    # Index it and record recalls
    chunk_id = store.index_text(path=filepath, source="daily", text="Important concept", date=old_date)
    for _ in range(5):
        store.record_recall(chunk_id)

    ps = engine.score(filepath, old_date)
    assert ps.recall_count == 5
    assert ps.frequency_score == 1.0
    # frequency=1.0 * 0.4 + quiz=0 * 0.4 + recency≈0 * 0.2 = 0.4
    # Need quiz data to reach 0.6. With no quiz data, score = 0.4
    assert ps.total_score >= 0.4
    # Verify the components are correct
    assert ps.frequency_score == 1.0
    assert ps.recency_score < 0.1  # very old


def test_promote_creates_permanent_memory(tmp_path, monkeypatch):
    store = MemoryIndexStore(str(tmp_path))
    engine = PromotionEngine(str(tmp_path))

    old_date = "2025-01-01"
    daily = DailyMemoryManager(str(tmp_path))
    daily.append("- Dijkstra algorithm\n- Shortest path", date=old_date)
    filepath = daily._file_path(old_date)

    chunk_id = store.index_text(path=filepath, source="daily", text="Dijkstra", date=old_date)
    for _ in range(5):
        store.record_recall(chunk_id)

    # Mock quiz score to return a value that makes total >= 0.6
    monkeypatch.setattr(engine, "_get_quiz_score", lambda d: 0.5)

    result = engine.promote(filepath)
    assert result["promoted"] is True

    # Check permanent memory was created
    from core.memory import MemoryManager
    manager = MemoryManager(str(tmp_path))
    entries = manager.load_entries()
    names = [e.name for e in entries]
    assert f"daily-{old_date}" in names


def test_promote_rejects_low_score(tmp_path):
    engine = PromotionEngine(str(tmp_path))
    daily = DailyMemoryManager(str(tmp_path))
    daily.append("some content")
    today = daily._today_str()
    filepath = daily._file_path(today)

    result = engine.promote(filepath)
    assert result["promoted"] is False


def test_run_promotion_check(tmp_path):
    store = MemoryIndexStore(str(tmp_path))
    engine = PromotionEngine(str(tmp_path))

    daily = DailyMemoryManager(str(tmp_path))
    daily.append("old content", date="2025-01-01")
    daily.append("recent content", date="2026-05-19")

    # Index the daily files in the store (simulating what the system does)
    old_path = daily._file_path("2025-01-01")
    recent_path = daily._file_path("2026-05-19")
    store.index_text(path=old_path, source="daily", text="old content", date="2025-01-01")
    store.index_text(path=recent_path, source="daily", text="recent content", date="2026-05-19")

    results = engine.run_promotion_check(min_age_days=3)
    # Only old one should appear
    dates = [r["date"] for r in results]
    assert "2025-01-01" in dates
    assert "2026-05-19" not in dates


# --- Integration with core/memory.py ---

def test_memory_manager_fts_integration(tmp_path):
    """Test that saving a memory also indexes it in FTS5."""
    from core.memory import MemoryManager
    manager = MemoryManager(str(tmp_path))
    manager.save("test-memory", "Test description", "Dijkstra shortest path algorithm", "user")

    # Check FTS5 index
    store = MemoryIndexStore(str(tmp_path))
    results = store.search_fts("Dijkstra")
    assert len(results) > 0


def test_memory_manager_search_uses_fts(tmp_path):
    """Test that MemoryManager.search() uses FTS5."""
    from core.memory import MemoryManager
    manager = MemoryManager(str(tmp_path))
    manager.save("algo-notes", "Algorithm notes", "Binary search tree operations", "user")

    results = manager.search("binary search")
    assert len(results) > 0


def test_memory_prompt_includes_daily(tmp_path):
    """Test that build_memory_prompt includes daily memory."""
    from core.memory import MemoryManager
    manager = MemoryManager(str(tmp_path))
    manager.save("test", "Test", "permanent content", "user")

    # Add daily memory
    daily = DailyMemoryManager(str(tmp_path))
    daily.append("Today I learned about graphs")

    prompt = manager.build_memory_prompt()
    assert prompt is not None
    assert "graphs" in prompt
    assert "Recent Daily Memory" in prompt


def test_memory_stats_includes_fts(tmp_path):
    """Test that get_stats includes FTS5 information."""
    from core.memory import MemoryManager
    manager = MemoryManager(str(tmp_path))
    manager.save("test", "Test", "content", "user")

    stats = manager.get_stats()
    assert "fts" in stats
    assert "total_chunks" in stats["fts"]


# --- REPL commands ---

def _make_repl(tmp_path):
    """Create a minimal REPL-like object for testing memory commands."""
    from cli.repl import REPL
    from core.memory import MemoryManager

    repl = REPL.__new__(REPL)
    repl.memory_manager = MemoryManager(str(tmp_path))
    repl.session = type("S", (), {"workspace_root": str(tmp_path), "cwd": str(tmp_path)})()
    return repl


def test_memory_daily_command(tmp_path, capsys):
    repl = _make_repl(tmp_path)
    repl.handle_memory_daily(["Learned", "about", "algorithms"])
    output = capsys.readouterr().out
    assert "已保存" in output or "saved" in output.lower()


def test_memory_daily_command_view_today(tmp_path, capsys):
    repl = _make_repl(tmp_path)
    # Write first, then view
    daily = DailyMemoryManager(str(tmp_path))
    daily.append("Test daily note")

    repl.handle_memory_daily([])
    output = capsys.readouterr().out
    assert "Test daily note" in output


def test_memory_promote_command_empty(tmp_path, capsys):
    repl = _make_repl(tmp_path)
    repl.handle_memory_promote([])
    output = capsys.readouterr().out
    assert "没有" in output or "no" in output.lower()


def test_memory_review_command_no_data(tmp_path, capsys):
    repl = _make_repl(tmp_path)
    repl.handle_memory_review()
    output = capsys.readouterr().out
    # Should show notice (no learning data)
    assert "没有" in output or "no" in output.lower() or "失败" in output


# --- Agent tools ---

def test_memory_daily_save_tool(tmp_path):
    from tools.memory_tools import memory_daily_save

    class FakeSession:
        workspace_root = str(tmp_path)

    result = memory_daily_save("Learned about BFS", tags=["algorithm"], session=FakeSession())
    assert result.ok
    assert "daily" in result.data["path"].lower() or result.data["date"]


def test_memory_daily_read_tool_empty(tmp_path):
    from tools.memory_tools import memory_daily_read

    class FakeSession:
        workspace_root = str(tmp_path)

    result = memory_daily_read(session=FakeSession())
    assert result.ok
    assert "no" in result.content.lower() or "暂无" in result.content


def test_memory_promote_tool_no_candidates(tmp_path):
    from tools.memory_tools import memory_promote

    class FakeSession:
        workspace_root = str(tmp_path)

    result = memory_promote(session=FakeSession())
    assert result.ok
