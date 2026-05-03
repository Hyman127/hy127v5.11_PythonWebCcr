import shutil
import uuid
from pathlib import Path

import pytest


@pytest.fixture
def tmp_path(request):
    """Workspace-local tmp_path replacement.

    Some locked-down Windows profiles deny access to pytest's default temp root.
    Keeping test scratch space inside the writable project directory makes the
    test suite deterministic for this portable workstation project.
    """
    root = Path(__file__).resolve().parents[2] / ".test-tmp"
    root.mkdir(exist_ok=True)
    prefix = "".join(c if c.isalnum() else "_" for c in request.node.name)[:40]
    path = root / f"{prefix}-{uuid.uuid4().hex[:8]}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
