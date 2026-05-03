# Code880 Web — 本地化 Manus 轻量 Python AI 工作台方案 v2

版本: v2.0
日期: 2026-05-01

---

## 一、核心命题

用户的问题是：如果要把 Code880 Web 做成一个本地化的 Manus，右侧 AI 模型面板应该怎么设计？

回答这个问题之前，必须先回答一个前置问题：Manus 的本质是什么？

Manus 不是一个聊天机器人。它是一个任务执行器。用户给出目标，Manus 拆解、执行、交付。聊天只是交互界面，不是核心能力。核心能力是：

```
理解目标 → 制定计划 → 调用工具 → 观察结果 → 自我修正 → 交付产物
```

因此，右侧面板不应该只是"选一个模型然后聊天"。它应该是一个**任务控制台**。

---

## 二、重新定义右侧面板

### 2.1 当前状态

现在的右侧面板是一个标准的 AI 聊天窗口：

```
┌─────────────────────┐
│  模型配置按钮        │
│                     │
│  对话消息列表        │
│                     │
│                     │
│  输入框 + 发送按钮   │
└─────────────────────┘
```

这个设计只能做问答。用户问一句，AI 答一句。AI 不能主动读文件、不能运行代码、不能生成补丁、不能验证结果。

### 2.2 目标状态

如果要做本地 Manus，右侧应该变成：

```
┌─────────────────────┐
│  模式切换            │
│  [对话] [任务] [设置] │
├─────────────────────┤
│                     │
│  内容区域            │
│  (对话/任务步骤/设置) │
│                     │
├─────────────────────┤
│  输入框              │
│  [上下文] [权限] 发送 │
└─────────────────────┘
```

三种模式服务于不同场景：

| 模式 | 用户意图 | AI 行为 |
|---|---|---|
| 对话 | 问一个问题，得到回答 | 读上下文文件，生成回答，不执行任何操作 |
| 任务 | 达成一个目标 | 拆解步骤，调用工具，生成产物，等待审批 |
| 设置 | 配置模型和权限 | 无 AI 行为 |

---

## 三、模型层设计

### 3.1 一个根本性的设计选择

Manus 在云端运行，它可以内部整合多个模型、多种工具、沙箱环境，用户无感知。但 Code880 是本地工具，用户自己提供 API Key，自己承担成本。这决定了：

1. **用户必须清楚地知道自己在用什么模型**。不能像 Manus 那样黑盒。
2. **用户必须能控制成本**。不能一个任务默默调用 50 次 API。
3. **模型配置必须简单**。不能要求用户理解 Provider/Protocol/Runtime 三层抽象。

所以，模型层的设计原则是：**对用户简单，对系统灵活**。

### 3.2 用户视角的模型配置

用户看到的应该是这样的设置页面：

```
模型列表
────────────────────────────
+ 添加模型

[1] DeepSeek Chat
    API 地址: https://api.deepseek.com/v1
    模型: deepseek-chat
    用途: 对话 · 执行
    状态: ● 已连通

[2] DeepSeek Reasoner
    API 地址: https://api.deepseek.com/v1
    模型: deepseek-reasoner
    用途: 规划 · 审核
    状态: ● 已连通

[3] 本地 Ollama
    API 地址: http://localhost:11434/v1
    模型: qwen2.5-coder:7b
    用途: 对话
    状态: ○ 未连通
```

每个模型只需要填 5 个字段：

```
名称        自定义名称
API 地址    https://api.deepseek.com/v1
API Key     sk-****
模型 ID     deepseek-chat
用途        勾选: □ 对话  □ 规划  □ 执行  □ 审核
```

"用途"是关键。它让用户决定模型的角色，而不是让系统猜。

### 3.3 系统视角的模型调度

用户配置了多个模型和用途后，系统内部维护一个调度表：

```
对话请求 → 找用途包含"对话"的第一个已启用模型
规划请求 → 找用途包含"规划"的第一个已启用模型
执行请求 → 找用途包含"执行"的第一个已启用模型
审核请求 → 找用途包含"审核"的第一个已启用模型
```

