import json
import os
import socket
import sys
from dataclasses import dataclass, field
from pathlib import Path


def get_global_dir() -> str:
    override = os.environ.get("CODE880WEB_GLOBAL_DIR", "").strip()
    if override:
        return override
    return os.path.join(os.environ.get("LOCALAPPDATA", ""), "Code880Web")


@dataclass
class InstallInfo:
    install_root: str = ""
    python_path: str = ""
    hub_app_path: str = ""
    worker_app_path: str = ""
    static_path: str = ""
    installed_at: str = ""
    version: str = ""


def read_install_info() -> InstallInfo:
    override_root = os.environ.get("CODE880WEB_INSTALL_ROOT", "").strip()
    if override_root:
        code880web_dir = os.path.join(override_root, "code880web")
        return InstallInfo(
            install_root=override_root,
            python_path=os.environ.get("CODE880WEB_PYTHON_PATH", "").strip() or sys.executable,
            hub_app_path=os.path.join(code880web_dir, "hub", "app.py"),
            worker_app_path=os.path.join(code880web_dir, "worker", "app.py"),
            static_path=os.path.join(code880web_dir, "static"),
            version="dev",
        )

    path = os.path.join(get_global_dir(), "install.json")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"安装信息文件不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return InstallInfo(**{k: data.get(k, "") for k in InstallInfo.__dataclass_fields__})


def find_available_port(start: int = 8800, count: int = 50) -> int:
    for port in range(start, start + count):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("无可用端口")


@dataclass
class HubConfig:
    port: int = 0
    host: str = "127.0.0.1"
    global_dir: str = field(default_factory=get_global_dir)
    version: str = "1.0.0"

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def runtime_path(self) -> str:
        return os.path.join(self.global_dir, "hub_runtime.json")

    @property
    def keys_dir(self) -> str:
        return os.path.join(self.global_dir, "keys")

    @property
    def worker_tokens_dir(self) -> str:
        return os.path.join(self.global_dir, "worker_tokens")

    @property
    def db_path(self) -> str:
        return os.path.join(self.global_dir, "hub.db")

    @property
    def models_path(self) -> str:
        return os.path.join(self.global_dir, "models.json")

    @property
    def log_dir(self) -> str:
        return os.path.join(self.global_dir, "logs")
