"""Tests for file service: version conflict detection (§9.1 of spec)."""

import os
import hashlib
import pytest

from code880web.worker.services.file_service import FileService


@pytest.fixture
def project(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('v1')", encoding="utf-8")
    (tmp_path / "readme.txt").write_text("hello", encoding="utf-8")
    (tmp_path / ".web-workbench").mkdir()
    return FileService(str(tmp_path))


class TestFileRead:
    def test_read_text_file(self, project):
        result = project.read_file("src/main.py")
        assert result["type"] == "text"
        assert "print" in result["content"]
        assert result["sha256"]

    def test_read_nonexistent_raises(self, project):
        with pytest.raises(FileNotFoundError):
            project.read_file("nonexistent.py")

    def test_reject_traversal_path(self, project):
        with pytest.raises(ValueError):
            project.read_file("../../etc/passwd")


class TestFileSave:
    def test_save_with_correct_sha256(self, project):
        read = project.read_file("src/main.py")
        result = project.save_file("src/main.py", "print('v2')", read["sha256"])
        assert result["sha256"] != read["sha256"]

    def test_save_rejects_stale_sha256(self, project):
        project.read_file("src/main.py")
        with pytest.raises(ValueError, match="已被修改"):
            project.save_file("src/main.py", "print('v2')", "wrong_sha256")

    def test_save_without_sha256_check(self, project):
        result = project.save_file("src/main.py", "print('v3')")
        assert result["sha256"]

    def test_save_creates_backup(self, project, tmp_path):
        project.save_file("src/main.py", "print('v2')")
        backup_dir = tmp_path / ".web-workbench" / "backups"
        assert backup_dir.exists()
        backups = list(backup_dir.iterdir())
        assert len(backups) >= 1


class TestFileTree:
    def test_tree_returns_items(self, project):
        tree = project.get_tree()
        names = [n["name"] for n in tree]
        assert "src" in names
        assert "readme.txt" in names

    def test_tree_excludes_hidden(self, project, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / "__pycache__").mkdir()
        tree = project.get_tree()
        names = [n["name"] for n in tree]
        assert ".git" not in names
        assert "__pycache__" not in names


class TestFileSearch:
    def test_search_by_name(self, project):
        results = project.search_files("main")
        assert len(results) >= 1
        assert any("main.py" in r["name"] for r in results)

    def test_search_no_match(self, project):
        results = project.search_files("nonexistent_xyz")
        assert len(results) == 0
