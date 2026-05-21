"""Tests for wiki module: schema, compiler, index, lint."""

import json
import os
import pytest

from wiki.schema import (
    WikiPage, CompileResult, WikiConfig,
    load_wiki_state, save_wiki_state,
    PAGE_TYPES,
)
from wiki.index import WikiIndexer
from wiki.lint import WikiLinter, LintResult


# --- WikiPage ---

def test_wiki_page_defaults():
    page = WikiPage(title="Test", page_type="wiki_entity", content="Some content")
    assert page.page_type == "wiki_entity"
    assert page.tags == []
    assert page.sources == []


def test_wiki_page_to_markdown():
    page = WikiPage(
        title="Dijkstra",
        page_type="wiki_entity",
        content="Shortest path algorithm.",
        tags=["algorithm", "graph"],
        sources=["course/graph/Dijkstra.md"],
        source_hash="abc123",
    )
    md = page.to_markdown()
    assert "---" in md
    assert "type: wiki_entity" in md
    assert "generated_by: bobodan" in md
    assert "title: Dijkstra" in md
    assert "# Dijkstra" in md
    assert "Shortest path algorithm." in md
    assert "abc123" in md


def test_wiki_page_types_valid():
    assert PAGE_TYPES == {"wiki_entity", "wiki_concept", "wiki_source"}


# --- CompileResult ---

def test_compile_result_defaults():
    result = CompileResult()
    assert result.pages == []
    assert result.entities_count == 0
    assert result.errors == []
    assert result.skipped == []


# --- WikiConfig ---

def test_wiki_config_paths():
    config = WikiConfig()
    assert config.entities_path("/vault") == os.path.join("/vault", "wiki", "entities")
    assert config.concepts_path("/vault") == os.path.join("/vault", "wiki", "concepts")
    assert config.index_path("/vault") == os.path.join("/vault", "wiki", "index.md")
    assert config.log_path("/vault") == os.path.join("/vault", "wiki", "log.md")
    assert config.registry_path("/vault") == os.path.join("/vault", "wiki", "source_registry.json")


# --- State persistence ---

def test_save_and_load_wiki_state(tmp_path):
    state = {"sources": {"/path/to/file.md": "abc123"}, "last_compile": "2026-05-20"}
    save_wiki_state(str(tmp_path), state)
    loaded = load_wiki_state(str(tmp_path))
    assert loaded["sources"]["/path/to/file.md"] == "abc123"
    assert loaded["last_compile"] == "2026-05-20"


def test_load_wiki_state_missing(tmp_path):
    state = load_wiki_state(str(tmp_path))
    assert state == {}


# --- WikiIndexer ---

