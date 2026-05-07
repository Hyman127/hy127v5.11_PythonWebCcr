"""Tests for project registry (§3.1 of spec)."""

import os
import pytest

from hy127web.hub.registry import ProjectRegistry


@pytest.fixture
def registry(tmp_path):
    db_path = str(tmp_path / "hub.db")
    return ProjectRegistry(db_path)


@pytest.fixture
def project_dir(tmp_path):
    proj = tmp_path / "my_project"
    proj.mkdir()
    return str(proj)


class TestProjectRegistry:
    def test_register_project(self, registry, project_dir):
        result = registry.register(project_dir)
        assert "workspace_id" in result
        assert result["root_path"] == project_dir

    def test_register_same_project_twice(self, registry, project_dir):
        r1 = registry.register(project_dir)
        r2 = registry.register(project_dir)
        assert r1["workspace_id"] == r2["workspace_id"]

    def test_get_project(self, registry, project_dir):
        registered = registry.register(project_dir)
        fetched = registry.get(registered["workspace_id"])
        assert fetched is not None
        assert fetched["root_path"] == project_dir

    def test_get_nonexistent(self, registry):
        assert registry.get("nonexistent") is None

    def test_list_all(self, registry, tmp_path):
        proj_a = tmp_path / "proj_a"
        proj_b = tmp_path / "proj_b"
        proj_a.mkdir()
        proj_b.mkdir()
        registry.register(str(proj_a))
        registry.register(str(proj_b))
        all_projects = registry.list_all()
        assert len(all_projects) == 2

    def test_remove_project(self, registry, project_dir):
        registered = registry.register(project_dir)
        assert registry.remove(registered["workspace_id"]) is True
        assert registry.get(registered["workspace_id"]) is None

    def test_remove_nonexistent(self, registry):
        assert registry.remove("nonexistent") is False

    def test_register_invalid_path_raises(self, registry):
        with pytest.raises(ValueError):
            registry.register("/nonexistent/path/xyz")

    def test_workspace_id_is_deterministic(self, registry, project_dir):
        r1 = registry.register(project_dir)
        wid = r1["workspace_id"]
        registry.remove(wid)
        r2 = registry.register(project_dir)
        assert r2["workspace_id"] == wid
