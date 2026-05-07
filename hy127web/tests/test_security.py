"""Tests for path traversal prevention (§6 of spec)."""

import os
import tempfile
import pytest

from hy127web.worker.services.security import validate_path


@pytest.fixture
def project_dir(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hello')")
    (tmp_path / "data.txt").write_text("data")
    return str(tmp_path)


class TestPathValidation:
    def test_valid_relative_path(self, project_dir):
        assert validate_path(project_dir, "src/main.py") is True

    def test_valid_root_file(self, project_dir):
        assert validate_path(project_dir, "data.txt") is True

    def test_reject_parent_traversal(self, project_dir):
        assert validate_path(project_dir, "../secret") is False

    def test_reject_double_parent_traversal(self, project_dir):
        assert validate_path(project_dir, "../../etc/passwd") is False

    def test_reject_absolute_path_unix(self, project_dir):
        assert validate_path(project_dir, "/etc/passwd") is False

    def test_reject_absolute_path_windows(self, project_dir):
        assert validate_path(project_dir, "C:\\Windows\\system32") is False

    def test_reject_drive_letter_variant(self, project_dir):
        assert validate_path(project_dir, "D:\\hack\\file.py") is False

    def test_reject_unc_path_backslash(self, project_dir):
        assert validate_path(project_dir, "\\\\server\\share") is False

    def test_reject_unc_path_forward(self, project_dir):
        assert validate_path(project_dir, "//server/share") is False

    def test_reject_empty_path(self, project_dir):
        assert validate_path(project_dir, "") is False

    def test_reject_whitespace_only(self, project_dir):
        assert validate_path(project_dir, "   ") is False

    def test_reject_path_with_encoded_traversal(self, project_dir):
        assert validate_path(project_dir, "..\\..\\secret") is False

    def test_nonexistent_but_within_boundary(self, project_dir):
        assert validate_path(project_dir, "src/nonexistent.py") is True