如果某个用途没有配置模型，降级到"对话"模型。如果连对话模型都没有，报错。

这样，一个 DeepSeek 用户可以：
- deepseek-reasoner 用于规划和审核（贵但准）
- deepseek-chat 用于对话和执行（便宜快速）

一个只用一个模型的用户可以：
- 给唯一的模型勾选所有用途

### 3.4 协议适配

不同 Provider 的 API 格式不同，但用户不应该关心这个。系统应该根据 API 地址自动判断协议：

```
包含 api.deepseek.com       → OpenAI-compatible
包含 api.openai.com         → OpenAI 原生
包含 api.anthropic.com      → Anthropic Messages
包含 localhost / 127.0.0.1  → OpenAI-compatible（Ollama/LM Studio 通常如此）
包含 openrouter.ai          → OpenAI-compatible
其他                        → 默认 OpenAI-compatible，可手动切换
```

用户也可以在高级设置中手动选择协议，但默认应该自动识别。

---

## 四、任务模式设计

### 4.1 什么是"任务"

在对话模式中，用户说"帮我分析一下这段代码"，AI 读上下文、输出文字，结束。

在任务模式中，用户说"帮我修复启动脚本的编码问题"，AI 需要：

```
1. 读取启动脚本内容
2. 分析编码相关的代码段
3. 定位问题
4. 生成修复补丁
5. 展示补丁让用户确认
6. 用户确认后应用修改
7. 运行脚本验证修复是否生效
8. 报告结果
```

这就是 Manus 式的任务执行。关键在于 AI 能调用工具、能分步执行、能等待用户确认。

### 4.2 任务生命周期

```
用户输入目标
    ↓
[规划阶段] 规划模型分析目标，生成执行计划
    ↓
用户确认或修改计划
    ↓
[执行阶段] 执行模型按计划逐步执行
    │
    ├→ 调用只读工具（自动）
    ├→ 调用写入工具（需确认）
    ├→ 调用运行工具（需确认）
    ├→ 遇到问题自行修正
    │
    ↓
[审核阶段] 审核模型检查结果
    ↓
[交付阶段] 汇总产物和报告
```

### 4.3 前端展示

任务执行时，右侧面板应该展示步骤流：

```
┌─────────────────────────┐
│ 任务: 修复启动脚本编码    │
│ 状态: 执行中              │
├─────────────────────────┤
│                         │
│ ✓ 步骤 1: 读取启动脚本   │
│   读取了 启动Web工作台.ps1 │
│   共 206 行              │
│                         │
│ ✓ 步骤 2: 分析编码问题   │
│   发现第 171 行 ConvertTo │
│   -Json 输出可能包含非    │
│   UTF-8 字符             │
│                         │
│ ● 步骤 3: 生成修复补丁   │
│   正在生成...             │
│                         │
│ ○ 步骤 4: 等待确认       │
│ ○ 步骤 5: 应用并验证     │
│                         │
├─────────────────────────┤
│ [停止任务]               │
└─────────────────────────┘
```

每个步骤可以展开查看详情：调用了什么工具、传了什么参数、返回了什么结果、耗时多少、用了哪个模型。

### 4.4 审批机制

任务执行中遇到需要确认的操作时，前端应该弹出明确的审批卡片：

```
┌─────────────────────────┐
│ ⚠ AI 请求写入文件        │
│                         │
│ 文件: 启动Web工作台.ps1   │
│ 变更: 修改第 171 行       │
│                         │
│ - $regBody = ... |      │
│   ConvertTo-Json        │
│ + $regBody = ... |      │
│   ConvertTo-Json -Comp  │
│                         │
│ 写入前将自动备份原文件     │
│                         │
│ [拒绝]    [允许本次]      │
└─────────────────────────┘
```

```
┌─────────────────────────┐
│ ⚠ AI 请求运行命令        │
│                         │
│ 命令: python -m pytest   │
│ 目录: 当前项目根目录      │
│                         │
│ [拒绝]    [允许本次]      │
└─────────────────────────┘
```

