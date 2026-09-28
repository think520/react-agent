"""R09（F02/F03/F07）：整理的**文件安全**链路 —— 审查失败探针转正。

来源：`docs/reviews/2026-09-28-remediation-code-review.md` §2 与
`docs/reviews/evidence/2026-09-28/backend-probe-source.py.txt`。审查确认三件事没做到：

- **F02**：已索引文件在移动或迁移索引时**抛异常**，异常直接逃出 `apply_organization`，
  已经移动的文件没有台账；而且"先写计划再动手"根本没做（第一次移动前台账是空的）。
- **F03**：撤销**未索引**文件时直接 `shutil.move` 回原路径，会**覆盖用户后来新建的同名文件**。
- **F07**：部分失败的部分结果（moved / batch_id）在 HTTP 边界被丢掉，界面拿不到恢复入口。

这五条就是当时失败的探针，现在作为回归测试留下：修好之前它们必须是红的。
"""

import sqlite3
import shutil

import pytest

from rag.sqlite_store import KBSQLiteStore
from service.kb_service import KBService
from service.library_service import LibraryService
from tests.test_organization_apply import _sync
from web.backend.errors import APIError, unwrap_service_result


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "library"
    LibraryService(str(tmp_path / "home")).initialize(str(root), name="Portable")
    for name in ("first.md", "second.md"):
        (root / name).write_text("A lesson with enough text for indexing. " * 20, encoding="utf-8")
    return root


