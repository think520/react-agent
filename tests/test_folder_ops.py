"""③（E17）：树上写操作的后端语义 —— 新建文件夹、删文件夹=只删容器、移动。

设计 §3.5 决定 21：删文件夹**默认只删容器**，里面的资料移回库根并明说后果
（参考项目原话：a container's ⋯ must not be able to destroy work）。
"""

import pytest

from service.kb_service import KBService
from service.library_service import LibraryService


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "library"
    LibraryService(str(tmp_path / "home")).initialize(str(root), name="Portable")
    return root


def _service(library):
    return KBService(str(library))


def test_create_folder_makes_a_real_directory(library):
    result = _service(library).create_folder("课程包/第一章")
    assert result["ok"], result
    assert (library / "课程包" / "第一章").is_dir()
    assert result["folder"]["path"] == "课程包/第一章"


def test_create_folder_rejects_bad_targets(library):
    service = _service(library)
    (library / "已有").mkdir()
    assert service.create_folder("../外面")["code"] == "invalid_target"
    assert service.create_folder("已有")["code"] == "target_exists"
    assert service.create_folder("wiki/我的")["code"] == "invalid_target"
    assert service.create_folder("")["code"] == "invalid_target"


def test_delete_folder_moves_materials_back_to_the_root(library):
    (library / "课程包" / "第一章").mkdir(parents=True)
    (library / "课程包" / "第一章" / "第一课.md").write_text("# 第一课", encoding="utf-8")
    (library / "课程包" / "封面.png").write_bytes(b"png")

    result = _service(library).delete_folder("课程包")

    assert result["ok"], result
    assert result["moved"] == ["课程包/第一章/第一课.md"]
    assert (library / "第一课.md").is_file(), "资料必须被移回库根，而不是被删掉"
    assert not (library / "课程包" / "第一章").exists()
    # 非资料文件留在原地 → 目录因此保留（不静默丢东西）
    assert (library / "课程包" / "封面.png").is_file()
    assert result["kept_directory"] is True


def test_delete_folder_removes_the_directory_when_it_becomes_empty(library):
    (library / "空壳").mkdir()
    (library / "空壳" / "第一课.md").write_text("# 第一课", encoding="utf-8")

    result = _service(library).delete_folder("空壳")

    assert result["ok"], result
    assert not (library / "空壳").exists()
    assert (library / "第一课.md").is_file()
    assert result["kept_directory"] is False


def test_delete_folder_refuses_the_root_and_internal_dirs(library):
    service = _service(library)
    assert service.delete_folder("")["code"] == "invalid_target"
    assert service.delete_folder(".bobodan")["code"] == "invalid_target"
    assert service.delete_folder("wiki")["code"] == "invalid_target"
