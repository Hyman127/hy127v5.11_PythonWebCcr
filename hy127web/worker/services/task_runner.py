import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

from .security import validate_path
from .platform_utils import build_popen_kwargs, terminate_process


class TaskRunner:
    MAX_OUTPUT_LINES = 10000
    DEFAULT_TIMEOUT = 300
    COMPLETED_TTL = 300

    def __init__(self, project_root: str):
        self.project_root = project_root
        self.running_tasks: dict[str, dict] = {}
        self.completed_tasks: dict[str, dict] = {}

    def _runs_dir(self) -> str:
        return os.path.join(self.project_root, ".web-workbench", "runs")

    def _run_log_rel_path(self, run_id: str) -> str:
        return f".web-workbench/runs/{run_id}.log"

    def _run_meta_path(self, run_id: str) -> str:
        return os.path.join(self._runs_dir(), f"{run_id}.json")

    def detect_python(self) -> str:
        from .python_env_service import PythonEnvService
        selected = PythonEnvService(self.project_root).get_selected_interpreter()
        path = selected.get("path", "")
        if selected.get("exists") and path:
            return path
        if path:
            return path
        return "python"

    async def start_run(self, file_rel_path: str, args: list[str] | None = None) -> str:
        if not validate_path(self.project_root, file_rel_path):
            raise ValueError("路径不合法")
        ext = Path(file_rel_path).suffix.lower()
        if ext not in (".py", ".bat", ".ps1"):
            raise ValueError("只能运行 .py / .bat / .ps1 文件")

        target = Path(self.project_root) / file_rel_path
        if not target.exists():
            raise FileNotFoundError(f"文件不存在: {file_rel_path}")

        if self.running_tasks:
            raise RuntimeError("已有任务运行中，请先停止")

        run_id = uuid.uuid4().hex[:8]

        env = os.environ.copy()
        if sys.platform == "win32":
            venv_bin = os.path.join(self.project_root, ".venv", "Scripts")
        else:
            venv_bin = os.path.join(self.project_root, ".venv", "bin")
        if os.path.isdir(venv_bin):
            env["PATH"] = f"{venv_bin}{os.pathsep}{env.get('PATH', '')}"
        env["PYTHONIOENCODING"] = "utf-8"

        cmd_args = args or []
        popen_kwargs = build_popen_kwargs()

        if ext == ".bat":
            env["HY127WEB_INSTALL_ROOT"] = self.project_root
            env["HY127WEB_PYTHON_PATH"] = self.detect_python()
            env["HY127WEB_GLOBAL_DIR"] = os.path.join(self.project_root, ".web-workbench", "global")
            process = await asyncio.create_subprocess_exec(
                "cmd.exe", "/c", str(target), *cmd_args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=self.project_root,
                env=env,
                **popen_kwargs,
            )
        elif ext == ".ps1":
            process = await asyncio.create_subprocess_exec(
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(target), *cmd_args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=self.project_root,
                env=env,
                **popen_kwargs,
            )
        else:
            python_path = self.detect_python()
            env["PYTHONUNBUFFERED"] = "1"
            env["PYTHONPATH"] = self.project_root
            process = await asyncio.create_subprocess_exec(
                python_path, "-u", str(target), *cmd_args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=self.project_root,
                env=env,
                **popen_kwargs,
            )

        runs_dir = self._runs_dir()
        os.makedirs(runs_dir, exist_ok=True)
        log_path = os.path.join(runs_dir, f"{run_id}.log")

        self.running_tasks[run_id] = {
            "process": process,
            "file": file_rel_path,
            "pid": process.pid,
            "started_at": datetime.now().isoformat(),
            "log_path": log_path,
            "ws_clients": [],
        }

        return run_id

    async def read_output_and_broadcast(self, run_id: str):
        task = self.running_tasks.get(run_id)
        if not task:
            return

        process = task["process"]
        log_path = task["log_path"]
        output_bytes = 0
        max_output_bytes = self.MAX_OUTPUT_LINES * 200
        start_time = time.time()
        exit_code = -1
        elapsed = 0.0

        with open(log_path, "w", encoding="utf-8") as log_file:
            try:
                while True:
                    remaining = self.DEFAULT_TIMEOUT - (time.time() - start_time)
                    if remaining <= 0:
                        await self._broadcast(run_id, {
                            "type": "run_error",
                            "run_id": run_id,
                            "data": "执行超时，已自动终止\n",
                        })
                        process.kill()
                        break

                    try:
                        chunk = await asyncio.wait_for(
                            process.stdout.read(4096),
                            timeout=min(remaining, 30),
                        )
                    except asyncio.TimeoutError:
                        continue

                    if not chunk:
                        break

                    text = chunk.decode("utf-8", errors="replace")
                    output_bytes += len(chunk)

                    if output_bytes >= max_output_bytes:
                        await self._broadcast(run_id, {
                            "type": "run_error",
                            "run_id": run_id,
                            "data": "\n[输出截断：超过最大输出量限制]\n",
                        })
                        process.kill()
                        break

                    log_file.write(text)
                    log_file.flush()

                    await self._broadcast(run_id, {
                        "type": "run_output",
                        "run_id": run_id,
                        "data": text,
                    })

                exit_code = await process.wait()
                elapsed = round(time.time() - start_time, 1)
                await self._broadcast(run_id, {
                    "type": "run_finished",
                    "run_id": run_id,
                    "exit_code": exit_code,
                    "elapsed": elapsed,
                })

            finally:
                task_info = self.running_tasks.get(run_id)
                if task_info:
                    finished_ts = time.time()
                    finished_iso = datetime.now().isoformat()
                    completed = {
                        "exit_code": exit_code,
                        "elapsed": elapsed,
                        "log_path": task_info.get("log_path"),
                        "file": task_info.get("file"),
                        "finished_at": finished_ts,
                        "finished_at_iso": finished_iso,
                    }
                    self.completed_tasks[run_id] = completed
                    self._write_run_metadata(run_id, completed)
                self._cleanup_expired()
                self.running_tasks.pop(run_id, None)

    async def send_stdin(self, run_id: str, content: str):
        task = self.running_tasks.get(run_id)
        if not task:
            raise ValueError("任务不存在或已结束")
        process = task["process"]
        if process.stdin:
            process.stdin.write((content + "\n").encode("utf-8"))
            await process.stdin.drain()

    async def stop_run(self, run_id: str):
        task = self.running_tasks.get(run_id)
        if not task:
            return
        process = task["process"]
        try:
            terminate_process(process)
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except asyncio.TimeoutError:
                process.kill()
        except ProcessLookupError:
            pass

    def register_ws_client(self, run_id: str, ws):
        task = self.running_tasks.get(run_id)
        if task:
            task["ws_clients"].append(ws)

    def remove_ws_client(self, run_id: str, ws):
        task = self.running_tasks.get(run_id)
        if task and ws in task["ws_clients"]:
            task["ws_clients"].remove(ws)
            if not task["ws_clients"]:
                asyncio.create_task(self.stop_run(run_id))

    async def _broadcast(self, run_id: str, msg: dict):
        task = self.running_tasks.get(run_id)
        if not task:
            return
        dead = []
        for ws in task["ws_clients"]:
            try:
                await ws.send_json(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in task["ws_clients"]:
                task["ws_clients"].remove(ws)

    def _cleanup_expired(self):
        now = time.time()
        expired = [
            rid for rid, info in self.completed_tasks.items()
            if now - info["finished_at"] > self.COMPLETED_TTL
        ]
        for rid in expired:
            del self.completed_tasks[rid]

    def get_completed(self, run_id: str) -> dict | None:
        self._cleanup_expired()
        return self.completed_tasks.get(run_id)

    def _write_run_metadata(self, run_id: str, completed: dict):
        os.makedirs(self._runs_dir(), exist_ok=True)
        meta = {
            "run_id": run_id,
            "file": completed.get("file", ""),
            "exit_code": completed.get("exit_code"),
            "elapsed": completed.get("elapsed"),
            "log_path": self._run_log_rel_path(run_id),
            "finished_at": completed.get("finished_at_iso") or datetime.now().isoformat(),
        }
        try:
            with open(self._run_meta_path(run_id), "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def get_run_history(self, limit: int = 50) -> list[dict]:
        runs_dir = self._runs_dir()
        os.makedirs(runs_dir, exist_ok=True)

        records: dict[str, dict] = {}
        try:
            entries = sorted(
                os.scandir(runs_dir),
                key=lambda e: e.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return []

        for entry in entries:
            if not entry.is_file() or not entry.name.endswith(".json"):
                continue
            run_id = os.path.splitext(entry.name)[0]
            try:
                with open(entry.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            data.setdefault("run_id", run_id)
            data.setdefault("log_path", self._run_log_rel_path(run_id))
            records[run_id] = data

        for entry in entries:
            if len(records) >= limit:
                break
            if not entry.is_file() or not entry.name.endswith(".log"):
                continue
            run_id = os.path.splitext(entry.name)[0]
            if run_id in records:
                continue
            records[run_id] = {
                "run_id": run_id,
                "file": "",
                "exit_code": None,
                "elapsed": None,
                "log_path": self._run_log_rel_path(run_id),
                "finished_at": "",
            }

        def _mtime(record: dict) -> float:
            meta_path = self._run_meta_path(record["run_id"])
            log_path = os.path.join(self._runs_dir(), f"{record['run_id']}.log")
            try:
                return os.path.getmtime(meta_path)
            except OSError:
                try:
                    return os.path.getmtime(log_path)
                except OSError:
                    return 0.0

        return sorted(records.values(), key=_mtime, reverse=True)[:limit]
