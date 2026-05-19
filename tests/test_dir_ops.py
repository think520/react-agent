from tools.dir_ops import list_dir, change_dir, stat_path
from tools.base import ToolResult


def test_list_dir(tmp_path):
    (tmp_path / "subdir").mkdir()
    (tmp_path / "file.txt").write_text("content", encoding="utf-8")

    result = list_dir(str(tmp_path), workspace=str(tmp_path))
    assert isinstance(result, ToolResult)
    assert result.ok
    assert "subdir" in result.content
    assert "file.txt" in result.content


def test_list_dir_empty(tmp_path):
    result = list_dir(str(tmp_path), workspace=str(tmp_path))
    assert result.ok
    assert result.content == "(empty directory)"


def test_list_dir_not_found(tmp_path):
    result = list_dir(str(tmp_path / "nope"), workspace=str(tmp_path))
    assert not result.ok
    assert "not found" in result.content.lower()


def test_change_dir_with_relative_path(tmp_path):
    subdir = tmp_path / "subdir"
    subdir.mkdir()

    result = change_dir("subdir", cwd=str(tmp_path), workspace=str(tmp_path))
    assert isinstance(result, ToolResult)
    assert result.ok
    assert str(subdir.resolve()) in result.content
    assert result.data["cwd"] == str(subdir.resolve())


def test_change_dir_outside_workspace(tmp_path):
    outside = tmp_path.parent
    result = change_dir(str(outside), cwd=str(tmp_path), workspace=str(tmp_path))
    assert not result.ok
    assert "denied" in result.content.lower()


def test_stat_path_file(tmp_path):
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello", encoding="utf-8")

    result = stat_path(str(test_file), workspace=str(tmp_path))
    assert isinstance(result, ToolResult)
    assert result.ok
    assert "file" in result.content.lower()
    assert "test.txt" in result.content


def test_stat_path_not_found(tmp_path):
    result = stat_path(str(tmp_path / "nonexistent"), workspace=str(tmp_path))
    assert not result.ok
    assert "not found" in result.content.lower()


def test_change_dir_subdir_then_back_to_root(tmp_path):
    """After cd into subdir, can cd back to root but cannot leave root."""
    subdir = tmp_path / "subdir"
    subdir.mkdir()

    # cd into subdir — workspace stays at tmp_path
    result = change_dir("subdir", cwd=str(tmp_path), workspace=str(tmp_path))
    assert result.ok
    assert result.data["cwd"] == str(subdir.resolve())

    # cd .. back to root — should succeed
    result = change_dir("..", cwd=str(subdir.resolve()), workspace=str(tmp_path))
    assert result.ok
    assert result.data["cwd"] == str(tmp_path.resolve())

    # cd .. from root — should be denied
    result = change_dir("..", cwd=str(tmp_path.resolve()), workspace=str(tmp_path))
    assert not result.ok
    assert "denied" in result.content.lower()
