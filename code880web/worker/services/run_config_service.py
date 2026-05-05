import json
import os

from .security import validate_path


class RunConfigService:
    CONFIG_REL_PATH = ".web-workbench/launch.json"

    def __init__(self, project_root: str):
        self.project_root = project_root

    def load(self) -> dict:
        config_path = os.path.join(self.project_root, self.CONFIG_REL_PATH)
        if not os.path.isfile(config_path):
            return {"configurations": []}
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {"configurations": []}

    def save(self, config: dict) -> dict:
        configurations = config.get("configurations", [])
        for item in configurations:
            if item.get("type") != "python":
                raise ValueError("当前只支持 python 类型")
            program = item.get("program", "")
            if not validate_path(self.project_root, program) or not program.endswith(".py"):
                raise ValueError("program 不合法")
            args = item.get("args", [])
            if not isinstance(args, list) or not all(isinstance(x, str) for x in args):
                raise ValueError("args 必须是字符串数组")

        config_dir = os.path.join(self.project_root, ".web-workbench")
        os.makedirs(config_dir, exist_ok=True)
        config_path = os.path.join(self.project_root, self.CONFIG_REL_PATH)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return {"status": "ok", "config_file": self.CONFIG_REL_PATH}
