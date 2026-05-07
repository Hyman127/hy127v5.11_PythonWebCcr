import logging
import os
import secrets
import shutil
import socket
import stat
import subprocess
import sys
from dataclasses import dataclass, field

from .config import HubConfig, read_install_info

logger = logging.getLogger("hub.supervisor")


@dataclass
class WorkerInfo:
    workspace_id: str
    project_root: str
    port: int
    pid: int
    internal_token: str
    token_file: str
    process: subprocess.Popen
    log_file_handle: object
    log_path: str
    status: str = "running"


class WorkerSupervisor:
    def __init__(self, config: HubConfig):
        self.config = config
        self._workers: dict[str, WorkerInfo] = {}
        self._next_port = 9100

    def _find_free_port(self) -> int:
        for port in range(self._next_port, self._next_port + 100):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("127.0.0.1", port))
                    self._next_port = port + 1
                    return port
                except OSError:
                    continue
        raise RuntimeError("无可用 Worker 端口")

    def start_worker(self, workspace_id: str, project_root: str) -> WorkerInfo:
        if workspace_id in self._workers:
            existing = self._workers[workspace_id]
            if existing.process.poll() is None:
                return existing
            self._cleanup_worker(workspace_id)

        install_info = read_install_info()
        worker_script = install_info.worker_app_path
        python_path = install_info.python_path
        install_root = install_info.install_root
        if not install_root or not os.path.isdir(install_root):
            install_root = os.path.dirname(os.path.dirname(os.path.dirname(worker_script)))

        internal_port = self._find_free_port()
        worker_token = secrets.token_hex(32)

        token_dir = self.config.worker_tokens_dir
        os.makedirs(token_dir, exist_ok=True)
        token_file = os.path.join(token_dir, f"worker_{internal_port}.token")
        with open(token_file, "w") as f:
            f.write(worker_token)
        try:
            os.chmod(token_file, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass

        workbench_dir = os.path.join(project_root, ".web-workbench")
        os.makedirs(workbench_dir, exist_ok=True)
        log_path = os.path.join(workbench_dir, "worker.log")
        self._rotate_log(log_path)
        log_file = open(log_path, "a", encoding="utf-8")

        if sys.platform == "win32":
            popen_kwargs = {
                "creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
            }
        else:
            popen_kwargs = {"start_new_session": True}

        env = os.environ.copy()
        env["CODE880_WORKER_TOKEN_FILE"] = token_file

        process = subprocess.Popen(
            [
                python_path, "-m", "hy127web.worker.app",
                "--port", str(internal_port),
                "--project-root", project_root,
            ],
            cwd=install_root,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=env,
            **popen_kwargs,
        )

        info = WorkerInfo(
            workspace_id=workspace_id,
            project_root=project_root,
            port=internal_port,
            pid=process.pid,
            internal_token=worker_token,
            token_file=token_file,
            process=process,
            log_file_handle=log_file,
            log_path=log_path,
        )
        self._workers[workspace_id] = info
        logger.info("Worker 已启动: workspace=%s port=%d pid=%d", workspace_id, internal_port, process.pid)
        return info

    def stop_worker(self, workspace_id: str):
        info = self._workers.get(workspace_id)
        if not info:
            return
        try:
            info.process.terminate()
            info.process.wait(timeout=10)
        except Exception:
            try:
                info.process.kill()
            except Exception:
                pass
        self._cleanup_worker(workspace_id)
        logger.info("Worker 已停止: workspace=%s", workspace_id)

    def restart_worker(self, workspace_id: str, project_root: str) -> WorkerInfo:
        self.stop_worker(workspace_id)
        return self.start_worker(workspace_id, project_root)

    def get_worker(self, workspace_id: str) -> WorkerInfo | None:
        info = self._workers.get(workspace_id)
        if info and info.process.poll() is not None:
            info.status = "exited"
        return info

    def list_workers(self) -> list[dict]:
        result = []
        for wid, info in self._workers.items():
            poll = info.process.poll()
            result.append({
                "workspace_id": wid,
                "port": info.port,
                "pid": info.pid,
                "status": "running" if poll is None else "exited",
            })
        return result

    def _cleanup_worker(self, workspace_id: str):
        info = self._workers.pop(workspace_id, None)
        if not info:
            return
        try:
            info.log_file_handle.close()
        except Exception:
            pass
        if os.path.exists(info.token_file):
            try:
                os.remove(info.token_file)
            except Exception:
                pass

    def stop_all(self):
        for wid in list(self._workers.keys()):
            self.stop_worker(wid)

    def _rotate_log(self, log_path: str, max_keep: int = 3):
        if not os.path.exists(log_path):
            return
        if os.path.getsize(log_path) < 10 * 1024 * 1024:
            return
        for i in range(max_keep - 1, 0, -1):
            old = f"{log_path}.{i}"
            new = f"{log_path}.{i + 1}"
            if os.path.exists(old):
                if i + 1 >= max_keep:
                    os.remove(old)
                else:
                    shutil.move(old, new)
        if os.path.exists(log_path):
            shutil.move(log_path, f"{log_path}.1")
