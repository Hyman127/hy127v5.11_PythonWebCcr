"""Tests for Worker-side AI context filtering."""

from hy127web.worker.services.ai_service import AIService


def test_context_files_are_filtered_to_project_files(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('ok')", encoding="utf-8")
    svc = AIService(str(tmp_path))

    svc.set_context_files(["src/main.py", "../secret.txt", "missing.py", 123])

    assert svc.get_context_files() == ["src/main.py"]


def test_build_context_revalidates_paths(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('ok')", encoding="utf-8")
    svc = AIService(str(tmp_path))
    svc.set_context_files(["src/main.py"])
    svc._context_files.append("../secret.txt")

    context = svc._build_context()

    assert "src/main.py" in context
    assert "../secret.txt" not in context
