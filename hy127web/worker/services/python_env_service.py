import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from .security import validate_path


class PythonEnvService:
    """Manage Python interpreter discovery, selection, and environment inspection."""

    CONFIG_REL_PATH = ".web-workbench/config.json"

    def __init__(self, project_root: str):
        self.project_root = project_root

    def list_interpreters(self) -> dict:
        candidates: list[dict] = []
        selected = None
        config_path = os.path.join(self.project_root, self.CONFIG_REL_PATH)
        config_interpreter = self._read_config_interpreter()

        if sys.platform == "win32":
            venv_python = os.path.join(self.project_root, ".venv", "Scripts", "python.exe")
        else:
            venv_python = os.path.join(self.project_root, ".venv", "bin", "python")

        def add_candidate(path, source, exists=None):
            if exists is None:
                exists = os.path.isfile(path)
            version = ""
            if exists:
                version = self._get_version(path)
            selected_flag = False
            if config_interpreter and os.path.normpath(path) == os.path.normpath(config_interpreter):
                selected_flag = True
            return {"path": path, "source": source, "exists": exists, "version": version, "selected": selected_flag}

        if config_interpreter:
            exists = os.path.isfile(config_interpreter)
            c = add_candidate(config_interpreter, ".web-workbench/config.json", exists)
            if c["selected"] is not True:
                c["selected"] = True
            selected = {
                "path": config_interpreter,
                "source": ".web-workbench/config.json",
                "exists": exists,
                "version": c["version"],
            }
            candidates.append(c)

        if os.path.isfile(venv_python) and (not config_interpreter or os.path.normpath(venv_python) != os.path.normpath(config_interpreter)):
            c = add_candidate(venv_python, ".venv")
            if not selected:
                selected = {"path": venv_python, "source": ".venv", "exists": True, "version": c["version"]}
            candidates.append(c)

        global_dir = os.environ.get("HY127WEB_GLOBAL_DIR", "").strip() or os.environ.get("CODE880WEB_GLOBAL_DIR", "").strip()
        if not global_dir:
            localappdata = os.environ.get("LOCALAPPDATA", "").strip()
            if localappdata:
                hy127_dir = os.path.join(localappdata, "Hy127Web")
                code880_dir = os.path.join(localappdata, "Code880Web")
                global_dir = hy127_dir if os.path.isdir(hy127_dir) else code880_dir
            else:
                state_home = os.environ.get("XDG_STATE_HOME", "").strip()
                if not state_home:
                    state_home = os.path.join(os.path.expanduser("~"), ".local", "state")
                global_dir = os.path.join(state_home, "hy127web")
        install_file = os.path.join(global_dir, "install.json")
        if os.path.isfile(install_file):
            try:
                with open(install_file, "r", encoding="utf-8") as f:
                    install = json.load(f)
                ipy = install.get("python_path")
                if ipy and os.path.isfile(ipy):
                    already = any(os.path.normpath(c["path"]) == os.path.normpath(ipy) for c in candidates)
                    if not already:
                        c = add_candidate(ipy, "install.json")
                        if not selected:
                            selected = {"path": ipy, "source": "install.json", "exists": True, "version": c["version"]}
                        candidates.append(c)
            except (json.JSONDecodeError, OSError):
                pass

        sys_py = sys.executable
        if sys_py and os.path.isfile(sys_py):
            already = any(os.path.normpath(c["path"]) == os.path.normpath(sys_py) for c in candidates)
            if not already:
                c = add_candidate(sys_py, "sys.executable")
                if not selected:
                    selected = {"path": sys_py, "source": "sys.executable", "exists": True, "version": c["version"]}
                candidates.append(c)

        for name in ("python3", "python"):
            path = shutil.which(name)
            if path:
                already = any(os.path.normpath(c["path"]) == os.path.normpath(path) for c in candidates)
                if not already:
                    c = add_candidate(path, f"shutil.which({name})")
                    if not selected:
                        selected = {"path": path, "source": f"shutil.which({name})", "exists": True, "version": c["version"]}
                    candidates.append(c)
                break

        if not selected:
            selected = {"path": "python", "source": "fallback", "exists": False, "version": ""}

        return {
            "selected": selected,
            "candidates": candidates,
            "config_path": self.CONFIG_REL_PATH,
        }

    def get_selected_interpreter(self) -> dict:
        return self.list_interpreters()["selected"]

    def set_project_interpreter(self, path: str) -> dict:
        if not os.path.isfile(path):
            raise ValueError(f"解释器路径不存在: {path}")
        config_dir = os.path.join(self.project_root, ".web-workbench")
        os.makedirs(config_dir, exist_ok=True)
        config_file = os.path.join(self.project_root, self.CONFIG_REL_PATH)
        config = {}
        if os.path.isfile(config_file):
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except (json.JSONDecodeError, OSError):
                config = {}
        config["python_path"] = os.path.normpath(path)
        config["updated_at"] = datetime.now().isoformat()
        config["source"] = "user"
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return {"status": "ok", "python_path": os.path.normpath(path), "config_file": self.CONFIG_REL_PATH}

    def inspect_environment(self) -> dict:
        py = self.get_selected_interpreter()
        version = py.get("version", "")
        venv_status = "none"
        if sys.platform == "win32":
            venv_bin = os.path.join(self.project_root, ".venv", "Scripts")
        else:
            venv_bin = os.path.join(self.project_root, ".venv", "bin")
        if os.path.isdir(venv_bin):
            venv_status = "active"
        elif os.path.isdir(os.path.join(self.project_root, ".venv")):
            venv_status = "present_no_bin"

        pip_available = False
        if py.get("exists") and py.get("path"):
            try:
                result = subprocess.run(
                    [py["path"], "-m", "pip", "--version"],
                    capture_output=True, text=True, timeout=10,
                )
                pip_available = result.returncode == 0
            except Exception:
                pass

        return {
            "python_path": py.get("path", ""),
            "python_version": version,
            "pip_available": pip_available,
            "venv_status": venv_status,
            "project_root": self.project_root,
            "platform": sys.platform,
            "config_file": self.CONFIG_REL_PATH,
        }

    def _read_config_interpreter(self) -> str | None:
        config_file = os.path.join(self.project_root, self.CONFIG_REL_PATH)
        if os.path.isfile(config_file):
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
                python = config.get("python_path")
                if python:
                    return python
            except (json.JSONDecodeError, OSError):
                pass
        return None

    @staticmethod
    def _get_version(python_path: str) -> str:
        try:
            result = subprocess.run(
                [python_path, "--version"],
                capture_output=True, text=True, timeout=10,
            )
            return result.stdout.strip() or result.stderr.strip()
        except Exception:
            return ""
