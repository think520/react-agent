"""E8（W1）：导入流程的**取消**。

路线图 W1 的 E8 = 导入流程（进度 + 失败清单 + 取消 + 拖拽热区）。这里先钉住服务层的
协作式取消：复用 A4 批次三的 `core/cancellation.py::CancelToken`（设计见
`docs/CANCELLATION_DESIGN.md`：Python 不能杀线程，语义是"不再等它 + 在检查点通知它停"）。

**诚实边界**：取消不会打断一份文件正在进行的解析，它在**文件边界**生效 —— 已经收进来的
文件保持收进来，剩下的如实报成 cancelled，不假装"什么都没发生"。
"""

from pathlib import Path

import pytest

from core.cancellation import CancelToken
from service.kb_service import KBService
from service.library_service import LibraryService
from tests.test_organization_apply import _sync


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "library"
    LibraryService(str(tmp_path / "home")).initialize(str(root), name="Portable")
    (root / "first.md").write_text("# first\n\n" + "A lesson with enough text for indexing. " * 20, encoding="utf-8")
    return root


class _FlipAfter(CancelToken):
    """第 N 次检查之后才开始说"已取消" —— 让"中途取消"可确定地复现。"""

    def __init__(self, after: int) -> None:
        super().__init__()
        self.checks = 0
        self.after = after

    def is_cancelled(self) -> bool:  # type: ignore[override]
        self.checks += 1
        return self.checks > self.after


def _files(count: int) -> list:
    return [(f"lesson-{index}.md", ("A lesson with enough text for indexing. " * 20).encode("utf-8"))
            for index in range(count)]


def test_an_already_cancelled_import_writes_nothing(library, monkeypatch):
    _sync(library, monkeypatch)
    service = KBService(str(library))
    token = CancelToken()
    token.cancel("user cancelled")

    result = service.import_files(_files(3), cancel_token=token)

    assert result["cancelled"] is True, result
    assert result["imported"] == [], "取消之后不该再收文件"
    assert [item["status"] for item in result["results"]] == ["cancelled"] * 3, result["results"]
    inbox = Path(service.managed_sources_dir)
    assert [path.name for path in inbox.iterdir()] == [], "取消的导入不该在 inbox 里留下半份文件"


def test_cancelling_midway_keeps_what_was_accepted_and_reports_the_rest(library, monkeypatch):
    _sync(library, monkeypatch)
    service = KBService(str(library))
    token = _FlipAfter(after=1)

    result = service.import_files(_files(3), cancel_token=token)

    assert result["cancelled"] is True, result
    assert result["imported"] == ["lesson-0.md"], result["imported"]
    assert [item["status"] for item in result["results"]] == ["imported", "cancelled", "cancelled"], result["results"]
    assert (Path(service.managed_sources_dir) / "lesson-0.md").is_file()
    assert not (Path(service.managed_sources_dir) / "lesson-1.md").exists()
