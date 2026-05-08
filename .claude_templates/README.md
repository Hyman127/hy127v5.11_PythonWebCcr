# Claude Code Sub-agent Templates

本目录存放 HY127 为 Claude Code + CCR 开箱即用准备的用户级 Sub-agent 基础模板。

运行 `重新初始化 V1.24.bat` 后，`重新初始化 V1.24.ps1` 会把 `.claude_templates/agents/*.md` 同步到当前用户：

    %USERPROFILE%\.claude\agents

同步完成后，基础模板默认使用：

    model: inherit

如需绑定 Claude Code 原生模型或 CCR provider/model（包括火山方舟 Coding Plan），请再运行：

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
| 存在且 `hy127_managed` 同名且版本低于模板 | 更新（更新前备份到 `.hy127_backup`） |
| 存在且 `hy127_managed` 同名且版本相同或更高 | 跳过 |
| 存在但无 `hy127_managed` | 跳过，不覆盖 |

## 高级跳过同步

默认会同步基础模板。只有在 CI、纯 Python 教学环境、用户完全手工维护 Claude agent 时，才建议设置环境变量跳过：

    HY127_CLAUDE_AGENTS=0
    HY127_SKIP_CLAUDE_AGENTS=1

跳过会让 Sub-agent + CCR 开箱即用状态未完成。后续运行 `src\sub_agent_ccr_model_config.py` 时，会自动补齐缺失的 HY127 受管理 agent。

## 模型绑定

本目录只提供 Claude Code agent 基础模板，不写 CCR provider、API Key、Base URL 或 Token。

长期模型绑定保存在仓库根目录的 `agent_role_binding.json`，由 `src\sub_agent_ccr_model_config.py` 写入，由 `src\sub_agent_ccr_renderer.py` 补齐并渲染到用户级受管理 agent。

## 火山方舟 Coding Plan

如需把某个角色绑定到 Ark Coding Plan，在模型绑定 UI 中选择 CCR 模式，provider 选 `ark_coding_plan`，再选具体模型。

注意：

- `ark_coding_plan` 与普通 `doubao` provider 是两套独立 provider，base_url 不同，API Key 不同，不能混用。
- CCR 鉴权（provider id、API Key、endpoint）须用户自行配置 CCR config，本仓库不写入任何密钥。
- `ark-code-latest` 通过控制台统一管理模型版本，切换后约 3-5 分钟生效，不推荐作为日常快速切换默认值。
