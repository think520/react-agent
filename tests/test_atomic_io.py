"""P0-13 + P1-8: writes to user data are atomic and one workspace has one writer."""

import json
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_document_write_failure_keeps_the_original(tmp_path):
    """P0-13: raw/ is the immutable evidence layer and was written with a bare
    open(path, "w"), so a failure mid-write truncated the user original."""
    from service.document_edit_service import DocumentEditService

    target = tmp_path / "raw" / "lesson.md"
    target.parent.mkdir(parents=True)
    target.write_text("原始内容", encoding="utf-8")

    with patch("os.replace", side_effect=OSError("disk full")):
        try:
            DocumentEditService._write_file(str(target), "新内容")
        except OSError:
            pass

    assert target.read_text(encoding="utf-8") == "原始内容"
    assert list(target.parent.glob("*.tmp")) == []


def test_session_save_failure_keeps_the_previous_snapshot(tmp_path):
    """P1-8: the session file was the only bare JSON write left in the project."""
    from core.session import Session

    path = tmp_path / "session.json"
    session = Session.new(str(tmp_path))
    session.add_message("user", "第一条")
    session.save_to_file(str(path))
    before = path.read_text(encoding="utf-8")

    session.add_message("user", "新的一条")
    with patch("os.replace", side_effect=OSError("disk full")):
        try:
            session.save_to_file(str(path))
        except OSError:
            pass

    after = path.read_text(encoding="utf-8")
    assert after == before
    assert json.loads(after)["messages"]


_LOCK_SCRIPT = "\n".join([
    "import sys, time",
    "sys.path.insert(0, %r)" % str(REPO_ROOT),
    "from core.atomic_io import workspace_write_lock",
    "with workspace_write_lock(sys.argv[1], timeout=5):",
    "    print('locked', flush=True)",
    "    time.sleep(3)",
])


def test_workspace_lock_excludes_another_process(tmp_path):
    """P0-13/P1-8: the CLI and the web server share one workspace."""
    from core.atomic_io import LockTimeout, workspace_write_lock

    workspace = str(tmp_path)
    holder = subprocess.Popen(
        [sys.executable, "-c", _LOCK_SCRIPT, workspace],
        stdout=subprocess.PIPE,
        text=True,
        cwd=str(REPO_ROOT),
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "locked"
        started = time.monotonic()
        try:
            with workspace_write_lock(workspace, timeout=0.5):
                raise AssertionError("the lock was handed out twice")
        except LockTimeout:
            pass
        assert time.monotonic() - started < 3
    finally:
        holder.kill()
        holder.wait(timeout=10)
