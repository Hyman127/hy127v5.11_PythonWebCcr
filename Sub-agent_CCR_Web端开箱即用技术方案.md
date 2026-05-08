# Sub-agent + CCR Web 端开箱即用技术方案

> 版本：v0.1-web-urgent  
> 日期：2026-05-08  
> 范围：`hy127v5.11_PythonWebCcr` 当前 Web 工作台 + 已有 Sub-agent 模板/渲染器 + Claude Code Router。  
> 目标：把原 `Sub-agent_CCR_多模型开箱即用技术方案.md` 改造成适合本项目 Web 端落地的“先能用、少改动、可继续扩展”版本。

## 1. 总体结论

Web 端不要继续以 `src/sub_agent_ccr_model_config.py` 的 tkinter 桌面工具作为主入口。当前项目已经有 `hy127web` Hub/Worker/静态前端架构，开箱即用版应改为：

```text
启动Web工作台
  -> AI 接入中心
    -> Sub-agent + CCR
      -> 粘贴一个 Provider Key
      -> 一键写 CCR provider 配置
      -> 一键套用角色模型绑定
      -> 渲染 ~/.claude/agents/*.md
      -> Web 提示/执行 ccr restart，用户用 ccr code 进入 Claude Code
```

即用版的默认推荐路径是 **火山方舟 Coding Plan 一个 Key 带多模型**：

| 角色 | 默认模型 |
|------|----------|
| `architect` | `ark_coding_plan,kimi-k2.5` |
| `implementer` | `ark_coding_plan,deepseek-v3.2` |
| `reviewer` | `ark_coding_plan,kimi-k2.5` |
| `tester` | `ark_coding_plan,deepseek-v3.2` |
| `docs-writer` | `inherit` |

## 2. 必须修正的边界

原方案里“主会话始终 Claude 原生、Sub-agent 单独通过 CCR 路由”的表述不适合作为即用验收承诺。CCR 官方 CLI 的基本用法是配置 provider 后通过 `ccr code` 启动 Claude Code，当前 Claude Code 进程的 API 请求由 Router 接管；CCR 配置里的模型格式是 `provider,model`。

因此 Web 即用版采用下面的边界：

| 模式 | 即用版处理 |
|------|------------|
| CCR 全会话模式 | **默认支持**。Web 写 CCR config，渲染 Sub-agent `model: provider,model`，启动或提示 `ccr code`。 |
| 主会话原生 Claude，仅 Sub-agent 走 CCR | 不作为即用版承诺。除非后续验证 Claude Code/CCR 支持该混合模式，否则只写成高级实验路径。 |
| 直接 API 对话 | 继续走现有 `hy127web/hub/models_manager.py` 与 `/internal/ai/relay`，不与 Sub-agent+CCR 混在同一个配置表单里。 |

## 3. 当前开发状态

已经具备的能力：

| 模块 | 当前状态 | 可复用方式 |
|------|----------|------------|
| Web Hub | `hy127web/hub/app.py` 已有会话、CSRF、项目注册、模型管理 API | 继续承载 Sub-agent/CCR 配置 API |
| Web Worker | `hy127web/worker/app.py` 按项目启动，持有 `PROJECT_ROOT` | 第 0 阶段不新增职责，后续多项目再拆 |
| 前端 | `hy127web/static/index.html` 已有“AI 接入中心”，当前工作区已加基础 `Sub-agent` 面板 | 补一键 Provider、默认绑定、CCR config/restart |
| 密钥存储 | `ModelsManager` 已把直接 API Key 存到 `global_dir/keys/api_keys.enc`，Windows 优先 DPAPI，非 Windows 退回 base64 开发兜底 | 第 0 阶段复用，不新增 provider key store |
| 直接 API 对话 | `/api/hub/models`、`/api/hub/models/{id}/test`、`DirectHttpRuntime` 已可用 | 保持不动 |
| 运行方式检测 | `/api/hub/runtimes` 已预留 Claude Code/Codex/Qwen/Gemini CLI | CCR 状态接入这里或新增 CCR 状态卡 |
| Sub-agent 模板 | `.claude_templates/agents/*.md` 已有 5 个受管理模板，默认 `model: inherit` | 继续作为渲染源 |
| 绑定文件 | `agent_role_binding.json` 已有默认全 `inherit` 结构 | Web 保存绑定时复用 |
| 渲染器 | `src/sub_agent_ccr_renderer.py` 已能安全更新 `~/.claude/agents` 的 `model` 字段 | Worker API 调用它 |
| 模型清单 | `ai_models_config.json` 已包含 `ark_coding_plan` 与 label | 前端候选列表直接读取 |

