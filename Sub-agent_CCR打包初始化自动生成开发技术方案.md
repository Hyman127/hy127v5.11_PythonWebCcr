# Sub-agent + CCR 打包初始化自动生成开发技术方案

> 版本：v3.1（Sub-agent + CCR 开箱即用定位修订稿）
> 日期：2026-05-07
> 范围：`hy127v5.11_multi-orchestration_CCR` 的 Python 架构定位为 Claude Code `Sub-agent + CCR` 开箱即用工作台；`重新初始化 V1.24.ps1` 默认生成 HY127 受管理 Sub-agent 基础模板，初始化成功后由用户运行 `src\sub_agent_ccr_model_config.py` 配置 Sub-agent 角色与 AI 模型绑定。本方案只给开发落地边界和实现细节，不直接写入用户密钥或 CCR provider 配置。
> 复核修订要点：`重新初始化 V1.24.ps1` 负责默认生成可用的 Claude agent 基础模板，跳过只作为 CI、纯 Python 教学环境或用户显式高级开关；模型/provider 绑定前置到 `ai_providers.py`、`ai_models_config.json` 和 `agent_role_binding.json`；用户通过 `src` 下 Python UI 配置后再渲染更新 `~/.claude/agents`，UI 必须能补齐缺失的受管理 agent；frontmatter 必须从第 1 行 `---` 开始；HY127 管理信息保留在 frontmatter 字段；`tools` 使用逗号分隔字符串；日志路径脱敏；新增 `.gitignore` 要求；同步逻辑保持版本比较、路径校验、原子写入和模板自检。

## 目录