---

## 五、工具系统设计

### 5.1 工具即能力

Manus 的核心能力来自工具，不是来自模型。模型只是决策层，工具才是执行层。对于本地 Python 工作台，需要以下工具：

**只读工具（默认允许）：**

| 工具 | 功能 | 对应现有模块 |
|---|---|---|
| `list_files` | 列出项目文件树 | FileService.get_tree |
| `read_file` | 读取文件内容 | FileService.read_file |
| `search_files` | 按文件名搜索 | FileService.search |
| `search_content` | 按内容搜索 | 新增 |
| `get_run_log` | 读取运行日志 | TaskRunner.completed_tasks |

**写入工具（需用户确认）：**

| 工具 | 功能 | 对应现有模块 |
|---|---|---|
| `write_file` | 写入/修改文件 | FileService.save_file |
| `create_file` | 创建新文件 | FileService.save_file |
| `apply_patch` | 应用 diff 补丁 | 新增 |

**执行工具（需用户确认）：**

| 工具 | 功能 | 对应现有模块 |
|---|---|---|
| `run_python` | 运行 Python 文件 | TaskRunner.start_run |
| `run_pytest` | 运行测试 | 新增，基于 TaskRunner |

### 5.2 工具调用协议

AI 模型需要能"调用工具"。实现方式有两种：

**方式 A：依赖模型原生 Function Calling**

如果模型支持 function calling / tool_use（如 GPT-4、Claude、部分 DeepSeek 模型），直接使用原生协议。

优点：标准化，模型理解好。
缺点：不是所有模型都支持，格式不统一。

**方式 B：提示词指令 + JSON 解析**

在 system prompt 中告诉模型工具清单和调用格式，让模型输出结构化 JSON，系统解析执行。

```
你可以使用以下工具，需要使用时请输出如下格式：

<tool_call>
{"tool": "read_file", "args": {"path": "code880web/hub/app.py"}}
</tool_call>

可用工具：
- list_files: 列出目录文件
- read_file: 读取文件内容 (参数: path, max_lines)
- search_content: 搜索文件内容 (参数: query, file_pattern)
- write_file: 修改文件 (参数: path, content) [需要用户确认]
- run_python: 运行 Python 文件 (参数: path) [需要用户确认]
```

优点：兼容所有模型，完全可控。
缺点：依赖模型遵循指令的能力，可能输出格式不规范。

**建议：两种都支持**。如果模型原生支持 function calling，用方式 A。否则用方式 B。系统内部统一为相同的工具调用结构。

### 5.3 安全边界

所有工具操作必须遵守以下规则：

```
1. 路径必须在项目目录内（复用现有 validate_path）
2. 敏感文件默认拒绝（.env, *.key, *.pem, credentials.*）
3. 读取单文件上限 50KB
4. 搜索结果上限 50 条
5. 写入前自动备份
6. 每个任务最多调用 30 次工具（防止死循环）
7. 每个任务最长运行 10 分钟
8. Python 执行复用现有 TaskRunner 的 5 分钟超时
```

---

## 六、上下文管理

### 6.1 问题

当前的 AI 上下文是"用户勾选了哪些文件，就拼接哪些文件的内容"。这对简单问答够用，但对任务执行不够：

1. 用户可能不知道该勾选哪些文件
2. 任务执行中 AI 需要动态读取新文件
3. 拼接全部文件会超出 token 限制
4. 没有项目全局视角

### 6.2 分层上下文

```
第 1 层: 项目概览（始终包含）
  - 文件树（目录结构，不含内容）
  - 项目名称、类型、语言

第 2 层: 焦点文件（按需包含）
  - 用户当前打开的文件
  - 用户手动勾选的文件

第 3 层: 工具获取（任务执行中动态获取）
  - AI 通过 read_file 工具读取
  - AI 通过 search_content 工具搜索
  - 运行日志和错误输出
```

