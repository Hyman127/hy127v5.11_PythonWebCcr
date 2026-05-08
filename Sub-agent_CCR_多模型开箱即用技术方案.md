# Sub-agent + CCR 多模型开箱即用技术方案

> 版本：v1.1
> 日期：2026-05-08
> 范围：`hy127v5.11_multi-orchestration_CCR` 全链路——从一键安装到 Sub-agent 多模型协作开箱即用。
> 本方案融合原 `Sub-agent_CCR打包初始化自动生成开发技术方案.md` 与 `火山方舟CodingPlan_多AI模型兼容改造方案.md`，以"用户只需粘贴 API Key"为目标，消除手写 CCR config、区分协议类型、辨别同名模型等认知负担。

## 目录

- [1. 总体结论](#1-总体结论)
- [2. 架构分工与用户链路](#2-架构分工与用户链路)
- [3. 目标](#3-目标)
- [4. 非目标](#4-非目标)
- [5. CCR 在本架构中的角色](#5-ccr-在本架构中的角色)
- [6. Provider 分类与协议边界](#6-provider-分类与协议边界)
- [7. 一键安装器扩展](#7-一键安装器扩展)
- [8. 重新初始化脚本职责](#8-重新初始化脚本职责)
- [9. 模型配置 UI 两步向导](#9-模型配置-ui-两步向导)
- [10. 配置文件结构](#10-配置文件结构)
- [11. 渲染与同步机制](#11-渲染与同步机制)
- [12. 安全边界](#12-安全边界)
- [13. 验收标准](#13-验收标准)
- [14. 实施顺序](#14-实施顺序)

---

## 1. 总体结论

本项目定位为 **Claude Code Sub-agent + CCR 开箱即用工作台**。核心体验目标：

```
全新用户完成"一键安装 → 重新初始化 → 模型配置 UI"三步后，
即可在 Claude Code 中使用多模型 Sub-agent 协作，
全程不需要手写任何 JSON 配置、不需要理解协议差异。
```

### 关键架构决策

1. **主会话始终是 Claude 原生模型**，不可替换。Sub-agent 的编排、工具调用、权限管理由 Claude Code 框架负责。
2. **Sub-agent 的推理模型可替换**，通过 `model` 字段 + CCR 路由到任意 OpenAI-compatible provider。
3. **CCR 是路由层，不是 AI 模型**。它把 Claude Code 发出的请求翻译成目标 provider 的协议格式。
4. **不需要全局切换 Claude Code**。CCR 模式下每个 Sub-agent 独立路由，主会话不受影响。全局切换（修改 `~/.claude/settings.json`）只是另一种可选路径。
5. **所有 provider 配置收敛到一个 UI 入口**（`src/sub_agent_ccr_model_config.py`），用户只需粘贴 API Key，UI 自动完成密钥加密存储（Windows 凭据管理器）、CCR config endpoint 写入、连通性验证和 agent frontmatter 渲染。
6. **API Key 安全存储**——密钥通过 `ai_providers.py` 已有的 Windows 凭据管理器基础设施（`Advapi32.dll` / `CredWriteW` / `CredReadW`）加密保存，凭据目标名 `HY127.AIProviders:{provider}`。CCR config.json 只写 endpoint，不写明文 Key。运行时通过环境变量注入 CCR 进程。

### 当前痛点与解决

| 痛点 | 原方案 | 本方案 |
|------|-------|-------|
| 用户需知道 Coding Plan 和普通方舟的 URL 区别 | 写文档说明 | UI 自动填写 endpoint，用户不感知 |
| 用户需手写 CCR config.json | 列为"非目标"，完全手工 | UI 向导自动写入 CCR config endpoint；Key 加密存储到凭据管理器 |
| 用户需区分 Coding Plan Key 和普通 Key | 写文档说明 | Provider 选择后 UI 自动关联 Key 类型和 endpoint |
| 同名模型（如 kimi-k2.5）来源混淆 | label 手工区分 | `ai_models_config.json` 预置 label，UI 按 provider 分组展示 |
| 选了 CCR 模型但忘记配 CCR | 无保护 | 未配置的 provider 模型灰显不可选 |

---

## 2. 架构分工与用户链路

### 三层工具链

```
一键安装.exe / src/一键安装卸载.py
  → 机器级基础环境：Python、uv、VSCode、CCR、PATH、右键菜单
  → 不写 ~/.claude/agents，不写 API Key，不做模型绑定

重新初始化 V1.24.bat / 重新初始化 V1.24.ps1
  → 项目级初始化：.venv、依赖、.vscode、hy127 工具库、初始化测试
  → 默认生成 Sub-agent 基础模板到 ~/.claude/agents（model: inherit）
  → 不写 API Key，不做模型绑定，不写 CCR config

src/sub_agent_ccr_model_config.py（唯一可视化配置入口）
  → Tab①: Provider 配置向导 — 粘贴 API Key → 加密存储到 Windows 凭据管理器
                                              → 自动写 CCR config（仅 endpoint，不含 Key）
  → Tab②: 角色模型绑定 — 选 provider + model → 自动渲染 agent frontmatter
  → 读取 ai_models_config.json（候选清单）
  → 写入 agent_role_binding.json（绑定关系）
  → 调用 src/sub_agent_ccr_renderer.py（渲染到 ~/.claude/agents）
```

### 用户完整链路

```
第一次使用：
  ① 双击 一键安装.exe → Python + uv + VSCode + CCR 就绪
  ② 解压项目 → 双击 重新初始化.bat → .venv + agent 基础模板就绪
  ③ 运行 src/sub_agent_ccr_model_config.py
     → Tab① 粘贴 Coding Plan Key（或其他 provider Key）→ Key 加密存入凭据管理器 + endpoint 写入 CCR config
     → Tab② 为每个角色选模型 → 自动渲染到 agent frontmatter
  ④ 在 Claude Code 中使用 Sub-agent 多模型协作

日常切换模型：
  只需重新运行 ③，换选模型，保存即生效
```

---

## 3. 目标

1. 全新用户按"一键安装 → 重新初始化 → 模型配置 UI"完成后，可直接使用 Sub-agent + CCR 多模型协作。
2. 模型配置 UI 升级为两步向导：先配 Provider（粘贴 Key），再绑角色模型。
3. UI 自动定位 CCR config 路径，自动写入 provider endpoint（不含明文 Key）；API Key 加密保存到 Windows 凭据管理器（`HY127.AIProviders:{provider}`），用户不需要手写任何 JSON。
4. UI 提供连通性测试按钮，帮助用户在绑定前确认 Key 有效。
5. 未配置 Key 的 provider 下属模型在角色绑定页灰显不可选，避免绑定后调用失败。
6. 火山方舟 Coding Plan 作为独立 provider `ark_coding_plan` 接入，不复用 `doubao` provider。
7. 同名模型（如 `kimi-k2.5`）通过 label + provider 分组在 UI 中清晰区分。
8. CCR 安装作为一键安装器的默认组件并入——本项目定位即 Sub-agent + CCR，CCR 是主流程必装项。
9. 所有配置变更可逆——UI 可以修改、删除已配置的 provider。

---

## 4. 非目标

1. 不把 Claude Code 或 CCR 作为 Python 项目依赖写入 `pyproject.toml`（CCR 由一键安装器独立部署，不进 `.venv`）。
2. 不在 `.venv` 中安装 LangGraph、CrewAI、AutoGen 等外部编排框架。
3. 不修改 `~/.claude/settings.json`（CCR 模式下不需要全局切换；全局切换走手工文档路径）。
4. 不把 Ark Coding Plan 模型加入 `native_models` 默认列表。
5. 不在卸载时删除 `~/.claude/agents`。
6. 不在 agent 模板中硬编码第三方模型 ID——基础模板始终 `model: inherit`。
7. 不替代 CCR 自身的高级配置能力——UI 只管理本项目声明的 provider 子集。

---

## 5. CCR 在本架构中的角色

### 调用链路

```
Claude Code 主会话（Claude 原生，不可换）
  │
  ├─ 派生 Sub-agent "architect"
  │    frontmatter: model: ark_coding_plan,kimi-k2.5
  │    │
  │    └─ Claude Code 识别 "provider,model" 格式 → 转发给 CCR
  │         │
  │         └─ CCR 查找 config 中的 ark_coding_plan
  │              → base_url: https://ark.cn-beijing.volces.com/api/coding/v3
  │              → api_key: 来源于环境变量（运行时由凭据管理器注入）
  │              → 发送 OpenAI-compatible 请求 {"model":"kimi-k2.5", ...}
  │              → 返回结果翻译回 Claude Code 格式
  │
  ├─ 派生 Sub-agent "implementer"
  │    frontmatter: model: deepseek,deepseek-chat
  │    └─ CCR → DeepSeek 官方 API
  │
  └─ 派生 Sub-agent "docs-writer"
       frontmatter: model: inherit
       └─ 直接使用主会话 Claude 模型（不经过 CCR）
```

### 主会话 vs Sub-agent

| 层面 | 角色 | 能否替换 |
|------|------|---------|
| 编排器 | Claude Code 框架：解析 frontmatter、分配工具、管理对话 | 不能，固定 |
| 主会话大脑 | 决定何时派生 Sub-agent、分配任务、汇总结果 | 不能，固定 Claude 原生 |
| Sub-agent 大脑 | 执行具体任务的推理模型 | **可以替换**，通过 CCR 路由 |

---

## 6. Provider 分类与协议边界

### Provider 总览

| Provider ID | 显示名 | Base URL | 协议 | Key 类型 | 特殊说明 |
|-------------|--------|----------|------|---------|---------|
| `anthropic` | Anthropic/Claude | `https://api.anthropic.com` | Anthropic | `ANTHROPIC_API_KEY` | 无需 CCR |
| `moonshot` | Moonshot/Kimi | `https://api.moonshot.cn/v1` | OpenAI-compatible | `MOONSHOT_API_KEY` | |
| `deepseek` | DeepSeek | `https://api.deepseek.com/v1` | OpenAI-compatible | `DEEPSEEK_API_KEY` | |
| `qwen` | 阿里云/通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | OpenAI-compatible | `DASHSCOPE_API_KEY` | |
| `hunyuan` | 腾讯混元 | `https://api.hunyuan.cloud.tencent.com/v1` | OpenAI-compatible | `HUNYUAN_API_KEY` | |
| `mimo` | 小米MiMo | `https://api.xiaomimimo.com/v1` | OpenAI-compatible | `XIAOMI_API_KEY` | |
| `doubao` | 字节豆包 | `https://ark.cn-beijing.volces.com/api/v3` | OpenAI-compatible | `ARK_API_KEY` | 普通方舟 API |
| `ark_coding_plan` | 火山方舟 Coding Plan | `https://ark.cn-beijing.volces.com/api/coding/v3` | OpenAI-compatible | `ARK_CODING_PLAN_API_KEY` | **独立 Key 和 endpoint，不可与 doubao 混用** |

### 火山方舟 Coding Plan 关键规则

- `doubao`（普通方舟 `/api/v3`）与 `ark_coding_plan`（Coding Plan `/api/coding/v3`）是**两套独立 provider**。
- Coding Plan 需要专属 API Key，不能用普通 ModelArk Key。
- 一个 Coding Plan Key 可访问多个模型（kimi-k2.5、deepseek-v3.2、doubao-seed-code 等），按 `model` 字段路由。
- `ark-code-latest` 是控制台统一管理入口，模型切换约 3-5 分钟生效，不推荐日常快速切换。

### 同名模型 label 规则

同一个模型 ID 可能出现在多个 provider 中（如 `kimi-k2.5` 同时在 Moonshot 和 Ark Coding Plan），必须通过 label 区分：

| Provider | Model ID | 显示 Label |
|----------|----------|-----------|
| `moonshot` | `kimi-k2.5` | Kimi K2.5（Moonshot API） |
| `ark_coding_plan` | `kimi-k2.5` | Ark Kimi K2.5（Coding Plan） |
| `deepseek` | `deepseek-chat` | DeepSeek Chat（DeepSeek API） |
| `ark_coding_plan` | `deepseek-v3.2` | Ark DeepSeek V3.2（Coding Plan） |

`ai_models_config.json` 中预置好 label，UI 按 provider 分组展示，用户不需要自己判断来源。

---

## 7. 一键安装器扩展

### 设计定位

本项目定位为 Sub-agent + CCR 开箱即用工作台。CCR 是多模型路由的核心基础设施，与 Python、uv、VSCode 同级——属于**主流程默认安装项**，不是可选附加功能。

### 安装器完整流程

```
Python 3.12 → uv → VSCode → CCR → PATH 配置 → 右键菜单
```

CCR 安装失败不阻断 Python/uv/VSCode 的安装，但必须在安装结果总结中明确标记为 WARN，提示用户"Sub-agent 多模型路由功能需要 CCR，当前未就绪"。

### CCR 安装实现

| 项目 | 说明 |
|------|------|
| CCR 安装方式 | 待确认（npm / pip / 独立 binary） |
| CCR 下载源 | 待确认（官方 GitHub / 镜像） |
| PATH 注册 | 安装后注册到用户 PATH，确保命令行可调用 |
| 安装检测 | 安装前检测 CCR 是否已存在，已安装则跳过并记录版本 |
| 安装成功提示 | 增加"运行重新初始化后，再运行模型配置 UI 完成 Sub-agent 多模型配置" |
| 安装失败处理 | 记录 WARN，提示手工安装方式，不阻断其他组件 |

### 安装器边界

- 安装器不写 `~/.claude/agents`。
- 安装器不做模型绑定。
- 安装器不输入或保存 API Key。
- 卸载时不删除 `~/.claude/agents`。
- 卸载时不删除 CCR config（属于用户级配置）。
- 卸载时可选清理 CCR 本体（与 VSCode 卸载同级处理）。

---

## 8. 重新初始化脚本职责

### 已实现的功能（保持不变）

| 功能 | 说明 |
|------|------|
| 项目名更新 | 根据文件夹名更新 `pyproject.toml` |
| 环境重建 | 删除并重建 `.venv` |
| 依赖同步 | `uv sync` 三级回退（离线 → 镜像 → PyPI） |
| hy127 部署 | `__hy127/init.bat` |
| VSCode 配置 | `.vscode/settings.json`、`launch.json`、`extensions.json` |
| Sub-agent 基础模板同步 | `.claude_templates/agents/*.md` → `~/.claude/agents/` |
| 初始化测试 | 包导入 + GUI 窗口验证 |

### Sub-agent 模板同步规则

| 目标文件状态 | 操作 |
|-------------|------|
| 文件不存在 | 创建 |
| 存在且 `hy127_managed` 同名版本低于模板 | 原子更新 |
| 存在且 `hy127_managed` 同名版本相同或更高 | 跳过 |
| 存在但无 `hy127_managed` 字段 | 跳过（保护用户自定义 agent） |
| 目录创建或写入失败 | 记录 WARN，不阻断 Python 初始化 |

基础模板始终使用 `model: inherit`。模型绑定由后续 UI 完成。

### CCR 就绪检测

重新初始化脚本在 Sub-agent 模板同步阶段增加 CCR 就绪检测：

| 检测项 | 处理 |
|--------|------|
| CCR 命令可用 | Summary 记录 PASS，附 CCR 版本号 |
| CCR 命令不可用 | Summary 记录 WARN："CCR 未安装，Sub-agent 多模型路由不可用。请运行一键安装或手工安装 CCR" |

检测结果只用于 summary 提示，不阻断任何初始化步骤。

### 不做事项

- 不写 API Key（不操作凭据管理器）、不写 CCR config。
- 不做模型绑定或渲染 provider,model 到 frontmatter。

---

## 9. 模型配置 UI 两步向导

`src/sub_agent_ccr_model_config.py` 从单一"模型绑定"升级为两步向导。

### Tab ①：Provider 配置

```
┌─────────────────────────────────────────────────────┐
│  ① Provider 配置                                     │
│                                                      │
│  ┌─ 可用 Provider ──────────────────────────────┐   │
│  │                                               │   │
│  │  ● 火山方舟 Coding Plan    [已配置 ✓]         │   │
│  │  ○ DeepSeek 官方 API       [未配置]           │   │
│  │  ○ Moonshot (Kimi)         [未配置]           │   │
│  │  ○ 阿里云 通义千问          [未配置]           │   │
│  │  ○ 腾讯混元                [未配置]           │   │
│  │  ○ 小米 MiMo               [未配置]           │   │
│  │  ○ 字节豆包                [未配置]           │   │
│  │                                               │   │
│  └───────────────────────────────────────────────┘   │
│                                                      │
│  ── 火山方舟 Coding Plan ────────────────────────    │
│                                                      │
│  API Key:  [________________________] [测试连接]     │
│                                                      │
│  ⓘ 一个 Coding Plan Key 即可使用以下全部模型：       │
│    · Kimi K2.5 · DeepSeek V3.2 · Doubao Seed Code   │
│    · Ark Code Latest（控制台切换，3-5 分钟生效）     │
│                                                      │
│  Endpoint: https://ark.cn-beijing.volces.com         │
│            /api/coding/v3          (自动填写，只读)  │
│                                                      │
│  ⚠ Key 加密保存在 Windows 凭据管理器，不写入明文文件  │
│                                                      │
│                           [保存 Provider 配置]       │
└─────────────────────────────────────────────────────┘
```

UI 行为：

| 操作 | 自动处理 |
|------|---------|
| 用户选中 provider | 显示该 provider 的配置面板，endpoint 自动从 `ai_models_config.json` 读取 |
| 用户粘贴 API Key | 仅保存到内存变量，不写入项目文件 |
| 点击"测试连接" | 向 endpoint 发送轻量请求，验证 Key 有效性 |
| 点击"保存 Provider 配置" | ① 调用 `保存密钥到凭据管理器()` 将 Key 加密存储到 Windows 凭据管理器（目标名 `HY127.AIProviders:{provider}`）<br>② 自动定位 CCR config.json → 写入/更新该 provider 的 endpoint（**不写 Key**） |
| provider 配置成功 | 列表中该 provider 显示"已配置 ✓"；凭据管理器中可查到对应条目 |

### API Key 存储与注入机制

```
用户粘贴 Key
  │
  ├─ ① 加密保存到 Windows 凭据管理器
  │     目标名: HY127.AIProviders:{provider}
  │     调用: ai_providers.保存密钥到凭据管理器(target_name, key)
  │     底层: Advapi32.dll → CredWriteW（DPAPI 加密，OS 级别保护）
  │
  ├─ ② CCR config.json 只写 endpoint
  │     {
  │       "ark_coding_plan": {
  │         "base_url": "https://ark.cn-beijing.volces.com/api/coding/v3"
  │       }
  │     }
  │     注意: 无 api_key 字段，不写明文密钥
  │
  └─ ③ 运行时注入
        CCR 启动时通过环境变量传入 Key：
        环境变量名: 由 ai_models_config.json 中 provider 的 env_key 字段决定
        值: 从凭据管理器 读取凭据管理器密钥(target_name) 获取
        CCR 自动从环境变量读取 api_key（无需写入 config.json）
```

### Tab ②：角色模型绑定

```
┌─────────────────────────────────────────────────────┐
│  ② 角色模型绑定                                     │
│                                                      │
│  角色          Provider                模型          │
│  ──────────    ─────────────────       ─────────     │
│  架构分析      [▼ 火山方舟 CP    ]     [▼ Kimi K2.5] │
│  代码实现      [▼ 火山方舟 CP    ]     [▼ DS V3.2  ] │
│  代码审查      [▼ 火山方舟 CP    ]     [▼ Kimi K2.5] │
│  测试验证      [▼ 火山方舟 CP    ]     [▼ DS V3.2  ] │
│  文档撰写      [▼ 继承 Claude    ]     [  ——       ] │
│                                                      │
│  ⓘ 灰色选项表示 Provider 未配置，                    │
│    需先在 Tab① 完成配置                              │
│                                                      │
│                    [保存并渲染到 Agent]               │
└─────────────────────────────────────────────────────┘
```

UI 行为：

| 操作 | 自动处理 |
|------|---------|
| 选择 provider 下拉 | 联动更新模型下拉列表，只显示该 provider 下的模型 |
| 未配置的 provider | 模型选项灰显不可选，提示"需先在 Tab① 配置" |
| 选择"继承 Claude" | 模型下拉隐藏，直接使用 `inherit` |
| 点击"保存并渲染" | 写入 `agent_role_binding.json` → 检查并补齐缺失 agent → 渲染 `model` 字段到 `~/.claude/agents` |
| 渲染失败 | 显示阻断性提示："绑定已保存但未渲染到 Claude Code，当前绑定未生效" |

### 火山方舟 Coding Plan 多模型选择

Coding Plan 的核心优势：一个 Key、一个 endpoint、多个模型。不同角色选同一个 provider，只换 model ID：

```
CCR config 只写一次（不含 Key）：
  provider: ark_coding_plan
  base_url: https://ark.cn-beijing.volces.com/api/coding/v3
  （api_key 存储在凭据管理器 HY127.AIProviders:ark_coding_plan，运行时环境变量注入）

5 个 Sub-agent 共用 provider，model ID 不同：
  architect.md    → model: ark_coding_plan,kimi-k2.5
  implementer.md  → model: ark_coding_plan,deepseek-v3.2
  reviewer.md     → model: ark_coding_plan,kimi-k2.5
  tester.md       → model: ark_coding_plan,deepseek-v3.2
  docs-writer.md  → model: inherit
```

也可以跨 provider 混搭：

```
架构分析    → 火山方舟 Coding Plan / Kimi K2.5
代码实现    → DeepSeek 官方 API / DeepSeek Chat
代码审查    → 火山方舟 Coding Plan / Kimi K2.5
测试验证    → 火山方舟 Coding Plan / DeepSeek V3.2
文档撰写    → 继承 Claude
```

---

## 10. 配置文件结构

### ai_models_config.json（随项目分发，不含密钥）

职责：声明所有 provider 候选清单、模型列表、显示名称、endpoint 和协议类型。

关键设计：

- 同时服务两层：`AIProviderManager` 直接调用层（使用 `base_url` / `env_key`）和 Sub-agent 绑定层（使用 `id` / `label` / `requires_ccr`）。
- `base_url` 和 `env_key` 仅供本机调用和 UI 自动填写 endpoint，不写入 agent frontmatter。
- 用户 pull 仓库即获得最新 provider/model 候选清单，无需手动添加。

### agent_role_binding.json（用户 UI 选择结果）

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

字段规则：

| mode | provider | model | 渲染到 frontmatter |
|------|----------|-------|--------------------|
| `inherit` | 省略 | `inherit` | `model: inherit` |
| `native` | 省略 | `<model-id>` | `model: <model-id>` |
| `ccr` | `<provider-id>` | `<model-id>` | `model: <provider>,<model>` |

### ai_providers.py（配置读写与校验）

职责扩展（相对原方案新增 CCR config 读写）：

| 函数 | 职责 | 原方案 | 本方案 |
|------|------|-------|-------|
| `load_models_config()` | 读取 `ai_models_config.json` | 已有 | 保留 |
| `load_agent_bindings()` | 读取 `agent_role_binding.json` | 已有 | 保留 |
| `save_agent_bindings()` | 原子写入绑定文件 | 已有 | 保留 |
| `list_route_options()` | 返回 UI 可用选项列表 | 已有 | 保留 |
| `validate_binding()` | 校验绑定结构 | 已有 | 保留 |
| `detect_ccr_config_path()` | 自动定位 CCR config.json | **无** | **新增** |
| `read_ccr_providers()` | 读取 CCR 已配置的 provider | **无** | **新增** |
| `write_ccr_provider()` | 写入/更新 CCR provider 的 endpoint（不写 Key） | **无** | **新增** |
| `test_provider_connection()` | 轻量连通性测试 | **无** | **新增** |
| `get_provider_status()` | 返回每个 provider 配置状态（含凭据管理器检测） | **无** | **新增** |
| `inject_ccr_env_keys()` | 从凭据管理器读取 Key，注入环境变量供 CCR 使用 | **无** | **新增** |

已有函数（直接复用，无需重写）：

| 函数 | 来源 | 职责 |
|------|------|------|
| `保存密钥到凭据管理器(target_name, 密钥值)` | `ai_providers.py` L314 | 通过 `CredWriteW` 加密存储 Key |
| `读取凭据管理器密钥(target_name)` | `ai_providers.py` L341 | 通过 `CredReadW` 读取已存储 Key |
| `删除凭据管理器密钥(target_name)` | `ai_providers.py` L363 | 通过 `CredDeleteW` 清除 Key |
| `脱敏显示密钥(密钥值)` | `ai_providers.py` L296 | 显示为 `sk-***xxxx` 格式 |
| `_构造凭据目标名(provider_key)` | `ai_providers.py` L310 | 生成 `HY127.AIProviders:{provider}` |

新增函数只读写 CCR 的 config.json 的 endpoint 部分（不含 Key），Key 的读写通过上述已有凭据管理器函数完成。不读取 `.env`、不把 Key 写入项目文件或 CCR config 明文。

### src/sub_agent_ccr_renderer.py（渲染逻辑，保持不变）

- 从 `.claude_templates/agents/*.md` 读取基准模板。
- 补齐 `~/.claude/agents` 中缺失的受管理 agent。
- 只更新带 `hy127_managed` 的同名 agent 的 `model` 字段。
- 原子写入，UTF-8，保护用户自定义文件。

---

## 11. 渲染与同步机制

### Agent 模板规范

每个模板文件使用 Claude Code agent frontmatter 格式：

```yaml
---
name: implementer
description: 根据明确任务完成代码开发
hy127_managed: implementer-v1.0.0
model: inherit
tools: Read, Write, Edit, Bash, Grep
---
```

关键约束：

- 文件第 1 行必须是 `---`。
- `name` 必须和文件名一致。
- `hy127_managed` 格式为 `<agent-name>-v<semver>`。
- 基础模板的 `model` 必须为 `inherit`。
- `tools` 使用逗号分隔字符串。
- prompt 不写任何密钥、endpoint 或 provider endpoint。

### 渲染流程

```
UI 保存 agent_role_binding.json
  → renderer 读取绑定
  → 对每个 agent 计算 model 字段：
      inherit → model: inherit
      native  → model: <native-model-id>
      ccr     → model: <provider>,<model>
  → 检查 ~/.claude/agents/<agent>.md 是否存在
      不存在 → 从 .claude_templates/agents 复制并写入计算后的 model
      存在且有 hy127_managed → 只替换 model 字段
      存在但无 hy127_managed → 跳过
  → 返回 RenderResult（created / updated / skipped / errors）
```

### 三种路由模式对照

| 路由模式 | agent frontmatter | 前置条件 |
|---------|-------------------|---------|
| 单模型继承 | `model: inherit` | 无需 CCR |
| Claude 原生模型 | `model: claude-sonnet-4-6` | Claude Code 能识别该模型 ID |
| CCR 多模型 | `model: ark_coding_plan,kimi-k2.5` | 已安装 CCR，CCR config 中存在该 provider endpoint，凭据管理器中存在对应 Key |

---

## 12. 安全边界

### API Key 处理

| 场景 | 处理方式 |
|------|---------|
| 用户在 UI 输入 Key | 加密保存到 Windows 凭据管理器（`HY127.AIProviders:{provider}`），通过 `Advapi32.dll` / `CredWriteW` 调用 DPAPI 加密 |
| Key 写入 CCR config.json | **禁止**——CCR config 只写 endpoint，不写 `api_key` 字段 |
| Key 写入项目文件 | **禁止**——不写入 `ai_models_config.json`、`agent_role_binding.json`、agent 模板、`.env`、git 仓库 |
| Key 写入日志 | **禁止**——`init_log.txt` 不记录 Key |
| Key 显示 | UI 中 Key 输入框使用密码模式（`show="*"`）；已保存 Key 使用 `脱敏显示密钥()` 显示为 `sk-***xxxx` |
| Key 运行时使用 | 从凭据管理器读取 → 注入环境变量 → CCR 进程通过环境变量获取 |
| Key 删除 | UI 提供"删除 Provider 配置"操作，同时清除凭据管理器条目 |

### 凭据管理器安全保障

| 安全特性 | 说明 |
|---------|------|
| 加密方式 | Windows DPAPI（Data Protection API），密钥绑定到用户登录会话 |
| 访问控制 | 仅当前 Windows 用户可读取，其他用户无法解密 |
| 存储位置 | Windows 系统凭据存储（非文件系统明文） |
| 凭据目标名 | `HY127.AIProviders:{provider_key}`（如 `HY127.AIProviders:ark_coding_plan`） |
| 可审计性 | 用户可通过"控制面板 → 凭据管理器"查看和管理已保存的条目 |
| 已有验证 | `ai_providers.py` 已实现并在生产中使用同一套凭据管理器基础设施 |

### 文件保护

| 场景 | 处理方式 |
|------|---------|
| `~/.claude/agents` 中存在无 `hy127_managed` 的同名文件 | 跳过，不覆盖 |
| 写入用户目录失败 | 记录 WARN，不阻断 Python 初始化 |
| CCR config 或凭据管理器写入失败 | UI 显示错误提示，不静默忽略 |
| 卸载时 | 不删除 `~/.claude/agents`，不删除 CCR config，不删除凭据管理器条目 |

### 日志脱敏

- 日志中用户目录显示为 `~\...` 或 `%USERPROFILE%\...`。
- `init_log.txt` 可能包含本机路径，分享前请审阅。
- `.gitignore` 忽略 `init_log.txt`、`init_exit_trace.txt`、`.uv-cache/`、`.venv/`。

---

## 13. 验收标准

### 功能验收

1. 全新用户按"一键安装 → 重新初始化 → 模型配置 UI"后，可在 Claude Code 使用 Sub-agent + CCR。
2. 模型配置 UI 有两个 Tab：Provider 配置 + 角色绑定。
3. Provider 配置 Tab 中选择 provider 后，endpoint 自动填写，用户只需粘贴 Key。
4. "测试连接"按钮能验证 Key 有效性。
5. "保存 Provider 配置"后 CCR config.json 中存在对应 provider 的 endpoint（不含 api_key 字段）。
6. 角色绑定 Tab 中未配置 provider 的模型灰显不可选。
7. 保存并渲染后，`~/.claude/agents` 中受管理 agent 的 `model` 字段正确。
8. `ai_models_config.json` 中 `ark_coding_plan` 与 `doubao` 共存，互不干扰。
9. 同名模型 label 清晰区分来源。
10. `ark-code-latest` 的 label 包含"控制台统一管理"或"3-5 分钟生效"字样。

### 架构验收

1. `pyproject.toml` 不新增 CCR 或 Claude Code 依赖（CCR 由一键安装器独立部署）。
2. `.venv` 不承担 Claude agent 配置职责。
3. 一键安装器默认安装 CCR，但不写 `~/.claude/agents`，不做模型绑定。
4. 重新初始化脚本只生成 `model: inherit` 基础模板，不写 provider/model 绑定；增加 CCR 就绪检测。
5. API Key 仅存在于 Windows 凭据管理器（`HY127.AIProviders:*`），不写入 CCR config 明文，不进 git。
6. provider/model 绑定只通过 `ai_models_config.json`、`agent_role_binding.json` 和 UI 管理。

### 安全验收

1. API Key 不写入项目文件、CCR config.json 明文、日志文件。
2. API Key 仅存在于 Windows 凭据管理器（`HY127.AIProviders:{provider}`）。
3. CCR config.json 中无 `api_key` 字段，grep 验证无明文 Key。
4. "控制面板 → 凭据管理器"可查到对应 `HY127.AIProviders:*` 条目。
5. 删除 Provider 配置时，凭据管理器条目同步清除。
6. 不删除用户已有 agent。
7. 不覆盖无管理标记的同名 agent。
8. 不在彻底删除中清理用户级 Claude Code 配置。

---

## 14. 实施顺序

### 第一阶段：配置层和基础模板（已基本完成）

- [x] `.claude_templates/agents/*.md` 基础模板
- [x] `ai_models_config.json` 含 `ark_coding_plan` provider
- [x] `agent_role_binding.json` 默认全 inherit
- [x] `ai_providers.py` 读取、校验、展示辅助
- [x] `src/sub_agent_ccr_renderer.py` 渲染逻辑
- [x] `重新初始化 V1.24.ps1` 默认生成基础模板
- [x] `.gitignore` 忽略运行期文件

### 第二阶段：UI 升级为两步向导

- [ ] `ai_providers.py` 凭据服务名从 `Code880.AIProviders` 更新为 `HY127.AIProviders`
- [ ] `ai_providers.py` 新增 CCR config endpoint 读写函数（`detect_ccr_config_path`、`read_ccr_providers`、`write_ccr_provider`）
- [ ] `ai_providers.py` 新增 `inject_ccr_env_keys()`：从凭据管理器读取 Key → 注入环境变量供 CCR 使用
- [ ] `ai_providers.py` 新增 `get_provider_status()`：综合检测 CCR config endpoint + 凭据管理器 Key 状态
- [ ] `ai_providers.py` 新增 `test_provider_connection()`：使用凭据管理器中的 Key 发送轻量连通性测试
- [ ] `src/sub_agent_ccr_model_config.py` 新增 Provider 配置 Tab
- [ ] Provider Tab：自动填写 endpoint、Key 输入（密码模式）、连通性测试、Key 存凭据管理器 + endpoint 写 CCR config
- [ ] Provider Tab：已保存 Key 使用 `脱敏显示密钥()` 显示为 `sk-***xxxx`
- [ ] Provider Tab：删除 Provider 时同步清除凭据管理器条目
- [ ] 角色绑定 Tab：provider/model 联动下拉、未配置 provider 灰显
- [ ] 保存时检查并补齐缺失 agent

### 第三阶段：CCR 安装并入一键安装器（主流程默认安装）

- [ ] 确认 CCR 安装方式和下载源
- [ ] `src/一键安装卸载.py` 新增 CCR 默认安装组件（与 Python/uv/VSCode 同级）
- [ ] CCR 安装失败不阻断其他组件，但 summary 标记 WARN
- [ ] 安装成功提示增加 Sub-agent + CCR 流程说明
- [ ] 重新初始化脚本新增 CCR 就绪检测（PASS/WARN，不阻断）

### 第四阶段：增强与打磨

- [ ] 已配置 provider 的状态持久化和刷新
- [ ] provider 分组展示和风险说明优化
- [ ] `ark-code-latest` 延迟生效的 UI 提示
- [ ] 文档统一更新（`一键安装说明.md`、`必须重新初始化说明.md`）

### 不做事项

- 不写 `~/.claude/settings.json`。
- 不创建 `scripts/claude-ark.sh` 或 `.hy127web_global`。
- 不把 Ark Coding Plan 模型写入 `native_models`。
- 不让安装器直接生成 agent。
- 不把 LangGraph 方案加入项目依赖。

---

## 附录：与原方案文档的关系

本方案融合并取代以下两个文档的技术实现指导作用：

| 原文档 | 融合后状态 |
|--------|-----------|
| `Sub-agent_CCR打包初始化自动生成开发技术方案.md` | 第一阶段内容已落地实现；后续开发以本方案为准 |
| `火山方舟CodingPlan_多AI模型兼容改造方案.md` | `ark_coding_plan` 配置已落地；协议边界和 label 规则已纳入本方案第 6 节 |

关键变更点（相对原两个方案）：

| 变更 | 原方案立场 | 本方案立场 |
|------|----------|-----------|
| CCR 安装 | 不涉及 | **主流程默认安装**，与 Python/uv/VSCode 同级 |
| CCR config 写入 | "非目标"，完全手工 | **UI 向导自动写入** endpoint；Key 不进 config 明文，加密存凭据管理器 |
| API Key 处理 | "不保存或迁移" | **UI 引导输入**，Key 加密存储到 Windows 凭据管理器（`HY127.AIProviders:{provider}`），CCR config 只写 endpoint 不含 Key，运行时环境变量注入 |
| CCR 就绪检测 | "不检查 CCR 是否已安装" | **初始化时检测**，WARN 提示但不阻断 |
| 配置入口 | 用户需理解 CCR config 结构 | **两步向导 UI**，用户只需粘贴 Key |
