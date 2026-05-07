import json
import os
from pathlib import Path

KNOWN_ENTRIES = ["main.py", "src/main.py", "app.py", "src/app.py", "run.py"]


def discover_entrypoints(project_root: str) -> list[dict]:
    results = []

    launch_file = Path(project_root) / ".web-workbench" / "launch.json"
    if launch_file.exists():
        with open(launch_file, "r", encoding="utf-8") as f:
            launch = json.load(f)
        for cfg in launch.get("configurations", []):
            if cfg.get("type") == "fixed_file" and cfg.get("program"):
                full = Path(project_root) / cfg["program"]
                if full.exists():
                    results.append({
                        "name": cfg.get("name", cfg["program"]),
                        "path": cfg["program"],
                        "source": "launch.json",
                    })

    for entry in KNOWN_ENTRIES:
        full = Path(project_root) / entry
        if full.exists():
            already = any(r["path"] == entry for r in results)
            if not already:
                results.append({
                    "name": entry,
                    "path": entry,
                    "source": "auto",
                })

    return results
