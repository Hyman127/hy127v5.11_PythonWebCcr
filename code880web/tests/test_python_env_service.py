"""Tests for PythonEnvService: interpreter discovery and environment inspection."""

import json
import os
import sys

import pytest

from code880web.worker.services.python_env_service import PythonEnvService


@pytest.fixture
def env_svc(tmp_path):
    (tmp_path / ".web-workbench").mkdir(parents=True)
    return PythonEnvService(str(tmp_path))


class TestListInterpreters:
    def test_returns_selected_and_candidates(self, env_svc):
        result = env_svc.list_interpreters()
        assert "selected" in result
        assert "candidates" in result
        assert "config_path" in result
        assert result["config_path"] == ".web-workbench/config.json"

    def test_selected_has_required_fields(self, env_svc):
        result = env_svc.list_interpreters()
        selected = result["selected"]
        assert "path" in selected
        assert "source" in selected
        assert "exists" in selected
        assert "version" in selected

    def test_candidates_exist(self, env_svc):
        result = env_svc.list_interpreters()
        assert len(result["candidates"]) >= 1

    def test_sys_executable_is_candidate(self, env_svc):
        result = env_svc.list_interpreters()
        paths = [c["path"] for c in result["candidates"]]
        assert sys.executable in paths or os.path.normpath(sys.executable) in [os.path.normpath(p) for p in paths]

    def test_fallback_to_python(self, env_svc):
        selected = env_svc.get_selected_interpreter()
        assert selected["path"]


class TestSetProjectInterpreter:
    def test_set_and_read_back(self, env_svc, tmp_path):
        env_svc.set_project_interpreter(sys.executable)
        config_file = tmp_path / ".web-workbench" / "config.json"
        assert config_file.exists()
        with open(config_file, "r", encoding="utf-8") as f:
            config = json.load(f)
        assert config["python_path"] == os.path.normpath(sys.executable)
        assert config["source"] == "user"

    def test_set_invalid_path_raises(self, env_svc):
        with pytest.raises(ValueError):
            env_svc.set_project_interpreter("/nonexistent/python")

    def test_explicit_config_overrides_venv(self, env_svc, tmp_path):
        env_svc.set_project_interpreter(sys.executable)
        result = env_svc.list_interpreters()
        selected = result["selected"]
        assert selected["source"] == ".web-workbench/config.json"
        assert selected["exists"] is True


class TestInspectEnvironment:
    def test_returns_platform_info(self, env_svc):
        info = env_svc.inspect_environment()
        assert "python_path" in info
        assert "python_version" in info
        assert "pip_available" in info
        assert "venv_status" in info
        assert "project_root" in info
        assert info["platform"] == sys.platform

    def test_venv_detected_when_present(self, env_svc, tmp_path):
        if sys.platform == "win32":
            (tmp_path / ".venv" / "Scripts").mkdir(parents=True)
        else:
            (tmp_path / ".venv" / "bin").mkdir(parents=True)
        info = env_svc.inspect_environment()
        assert info["venv_status"] != "none"
