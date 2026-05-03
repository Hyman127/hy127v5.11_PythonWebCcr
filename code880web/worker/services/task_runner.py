import asyncio
import json
import os
import signal
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path

from .security import validate_path


class TaskRunner:
    MAX_OUTPUT_LINES = 10000
    DEFAULT_TIMEOUT = 300
    COMPLETED_TTL = 300

    def __init__(self, project_root: str):
        self.project_root = project_root
        self.running_tasks: dict[str, dict] = {}
        self.completed_tasks: dict[str, dict] = {}

    def detect_python(self) -> str:
        venv_python = Path(self.project_root) / ".venv" / "Scripts" / "python.exe"
        if venv_python.exists():
            return str(venv_python)

        config_file = Path(self.project_root) / ".web-workbench" / "config.json"
        if config_file.exists():
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
                python = config.get("python_path")
                if python and os.path.isfile(python):
                    return python

        install_file = os.path.join(
            os.environ.get("LOCALAPPDATA", ""), "Code880Web", "install.json"
        )
        if os.path.isfile(install_file):
            with open(install_file, "r", encoding="utf-8") as f:
                install = json.load(f)
                python = install.get("python_path")
                if python and os.path.isfile(python):
                    return python

        return "python"

    async def start_run(self, file_rel_path: str, args: list[str] | None = None) -> str:
        if not validate_path(self.project_root, file_rel_path):
            raise ValueError("路径不合法")
        if not file_rel_path.endswith(".py"):
            raise ValueError("只能运行 .py 文件")

        target = Path(self.project_root) / file_rel_path
        if not target.exists():
            raise FileNotFoundError(f"文件不存在: {file_rel_path}")

        if self.running_tasks:
            raise RuntimeError("已有任务运行中，请先停止")

        run_id = uuid.uuid4().hex[:8]
        python_path = self.detect_python()

        env = os.environ.copy()
        venv_bin = os.path.join(self.project_root, ".venv", "Scripts")
        if os.path.isdir(venv_bin):
            env["PATH"] = f"{venv_bin};{env.get('PATH', '')}"
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONPATH"] = self.project_root

        cmd_args = args or []
        process = await asyncio.create_subprocess_exec(
            python_path, "-u", str(target), *cmd_args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=self.project_root,
            env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )

        runs_dir = os.path.join(self.project_root, ".web-workbench", "runs")
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
                    self.completed_tasks[run_id] = {
                        "exit_code": exit_code,
                        "elapsed": elapsed,
                        "log_path": task_info.get("log_path"),
                        "file": task_info.get("file"),
                        "finished_at": time.time(),
                    }
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
            os.kill(process.pid, signal.CTRL_BREAK_EVENT)
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
