"""Tests for the memory system."""

import os
import pytest
from core.memory import MemoryManager, MemoryEntry, MEMORY_MARKER
from core.skills import parse_frontmatter
from rag.vector_store import LocalVectorStore
from rag.chunker import TextChunk


# --- MemoryEntry basics ---

def test_memory_entry_defaults():
    entry = MemoryEntry(name="test", description="desc", type="user", content="body")
    assert entry.type == "user"
    assert entry.created  # auto-filled
    assert entry.updated


def test_memory_entry_invalid_type_fallback():
    entry = MemoryEntry(name="x", description="d", type="bogus", content="c")
    assert entry.type == "user"


# --- MemoryManager save/load/forget ---

def test_memory_manager_save_and_load(tmp_path):
    manager = MemoryManager(str(tmp_path))
    entry = manager.save("test-memory", "A test memory", "Remember this content", "user")
    assert entry.name == "test-memory"
    assert entry.type == "user"
    assert entry.content == "Remember this content"

    # File should exist
    assert os.path.exists(entry.file_path)
    with open(entry.file_path, "r", encoding="utf-8") as f:
        raw = f.read()
    assert "---" in raw
    assert "Remember this content" in raw

    # Reload
    entries = manager.load_entries()
    assert len(entries) == 1
    assert entries[0].name == "test-memory"
    assert entries[0].description == "A test memory"


def test_memory_manager_update_existing(tmp_path):
    manager = MemoryManager(str(tmp_path))
    manager.save("prefs", "User prefs", "likes dark mode", "user")
    manager.save("prefs", "Updated prefs", "likes light mode now", "feedback")

    entries = manager.load_entries()
    assert len(entries) == 1
    assert entries[0].content == "likes light mode now"
    assert entries[0].type == "feedback"


def test_memory_manager_forget(tmp_path):
    manager = MemoryManager(str(tmp_path))
    manager.save("to-delete", "temp", "content", "user")
    assert manager.forget("to-delete") is True
    assert manager.forget("nonexistent") is False
    entries = manager.load_entries()
    assert len(entries) == 0


def test_memory_manager_list_empty(tmp_path):
    manager = MemoryManager(str(tmp_path))
    assert manager.list_entries() == []