当前工作区还出现了几项相关的未提交实现，即用版应顺着这些实现继续推进，而不是重新设计一套入口：

| 模块 | 当前状态 | 评价 |
|------|----------|------|
| Hub Sub-agent API | `hy127web/hub/app.py` 已新增 `/api/hub/subagent/*` 路由 | 可作为即用版主入口 |
| SubAgentManager | `hy127web/hub/subagent_manager.py` 已新增候选查询、绑定保存、渲染、CCR 命令检测 | 可继续扩展 CCR config/restart |
| `web_model` 绑定 | `ai_providers.py` 已给 `validate_binding()` 增加 `web_model` 校验 | 适合 Web 引用 Hub 模型 |
| 前端 Sub-agent 面板 | `hy127web/static/index.html` 已新增顶部 `Sub-agent` 按钮、候选下拉、保存并渲染、已渲染列表 | 可作为最小 UI，继续补一键 Provider 和 CCR restart |
| SubAgentManager 测试 | `hy127web/tests/test_subagent_manager.py` 已新增 | 需要补测试隔离，避免写真实项目根绑定文件 |

未完成但即用版必须补齐：

| 缺口 | 即用版处理 |
|------|------------|
| Web 只有基础 Sub-agent 绑定面板 | 补“一键 Ark Coding Plan Provider”“默认角色绑定”“写 CCR config/restart” |
| Web 没有 CCR config 读写 | 在现有 `SubAgentManager` 或旁路 `CCRConfigManager` 中补齐 |
| Web 没有一键 Provider 初始化 | 复用 `ModelsManager`，用一个 Key 批量创建/更新 Ark Coding Plan 模型条目 |
| CCR 是否安装/运行不可见 | 现有 `detect_ccr()` 只能 `which ccr`，还需版本、config 路径、restart |
| 一键安装器未并入 CCR | 先在 Web 显示“未安装/安装命令”，安装器集成放第二阶段 |

## 4. Web 端用户链路

### 4.1 首次即用链路

```text
1. 双击 重新初始化 V1.24.bat
2. 双击 启动Web工作台.bat
3. 浏览器进入当前项目 Workspace
4. 打开右侧 `Sub-agent` 面板
5. 选择“火山方舟 Coding Plan 即用方案”
6. 粘贴 ARK_CODING_PLAN_API_KEY
7. 点击“测试并保存”
8. 点击“一键启用默认角色绑定”
9. Web 执行：
   - 保存 Key 到 Hub 密钥库
   - 写入 ~/.claude-code-router/config.json provider 配置
   - 写入项目 agent_role_binding.json
   - 调用 renderer 渲染 ~/.claude/agents
   - 提示或执行 ccr restart
10. 用户在终端运行 ccr code，或后续由 Web 提供“启动 Claude Code”按钮
```

### 4.2 日常切换链路

```text
Sub-agent 面板
  -> 调整某个角色的 provider/model
  -> 保存并渲染
  -> ccr restart
```

不需要用户手写 `agent_role_binding.json`、不需要打开 `~/.claude-code-router/config.json`，也不需要理解 `doubao` 与 `ark_coding_plan` endpoint 差异。

## 5. 分层设计

### 5.1 即用版采用 Hub 内聚实现

当前开发已经新增 `hy127web/hub/subagent_manager.py`，并在 `hy127web/hub/app.py` 挂载 `/api/hub/subagent/*`。为了尽快可用，即用版继续采用 **Hub 内聚实现**：

| 层 | 即用版职责 |
|----|------------|
| Hub / `ModelsManager` | 保存直接 API/CCR provider 所需 Key，提供模型 CRUD 和测试 |
| Hub / `SubAgentManager` | 读取候选、读写绑定、调用 renderer、检测 CCR、补写 CCR config |
| Frontend / `index.html` | 在 AI 接入中心提供 Sub-agent+CCR 面板 |
| Worker | 第 0 阶段不新增职责，避免扩大改动面 |

现有 Hub API 可以保留：

| API | 当前用途 |
|-----|----------|
| `GET /api/hub/subagent/status` | CCR 可用性、绑定摘要、已渲染数量 |
| `GET /api/hub/subagent/candidates` | 结合 `ModelsManager` 与 `ai_models_config.json` 返回候选 |
| `GET /api/hub/subagent/binding` | 返回当前绑定 |
| `POST /api/hub/subagent/binding` | 保存绑定并渲染 |
| `GET /api/hub/subagent/agents` | 返回已渲染 agent 的 model 字段 |
| `POST /api/hub/subagent/ccr/test` | 当前只检测 `ccr` 命令是否存在 |