第 1 层很小（几百 token），始终放入 system prompt。
第 2 层按用户选择放入。
第 3 层由 AI 在任务执行中自主获取。

### 6.3 上下文预算

不同模型的 context window 不同。系统应该根据模型配置中的上限自动管理：

```
总预算 = 模型 context window × 70%（留 30% 给输出）
已用 = system prompt + 对话历史 + 上下文文件
可用 = 总预算 - 已用
```

当可用空间不足时：
1. 对话模式：截断早期历史
2. 任务模式：摘要早期步骤，保留最近 3 步完整内容

---

## 七、Agent 循环实现

### 7.1 核心循环

```python
async def agent_loop(task):
    # 规划
    plan = await call_model("planner", build_plan_prompt(task))
    steps = parse_plan(plan)
    await notify_user("plan_ready", steps)

    # 等待用户确认计划
    await wait_for_approval("plan")

    # 逐步执行
    for step in steps:
        result = await execute_step(step)

        if result.needs_approval:
            await notify_user("approval_needed", result)
            approved = await wait_for_approval(result.action)
            if not approved:
                continue

        if result.failed:
            # 自我修正：把错误反馈给模型，让它调整
            correction = await call_model("executor", build_correction_prompt(result))
            # 最多重试 2 次
            ...

        task.record_step(step, result)

    # 审核
    review = await call_model("reviewer", build_review_prompt(task))
    await notify_user("review_complete", review)

    # 交付
    report = build_report(task)
    await notify_user("task_complete", report)
```

### 7.2 步骤执行

```python
async def execute_step(step):
    # 模型决定用什么工具
    response = await call_model("executor", build_step_prompt(step))

    # 解析工具调用
    tool_call = parse_tool_call(response)
    if not tool_call:
        # 模型没有调用工具，只是输出文字
        return StepResult(output=response.text)

    # 检查权限
    tool = tool_registry.get(tool_call.name)
    if tool.permission == "confirm":
        return StepResult(needs_approval=True, action=tool_call)

    # 执行工具
    result = await tool.execute(tool_call.args)
    return StepResult(output=result)
```

### 7.3 与现有架构的关系

```
新增组件:
  Worker/services/agent_runner.py   — Agent 循环和状态机
  Worker/services/tool_registry.py  — 工具注册和权限
  Worker/services/context_engine.py — 上下文构造

修改组件:
  Hub/models_manager.py     — 增加 roles 字段
  Hub/app.py                — AI relay 支持指定 model_id
  Worker/app.py             — 增加任务相关 API 路由
  Worker/ai_service.py      — 从纯聊天升级为支持工具调用
  前端 index.html           — 增加任务模式 UI
```

---

## 八、模型选择的实际建议

### 8.1 最低成本方案

只用一个模型：

```
DeepSeek Chat (deepseek-chat)
用途: 对话 + 规划 + 执行 + 审核
月成本估算: 几元人民币（日常使用）
```

适合个人开发者，日常辅助够用。规划和审核质量一般，但免费额度宽裕。

### 8.2 推荐方案

两个模型，角色分工：

```
DeepSeek Reasoner (deepseek-reasoner)
用途: 规划 + 审核
特点: 推理能力强，适合分析问题和检查结果

DeepSeek Chat (deepseek-chat)
用途: 对话 + 执行
特点: 速度快成本低，适合日常交互和工具调用
```

规划用强模型想清楚再做，执行用快模型省钱。

### 8.3 进阶方案

加入本地模型：

```
DeepSeek Reasoner → 规划 + 审核
DeepSeek Chat → 对话 + 执行
Ollama qwen2.5-coder:7b → 对话（离线备用）
```

断网时仍然可以用本地模型做基础问答。

### 8.4 高端方案

```
Claude Sonnet / GPT-4o → 规划 + 审核
DeepSeek Chat → 执行
本地模型 → 敏感文件摘要
```

---

## 九、与外部 Agent Runtime 的关系