def test_indexed_move_exception_retains_recovery_batch(library, monkeypatch):
    """F02-1：第二次物理移动抛 PermissionError，第一份已经搬走了 —— 必须有台账。"""
    _sync(library, monkeypatch)
    service = KBService(str(library))
    original = shutil.move
    calls = 0

    def fail_second(source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise PermissionError("review injected: file is locked")
        return original(source, target)

    monkeypatch.setattr("service.kb_service.shutil.move", fail_second)

    result = service.apply_organization(["first.md", "second.md"], "Lessons")

    assert (library / "Lessons/first.md").is_file()
    assert result.get("ok") is False, result
    state = service.organization_state()
    assert state["pending_undo"] is not None, "第一份已经搬走，却没有可撤销的台账"
    assert result.get("batch_id") == state["pending_undo"]["batch_id"]


def test_index_failure_after_physical_move_retains_recovery(library, monkeypatch):
    """F02-2：文件已经搬过去、索引迁移才失败 —— 这一份仍然必须能撤销。"""
    _sync(library, monkeypatch)
    service = KBService(str(library))

    def fail_index(*args, **kwargs):
        raise sqlite3.OperationalError("review injected: database is locked")

    monkeypatch.setattr(KBSQLiteStore, "remap_chunk_ids", fail_index)

    result = service.apply_organization(["first.md"], "Lessons")

    assert (library / "Lessons/first.md").is_file()
    assert not (library / "first.md").exists()
    assert result.get("ok") is False, result
    state = service.organization_state()
    assert state["pending_undo"] is not None, "物理移动已完成但索引更新失败，没有留下恢复台账"
    assert result["moved"] and result["moved"][0]["to"] == "Lessons/first.md"
    assert result["failed"], "索引迁移失败必须如实报出来，不能假装整批成功"


def test_recovery_plan_exists_before_the_first_move(library, monkeypatch):
    """F02-3：**先写计划再动手** —— 进程在第一次移动时被杀，重启后仍要看得出打算搬什么。"""
    service = KBService(str(library))

    def stop_process(source, target):
        assert service.organization_state()["pending_undo"] is not None,             "第一次文件系统改动之前就必须有持久化的操作计划"
        raise SystemExit("review simulated process exit")

    monkeypatch.setattr("service.kb_service.shutil.move", stop_process)

    with pytest.raises(SystemExit):
        service.apply_organization(["first.md"], "Lessons")

    plan = KBService(str(library)).organization_state()["pending_undo"]
    assert plan is not None, "进程退出后重启，计划必须还在"
    assert [move["from"] for move in plan["moves"]] == ["first.md"]
    assert [move["to"] for move in plan["moves"]] == ["Lessons/first.md"]


def test_partial_batch_survives_http_error_mapping(library, monkeypatch):
    """F07：部分失败的部分结果必须穿过 HTTP 边界（界面靠它给恢复入口）。"""
    original = shutil.move
    calls = 0

    def fail_second(source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("review injected failure")
        return original(source, target)

    monkeypatch.setattr("service.kb_service.shutil.move", fail_second)

    result = KBService(str(library)).apply_organization(["first.md", "second.md"], "Lessons")

    assert result["batch_id"] and len(result["moved"]) == 1, result
    assert result["failed"], result
    with pytest.raises(APIError) as caught:
        unwrap_service_result(result, code="organization_failed")
    assert caught.value.details, "HTTP 错误把恢复用的结构化信息丢掉了"
    assert caught.value.details.get("batch_id") == result["batch_id"]
    assert caught.value.details.get("moved")


def test_undo_does_not_overwrite_a_new_file_at_the_original_path(library):
    """F03：撤销**不许**覆盖用户后来新建的同名文件 —— 跳过并如实报告。"""
    service = KBService(str(library))
    applied = service.apply_organization(["first.md"], "Lessons")
    assert applied["ok"], applied

    (library / "first.md").write_text("New user file created after organizing", encoding="utf-8")

    undone = service.undo_organization(batch_id=applied["batch_id"])

    assert (library / "first.md").read_text(encoding="utf-8") == "New user file created after organizing",         "撤销把用户新建的文件覆盖掉了"
    assert undone["ok"], undone
    assert undone["restored"] == []
    assert undone["skipped"] and undone["skipped"][0]["reason"] == "target_exists", undone
    # 冲突没解决之前，台账必须留着（否则用户再也撤不回来）
    assert service.organization_state()["pending_undo"] is not None

def test_restart_can_undo_what_a_crash_left_behind(library, monkeypatch):
    """F02：搬到一半被杀 —— **重启后的实例**必须还能把已经搬走的收回来。

    这里不是"强杀进程"的实验，而是用 SystemExit 模拟工具中途退出，再用一个全新的
    KBService（等价于重开应用）去读磁盘上的台账并撤销。
    """
    original = shutil.move
    calls = 0

    def die_during_second(source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise SystemExit("review simulated crash after the first move")
        return original(source, target)

    monkeypatch.setattr("service.kb_service.shutil.move", die_during_second)

    with pytest.raises(SystemExit):
        KBService(str(library)).apply_organization(["first.md", "second.md"], "Lessons")

    assert (library / "Lessons/first.md").is_file(), "第一份应当已经搬走"

    restarted = KBService(str(library))
    assert restarted.organization_state()["pending_undo"] is not None, "重启后台账必须还在"

    undone = restarted.undo_organization()

    assert undone["ok"], undone
    assert undone["restored"] == ["first.md"]
    assert (library / "first.md").is_file()
    assert not (library / "Lessons/first.md").exists()
    assert (library / "second.md").is_file(), "没搬成的那一份必须原样留在原地"

def _rename_document_id(service: KBService, document_id: str, new_id: str) -> None:
    """把索引里的身份换掉，模拟"索引重建"（真机上就是这么发生的）。"""
    store = KBSQLiteStore(service.workspace)
    store.init_db()
    try:
        conn = store._get_conn()
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("UPDATE documents SET id = ? WHERE id = ?", (new_id, document_id))
        conn.commit()
    finally:
        store.close()


def test_apply_retries_with_the_current_identity_when_the_index_rebuilt_it(library, monkeypatch):
    """真机（2026-09-28）：计划到执行之间索引重建了身份，计划里的 id 已查不到 ——
    必须按**现在的路径**重新解析并重试，而不是把一份好好的资料判成"搬不动"。
    """
    _sync(library, monkeypatch)
    service = KBService(str(library))
    renamed = {"done": False}
    original_move = KBService.move_document

    def flaky_move(self, document_id, target, config=None):
        if not renamed["done"]:
            renamed["done"] = True
            _rename_document_id(self, str(document_id), "reindexed0000001")
            return {"ok": False, "code": "document_not_found", "error": f"Document not found: {document_id}"}
        return original_move(self, document_id, target, config=config)

    monkeypatch.setattr(KBService, "move_document", flaky_move)

    result = service.apply_organization(["first.md"], "Lessons")

    assert result["ok"], result
    assert (library / "Lessons/first.md").is_file()
    sources = {row["source"] for row in KBSQLiteStore(str(library)).list_documents()}
    assert any(source.endswith("Lessons/first.md") for source in sources), \
        "重试必须走索引迁移（身份保留），而不是退化成一个裸搬文件"


def test_a_batch_with_nothing_left_to_undo_is_not_reported_pending(library, monkeypatch):
    """真机（2026-09-28）：第一项撤销成功、第二项其实**没搬成** ——
    台账不该继续提示"可撤销"，那一项也不该被误报成"原位被占用"。
    """
    original = shutil.move
    calls = 0

    def fail_second(source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("review injected failure")
        return original(source, target)

    monkeypatch.setattr("service.kb_service.shutil.move", fail_second)

    service = KBService(str(library))
    applied = service.apply_organization(["first.md", "second.md"], "Lessons")
    assert applied["ok"] is False and len(applied["moved"]) == 1, applied
    assert service.organization_state()["pending_undo"] is not None, "还有一份可以撤"

    undone = service.undo_organization(batch_id=applied["batch_id"])

    assert undone["restored"] == ["first.md"], undone
    assert undone["skipped"] == [], "没搬成的那一项不该被报成'原位被占用'"
    assert service.organization_state()["pending_undo"] is None, "已经没有可撤销的东西了"