- [1. 背景和结论](#1-背景和结论)
- [2. 目标](#2-目标)
- [3. 非目标](#3-非目标)
- [4. 推荐目录结构](#4-推荐目录结构)
- [5. Agent 模板规范](#5-agent-模板规范)
- [6. 管理标记和覆盖策略](#6-管理标记和覆盖策略)
- [7. 初始化脚本改造方案](#7-初始化脚本改造方案)
- [8. 用户选择策略](#8-用户选择策略)
- [9. PowerShell 伪代码](#9-powershell-伪代码)
- [10. 打包安装器边界](#10-打包安装器边界)
- [11. CCR 配置边界](#11-ccr-配置边界)
- [12. 角色模板建议](#12-角色模板建议)
- [13. 日志输出规范](#13-日志输出规范)
- [14. 测试方案](#14-测试方案)
- [15. 验证命令](#15-验证命令)
- [16. 开发分阶段计划](#16-开发分阶段计划)
- [17. 验收标准](#17-验收标准)
- [18. 推荐最终用户流程](#18-推荐最终用户流程)
- [19. 推荐开发优先级](#19-推荐开发优先级)
- [20. v3.1 落地清单](#20-v31-落地清单)
- [21. 面向 DeepSeek 类实现模型的开发执行细节](#21-面向-deepseek-类实现模型的开发执行细节)
- [22. 前置化模型绑定与 UI 配置层](#22-前置化模型绑定与-ui-配置层)
- [23. 一句话方案](#23-一句话方案)

## 1. 背景和结论

本方案面向当前项目的 Claude Code 多模型使用方式。项目 Python 架构的定位不是普通 Python 工具附带一个可选 AI 模板，而是 **Sub-agent + CCR 开箱即用工作台**：完成一键安装、重新初始化和模型配置后，全新用户应能直接在 Claude Code 中使用 HY127 受管理 Sub-agent，并按角色路由到 Claude 原生模型或 CCR provider/model。

核心结论：

- `CCR` 是本项目目标 AI 路由环境，但仍不放进本项目 `.venv`，不和 Python 运行时强绑定。
- `Sub-agent` 基础模板是核心初始化产物，`重新初始化 V1.24.ps1` 默认生成到用户级 Claude Code 目录，初始 `model` 使用 `inherit`，保证模板生成后立即可被 Claude Code 识别。
- AI 模型绑定不再靠用户逐个手改 agent Markdown，而是由 `ai_providers.py`、`ai_models_config.json`、`agent_role_binding.json` 和 `src\sub_agent_ccr_model_config.py` 形成前置配置层。
- 自动生成逻辑应优先放进 `重新初始化 V1.24.ps1`，不建议默认放进 `一键安装卸载.py`。
- 初始化成功后，用户再双击或运行 `src\sub_agent_ccr_model_config.py`，在 UI 中选择单模型继承、Claude 原生模型或 CCR 多模型绑定，并把结果渲染回 `~/.claude/agents`。
- 生成过程必须幂等、安全、默认执行；仅在 CI、纯 Python 教学环境或用户显式设置高级环境变量时跳过，且不能静默覆盖用户已有 Claude agent。
- 若初始化阶段跳过或生成不完整，模型配置 UI 必须在渲染前自动补齐缺失的 HY127 受管理 agent；无法补齐时必须显示阻断性提示，不能只静默保存绑定。
- API Key、Base URL 等敏感或环境相关配置不写入 agent 模板；provider/model 清单由 `ai_models_config.json` 维护，密钥仍由凭据管理器、环境变量或 CCR 自身配置维护。

当前架构分工应保持如下：

```text
一键安装.exe / src/一键安装卸载.py
  -> 安装机器级基础环境：Python、uv、VSCode、PATH、右键菜单

重新初始化 V1.24.bat / 重新初始化 V1.24.ps1
  -> 初始化当前项目：.venv、依赖、.vscode、hy127、本项目测试
  -> 默认生成 Claude Code Sub-agent 基础模板到 ~/.claude/agents
  -> 仅在显式高级开关下跳过，跳过会让 Sub-agent 开箱即用状态未完成

src/sub_agent_ccr_model_config.py
  -> 初始化成功后由用户打开
  -> 读取 ai_providers.py + ai_models_config.json
  -> 写入或更新 agent_role_binding.json
  -> 检查并补齐缺失的 HY127 受管理 agent
  -> 按角色绑定渲染 ~/.claude/agents/*.md 的 model 字段

Claude Code + CCR
  -> 目标用户级 AI 工作流：~/.claude/agents、Claude 原生模型或 CCR provider/model 路由
```

## 2. 目标

本次开发目标：

1. 在项目根目录新增一套可维护的 Claude agent 模板。
2. 在重新初始化流程中默认生成 Claude Code 多模型 Agent 基础模板，作为开箱即用主流程的一部分。
3. 新增或复用 `ai_providers.py`、`ai_models_config.json` 的 provider/model 真相源，让 agent 模型绑定不再硬编码在模板里。
4. 新增 `agent_role_binding.json`，保存 Sub-agent 角色到模型的绑定关系。
5. 新增 `src\sub_agent_ccr_model_config.py`，让用户在初始化成功后通过 UI 设置模型绑定、补齐缺失 agent 并渲染 agent。
6. 自动创建用户级目录：

```text
Windows: %USERPROFILE%\.claude\agents
通用写法: ~/.claude/agents
```

7. 将项目模板复制或渲染到用户级 Claude Code agent 目录。
8. 对已有用户文件执行保护策略，避免误覆盖。
9. 在 `init_log.txt` 和最终 summary 中记录生成结果。
10. 让打包安装流程、项目初始化流程、模型绑定配置流程边界清晰，保证 Sub-agent + CCR 是项目主流程，同时避免 Python 基础安装器直接承担 Claude 用户目录写入职责。

## 3. 非目标

以下内容不纳入本阶段：

1. 不实现 CCR provider 配置写入。
2. 不保存或迁移 API Key。
3. 不在 `.venv` 中安装 LangGraph、CrewAI、AutoGen 等外部编排框架。
4. 不把 Claude Code 或 CCR 作为 Python 项目依赖写入 `pyproject.toml`。
5. 不在卸载器中默认删除 `~/.claude/agents`，因为该目录属于用户级配置，可能包含用户自己的 agent。
6. 不默认修改用户已有的非本工具生成 agent。
7. 不让 `重新初始化 V1.24.ps1` 直接写入用户 API Key、Base URL 或 CCR provider endpoint。
8. 不把模型绑定 UI 做进 `一键安装.exe`，该 UI 只作为项目内 `src` 路径下的独立配置工具。

## 4. 推荐目录结构

在项目根目录新增模板目录：

```text
.claude_templates/
├── README.md
└── agents/
    ├── architect.md
    ├── implementer.md
    ├── reviewer.md
    ├── tester.md
    └── docs-writer.md

agent_role_binding.json
ai_models_config.json
ai_providers.py
src/
├── sub_agent_ccr_model_config.py
└── sub_agent_ccr_renderer.py
```

说明：

- `.claude_templates/agents/*.md` 是开箱即用主流程必须安装的基础模板，默认 `model: inherit`。
- `agent_role_binding.json` 保存角色到模型的绑定，用户可通过 UI 修改。
- `ai_models_config.json` 保存 provider、base_url、模型列表，不保存 API Key。
- `ai_providers.py` 继续作为 provider/model 读取、校验、刷新和密钥状态检查的统一模块。
- `src\sub_agent_ccr_model_config.py` 是用户初始化成功后点击运行的配置 UI，也是模型绑定生效前的必经入口。
- `src\sub_agent_ccr_renderer.py` 是 UI 和命令行复用的渲染/同步逻辑，必须能从 `.claude_templates/agents` 补齐缺失的受管理 agent。

初始化后生成到：

```text
%USERPROFILE%\.claude\agents\
├── architect.md
├── implementer.md
├── reviewer.md
├── tester.md
└── docs-writer.md
```

如果后续需要把提示词模板也改为渲染式，可以扩展为：

```text
.claude_templates/
└── agents/
    ├── architect.md.tmpl
    ├── implementer.md.tmpl
    └── ...
```

后续还可以扩展：

```text
.claude_templates/
├── agents/
│   ├── *.md
│   └── *.md.tmpl
├── commands/
│   └── write-and-review.md
└── README.md
```

第一阶段只做 `agents`，不要同时引入 commands，降低行为面。

## 5. Agent 模板规范

每个模板文件使用 Claude Code agent frontmatter 格式。关键约束：**文件第 1 行必须是 `---`**，不能在 frontmatter 前放 HTML 注释，否则 Claude Code 可能无法识别该文件为 sub-agent。

v3.1 仍坚持模板不写死第三方模型，基础模板默认使用 `inherit`。用户初始化成功后运行 `src\sub_agent_ccr_model_config.py`，由 UI 根据 `agent_role_binding.json` 补齐缺失 agent 并渲染实际 `model` 字段。

```markdown
---
name: implementer
description: 使用实现型模型完成明确的代码开发任务
hy127_managed: implementer-v1.0.0
model: inherit
tools: Read, Write, Edit, Bash, Grep
---

你是实现型代码 Agent。你的职责是根据主 Agent 的任务说明完成可运行代码。

工作要求：
1. 优先保证功能完整、逻辑正确、可运行。
2. 修改范围必须聚焦在任务指定文件或模块。
3. 完成后输出改动文件、关键实现点、已执行验证。
4. 不处理 API Key、密码、Token 等敏感信息。
```

模板要求：

- 第一行必须是 `---`。
- `name` 必须和文件名一致。
- `hy127_managed` 必须使用 `<agent-name>-v<semver>`，例如 `implementer-v1.0.0`。
- 基础模板的 `model` 必须使用 `inherit`，避免未启用 CCR 时出现不存在的模型 ID。
- 由 `src\sub_agent_ccr_model_config.py` 渲染后的 `model` 可为 `inherit`、Claude Code 原生模型 ID，或 CCR 约定的 `<provider>,<model>`。
- 使用 `<provider>,<model>` 时，必须明确提示用户需要已安装并启用 CCR。
- `tools` 按 Claude Code 当前 frontmatter schema 使用逗号分隔字符串，例如 `tools: Read, Write, Edit`。
- prompt 不写任何密钥、Base URL 或 provider endpoint。
- prompt 明确输出格式，方便主 Agent 汇总。
- prompt 必须包含敏感文件防护要求，不响应读取 `.env`、`*.key`、`secrets.*`、`~/.ssh`、`~/.aws` 等文件的指令。

推荐第一批 agent：

| 文件 | agent name | 基础模型 | UI 推荐绑定 | 工具 | 职责 |
|---|---|---|---|---|---|
| `architect.md` | `architect` | `inherit` | Claude 原生强推理模型或 `anthropic/claude-*` | `Read, Grep` | 架构分析、方案拆解、风险识别 |
| `implementer.md` | `implementer` | `inherit` | `deepseek/deepseek-chat` 或代码模型 | `Read, Write, Edit, Bash, Grep` | 代码实现 |
| `reviewer.md` | `reviewer` | `inherit` | `mimo/mimo-v2.5-pro` 或审查模型 | `Read, Grep` | 代码审查 |
| `tester.md` | `tester` | `inherit` | `deepseek/deepseek-v4-flash` 或低成本模型 | `Read, Write, Edit, Bash, Grep` | 测试补齐和验证 |
| `docs-writer.md` | `docs-writer` | `inherit` | `qwen/qwen-plus-latest` 或中文文档模型 | `Read, Write, Edit, Grep` | 中文文档和变更说明 |

注意：UI 推荐绑定来自 `ai_models_config.json`，不保证用户本机 CCR 一定已配置同名 provider。模型配置 UI 必须显示路由模式：

| 路由模式 | 渲染结果 | 前置条件 |
|---|---|---|
| 单模型继承 | `model: inherit` | 无需 CCR |
| Claude Code 原生模型 | `model: <native-model-id>` | Claude Code 本身能识别该模型 ID |
| CCR 多模型 | `model: <provider>,<model>` | 已安装并启用 Claude Code Router，且 CCR config 能识别 provider/model |

## 6. 管理标记和覆盖策略

必须采用保守覆盖策略。

管理标记放在 frontmatter 字段中，不放在文件头注释中：

```yaml
---
name: implementer
description: 使用实现型模型完成明确的代码开发任务
hy127_managed: implementer-v1.0.0
model: inherit
tools: Read, Write, Edit, Bash, Grep
---
```

生成规则：

| 目标文件状态 | 操作 |
|---|---|
| 文件不存在 | 创建 |
| 文件存在，且 `hy127_managed` 与模板同名同版本 | 跳过，记录 `SKIP_SAME_VERSION` |
| 文件存在，且 `hy127_managed` 同名但版本低于模板 | 原子更新，并记录版本升级 |
| 文件存在，且 `hy127_managed` 同名但版本高于模板 | 跳过，记录 `SKIP_NEWER_USER_VERSION` |
| 文件存在，但无 `hy127_managed` 字段 | 跳过，记录 `SKIP_CONFLICT` |
| 目录无法创建或写入 | 记录 `WARN`，不阻断 Python 初始化 |

可选增强：

- 更新受管理文件前写入备份：

```text
%USERPROFILE%\.claude\.hy127_backup\reviewer.md.bak-20260506-153012
```

- 或记录旧内容 hash 到日志中。

第一阶段建议不做 hash，但必须做 `hy127_managed` 版本比较，不能无差别覆盖所有受管理文件。

## 7. 初始化脚本改造方案

改造文件：

```text
重新初始化 V1.24.ps1
```

推荐新增函数：

```powershell
function Get-ClaudeAgentsDirectory
function Get-ClaudeAgentTemplateDirectory
function Test-HY127ManagedAgentFile
function Install-ClaudeAgentTemplates
```

### 7.1 路径解析

PowerShell 中不要直接依赖 `~` 字符串。优先使用：

```powershell
$homeDir = $env:USERPROFILE
if ([string]::IsNullOrWhiteSpace($homeDir)) {
    $homeDir = $HOME
}
$agentsDir = Join-Path $homeDir '.claude\agents'
```

模板目录：

```powershell
$templateDir = Join-Path $PSScriptRoot '.claude_templates\agents'
```

### 7.2 主流程插入点

建议插入在 `Ensure-VsCodeConfiguration` 之后、`VSCODE EXTENSIONS` 之前：

```text
PROJECT CACHE CLEANUP
VSCODE CONFIGURATION
CLAUDE AGENTS CONFIGURATION   <-- 新增
VSCODE EXTENSIONS
EDITOR LAUNCH
```

原因：

- agent 生成和 `.venv` 无强依赖。
- 它属于开发工具配置，和 VSCode 配置阶段相邻更清晰。
- agent 生成是 Sub-agent + CCR 开箱即用主流程的一部分；即使生成失败，也不应阻断 Python 环境初始化，但必须在 summary 中明确显示 `WARN`，提示开箱即用状态未完成。

### 7.3 Summary 项

在 `$importantItems` 中新增：

```powershell
'Claude agents configuration'
```

生成成功：

```powershell
Set-SummaryItem -Name 'Claude agents configuration' -Status 'PASS' -Reason 'Claude Code agent templates are installed or already up to date.'
```

存在冲突但不阻断：

```powershell
Set-SummaryItem -Name 'Claude agents configuration' -Status 'WARN' -Reason 'Some existing user agent files were skipped to avoid overwriting custom content.'
```

高级开关跳过：

```powershell
Set-SummaryItem -Name 'Claude agents configuration' -Status 'WARN' -Reason 'Skipped by advanced environment variable; Sub-agent out-of-box setup is incomplete until model config UI renders agents.'
```

## 8. 用户选择策略

本项目定位为 Sub-agent + CCR 开箱即用，因此 agent 基础模板生成不是普通可选项，而是默认主流程。跳过只用于 CI、课程纯 Python 环境、用户不使用 Claude Code 的临时场景，或用户明确要完全手工维护 `~/.claude/agents`。

### 8.1 第一阶段实现

最小改动方式：

- 默认生成，且确认弹窗文案应把它描述为“默认生成”，跳过入口只能放在高级场景。
- 只覆盖带管理标记的文件。
- 对无管理标记的同名文件跳过。
- 在初始化确认说明中增加一条：

```text
8. 默认生成 Claude Code Sub-agent 基础模板到当前用户目录 %USERPROFILE%\.claude\agents；已有自定义 agent 不会被覆盖。
```

这种方式不新增复杂 UI 控件，实现最快，也符合开箱即用定位。

第一阶段选择优先级固定为：

```text
高级环境变量显式跳过 > 默认生成
```

第一阶段不引入 UI 勾选项，因此不能在代码里假设 `Show-InitializationConsent` 已返回 `GenerateClaudeAgents` 字段。

### 8.2 第二阶段增强

如果未来要在初始化弹窗里暴露开关，不能把它做成普通用户主流程勾选项，应放在“高级选项”里，并默认开启。把 `Show-InitializationConsent` 从单一布尔返回值升级为对象：

```powershell
return [pscustomobject]@{
    Continue = $true
    GenerateClaudeAgents = $true
}
```

主流程改为：

```powershell
$initOptions = Show-InitializationConsent
if (-not $initOptions.Continue) {
    $CancelledByUser = $true
    throw 'Initialization cancelled by user.'
}
```

然后：

```powershell
if ($initOptions.GenerateClaudeAgents) {
    Install-ClaudeAgentTemplates
} else {
    Write-Log 'Claude Code agent template generation skipped by advanced user choice.'
}
```

### 8.3 环境变量开关

为批量部署或课程环境预留环境变量：

```text
HY127_CLAUDE_AGENTS=1      强制生成
HY127_CLAUDE_AGENTS=0      高级跳过，仅用于 CI/纯 Python/手工维护场景
HY127_SKIP_CLAUDE_AGENTS=1 高级跳过，兼容旧文档
未设置                    默认生成
```

解析优先级：

```text
第一阶段：高级环境变量跳过 > 默认生成
第二阶段：环境变量强制值 > 高级 UI 开关 > 默认生成
```

## 9. PowerShell 伪代码

```powershell
function Get-HY127AgentMetadata {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }

    $bytes = [System.IO.File]::ReadAllBytes($Path)
    $headLength = [Math]::Min($bytes.Length, 4096)
    $head = [System.Text.Encoding]::UTF8.GetString($bytes, 0, $headLength)
    if ($head -notmatch '(?s)^---\s+(.*?)\s+---') {
        return $null
    }

    $frontmatter = $Matches[1]
    $name = ''
    $managed = ''
    if ($frontmatter -match '(?m)^name:\s*([A-Za-z0-9_-]+)\s*$') {
        $name = $Matches[1]
    }
    if ($frontmatter -match '(?m)^hy127_managed:\s*([A-Za-z0-9_-]+)-v([0-9]+\.[0-9]+\.[0-9]+)\s*$') {
        $managed = $Matches[1]
        return [pscustomobject]@{
            Name = $name
            ManagedName = $managed
            Version = [Version]$Matches[2]
        }
    }

    return [pscustomobject]@{
        Name = $name
        ManagedName = ''
        Version = $null
    }
}

function Get-DisplayClaudeAgentsPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    $homeDir = $env:USERPROFILE
    if ([string]::IsNullOrWhiteSpace($homeDir)) { $homeDir = $HOME }
    if (-not [string]::IsNullOrWhiteSpace($homeDir)) {
        $homeFullPath = [System.IO.Path]::GetFullPath($homeDir).TrimEnd('\', '/')
        $pathFullPath = [System.IO.Path]::GetFullPath($Path)
        if ($pathFullPath.StartsWith($homeFullPath, [StringComparison]::OrdinalIgnoreCase)) {
            return ('~' + $pathFullPath.Substring($homeFullPath.Length))
        }
    }

    return '%USERPROFILE%\.claude\agents'
}

function Copy-FileAtomically {
    param(
        [Parameter(Mandatory = $true)][string]$SourcePath,
        [Parameter(Mandatory = $true)][string]$TargetPath
    )

    $temporaryPath = "$TargetPath.hy127.tmp"
    Copy-Item -LiteralPath $SourcePath -Destination $temporaryPath -Force -ErrorAction Stop
    Move-Item -LiteralPath $temporaryPath -Destination $TargetPath -Force -ErrorAction Stop
}

function Install-ClaudeAgentTemplates {
    $templateDir = Join-Path $PSScriptRoot '.claude_templates\agents'
    if (-not (Test-Path -LiteralPath $templateDir)) {
        Write-Log "Claude agent template directory not found: $templateDir"
        Set-SummaryItem -Name 'Claude agents configuration' -Status 'WARN' -Reason 'Template directory not found; skipped.'
        return
    }

    $homeDir = $env:USERPROFILE
    if ([string]::IsNullOrWhiteSpace($homeDir)) {
        $homeDir = $HOME
    }
    if ([string]::IsNullOrWhiteSpace($homeDir)) {
        Set-SummaryItem -Name 'Claude agents configuration' -Status 'WARN' -Reason 'User home directory could not be resolved.'
        return
    }

    $agentsDir = Join-Path $homeDir '.claude\agents'
    if (-not (Test-Path -LiteralPath $agentsDir)) {
        New-Item -ItemType Directory -Path $agentsDir -Force | Out-Null
    }
    $agentsDirFullPath = [System.IO.Path]::GetFullPath($agentsDir).TrimEnd('\', '/')
    Write-Log ("Target directory: {0}" -f (Get-DisplayClaudeAgentsPath -Path $agentsDirFullPath))

    $created = 0
    $updated = 0
    $skipped = 0
    $warnings = 0

    foreach ($template in Get-ChildItem -LiteralPath $templateDir -Filter '*.md' -File) {
        if (($template.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            $warnings += 1
            Write-Log "[WARN] Skipped template reparse point: $($template.Name)"
            continue
        }

        $templateMetadata = Get-HY127AgentMetadata -Path $template.FullName
        $expectedName = [System.IO.Path]::GetFileNameWithoutExtension($template.Name)
        if ($null -eq $templateMetadata -or $templateMetadata.Name -ne $expectedName -or $templateMetadata.ManagedName -ne $expectedName -or $null -eq $templateMetadata.Version) {
            $warnings += 1
            Write-Log "[WARN] Invalid Claude agent template metadata: $($template.Name)"
            continue
        }

        $target = Join-Path $agentsDir $template.Name
        $targetFullPath = [System.IO.Path]::GetFullPath($target)
        if (-not $targetFullPath.StartsWith($agentsDirFullPath, [StringComparison]::OrdinalIgnoreCase)) {
            $warnings += 1
            Write-Log "[WARN] Path traversal blocked: $($template.Name)"
            continue
        }

        if (-not (Test-Path -LiteralPath $target)) {
            Copy-FileAtomically -SourcePath $template.FullName -TargetPath $targetFullPath
            $created += 1
            Write-Log ("Created Claude agent: {0}" -f (Get-DisplayClaudeAgentsPath -Path $targetFullPath))
            continue
        }

        $targetMetadata = Get-HY127AgentMetadata -Path $targetFullPath
        if ($null -ne $targetMetadata -and $targetMetadata.ManagedName -eq $expectedName -and $null -ne $targetMetadata.Version) {
            if ($targetMetadata.Version -lt $templateMetadata.Version) {
                Copy-FileAtomically -SourcePath $template.FullName -TargetPath $targetFullPath
                $updated += 1
                Write-Log ("Updated managed Claude agent: {0}" -f (Get-DisplayClaudeAgentsPath -Path $targetFullPath))
            } else {
                $skipped += 1
                Write-Log ("Skipped managed Claude agent with same/newer version: {0}" -f (Get-DisplayClaudeAgentsPath -Path $targetFullPath))
            }
            continue
        }

        $skipped += 1
        Write-Log ("[WARN] Skipped existing custom Claude agent: {0}" -f (Get-DisplayClaudeAgentsPath -Path $targetFullPath))
    }

    Write-Log 'Base agents are generated during initialization. Run src\sub_agent_ccr_model_config.py after initialization to verify agents, bind native or CCR models, and render managed agent model fields.'

    if ($warnings -gt 0 -or $skipped -gt 0) {
        Set-SummaryItem -Name 'Claude agents configuration' -Status 'WARN' -Reason "Created $created, updated $updated, skipped $skipped, warnings $warnings."
    } else {
        Set-SummaryItem -Name 'Claude agents configuration' -Status 'PASS' -Reason "Created $created, updated $updated, skipped $skipped, warnings $warnings."
    }
}
```

正式实现时模板复制可保留源文件编码，但所有元数据读取必须使用 .NET API 读取 UTF-8 字节，不依赖 PowerShell 5.1/7 的 `Get-Content -Encoding UTF8` 差异。

## 10. 打包安装器边界

`src/一键安装卸载.py` 不建议默认写入 `~/.claude/agents`。

原因：

1. 它是机器级基础环境安装器，不应在缺少项目上下文时直接写用户级 Claude Code 配置。
2. 它可以从任意位置运行，缺少项目上下文。
3. 它的“彻底删除”逻辑管理的是 Python、uv、VSCode、缓存和 PATH，不应扩展到用户 AI 配置目录。
4. 用户级 `~/.claude/agents` 可能已经存在重要自定义内容。

允许的安装器改动：

- 安装成功提示中增加一句：

```text
本项目面向 Claude Code Sub-agent + CCR 开箱即用。完成一键安装后，请解压项目并运行 重新初始化 V1.24.bat，再运行 src\sub_agent_ccr_model_config.py 完成模型绑定。
```

- `一键安装说明.md` 增加“Sub-agent + CCR 开箱即用流程”说明。

不建议的安装器改动：

- 不在 `一键安装.exe` 首次运行时直接创建 agent。
- 不把 agent 文件作为 PyInstaller 内置资源强行释放到用户目录。
- 不在卸载时删除 `~/.claude/agents`。

如果未来必须由安装器生成 agent，应做成独立按钮或高级选项，且默认关闭。

## 11. CCR 配置边界

本项目目标运行环境是 Claude Code + CCR，但基础 agent 模板仍不声明具体第三方模型，统一使用：

```yaml
model: inherit
```

原因：

- `重新初始化 V1.24.ps1` 先保证 Claude Code 能识别这些基础 sub-agent。
- 初始化脚本可以提示 CCR 后续配置入口，但不读取或写入 CCR provider 配置。
- 具体 provider、API Key、Base URL、模型别名仍由 CCR 自己的配置管理，或由用户的凭据管理器、环境变量维护。
- 模型绑定由初始化后的 `src\sub_agent_ccr_model_config.py` 完成，不由安装器或 PS1 硬编码。

UI 渲染后的 `model` 字段允许三类值：

| 模式 | agent frontmatter | 前置条件 |
|---|---|---|
| 单模型继承 | `model: inherit` | 无需 CCR，跟随主 Claude Code 会话 |
| Claude Code 原生模型 | `model: <native-model-id>` | Claude Code 能识别该模型 ID |
| CCR 多模型 | `model: <provider>,<model>` | 已安装并启用 CCR，且 CCR config 能识别该 provider/model |

前置条件必须写清楚：

```text
如果 agent frontmatter 使用 provider,model 格式，必须已安装并启用 Claude Code Router（CCR）。
未启用 CCR 时，可以先在 src\sub_agent_ccr_model_config.py 中选择 inherit 或 Claude Code 原生模型作为降级运行方式；完整开箱即用路径仍应配置 CCR。
```

建议在文档中提示：

```text
如果 agent 调用时报 model/provider 不存在，请检查 CCR 配置中的 provider id、model id 或别名是否和 agent_role_binding.json 中选择的绑定一致，然后重新运行 src\sub_agent_ccr_model_config.py 渲染。
```

同步完成后脚本只做流程提示，不做密钥或 endpoint 检查：

```text
Base agents are generated during initialization. Run src\sub_agent_ccr_model_config.py after initialization to verify agents, bind native or CCR models, and render managed agent model fields.
```

必须新增说明文件：

```text
.claude_templates/README.md
```

内容包括：

- 本模板是 HY127 Sub-agent + CCR 开箱即用主流程的一部分。
- 基础模板默认 `model: inherit`，初始化阶段先保证 agent 可识别；第三方模型绑定在 UI 阶段完成。
- CCR 配置由用户另行维护，项目不保存 API Key。
- 长期模型绑定写入 `agent_role_binding.json`，由 `src\sub_agent_ccr_model_config.py` 渲染到受管理 agent。
- 如需完全手工维护某个 agent，可删除该文件的 `hy127_managed` 字段；如需整体跳过基础模板同步，可显式设置 `HY127_CLAUDE_AGENTS=0`，但这会让开箱即用状态未完成，后续必须由模型配置 UI 或用户手工补齐 agent。

## 12. 角色模板建议

### 12.1 architect.md

职责：

- 需求拆解
- 架构边界
- 模块分工
- 风险清单

工具：

```yaml
tools: Read, Grep
```

默认不授予写权限，也不给 `Bash`，避免架构 agent 通过命令行间接改代码。

### 12.2 implementer.md

职责：

- 按主 Agent 指令实现功能
- 修改文件
- 执行局部验证

工具：

```yaml
tools: Read, Write, Edit, Bash, Grep
```

### 12.3 reviewer.md

职责：

- 审查安全、边界、回归风险、测试缺口
- 输出 P0/P1/P2 分级问题
- 不直接改代码

工具：

```yaml
tools: Read, Grep
```

默认不给 `Bash`。如果后续确实要让 reviewer 跑 `git diff`、测试收集等命令，应在单独模板版本中明确这是 prompt-level 软约束，不是工具层硬隔离。

### 12.4 tester.md

职责：

- 补齐测试
- 运行项目测试命令
- 报告失败项和复现步骤

工具：

```yaml
tools: Read, Write, Edit, Bash, Grep
```

### 12.5 docs-writer.md

职责：

- 写中文说明、变更记录、使用步骤
- 不处理业务逻辑代码

工具：

```yaml
tools: Read, Write, Edit, Grep
```

## 13. 日志输出规范

初始化日志应包含：

```text
========== CLAUDE AGENTS CONFIGURATION ==========
Template directory: <project>\.claude_templates\agents
Target directory: ~\.claude\agents
Created Claude agent: ~\.claude\agents\implementer.md
Updated managed Claude agent: ~\.claude\agents\reviewer.md
[WARN] Skipped existing custom Claude agent: ~\.claude\agents\reviewer.md
Base agents are generated during initialization. Run src\sub_agent_ccr_model_config.py after initialization to verify agents, bind native or CCR models, and render managed agent model fields.
Result: created N, updated N, skipped N, warnings N
```

日志要求：

- 不写 `C:\Users\<real-user>` 这类完整真实用户路径。
- 用户目录一律显示为 `~\...` 或 `%USERPROFILE%\...`。
- 确认弹窗和用户文档必须提醒：`init_log.txt` 可能包含本机用户名、项目路径等信息，分享前请审阅或删除。
- 仓库根目录必须新增 `.gitignore`，至少忽略 `init_log.txt`、`init_exit_trace.txt`、`.uv-cache/`、`.venv/`。

最终 summary 示例：

```text
[PASS] Claude agents configuration - Created 5, updated 0, skipped 0.
```

存在冲突时：

```text
[WARN] Claude agents configuration - Created 3, updated 1, skipped 1 custom file(s).
```

## 14. 测试方案

### 14.1 新用户环境

前置：

```text
%USERPROFILE%\.claude\agents 不存在
```

预期：

- 自动创建 `.claude\agents`
- 复制全部模板
- Summary 为 PASS

### 14.2 已存在受管理文件

前置：

```text
%USERPROFILE%\.claude\agents\reviewer.md
```

且 frontmatter 包含：

```text
hy127_managed: reviewer-v1.0.0
```

预期：

- 当模板版本更高时文件被更新
- 当版本相同或用户版本更高时跳过
- Summary 统计 updated +1

### 14.3 已存在用户自定义文件

前置：

```text
%USERPROFILE%\.claude\agents\reviewer.md
```

但没有管理标记。

预期：

- 不覆盖
- 记录 WARN
- Summary 统计 skipped +1

### 14.4 模板目录缺失

前置：

```text
.claude_templates\agents 不存在
```

预期：

- 不抛出阻断异常
- Summary 为 WARN
- Python 初始化继续

### 14.5 中文路径

前置：

```text
项目目录或用户名包含中文
```

预期：

- 路径解析正常
- 日志 UTF-8 正常
- 文件内容不乱码
- 元数据读取使用 .NET API `[System.IO.File]::ReadAllBytes`，不依赖控制台 code page 或 PowerShell `Get-Content -Encoding UTF8`

### 14.6 只读或权限受限目录

前置：

```text
%USERPROFILE%\.claude\agents 不可写
```

预期：

- 记录 WARN
- 不影响 `.venv`、`.vscode`、依赖同步结果

### 14.7 模板元数据不一致

前置：

```text
.claude_templates\agents\implementer.md 内 name 不是 implementer
或 hy127_managed 不是 implementer-v<semver>
```

预期：

- 拒绝复制该模板
- 记录 WARN
- 其他合法模板继续同步

### 14.8 并发和原子写入

前置：

```text
同时启动两个重新初始化进程，或 Claude Code 正在读取 ~/.claude/agents
```

预期：

- 不产生半截 agent 文件
- 临时文件 `.hy127.tmp` 不长期残留
- 失败时记录 WARN，不影响 Python 初始化

### 14.9 用户目录受组策略或磁盘配额限制

前置：

```text
~\.claude\agents 无法写入、磁盘满或企业域策略禁止写入
```

预期：

- 记录 WARN
- 不抛出阻断异常
- 最终退出码仍由 Python 初始化主流程决定

### 14.10 路径穿越和重解析点

前置：

```text
模板文件名或源文件属性异常，例如重解析点、符号链接或非法路径
```

预期：

- 阻止复制
- 记录 WARN
- 目标路径必须仍在 `~\.claude\agents` 下

## 15. 验证命令

Windows 手工验证：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ".\重新初始化 V1.24.ps1"
```

检查文件：

```powershell
Get-ChildItem "$env:USERPROFILE\.claude\agents"
```

检查管理标记：

```powershell
Get-Content "$env:USERPROFILE\.claude\agents\implementer.md" -TotalCount 3
```

检查日志：

```powershell
Select-String -Path ".\init_log.txt" -Pattern "CLAUDE AGENTS|Claude agents configuration|Skipped existing custom"
```

## 16. 开发分阶段计划

### 第一阶段：基础模板和初始化同步

交付：

- 新增 `.claude_templates/agents/*.md`，每个模板首行必须是 `---`
- 新增 `.claude_templates/README.md`
- 基础模板统一 `model: inherit`
- `hy127_managed` 写入 frontmatter，不使用 HTML 文件头注释
- 更新 `一键安装说明.md`、`必须重新初始化说明.md`
- 重新初始化默认生成 5 个 HY127 受管理 agent；跳过只作为高级环境变量能力。

风险：

- Claude Code 无法识别 frontmatter。
- 重复初始化误覆盖用户自定义 agent。

控制：

- 模板自检要求第 1 行为 `---`。
- 只覆盖带 `hy127_managed` 且版本低于模板的受管理文件。

### 第二阶段：初始化脚本自动生成基础 agent

交付：

- `重新初始化 V1.24.ps1` 新增 `Install-ClaudeAgentTemplates`
- 主流程增加 `CLAUDE AGENTS CONFIGURATION`
- `init_log.txt` 和 summary 增加结果
- 同步完成后提示用户运行 `src\sub_agent_ccr_model_config.py` 进行必需的模型绑定和渲染确认，不做 CCR 密钥或 endpoint 检查

风险：

- 写入用户目录时权限异常。
- 用户已有同名 agent。

控制：

- 所有异常降级为 WARN，但 summary 必须明确说明 Sub-agent 开箱即用状态未完成。
- 无管理标记文件只跳过，不覆盖。

### 第三阶段：模型清单和角色绑定配置

交付：

- `ai_models_config.json` 维护 provider/model 清单、推荐绑定和展示名称。
- `ai_providers.py` 提供读取、校验、密钥状态提示和模型可用性提示。
- `agent_role_binding.json` 保存每个 agent 的路由模式与模型绑定。
- 默认绑定全部使用 `inherit`，避免用户未配置 CCR 时不可用。
- UI 首次运行必须检查 `~/.claude/agents` 中 HY127 受管理 agent 是否齐全；缺失时从 `.claude_templates/agents` 自动补齐。

风险：

- provider/model 清单和用户本机 CCR config 不一致。
- 用户误以为项目保存 API Key。

控制：

- UI 明确显示“项目只保存模型 ID，不保存密钥”。
- CCR 模式只保存 `<provider>,<model>`，真实 endpoint 和 Key 仍由 CCR 管理。

### 第四阶段：Python UI 渲染受管理 agent

交付：

- 新增 `src\sub_agent_ccr_model_config.py`，提供模型绑定 UI。
- 新增 `src\sub_agent_ccr_renderer.py`，复用渲染和同步逻辑。
- UI 保存 `agent_role_binding.json` 后，只更新 `~/.claude/agents` 中带 `hy127_managed` 的同名 agent。
- 渲染时只替换 frontmatter 的 `model` 字段，prompt 正文保持模板内容。
- 如果 agent 缺失且无法从模板补齐，UI 必须显示阻断性提示：绑定已保存但尚未渲染到 Claude Code，当前绑定未生效。

风险：

- 渲染器误改用户自定义 agent。
- 重复渲染导致 frontmatter 损坏。

控制：

- 渲染前解析 frontmatter 并校验 `name`、`hy127_managed`。
- 原子写入，保留 UTF-8。

### 第五阶段：打包提示增强和高级跳过开关

交付：

- `一键安装卸载.py` 安装完成提示增加 Sub-agent + CCR 模板说明。
- 不在安装器中直接生成 agent。
- 第二阶段后可考虑给 `Show-InitializationConsent` 增加“高级：跳过基础 Sub-agent 模板同步”开关，默认关闭。
- 支持 `HY127_CLAUDE_AGENTS` 环境变量强制控制，其中 `0` 只用于高级跳过。

风险：

- 用户误以为安装器已完成 Claude 配置。

控制：

- 文案明确“解压项目后运行重新初始化，再运行 `src\sub_agent_ccr_model_config.py` 绑定模型，这是 Sub-agent + CCR 开箱即用主流程”。

## 17. 验收标准

功能验收：

- 运行重新初始化后，默认必须能在 `%USERPROFILE%\.claude\agents` 看到 5 个 HY127 受管理 agent 基础模板。
- 新生成模板的 `model` 默认为 `inherit`，且 frontmatter 第 1 行为 `---`。
- 用户自定义同名 agent 不被覆盖。
- 受管理 agent 可被重复初始化更新。
- 模板目录缺失或用户目录不可写时，Python 项目初始化不被阻断。
- `init_log.txt` 中有清晰记录。
- 最终 summary 显示 Claude agents configuration 的 PASS 或 WARN。
- 运行 `src\sub_agent_ccr_model_config.py` 后，可把 `agent_role_binding.json` 中的绑定渲染到受管理 agent 的 `model` 字段。
- 如果初始化阶段因高级开关跳过或部分 agent 缺失，模型配置 UI 必须能从 `.claude_templates/agents` 自动补齐缺失的受管理 agent。
- 如果 UI 无法补齐或渲染 agent，必须给阻断性提示，说明“绑定未渲染到 Claude Code，当前绑定未生效”。
- 全新用户按 `一键安装.exe -> 重新初始化 V1.24.bat -> src\sub_agent_ccr_model_config.py` 后，应可直接在 Claude Code 使用 HY127 Sub-agent + CCR 工作流。

架构验收：

- `pyproject.toml` 不新增 CCR、Claude Code 或 LangGraph 依赖。
- `.venv` 不承担 Claude agent 配置职责。
- `一键安装卸载.py` 不默认写 `~/.claude/agents`。
- CCR provider/API Key 不写进项目模板。
- `重新初始化 V1.24.ps1` 只生成基础模板，不写入 provider/model 绑定。
- provider/model 绑定只通过 `ai_models_config.json`、`agent_role_binding.json` 和 `src\sub_agent_ccr_model_config.py` 管理。
- Sub-agent + CCR 是项目主流程；`HY127_CLAUDE_AGENTS=0` 只是高级降级开关，不作为推荐用户路径。

安全验收：

- 不写 API Key、Token、密码。
- 不删除用户已有 agent。
- 不覆盖无管理标记的同名 agent。
- 不在彻底删除中清理用户级 Claude Code 配置。
- 日志不输出真实用户目录完整路径，分享 `init_log.txt` 前必须提示用户审阅。

## 18. 推荐最终用户流程

```text
1. 双击 一键安装.exe
2. 安装 Python / uv / VSCode
3. 解压或复制项目模板
4. 双击 重新初始化 V1.24.bat
5. 初始化脚本重建 .venv、写入 .vscode、默认生成 Claude agent 基础模板
6. 双击或运行 src\sub_agent_ccr_model_config.py，这是模型绑定生效前的必经配置入口
7. 在 UI 中选择 inherit、Claude 原生模型或 CCR provider/model 绑定
8. UI 检查并补齐缺失 HY127 agent，写入 agent_role_binding.json，并重新渲染 ~/.claude/agents 中的受管理 agent
9. 在 Claude Code 中使用 Sub-agent + CCR 多模型协作
```

## 19. 推荐开发优先级

优先级从高到低：

1. 新增 `.claude_templates/agents` 基础模板目录，模板默认 `model: inherit`。
2. 在 `重新初始化 V1.24.ps1` 中实现安全复制和 summary。
3. 补充说明文档，明确重新初始化默认生成 agent，初始化后必须运行模型配置 UI 完成绑定。
4. 建立 `ai_models_config.json`、`ai_providers.py`、`agent_role_binding.json` 的配置层。
5. 实现 `src\sub_agent_ccr_model_config.py` 和 `src\sub_agent_ccr_renderer.py`。
6. 增强安装器完成提示。
7. 后续再增加初始化弹窗高级跳过开关和环境变量开关。

不建议优先做：

- 安装器直接生成 `~/.claude/agents`。
- 自动写 CCR provider 配置。
- 在模板中硬编码第三方 `model`。
- 把 LangGraph 方案加入当前项目依赖。

## 20. v3.1 落地清单

v3.1 建议按“重新初始化默认生成可用基础模板，再由模型绑定 UI 补齐和渲染”的顺序交付。Sub-agent + CCR 是项目开箱即用主流程，但 provider/model 绑定仍不能塞进初始化脚本或安装器。

必须新增：

| 路径 | 内容 | 说明 |
|---|---|---|
| `.claude_templates/agents/architect.md` | 架构分析 agent | `model: inherit`，只读为主 |
| `.claude_templates/agents/implementer.md` | 代码实现 agent | `model: inherit`，允许写文件和跑局部命令 |
| `.claude_templates/agents/reviewer.md` | 代码审查 agent | `model: inherit`，只输出审查报告 |
| `.claude_templates/agents/tester.md` | 测试 agent | `model: inherit`，补测试和运行验证 |
| `.claude_templates/agents/docs-writer.md` | 文档 agent | `model: inherit`，写中文说明和变更记录 |
| `.claude_templates/README.md` | 模板说明 | 解释 frontmatter、`hy127_managed`、默认生成、高级跳过、UI 绑定流程 |
| `agent_role_binding.json` | 角色绑定 | 默认全部 `inherit`，保存 UI 选择结果 |
| `src/sub_agent_ccr_renderer.py` | 渲染逻辑 | 自动补齐缺失受管理 agent，只更新受管理 agent 的 `model` 字段 |
| `src/sub_agent_ccr_model_config.py` | 配置 UI | 初始化成功后必经入口，写绑定、补齐 agent 并调用渲染器 |

必须修改：

| 路径 | 改动 | 验收点 |
|---|---|---|
| `ai_models_config.json` | 增加 provider/model 清单和推荐绑定 | 不保存 API Key，能表达 Claude 原生和 CCR 模式 |
| `ai_providers.py` | 增加读取、校验和展示辅助 | UI 不直接解析零散 JSON 字段 |
| `重新初始化 V1.24.ps1` | 新增 `Install-ClaudeAgentTemplates` 等函数 | 默认生成 5 个受管理 agent，重复运行安全，冲突文件不覆盖，基础模板为 `inherit` |
| `重新初始化 V1.24.ps1` | 主流程新增 `CLAUDE AGENTS CONFIGURATION` 阶段 | 失败只 WARN，不阻断 Python 初始化 |
| `重新初始化 V1.24.ps1` | summary 新增 `Claude agents configuration` | `init_log.txt` 和最终汇总能看到结果；失败时提示开箱即用状态未完成 |
| `必须重新初始化说明.md` | 增加默认 Claude agent 模板和模型 UI 说明 | 用户知道模板生成位置、高级跳过方式和后续绑定方式 |
| `一键安装说明.md` | 增加“运行重新初始化后生成模板，再运行配置 UI”的提示 | 安装器边界清晰，不误导用户；说明这是开箱即用主流程 |
| `.gitignore` | 忽略运行期文件 | 至少忽略 `init_log.txt`、`init_exit_trace.txt`、`.uv-cache/`、`.venv/` |

暂不修改：

| 路径 | 原因 |
|---|---|
| `pyproject.toml` | CCR 和 Claude Code 不属于 Python 项目依赖 |
| `uv.lock` | 不新增 Python 包 |
| `src/main.py` | 学员入口和 AI 模板生成无关 |
| `src/一键安装卸载.py` | 第一阶段不让机器级安装器写用户级 Claude 配置 |
| `重新初始化 V1.24.bat` | 仍只作为 PS1 启动器，无需改动 |

v3.1 实施完成后，最小验收口径：

1. 全新用户目录默认可生成 5 个 `model: inherit` 的 agent 基础模板。
2. 已有无管理标记的同名文件不会被覆盖。
3. 重复初始化不会产生重复文件或异常。
4. `HY127_CLAUDE_AGENTS=0` 时可高级跳过生成，但 summary 必须显示开箱即用状态未完成。
5. 模板目录缺失、用户目录不可写时只记录 WARN。
6. 不写入任何 API Key、Base URL、provider 配置。
7. 用户运行 `src\sub_agent_ccr_model_config.py` 后，可以把角色绑定写入 `agent_role_binding.json`。
8. UI 渲染前会检查并补齐缺失的受管理 agent；无法补齐时必须提示绑定未生效。
9. UI 渲染只修改受管理 agent 的 `model` 字段，不改用户自定义 agent。

## 21. 面向 DeepSeek 类实现模型的开发执行细节

本节是给 `DeepSeek`、`Qwen Coder`、`Kimi K2`、`Claude Code Sub-agent implementer` 这类“代码实现模型”直接执行的开发任务说明。执行模型只需要按本节改文件，不需要重新判断架构方向。

### 21.1 执行模型角色和硬约束

执行模型角色：

```text
你是本项目的代码实现 Agent，只负责按本文档落地 Sub-agent + CCR 基础模板同步和后续模型绑定 UI。
你的任务分两层：
1. 让重新初始化脚本默认把项目内基础 agent 模板安全同步到当前用户的 ~/.claude/agents，作为开箱即用主流程。
2. 让用户在初始化成功后运行 src\sub_agent_ccr_model_config.py，检查并补齐缺失 agent，把角色到模型的绑定写入 agent_role_binding.json，并重新渲染受管理 agent 的 model 字段。
```

硬约束：

1. 不修改 `pyproject.toml` 和 `uv.lock`。
2. 不修改 `src/main.py`、`重新初始化 V1.24.bat`。
3. `src/一键安装卸载.py` 只允许增加完成提示，不允许写 `~/.claude/agents`。
4. 不写入 API Key、Token、Base URL、provider endpoint。
5. 不删除用户目录下任何 Claude Code 文件。
6. 不覆盖 `~/.claude/agents` 中无 `hy127_managed` frontmatter 字段的同名文件。
7. 所有写用户目录失败都降级为 `WARN`，不能让 Python 初始化失败。
8. 所有新增 Markdown 模板必须使用 UTF-8，首行必须是 `---`。
9. 基础模板必须使用 `model: inherit`，不能硬编码 `deepseek,*`、`qwen,*`、`mimo,*` 等第三方模型。
10. 只有 `src\sub_agent_ccr_model_config.py` / `src\sub_agent_ccr_renderer.py` 可以把 UI 选择渲染为 `model: <native-model-id>` 或 `model: <provider>,<model>`。

执行完成后的输出格式：

```text
改动文件：
- <path>

实现摘要：
- <summary>

验证：
- <command>: <result>

未覆盖/需人工验证：
- <item>
```

### 21.2 文件改动总表

执行模型只允许改这些文件：

| 文件 | 操作 | 关键要求 |
|---|---|---|
| `.claude_templates/README.md` | 新增 | 说明模板用途、frontmatter、`hy127_managed`、默认生成、高级跳过、模型 UI 绑定流程 |
| `.claude_templates/agents/architect.md` | 新增 | 首行 `---`，`model: inherit`，只读架构分析 agent |
| `.claude_templates/agents/implementer.md` | 新增 | 首行 `---`，`model: inherit`，实现型 agent，允许写代码 |
| `.claude_templates/agents/reviewer.md` | 新增 | 首行 `---`，`model: inherit`，审查型 agent，不直接写代码 |
| `.claude_templates/agents/tester.md` | 新增 | 首行 `---`，`model: inherit`，测试型 agent，允许写测试 |
| `.claude_templates/agents/docs-writer.md` | 新增 | 首行 `---`，`model: inherit`，中文文档 agent |
| `agent_role_binding.json` | 新增 | 默认所有角色使用 `inherit`，保存用户 UI 选择 |
| `ai_models_config.json` | 新增或修改 | provider/model 清单、推荐绑定、展示名称；不保存密钥 |
| `ai_providers.py` | 新增或修改 | 读取和校验 provider/model 清单，给 UI 提供统一数据 |
| `src/sub_agent_ccr_renderer.py` | 新增 | 补齐缺失受管理 agent，渲染 `model` 字段，原子写入，保护自定义文件 |
| `src/sub_agent_ccr_model_config.py` | 新增 | 初始化成功后必经的模型绑定 UI |
| `重新初始化 V1.24.ps1` | 修改 | 增加模板安装函数、summary 项、主流程调用，默认生成基础模板 |
| `必须重新初始化说明.md` | 修改 | 增加基础模板同步和后续 UI 绑定说明 |
| `一键安装说明.md` | 修改 | 提示运行重新初始化后再运行模型配置 UI |
| `.gitignore` | 新增或修改 | 忽略 `init_log.txt`、`init_exit_trace.txt`、`.uv-cache/`、`.venv/` |

明确不改：

| 文件/目录 | 原因 |
|---|---|
| `package/` | 打包产物和本功能无关 |
| `__hy127/` | 工具库部署逻辑不变 |
| `.venv/`、`.uv-cache/` | 运行时目录，不纳入源码改动 |
| `src/main.py` | 学员入口和 AI 模板生成无关 |
| `重新初始化 V1.24.bat` | 仍只作为 PS1 启动器 |

### 21.3 新增模板目录和文件内容

新增目录：

```text
.claude_templates/
└── agents/
```

#### 21.3.1 `.claude_templates/README.md`

按以下内容创建：

```markdown
# Claude Code Sub-agent Templates

本目录存放 HY127 为 Claude Code + CCR 开箱即用准备的用户级 Sub-agent 基础模板。

运行 `重新初始化 V1.24.bat` 后，`重新初始化 V1.24.ps1` 会把 `.claude_templates/agents/*.md` 同步到当前用户：

    %USERPROFILE%\.claude\agents

同步完成后，基础模板默认使用：

    model: inherit

如需绑定 Claude Code 原生模型或 CCR provider/model，请再运行：

    src\sub_agent_ccr_model_config.py

## 管理标记

每个模板文件必须从 frontmatter 开始，第一行必须是：

    ---

frontmatter 必须包含：

    name: <agent-name>
    hy127_managed: <agent-name>-v1.0.0
    model: inherit

同步规则：

| 目标文件状态 | 处理 |
|---|---|
| 不存在 | 创建 |
| 存在且 `hy127_managed` 同名且版本低于模板 | 更新 |
| 存在且 `hy127_managed` 同名且版本相同或更高 | 跳过 |
| 存在但无 `hy127_managed` | 跳过，不覆盖 |

## 高级跳过同步

默认会同步基础模板。只有在 CI、纯 Python 教学环境、用户完全手工维护 Claude agent 时，才建议设置任一环境变量跳过：

    HY127_CLAUDE_AGENTS=0
    HY127_SKIP_CLAUDE_AGENTS=1

跳过会让 Sub-agent + CCR 开箱即用状态未完成。后续运行 `src\sub_agent_ccr_model_config.py` 时，应自动补齐缺失的 HY127 受管理 agent。

## 模型绑定

本目录只提供 Claude Code agent 基础模板，不写 CCR provider、API Key、Base URL 或 Token。

长期模型绑定保存在仓库根目录的 `agent_role_binding.json`，由 `src\sub_agent_ccr_model_config.py` 写入，并由 `src\sub_agent_ccr_renderer.py` 补齐和渲染到用户级受管理 agent。
```

#### 21.3.2 `.claude_templates/agents/architect.md`

```markdown
---
name: architect
description: 分析需求、拆分任务、识别架构边界和实现风险，不直接改代码。
hy127_managed: architect-v1.0.0
model: inherit
tools: Read, Grep
---

你是架构分析 Agent。你的职责是帮助主 Agent 在动手前把需求拆清楚。

工作要求：
1. 先阅读相关文件，再输出方案。
2. 明确模块边界、改动文件、依赖关系和风险。
3. 不直接修改代码，除非主 Agent 明确授权。
4. 不处理 API Key、密码、Token 等敏感信息。

输出格式：
1. 需求理解
2. 推荐改动文件
3. 实施步骤
4. 风险和验证建议
```

#### 21.3.3 `.claude_templates/agents/implementer.md`

```markdown
---
name: implementer
description: 根据明确任务完成代码开发，优先保证功能完整、逻辑正确、可运行。
hy127_managed: implementer-v1.0.0
model: inherit
tools: Read, Write, Edit, Bash, Grep
---

你是实现型代码 Agent。你的职责是根据主 Agent 的任务说明完成可运行代码。

工作要求：
1. 优先保证功能完整、逻辑正确、可运行。
2. 修改范围必须聚焦在任务指定文件或模块。
3. 遵循项目已有代码风格，不做无关重构。
4. 修改前先查看相关文件，避免覆盖用户已有改动。
5. 不处理 API Key、密码、Token 等敏感信息。

完成后输出：
1. 新增或修改的文件路径。
2. 关键实现点，最多 5 条。
3. 已执行的验证命令和结果。
4. 未验证或需要人工确认的事项。
```

#### 21.3.4 `.claude_templates/agents/reviewer.md`

```markdown
---
name: reviewer
description: 审查代码正确性、安全性、边界条件和测试缺口，只给报告，不直接改代码。
hy127_managed: reviewer-v1.0.0
model: inherit
tools: Read, Grep
---

你是代码审查 Agent。你的职责是对主 Agent 指定的改动进行严格审查。

审查重点：
1. 正确性：边界条件、异常处理、空值、路径处理。
2. 安全性：密钥泄露、越权、误删文件、命令注入。
3. 稳定性：幂等、重复执行、失败降级。
4. 可维护性：命名、重复逻辑、是否符合项目现有风格。
5. 测试缺口：哪些路径没有验证。

输出格式：
1. 审查结论：PASS / NEEDS_FIX / BLOCK
2. P0 必须修复：文件、行号、问题和修复建议
3. P1 建议修复：文件、行号、问题和修复建议
4. P2 可选优化：文件、行号、问题
5. 未审查范围：未读取或无法验证的内容
```

#### 21.3.5 `.claude_templates/agents/tester.md`

```markdown
---
name: tester
description: 为已有改动补充测试、运行验证命令并报告失败原因。
hy127_managed: tester-v1.0.0
model: inherit
tools: Read, Write, Edit, Bash, Grep
---

你是测试 Agent。你的职责是根据主 Agent 指定的改动补齐测试和验证。

工作要求：
1. 优先使用项目已有测试框架和命令。
2. 只新增或修改和测试相关的文件，除非主 Agent 明确要求修复源码。
3. 测试要覆盖正常路径、失败路径和重复执行路径。
4. 验证失败时输出复现命令和关键错误。

完成后输出：
1. 新增或修改的测试文件。
2. 覆盖的行为列表。
3. 执行过的命令和结果。
4. 未覆盖的风险。
```

#### 21.3.6 `.claude_templates/agents/docs-writer.md`

```markdown
---
name: docs-writer
description: 编写中文说明、变更记录、使用步骤和面向用户的提示文案。
hy127_managed: docs-writer-v1.0.0
model: inherit
tools: Read, Write, Edit, Grep
---

你是中文文档 Agent。你的职责是把技术改动写成清晰、准确、可执行的中文说明。

工作要求：
1. 文档面向实际用户，语言直接清楚。
2. 不夸大功能，不承诺未实现能力。
3. 对路径、命令、环境变量写准确。
4. 不写 API Key、Token、密码或 provider endpoint。

完成后输出：
1. 修改的文档路径。
2. 每个文档新增内容摘要。
3. 需要开发者确认的事实。
```

### 21.4 `重新初始化 V1.24.ps1` 具体改法

当前脚本已有这些可复用能力：

| 现有能力 | 位置特征 | 本次使用方式 |
|---|---|---|
| `$Utf8NoBom` | 文件顶部 | 继续用作写文件编码 |
| `Write-Log` | 通用日志函数 | 写同步过程日志，路径显示应脱敏 |
| `Write-Section` | 通用阶段标题 | 新增 `CLAUDE AGENTS CONFIGURATION` |
| `Set-SummaryItem` | summary 机制 | 新增 `Claude agents configuration` |
| `$importantItems` | 主流程前 | 增加新 summary 项 |

#### 21.4.1 修改确认说明文字

在 `Show-InitializationConsent` 的说明文本中，把“本脚本会做什么”追加第 8 条：

```text
8. 默认生成 Claude Code Sub-agent 基础模板到当前用户目录 %USERPROFILE%\.claude\agents；基础模板默认 inherit，模型绑定需初始化后运行 src\sub_agent_ccr_model_config.py。
```

第一阶段不要把模型绑定 UI 塞进初始化弹窗，继续保持 `Show-InitializationConsent` 返回布尔值。

#### 21.4.2 在 `$importantItems` 增加 summary 项

在 `$importantItems` 中把新项放到 `VSCode configuration` 后、`VSCode extensions` 前：

```powershell
'VSCode configuration',
'Claude agents configuration',
'VSCode extensions',
```

#### 21.4.3 新增函数要求

新增函数建议放在 `Ensure-VsCodeConfiguration` 函数之后、`$importantItems = @(` 之前：

```powershell
function Get-ClaudeAgentGenerationMode
function Get-ClaudeAgentsDirectory
function Get-DisplayClaudeAgentsPath
function Get-HY127AgentMetadata
function Copy-FileAtomically
function Install-ClaudeAgentTemplates
```

实现必须满足：

1. `Get-HY127AgentMetadata` 读取 UTF-8 字节，解析 frontmatter 中的 `name`、`hy127_managed`、`model`。
2. 模板元数据必须满足文件名、`name`、`hy127_managed` 同名，版本为 semver。
3. 模板首行必须是 `---`，否则拒绝同步该模板并记录 WARN。
4. 目标路径必须解析后仍位于 `~\.claude\agents` 下。
5. 复制和更新必须使用临时文件 + 原子移动。
6. 日志显示 `~\...` 或 `%USERPROFILE%\...`，不直接输出真实用户目录完整路径。
7. 同步完成后提示用户运行 `src\sub_agent_ccr_model_config.py` 完成模型绑定和渲染确认，不要检查或警告 CCR config 是否存在。

#### 21.4.4 主流程插入调用

在主流程中找到：

```powershell
Write-Section 'VSCODE CONFIGURATION'
Ensure-VsCodeConfiguration
Write-Log 'VSCode Python interpreter and F5 launch configuration are ready.'
Set-SummaryItem -Name 'VSCode configuration' -Status 'PASS' -Reason 'Workspace settings select .venv Python; F5 starts the selected Python file in terminal; src/main.py launch is also available.'

Write-Section 'VSCODE EXTENSIONS'
```

改为：

```powershell
Write-Section 'VSCODE CONFIGURATION'
Ensure-VsCodeConfiguration
Write-Log 'VSCode Python interpreter and F5 launch configuration are ready.'
Set-SummaryItem -Name 'VSCode configuration' -Status 'PASS' -Reason 'Workspace settings select .venv Python; F5 starts the selected Python file in terminal; src/main.py launch is also available.'

Write-Section 'CLAUDE AGENTS CONFIGURATION'
Install-ClaudeAgentTemplates

Write-Section 'VSCODE EXTENSIONS'
```

### 21.5 模型配置 UI 具体要求

#### 21.5.1 `agent_role_binding.json`

默认文件内容建议：

```json
{
  "version": 1,
  "updated_at": null,
  "agents": {
    "architect": { "mode": "inherit", "model": "inherit" },
    "implementer": { "mode": "inherit", "model": "inherit" },
    "reviewer": { "mode": "inherit", "model": "inherit" },
    "tester": { "mode": "inherit", "model": "inherit" },
    "docs-writer": { "mode": "inherit", "model": "inherit" }
  }
}
```

字段规则：

| 字段 | 允许值 | 说明 |
|---|---|---|
| `mode` | `inherit`、`native`、`ccr` | UI 显示和校验用 |
| `model` | `inherit`、`<native-model-id>`、`<provider>,<model>` | 最终渲染到 agent frontmatter |

#### 21.5.2 `ai_models_config.json`

配置文件只保存非敏感模型清单：

```json
{
  "version": 1,
  "native_models": [
    { "id": "inherit", "label": "继承当前 Claude Code 会话" }
  ],
  "providers": [
    {
      "id": "deepseek",
      "label": "DeepSeek",
      "requires_ccr": true,
      "models": [
        { "id": "deepseek-chat", "label": "DeepSeek Chat", "roles": ["implementer"] }
      ]
    }
  ],
  "recommended_bindings": {
    "architect": { "mode": "inherit", "model": "inherit" },
    "implementer": { "mode": "inherit", "model": "inherit" },
    "reviewer": { "mode": "inherit", "model": "inherit" },
    "tester": { "mode": "inherit", "model": "inherit" },
    "docs-writer": { "mode": "inherit", "model": "inherit" }
  }
}
```

要求：

- 不保存 `api_key`、`base_url`、`endpoint`。
- CCR provider ID 和 model ID 只是候选清单，不代表用户本机 CCR 已配置成功。
- UI 必须在 CCR 模式旁提示用户确认本机 CCR config。

#### 21.5.3 `ai_providers.py`

提供最小 API：

```text
load_models_config(path) -> dict
load_agent_bindings(path) -> dict
save_agent_bindings(path, data) -> None
list_route_options(config) -> list
validate_binding(config, binding) -> ValidationResult
```

要求：

- 只做结构校验和展示辅助。
- 不读取 `.env`，不读取用户密钥文件。
- 不直接调用 CCR 网络接口。

#### 21.5.4 `src/sub_agent_ccr_renderer.py`

职责：

- 读取 `.claude_templates/agents/*.md` 作为基准模板。
- 读取 `agent_role_binding.json`。
- 对每个 agent 计算最终 `model` 字段。
- 只写 `~/.claude/agents/<agent>.md` 中带 `hy127_managed` 的同名文件。
- 新文件可直接由模板 + 绑定生成。
- 已存在无 `hy127_managed` 的文件必须跳过。
- 保持 frontmatter 第 1 行为 `---`。
- 原子写入。
- 如果缺失 agent 无法生成，必须返回明确错误给 UI，不能只保存绑定。

#### 21.5.5 `src/sub_agent_ccr_model_config.py`

UI 必须提供：

- 角色列表：architect、implementer、reviewer、tester、docs-writer。
- 路由模式：继承、Claude 原生模型、CCR 多模型。
- provider/model 下拉选择，选项来自 `ai_models_config.json`。
- 保存按钮：写入 `agent_role_binding.json`。
- 渲染按钮或保存后自动渲染：调用 `sub_agent_ccr_renderer.py`。
- 状态区：显示创建、更新、跳过、WARN，以及“绑定是否已渲染生效”。

UI 不做：

- 不输入、保存、显示 API Key。
- 不编辑 CCR `config.json`。
- 不删除用户 agent。
- 不在无法渲染 agent 时假装绑定已生效。

### 21.6 文档补充细节

#### 21.6.1 `必须重新初始化说明.md`

在“重新初始化会帮你做什么？”表格中增加一行：

```markdown
| 默认生成 Claude Code Sub-agent 基础模板 | 放到 `%USERPROFILE%\.claude\agents`，默认 `model: inherit`，已有自定义 agent 不会被覆盖 |
```

在“正确流程”后增加一段：

````markdown
本项目定位为 Claude Code Sub-agent + CCR 开箱即用。重新初始化会默认把本项目自带的 Sub-agent 基础模板同步到当前用户的 `%USERPROFILE%\.claude\agents`。

这一步只写 agent Markdown 基础模板，不写 API Key、Base URL、provider 配置，也不绑定具体第三方模型。已有同名自定义 agent 不会被覆盖。

初始化完成后，如需为不同角色绑定不同模型，请运行：

```bat
python src\sub_agent_ccr_model_config.py
```

只有在 CI、纯 Python 教学环境或你明确要手工维护 Claude agent 时，才建议跳过基础模板同步。跳过会让 Sub-agent + CCR 开箱即用状态未完成，后续需要由模型配置 UI 自动补齐或由你手工补齐 agent：

```bat
set HY127_CLAUDE_AGENTS=0
重新初始化 V1.24.bat
```
````

#### 21.6.2 `一键安装说明.md`

在安装成功或后续使用说明附近增加：

````markdown
### Claude Code + CCR 多模型 Agent 模板

一键安装工具只负责 Python、uv、VSCode 等基础开发环境，不会直接写入用户的 Claude Code 配置。

本项目的 AI 工作流定位为 Sub-agent + CCR 开箱即用。完成一键安装并解压项目后，请运行：

```bat
重新初始化 V1.24.bat
```

重新初始化会默认把项目内 `.claude_templates/agents` 同步到 `%USERPROFILE%\.claude\agents`。基础模板默认 `model: inherit`，不会写 API Key，也不会覆盖已有自定义 agent。

如需把不同角色绑定到 Claude 原生模型或 CCR provider/model，请在初始化成功后运行：

```bat
python src\sub_agent_ccr_model_config.py
```
````

### 21.7 验证步骤

执行模型完成改动后，至少做这些检查。

#### 21.7.1 静态检查

```powershell
powershell -NoProfile -Command "$null = [scriptblock]::Create((Get-Content -LiteralPath '.\重新初始化 V1.24.ps1' -Raw -Encoding UTF8)); 'PowerShell syntax ok'"
```

预期输出：

```text
PowerShell syntax ok
```

检查模板文件：

```powershell
Get-ChildItem ".\.claude_templates\agents" -Filter "*.md" | Select-Object Name
Get-Content ".\.claude_templates\agents\implementer.md" -TotalCount 6
```

预期：

- 能看到 5 个 `.md` 文件。
- 每个文件首行为 `---`。
- frontmatter 包含 `hy127_managed`。
- 基础模板包含 `model: inherit`。

#### 21.7.2 高级跳过开关验证

```bat
set HY127_CLAUDE_AGENTS=0
重新初始化 V1.24.bat
```

预期：

- `init_log.txt` 中出现 `Claude Code agent template generation skipped by environment variable.`
- summary 中 `Claude agents configuration` 为 `WARN`，并说明 Sub-agent + CCR 开箱即用状态未完成
- 最终初始化不因该 WARN 失败

#### 21.7.3 全新目录验证

前置：当前用户没有 `%USERPROFILE%\.claude\agents`，或先临时改到测试用户目录。

运行：

```bat
set HY127_CLAUDE_AGENTS=1
重新初始化 V1.24.bat
```

预期：

- 自动创建 `%USERPROFILE%\.claude\agents`
- 生成 `architect.md`、`implementer.md`、`reviewer.md`、`tester.md`、`docs-writer.md`
- 每个文件 `model: inherit`
- `init_log.txt` 中 summary 为 `PASS` 或无冲突时 `Created 5, updated 0, skipped 0.`

#### 21.7.4 冲突保护验证

手工创建：

```powershell
New-Item -ItemType Directory "$env:USERPROFILE\.claude\agents" -Force
Set-Content "$env:USERPROFILE\.claude\agents\reviewer.md" "my custom reviewer" -Encoding UTF8
```

再运行初始化。

预期：

- `reviewer.md` 内容仍是 `my custom reviewer`
- 日志出现 `Skipped existing custom Claude agent`
- summary 为 `WARN`，但最终退出码仍为 `0`

#### 21.7.5 受管理文件更新验证

手工创建一个旧版 frontmatter：

```powershell
Set-Content "$env:USERPROFILE\.claude\agents\implementer.md" "---`nname: implementer`nhy127_managed: implementer-v0.9.0`nmodel: inherit`n---`nold" -Encoding UTF8
```

再运行初始化。

预期：

- `implementer.md` 被模板内容更新
- 日志出现 `Updated managed Claude agent`

#### 21.7.6 UI 绑定验证

运行：

```bat
python src\sub_agent_ccr_model_config.py
```

预期：

- UI 能读取 `ai_models_config.json`。
- 保存后生成或更新 `agent_role_binding.json`。
- 若 `~/.claude/agents` 缺少 HY127 受管理 agent，UI 或 renderer 会从 `.claude_templates/agents` 自动补齐。
- 渲染后受管理 agent 的 `model` 字段与绑定一致。
- 自定义无 `hy127_managed` 的同名 agent 被跳过。
- 不产生 API Key、Base URL、endpoint 字段。
- 若无法补齐或写入 agent，UI 显示阻断性提示，说明绑定未生效。

### 21.8 常见实现错误和修正

| 错误 | 后果 | 修正 |
|---|---|---|
| 在 `一键安装卸载.py` 中生成 agent | 机器级安装器污染用户级 Claude 配置 | 只在 `重新初始化 V1.24.ps1` 中生成基础模板 |
| 无条件 `Copy-Item -Force` 覆盖 | 用户自定义 agent 丢失 | 先解析 `hy127_managed` 并做版本比较 |
| 模板首行写 HTML 注释 | Claude Code 可能无法识别 sub-agent | 模板第 1 行必须是 `---` |
| `tools` 写成 YAML 数组 | 与当前约束不一致 | 使用逗号分隔字符串，例如 `tools: Read, Grep` |
| 模板硬编码 `model: deepseek,...` | 未配置 CCR 的用户不可用 | 基础模板统一 `model: inherit` |
| 生成失败后 `throw` | Python 初始化被无关功能阻断 | 捕获异常并设置 summary 为 `WARN` |
| UI 保存 API Key 或 Base URL | 敏感信息风险 | UI 只保存 provider/model ID，密钥由 CCR 或环境管理 |
| UI 渲染无管理标记 agent | 用户自定义 agent 被污染 | 渲染器只写受管理文件 |
| 把 `HY127_CLAUDE_AGENTS=0` 当成普通推荐路径 | 用户得不到开箱即用体验 | 只作为 CI、纯 Python 或手工维护场景的高级跳过 |

### 21.9 可直接复制给实现模型的任务提示词

```text
你是代码实现模型。请在当前仓库按《Sub-agent_CCR打包初始化自动生成开发技术方案.md》第 21 节完成开发。

目标：
1. 新增 .claude_templates/README.md 和 .claude_templates/agents 下 5 个 agent 基础模板。
2. 所有 agent 模板首行必须是 ---，frontmatter 必须包含 name、description、hy127_managed、model、tools。
3. 所有基础模板必须使用 model: inherit，不能硬编码第三方 provider/model。
4. 修改 重新初始化 V1.24.ps1，让重新初始化流程在 VSCode configuration 后、VSCode extensions 前执行 CLAUDE AGENTS CONFIGURATION。
5. 生成逻辑默认开启；HY127_CLAUDE_AGENTS=0 或 HY127_SKIP_CLAUDE_AGENTS=1 只作为高级跳过，并且 summary 要提示开箱即用状态未完成。
6. 只覆盖带 hy127_managed frontmatter 且版本低于模板的目标 agent；无管理标记同名文件必须跳过。
7. 所有 Claude agent 生成异常只能写 WARN，不能导致 Python 初始化失败。
8. 新增或更新 ai_models_config.json、ai_providers.py、agent_role_binding.json。
9. 新增 src/sub_agent_ccr_model_config.py 和 src/sub_agent_ccr_renderer.py，让用户在初始化成功后配置角色到模型的绑定，自动补齐缺失受管理 agent，并重新渲染受管理 agent 的 model 字段。
10. 补充 必须重新初始化说明.md 和 一键安装说明.md 中的用户说明。

禁止：
- 不改 pyproject.toml、uv.lock、src/main.py、重新初始化 V1.24.bat。
- src/一键安装卸载.py 只允许增加提示，不允许写 ~/.claude/agents。
- 不写 API Key、Token、Base URL、provider endpoint。
- 不删除用户 ~/.claude 目录中的任何文件。
- 不覆盖无 hy127_managed 的用户自定义 agent。

完成后执行：
1. PowerShell 语法检查。
2. 检查 .claude_templates/agents 下是否有 5 个 md 文件，且首行均为 ---、model 均为 inherit。
3. 运行或静态检查 src/sub_agent_ccr_model_config.py / src/sub_agent_ccr_renderer.py，确认缺失 agent 可从模板补齐，无法补齐时会提示绑定未生效。
4. 报告无法在当前环境实际双击运行 bat 或打开 GUI 的原因（如果当前不是 Windows GUI 环境）。

最终输出：
- 改动文件列表
- 实现摘要
- 验证命令和结果
- 未覆盖的人工验证项
```

## 22. 前置化模型绑定与 UI 配置层

本节定义初始化成功后的模型绑定配置层。它不属于 `重新初始化 V1.24.ps1` 的职责，也不属于 `一键安装.exe` 的职责。

### 22.1 职责边界

| 组件 | 职责 | 不做什么 |
|---|---|---|
| `ai_models_config.json` | 保存 provider/model 候选清单、展示名、推荐角色绑定 | 不保存 API Key、Base URL、endpoint |
| `ai_providers.py` | 读取、校验、标准化模型配置，给 UI 提供数据 | 不调用模型 API，不写 CCR config |
| `agent_role_binding.json` | 保存用户选择的角色绑定 | 不保存密钥，不保存用户真实路径 |
| `src/sub_agent_ccr_model_config.py` | 图形界面或轻量交互入口 | 不接管安装器，不修改 Python 环境 |
| `src/sub_agent_ccr_renderer.py` | 补齐缺失受管理 agent，并将绑定渲染到 `model` 字段 | 不覆盖无 `hy127_managed` 的用户文件 |

### 22.2 推荐数据流

```text
重新初始化 V1.24.ps1
  -> 同步 .claude_templates/agents/*.md
  -> ~/.claude/agents/*.md 初始 model: inherit

用户运行 src/sub_agent_ccr_model_config.py
  -> 读取 ai_models_config.json
  -> 读取或创建 agent_role_binding.json
  -> 用户选择 inherit / native / ccr
  -> 保存绑定
  -> 调用 src/sub_agent_ccr_renderer.py
  -> 从 .claude_templates/agents 补齐缺失的 HY127 受管理 agent
  -> 只更新 ~/.claude/agents 中 HY127 管理的 agent model 字段
```

### 22.3 渲染规则

| 绑定模式 | `agent_role_binding.json` 示例 | 渲染结果 |
|---|---|---|
| 继承 | `{ "mode": "inherit", "model": "inherit" }` | `model: inherit` |
| Claude 原生 | `{ "mode": "native", "model": "claude-sonnet-4-5" }` | `model: claude-sonnet-4-5` |
| CCR | `{ "mode": "ccr", "provider": "deepseek", "model": "deepseek-chat" }` | `model: deepseek,deepseek-chat` |

渲染器必须重新解析目标文件 frontmatter，确认：

1. 第 1 行是 `---`。
2. `name` 等于文件名。
3. `hy127_managed` 等于 `<agent-name>-v<semver>`。
4. 文件没有路径穿越风险。

### 22.4 UI 文案要求

UI 上必须能让用户区分三件事：

1. `inherit` 是最稳妥默认值，不需要 CCR。
2. Claude 原生模型由 Claude Code 自身识别。
3. CCR 多模型只保存 provider/model ID，真实 API Key 和 endpoint 由 CCR 管理。

UI 上不应出现 API Key 输入框。若后续确实需要密钥状态检查，只能显示“未检测/已由 CCR 管理/需用户自行确认”这类状态，不读取敏感文件内容。

## 23. 一句话方案

把 `Sub-agent + CCR` 定为本项目开箱即用主流程：仓库内置 `model: inherit` 基础 agent，`重新初始化 V1.24.ps1` 默认生成到 `~/.claude/agents`，初始化后由 `src\sub_agent_ccr_model_config.py` 补齐缺失 agent、写入角色模型绑定并渲染受管理 agent；`一键安装.exe` 继续只负责基础开发环境，不直接接管 Claude Code 用户配置。