### 9.1 Claude Code 和 Codex CLI 的定位

Claude Code、Codex CLI 本身就是成熟的编程 Agent。Code880 不应该试图"复制"它们的能力，而应该把它们当作可选的"高级执行引擎"。

```
Code880 内置轻量 Agent:
  优点 — 完全可控、成本透明、任何模型都能用
  缺点 — 能力上限取决于自身实现质量

Claude Code / Codex CLI 作为外部 Runtime:
  优点 — 成熟强大、持续迭代
  缺点 — 需要额外安装、依赖特定 Provider
```

### 9.2 接入方式

如果用户本机安装了 Claude Code 或 Codex CLI，可以作为一种"运行时"选项出现在任务模式中：

```
执行引擎:
  ○ 内置 Agent（使用已配置的模型）
  ○ Claude Code（需要本机安装）
  ○ Codex CLI（需要本机安装）
```

接入方式是子进程调用 + 输出流解析，不需要改动 Hub 的模型管理。这些运行时自带模型和密钥管理。

### 9.3 实现优先级

第一期不做外部 Runtime 接入。先把内置轻量 Agent 做好做稳。原因：

1. 内置 Agent 是核心竞争力，外部 Runtime 只是锦上添花
2. 内置 Agent 兼容任何模型，用户选择更自由
3. 内置 Agent 的工具权限、审批流、审计完全可控
4. 外部 Runtime 的接口可能变化，维护成本不确定

---

## 十、实现路线图

### Phase 1: 模型角色化（1-2 天）

```
目标: 让用户能给模型分配角色

改动:
  - models.json 增加 roles 字段: ["chat", "planner", "executor", "reviewer"]
  - ModelsManager 增加 get_model_for_role(role) 方法
  - Hub AI Relay 支持请求体指定 model_id
  - 前端模型设置页增加"用途"勾选
  - 前端对话模式显示当前使用的模型名称

验收:
  - 用户能配置两个模型，分别用于对话和规划
  - 对话请求自动路由到"对话"角色的模型
```

### Phase 2: 上下文引擎（2-3 天）

```
目标: AI 能理解项目结构，不仅仅是拼接勾选文件

改动:
  - 新增 context_engine.py
  - 自动生成项目文件树作为基础上下文
  - 支持上下文预算计算
  - 对话回答中标注引用了哪些文件
  - 前端显示上下文来源

验收:
  - AI 回答"这个项目有哪些模块"时能准确回答
  - 不勾选文件也能基于文件树给出有用建议
```

### Phase 3: 工具系统（3-5 天）

```
目标: AI 能在对话中调用只读工具

改动:
  - 新增 tool_registry.py
  - 实现 list_files、read_file、search_content 工具
  - AI Service 支持解析工具调用指令
  - 工具调用结果回填到对话上下文
  - 前端展示工具调用过程

验收:
  - 用户问"app.py 里有哪些路由"，AI 自动读取文件并回答
  - 用户问"哪些文件引用了 AuthManager"，AI 自动搜索并回答
```

### Phase 4: 任务模式（5-7 天）

```
目标: 支持多步骤任务执行

改动:
  - 新增 agent_runner.py
  - 任务状态机: created → planning → running → reviewing → completed
  - 规划阶段使用"规划"角色模型
  - 执行阶段使用"执行"角色模型
  - 写入和运行操作需要用户确认
  - WebSocket 推送任务事件
  - 前端任务面板 UI

验收:
  - 用户能发起"分析项目结构并生成说明文档"任务
  - 任务能自动读取文件、分析、生成文档
  - 写入文件前弹出确认
  - 任务可以中途停止
```

### Phase 5: 补丁与验证（3-5 天）

```
目标: AI 能生成代码修改，用户确认后应用并验证

改动:
  - 工具增加 write_file、apply_patch
  - diff 预览组件
  - 写入前自动备份
  - 运行 Python/pytest 验证修改
  - 验证结果反馈给 AI 继续迭代

验收:
  - AI 生成修复补丁，前端展示 diff
  - 用户确认后文件被修改，原文件自动备份
  - AI 自动运行测试验证修复是否生效
```

