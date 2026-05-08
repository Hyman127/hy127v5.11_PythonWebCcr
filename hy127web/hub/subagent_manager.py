"""
Sub-agent 绑定管理器（Web 端）
==============================
封装候选查询、绑定读写、渲染调用，供 hub/app.py 路由调用。

路径约定（相对于本文件）：
  本文件        → hy127web/hub/subagent_manager.py
  仓库根        → hy127web/../  = 项目根
  ai_models_config.json → 项目根/ai_models_config.json
  agent_role_binding.json → 项目根/agent_role_binding.json
  src/sub_agent_ccr_renderer.py → 项目根/src/sub_agent_ccr_renderer.py
"""

import json
import os
import re
import shutil
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent.parent
_CONFIG_PATH = _REPO_ROOT / "ai_models_config.json"
_BINDINGS_PATH = _REPO_ROOT / "agent_role_binding.json"

# 将仓库根加入 sys.path，使 import ai_providers / src.sub_agent_ccr_renderer 可用
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ai_providers import load_models_config, list_route_options, validate_binding
from src.sub_agent_ccr_renderer import render as _render, RenderResult

AGENT_NAMES = ["architect", "implementer", "reviewer", "tester", "docs-writer"]

_FM_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)


class SubAgentManager:
    """Web 端 Sub-agent 绑定管理器。"""

    def __init__(self, models_manager, bindings_path=None):
        self._mm = models_manager
        self._bindings_path = Path(bindings_path) if bindings_path else _BINDINGS_PATH
        self._config = self._load_config()

    # ── 内部辅助 ─────────────────────────────────────────────────────────────

    @staticmethod
    def _load_config() -> dict:
        if not _CONFIG_PATH.exists():
            return {}
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def _requires_ccr(self, provider_id: str) -> bool:
        providers = self._config.get("providers", {})
        return bool(providers.get(provider_id, {}).get("requires_ccr", False))

    # ── 候选列表 ─────────────────────────────────────────────────────────────

    def list_candidates(self) -> list[dict]:
        """
        返回可用绑定候选列表。

        每项包含：
          mode, label, requires_ccr, configured
          + hub_model_id（来自 ModelsManager 的 ID，web_model 模式）
          + provider, model（ccr/native 格式）
          + ccr_format（渲染到 frontmatter 的 "provider,model" 字符串）
        """
        candidates = [
            {
                "mode": "inherit",
                "label": "继承主会话（inherit）",
                "requires_ccr": False,
                "configured": True,
                "hub_model_id": None,
                "provider": "",
                "model": "inherit",
                "ccr_format": "",
            }
        ]

        # Hub 中已配置的模型优先展示
        for m in self._mm.list_models():
            if not m.get("enabled"):
                continue
            provider_id = m.get("provider", "")
            model_id = m.get("model_id", "")
            requires_ccr = self._requires_ccr(provider_id)
            ccr_format = f"{provider_id},{model_id}" if requires_ccr else ""
            candidates.append(
                {
                    "mode": "web_model",
                    "hub_model_id": m["id"],
                    "label": f"[已配置] {m['name']}（{model_id}）",
                    "provider": provider_id,
                    "model": model_id,
                    "ccr_format": ccr_format,
                    "requires_ccr": requires_ccr,
                    "configured": True,
                }
            )

        # ai_models_config.json 中的候选（未在 Hub 配置的 Provider）
        configured_key = {
            (m.get("provider", ""), m.get("model_id", ""))
            for m in self._mm.list_models()
            if m.get("enabled")
        }
        for opt in list_route_options(self._config):
            key = (opt["provider"], opt["model_id"])
            if key in configured_key:
                continue  # 已通过 ModelsManager 展示，不重复
            candidates.append(
                {
                    "mode": "ccr" if opt["requires_ccr"] else "native",
                    "hub_model_id": None,
                    "label": f"[未配置] {opt['label']}",
                    "provider": opt["provider"],
                    "model": opt["model_id"],
                    "ccr_format": f"{opt['provider']},{opt['model_id']}" if opt["requires_ccr"] else "",
                    "requires_ccr": opt["requires_ccr"],
                    "configured": False,
                }
            )

        return candidates

    # ── 绑定读写 ─────────────────────────────────────────────────────────────

    def get_binding(self) -> dict:
        """加载 agent_role_binding.json；文件不存在返回全 inherit 默认值。"""
        if not self._bindings_path.exists():
            return {
                "version": 1,
                "updated_at": None,
                "agents": {n: {"mode": "inherit", "model": "inherit"} for n in AGENT_NAMES},
            }
        with open(self._bindings_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def validate_agents(self, agents: dict) -> list[str]:
        """
        对每个 agent 绑定进行校验。返回错误描述列表（空列表表示全部合法）。
        """
        errors = []
        for name, binding in agents.items():
            mode = binding.get("mode", "inherit")
            if mode == "web_model":
                hub_id = binding.get("hub_model_id", "")
                if not hub_id:
                    errors.append(f"{name}: web_model 模式缺少 hub_model_id")
                    continue
                model_entry = self._mm.get_model(hub_id)
                if not model_entry:
                    errors.append(f"{name}: hub_model_id {hub_id!r} 不存在")
                    continue
                provider_id = model_entry.get("provider", "")
                if self._requires_ccr(provider_id) and not binding.get("ccr_format", ""):
                    errors.append(
                        f"{name}: provider {provider_id!r} 需要 CCR 路由，ccr_format 不得为空"
                    )
            else:
                vr = validate_binding(self._config, binding)
                if not vr.ok:
                    errors.append(f"{name}: {vr.error}")
        return errors

    def _normalize_binding_for_render(self, binding: dict) -> dict:
        """
        web_model 模式：转换为 renderer 可识别的格式（ccr 或 native）。
        其他模式直接透传。
        """
        if binding.get("mode") != "web_model":
            return binding
        ccr_format = binding.get("ccr_format", "")
        if ccr_format and "," in ccr_format:
            provider, model = ccr_format.split(",", 1)
            return {"mode": "ccr", "provider": provider, "model": model}
        model = binding.get("model", "")
        if model:
            return {"mode": "native", "model": model}
        return {"mode": "inherit", "model": "inherit"}

    def save_and_render(self, agents: dict) -> RenderResult:
        """
        校验 → 原子保存 agent_role_binding.json（保留 web_model）→ 渲染到 ~/.claude/agents/。
        返回 RenderResult（errors 非空代表部分/全部失败）。

        持久化文件保留原始 web_model 模式（含 hub_model_id），供 UI 回显反查；
        renderer 读取的是归一化后的临时文件（ccr/native），用后删除。
        """
        import datetime

        ts = datetime.datetime.now().isoformat(timespec="seconds")

        # 1. 原子写入原始绑定（保留 web_model，供 UI 回显）
        data = {"version": 1, "updated_at": ts, "agents": agents}
        tmp = str(self._bindings_path) + ".web.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, str(self._bindings_path))

        # 2. 归一化 web_model → ccr/native，写临时文件供 renderer 使用
        normalized = {
            name: self._normalize_binding_for_render(b)
            for name, b in agents.items()
        }
        render_data = {"version": 1, "updated_at": ts, "agents": normalized}
        render_tmp = str(self._bindings_path) + ".render.tmp"
        try:
            with open(render_tmp, "w", encoding="utf-8") as f:
                json.dump(render_data, f, ensure_ascii=False, indent=2)
                f.write("\n")
            return _render(bindings_path=render_tmp)
        finally:
            try:
                os.unlink(render_tmp)
            except OSError:
                pass

    # ── CCR 检测 ─────────────────────────────────────────────────────────────

    @staticmethod
    def detect_ccr() -> dict:
        path = shutil.which("ccr")
        return {"available": path is not None, "path": path or ""}

    # ── 已渲染 Agent 状态 ─────────────────────────────────────────────────────

    @staticmethod
    def list_rendered_agents() -> list[dict]:
        """列出 ~/.claude/agents/ 中 hy127_managed 文件的当前 model 字段。"""
        agents_dir = Path.home() / ".claude" / "agents"
        # 允许测试覆盖
        override = os.environ.get("HY127_TEST_AGENTS_DIR", "").strip()
        if override:
            agents_dir = Path(override)

        result = []
        if not agents_dir.exists():
            return result

        for f in sorted(agents_dir.glob("*.md")):
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            m = _FM_RE.match(text)
            if not m:
                continue
            fields = {}
            for line in m.group(1).splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    fields[k.strip()] = v.strip()
            if not fields.get("hy127_managed", "").startswith(f.stem + "-v"):
                continue
            result.append(
                {
                    "name": f.stem,
                    "model": fields.get("model", "inherit"),
                    "hy127_managed": fields.get("hy127_managed", ""),
                }
            )
        return result

    # ── Phase W4: 初始化状态检查 ─────────────────────────────────────────────

    @staticmethod
    def get_init_status() -> dict:
        """检测 ~/.claude/agents/ 中 hy127_managed 文件是否就绪。"""
        agents = SubAgentManager.list_rendered_agents()
        managed_count = len(agents)
        ready = managed_count >= len(AGENT_NAMES)
        if not ready:
            return {
                "ready": False,
                "managed_count": managed_count,
                "message": f"基础模板未就绪（{managed_count}/{len(AGENT_NAMES)}），请先运行重新初始化脚本",
            }
        return {
            "ready": True,
            "managed_count": managed_count,
            "message": f"已就绪（{managed_count} 个 hy127_managed 文件）",
        }

    # ── Phase W4: CCR config 写入 ─────────────────────────────────────────────

    def write_ccr_config(self, provider_id: str, set_as_default: bool = False, models_manager=None) -> dict:
        """备份 + 写入 ~/.claude-code-router/config.json。

        - apiKey 只写 $ENV_KEY_NAME，不写真实 Key
        - Router.default 若不存在则写入，若已有值且 set_as_default=True 则覆盖
        - 模型列表优先使用 ModelsManager 中已配置的模型；无已配置模型时回退到 ai_models_config.json
        - 写入前生成带时间戳备份，保留最近 3 份
        - 保留已有 config 中的其他顶层字段（无损合并）
        """
        import datetime
        import shutil as _shutil
        import glob as _glob

        ccr_config_dir = Path.home() / ".claude-code-router"
        config_path = ccr_config_dir / "config.json"

        # 读取 ai_models_config.json 获取 provider 元数据
        providers_cfg = self._config.get("providers", {})
        pdata = providers_cfg.get(provider_id)
        if not pdata:
            raise ValueError(f"provider {provider_id!r} 不在 ai_models_config.json 中")

        env_key = pdata.get("env_key", "")
        if not env_key:
            raise ValueError(f"provider {provider_id!r} 缺少 env_key，无法生成 $ENV_KEY_NAME")

        base_url = pdata.get("base_url", "")

        # 模型列表：优先取 ModelsManager 中已配置的模型，回退到 ai_models_config.json 静态列表
        if models_manager is not None:
            configured_models = [
                m.get("model_id", "")
                for m in models_manager.list_models()
                if m.get("enabled") and m.get("provider") == provider_id and m.get("model_id")
            ]
        else:
            configured_models = []
        if configured_models:
            models = configured_models
        else:
            models_raw = pdata.get("models", [])
            models = [
                m["id"] if isinstance(m, dict) and "id" in m else str(m)
                for m in models_raw
            ]

        # 读取现有 config
        existing = {}
        if config_path.exists():
            try:
                raw = config_path.read_text(encoding="utf-8")
                existing = json.loads(raw) if raw.strip() else {}
            except (json.JSONDecodeError, OSError):
                existing = {}

        # 备份
        backup_path = ""
        if config_path.exists():
            ccr_config_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = str(ccr_config_dir / f"config.hy127.backup.{ts}.json")
            _shutil.copy2(str(config_path), backup_path)

            # 清理旧备份，保留最近 3 份
            backups = sorted(
                _glob.glob(str(ccr_config_dir / "config.hy127.backup.*.json"))
            )
            for old in backups[:-3]:
                try:
                    os.unlink(old)
                except OSError:
                    pass

        # 构造 providers 列表（兼容旧格式 NAME/HOST/APIKEY/MODELS 和新格式 name/baseUrl/apiKey/models）
        providers = existing.get("Providers", existing.get("providers", []))
        found = False
        for p in providers:
            p_name = p.get("name", p.get("NAME", ""))
            if p_name == provider_id:
                p["name"] = provider_id
                p["baseUrl"] = base_url
                p["apiKey"] = f"${env_key}"
                p["models"] = models
                for old_key in ("NAME", "HOST", "APIKEY", "MODELS"):
                    p.pop(old_key, None)
                found = True
                break

        if not found:
            providers.append({
                "name": provider_id,
                "baseUrl": base_url,
                "apiKey": f"${env_key}",
                "models": models,
            })

        # Router.default
        router = existing.get("Router", existing.get("router", {}))
        if isinstance(router, dict):
            if "default" not in router or set_as_default:
                first_model = models[0] if models else ""
                router["default"] = f"{provider_id},{first_model}" if first_model else ""
        else:
            router = {"default": ""}

        # 无损合并：基于已有 config 更新 Providers / Router，保留其他顶层字段
        new_config = dict(existing)
        new_config["Providers"] = providers
        new_config["Router"] = router
        # 清理可能的旧格式 key（小写变体不会同时在顶层共存）
        new_config.pop("providers", None)
        new_config.pop("router", None)

        ccr_config_dir.mkdir(parents=True, exist_ok=True)
        tmp = str(config_path) + ".hy127.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(new_config, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, str(config_path))

        return {
            "written": True,
            "backup_path": backup_path,
            "config_path": str(config_path),
        }

    # ── Phase W4: CCR 重启 ────────────────────────────────────────────────────

    @staticmethod
    def restart_ccr(models_manager=None) -> dict:
        """从 ModelsManager 读取 Key，构造 env，subprocess 执行 ccr restart。

        models_manager: ModelsManager 实例，用于读取 api_keys。若为 None 则尝试从全局获取。

        env_key 优先读模型记录，回退到 ai_models_config.json 的 provider 元数据。
        """
        ccr_path = shutil.which("ccr")
        if not ccr_path:
            return {"ok": False, "output": "ccr 命令不可用", "ccr_path": ""}

        # 从 ai_models_config.json 构建 provider→env_key 回退映射
        fallback_env_keys = {}
        if _CONFIG_PATH.exists():
            try:
                with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                for pkey, pdata in cfg.get("providers", {}).items():
                    ek = pdata.get("env_key", "")
                    if ek:
                        fallback_env_keys[pkey] = ek
            except (OSError, json.JSONDecodeError):
                pass

        env = os.environ.copy()
        if models_manager is not None:
            provider_env_added = set()
            for m in models_manager.list_models():
                if not m.get("enabled"):
                    continue
                provider = m.get("provider", "")
                env_key_name = m.get("env_key", "") or fallback_env_keys.get(provider, "")
                if not provider or not env_key_name or provider in provider_env_added:
                    continue
                key = models_manager.get_api_key(m["id"])
                if key:
                    env[env_key_name] = key
                    provider_env_added.add(provider)

        import subprocess
        try:
            proc = subprocess.run(
                [ccr_path, "restart"],
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
            )
            ok = proc.returncode == 0
            return {
                "ok": ok,
                "output": (proc.stdout + proc.stderr).strip()[:2000],
                "ccr_path": ccr_path,
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "output": "ccr restart 超时", "ccr_path": ccr_path}
        except Exception as e:
            return {"ok": False, "output": str(e), "ccr_path": ccr_path}

    # ── 状态摘要 ─────────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        """返回 CCR 状态 + 绑定摘要 + 已渲染 agent 数量。"""
        binding = self.get_binding()
        agents = binding.get("agents", {})
        non_inherit = sum(
            1 for b in agents.values() if b.get("mode", "inherit") != "inherit"
        )
        return {
            "ccr": self.detect_ccr(),
            "binding_updated_at": binding.get("updated_at"),
            "agents_count": len(agents),
            "non_inherit_count": non_inherit,
            "rendered_count": len(self.list_rendered_agents()),
        }
