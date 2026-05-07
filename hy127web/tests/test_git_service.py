"""Tests for GitService: read-only git operations."""

import os
import subprocess
import sys

import pytest

from hy127web.worker.services.git_service import GitService


@pytest.fixture
def git_repo(tmp_path):
    """Create a real git repo inside tmp_path for testing."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hello')", encoding="utf-8")
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW
    else:
        creationflags = 0

    subprocess.run(["git", "init", "-b", "master"], cwd=str(tmp_path),
                   capture_output=True, creationflags=creationflags)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path),
                   capture_output=True, creationflags=creationflags)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path),
                   capture_output=True, creationflags=creationflags)
    subprocess.run(["git", "add", "-A"], cwd=str(tmp_path),
                   capture_output=True, creationflags=creationflags)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=str(tmp_path),
                   capture_output=True, creationflags=creationflags)
    (tmp_path / "src" / "main.py").write_text("print('modified')", encoding="utf-8")
    (tmp_path / "new_file.py").write_text("print('new')", encoding="utf-8")
    return GitService(str(tmp_path))


@pytest.fixture
def non_repo(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hello')", encoding="utf-8")
    return GitService(str(tmp_path))


class TestGitAvailable:
    def test_repo_detected(self, git_repo):
        info = git_repo.available()
        assert info["git_installed"] is True
        assert info["is_repo"] is True
        assert info["root"]
        assert info["branch"] == "master"

    def test_non_repo(self, non_repo):
        info = non_repo.available()
        assert info["git_installed"] is True
        assert info["is_repo"] is False

    def test_ensure_repo_raises_on_non_repo(self, non_repo):
        with pytest.raises(RuntimeError):
            non_repo.status()


class TestGitStatus:
    def test_detects_modified_and_untracked(self, git_repo):
        status = git_repo.status()
        assert "src/main.py" in status["unstaged"]
        assert "new_file.py" in status["untracked"]

    def test_clean_repo(self, git_repo):
        subprocess.run(["git", "add", "src/main.py", "new_file.py"], cwd=git_repo.project_root,
                       capture_output=True)
        subprocess.run(["git", "commit", "-m", "all"], cwd=git_repo.project_root,
                       capture_output=True)
        status = git_repo.status()
        assert len(status["staged"]) == 0
        assert len(status["unstaged"]) == 0
        assert len(status["untracked"]) == 0


class TestGitDiff:
    def test_diff_has_files(self, git_repo):
        diff = git_repo.diff()
        assert len(diff["files"]) >= 1
        assert any(f["path"] == "src/main.py" for f in diff["files"])

    def test_single_file_diff(self, git_repo):
        diff = git_repo.diff("src/main.py")
        assert diff["path"] == "src/main.py"
        assert "print('modified')" in diff["diff"]

    def test_diff_rejects_traversal(self, git_repo):
        with pytest.raises(ValueError):
            git_repo.diff("../../etc/passwd")


class TestGitBranch:
    def test_current_branch(self, git_repo):
        branch = git_repo.branch()
        assert branch["current"] == "master"
        assert any(b["name"] == "master" for b in branch["branches"])


class TestGitLog:
    def test_log_has_initial_commit(self, git_repo):
        log = git_repo.log()
        assert len(log["commits"]) >= 1
        assert log["commits"][-1]["subject"] == "initial"


class TestGitCommitMessage:
    def test_generates_draft(self, git_repo):
        cm = git_repo.generate_commit_message()
        assert cm["draft"]
        assert "src/main.py" in cm["files"]


class TestGitDiffTruncation:
    def test_large_diff_truncated(self, git_repo):
        diff = git_repo.diff()
        assert isinstance(diff["truncated"], bool)
        assert isinstance(diff["summary"], str)
        for f in diff["files"]:
            assert "path" in f
            assert "hunks_preview" in f
            assert isinstance(f["truncated"], bool)
