import json
import os
import socket
import sys
from dataclasses import dataclass, field
from pathlib import Path


def first_env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def get_global_dir() -> str:
    override = first_env("HY127WEB_GLOBAL_DIR", "CODE880WEB_GLOBAL_DIR")
    if override:
        return override

    localappdata = os.environ.get("LOCALAPPDATA", "").strip()
    if localappdata:
        hy127_dir = os.path.join(localappdata, "Hy127Web")
        code880_dir = os.path.join(localappdata, "Code880Web")
        if os.path.exists(hy127_dir):
            return hy127_dir
        return code880_dir

    state_home = os.environ.get("XDG_STATE_HOME", "").strip()
    if not state_home:
        state_home = os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(state_home, "hy127web")


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
    override_root = first_env("HY127WEB_INSTALL_ROOT", "CODE880WEB_INSTALL_ROOT")
    if override_root:
        hy127web_dir = os.path.join(override_root, "hy127web")
        python_path = first_env("HY127WEB_PYTHON_PATH", "CODE880WEB_PYTHON_PATH") or sys.executable
        return InstallInfo(
            install_root=override_root,
            python_path=python_path,
            hub_app_path=os.path.join(hy127web_dir, "hub", "app.py"),
            worker_app_path=os.path.join(hy127web_dir, "worker", "app.py"),
            static_path=os.path.join(hy127web_dir, "static"),
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
