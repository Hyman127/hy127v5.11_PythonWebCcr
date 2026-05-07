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


PROTECTED_TOP_NAMES = {".git", ".venv", ".web-workbench", ".hy127web_global"}
MAX_TEXT_SAVE_BYTES = 2 * 1024 * 1024


class FileService:
    def __init__(self, project_root: str):
        self.project_root = project_root

    def _check_protected(self, rel_path: str):
        parts = rel_path.replace("\\", "/").split("/")
        lower_parts = {p.lower() for p in parts}
        protected_lower = {n.lower() for n in PROTECTED_TOP_NAMES}
        if lower_parts & protected_lower:
            raise ValueError("禁止操作受保护的目录")

    @staticmethod
    def _check_leaf_name(name: str):
        if not name or not name.strip():
            raise ValueError("名称不能为空")
        if "/" in name or "\\" in name:
            raise ValueError("名称不能包含路径分隔符")
        if name in (".", ".."):
            raise ValueError("名称不合法")
        if "\0" in name:
            raise ValueError("名称不能包含空字符")

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
        self._check_protected(rel_path)

        raw = content.encode("utf-8")
        if len(raw) > MAX_TEXT_SAVE_BYTES:
            raise ValueError("文件超过 2 MB，禁止通过 Web 编辑保存")

        abs_path = os.path.join(self.project_root, rel_path)

        if base_sha256 and os.path.isfile(abs_path):
            with open(abs_path, "rb") as f:
                current_sha256 = hashlib.sha256(f.read()).hexdigest()
            if current_sha256 != base_sha256:
                raise ValueError("文件已被修改，请刷新后重试")

        if os.path.isfile(abs_path):
            self._backup(abs_path, rel_path)

        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
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

    def create_file(self, rel_path: str) -> dict:
        if not validate_path(self.project_root, rel_path):
            raise ValueError("路径不合法")
        self._check_protected(rel_path)
        abs_path = os.path.join(self.project_root, rel_path)
        if os.path.exists(abs_path):
            raise FileExistsError(f"文件已存在: {rel_path}")
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write("")
        return {"path": rel_path, "type": "file", "created": True}

    def create_dir(self, rel_path: str) -> dict:
        if not validate_path(self.project_root, rel_path):
            raise ValueError("路径不合法")
        self._check_protected(rel_path)
        abs_path = os.path.join(self.project_root, rel_path)
        if os.path.exists(abs_path):
            raise FileExistsError(f"已存在: {rel_path}")
        os.makedirs(abs_path, exist_ok=True)
        return {"path": rel_path, "type": "directory", "created": True}

    def rename(self, rel_path: str, new_name: str) -> dict:
        if not validate_path(self.project_root, rel_path):
            raise ValueError("路径不合法")
        self._check_protected(rel_path)
        self._check_leaf_name(new_name)
        abs_path = os.path.join(self.project_root, rel_path)
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"不存在: {rel_path}")
        parent_dir = os.path.dirname(abs_path)
        new_abs_path = os.path.join(parent_dir, new_name)
        new_rel_path = os.path.join(os.path.dirname(rel_path), new_name).replace("\\", "/")
        if not validate_path(self.project_root, new_rel_path):
            raise ValueError("新路径不合法")
        if os.path.exists(new_abs_path):
            raise FileExistsError(f"目标已存在: {new_name}")
        os.rename(abs_path, new_abs_path)
        return {"old_path": rel_path, "new_path": new_rel_path}

    def delete_file(self, rel_path: str, soft: bool = True) -> dict:
        if not validate_path(self.project_root, rel_path):
            raise ValueError("路径不合法")
        self._check_protected(rel_path)
        abs_path = os.path.join(self.project_root, rel_path)
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"不存在: {rel_path}")
        is_dir = os.path.isdir(abs_path)
        if soft and not is_dir:
            trash_dir = os.path.join(self.project_root, ".web-workbench", "trash")
            os.makedirs(trash_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = rel_path.replace("/", "_").replace("\\", "_")
            dest = os.path.join(trash_dir, f"{ts}_{safe_name}")
            shutil.move(abs_path, dest)
            return {"path": rel_path, "deleted": True, "soft": True, "trash_path": dest}
        if is_dir:
            shutil.rmtree(abs_path)
        else:
            os.remove(abs_path)
        return {"path": rel_path, "deleted": True, "soft": False}

    def copy_path(self, src_rel: str, dst_rel: str) -> dict:
        if not validate_path(self.project_root, src_rel):
            raise ValueError("源路径不合法")
        if not validate_path(self.project_root, dst_rel):
            raise ValueError("目标路径不合法")
        self._check_protected(src_rel)
        self._check_protected(dst_rel)
        src_abs = os.path.join(self.project_root, src_rel)
        dst_abs = os.path.join(self.project_root, dst_rel)
        if not os.path.exists(src_abs):
            raise FileNotFoundError(f"源不存在: {src_rel}")
        if os.path.exists(dst_abs):
            raise FileExistsError(f"目标已存在: {dst_rel}")
        os.makedirs(os.path.dirname(dst_abs), exist_ok=True)
        if os.path.isdir(src_abs):
            shutil.copytree(src_abs, dst_abs)
        else:
            shutil.copy2(src_abs, dst_abs)
        return {"src": src_rel, "dst": dst_rel, "copied": True}

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
