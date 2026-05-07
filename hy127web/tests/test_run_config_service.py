"""Tests for run configuration validation."""

import json

import pytest

from hy127web.worker.services.run_config_service import RunConfigService


@pytest.fixture
def svc(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('ok')", encoding="utf-8")
    return RunConfigService(str(tmp_path))


def test_save_and_load_config(svc, tmp_path):
    config = {
        "configurations": [
            {
                "name": "main",
                "type": "python",
                "program": "src/main.py",
                "args": ["--demo"],
            }
        ]
    }
    result = svc.save(config)
    assert result["status"] == "ok"
    assert (tmp_path / ".web-workbench" / "launch.json").exists()
    assert svc.load()["configurations"][0]["program"] == "src/main.py"


@pytest.mark.parametrize(
    "payload, message",
    [
        ([], "配置必须是对象"),
        ({"configurations": "bad"}, "configurations 必须是数组"),
        ({"configurations": ["bad"]}, "configuration 必须是对象"),
        ({"configurations": [{"type": "shell", "program": "src/main.py"}]}, "只支持 python"),
        ({"configurations": [{"type": "python", "program": "../x.py"}]}, "program 不合法"),
        ({"configurations": [{"type": "python", "program": "src/main.py", "args": "--bad"}]}, "args 必须是字符串数组"),
    ],
)
def test_save_rejects_invalid_config(svc, payload, message):
    with pytest.raises(ValueError, match=message):
        svc.save(payload)


def test_load_bad_json_returns_empty(svc, tmp_path):
    config_dir = tmp_path / ".web-workbench"
    config_dir.mkdir()
    (config_dir / "launch.json").write_text("{bad", encoding="utf-8")
    assert svc.load() == {"configurations": []}