def test_memory_manager_index_file(tmp_path):
    manager = MemoryManager(str(tmp_path))
    manager.save("learning-style", "Visual learner", "Prefers diagrams", "user")

    index_path = os.path.join(str(tmp_path), ".bobodan", "MEMORY.md")
    assert os.path.exists(index_path)
    with open(index_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "learning-style" in content
    assert "Visual learner" in content


# --- Vector store integration ---

def test_memory_save_updates_vector_store(tmp_path):
    manager = MemoryManager(str(tmp_path))
    manager.save("python-level", "Python experience", "Intermediate Python developer", "user")

    store = LocalVectorStore(manager.index_path)
    store.load()
    assert len(store.chunks) > 0
    assert any("python" in c.get("source", "") for c in store.chunks)


def test_memory_forget_removes_from_vector_store(tmp_path):
    manager = MemoryManager(str(tmp_path))
    manager.save("temp-mem", "temporary", "will be deleted", "user")

    store = LocalVectorStore(manager.index_path)
    store.load()
    chunks_before = len(store.chunks)
    assert chunks_before > 0

    manager.forget("temp-mem")

    store.load()
    assert len(store.chunks) == 0


def test_memory_search(tmp_path):
    manager = MemoryManager(str(tmp_path))
    manager.save("learning-style", "Visual learner", "Prefers charts and diagrams over text", "user")
    manager.save("python-prefs", "Python setup", "Uses VS Code with Pylance", "project")

    results = manager.search("visual learning preferences")
    assert len(results) > 0
    # The learning-style memory should be more relevant
    assert any("learning" in r.get("source", "") for r in results)


# --- Vector store upsert ---

def test_vector_store_upsert_adds_new(tmp_path):
    store = LocalVectorStore(str(tmp_path / "index.json"))
    chunks = [TextChunk(id="c1", text="hello world", source="test")]
    store.upsert(chunks)
    store.load()
    assert len(store.chunks) == 1


def test_vector_store_upsert_replaces_existing(tmp_path):
    store = LocalVectorStore(str(tmp_path / "index.json"))
    chunks1 = [TextChunk(id="c1", text="old content", source="test")]
    store.upsert(chunks1)

    chunks2 = [TextChunk(id="c1", text="new content", source="test")]
    store.upsert(chunks2)

    store.load()
    assert len(store.chunks) == 1
    assert store.chunks[0]["text"] == "new content"


def test_vector_store_remove_by_source(tmp_path):
    store = LocalVectorStore(str(tmp_path / "index.json"))
    chunks = [
        TextChunk(id="c1", text="a", source="memory://foo"),
        TextChunk(id="c2", text="b", source="memory://bar"),
        TextChunk(id="c3", text="c", source="other://baz"),
    ]
    store.upsert(chunks)

    removed = store.remove_by_source("memory://")
    assert removed == 2
    store.load()
    assert len(store.chunks) == 1
    assert store.chunks[0]["source"] == "other://baz"


# --- Memory prompt ---

def test_build_memory_prompt_returns_none_when_empty(tmp_path):
    manager = MemoryManager(str(tmp_path))
    assert manager.build_memory_prompt() is None


def test_build_memory_prompt_contains_marker_and_content(tmp_path):
    manager = MemoryManager(str(tmp_path))
    manager.save("test", "Test memory", "Remember this", "user")

    prompt = manager.build_memory_prompt()
    assert prompt is not None
    assert MEMORY_MARKER in prompt
    assert "Remember this" in prompt
    assert "<memories>" in prompt
    assert "test" in prompt


def test_memory_prompt_groups_by_type(tmp_path):
    manager = MemoryManager(str(tmp_path))
    manager.save("user-pref", "User preference", "likes coffee", "user")
    manager.save("correction", "Feedback", "don't use jargon", "feedback")

    prompt = manager.build_memory_prompt()
    assert "User Profile" in prompt
    assert "User Feedback" in prompt


# --- Frontmatter parsing ---

def test_parse_frontmatter_valid():
    content = "---\nname: test\ntype: user\n---\nBody here"
    meta = parse_frontmatter(content)
    assert meta["name"] == "test"
    assert meta["type"] == "user"


def test_parse_frontmatter_missing():
    assert parse_frontmatter("no frontmatter") == {}


def test_parse_frontmatter_incomplete():
    assert parse_frontmatter("---\nname: test") == {}


# --- Stats ---

def test_memory_stats(tmp_path):
    manager = MemoryManager(str(tmp_path))
    manager.save("a", "desc a", "content a", "user")
    manager.save("b", "desc b", "content b", "feedback")

    stats = manager.get_stats()
    assert stats["total"] == 2
    assert stats["by_type"]["user"] == 1
    assert stats["by_type"]["feedback"] == 1
    assert stats["vector_chunks"] > 0


# --- Agent tools ---

def test_memory_save_tool(tmp_path, monkeypatch):
    from tools.memory_tools import memory_save

    class FakeSession:
        workspace_root = str(tmp_path)

    result = memory_save("test-tool", "Tool test", "saved via tool", "user", session=FakeSession())
    assert result.ok
    assert "test-tool" in result.content


def test_memory_save_tool_empty_name(tmp_path):
    from tools.memory_tools import memory_save

    class FakeSession:
        workspace_root = str(tmp_path)

    result = memory_save("", "desc", "content", session=FakeSession())
    assert not result.ok


def test_memory_recall_tool_no_memories(tmp_path):
    from tools.memory_tools import memory_recall

    class FakeSession:
        workspace_root = str(tmp_path)

    result = memory_recall("anything", session=FakeSession())
    assert result.ok
    assert "No memories" in result.content


def test_memory_recall_tool_with_memories(tmp_path):
    from tools.memory_tools import memory_save, memory_recall

    class FakeSession:
        workspace_root = str(tmp_path)

    session = FakeSession()
    memory_save("learning", "Learning style", "visual learner who likes diagrams", session=session)

    result = memory_recall("how do I learn best", session=session)
    assert result.ok
    assert "learning" in result.content.lower() or "visual" in result.content.lower()


# --- Agent loop memory injection ---

def test_agent_loop_injects_memory_prompt(monkeypatch):
    from core.agent_loop import AgentLoop
    from core.session import Session

    class DummyProvider:
        def complete(self, messages, tools=None):
            from providers.types import LLMResponse
            return LLMResponse(content="ok")

        def get_name(self):
            return "dummy"

    session = Session.new("/tmp")
    monkeypatch.setattr("core.agent_loop.get_tools_schema", lambda: [])
    agent = AgentLoop(DummyProvider(), session, memory_prompt=f"{MEMORY_MARKER}\nTest memory content")

    # run() triggers injection
    agent.run("hello")

    system_messages = [m for m in session.messages if m.get("role") == "system"]
    assert any(MEMORY_MARKER in m.get("content", "") for m in system_messages)


def test_agent_loop_no_duplicate_memory_injection(monkeypatch):
    from core.agent_loop import AgentLoop
    from core.session import Session

    class DummyProvider:
        def complete(self, messages, tools=None):
            from providers.types import LLMResponse
            return LLMResponse(content="ok")

        def get_name(self):
            return "dummy"

    session = Session.new("/tmp")
    # Pre-inject memory prompt
    session.add_message("system", f"{MEMORY_MARKER}\nExisting memory")

    monkeypatch.setattr("core.agent_loop.get_tools_schema", lambda: [])
    agent = AgentLoop(DummyProvider(), session, memory_prompt=f"{MEMORY_MARKER}\nNew memory")

    agent.run("hello")

    memory_msgs = [m for m in session.messages if m.get("role") == "system" and MEMORY_MARKER in m.get("content", "")]
    assert len(memory_msgs) == 1
    assert "Existing memory" in memory_msgs[0]["content"]


# --- REPL /memory commands ---

def test_memory_command_list(tmp_path, capsys):
    from cli.repl import REPL

    repl = REPL()
    repl.memory_manager = MemoryManager(str(tmp_path))
    repl.memory_manager.save("test", "Test entry", "content", "user")

    repl.handle_memory_command("list")
    output = capsys.readouterr().out
    assert "test" in output
    assert "Test entry" in output


def test_memory_command_show(tmp_path, capsys):
    from cli.repl import REPL

    repl = REPL()
    repl.memory_manager = MemoryManager(str(tmp_path))
    repl.memory_manager.save("my-pref", "User preference", "likes dark mode", "user")

    repl.handle_memory_command("show my-pref")
    output = capsys.readouterr().out
    assert "my-pref" in output
    assert "likes dark mode" in output


def test_memory_command_search(tmp_path, capsys):
    from cli.repl import REPL

    repl = REPL()
    repl.memory_manager = MemoryManager(str(tmp_path))
    repl.memory_manager.save("python-setup", "Python config", "Uses VS Code", "project")

    repl.handle_memory_command("search python")
    output = capsys.readouterr().out
    assert "python" in output.lower()


def test_memory_command_forget(tmp_path, capsys):
    from cli.repl import REPL

    repl = REPL()
    repl.memory_manager = MemoryManager(str(tmp_path))
    repl.memory_manager.save("temp", "temporary", "content", "user")
    repl.memory_count = 1

    repl.handle_memory_command("forget temp")
    output = capsys.readouterr().out
    assert "forgotten" in output.lower()
    assert repl.memory_count == 0


def test_memory_command_stats(tmp_path, capsys):
    from cli.repl import REPL

    repl = REPL()
    repl.memory_manager = MemoryManager(str(tmp_path))
    repl.memory_manager.save("a", "desc a", "content a", "user")

    repl.handle_memory_command("stats")
    output = capsys.readouterr().out
    assert "total" in output.lower() or "1" in output


def test_memory_command_empty(tmp_path, capsys):
    from cli.repl import REPL

    repl = REPL()
    repl.memory_manager = MemoryManager(str(tmp_path))

    repl.handle_memory_command("")
    output = capsys.readouterr().out
    assert "Memory commands" in output


def test_memory_command_disabled(capsys):
    from cli.repl import REPL

    repl = REPL()
    repl.memory_manager = None

    repl.handle_memory_command("list")
    output = capsys.readouterr().out
    assert "not enabled" in output.lower()
