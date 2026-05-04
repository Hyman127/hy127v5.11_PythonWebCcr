import os
import signal
import subprocess
import sys


def build_popen_kwargs() -> dict:
    """Return platform-appropriate subprocess.Popen kwargs for process-group isolation."""
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def build_supervisor_kwargs() -> dict:
    """Return platform-appropriate subprocess.Popen kwargs for headless worker startup."""
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def terminate_process(process):
    """Cross-platform process termination with group cleanup."""
    if process.returncode is not None:
        return
    if sys.platform == "win32":
        try:
            os.kill(process.pid, signal.CTRL_BREAK_EVENT)
        except (ProcessLookupError, OSError):
            pass
    else:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except (ProcessLookupError, OSError):
            pass
