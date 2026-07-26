"""Tests for maintained Wiki schema, workflow support, index, and lint."""

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
from wiki.reliability import WikiTaskStore


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
    assert PAGE_TYPES == {
        "wiki_entity", "wiki_concept", "wiki_source", "wiki_analysis", "wiki_question", "wiki_note",
    }


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


def test_linter_separates_duplicates_from_semantic_candidates(tmp_path):
    concepts = tmp_path / "wiki" / "concepts"
    concepts.mkdir(parents=True)
    (concepts / "RAG.md").write_text("---\ntitle: RAG\ntype: wiki_concept\n---\n\n# RAG", encoding="utf-8")
    (concepts / "rag-copy.md").write_text("---\ntitle: r a g\ntype: wiki_concept\n---\n\n# RAG", encoding="utf-8")
    (tmp_path / "wiki" / ".semantic-review.json").write_text(json.dumps({
        "issues": [{"type": "contradiction", "pages": ["RAG", "Retriever"], "reason": "Claims differ."}],
    }), encoding="utf-8")

    result = WikiLinter(str(tmp_path)).lint()

    assert result.duplicate_candidates[0]["canonical_title"] == "RAG"
    assert result.contradiction_candidates == ["RAG", "Retriever"]
    assert result.semantic_candidates[0]["reason"] == "Claims differ."


def test_semantic_review_persists_advisory_candidates(tmp_path):
    from providers.types import LLMResponse

    concepts = tmp_path / "wiki" / "concepts"
    concepts.mkdir(parents=True)
    (concepts / "RAG.md").write_text("---\ntitle: RAG\ntype: wiki_concept\n---\n\n# RAG\n\nClaim A.", encoding="utf-8")
    provider = type("Provider", (), {
        "complete": lambda self, messages: LLMResponse(content=json.dumps({
            "issues": [{"type": "stale", "pages": ["RAG"], "reason": "Needs a newer source."}],
        })),
    })()

    review = WikiLinter(str(tmp_path)).semantic_review(provider)

    assert review["issues"][0]["type"] == "stale"
    assert (tmp_path / "wiki" / ".semantic-review.json").is_file()
    assert WikiLinter(str(tmp_path)).lint().semantic_candidates == review["issues"]


def test_task_store_recovers_interrupted_process_tasks(tmp_path):
    store = WikiTaskStore(str(tmp_path))
    os.makedirs(os.path.dirname(store.path), exist_ok=True)
    with open(store.path, "w", encoding="utf-8") as handle:
        json.dump([{
            "task_id": "task-1",
            "operation": "apply",
            "status": "running",
            "runner_id": "previous-process",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }], handle)

    task = store.list()[0]

    assert task["status"] == "failed"
    assert task["retryable"] is True




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
