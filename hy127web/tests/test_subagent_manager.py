"""
Tests for SubAgentManager (Web 端 Sub-agent 绑定管理器)
"""
import json
import os
from pathlib import Path

import pytest

from hy127web.hub.models_manager import ModelsManager
from hy127web.hub.subagent_manager import AGENT_NAMES, SubAgentManager


# ── 辅助 ──────────────────────────────────────────────────────────────────────

def _make_manager(tmp_path: Path) -> SubAgentManager:
    mm = ModelsManager(str(tmp_path / "models.json"), str(tmp_path / "keys"))
    return SubAgentManager(mm, bindings_path=str(tmp_path / "bindings.json"))


def _make_manager_with_model(tmp_path: Path, provider="openai", model_id="gpt-test") -> tuple:
    mm = ModelsManager(str(tmp_path / "models.json"), str(tmp_path / "keys"))
    model = mm.add_model(
        name="Test Model",
        provider=provider,
        api_base="https://api.example.test/v1",
        api_key="sk-test",
        model_id=model_id,
    )
    mgr = SubAgentManager(mm, bindings_path=str(tmp_path / "bindings.json"))
    return mgr, model


# ── 候选列表 ──────────────────────────────────────────────────────────────────

def test_candidates_always_contains_inherit(tmp_path):
    mgr = _make_manager(tmp_path)
    candidates = mgr.list_candidates()
    assert any(c["mode"] == "inherit" for c in candidates)


def test_candidates_include_configured_hub_model(tmp_path):
    mgr, model = _make_manager_with_model(tmp_path)
    candidates = mgr.list_candidates()
    configured = [c for c in candidates if c.get("hub_model_id") == model["id"]]
    assert len(configured) == 1
    assert configured[0]["configured"] is True
    assert configured[0]["mode"] == "web_model"


def test_candidates_unconfigured_from_config(tmp_path):
    mgr = _make_manager(tmp_path)
    candidates = mgr.list_candidates()
    # ai_models_config.json 有若干预置 provider
    unconfigured = [c for c in candidates if c.get("configured") is False]
    assert len(unconfigured) > 0, "Should have unconfigured candidates from ai_models_config.json"
    for c in unconfigured:
        assert "[未配置]" in c["label"]


def test_candidates_no_duplicate_for_configured_hub_model(tmp_path):
    """已通过 Hub 配置的 (provider,model) 不应在候选列表中重复出现。"""
    mgr, model = _make_manager_with_model(tmp_path, provider="deepseek", model_id="deepseek-chat")
    candidates = mgr.list_candidates()
    # All entries with provider=deepseek + model=deepseek-chat
    matching = [
        c for c in candidates
        if c.get("provider") == "deepseek" and c.get("model") == "deepseek-chat"
    ]
    # Should appear only once (as web_model, not also as unconfigured)
    assert len(matching) == 1


# ── 绑定读写 ──────────────────────────────────────────────────────────────────

def test_get_binding_returns_defaults_when_no_file(tmp_path):
    mgr = _make_manager(tmp_path)
    binding = mgr.get_binding()
    assert binding["version"] == 1
    agents = binding["agents"]
    for name in AGENT_NAMES:
        assert name in agents
        assert agents[name]["mode"] == "inherit"


