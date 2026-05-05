"""Tests for persisted TaskRunner run history."""

from code880web.worker.services.task_runner import TaskRunner


def test_run_history_reads_persisted_metadata(tmp_path):
    runner = TaskRunner(str(tmp_path))
    runs_dir = tmp_path / ".web-workbench" / "runs"
    runs_dir.mkdir(parents=True)
    (runs_dir / "deadbeef.log").write_text("ok", encoding="utf-8")
    runner._write_run_metadata(
        "deadbeef",
        {
            "file": "src/main.py",
            "exit_code": 0,
            "elapsed": 1.2,
            "finished_at_iso": "2026-05-05T10:00:00",
        },
    )

    runs = runner.get_run_history()

    assert runs[0]["run_id"] == "deadbeef"
    assert runs[0]["file"] == "src/main.py"
    assert runs[0]["exit_code"] == 0
    assert runs[0]["log_path"] == ".web-workbench/runs/deadbeef.log"


def test_run_history_includes_legacy_log_without_metadata(tmp_path):
    runner = TaskRunner(str(tmp_path))
    runs_dir = tmp_path / ".web-workbench" / "runs"
    runs_dir.mkdir(parents=True)
    (runs_dir / "cafebabe.log").write_text("legacy", encoding="utf-8")

    runs = runner.get_run_history()

    assert runs[0]["run_id"] == "cafebabe"
    assert runs[0]["file"] == ""
    assert runs[0]["log_path"] == ".web-workbench/runs/cafebabe.log"
