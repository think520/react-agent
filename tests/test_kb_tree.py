"""② 只读文件夹树（E17 ②）的复现测试。

设计：`docs/LIBRARY_TREE_DESIGN.md` §3.1 / §3.3。
- 树建在**真实文件系统**上：文件夹就是文件夹，资料文件按扩展名白名单出现；
- 隐藏 Bobodan 自己的内部结构（`.bobodan/`、`wiki/`、点目录）与标记文件；
- 仓库元文件不算资料，但要在「另有 N 个文件已忽略」里可核对；
- 每份资料文件带索引徽章（document_id / 提取状态），未索引的也要看得见（不然
  用户会以为东西没进去）；
- **绝不外泄绝对路径**（沿用 raw/asset 的既有约定）。
"""

import json
import os

import pytest

from service.kb_service import KBService
from service.library_service import LibraryService


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "library"
    LibraryService(str(tmp_path / "home")).initialize(str(root), name="Portable")
    return root


def _seed_files(root):
    (root / "ai-agents-from-zero" / "assets").mkdir(parents=True, exist_ok=True)
    (root / "ai-agents-from-zero" / "1-1-学习.md").write_text("# 学习\n\n内容", encoding="utf-8")
    (root / "ai-agents-from-zero" / "README.md").write_text("# 仓库说明", encoding="utf-8")
    (root / "ai-agents-from-zero" / "assets" / "logo.png").write_bytes(b"\x89PNG")
    (root / "ai-agents-from-zero" / "assets" / "deep").mkdir(exist_ok=True)
    (root / "ai-agents-from-zero" / "assets" / "deep" / "script.py").write_text("print(1)", encoding="utf-8")
    (root / "raw" / "inbox" / "paper.pdf").write_bytes(b"%PDF-1.4 fake")
    (root / "wiki" / "concepts").mkdir(parents=True, exist_ok=True)
    (root / "wiki" / "concepts" / "RAG.md").write_text("# RAG", encoding="utf-8")
    (root / "正则表达式.md").write_text("# 正则\n\n内容", encoding="utf-8")


def _sync(root, monkeypatch):
    from unittest.mock import MagicMock

    from obsidian.sync import sync_sources

    monkeypatch.setattr("rag.qdrant_store.QdrantStore", MagicMock())
    monkeypatch.setattr(
        "rag.embedding_service.EmbeddingService",
        lambda *a, **k: type("Embedding", (), {"is_available": lambda self: False})(),
    )
    return sync_sources(
        workspace=str(root),
        vault_path=str(root),
        course_dir=str(root),
        mode="full",
    )


def _folder(node, name):
    for child in node["children"]:
        if child["name"] == name:
            return child
    raise AssertionError(f"folder {name!r} not in {[c['name'] for c in node['children']]}")


def test_the_tree_shows_real_folders_and_hides_bobodans_own_structure(library):
    _seed_files(library)
    result = KBService(str(library)).tree()
    assert result["ok"]

    root = result["tree"]
    names = [child["name"] for child in root["children"]]
    assert "ai-agents-from-zero" in names
    assert "raw" in names
    # 内部结构与标记文件不出现在树里
    assert "wiki" not in names
    assert ".bobodan" not in names
    assert "BOBODAN_LIBRARY.yaml" not in names

    files = [item["name"] for item in root["files"]]
    assert "正则表达式.md" in files
    assert "README.md" not in files

    # 文件夹优先、同级按名称（casefold）
    kinds = [child["type"] for child in root["children"]]
    assert kinds == sorted(kinds, key=lambda kind: 0 if kind == "folder" else 1)


def test_ignored_files_are_counted_and_explained(library):
    """计数是**含子目录**的合计（文件夹行的徽章），明细只列本层。"""
    _seed_files(library)
    result = KBService(str(library)).tree()
    pack = _folder(result["tree"], "ai-agents-from-zero")

    assert pack["material_count"] == 1, pack
    # README.md（本层）+ assets/logo.png + assets/deep/script.py
    assert pack["ignored_count"] == 3, pack
    assert [item["name"] for item in pack["ignored_here"]] == ["README.md"]
    assert pack["ignored_here"][0]["reason"] == "repo_metadata"

    assets = next(child for child in pack["children"] if child["name"] == "assets")
    assert assets["material_count"] == 0
    assert assets["ignored_count"] == 2
    assert [item["name"] for item in assets["ignored_here"]] == ["logo.png"]
    assert assets["ignored_here"][0]["reason"] == "unsupported_type"

    deep = next(child for child in assets["children"] if child["name"] == "deep")
    assert deep["ignored_count"] == 1
    assert [item["name"] for item in deep["ignored_here"]] == ["script.py"]


def test_material_files_carry_their_index_badges(library, monkeypatch):
    _seed_files(library)
    _sync(library, monkeypatch)
    (library / "ai-agents-from-zero" / "还没同步.md").write_text("# 新的", encoding="utf-8")

    result = KBService(str(library)).tree()
    pack = _folder(result["tree"], "ai-agents-from-zero")
    indexed = next(item for item in pack["files"] if item["name"] == "1-1-学习.md")
    assert indexed["indexed"] is True
    assert indexed["document_id"]
    assert indexed["extraction_status"] in {"complete", "partial", "empty", "error"}

    pending = next(item for item in pack["files"] if item["name"] == "还没同步.md")
    assert pending["indexed"] is False, "未索引的资料也要看得见，否则用户以为没进去"


def test_the_tree_never_leaks_absolute_paths(library):
    _seed_files(library)
    result = KBService(str(library)).tree()
    blob = json.dumps(result, ensure_ascii=False)
    assert str(library) not in blob
    assert "F:\\" not in blob and "C:\\" not in blob

    assert result["tree"]["path"] == ""
    pack = _folder(result["tree"], "ai-agents-from-zero")
    assert pack["path"] == "ai-agents-from-zero"


def test_document_list_exposes_the_real_relative_path(library, monkeypatch):
    """① 的最后一项：来源标签在**显示层**用真实相对路径。

    `source` 是索引身份（`course-2/…`、`course/inbox/…`），由扫描根前缀决定，
    对用户毫无意义；显示要用真实相对路径（`raw/inbox/paper.pdf`）。
    """
    _seed_files(library)
    _sync(library, monkeypatch)
    documents = KBService(str(library)).list_documents(collection="material")["documents"]
    pdf = next(item for item in documents if item["source"].endswith("paper.pdf"))
    assert pdf["relative_path"] == "raw/inbox/paper.pdf"

    # 库根的 markdown 由 vault 扫描收进来，title 是 H1，不是文件名——所以按路径断言
    paths = {item["relative_path"] for item in documents}
    assert "正则表达式.md" in paths
    assert all(not item["relative_path"].startswith("/") for item in documents)
    assert all(":" not in item["relative_path"] for item in documents), "绝不能出现盘符"
