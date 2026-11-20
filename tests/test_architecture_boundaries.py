from scripts.check_architecture import REPO_ROOT, find_violations


def test_current_repository_respects_declared_boundaries():
    violations = []
    for root in ("knowledge", "learning", "memory", "providers", "quiz", "rag", "web", "wiki"):
        for path in (REPO_ROOT / root).rglob("*.py"):
            violations.extend(find_violations(path, path.read_text(encoding="utf-8")))

    assert violations == []


def test_router_storage_import_is_rejected():
    path = REPO_ROOT / "web" / "backend" / "routers" / "example.py"

    violations = find_violations(path, "import sqlite3\n")

    assert len(violations) == 1
    assert "Routers must call a service" in violations[0]


def test_rag_learning_import_is_rejected():
    path = REPO_ROOT / "rag" / "example.py"

    violations = find_violations(path, "from learning.store import LearningStore\n")

    assert len(violations) == 1
    assert "RAG must not depend" in violations[0]


def test_agents_md_and_claude_md_stay_in_sync():
    """Git checkouts break NTFS hardlinks; guard against multi-agent instruction drift."""
    agents_text = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    claude_text = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert agents_text == claude_text, (
        "AGENTS.md and CLAUDE.md have diverged. Keep AGENTS.md as the single source "
        "and mirror identical content to CLAUDE.md."
    )