即用版需要在现有 API 上补齐：

| API | 用途 |
|-----|------|
| `POST /api/hub/subagent/quick-ark-coding-plan` | 用一个 Key 批量创建/更新 Ark Coding Plan 的 Hub 模型条目 |
| `POST /api/hub/subagent/quick-enable` | 写默认角色绑定并渲染 |
| `POST /api/hub/subagent/ccr/config` | 根据已配置模型写 `~/.claude-code-router/config.json` |
| `POST /api/hub/subagent/ccr/restart` | 带 env 注入执行 `ccr restart` |

### 5.2 Provider 配置复用 ModelsManager

第 0 阶段不新建 `CCRProviderKeyStore`。原因是 Web 端已经有 `ModelsManager`，并且当前 `SubAgentManager.list_candidates()` 已把 Hub 中已配置模型作为优先候选。

即用版 Provider 初始化规则：

| 操作 | 处理 |
|------|------|
| 用户粘贴 Ark Coding Plan Key | 调用 `ModelsManager.add_model()` 或 `update_model()` 批量创建 `kimi-k2.5`、`deepseek-v3.2` 等模型条目 |
| 多个模型共用一个 Key | 允许；Key 重复保存在各 Hub 模型条目中，先满足即用 |
| `web_model` 绑定 | 前端保存 `hub_model_id`，后端渲染前归一化为 `ccr` 或 `native` |
| CCR config 写入 | 从已配置 Hub 模型推导 provider、baseUrl、models、env_key |
| 后续优化 | 如果重复 Key 存储不可接受，再抽出 provider 级 key store |

### 5.3 Worker 拆分延后

从架构上看，项目级绑定/渲染更适合 Worker；但当前 Web 工作台就是服务本项目目录，且已有 Hub 内 `SubAgentManager`。即用版不迁移到 Worker，避免引入跨进程 API 和路径适配风险。

后续需要支持“一个 Hub 管多个不同项目的 Sub-agent 配置”时，再迁移为：

```text
Hub: Key、CCR config、CCR restart
Worker: 项目 catalog、agent_role_binding.json、renderer
```

### 5.4 Frontend 负责一个即用面板

当前前端是单文件 Vue CDN，不引入构建链。工作区已经在 `hy127web/static/index.html` 加了顶部 `Sub-agent` 按钮和基础绑定面板，即用版继续在这个面板上补齐。

`Sub-agent` 面板最终需要包含三块：

| 区块 | 行为 |
|------|------|
| CCR 状态 | 显示 `ccr` 是否安装、配置路径、是否需要 restart |
| Provider 配置 | 现有面板还缺；补“火山方舟 Coding Plan 一 Key 初始化” |
| 角色绑定 | 已有 5 个角色候选下拉和保存渲染；继续补“一键即用默认绑定” |

即用版不要做复杂多页向导；在右侧 AI 面板中完成即可。

## 6. CCR 配置结构

CCR 官方当前配置文件路径是：

```text
~/.claude-code-router/config.json
```

即用版写入 provider 时使用 env 变量引用，不写明文 Key：

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

兼容策略：

| 项 | 规则 |
|----|------|
| 字段名 | 写入使用 `name/baseUrl/apiKey/models`；读取时兼容旧示例里的 `NAME/HOST/APIKEY/MODELS` |
| `apiKey` | 只写 `$ENV_KEY`，不写真实 Key |
| `Router.default` | 如果不存在，即用版写成第一个可用模型；如果用户已有值，默认不覆盖，除非用户勾选“设为 CCR 默认模型” |
| 备份 | 每次写入前生成 `config.hy127.backup.<timestamp>.json` |
| 重启 | 写入后状态标记为“需要重启 CCR” |

## 7. Key 存储与注入

### 7.1 即用版复用 ModelsManager 密钥库

`ai_providers.py` 里已有 Windows 凭据管理器函数，但它是桌面工具历史路径。当前 Web 端已经使用 `ModelsManager` 保存 API Key：

```text
Hy127Web global_dir/
  keys/
    api_keys.enc
```

即用版不新增第二套 provider key store。Ark Coding Plan 的“一 Key 多模型”通过批量创建 Hub 模型条目实现：

```text
Ark Coding Plan Key
  -> Hub model: Ark Kimi K2.5 / kimi-k2.5
  -> Hub model: Ark DeepSeek V3.2 / deepseek-v3.2
  -> Hub model: Ark Doubao Seed Code / doubao-seed-code-preview-latest
```

限制是同一个 Key 会以多个模型条目保存多份。这个取舍能最快接上现有 `/api/hub/models`、`test_model()`、`web_model` 候选逻辑。后续如果要做更干净的 provider 级配置，再新增 `ccr_provider_keys.enc`。

