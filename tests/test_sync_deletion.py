"""P0-12: a source the scan cannot see is not necessarily deleted."""

import os

from obsidian.sync import _resolve_deletions, _scan_course_files


def test_scanner_reports_files_it_cannot_read(tmp_path):
    """A file listed by the walk but unreadable (locked, removed, permission)
    used to raise out of the scan or vanish silently."""
    (tmp_path / "real.md").write_text("content", encoding="utf-8")

    real_walk = os.walk

    def fake_walk(root, onerror=None):
        for root_path, dirs, filenames in real_walk(root, onerror=onerror):
            yield root_path, dirs, filenames + ["ghost.md"]

    original = os.walk
    os.walk = fake_walk
    try:
        errors: list[str] = []
        files = _scan_course_files(str(tmp_path), errors)
    finally:
        os.walk = original

    assert errors, "the unreadable file must be reported"
    assert any("ghost" in message for message in errors)
    assert all("ghost" not in source for source, _path, _hash in files)


def test_vault_scanner_reports_unreadable_files(tmp_path):
    """The vault scan is the main obsidian path and had the same silent walk."""
    from obsidian.vault import scan_vault

    (tmp_path / "note.md").write_text("# 标题", encoding="utf-8")

    real_walk = os.walk

    def fake_walk(root, onerror=None):
        for root_path, dirs, filenames in real_walk(root, onerror=onerror):
            yield root_path, dirs, filenames + ["ghost.md"]

    os.walk = fake_walk
    try:
        errors: list[str] = []
        notes = scan_vault(str(tmp_path), errors)
    finally:
        os.walk = real_walk

    assert any("ghost" in message for message in errors)
    assert all("ghost" not in note.rel_path for note in notes)

def test_missing_source_needs_two_scans_before_deletion():
    """One blink of a network share must not cascade-delete a document."""
    old_state = {"course/a.md": "hash-a", "course/b.md": "hash-b"}
    new_state = {"course/b.md": "hash-b"}

    deleted, pending = _resolve_deletions(old_state, new_state, {}, scan_failed=False)
    assert deleted == []
    assert pending == {"course/a.md": 1}

    deleted, pending = _resolve_deletions(old_state, new_state, pending, scan_failed=False)
    assert deleted == ["course/a.md"]
    assert pending == {}


def test_scan_failure_suppresses_deletion_entirely():
    """When the scan reported errors we cannot tell absence from invisibility."""
    old_state = {"course/a.md": "hash-a"}

    deleted, pending = _resolve_deletions(old_state, {}, {"course/a.md": 1}, scan_failed=True)
    assert deleted == []
    assert pending == {"course/a.md": 1}


def test_a_visible_source_clears_its_pending_count():
    old_state = {"course/a.md": "hash-a"}
    deleted, pending = _resolve_deletions(old_state, {"course/a.md": "hash-a"}, {"course/a.md": 1}, scan_failed=False)
    assert deleted == []
    assert pending == {}
