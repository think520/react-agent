"""ResearchStore 的并发去重分支。"""

from __future__ import annotations

from types import SimpleNamespace

from research.store import ResearchStore


def _snapshot():
    return SimpleNamespace(
        final_url="https://example.com/a", title="A", domain="example.com",
        content="正文", content_hash="hash-1", reader="direct",
    )


def test_a_concurrent_duplicate_snapshot_returns_the_existing_id(tmp_path, monkeypatch):
    """SELECT 与 INSERT 之间另一个写者插入了同一快照：应返回已有 id，而不是崩溃。

    以前 except 分支引用了未导入的 sqlite3，这里会抛 NameError（ruff F821 发现）。
    """
    store = ResearchStore(str(tmp_path))
    first = store.save_snapshot("https://example.com/a", _snapshot(), "摘录")

    real_connect = store._connect

    class _HideFirstSelect:
        def __init__(self, conn):
            self._conn = conn
            self._selects = 0

        def __enter__(self):
            self._inner = self._conn.__enter__()
            return self

        def __exit__(self, *exc):
            return self._conn.__exit__(*exc)

        def execute(self, sql, params=()):
            if sql.lstrip().upper().startswith("SELECT") and self._selects == 0:
                self._selects += 1
                return self._inner.execute("SELECT NULL AS id WHERE 0")
            return self._inner.execute(sql, params)

    monkeypatch.setattr(store, "_connect", lambda: _HideFirstSelect(real_connect()))
    assert store.save_snapshot("https://example.com/a", _snapshot(), "摘录") == first
