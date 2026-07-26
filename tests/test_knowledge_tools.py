from tools.concept_map import concept_map_status
from tools.obsidian_tool import obsidian_sync
from tools.rag_search import rag_search


def test_obsidian_sync_rag_search_without_auto_approving_graph(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Dijkstra.md").write_text(
        """---
course: 数据结构
chapter: 图
---

# Dijkstra 算法

Dijkstra solves shortest path problems with [[图]] and [[优先队列]]. #algorithm
""",
        encoding="utf-8",
    )

    sync_result = obsidian_sync("vault", cwd=str(tmp_path), workspace=str(tmp_path))
    search_result = rag_search("shortest path", workspace=str(tmp_path))
    graph_result = concept_map_status(workspace=str(tmp_path))

    assert sync_result.ok
    assert sync_result.data["graph_backend"] == "concept_sqlite"
    assert sync_result.data["chunk_count"] >= 1
    assert search_result.ok
    assert search_result.data["results"][0]["source"] == "obsidian/Dijkstra.md"
    assert search_result.data["retrieval_mode"] == "fts_only"
    assert search_result.data["semantic_available"] is False
    assert graph_result.ok
    assert graph_result.data["has_reviewed_graph"] is False


def test_obsidian_sync_denies_outside_workspace(tmp_path):
    outside = tmp_path.parent
    result = obsidian_sync(str(outside), cwd=str(tmp_path), workspace=str(tmp_path))

    assert not result.ok
    assert "denied" in result.content.lower()
