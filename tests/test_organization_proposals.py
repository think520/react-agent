"""⑤（E17）：整理建议 —— 只提议，不动文件。

设计：docs/LIBRARY_TREE_DESIGN.md §3.5 决定 22 —— AI 整理的形状是
「提议 → 预览 → 用户确认 → 执行 → 一键撤销」。这一块只做**前半**：
给出可复核的建议清单，**一份文件都不动**（可执行的那一半与撤销留在下一步）。
"""

import os

import pytest

from service.kb_service import KBService
from service.library_service import LibraryService


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "library"
    LibraryService(str(tmp_path / "home")).initialize(str(root), name="Portable")
    return root


def test_organization_proposals_point_at_loose_files_without_moving_anything(library):
    (library / "课程包").mkdir()
    (library / "课程包" / "第一课.md").write_text("# 第一课", encoding="utf-8")
    (library / "散落的一课.md").write_text("# 散落的一课", encoding="utf-8")
    (library / "散落的二课.md").write_text("# 散落的二课", encoding="utf-8")
    (library / "封面.png").write_bytes(b"png")

    before = sorted(str(path.relative_to(library)) for path in library.rglob("*"))

    result = KBService(str(library)).propose_organization()

    assert result["ok"], result
    proposals = result["proposals"]
    assert proposals, "至少要指出库根散落的资料"

    kinds = {item["kind"] for item in proposals}
    assert "loose_materials" in kinds, proposals
    loose = next(item for item in proposals if item["kind"] == "loose_materials")
    assert sorted(loose["items"]) == ["散落的一课.md", "散落的二课.md"]
    assert loose["requires_confirmation"] is True
    assert loose["reason"]

    # 只提议，不动文件（含非资料文件也不碰）
    after = sorted(str(path.relative_to(library)) for path in library.rglob("*"))
    assert before == after


def test_organization_proposals_are_empty_for_a_tidy_library(library):
    (library / "课程包").mkdir()
    (library / "课程包" / "第一课.md").write_text("# 第一课", encoding="utf-8")

    result = KBService(str(library)).propose_organization()
    assert result["ok"]
    assert result["proposals"] == []
