"""Tests for cross-platform process control utilities."""

import subprocess
import sys

from hy127web.worker.services.platform_utils import (
    build_popen_kwargs,
    build_supervisor_kwargs,
    terminate_process,
)


class TestBuildPopenKwargs:
    def test_returns_dict(self):
        result = build_popen_kwargs()
        assert isinstance(result, dict)

    def test_has_expected_keys(self):
        result = build_popen_kwargs()
        if sys.platform == "win32":
            assert "creationflags" in result
        else:
            assert "start_new_session" in result


class TestBuildSupervisorKwargs:
    def test_returns_dict(self):
        result = build_supervisor_kwargs()
        assert isinstance(result, dict)

    def test_windows_has_no_window_flag(self):
        result = build_supervisor_kwargs()
        if sys.platform == "win32":
            assert subprocess.CREATE_NO_WINDOW & result["creationflags"]


class TestTerminateProcess:
    def test_terminate_nonexistent_process(self):
        import subprocess as sp
        proc = sp.Popen([sys.executable, "-c", "exit(0)"])
        proc.wait()
        terminate_process(proc)
