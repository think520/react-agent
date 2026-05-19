from obsidian.parser import parse_markdown_note


def test_parse_frontmatter_links_tags_and_aliases():
    content = """---
course: 数据结构
chapter: 图
aliases:
  - 单源最短路
tags: [algorithm]
---

# Dijkstra 算法

相关知识：[[图|Graph]]、[[优先队列]] #shortest-path
"""

    note = parse_markdown_note(content, "算法/Dijkstra.md")

    assert note.title == "Dijkstra 算法"
    assert note.course == "数据结构"
    assert note.chapter == "图"
    assert "algorithm" in note.tags
    assert "shortest-path" in note.tags
    assert note.links[0].target == "图"
    assert note.links[0].alias == "Graph"
    assert "单源最短路" in note.aliases
    assert "Graph" in note.aliases
