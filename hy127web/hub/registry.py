import hashlib
import json
import os
import sqlite3
from datetime import datetime


class ProjectRegistry:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    workspace_id TEXT PRIMARY KEY,
                    root_path    TEXT UNIQUE NOT NULL,
                    name         TEXT NOT NULL,
                    registered_at TEXT NOT NULL,
                    last_opened   TEXT
                )
            """)
            conn.commit()

    @staticmethod
    def _make_workspace_id(root_path: str) -> str:
        normalized = os.path.normpath(root_path).lower()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]

    def register(self, root_path: str) -> dict:
        root_path = os.path.normpath(root_path)
        if not os.path.isdir(root_path):
            raise ValueError(f"项目路径不存在: {root_path}")

        workspace_id = self._make_workspace_id(root_path)
        name = os.path.basename(root_path) or root_path
        now = datetime.now().isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO projects (workspace_id, root_path, name, registered_at, last_opened)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(workspace_id) DO UPDATE SET last_opened = ?
            """, (workspace_id, root_path, name, now, now, now))
            conn.commit()

        return {"workspace_id": workspace_id, "name": name, "root_path": root_path}

    def get(self, workspace_id: str) -> dict | None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM projects WHERE workspace_id = ?", (workspace_id,)
            ).fetchone()
        if not row:
            return None
        return dict(row)

    def list_all(self) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM projects ORDER BY last_opened DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def remove(self, workspace_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM projects WHERE workspace_id = ?", (workspace_id,)
            )
            conn.commit()
        return cursor.rowcount > 0

    def get_root_path(self, workspace_id: str) -> str | None:
        proj = self.get(workspace_id)
        return proj["root_path"] if proj else None
