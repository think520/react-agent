import os
from tools.file_ops import read_file, write_file
from tools.base import ToolResult, DENY_READ_PATTERNS


def test_read_file(tmp_path):
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello world", encoding="utf-8")

    result = read_file(str(test_file), workspace=str(tmp_path))
    assert isinstance(result, ToolResult)
    assert result.ok
    assert result.content == "hello world"


def test_read_file_not_found(tmp_path):
    result = read_file(str(tmp_path / "missing.txt"), workspace=str(tmp_path))
    assert not result.ok
    assert "not found" in result.content.lower()


def test_read_file_outside_workspace(tmp_path):
    result = read_file("/etc/passwd", workspace=str(tmp_path))
    assert not result.ok
    assert "denied" in result.content.lower()


def test_read_file_deny_env(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET=abc", encoding="utf-8")

    result = read_file(str(env_file), workspace=str(tmp_path))
    assert not result.ok
    assert "denied" in result.content.lower()


def test_read_file_binary(tmp_path):
    bin_file = tmp_path / "data.bin"
    bin_file.write_bytes(b"\x00\x01\x02\x03")

    result = read_file(str(bin_file), workspace=str(tmp_path))
    assert not result.ok
    assert "binary" in result.content.lower()


def test_read_file_too_large(tmp_path):
    big_file = tmp_path / "big.txt"
    big_file.write_text("x" * (2 * 1024 * 1024), encoding="utf-8")

    result = read_file(str(big_file), workspace=str(tmp_path))
    assert not result.ok
    assert "too large" in result.content.lower()


def test_write_file(tmp_path):
    file_path = tmp_path / "output.txt"
    result = write_file(str(file_path), "test content", workspace=str(tmp_path))
    assert isinstance(result, ToolResult)
    assert result.ok
    assert file_path.read_text(encoding="utf-8") == "test content"


def test_write_file_creates_directory(tmp_path):
    file_path = tmp_path / "subdir" / "output.txt"
    result = write_file(str(file_path), "content", workspace=str(tmp_path))
    assert result.ok
    assert file_path.exists()


def test_write_file_refuses_overwrite(tmp_path):
    file_path = tmp_path / "existing.txt"
    file_path.write_text("original", encoding="utf-8")

    result = write_file(str(file_path), "new content", workspace=str(tmp_path))
    assert not result.ok
    assert "already exists" in result.content.lower()
    assert file_path.read_text(encoding="utf-8") == "original"


def test_write_file_allows_overwrite(tmp_path):
    file_path = tmp_path / "existing.txt"
    file_path.write_text("original", encoding="utf-8")

    result = write_file(str(file_path), "new content", workspace=str(tmp_path), overwrite=True)
    assert result.ok
    assert file_path.read_text(encoding="utf-8") == "new content"


def test_write_file_outside_workspace(tmp_path):
    result = write_file("/tmp/outside.txt", "content", workspace=str(tmp_path))
    assert not result.ok
    assert "denied" in result.content.lower()


def test_write_file_deny_env(tmp_path):
    env_path = tmp_path / ".env"
    result = write_file(str(env_path), "SECRET=abc", workspace=str(tmp_path))
    assert not result.ok
    assert "denied" in result.content.lower()
