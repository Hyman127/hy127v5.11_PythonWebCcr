# Sub-agent + CCR Web 端开箱即用技术方案

> 版本：v1.2
> 日期：2026-05-08
> 范围：`hy127web/` FastAPI 应用——在现有 Hub 架构之上，提供 Sub-agent 多模型绑定配置的 Web 管理界面。
> 基础：本方案是 `Sub-agent_CCR_多模型开箱即用技术方案.md`（v1.1）的 Web 端适配版，专注于差异点，复用部分直接引用原方案。
> v1.1 变更：吸收 CCR 使用模式边界、CCR config 写入设计、env 注入运营限制。
> v1.2 变更：将原 5 步手工操作（Provider 配置 → 角色绑定 → 保存渲染 → 写 CCR config → Web 重启）合并为面板内线性向导 + 单个「一键应用」端点，用户路径压缩为 4 步。

---

## 目录

- [1. 适配背景与核心差异](#1-适配背景与核心差异)
- [2. 架构分工（Web 端）](#2-架构分工web-端)
- [3. 复用原方案的部分](#3-复用原方案的部分)
- [4. Provider 配置：复用 ModelsManager](#4-provider-配置复用-modelsmanager)
- [5. 新增：Sub-agent 绑定 API](#5-新增sub-agent-绑定-api)
- [6. 新增：SubAgentManager 模块](#6-新增subagentmanager-模块)
- [7. CCR config 写入设计](#7-ccr-config-写入设计)
- [8. Web 前端面板](#8-web-前端面板)
- [9. 安全边界](#9-安全边界)
- [10. 实施阶段](#10-实施阶段)
- [11. 验收标准](#11-验收标准)

---

## 1. 适配背景与核心差异

### v1.1 原方案的定位

v1.1 是 **Windows 桌面工具链**：
- GUI：tkinter（`src/sub_agent_ccr_model_config.py`）
- 密钥存储：Windows 凭据管理器（`Advapi32.dll`，`CredWriteW/CredReadW`）
- CCR 管理：桌面进程，由一键安装器部署

### Web 端适配的核心替换

| v1.1（桌面）| Web 端（本方案）|
|------------|----------------|
| tkinter GUI | Vue.js SPA 面板（扩展现有 `index.html`）|
| Windows 凭据管理器 | `ModelsManager.api_keys.enc`（现有，DPAPI/base64 按平台自动选择）|
| `src/sub_agent_ccr_model_config.py` 独立脚本 | Hub REST API + 前端面板 |
| `ai_models_config.json` Provider 候选清单 | 沿用（Provider 预置元数据来源不变）|
| Provider 配置步骤（Tab①）| **复用 ModelsManager 现有模型管理**，不新建独立 Provider 存储 |
| 角色绑定步骤（Tab②）| 新增 `/api/hub/subagent/binding` API |
| 渲染步骤 | 新增 `/api/hub/subagent/render` API，内部调用现有 `sub_agent_ccr_renderer.py` |
| CCR 检测：重新初始化脚本 | Hub `/api/hub/subagent/ccr` 端点（运行时检测）|
| 密钥注入 CCR：Windows 环境变量 | CCR 启动由 Worker 进程控制；Hub 写 CCR config endpoint，Key 通过 `subprocess.env` 注入 |

### 什么不变

- `agent_role_binding.json`、`.claude_templates/agents/`、`src/sub_agent_ccr_renderer.py` 完全不变。
- `ai_models_config.json` 预置清单作为 UI 向导的展示数据来源，不变。
- `~/.claude/agents/` 渲染目标目录不变。
- `hy127_managed` frontmatter 机制、原子写入、路径穿越保护不变。

### CCR 使用模式边界

v1.1 原方案将"主会话始终 Claude 原生、仅 Sub-agent 走 CCR"作为默认架构描述。**Web 端即用版不把该混合模式作为验收承诺**，原因是 CCR CLI 当前文档的标准用法是通过 `ccr code` 接管整个 Claude Code 进程，混合路由（主会话原生 + Sub-agent 单独绕过主路由）是否真实支持尚未验证。

Web 端采用以下明确分层：

| 模式 | Web 端处理 |
|------|-----------|
| **CCR 全会话模式（默认支持）** | Hub 写 CCR config，渲染 Sub-agent `model: provider,model`，UI 提示用户通过 `ccr code` 进入 Claude Code |
| 主会话原生 + 仅 Sub-agent 走 CCR（混合模式） | 不作为即用版承诺；若后续验证 Claude Code 支持该混合路由，再作为高级可选路径 |
| 直接 API 对话 | 继续走现有 `ModelsManager` + `/internal/ai/relay`，与 Sub-agent 配置面板完全独立 |

---

## 2. 架构分工（Web 端）

```
浏览器（Vue.js SPA）
  │
  └─ /api/hub/subagent/*  ← 本方案新增路由
  │
Hub（FastAPI，hy127web/hub/app.py）
  │
  ├─ ModelsManager（已有）← Provider 配置和 API Key 存储
  │    └─ api_keys.enc：DPAPI（Windows）/ base64（Linux dev）
  │
  └─ SubAgentManager（新增，hy127web/hub/subagent_manager.py）
       ├─ 读 ai_models_config.json：Provider 候选清单
       ├─ 读/写 agent_role_binding.json：角色绑定持久化
       ├─ 调用 src/sub_agent_ccr_renderer.py：渲染到 ~/.claude/agents/
       ├─ 检测 CCR 可用性（shutil.which）
       └─ 写 CCR config endpoint（不含 Key）
```

### 用户链路 A — 基础绑定版（Phase W1–W3，当前已实现）

```
① 一键安装.exe → Python + uv + VSCode + CCR 就绪
② 解压项目 → 重新初始化 → ~/.claude/agents/ 基础模板就绪
③ 启动 Web 工作台（启动Web工作台.bat）→ 浏览器打开 http://127.0.0.1:88xx
④ 「模型管理」页添加 Provider 模型（已有功能）
⑤ 右上角点击「Sub-agent 配置」面板
   → 为 5 个角色选择模型（已配置模型可选，未配置置灰）
   → 点击「保存并渲染」→ agent frontmatter 写入 ~/.claude/agents/
   → 面板展示渲染结果（created/updated/skipped/errors）
⑥ 手动配置 CCR config（目前无 Web 写入，见 §7）
⑦ 在终端运行 `ccr code` → Sub-agent 多模型路由生效
```

> **验收范围**：W-01 ~ W-10（§11）。W-11 ~ W-23 属目标态，当前未实现。

### 用户链路 B — 完整向导版（Phase W4，目标态）

```
① 一键安装.exe → Python + uv + VSCode + CCR 就绪
② 解压项目 → 重新初始化 → ~/.claude/agents/ 基础模板就绪；启动 Web 工作台
③ 右上角点击「Sub-agent 配置」→ 面板内 3 屏线性向导自动衔接：
   ┌ Step 1 Provider 确认 ─────────────────────────────────────────┐
   │ 面板读取 init-status（GET /api/hub/subagent/init-status）       │
   │ 检查基础模板是否已就绪；展示已配置 Hub 模型，可跳到「模型管理」页  │
   └──────────────────────────────────────────────────────────────┘
   ┌ Step 2 角色绑定 ─────────────────────────────────────────────┐
   │ 为 5 个角色各选一个模型；可一键应用「默认方案」                   │
   │ 确认后点「一键应用」                                             │
   └──────────────────────────────────────────────────────────────┘
   ┌ Step 3 一键应用（后端串行，单端点） ──────────────────────────┐
   │ POST /api/hub/subagent/apply-all 串行执行：                    │
   │   [1] 保存绑定 + 渲染 → ~/.claude/agents/                     │
   │   [2] 写 CCR config → ~/.claude-code-router/config.json       │
   │   [3] 重启 CCR（含 Hub env 注入）                              │
   │ 面板逐步显示各步结果；任一步失败在原位报错，可修正后重试          │
   └──────────────────────────────────────────────────────────────┘
④ 向导完成屏显示「复制命令」按钮 → 复制 `ccr code` 到剪贴板 → 粘贴到终端运行
   ⚠ CCR 重启已由 apply-all 完成（含 Hub env 注入），勿在外部终端手动执行 `ccr restart`
```

> **验收范围**：W-01 ~ W-23（§11）。

---

## 3. 复用原方案的部分

### 直接复用，无需修改

| 文件/模块 | 用途 | 状态 |
|----------|------|------|
| `agent_role_binding.json` | 角色绑定持久化 | ✅ 已存在 |
| `.claude_templates/agents/*.md` | 5 个基础 agent 模板 | ✅ 已存在 |
| `src/sub_agent_ccr_renderer.py` | 渲染 model 字段到 `~/.claude/agents/` | ✅ 已存在 |
| `ai_models_config.json` | Provider + 模型候选清单（含 label、roles） | ✅ 已存在 |
| `ai_providers.py` `list_route_options()` | 返回扁平化 provider/model 列表 | ✅ 已存在 |
| `ai_providers.py` `validate_binding()` | 绑定校验 | ✅ 已存在 |

### 继续在桌面使用的部分（不影响 Web）

- `src/sub_agent_ccr_model_config.py`（tkinter GUI）：桌面用户仍可使用，Web 端不依赖它，两者独立。

---

## 4. Provider 配置：复用 ModelsManager

### 设计决策

Web 端**不新建 Provider 配置存储**。`hy127web/hub/models_manager.py` 中的 `ModelsManager` 已经提供：

- 按 `{name, provider, api_base, model_id}` 存储模型配置
- API Key 加密保存到 `api_keys.enc`（DPAPI/base64 双模式）
- 连通性测试（`test_model`）
- REST API：`/api/hub/models`（GET/POST/DELETE）、`/api/hub/models/{id}/test`

**用户在「模型管理」页添加模型 = 完成了 v1.1 Tab① Provider 配置的等价操作。**

### Hub 与 ai_models_config.json 的关系

`ai_models_config.json` 是**预置候选清单**（面向桌面 CCR 路由），在 Web 端：

1. Sub-agent 面板加载时，读取 `ai_models_config.json` 获得 Provider 元数据（display_name、base_url、requires_ccr 等），用于显示向导提示。
2. 实际绑定目标是 **`ModelsManager` 中已添加的模型**，而不是 `ai_models_config.json` 的条目。
3. 当 `requires_ccr: true` 的 Provider 被选为绑定目标时，Sub-agent 面板额外提示"此模型需要 CCR，当前 CCR 状态：{可用/不可用}"。

### 绑定格式扩展

原 `agent_role_binding.json` 格式保留，新增 `web_model` 模式：

```json
{
  "version": 1,
  "updated_at": "...",
  "agents": {
    "architect": {
      "mode": "web_model",
      "hub_model_id": "a1b2c3d4",
      "ccr_format": "ark_coding_plan,kimi-k2.5"
    },
    "implementer": {
      "mode": "ccr",
      "provider": "deepseek",
      "model": "deepseek-chat"
    },
    "reviewer": {
      "mode": "inherit",
      "model": "inherit"
    }
  }
}
```

| `mode` | 来源 | 说明 |
|--------|------|------|
| `inherit` | 原有 | 使用主会话 Claude 模型 |
| `native` | 原有 | Claude Code native 模型（格式：`model_id`）|
| `ccr` | 原有 | CCR 路由（格式：`provider,model`）|
| `web_model` | **新增** | 引用 Hub `ModelsManager` 中的模型条目；渲染时根据 `ccr_format` 写 frontmatter |

`web_model` 模式渲染规则：
- 如果 `ccr_format` 存在 → frontmatter 写 `model: {ccr_format}`（CCR 路由格式）
- 如果 `ccr_format` 为空 → frontmatter 写 `model: {model_id}`（native 格式）
- `hub_model_id` 仅供 Web UI 回显使用，不写入 frontmatter

> ⚠ **native 渲染仅适用于 Claude 模型 ID**
> Claude Code Sub-agent 的 `model` 字段官方仅支持：`inherit`、Claude 模型别名（`opus/sonnet/haiku`）、完整 Claude model ID（如 `claude-opus-4-7-20251101`）。
> OpenAI、DeepSeek、Ark 等第三方模型 ID 若写成 native 格式（`ccr_format` 为空），Claude Code **不会识别**，Sub-agent 将无法调用。
> **规则：所有第三方 provider 的模型都必须通过 CCR 路由，`ccr_format` 不得为空。**
> 若用户在 ModelsManager 中添加了非 Claude provider（如直接 OpenAI），Web 端应在绑定时提示"此 provider 需要 CCR 路由，请确认 ccr_format 已填写"，并在 validate_agents 中做强校验。

### 当前 ModelsManager 与 Provider 配置的差距

"模型管理页添加模型 = Provider 配置完成"在当前实现中**尚不完全成立**，存在以下两个缺口：

**缺口 1 — UI 缺少预置 Provider 选项**：当前模型管理 UI（`index.html` 模型管理区）没有 `ark_coding_plan` 等预置 provider 的快速填充入口，用户需要手动填写 provider 名称、base URL。建议 Phase W4 补充"一键 Ark Coding Plan 初始化"快捷入口，预填 `baseUrl` 和环境变量名。

**缺口 2 — Key 按模型 ID 存储，不按 Provider**：`ModelsManager` 的 Key 以随机 8 位 model ID 为索引（`models_manager.py:88`），不是以 `provider` 为键。`write_ccr_config` 在读取 Key 时需要按 `provider` 聚合同 provider 的多条记录。当同 provider 存在多条记录且 API Key 不一致时，规则为：取 `model_id == provider 的默认模型` 的 Key；若无匹配，取第一条。Phase W4 需明确该规则并在实现中约束。

---

## 5. 新增：Sub-agent 绑定 API

在 `hy127web/hub/app.py` 新增以下路由，全部挂载在 `/api/hub/subagent/` 前缀下：

### 5.1 端点一览

```
GET  /api/hub/subagent/init-status
     → 检测 ~/.claude/agents/ 中是否存在 hy127_managed 文件
     → 返回 { "ready": bool, "managed_count": int, "message": "..." }
     → 用于向导 Step 1 入口前提检查（基础模板是否已通过重新初始化就绪）

GET  /api/hub/subagent/status
     → 返回 CCR 可用状态、已渲染 agent 数量、当前绑定摘要

GET  /api/hub/subagent/candidates
     → 从 ai_models_config.json 读取候选 Provider/模型列表
     → 结合 ModelsManager 标记"已配置/未配置"状态
     → 结合 CCR 状态标记"可路由/不可路由"

GET  /api/hub/subagent/binding
     → 返回 agent_role_binding.json 当前内容

POST /api/hub/subagent/binding
     body: { "agents": { "architect": {...}, ... } }
     → 校验绑定合法性
     → 写 agent_role_binding.json（原子写入）
     → 调用 sub_agent_ccr_renderer.render()
     → 返回渲染结果 { "created": [...], "updated": [...], "skipped": [...], "errors": [...] }

GET  /api/hub/subagent/agents
     → 列出 ~/.claude/agents/ 中 hy127_managed 文件的当前 model 字段
     → 用于前端确认渲染结果

POST /api/hub/subagent/ccr/test
     → 检测 CCR 命令可用性（shutil.which）
     → 可选：发送探测请求验证 CCR 进程健康状态
     → 返回 { "available": bool, "path": "..." }

POST /api/hub/subagent/apply-all               ← 向导「一键应用」专用组合端点
     body: {
       "agents": { "architect": {...}, ... },
       "provider": "ark_coding_plan",           ← 写 CCR config 目标 provider
       "set_as_default": false                  ← 是否覆盖 Router.default
     }
     → 串行执行（任一步失败立即终止后续步骤，errors 非空）：
       [1] 校验 + 保存 agent_role_binding.json + 渲染 ~/.claude/agents/
       [2] 写 ~/.claude-code-router/config.json（备份 + 写入）
       [3] 执行 ccr restart（注入 Hub env）
     → 返回 {
         "binding":     { "created": [...], "updated": [...], "skipped": [...], "errors": [...] },
         "ccr_config":  { "written": bool, "backup_path": "...", "config_path": "..." },
         "ccr_restart": { "ok": bool, "output": "..." },
         "errors":      ["step [N]: <reason>", ...]
       }
     → 幂等设计：已完成步骤不因后续步骤失败而回滚
```

### 5.2 路由鉴权

沿用现有鉴权规则：
- GET 端点：`auth.require_session(request)`
- POST 端点：`auth.require_csrf(request)`

### 5.3 POST /api/hub/subagent/binding 详细流程

```
1. 解析 body.agents
2. 对每个 agent 调用 validate_binding（来自 ai_providers.py）
   - web_model 模式：额外验证 hub_model_id 在 ModelsManager 中存在
3. 写 agent_role_binding.json（原子写入，tmp + os.replace）
4. 调用 src.sub_agent_ccr_renderer.render(
       bindings_path=...,
       agents_dir=Path.home() / ".claude/agents"
   )
5. 返回 RenderResult 序列化
6. 如有错误，HTTP 200 但 body.errors 非空（前端展示警告）
```

---

## 6. 新增：SubAgentManager 模块

文件：`hy127web/hub/subagent_manager.py`（已实现，以下为接口契约）。

> 实现细节以源文件为准，本节只记录契约和关键设计决策，不内嵌实现代码。

### 6.1 公开接口

| 方法 | 签名 | 说明 |
|------|------|------|
| `__init__` | `(models_manager, bindings_path=None)` | `bindings_path` 默认为项目根 `agent_role_binding.json`；测试时传 `tmp_path` 隔离 |
| `list_candidates` | `() → list[dict]` | 返回 inherit + Hub 已配置模型（`web_model`）+ `ai_models_config.json` 未配置候选 |
| `get_binding` | `() → dict` | 读 `agent_role_binding.json`；不存在时返回全 inherit 默认值 |
| `validate_agents` | `(agents: dict) → list[str]` | 每个 agent 校验：`web_model` 验 `hub_model_id`，其余走 `ai_providers.validate_binding` |
| `save_and_render` | `(agents: dict) → RenderResult` | 原子写原始绑定（含 `web_model`）→ 归一化写 render_tmp → 调用 renderer → 删 render_tmp |
| `detect_ccr` | `@staticmethod () → dict` | `shutil.which("ccr")` 检测；返回 `{available, path}` |
| `list_rendered_agents` | `@staticmethod () → list[dict]` | 扫描 `~/.claude/agents/` 中 `hy127_managed` 文件；`HY127_TEST_AGENTS_DIR` 覆盖路径 |
| `get_status` | `() → dict` | 汇总 CCR 状态 + 绑定摘要 + 已渲染 agent 数 |

Phase W4 新增（待实现）：

| 方法 | 签名 | 说明 |
|------|------|------|
| `get_init_status` | `() → dict` | 检测 `~/.claude/agents/` hy127_managed 文件数；返回 `{ready, managed_count, message}` |
| `write_ccr_config` | `(provider_id, set_as_default) → dict` | 备份 + 写 `~/.claude-code-router/config.json`；`apiKey` 只写 `$ENV_VAR` |
| `restart_ccr` | `() → dict` | 从 ModelsManager 读 Key，构造 env，subprocess 执行 `ccr restart` |

### 6.2 关键设计决策

**web_model 回显链路**：`save_and_render` 将**原始绑定**（含 `mode: web_model` 和 `hub_model_id`）写入持久化文件，供 `get_binding` 返回给前端回显。渲染使用归一化后的**临时文件**，用后删除。这样避免了"保存后重读得到 `mode: ccr` 导致前端无法匹配已配置 Hub 模型"的回显断链问题。

**路径硬编码范围**：`_REPO_ROOT = Path(__file__).parent.parent.parent` 仅适用于本仓库单项目部署。多 workspace 场景需迁移到 workspace-scoped API（见 §9 安全边界）。

在 `hub/app.py` 的 `lifespan()` 中初始化：
```python
subagent_mgr = SubAgentManager(models_mgr)
```

---

## 7. CCR config 写入设计

### 7.1 配置文件路径

CCR 使用的配置文件路径为：

```
~/.claude-code-router/config.json
```

### 7.2 写入格式

Hub 写入 provider 时，`apiKey` 只写环境变量占位符，不写真实 Key：

```json
{
  "Providers": [
    {
      "name": "ark_coding_plan",
      "baseUrl": "https://ark.cn-beijing.volces.com/api/coding/v3",
      "apiKey": "$ARK_CODING_PLAN_API_KEY",
      "models": [
        "kimi-k2.5",
        "deepseek-v3.2",
        "doubao-seed-code-preview-latest",
        "ark-code-latest"
      ]
    }
  ],
  "Router": {
    "default": "ark_coding_plan,kimi-k2.5"
  }
}
```

写入规则：

| 项 | 规则 |
|----|------|
| `apiKey` | 只写 `$ENV_KEY_NAME`，不写真实 Key |
| `Router.default` | 如果 key 不存在，写入第一个已配置模型的 `provider,model`；如果已有值，默认不覆盖（除非用户勾选"设为 CCR 默认"）|
| 字段兼容性 | 写入使用 `name/baseUrl/apiKey/models`；读取时兼容旧格式 `NAME/HOST/APIKEY/MODELS` |
| 写前备份 | 每次写入前生成 `config.hy127.backup.<timestamp>.json`，保留最近 3 份 |
| 写入后状态 | 标记"需要重启 CCR"，前端显示提示 |

### 7.3 新增 Hub 端点

在现有 `/api/hub/subagent/*` 基础上补充：

```
POST /api/hub/subagent/ccr/config
     body: { "provider": "ark_coding_plan", "set_as_default": false }
     → 从 ModelsManager 查找该 provider 的已配置模型
     → 写 ~/.claude-code-router/config.json（备份 + 写入）
     → 返回 { "written": bool, "backup_path": "...", "config_path": "..." }

POST /api/hub/subagent/ccr/restart
     → 从 ModelsManager 读取各 provider 的 API Key
     → 构造 env（ARK_CODING_PLAN_API_KEY=xxx, DEEPSEEK_API_KEY=xxx, ...）
     → 执行 ccr restart（subprocess，注入 env）
     → 返回 { "ok": bool, "output": "..." }
```

> **向导集成说明**：上述两个端点可单独调用（高级用户），也可通过向导的
> `POST /api/hub/subagent/apply-all` 组合端点串行触发——前端只需调用一次即可完成
> "保存绑定 → 渲染 → 写 CCR config → 重启 CCR"全流程，无需前端手动协调调用顺序。

### 7.4 env 注入限制（运营风险）

Hub 执行 `ccr restart` 时会将 API Key 通过 `subprocess.env` 注入 CCR 进程。**如果用户在外部终端直接执行 `ccr restart`，该终端没有 Hub 注入的 env，CCR 可能读不到 API Key。**

对应 UI 要求：
- 写入 CCR config 后，面板必须显示"CCR 配置已更新，请通过下方按钮重启 CCR"
- 提供「Web 重启 CCR」按钮（调用 `/api/hub/subagent/ccr/restart`）
- 在高级说明中注明外部终端重启的限制和手工设置 env 的方法

---

## 8. Web 前端面板

### 8.1 入口位置

在现有 `index.html` 顶栏 `.top-bar` 增加「Sub-agent」按钮，点击后在右侧面板（`.right-panel`）渲染 Sub-agent 配置视图，与现有 AI 聊天面板互斥切换。

### 8.2 向导状态机

面板内部维护 `wizardStep`（1–4）：

```
步骤 1 → Provider 确认（init-status + 已配置模型列表）
  └── [下一步] ──→ 步骤 2
步骤 2 → 角色绑定（5 个角色下拉 + 默认方案按钮）
  ├── [上一步] ──→ 步骤 1
  └── [一键应用] ──→ 步骤 3（触发 POST /apply-all，进入 loading）
步骤 3 → 执行进度（逐步展示 binding/ccr_config/ccr_restart 三步结果）
  ├── 有 errors → 显示错误，[重试] 回到步骤 2
  └── 全部成功 ──→ 步骤 4
步骤 4 → 完成屏（复制命令 + 说明）
  └── [重新配置] → 步骤 2（保留已有绑定值）
```

### 8.3 各步骤线框

**步骤 1 — Provider 确认**

```
┌─ Sub-agent 配置 [1/4 Provider 确认] ─────────────────────────┐
│  基础模板状态：● 已就绪（5 个 hy127_managed 文件）              │
│               ○ 未就绪 → 请先运行"重新初始化"脚本              │
│                                                               │
│  已配置 Hub 模型：                                             │
│  ✓ 火山方舟 Kimi K2.5   (ark_coding_plan / kimi-k2.5)        │
│  ✓ DeepSeek Chat        (deepseek / deepseek-chat)            │
│                                                               │
│  需要 CCR 路由的模型会在应用时自动写入 CCR config。             │
│  如需添加更多模型，请前往 [模型管理]（新标签打开）。              │
│                                                               │
│  CCR 状态：● 可用（/usr/local/bin/ccr）                        │
│            ○ 不可用 → 请先安装 CCR                            │
│                                                               │
│                            [刷新]        [下一步 →]           │
└───────────────────────────────────────────────────────────────┘
```

**步骤 2 — 角色绑定**

```
┌─ Sub-agent 配置 [2/4 角色绑定] ──────────────────────────────┐
│  [一键默认方案：全 inherit] [一键 CCR 首选]                    │
│                                                               │
│  architect    [继承主会话（inherit）▼              ]          │
│  implementer  [火山方舟 Kimi K2.5 ▼               ]          │
│  reviewer     [继承主会话（inherit）▼              ]          │
│  tester       [继承主会话（inherit）▼              ]          │
│  docs-writer  [继承主会话（inherit）▼              ]          │
│                                                               │
│  下拉分组：继承 / 已配置模型 / 候选（置灰，需先配置）           │
│                                                               │
│  [← 上一步]                              [一键应用 ▶]        │
└───────────────────────────────────────────────────────────────┘
```

**步骤 3 — 执行进度**

```
┌─ Sub-agent 配置 [3/4 应用中] ────────────────────────────────┐
│  [1] 保存绑定 + 渲染 agents       ✓ created=1 updated=4      │
│  [2] 写入 CCR config              ✓ 已备份 + 写入            │
│  [3] 重启 CCR                     ⟳ 执行中...               │
│                                                               │
│  （任一步失败显示红色 ✗ + 错误信息，其余步骤不执行）            │
│                                        （失败时）[重试]       │
└───────────────────────────────────────────────────────────────┘
```

**步骤 4 — 完成**

```
┌─ Sub-agent 配置 [4/4 完成] ──────────────────────────────────┐
│  ✅ Sub-agent 多模型绑定已就绪                                  │
│                                                               │
│  在终端运行以下命令启动 Claude Code（CCR 全会话模式）：          │
│  ┌─────────────────────────────┐                             │
│  │  ccr code                   │  [复制]                     │
│  └─────────────────────────────┘                             │
│                                                               │
│  ⚠ 注意：请勿在外部终端手动执行 ccr restart，                  │
│    那样会绕过 Hub 的 env 注入（API Key 不可用）。               │
│                                                               │
│  architect   → ark_coding_plan,kimi-k2.5                     │
│  implementer → inherit                                        │
│  reviewer    → inherit        （渲染摘要，来自 /agents）       │
│  tester      → inherit                                        │
│  docs-writer → inherit                                        │
│                                                               │
│  [重新配置]                                                    │
└───────────────────────────────────────────────────────────────┘
```

### 8.4 下拉选项分组

```
──── 继承 ────
  继承主会话（inherit）

──── 已配置模型 ────
  [已配置] 火山方舟 Kimi K2.5 (kimi-k2.5)       → web_model mode
  [已配置] DeepSeek Chat (deepseek-chat)          → web_model mode

──── 候选（需先在模型管理页配置）────
  [未配置] Ark DeepSeek V3.2（Coding Plan）       → disabled，CSS 置灰
  [未配置] Moonshot Kimi K2.5                     → disabled，CSS 置灰
```

`[未配置]` 项在 `<option>` 上添加 `disabled` 属性，用户不可选中。

### 8.5 Vue 响应式状态

```javascript
// 向导核心状态（挂载在现有 Vue app 实例上）
subagent: {
  wizardStep: 1,              // 1–4
  initStatus: null,           // GET /init-status 返回
  ccr: { available: false, path: "" },
  candidates: [],             // GET /candidates 返回
  binding: {},                // GET /binding 返回
  selections: {},             // { architect: <candidate_obj>, ... }
  applyResult: null,          // POST /apply-all 返回
  rendered: [],               // GET /agents 返回（步骤 4 渲染摘要）
  loading: false,
  error: "",
}

// 方法
async loadStep1()     → 并发：GET /init-status + GET /candidates + GET /status
async applyAll()      → POST /apply-all，更新 applyResult，跳转步骤 3→4
async refreshRendered() → GET /agents
copyCommand()         → navigator.clipboard.writeText("ccr code")
```

---

## 9. 安全边界

与 v1.1 安全边界完全一致，以下额外说明 Web 端特有项：

| 约束 | Web 端实现 |
|------|-----------|
| API Key 不出现在 JSON 响应中 | ModelsManager 只返回 `api_key_masked`，Hub 路由不透传明文 Key |
| `agent_role_binding.json` 原子写入 | `SubAgentManager.save_and_render()` 使用 tmp + os.replace |
| hy127_managed 保护 | `sub_agent_ccr_renderer.py` 不覆盖非受管理文件（现有机制，不改）|
| 路径穿越保护 | `sub_agent_ccr_renderer.py` 中 `relative_to(agents_dir_resolved)` 检查（现有机制）|
| CSRF 保护 | POST 端点调用 `auth.require_csrf(request)`（沿用现有鉴权）|
| CCR config 不含明文 Key | CCR config 只写 `$ENV_KEY_NAME`；Key 通过 ModelsManager 加密存储，仅在 `ccr restart` 时通过 `subprocess.env` 注入 |
| CCR config 写前备份 | 每次写入 `~/.claude-code-router/config.json` 前生成带时间戳的备份文件 |
| 外部终端 env 注入限制 | 用户在外部终端直接 `ccr restart` 会绕过 Hub env 注入；Web UI 必须提供「Web 重启 CCR」按钮并展示警告说明 |
| 项目根硬编码范围 | `SubAgentManager` 用 `Path(__file__).parent.parent.parent` 定位项目根，仅支持本仓库单项目部署。若 Hub 未来支持多 workspace，绑定/渲染路径需迁移到 workspace-scoped API，不得直接使用此硬编码路径。 |

---

## 10. 实施阶段

### Phase W1 — 后端基础（SubAgentManager + Hub 路由）

**目标**：所有 Sub-agent API 端点可通过 curl/Swagger 调用。

**文件变更**：
- 新建 `hy127web/hub/subagent_manager.py`（SubAgentManager 类）
- 修改 `hy127web/hub/app.py`：lifespan 初始化 `subagent_mgr`，注册 6 个路由
- 新建 `hy127web/tests/test_subagent_manager.py`

**验收**：
1. `GET /api/hub/subagent/status` 返回 `{ "ccr": {...}, "agents_count": 5, "binding": {...} }`
2. `GET /api/hub/subagent/candidates` 返回 >0 条候选（`inherit` + 已配置模型 + 未配置清单）
3. `POST /api/hub/subagent/binding` 保存并渲染，返回 `errors=[]`（测试环境用 `HY127_TEST_AGENTS_DIR`）
4. `agent_role_binding.json` 文件内容与请求体一致
5. `~/.claude/agents/`（或测试目录）中对应文件 model 字段已更新

### Phase W2 — 前端面板

**目标**：Web UI 面板可完整完成角色绑定操作。

**文件变更**：
- 修改 `hy127web/static/index.html`：
  - 顶栏增加「Sub-agent」切换按钮
  - 右侧面板增加 `subagent-view` 组件
  - Vue data/methods 增加 `subagentPanel` 及相关 API 调用

**验收**：
1. 打开工作台，点击「Sub-agent」可正常展示面板
2. 下拉框已配置模型可选、未配置模型置灰
3. 点击「保存并渲染」后显示渲染结果（created/updated/skipped/errors）
4. CCR 状态显示正确（可用/不可用）

### Phase W3 — validate_binding 支持 web_model 模式

**目标**：`ai_providers.py` 的 `validate_binding()` 支持校验 `web_model` 模式绑定。

**文件变更**：
- 修改 `ai_providers.py`：`validate_binding()` 新增 `web_model` 分支，校验 `hub_model_id` 格式合法（8 位 hex）

**验收**：
1. `validate_binding(config, {"mode": "web_model", "hub_model_id": "a1b2c3d4", "ccr_format": "ark_coding_plan,kimi-k2.5"})` 返回 `ValidationResult(ok=True, error="")`
2. `hub_model_id` 缺失时返回 `ValidationResult(ok=False, error="web_model 缺少 hub_model_id")`

### Phase W4 — 向导 UI + apply-all 组合端点 + init-status

**目标**：将 Phase W1–W3 后端能力整合为面板内 4 步线性向导；单次「一键应用」完成全流程闭环。

**文件变更**：
- `hy127web/hub/subagent_manager.py`：
  - 增加 `get_init_status()` 方法（检测 `~/.claude/agents/` hy127_managed 文件数量）
  - 增加 `write_ccr_config(provider_id, set_as_default)` 方法（写 CCR config，含备份）
  - 增加 `restart_ccr()` 方法（subprocess + env 注入）
- `hy127web/hub/app.py`：
  - 注册 `GET /api/hub/subagent/init-status`
  - 注册 `POST /api/hub/subagent/ccr/config`
  - 注册 `POST /api/hub/subagent/ccr/restart`
  - 注册 `POST /api/hub/subagent/apply-all`（串行调用上述三步）
- `hy127web/static/index.html`：
  - 实现 4 步向导状态机（`wizardStep` 1→2→3→4）
  - 步骤 1：init-status 前提检查 + 模型列表
  - 步骤 2：角色绑定下拉 + 默认方案快捷按钮
  - 步骤 3：apply-all 执行进度（逐步展示三子步结果）
  - 步骤 4：完成屏 + `ccr code` 复制按钮 + 渲染摘要 + env 限制说明
- `hy127web/tests/test_subagent_manager.py`：补充 init-status、CCR config 写入、备份、apply-all 相关测试

**验收**：
1. `GET /api/hub/subagent/init-status` 返回 `{ "ready": bool, "managed_count": int }`
2. `POST /api/hub/subagent/ccr/config` 后，`~/.claude-code-router/config.json` 包含对应 provider，`apiKey` 为 `$ENV_KEY_NAME`
3. 原 config 若存在，写入前有带时间戳的备份文件生成
4. `POST /api/hub/subagent/ccr/restart` 后，CCR 以注入 env 重启，响应 `ok: true`，日志不含明文 Key
5. `POST /api/hub/subagent/apply-all` 串行完成三步，`errors=[]` 时前端自动跳转步骤 4
6. 步骤 4 显示「复制 `ccr code`」按钮，点击后命令写入剪贴板
7. 步骤 3 任一子步失败时显示红色错误，停止后续步骤，提供「重试」回到步骤 2
8. 步骤 4 展示外部终端 env 注入限制说明

---

## 11. 验收标准

| 编号 | 场景 | 预期结果 |
|------|------|---------|
| W-01 | 已配置 1 个 Hub 模型，打开 Sub-agent 面板 | 候选列表包含该模型，标注"[已配置]" |
| W-02 | 未配置任何 Hub 模型，打开 Sub-agent 面板 | 候选列表只有 inherit + [未配置]（全部置灰）|
| W-03 | 为 architect 选择已配置 CCR 模型，保存 | `~/.claude/agents/architect.md` frontmatter `model` 字段 = `{provider},{model_id}` |
| W-04 | 为 implementer 选择 inherit，保存 | `implementer.md` frontmatter `model` 字段 = `inherit` |
| W-05 | CCR 可用时 | 面板顶部显示绿点 + 路径 |
| W-06 | CCR 不可用时 | 面板显示警告"CCR 未安装，CCR 路由模型将无法调用" |
| W-07 | ModelsManager 中存在非 CCR 模型（如直接 OpenAI） | 候选列表包含但标注"需 CCR 路由"警告；若 `ccr_format` 为空，保存时 validate_agents 报错，阻止渲染非 Claude ID 进入 frontmatter |
| W-08 | 渲染目标存在用户自定义 agent（无 hy127_managed 字段） | 该 agent 跳过，不覆盖；`skipped` 列表中包含 |
| W-09 | 重复保存相同绑定 | 渲染输出 `updated=0 skipped=5 errors=0`；文件未变化 |
| W-10 | `agent_role_binding.json` 写入中途进程崩溃 | tmp 文件残留，原文件不损坏；下次保存时正常覆盖 |
| — | **以下 W-11 ~ W-23 为目标态（Phase W4），当前未实现** | |
| W-11 | 调用"写入 CCR config"（`ark_coding_plan` 已配置） | `~/.claude-code-router/config.json` 存在对应 provider，`apiKey` 为 `$ARK_CODING_PLAN_API_KEY`，不含真实 Key |
| W-12 | config.json 已存在时写入 | 写入前自动生成带时间戳备份文件 |
| W-13 | 调用"Web 重启 CCR" | CCR 进程以注入 env 重启，响应返回 `ok: true`；日志不含明文 Key |
| W-14 | 在外部终端执行 `ccr restart` | Web 面板仍显示"env 注入限制"说明，告知用户应使用 Web 重启按钮 |
| W-15 | 基础模板未就绪（`~/.claude/agents/` 无 hy127_managed 文件） | 向导步骤 1 显示"未就绪"提示，[下一步] 按钮禁用 |
| W-16 | 基础模板已就绪时进入向导 | 步骤 1 显示 managed_count，[下一步] 可点击 |
| W-17 | 步骤 2 点击「一键默认方案：全 inherit」 | 5 个角色全部重置为 inherit |
| W-18 | 步骤 2 点击「一键 CCR 首选」（已有至少一个 CCR 模型） | 5 个角色全部切换为第一个已配置 CCR 模型 |
| W-19 | 步骤 2 点击「一键应用」，全流程无错误 | 步骤 3 三行结果均显示 ✓，自动跳转步骤 4 |
| W-20 | 步骤 3 子步骤 [2] 写 CCR config 失败 | [2] 显示 ✗ + 错误信息，[3] 不执行，显示「重试」按钮 |
| W-21 | 步骤 4 点击「复制」 | `ccr code` 写入剪贴板，按钮文字短暂变为"已复制" |
| W-22 | 步骤 4 显示渲染摘要 | 5 个角色各自的实际 model 值来自 `GET /agents` |
| W-23 | 步骤 4 显示 env 注入限制说明 | 说明文字包含"勿在外部终端手动执行 ccr restart" |

---

## 附录 A：与 v1.1 原方案对照表

| v1.1 功能点 | Web 端等价实现 | 优先级 |
|------------|--------------|--------|
| Tab① Provider 配置 | ModelsManager 现有「模型管理」（已实现）| 已有 |
| Tab① API Key → Windows 凭据管理器 | ModelsManager `api_keys.enc`（DPAPI/base64，已实现）| 已有 |
| Tab① CCR config endpoint 写入 | `SubAgentManager`（W1）| Phase W1 |
| Tab② 角色绑定 | `POST /api/hub/subagent/binding`（W1）| Phase W1 |
| Tab② 未配置模型灰显 | 候选列表 `configured: false` → 前端 `disabled`（W2）| Phase W2 |
| Tab② 连通性测试 | ModelsManager `/api/hub/models/{id}/test`（已实现）| 已有 |
| 渲染到 `~/.claude/agents/` | `sub_agent_ccr_renderer.render()`，已有，Web 端通过 API 调用（W1）| Phase W1 |
| CCR 可用性检测 | `SubAgentManager.detect_ccr()`（W1）| Phase W1 |
| Windows 凭据管理器 Key 注入 CCR | Web 端：ModelsManager `get_api_key()` 在运行时注入（待 Worker 接入 CCR 时实现）| Phase W3+ |
| 桌面 tkinter GUI | Vue.js 面板（W2）| Phase W2 |

---

> **注**：本方案不影响原桌面工具链（`src/sub_agent_ccr_model_config.py`、重新初始化脚本），两条路径并行存在，用户可根据使用习惯选择桌面或 Web 端完成配置。

---

## 附录 B：外部参考文档

| 文档 | 内容 | 链接 |
|------|------|------|
| CCR CLI 介绍 | `ccr code`、`ccr restart` 命令说明 | https://musistudio.github.io/claude-code-router/docs/cli/intro/ |
| CCR config 格式 | `Providers[]`、`Router` 字段结构，`$ENV_KEY` 用法 | https://musistudio.github.io/claude-code-router/docs/cli/config/basic/ |
| Claude Code Sub-agents | frontmatter 格式、`model` 字段、项目级 `.claude/agents` 优先级 | https://docs.anthropic.com/en/docs/claude-code/sub-agents |