### 7.2 CCR env 注入

保存 provider 后：

```text
ark_coding_plan -> env_key ARK_CODING_PLAN_API_KEY
```

执行 `ccr restart` 时，Hub 从密钥库读取真实 Key，构造环境变量：

```text
ARK_CODING_PLAN_API_KEY=<真实 Key>
```

然后启动/重启 CCR。这样 `config.json` 只含 `$ARK_CODING_PLAN_API_KEY`。

限制：如果用户在外部终端自行执行 `ccr restart`，外部终端没有 Hub 注入的 env，CCR 可能读不到 Key。即用版 UI 必须提供“通过 Web 重启 CCR”按钮，并把外部手工命令写成高级说明。

## 8. 绑定与渲染

项目根 `agent_role_binding.json` 保持现有结构：

```json
{
  "version": 1,
  "updated_at": "2026-05-08T10:30:00",
  "agents": {
    "architect":   { "mode": "ccr", "provider": "ark_coding_plan", "model": "kimi-k2.5" },
    "implementer": { "mode": "ccr", "provider": "ark_coding_plan", "model": "deepseek-v3.2" },
    "reviewer":    { "mode": "ccr", "provider": "ark_coding_plan", "model": "kimi-k2.5" },
    "tester":      { "mode": "ccr", "provider": "ark_coding_plan", "model": "deepseek-v3.2" },
    "docs-writer": { "mode": "inherit", "model": "inherit" }
  }
}
```

渲染结果：

```text
architect.md    -> model: ark_coding_plan,kimi-k2.5
implementer.md  -> model: ark_coding_plan,deepseek-v3.2
reviewer.md     -> model: ark_coding_plan,kimi-k2.5
tester.md       -> model: ark_coding_plan,deepseek-v3.2
docs-writer.md  -> model: inherit
```

即用版继续写用户级目录 `~/.claude/agents`，因为当前 `src/sub_agent_ccr_renderer.py` 已经实现并有保护逻辑。项目级 `.claude/agents` 可作为后续增强，暂不扩大范围。

## 9. 前端交互草图

```text
AI 接入中心 / 设置
┌─────────────────────────────────────────────┐
│ [直接 API 模型] [Sub-agent + CCR]            │
├─────────────────────────────────────────────┤
│ CCR: 已安装 1.x.x / 服务需重启               │
│ 配置: ~/.claude-code-router/config.json      │
│                      [通过 Web 重启 CCR]     │
├─────────────────────────────────────────────┤
│ 即用 Provider                                │
│ 服务商: 火山方舟 Coding Plan                 │
│ Endpoint: https://ark.../api/coding/v3       │
│ API Key: [****************] [测试并保存]     │
├─────────────────────────────────────────────┤
│ 角色绑定                                    │
│ architect    [火山方舟 CP] [Kimi K2.5]       │
│ implementer  [火山方舟 CP] [DeepSeek V3.2]  │
│ reviewer     [火山方舟 CP] [Kimi K2.5]       │
│ tester       [火山方舟 CP] [DeepSeek V3.2]  │
│ docs-writer  [继承]        [-]              │
│        [一键即用默认绑定] [保存并渲染]        │
└─────────────────────────────────────────────┘
```

状态提示必须明确：

| 状态 | 提示 |
|------|------|
| `ccr` 未安装 | “未检测到 ccr。请先安装 `@musistudio/claude-code-router`，或运行新版一键安装器。” |
| Provider 未保存 Key | “先保存 Provider Key 后才能绑定该 provider。” |
| 已写 config 未重启 | “CCR 配置已更新，需要通过 Web 重启 CCR 后生效。” |
| 渲染成功 | “已渲染到 `~/.claude/agents`，请在 `ccr code` 会话中使用。” |
| 外部终端限制 | “直接在外部终端重启 CCR 可能缺少 Web 密钥库注入的环境变量。” |

## 10. 实施顺序

### 第 0 阶段：Web 即用闭环

- [x] 新增 `hy127web/hub/subagent_manager.py`（当前工作区已有）
- [x] Hub API：status、candidates、binding、agents、ccr/test（当前工作区已有）
- [x] `ai_providers.py` 支持 `web_model` 校验（当前工作区已有）
- [x] 新增 `hy127web/tests/test_subagent_manager.py`（当前工作区已有）
- [ ] 修正 SubAgentManager 测试隔离，避免测试写真实项目根 `agent_role_binding.json`
- [x] 前端增加基础 `Sub-agent` 面板（当前工作区已有）
- [ ] 前端补 Ark Coding Plan 一键 Provider、默认绑定、CCR config/restart 状态
- [ ] 默认支持 `ark_coding_plan` 即用方案：一个 Key 批量创建/更新 Hub 模型
- [ ] 写 CCR config 时只写 `$ENV_KEY`
- [ ] Hub API：CCR config 写入、CCR restart、env 注入
- [x] 保存绑定并调用现有 renderer（当前工作区已有）
- [ ] 手工验证：保存 Key -> 写 config -> 渲染 agents -> Web 重启 CCR -> `ccr code`

