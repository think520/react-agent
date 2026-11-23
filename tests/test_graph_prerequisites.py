"""Tests for pure prerequisite graph traversal and topological ordering."""

from graph.prerequisites import find_prerequisites, topological_prerequisite_order


def _sample_graph():
    concepts = [
        {"concept_id": "c-lin", "name": "线性代数", "aliases": ["Linear Algebra"]},
        {"concept_id": "c-mat", "name": "矩阵乘法", "aliases": []},
        {"concept_id": "c-prob", "name": "概率论", "aliases": []},
        {"concept_id": "c-attn", "name": "注意力机制", "aliases": ["Attention"]},
        {"concept_id": "c-trans", "name": "Transformer", "aliases": []},
        {"concept_id": "c-unrelated", "name": "操作系统", "aliases": ["OS"]},
    ]
    relationships = [
        {"from_id": "c-lin", "to_id": "c-mat", "rel_type": "前置知识"},
        {"from_id": "c-mat", "to_id": "c-attn", "rel_type": "前置知识"},
        {"from_id": "c-prob", "to_id": "c-attn", "rel_type": "前置知识"},
        {"from_id": "c-attn", "to_id": "c-trans", "rel_type": "前置知识"},
        # Non-prerequisite relations must be ignored.
        {"from_id": "c-unrelated", "to_id": "c-trans", "rel_type": "对比"},
    ]
    return concepts, relationships


def test_find_prerequisites_two_hops_and_alias():
    concepts, rels = _sample_graph()

    direct_and_indirect = find_prerequisites("注意力机制", concepts, rels, max_depth=2)
    assert [(item["name"], item["depth"], item["via"]) for item in direct_and_indirect] == [
        ("概率论", 1, None),
        ("矩阵乘法", 1, None),
        ("线性代数", 2, "矩阵乘法"),
    ]

    via_alias = find_prerequisites("attention", concepts, rels, max_depth=1)
    assert [item["name"] for item in via_alias] == ["概率论", "矩阵乘法"]


def test_find_prerequisites_handles_cycles_safely():
    concepts = [
        {"concept_id": "c1", "name": "A", "aliases": []},
        {"concept_id": "c2", "name": "B", "aliases": []},
    ]
    rels = [
        {"from_id": "c1", "to_id": "c2", "rel_type": "前置知识"},
        {"from_id": "c2", "to_id": "c1", "rel_type": "前置知识"},
    ]
    found = find_prerequisites("B", concepts, rels, max_depth=3)
    assert [item["name"] for item in found] == ["A"]


def test_topological_prerequisite_order_diamond_and_scoping():
    concepts, rels = _sample_graph()
    rels = [
        *rels,
        {"from_id": "c-unrelated", "to_id": "c-extra", "rel_type": "前置知识"},
    ]
    concepts = [*concepts, {"concept_id": "c-extra", "name": "进程管理", "aliases": []}]

    result = topological_prerequisite_order(
        concepts,
        rels,
        scope_names=["复习 Transformer"],
    )
    order = result["ordered_concepts"]
    assert result["has_cycles"] is False
    assert result["cycle_concepts"] == []
    assert "操作系统" not in order
    assert "进程管理" not in order
    assert order.index("线性代数") < order.index("矩阵乘法") < order.index("注意力机制") < order.index("Transformer")
    assert order.index("概率论") < order.index("注意力机制")


def test_topological_prerequisite_order_reports_cycles_without_crashing():
    concepts = [
        {"concept_id": "c0", "name": "基础", "aliases": []},
        {"concept_id": "c1", "name": "循环A", "aliases": []},
        {"concept_id": "c2", "name": "循环B", "aliases": []},
    ]
    rels = [
        {"from_id": "c0", "to_id": "c1", "rel_type": "前置知识"},
        {"from_id": "c1", "to_id": "c2", "rel_type": "前置知识"},
        {"from_id": "c2", "to_id": "c1", "rel_type": "前置知识"},
    ]
    result = topological_prerequisite_order(concepts, rels)
    assert result["has_cycles"] is True
    assert result["cycle_concepts"] == ["循环A", "循环B"]
    assert result["ordered_concepts"][0] == "基础"
    assert set(result["ordered_concepts"]) == {"基础", "循环A", "循环B"}
