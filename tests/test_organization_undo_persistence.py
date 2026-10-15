"""⑤（E17）：一键撤销必须活过刷新与重启。

修前状态：`apply_organization` 把 moved 清单**只交给调用方**（HTTP 响应），服务端
不留痕。于是页面一刷新，前端 state 里的清单就没了 —— 文件已经进了「未归类」，
而 README/CLAUDE.md 承诺的「任何移动/重命名都只在用户确认后执行，且**永远可一键
撤销**」在界面上变成"刷新之后不可撤销"。

复现：执行整理 → **重新构造一个 KBService**（等价于刷新/重启进程）→ 不带清单调用
`undo_organization()`。修前：restored 为空，文件仍在文件夹里。
"""

import pytest

from service.kb_service import KBService
from service.library_service import LibraryService


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "library"
    LibraryService(str(tmp_path / "home")).initialize(str(root), name="Portable")
    return root


def _sync(library, monkeypatch):
    from unittest.mock import MagicMock

    from obsidian.sync import sync_sources

    monkeypatch.setattr("rag.qdrant_store.QdrantStore", MagicMock())
    monkeypatch.setattr(
        "rag.embedding_service.EmbeddingService",
        lambda *a, **k: type("Embedding", (), {"is_available": lambda self: False})(),
    )
    return sync_sources(
        workspace=str(library), vault_path=str(library), course_dir=str(library), mode="full"
    )


def _prepare(library, monkeypatch):
    (library / "散落的一课.md").write_text("# 散落的一课\n\n内容足够长，能切出一段。", encoding="utf-8")
    _sync(library, monkeypatch)
    return KBService(str(library))


def test_undo_survives_a_restart(library, monkeypatch):
    service = _prepare(library, monkeypatch)
    applied = service.apply_organization(["散落的一课.md"], "未归类")
    assert applied["ok"], applied
    assert (library / "未归类" / "散落的一课.md").is_file()

    # 刷新 / 重启：新的服务实例，调用方手里**没有任何清单**。
    restarted = KBService(str(library))
    state = restarted.organization_state()
    assert state["ok"], state
    assert state["pending_undo"] is not None, "整理过之后，服务端必须记得这一步"
    assert [move["to"] for move in state["pending_undo"]["moves"]] == ["未归类/散落的一课.md"]

    undone = restarted.undo_organization()
    assert undone["ok"], undone
    assert undone["restored"] == ["散落的一课.md"]
    assert (library / "散落的一课.md").is_file(), "撤销必须放回原位"
    assert not (library / "未归类" / "散落的一课.md").exists()


def test_nothing_pending_is_reported_not_guessed(library):
    service = KBService(str(library))

    state = service.organization_state()
    assert state["ok"], state
    assert state["pending_undo"] is None

    result = service.undo_organization()
    assert result["ok"], result
    assert result["restored"] == [], "没有可撤销的东西时，不能假装撤销了"


def test_undoing_with_an_explicit_list_also_clears_the_record(library, monkeypatch):
    service = _prepare(library, monkeypatch)
    applied = service.apply_organization(["散落的一课.md"], "未归类")
    assert applied["ok"], applied

    undone = service.undo_organization(applied["moved"])

    assert undone["ok"], undone
    assert undone["restored"] == ["散落的一课.md"]
    assert service.organization_state()["pending_undo"] is None, "撤销过就不该再提示可撤销"

def test_undo_removes_the_folder_that_apply_itself_created(library):
    """真实资料库上发现的缺口：整理建了「未归类」，撤销把文件放回去了，却把空文件夹留下。"""
    (library / "散落的一课.md").write_text("# 散落的一课\n\n内容足够长，能切出一段。", encoding="utf-8")
    service = KBService(str(library))
    assert not (library / "未归类").exists()

    applied = service.apply_organization(["散落的一课.md"], "未归类")
    assert applied["ok"], applied
    assert (library / "未归类").is_dir()

    undone = service.undo_organization()

    assert undone["ok"], undone
    assert (library / "散落的一课.md").is_file()
    assert not (library / "未归类").exists(), "整理自己建的空文件夹不该留在用户的资料库里"


def test_undo_never_deletes_a_folder_the_user_already_had(library):
    (library / "已存在").mkdir()
    (library / "已存在" / "别动我.md").write_text("# 别动我\n\n无关资料。", encoding="utf-8")
    (library / "散落的一课.md").write_text("# 散落的一课\n\n内容足够长，能切出一段。", encoding="utf-8")
    service = KBService(str(library))

    applied = service.apply_organization(["散落的一课.md"], "已存在")
    assert applied["ok"], applied
    undone = service.undo_organization()

    assert undone["ok"], undone
    assert (library / "已存在").is_dir(), "用户自己的文件夹绝不能被撤销顺手删掉"
    assert (library / "已存在" / "别动我.md").is_file()
    assert (library / "散落的一课.md").is_file()

def test_undo_resolves_the_current_identity_instead_of_the_recorded_one(library, monkeypatch):
    """真机（2026-09-24）发现的缺口：移动之后索引会重新分配身份。

    真实资料库上执行整理后，台账里记的 `document_id` 已经查不到了，于是
    `undo_organization()` 直接 404（`document_not_found`）——文件躺在「未归类」里
    撤不回来。撤销必须**以"文件现在在哪"重新解析身份**，记下的 id 只是台账。
    """
    from rag.sqlite_store import KBSQLiteStore

    service = _prepare(library, monkeypatch)
    applied = service.apply_organization(["散落的一课.md"], "未归类")
    assert applied["ok"], applied
    recorded_id = applied["moved"][0]["document_id"]

    # 模拟索引在移动后重新分配了身份：台账里那个 id 从此查不到（真机就是这个状态）。
    store = KBSQLiteStore(str(library))
    store.init_db()
    try:
        conn = store._get_conn()
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("UPDATE documents SET id = ? WHERE id = ?", ("reindexed0000000", recorded_id))
        conn.commit()
    finally:
        store.close()
    assert KBSQLiteStore(str(library)).get_document(recorded_id) is None

    undone = service.undo_organization()

    assert undone["ok"], undone
    assert undone["restored"] == ["散落的一课.md"]
    assert (library / "散落的一课.md").is_file()
    assert not (library / "未归类").exists()
