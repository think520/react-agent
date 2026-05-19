from graph.local_store import LocalGraphStore
from obsidian.vault import scan_vault


def test_local_graph_from_obsidian_links_and_tags(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Dijkstra.md").write_text(
        """---
course: 数据结构
chapter: 图
aliases: [单源最短路]
---

# Dijkstra 算法

[[图]] [[优先队列]] #algorithm
""",
        encoding="utf-8",
    )

    notes = scan_vault(str(vault))
    store = LocalGraphStore(str(tmp_path / "graph_store.json"))
    relationship_count = store.replace_from_notes(notes)

    related = store.query("Dijkstra 算法", intent="related")
    tags = store.query("单源最短路", intent="tags")

    assert relationship_count >= 4
    assert any(node["name"] == "图" for node in related["nodes"])
    assert any(node["name"] == "algorithm" for node in tags["nodes"])
    assert related["source"] == "local_json"
