#!/usr/bin/env python3
"""dev_start_web.py -- 开发环境启动 Hy127 Web 工作台 (Windows / Linux / macOS).

Usage:
    python scripts/dev_start_web.py [--project-root ./]

This script:
  1. Sets HY127WEB_* env vars (and legacy CODE880WEB_* compat vars)
  2. Starts the Hub
  3. Registers the current project
  4. Creates a bootstrap code for browser access
  5. Outputs the access URL (does NOT auto-open a GUI browser)
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import time

PROJECT_ROOT = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
GLOBAL_DIR = os.path.join(PROJECT_ROOT, ".hy127web_global")
HUB_PORT = 8800


def find_free_port(start: int = 8800) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free port found")


def ensure_env():
    os.makedirs(GLOBAL_DIR, exist_ok=True)

    os.environ.setdefault("HY127WEB_INSTALL_ROOT", PROJECT_ROOT)
    os.environ.setdefault("HY127WEB_PYTHON_PATH", sys.executable)
    os.environ.setdefault("HY127WEB_GLOBAL_DIR", GLOBAL_DIR)

    os.environ.setdefault("CODE880WEB_INSTALL_ROOT", PROJECT_ROOT)
    os.environ.setdefault("CODE880WEB_PYTHON_PATH", sys.executable)
    os.environ.setdefault("CODE880WEB_GLOBAL_DIR", GLOBAL_DIR)


def start_hub() -> subprocess.Popen:
    hub_app = os.path.join(PROJECT_ROOT, "code880web", "hub", "app.py")
    if sys.platform == "win32":
        popen_kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
    else:
        popen_kwargs = {"start_new_session": True}

    proc = subprocess.Popen(
        [sys.executable, hub_app],
        cwd=PROJECT_ROOT,
        env=os.environ.copy(),
        **popen_kwargs,
    )
    return proc


def wait_for_hub(port: int, timeout: float = 15) -> bool:
    import urllib.request
    url = f"http://127.0.0.1:{port}/api/hub/identity"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def register_project(port: int, project_root: str) -> dict | None:
    import urllib.request

    launch_token_path = os.path.join(GLOBAL_DIR, "keys", "launch_token")
    for _ in range(30):
        if os.path.exists(launch_token_path):
            with open(launch_token_path, "r") as f:
                launch_token = f.read().strip()
            break
        time.sleep(0.3)
    else:
        print("ERROR: Launch token not found")
        return None

    body = json.dumps({"root_path": project_root}).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/internal/projects/register",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {launch_token}",
        },
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"ERROR registering project: {e}")
        return None


def create_bootstrap_code(port: int) -> str | None:
    import urllib.request

    launch_token_path = os.path.join(GLOBAL_DIR, "keys", "launch_token")
    if not os.path.exists(launch_token_path):
        return None
    with open(launch_token_path, "r") as f:
        launch_token = f.read().strip()

    body = json.dumps({"target": "/"}).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/internal/bootstrap-code",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {launch_token}",
        },
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read().decode("utf-8"))
        return data.get("code")
    except Exception as e:
        print(f"ERROR creating bootstrap code: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Hy127 Web Dev Starter")
    parser.add_argument("--project-root", default=PROJECT_ROOT, help="Project root directory")
    parser.add_argument("--port", type=int, default=0, help="Hub port (0=auto)")
    args = parser.parse_args()

    ensure_env()

    port = args.port or find_free_port(HUB_PORT)
    print(f"[Hy127 Web Dev] Starting on port {port}")

    os.environ["HY127WEB_HUB_PORT"] = str(port)
    os.environ["CODE880WEB_HUB_PORT"] = str(port)

    hub_proc = start_hub()
    print(f"[Hy127 Web Dev] Hub PID: {hub_proc.pid}")

    if not wait_for_hub(port):
        print("ERROR: Hub did not start within timeout")
        hub_proc.kill()
        sys.exit(1)

    print("[Hy127 Web Dev] Hub is ready")

    project = register_project(port, args.project_root)
    if project:
        print(f"[Hy127 Web Dev] Project registered: {project.get('name', '?')} -> {project.get('workspace_id', '?')}")

    code = create_bootstrap_code(port)
    if code:
        print()
        print("=" * 60)
        print(f"  Open in browser:")
        print(f"  http://127.0.0.1:{port}/bootstrap?code={code}")
        print("=" * 60)
        print()

    print("[Hy127 Web Dev] Running. Press Ctrl+C to stop.")
    try:
        hub_proc.wait()
    except KeyboardInterrupt:
        print("\n[Hy127 Web Dev] Shutting down...")
        hub_proc.terminate()
        try:
            hub_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            hub_proc.kill()
        print("[Hy127 Web Dev] Stopped.")


if __name__ == "__main__":
    main()
