import hashlib
import os
import shutil
from datetime import datetime
from pathlib import Path

from .security import validate_path

HIDDEN_DIRS = {
    ".git", ".svn", ".hg", "__pycache__", ".mypy_cache", ".pytest_cache",
    "node_modules", ".venv", ".uv-cache", ".web-workbench",
    ".vscode", ".idea", ".lingma",
}

HIDDEN_FILES = {".DS_Store", "Thumbs.db", "desktop.ini"}

TEXT_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".json", ".toml", ".yaml", ".yml",
    ".md", ".txt", ".csv", ".log", ".bat", ".ps1", ".sh", ".html", ".css",
    ".xml", ".ini", ".cfg", ".conf", ".env", ".gitignore", ".editorconfig",
    ".sql", ".r", ".R", ".ipynb",
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".ico", ".webp"}
PREVIEW_EXTENSIONS = {".pdf", ".xlsx", ".docx", ".pptx"}


class FileService:
    def __init__(self, project_root: str):
        self.project_root = project_root

    def get_tree(self, rel_dir: str = "", depth: int = 3) -> list[dict]:
        if rel_dir and not validate_path(self.project_root, rel_dir):
            return []

        abs_dir = os.path.join(self.project_root, rel_dir) if rel_dir else self.project_root
        if not os.path.isdir(abs_dir):
            return []

        return self._scan_dir(abs_dir, rel_dir, depth)

    def _scan_dir(self, abs_dir: str, rel_prefix: str, depth: int) -> list[dict]:
        if depth <= 0:
            return []

        items = []
        try:
            entries = sorted(os.scandir(abs_dir), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return []

        for entry in entries:
            if entry.name in HIDDEN_DIRS or entry.name in HIDDEN_FILES:
                continue
            if entry.name.startswith(".") and entry.name not in (".env",):
                continue

            rel_path = os.path.join(rel_prefix, entry.name) if rel_prefix else entry.name
            rel_path = rel_path.replace("\\", "/")

            if entry.is_dir():
                children = self._scan_dir(entry.path, rel_path, depth - 1) if depth > 1 else []
                items.append({
                    "name": entry.name,
                    "path": rel_path,
                    "type": "directory",
                    "children": children,
                    "has_children": bool(children) or depth <= 1,
                })
            elif entry.is_file():
                ext = os.path.splitext(entry.name)[1].lower()
                try:
                    size = entry.stat().st_size
                except OSError:
                    size = 0
                items.append({
                    "name": entry.name,
                    "path": rel_path,
                    "type": "file",
                    "extension": ext,
                    "size": size,
                    "editable": ext in TEXT_EXTENSIONS,
                    "previewable": ext in PREVIEW_EXTENSIONS or ext in IMAGE_EXTENSIONS,
                })
        return items

    def read_file(self, rel_path: str) -> dict:
        if not validate_path(self.project_root, rel_path):
            raise ValueError("路径不合法")

        abs_path = os.path.join(self.project_root, rel_path)
        if not os.path.isfile(abs_path):
            raise FileNotFoundError(f"文件不存在: {rel_path}")

        with open(abs_path, "rb") as f:
            raw = f.read()

        sha256 = hashlib.sha256(raw).hexdigest()

        ext = os.path.splitext(rel_path)[1].lower()
        if ext in IMAGE_EXTENSIONS:
            import base64
            return {
                "path": rel_path,
                "type": "image",
                "content_base64": base64.b64encode(raw).decode(),
                "sha256": sha256,
                "size": len(raw),
            }

        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            content = raw.decode("gbk", errors="replace")

        return {
            "path": rel_path,
            "type": "text",
            "content": content,
            "sha256": sha256,
            "size": len(raw),
            "extension": ext,
        }

    def save_file(self, rel_path: str, content: str, base_sha256: str | None = None) -> dict:
        if not validate_path(self.project_root, rel_path):
            raise ValueError("路径不合法")

        abs_path = os.path.join(self.project_root, rel_path)

        if base_sha256 and os.path.isfile(abs_path):
            with open(abs_path, "rb") as f:
                current_sha256 = hashlib.sha256(f.read()).hexdigest()
            if current_sha256 != base_sha256:
                raise ValueError("文件已被修改，请刷新后重试")

        if os.path.isfile(abs_path):
            self._backup(abs_path, rel_path)

        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        raw = content.encode("utf-8")
        with open(abs_path, "wb") as f:
            f.write(raw)

        new_sha256 = hashlib.sha256(raw).hexdigest()
        return {"path": rel_path, "sha256": new_sha256, "size": len(raw)}

    def _backup(self, abs_path: str, rel_path: str):
        backup_dir = os.path.join(self.project_root, ".web-workbench", "backups")
        os.makedirs(backup_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = rel_path.replace("/", "_").replace("\\", "_")
        backup_path = os.path.join(backup_dir, f"{ts}_{safe_name}")
        try:
            shutil.copy2(abs_path, backup_path)
        except Exception:
            pass

    def search_files(self, query: str, max_results: int = 50) -> list[dict]:
        results = []
        query_lower = query.lower()
        for root, dirs, files in os.walk(self.project_root):
            dirs[:] = [d for d in dirs if d not in HIDDEN_DIRS and not d.startswith(".")]
            for fname in files:
                if fname in HIDDEN_FILES:
                    continue
                if query_lower in fname.lower():
                    rel = os.path.relpath(os.path.join(root, fname), self.project_root)
                    rel = rel.replace("\\", "/")
                    results.append({"name": fname, "path": rel, "match_type": "filename"})
                    if len(results) >= max_results:
                        return results
        return results
