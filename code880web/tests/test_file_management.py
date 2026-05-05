"""Tests for file management operations: create, mkdir, rename, delete, copy."""

import os

import pytest

from code880web.worker.services.file_service import FileService


@pytest.fixture
def fs(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hello')", encoding="utf-8")
    (tmp_path / ".web-workbench").mkdir()
    return FileService(str(tmp_path))


class TestCreateFile:
    def test_create_empty_file(self, fs, tmp_path):
        result = fs.create_file("new.py")
        assert result["created"] is True
        assert (tmp_path / "new.py").exists()

    def test_create_in_subdir(self, fs, tmp_path):
        result = fs.create_file("src/utils/helpers.py")
        assert (tmp_path / "src" / "utils" / "helpers.py").exists()

    def test_create_existing_raises(self, fs):
        with pytest.raises(FileExistsError):
            fs.create_file("src/main.py")

    def test_create_rejects_traversal(self, fs):
        with pytest.raises(ValueError):
            fs.create_file("../../etc/passwd")

    def test_create_empty_name_rejected(self, fs):
        with pytest.raises(ValueError):
            fs.create_file("")


class TestCreateDir:
    def test_create_directory(self, fs, tmp_path):
        result = fs.create_dir("docs")
        assert result["created"] is True
        assert (tmp_path / "docs").is_dir()

    def test_create_nested_dir(self, fs, tmp_path):
        fs.create_dir("a/b/c")
        assert (tmp_path / "a" / "b" / "c").is_dir()

    def test_mkdir_existing_raises(self, fs):
        fs.create_dir("mydir")
        with pytest.raises(FileExistsError):
            fs.create_dir("mydir")


class TestRename:
    def test_rename_file(self, fs, tmp_path):
        result = fs.rename("src/main.py", "app.py")
        assert result["new_path"] == "src/app.py"
        assert not (tmp_path / "src" / "main.py").exists()
        assert (tmp_path / "src" / "app.py").exists()

    def test_rename_empty_name_raises(self, fs):
        with pytest.raises(ValueError):
            fs.rename("src/main.py", "")

    def test_rename_nonexistent_raises(self, fs):
        with pytest.raises(FileNotFoundError):
            fs.rename("nonexistent.py", "newname.py")

    def test_rename_to_existing_raises(self, fs):
        tmp_path = fs.project_root
        other = os.path.join(tmp_path, "src", "other.py")
        open(other, "w").write("x")
        with pytest.raises(FileExistsError):
            fs.rename("src/main.py", "other.py")

    def test_rename_rejects_path_separator(self, fs):
        with pytest.raises(ValueError, match="路径分隔符"):
            fs.rename("src/main.py", "nested/app.py")


class TestDeleteFile:
    def test_soft_delete_file(self, fs, tmp_path):
        result = fs.delete_file("src/main.py", soft=True)
        assert result["deleted"] is True
        assert result["soft"] is True
        assert not (tmp_path / "src" / "main.py").exists()
        assert (tmp_path / ".web-workbench" / "trash").is_dir()

    def test_hard_delete_file(self, fs, tmp_path):
        result = fs.delete_file("src/main.py", soft=False)
        assert result["deleted"] is True
        assert result["soft"] is False
        assert not (tmp_path / "src" / "main.py").exists()

    def test_delete_nonexistent_raises(self, fs):
        with pytest.raises(FileNotFoundError):
            fs.delete_file("nonexistent.py")

    def test_delete_directory(self, fs, tmp_path):
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "readme.md").write_text("hello")
        result = fs.delete_file("docs", soft=False)
        assert result["deleted"] is True
        assert not (tmp_path / "docs").exists()

    def test_delete_rejects_traversal(self, fs):
        with pytest.raises(ValueError):
            fs.delete_file("../../etc/passwd")


class TestCopyPath:
    def test_copy_file(self, fs, tmp_path):
        result = fs.copy_path("src/main.py", "src/main_copy.py")
        assert result["copied"] is True
        assert (tmp_path / "src" / "main_copy.py").exists()

    def test_copy_to_new_dir(self, fs, tmp_path):
        fs.copy_path("src/main.py", "backup/main.py")
        assert (tmp_path / "backup" / "main.py").exists()

    def test_copy_rejects_traversal_src(self, fs):
        with pytest.raises(ValueError):
            fs.copy_path("../../etc/passwd", "local.txt")

    def test_copy_rejects_traversal_dst(self, fs):
        with pytest.raises(ValueError):
            fs.copy_path("src/main.py", "../../etc/passwd")

    def test_copy_nonexistent_raises(self, fs):
        with pytest.raises(FileNotFoundError):
            fs.copy_path("nonexistent.py", "dest.py")