def test_save_and_render_creates_agent_files(tmp_path, monkeypatch):
    agents_dir = tmp_path / "test_agents"
    monkeypatch.setenv("HY127_TEST_AGENTS_DIR", str(agents_dir))

    mgr = _make_manager(tmp_path)
    agents = {name: {"mode": "inherit", "model": "inherit"} for name in AGENT_NAMES}
    result = mgr.save_and_render(agents)

    assert result.ok, f"Render errors: {result.errors}"
    assert result.created or result.updated or result.skipped

    binding_path = tmp_path / "bindings.json"
    assert binding_path.exists()
    data = json.loads(binding_path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert "updated_at" in data


def test_save_and_render_web_model_ccr(tmp_path, monkeypatch):
    """web_model 模式（CCR provider）应渲染为 provider,model 格式。"""
    agents_dir = tmp_path / "test_agents"
    monkeypatch.setenv("HY127_TEST_AGENTS_DIR", str(agents_dir))

    mgr, model = _make_manager_with_model(tmp_path, provider="deepseek", model_id="deepseek-chat")
    agents = {
        "architect": {
            "mode": "web_model",
            "hub_model_id": model["id"],
            "provider": "deepseek",
            "model": "deepseek-chat",
            "ccr_format": "deepseek,deepseek-chat",
        },
        **{name: {"mode": "inherit", "model": "inherit"} for name in AGENT_NAMES if name != "architect"},
    }
    result = mgr.save_and_render(agents)
    assert result.ok, f"Render errors: {result.errors}"

    # Check rendered frontmatter
    rendered = mgr.list_rendered_agents()
    arch = next((a for a in rendered if a["name"] == "architect"), None)
    assert arch is not None
    assert arch["model"] == "deepseek,deepseek-chat"


def test_save_and_render_preserves_web_model_for_echo(tmp_path, monkeypatch):
    """保存 web_model 绑定后，重读 binding 应仍为 web_model 模式（UI 回显链路）。"""
    agents_dir = tmp_path / "test_agents"
    monkeypatch.setenv("HY127_TEST_AGENTS_DIR", str(agents_dir))

    mgr, model = _make_manager_with_model(tmp_path, provider="deepseek", model_id="deepseek-chat")
    agents = {
        "architect": {
            "mode": "web_model",
            "hub_model_id": model["id"],
            "provider": "deepseek",
            "model": "deepseek-chat",
            "ccr_format": "deepseek,deepseek-chat",
        },
        **{name: {"mode": "inherit", "model": "inherit"} for name in AGENT_NAMES if name != "architect"},
    }
    result = mgr.save_and_render(agents)
    assert result.ok, f"Render errors: {result.errors}"

    reloaded = mgr.get_binding()
    arch = reloaded["agents"]["architect"]
    assert arch["mode"] == "web_model", f"Expected web_model, got {arch['mode']}"
    assert arch["hub_model_id"] == model["id"]


def test_save_and_render_web_model_native(tmp_path, monkeypatch):
    """web_model 模式（Anthropic provider，ccr_format 为空）应渲染为 native model_id。

    只有 Anthropic/Claude 模型可以走 native 路径；第三方 provider 必须走 CCR。
    """
    agents_dir = tmp_path / "test_agents"
    monkeypatch.setenv("HY127_TEST_AGENTS_DIR", str(agents_dir))

    mgr, model = _make_manager_with_model(tmp_path, provider="anthropic", model_id="claude-sonnet-4-6")
    agents = {
        "implementer": {
            "mode": "web_model",
            "hub_model_id": model["id"],
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "ccr_format": "",
        },
        **{name: {"mode": "inherit", "model": "inherit"} for name in AGENT_NAMES if name != "implementer"},
    }
    result = mgr.save_and_render(agents)
    assert result.ok, f"Render errors: {result.errors}"

    rendered = mgr.list_rendered_agents()
    impl = next((a for a in rendered if a["name"] == "implementer"), None)
    assert impl is not None
    assert impl["model"] == "claude-sonnet-4-6"


# ── 绑定校验 ──────────────────────────────────────────────────────────────────

def test_validate_web_model_ccr_provider_requires_ccr_format(tmp_path):
    """requires_ccr provider 的 web_model 绑定，ccr_format 为空时应报错。"""
    mgr, model = _make_manager_with_model(tmp_path, provider="deepseek", model_id="deepseek-chat")
    errors = mgr.validate_agents({
        "architect": {
            "mode": "web_model",
            "hub_model_id": model["id"],
            "ccr_format": "",       # deepseek requires_ccr=True，所以这里应该报错
        }
    })
    # deepseek 在 ai_models_config.json 中是否标了 requires_ccr 决定是否报错；
    # 如果 provider 不在 config 中（requires_ccr 默认 False），则不报错，测试跳过
    import json as _json
    from pathlib import Path as _Path
    config_path = _Path(__file__).resolve().parents[2] / "ai_models_config.json"
    if config_path.exists():
        cfg = _json.loads(config_path.read_text(encoding="utf-8"))
        if cfg.get("providers", {}).get("deepseek", {}).get("requires_ccr", False):
            assert any("ccr_format" in e or "CCR" in e for e in errors), errors


def test_validate_web_model_missing_hub_id(tmp_path):
    mgr = _make_manager(tmp_path)
    errors = mgr.validate_agents({
        "architect": {"mode": "web_model"}
    })
    assert any("hub_model_id" in e for e in errors)


def test_validate_web_model_nonexistent_hub_id(tmp_path):
    mgr = _make_manager(tmp_path)
    errors = mgr.validate_agents({
        "architect": {"mode": "web_model", "hub_model_id": "deadbeef"}
    })
    assert any("不存在" in e for e in errors)


def test_validate_web_model_valid(tmp_path):
    mgr, model = _make_manager_with_model(tmp_path)
    errors = mgr.validate_agents({
        "architect": {"mode": "web_model", "hub_model_id": model["id"], "ccr_format": ""},
    })
    assert errors == []


def test_validate_inherit_always_valid(tmp_path):
    mgr = _make_manager(tmp_path)
    errors = mgr.validate_agents({name: {"mode": "inherit"} for name in AGENT_NAMES})
    assert errors == []


# ── CCR 检测 ──────────────────────────────────────────────────────────────────

def test_detect_ccr_returns_dict(tmp_path):
    mgr = _make_manager(tmp_path)
    result = mgr.detect_ccr()
    assert "available" in result
    assert "path" in result
    assert isinstance(result["available"], bool)


# ── 已渲染 Agent 列表 ─────────────────────────────────────────────────────────

def test_list_rendered_agents_empty_when_dir_missing(tmp_path, monkeypatch):
    nonexistent = tmp_path / "no_such_dir"
    monkeypatch.setenv("HY127_TEST_AGENTS_DIR", str(nonexistent))
    result = SubAgentManager.list_rendered_agents()
    assert result == []


def test_list_rendered_agents_only_hy127_managed(tmp_path, monkeypatch):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    monkeypatch.setenv("HY127_TEST_AGENTS_DIR", str(agents_dir))

    # Write a managed file
    (agents_dir / "architect.md").write_text(
        "---\nname: architect\nhy127_managed: architect-v1.0.0\nmodel: inherit\n---\nbody\n",
        encoding="utf-8",
    )
    # Write a non-managed file
    (agents_dir / "custom.md").write_text(
        "---\nname: custom\n---\nsome custom agent\n",
        encoding="utf-8",
    )

    result = SubAgentManager.list_rendered_agents()
    names = [r["name"] for r in result]
    assert "architect" in names
    assert "custom" not in names


# ── 状态摘要 ──────────────────────────────────────────────────────────────────

def test_get_status_structure(tmp_path, monkeypatch):
    monkeypatch.setenv("HY127_TEST_AGENTS_DIR", str(tmp_path / "agents"))
    mgr = _make_manager(tmp_path)
    status = mgr.get_status()
    assert "ccr" in status
    assert "agents_count" in status
    assert "non_inherit_count" in status
    assert "rendered_count" in status


# ── Phase W4：init-status ────────────────────────────────────────────────────

def test_get_init_status_when_agents_dir_empty(tmp_path, monkeypatch):
    """无 hy127_managed 文件时 ready=False。"""
    agents_dir = tmp_path / "empty_agents"
    agents_dir.mkdir()
    monkeypatch.setenv("HY127_TEST_AGENTS_DIR", str(agents_dir))
    status = SubAgentManager.get_init_status()
    assert status["ready"] is False
    assert status["managed_count"] == 0
    assert "未就绪" in status["message"]


def test_get_init_status_when_all_managed(tmp_path, monkeypatch):
    """全部 5 个 hy127_managed 文件就绪时 ready=True。"""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    monkeypatch.setenv("HY127_TEST_AGENTS_DIR", str(agents_dir))
    for name in AGENT_NAMES:
        (agents_dir / f"{name}.md").write_text(
            f"---\nname: {name}\nhy127_managed: {name}-v1.0.0\nmodel: inherit\n---\nbody\n",
            encoding="utf-8",
        )
    status = SubAgentManager.get_init_status()
    assert status["ready"] is True
    assert status["managed_count"] == 5


def test_get_init_status_partial_ready(tmp_path, monkeypatch):
    """仅有 3/5 文件时 ready=False。"""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    monkeypatch.setenv("HY127_TEST_AGENTS_DIR", str(agents_dir))
    for name in AGENT_NAMES[:3]:
        (agents_dir / f"{name}.md").write_text(
            f"---\nname: {name}\nhy127_managed: {name}-v1.0.0\nmodel: inherit\n---\nbody\n",
            encoding="utf-8",
        )
    status = SubAgentManager.get_init_status()
    assert status["ready"] is False
    assert status["managed_count"] == 3


# ── Phase W4：CCR config 写入 ─────────────────────────────────────────────────

def test_write_ccr_config_creates_file(tmp_path, monkeypatch):
    """write_ccr_config 应在测试目录中生成 config.json（覆盖 HOME）。"""
    ccr_dir = tmp_path / "ccr"
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    ccr_dir.mkdir(parents=True, exist_ok=True)

    mgr = _make_manager(tmp_path)
    # ark_coding_plan 应在 ai_models_config.json 中
    result = mgr.write_ccr_config("ark_coding_plan", set_as_default=False)

    assert result["written"] is True
    config_path = tmp_path / ".claude-code-router" / "config.json"
    assert config_path.exists()

    data = json.loads(config_path.read_text(encoding="utf-8"))
    providers = data.get("Providers", data.get("providers", []))
    ark = next((p for p in providers if p.get("name") == "ark_coding_plan"), None)
    assert ark is not None
    assert ark["apiKey"].startswith("$")
    assert "ARK_CODING_PLAN_API_KEY" in ark["apiKey"]


def test_write_ccr_config_creates_backup(tmp_path, monkeypatch):
    """已存在 config.json 时写入前生成备份。"""
    ccr_dir = tmp_path / ".claude-code-router"
    ccr_dir.mkdir(parents=True, exist_ok=True)
    config_path = ccr_dir / "config.json"
    config_path.write_text('{"old": true}', encoding="utf-8")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    mgr = _make_manager(tmp_path)
    result = mgr.write_ccr_config("ark_coding_plan", set_as_default=False)

    assert result["written"] is True
    assert result["backup_path"] != ""
    assert "config.hy127.backup." in result["backup_path"]
    assert Path(result["backup_path"]).exists()


def test_write_ccr_config_unknown_provider(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    mgr = _make_manager(tmp_path)
    with pytest.raises(ValueError, match="不在 ai_models_config.json"):
        mgr.write_ccr_config("nonexistent_provider_xyz")


# ── Phase W4：CCR 重启 ────────────────────────────────────────────────────────

def test_restart_ccr_no_ccr_binary(tmp_path, monkeypatch):
    """当 ccr 命令不存在时返回 ok=False。"""
    from hy127web.hub.subagent_manager import SubAgentManager as SM
    # 清除 PATH 使 shutil.which 找不到 ccr
    monkeypatch.setattr("shutil.which", lambda x: None)
    result = SM.restart_ccr()
    assert result["ok"] is False
    assert "不可用" in result["output"]


# ── Phase W4：apply-all 流程 ──────────────────────────────────────────────────

def test_apply_all_without_ccr_writes_binding(tmp_path, monkeypatch):
    """apply-all 在无 CCR 时应只完成 step [1] 保存绑定。"""
    agents_dir = tmp_path / "test_agents"
    monkeypatch.setenv("HY127_TEST_AGENTS_DIR", str(agents_dir))

    mgr, model = _make_manager_with_model(tmp_path, provider="deepseek", model_id="deepseek-chat")
    agents = {
        "architect": {
            "mode": "web_model",
            "hub_model_id": model["id"],
            "provider": "deepseek",
            "model": "deepseek-chat",
            "ccr_format": "deepseek,deepseek-chat",
        },
        **{name: {"mode": "inherit", "model": "inherit"} for name in AGENT_NAMES if name != "architect"},
    }

    # 模拟调用 apply-all 的 step [1]
    errors = mgr.validate_agents(agents)
    assert errors == [], f"Validation errors: {errors}"
    result = mgr.save_and_render(agents)
    assert result.ok, f"Render errors: {result.errors}"
    assert "architect" in result.created or "architect" in result.updated

    # 验证绑定文件已持久化
    binding = mgr.get_binding()
    assert binding["agents"]["architect"]["mode"] == "web_model"