def test_indexer_update_index(tmp_path):
    indexer = WikiIndexer(str(tmp_path))
    pages = [
        WikiPage(title="Dijkstra", page_type="wiki_entity", content="algo", tags=["graph"]),
        WikiPage(title="Greedy", page_type="wiki_concept", content="strategy", tags=["algorithm"]),
    ]
    indexer.update_index(pages)

    index_path = os.path.join(str(tmp_path), "wiki", "index.md")
    assert os.path.exists(index_path)
    with open(index_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "Dijkstra" in content
    assert "Greedy" in content
    assert "实体" in content
    assert "概念" in content


def test_indexer_append_log(tmp_path):
    indexer = WikiIndexer(str(tmp_path))
    result = CompileResult(entities_count=2, concepts_count=1, sources_count=1)
    indexer.append_log("ingest", "test.md", result)

    log_path = os.path.join(str(tmp_path), "wiki", "log.md")
    assert os.path.exists(log_path)
    with open(log_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "ingest" in content
    assert "test.md" in content


def test_indexer_read_empty(tmp_path):
    indexer = WikiIndexer(str(tmp_path))
    assert indexer.read_index() == {}
    assert indexer.read_log() == []


# --- WikiLinter ---

def test_linter_empty_wiki(tmp_path):
    linter = WikiLinter(str(tmp_path))
    result = linter.lint()
    assert result.total_pages == 0
    assert result.errors  # should report missing wiki dir


def test_linter_healthy_wiki(tmp_path):
    # Two pages that link to each other — no orphans, no broken links
    ent_dir = os.path.join(str(tmp_path), "wiki", "entities")
    con_dir = os.path.join(str(tmp_path), "wiki", "concepts")
    os.makedirs(ent_dir)
    os.makedirs(con_dir)
    with open(os.path.join(ent_dir, "Test.md"), "w", encoding="utf-8") as f:
        f.write("---\ntitle: Test\ntype: wiki_entity\ngenerated_by: bobodan\n---\n\n# Test\n\nSee [[ConceptA]].\n")
    with open(os.path.join(con_dir, "ConceptA.md"), "w", encoding="utf-8") as f:
        f.write("---\ntitle: ConceptA\ntype: wiki_concept\ngenerated_by: bobodan\n---\n\n# ConceptA\n\nSee [[Test]].\n")

    linter = WikiLinter(str(tmp_path))
    result = linter.lint()
    assert result.total_pages == 2
    assert result.healthy


def test_linter_broken_links(tmp_path):
    wiki_dir = os.path.join(str(tmp_path), "wiki", "entities")
    os.makedirs(wiki_dir)
    with open(os.path.join(wiki_dir, "Test.md"), "w", encoding="utf-8") as f:
        f.write("---\ntitle: Test\ntype: wiki_entity\ngenerated_by: bobodan\n---\n\n# Test\n\nSee [[NonExistent]] for details.\n")

    linter = WikiLinter(str(tmp_path))
    result = linter.lint()
    assert len(result.broken_links) == 1
    assert result.broken_links[0]["target"] == "NonExistent"
    assert "NonExistent" in result.missing_pages
    assert not result.healthy


def test_linter_orphan_page(tmp_path):
    wiki_dir = os.path.join(str(tmp_path), "wiki", "entities")
    os.makedirs(wiki_dir)
    # Page with no inbound links
    with open(os.path.join(wiki_dir, "Orphan.md"), "w", encoding="utf-8") as f:
        f.write("---\ntitle: Orphan\ntype: wiki_entity\ngenerated_by: bobodan\n---\n\n# Orphan\n\nNo one links here.\n")

    linter = WikiLinter(str(tmp_path))
    result = linter.lint()
    assert "Orphan" in result.orphan_pages


def test_linter_format_result(tmp_path):
    linter = WikiLinter(str(tmp_path))
    result = LintResult(total_pages=5, orphan_pages=["A"], broken_links=[{"source": "x", "target": "y"}])
    summary = linter.format_result(result)
    assert "5" in summary
    assert "A" in summary


# --- Compiler ---

def test_compiler_compile_source_no_llm(tmp_path, monkeypatch):
    """Test compile_source without LLM tracks source but generates no pages."""
    from wiki.compiler import WikiCompiler

    src = tmp_path / "test.md"
    src.write_text("# Test\n\nSome content about algorithms.", encoding="utf-8")

    compiler = WikiCompiler(str(tmp_path), str(tmp_path / "vault"), llm_provider=None)
    monkeypatch.setattr(compiler, "_get_llm", lambda: None)

    result = compiler.compile_source(str(src))
    assert result.sources_count == 1
    assert len(result.pages) == 0  # no LLM = no pages, just registry tracking


def test_compiler_incremental_skip(tmp_path, monkeypatch):
    """Test that unchanged sources are skipped."""
    from wiki.compiler import WikiCompiler

    src = tmp_path / "test.md"
    src.write_text("# Test\n\nContent.", encoding="utf-8")

    vault = tmp_path / "vault"
    compiler = WikiCompiler(str(tmp_path), str(vault), llm_provider=None)
    monkeypatch.setattr(compiler, "_get_llm", lambda: None)

    # First compile
    result1 = compiler.compile_source(str(src))
    assert result1.sources_count == 1

    # Save state manually
    from wiki.schema import save_wiki_state
    from wiki.compiler import _content_hash
    state = {"sources": {str(src): _content_hash(src.read_text(encoding="utf-8"))}}
    save_wiki_state(str(vault), state)

    # Second compile — should skip
    result2 = compiler.compile_source(str(src))
    assert str(src) in result2.skipped
    assert result2.sources_count == 0


def test_compiler_force_recompile(tmp_path, monkeypatch):
    """Test force=True bypasses incremental check."""
    from wiki.compiler import WikiCompiler

    src = tmp_path / "test.md"
    src.write_text("# Test\n\nContent.", encoding="utf-8")

    vault = tmp_path / "vault"
    compiler = WikiCompiler(str(tmp_path), str(vault), llm_provider=None)
    monkeypatch.setattr(compiler, "_get_llm", lambda: None)

    # First compile
    compiler.compile_source(str(src))

    # Save state with same hash
    from wiki.schema import save_wiki_state
    from wiki.compiler import _content_hash
    state = {"sources": {str(src): _content_hash(src.read_text(encoding="utf-8"))}}
    save_wiki_state(str(vault), state)

    # Force recompile
    result = compiler.compile_source(str(src), force=True)
    assert result.sources_count == 1
    assert str(src) not in result.skipped


def test_compiler_write_pages(tmp_path):
    """Test write_pages creates files in correct directories."""
    from wiki.compiler import WikiCompiler

    vault = tmp_path / "vault"
    compiler = WikiCompiler(str(tmp_path), str(vault))

    result = CompileResult(pages=[
        WikiPage(title="Algo", page_type="wiki_entity", content="An algorithm."),
        WikiPage(title="Greedy", page_type="wiki_concept", content="A strategy."),
    ])

    written = compiler.write_pages(result)
    assert len(written) == 2
    for path in written:
        assert os.path.exists(path)


def test_parse_llm_json():
    """Test JSON extraction from LLM response."""
    from wiki.compiler import _parse_llm_json

    # Direct JSON
    result = _parse_llm_json('{"entities": [], "concepts": []}')
    assert result is not None

    # With markdown fences
    result = _parse_llm_json('```json\n{"entities": []}\n```')
    assert result is not None

    # With extra text
    result = _parse_llm_json('Here is the result:\n{"entities": []}\nDone.')
    assert result is not None

    # Invalid
    result = _parse_llm_json('no json here')
    assert result is None


# --- REPL commands ---

def test_wiki_init_command(tmp_path, capsys):
    from cli.repl import REPL
    repl = REPL.__new__(REPL)
    repl.session = type("S", (), {"workspace_root": str(tmp_path), "cwd": str(tmp_path)})()

    vault = tmp_path / "vault"
    vault.mkdir()

    repl.handle_wiki_init([str(vault)])
    output = capsys.readouterr().out
    assert "初始化" in output or "initialized" in output.lower()


def test_wiki_init_command_no_args(tmp_path, capsys):
    from cli.repl import REPL
    repl = REPL.__new__(REPL)
    repl.session = type("S", (), {"workspace_root": str(tmp_path), "cwd": str(tmp_path)})()

    repl.handle_wiki_init([])
    output = capsys.readouterr().out
    assert "Usage" in output


def test_wiki_status_command_empty(tmp_path, capsys):
    from cli.repl import REPL
    repl = REPL.__new__(REPL)
    repl.session = type("S", (), {"workspace_root": str(tmp_path), "cwd": str(tmp_path)})()

    repl.handle_wiki_status([str(tmp_path)])
    output = capsys.readouterr().out
    assert "未初始化" in output or "not" in output.lower()
