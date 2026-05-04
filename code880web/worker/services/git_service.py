import os
import shutil
import subprocess

from .security import validate_path


class GitService:
    MAX_DIFF_BYTES = 80 * 1024
    MAX_HUNKS_PER_FILE = 3

    def __init__(self, project_root: str):
        self.project_root = project_root

    def available(self) -> dict:
        git_installed = shutil.which("git") is not None
        is_repo = False
        repo_root = ""
        branch = ""
        error = ""
        if git_installed:
            try:
                result = subprocess.run(
                    ["git", "rev-parse", "--show-toplevel"],
                    cwd=self.project_root, capture_output=True, text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    repo_root_abs = result.stdout.strip()
                    if self._is_within_project(repo_root_abs):
                        is_repo = True
                        repo_root = repo_root_abs
                        branch_result = subprocess.run(
                            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                            cwd=self.project_root, capture_output=True, text=True,
                            timeout=5,
                        )
                        branch = branch_result.stdout.strip()
                    else:
                        error = "Git 仓库根目录不在项目内"
                else:
                    error = result.stderr.strip()
            except Exception as e:
                error = str(e)
        return {
            "git_installed": git_installed,
            "is_repo": is_repo,
            "root": repo_root,
            "branch": branch,
            "error": error,
        }

    def status(self) -> dict:
        self._ensure_repo()
        staged, unstaged, untracked, conflicted = [], [], [], []

        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.project_root, capture_output=True, text=True,
                timeout=5,
            )
            for line in result.stdout.splitlines():
                if not line:
                    continue
                xy = line[:2]
                fname = line[3:].strip()
                if xy[0] in "MRC" or (xy[0] == "A" and xy[1] != "?"):
                    staged.append(fname)
                if xy[1] in "MRC" or (xy[1] == "M" and xy[0] != "?"):
                    unstaged.append(fname)
                if xy == "??":
                    untracked.append(fname)
                if xy[0] == "U" or xy[1] == "U" or "UU" in xy:
                    conflicted.append(fname)

            branch = self._current_branch()
        except Exception:
            return {"branch": "", "staged": [], "unstaged": [], "untracked": [], "conflicted": []}

        return {
            "branch": branch,
            "staged": staged,
            "unstaged": unstaged,
            "untracked": untracked,
            "conflicted": conflicted,
        }

    def diff(self, path: str = "") -> dict:
        self._ensure_repo()
        if path:
            if not validate_path(self.project_root, path):
                raise ValueError("路径不合法")
            return self._diff_single(path)

        cmd = ["git", "diff", "--stat"]
        result = subprocess.run(cmd, cwd=self.project_root, capture_output=True, text=True, timeout=5)
        summary = result.stdout.strip()

        cmd = ["git", "diff", "--unified=8"]
        result = subprocess.run(cmd, cwd=self.project_root, capture_output=True, text=True, timeout=5)
        full_diff = result.stdout

        truncated = False
        files = []
        current_file = None
        current_hunks = 0
        current_lines: list[str] = []

        for line in full_diff.splitlines():
            if line.startswith("diff --git"):
                if current_file:
                    files.append({
                        "path": current_file,
                        "hunks_preview": "\n".join(current_lines),
                        "truncated": current_hunks > self.MAX_HUNKS_PER_FILE,
                    })
                current_file = self._extract_diff_path(line)
                current_hunks = 0
                current_lines = [line]
            else:
                current_lines.append(line)
                if line.startswith("@@"):
                    current_hunks += 1

        if current_file:
            files.append({
                "path": current_file,
                "hunks_preview": "\n".join(current_lines),
                "truncated": current_hunks > self.MAX_HUNKS_PER_FILE,
            })

        total_size = len(full_diff.encode("utf-8"))
        if total_size > self.MAX_DIFF_BYTES:
            truncated = True

        return {
            "files": files,
            "summary": summary,
            "truncated": truncated,
        }

    def branch(self) -> dict:
        self._ensure_repo()
        current = self._current_branch()
        branches = []
        try:
            result = subprocess.run(
                ["git", "branch", "--format=%(refname:short)"],
                cwd=self.project_root, capture_output=True, text=True,
                timeout=5,
            )
            for name in result.stdout.splitlines():
                branches.append({
                    "name": name.strip(),
                    "current": name.strip() == current,
                })
        except Exception:
            branches = [{"name": current, "current": True}]
        return {"current": current, "branches": branches}

    def log(self, max_count: int = 20) -> dict:
        self._ensure_repo()
        try:
            result = subprocess.run(
                ["git", "log", f"--max-count={max_count}", "--format=%H|%h|%s|%an|%ai"],
                cwd=self.project_root, capture_output=True, text=True,
                timeout=5,
            )
        except Exception:
            return {"commits": []}
        commits = []
        for line in result.stdout.splitlines():
            parts = line.split("|", 4)
            if len(parts) >= 5:
                commits.append({
                    "hash": parts[0],
                    "short_hash": parts[1],
                    "subject": parts[2],
                    "author": parts[3],
                    "date": parts[4],
                })
        return {"commits": commits}

    def generate_commit_message(self) -> dict:
        """Generate a draft commit message from staged + unstaged diff summary."""
        self._ensure_repo()
        diff_data = self.diff()
        stat = diff_data.get("summary", "")
        changed_files = [f["path"] for f in diff_data.get("files", []) if f.get("path")]
        if not stat and not changed_files:
            return {"draft": "", "files": [], "hint": "无变更可提交"}
        draft_lines = []
        if changed_files:
            draft_lines.append(f"更新 {len(changed_files)} 个文件")
            draft_lines.append("")
            draft_lines.append("变更文件:")
            for f in changed_files[:10]:
                draft_lines.append(f"- {f}")
            if len(changed_files) > 10:
                draft_lines.append(f"- ... 及其他 {len(changed_files) - 10} 个文件")
        draft = "\n".join(draft_lines)
        return {"draft": draft, "files": changed_files, "stat": stat}

    def _diff_single(self, rel_path: str) -> dict:
        cmd = ["git", "diff", "--unified=8", "--", rel_path]
        result = subprocess.run(cmd, cwd=self.project_root, capture_output=True, text=True, timeout=5)
        diff_text = result.stdout
        total_size = len(diff_text.encode("utf-8"))
        truncated = total_size > self.MAX_DIFF_BYTES
        return {
            "path": rel_path,
            "diff": diff_text if not truncated else diff_text[:self.MAX_DIFF_BYTES],
            "truncated": truncated,
        }

    def _ensure_repo(self):
        avail = self.available()
        if not avail["git_installed"]:
            raise RuntimeError("未检测到 Git")
        if not avail["is_repo"]:
            raise RuntimeError("当前项目不是 Git 仓库")

    def _current_branch(self) -> str:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.project_root, capture_output=True, text=True,
                timeout=5,
            )
            return result.stdout.strip()
        except Exception:
            return ""

    def _is_within_project(self, repo_root: str) -> bool:
        repo_norm = os.path.normpath(repo_root)
        proj_norm = os.path.normpath(self.project_root)
        return repo_norm.startswith(proj_norm) or repo_norm == proj_norm

    @staticmethod
    def _extract_diff_path(line: str) -> str:
        if " b/" in line:
            return line.split(" b/")[-1]
        return ""