### Phase 6: 外部 Runtime（后续）

```
目标: 可选接入 Claude Code / Codex CLI

改动:
  - 新增 cli_runtime.py
  - 检测本机安装的 Agent CLI
  - 子进程方式调用
  - 输出流解析为 WebSocket 事件
  - 前端执行引擎选择

验收:
  - 用户能选择 Codex CLI 执行代码任务
  - 输出流式展示在前端
```

---

## 十一、关键设计决策

### 11.1 为什么不用 LangChain / AutoGen 等框架

```
1. 依赖太重。Code880 是轻量本地工具，不应该引入庞大框架。
2. 黑盒太多。Agent 的行为必须完全可控、可审计。
3. 工具有限。本项目的工具集很小（读、写、搜索、运行），手写比框架更直接。
4. 部署复杂。这些框架的依赖链在 Windows + uv 环境下容易出问题。
```

直接用 Python async + httpx + 现有 FastAPI 框架实现，代码量不大，完全可控。

### 11.2 为什么任务要用多模型而不是单模型

```
1. 成本控制。规划只需要 1-2 次调用，用贵模型可以接受。执行可能需要 10-20 次调用，用便宜模型省钱。
2. 能力匹配。推理强的模型适合分析和判断，速度快的模型适合执行和工具调用。
3. 审核独立性。审核模型最好和执行模型不同，避免自己检查自己。
4. 灵活性。用户可以全部用同一个模型（全勾选），也可以精细分工。
```

### 11.3 为什么提示词工具调用优先于 Function Calling

```
1. 兼容性。所有模型都支持提示词，不是所有模型都支持 function calling。
2. 透明性。提示词方式下，用户能在对话中看到 AI 的工具调用意图。
3. 可调试。出了问题，看 system prompt 就能定位。
4. 渐进增强。先用提示词方式跑通，后续对支持 function calling 的模型自动升级。
```

### 11.4 安全底线

```
1. API Key 只在 Hub 进程中存在，Worker 不持有。
2. 文件操作只在项目目录内。
3. 写操作必须用户确认。
4. 命令执行必须用户确认。
5. 每个任务有工具调用次数上限和时间上限。
6. 敏感文件（.env、密钥文件）默认禁止 AI 读取。
7. 所有 AI 工具调用写入审计日志。
8. 用户可以随时停止任务。
```

---

## 十二、前端交互细节

### 12.1 对话模式

```
与现有基本相同，增加：
- 顶部显示当前模型名称和角色
- AI 回答中如果调用了工具，以折叠卡片形式展示
- 底部增加上下文指示器（显示包含了哪些文件）
```

### 12.2 任务模式

```
上方: 任务标题 + 状态 + 停止按钮
中间: 步骤列表，每步可展开
  - 步骤名称
  - 使用的模型
  - 调用的工具和参数
  - 工具返回摘要
  - 耗时
下方: 审批卡片（写入确认、命令确认）
底部: 最终报告
```

### 12.3 设置页

```
模型列表（增加角色勾选）
上下文策略（项目文件树 / 手动勾选 / 自动）
工具权限（只读自动 / 写入确认 / 命令确认）
任务限制（最大步骤数 / 最大时间 / 最大 token 消耗）
审计日志路径
```

---

## 十三、总结

把 Code880 Web 做成本地 Manus，核心不在于模型有多强，而在于：

```
1. 模型能读懂项目 — 上下文引擎
2. 模型能调用工具 — 工具系统
3. 工具受人控制 — 审批机制
4. 过程可追溯   — 审计日志
5. 用户能干预   — 步骤展示和停止
6. 成本可控     — 角色分工和预算
```

右侧 AI 面板从"聊天框"升级为"任务控制台"，模型从"单一 Provider"升级为"角色化调度"，交互从"一问一答"升级为"目标驱动的多步执行"。

这就是本地化 Manus 的核心。