### 第 1 阶段：安装器并入 CCR

- [ ] `src/一键安装卸载.py` 默认安装 Node.js/CCR 或检测并提示
- [ ] 安装器 summary 增加 CCR PASS/WARN
- [ ] `重新初始化 V1.24.ps1` 增加 CCR 检测，不阻断初始化
- [ ] `启动Web工作台.ps1` 启动后显示 CCR 状态

### 第 2 阶段：体验增强

- [ ] 支持 Moonshot、DeepSeek、Qwen 等 provider 的 Web 配置
- [ ] 支持项目级 `.claude/agents` 输出选项
- [ ] 支持 Web 启动 `ccr code` 或生成一键启动脚本
- [ ] 支持 CCR config 冲突对比和回滚
- [ ] 支持导出脱敏诊断包

## 11. 验收标准

### 即用功能验收

1. 打开 Web 工作台后，可在 AI 接入中心看到 `Sub-agent + CCR` 面板。
2. 未安装 `ccr` 时，Web 能明确显示未安装状态，不影响直接 API 对话。
3. 保存 `ark_coding_plan` Key 后，Key 不出现在 `models.json`、`agent_role_binding.json`、agent 模板或 CCR config 明文中。
4. `~/.claude-code-router/config.json` 中存在 `ark_coding_plan` provider，`apiKey` 为 `$ARK_CODING_PLAN_API_KEY`。
5. 点击“一键即用默认绑定”后，`agent_role_binding.json` 更新为默认角色分配。
6. 点击“保存并渲染”后，`~/.claude/agents/*.md` 受管理 agent 的 `model` 字段正确。
7. Web 能提示或执行 `ccr restart`，并说明外部终端 env 注入限制。
8. 用户通过 `ccr code` 进入 Claude Code 后，可以显式调用 `architect`、`implementer` 等 Sub-agent。

### 安全验收

1. Hub API 不返回明文 Key，只返回脱敏值或 `configured: true`。
2. Worker 不接收、不保存、不打印 API Key。
3. CCR config 不写真实 Key。
4. 写 CCR config 前自动备份。
5. renderer 不覆盖无 `hy127_managed` 的用户自定义 agent。
6. 日志不打印 Key、请求 Authorization header 或完整 provider 响应。

### 回归验收

1. 现有 `/api/hub/models` 直接 API 模型管理不受影响。
2. 现有 AI 对话仍可使用直接 API 模型。
3. 现有文件树、运行、Git、预览功能不受影响。
4. `hy127web/tests/test_models_manager.py` 继续通过。

## 12. 与原方案的取舍

| 原方案点 | Web 即用版处理 |
|----------|----------------|
| tkinter 两步向导 | 降级为开发/兜底工具；用户主入口迁移到 Web |
| `ai_providers.py` 扩展 CCR 写入 | 不作为 Web 主路径；Web 延续当前 `hy127web/hub/subagent_manager.py` |
| Windows 凭据管理器目标名 `HY127.AIProviders:*` | 第 0 阶段复用 Web `ModelsManager` 的 `api_keys.enc` |
| “主会话原生 Claude，只 Sub-agent 走 CCR” | 不作为即用承诺；默认用 CCR 全会话模式 |
| 一键安装器默认安装 CCR | 保留为第 1 阶段；第 0 阶段先检测并提示 |
| 修改 `~/.claude/settings.json` | 继续不做 |
| 删除用户 agent | 继续不做 |

## 13. 外部依据

- Claude Code Router 官方文档说明 `ccr` 使用 `~/.claude-code-router/config.json`，支持 `ccr code`、`ccr restart`，配置中 provider/model 路由格式为 `provider,model`。  
  https://musistudio.github.io/claude-code-router/docs/cli/intro/  
  https://musistudio.github.io/claude-code-router/docs/cli/config/basic/
- Claude Code Subagents 文档说明 subagent 是 Markdown + YAML frontmatter，支持 `model` 字段，项目级 `.claude/agents` 优先级高于用户级 `~/.claude/agents`。  
  https://code.claude.com/docs/en/sub-agents
