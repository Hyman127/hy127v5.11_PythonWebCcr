# 火山方舟 Coding Plan 手工模型配置

本文记录本项目接入火山方舟 Coding Plan 的手工配置方式。结论来自火山方舟 Claude Code 官方指引、截图中的配置方式，以及本项目 2026-05-07 的实际验证。

> **当前仓库适用范围说明**
>
> 本文档部分章节依赖以下资源，**当前仓库（`hy127v5.11_multi-orchestration_CCR`）不包含这些文件**，对应章节仅作参考，不作为本仓库落地要求：
>
> | 依赖资源 | 本仓库是否存在 | 对应章节 |
> |---|---|---|
> | `scripts/claude-ark.sh` | ❌ 不存在 | 本项目启动器配置、不等 3-5 分钟的切换办法 |
> | `scripts/import_ark_coding_models.py` | ❌ 不存在 | Web 工作台手工 Provider 配置 |
> | `.hy127web_global/` | ❌ 不存在 | Web 工作台手工 Provider 配置、迁移到其他项目 |
>
> **本仓库直接适用的内容**：
> - [协议和 Base URL](#协议和-base-url)：两个入口的区分规则
> - [Claude Code 官方手工配置](#claude-code-官方手工配置)：通过 `~/.claude/settings.json` 配置
> - [排障记录](#排障记录)：400、401、控制字符、Base URL 错误处理

## 结论

推荐日常使用“具体 Model Name”模式，不推荐频繁依赖 `ark-code-latest` 去控制台切换。

两种切换方式的差异：

| 方式 | 配置模型 | 切换速度 | 适用场景 |
| --- | --- | --- | --- |
| 具体模型名 | `kimi-k2.5` / `deepseek-v3.2` / `doubao-seed-code-preview-latest` 等 | 立即生效 | 日常快速切换，推荐 |
| 控制台统一管理 | `ark-code-latest` | 控制台切换后约 3-5 分钟生效 | 多工具统一跟随控制台默认模型 |

本项目已经验证通过的 Claude Code 命令：

```bash
ENABLE_TOOL_SEARCH=0 bash scripts/claude-ark.sh ark-code-latest --model ark-code-latest -p '只输出 OK 两个字母，不要解释。' --output-format text --no-session-persistence
```

成功输出：

```text
→ using ANTHROPIC_AUTH_TOKEN from .hy127web_global
→ ANTHROPIC_MODEL=ark-code-latest
OK
```

## 协议和 Base URL

Coding Plan 有两类入口，不要混用：

| 工具协议 | Base URL | 用途 |
| --- | --- | --- |
| Anthropic 兼容 | `https://ark.cn-beijing.volces.com/api/coding` | Claude Code |
| OpenAI 兼容 | `https://ark.cn-beijing.volces.com/api/coding/v3` | Web 工作台、自定义 OpenAI-compatible provider |

注意：

- 不要使用普通方舟 API Base：`https://ark.cn-beijing.volces.com/api/v3`。
- 不要使用普通 ModelArk API Key。这里需要 Coding Plan 专属 API Key。
- Claude Code 使用 `ANTHROPIC_AUTH_TOKEN`，不要让旧的 `ANTHROPIC_API_KEY` 影响鉴权路径。

## Claude Code 官方手工配置

官方截图中的核心思路是配置 Claude Code 的 settings/env。Linux/macOS 路径：

```text
~/.claude/settings.json
```

示例，使用具体模型名，切换不用等 3-5 分钟：

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "https://ark.cn-beijing.volces.com/api/coding",
    "ANTHROPIC_AUTH_TOKEN": "你的 Coding Plan API Key",
    "ANTHROPIC_MODEL": "kimi-k2.5",
    "ANTHROPIC_SMALL_FAST_MODEL": "kimi-k2.5"
  }
}
```

如需控制台统一管理，才把模型设为：

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "https://ark.cn-beijing.volces.com/api/coding",
    "ANTHROPIC_AUTH_TOKEN": "你的 Coding Plan API Key",
    "ANTHROPIC_MODEL": "ark-code-latest",
    "ANTHROPIC_SMALL_FAST_MODEL": "ark-code-latest"
  }
}
```

启动后可用 `/status` 查看当前模型和连接状态。需要临时切换时，优先用：

```bash
claude --model kimi-k2.5
claude --model deepseek-v3.2
claude --model doubao-seed-code-preview-latest
```

在 Claude Code 对话里也可以用：

```text
/model kimi-k2.5
/model deepseek-v3.2
/model doubao-seed-code-preview-latest
```

## 本项目启动器配置

本项目推荐使用：

```bash
bash scripts/claude-ark.sh <provider|model-id> --model <model-id>
```

启动器位置：

```text
scripts/claude-ark.sh
```

当前内置别名：

| 别名 | 实际模型 |
| --- | --- |
| `latest` | `ark-code-latest` |
| `auto` | `ark-code-latest` |
| `deepseek` | `ark-code-latest` |
| `doubao` | `doubao-seed-code-preview-latest` |

也可以直接传完整模型 ID。为避免 Claude Code 使用旧 settings 里的模型别名，建议同时显式传 `--model`：

```bash
ENABLE_TOOL_SEARCH=0 bash scripts/claude-ark.sh kimi-k2.5 --model kimi-k2.5 -p '只输出 OK 两个字母，不要解释。' --output-format text --no-session-persistence
ENABLE_TOOL_SEARCH=0 bash scripts/claude-ark.sh deepseek-v3.2 --model deepseek-v3.2 -p '只输出 OK 两个字母，不要解释。' --output-format text --no-session-persistence
ENABLE_TOOL_SEARCH=0 bash scripts/claude-ark.sh doubao-seed-code-preview-latest --model doubao-seed-code-preview-latest -p '只输出 OK 两个字母，不要解释。' --output-format text --no-session-persistence
```

如果只验证当前默认模型：

```bash
ENABLE_TOOL_SEARCH=0 bash scripts/claude-ark.sh ark-code-latest --model ark-code-latest -p '只输出 OK 两个字母，不要解释。' --output-format text --no-session-persistence
```

## Web 工作台手工 Provider 配置

Web 工作台按 OpenAI-compatible provider 保存模型，使用 `/api/coding/v3`。

通用字段：

| 字段 | 值 |
| --- | --- |
| Provider / 服务商 | `custom` / 自定义 |
| API Base | `https://ark.cn-beijing.volces.com/api/coding/v3` |
| API Key | Coding Plan API Key |
| Protocol / 协议 | `openai_chat` / OpenAI-compatible |
| Runtime / 运行方式 | `api` |
| Enabled | `true` |

推荐手工配置多个具体模型，而不是只配 `ark-code-latest`：

| 名称 | Model ID | 说明 |
| --- | --- | --- |
| Ark Kimi K2.5 | `kimi-k2.5` | 需要快速切换时直接选 |
| Ark DeepSeek V3.2 | `deepseek-v3.2` | 需要快速切换时直接选 |
| Ark Doubao Preview | `doubao-seed-code-preview-latest` | 当前项目脚本已内置 |
| Ark Code Latest | `ark-code-latest` | 控制台统一管理时使用 |

当前项目导入脚本默认只写入两个模型：

```text
Ark Code Latest    -> ark-code-latest
Ark Doubao Preview -> doubao-seed-code-preview-latest
```

查看已保存的方舟模型：

```bash
jq '.models[]?
  | select((.api_base // "") | contains("ark.cn-beijing.volces.com"))
  | {name,model_id,api_base,protocol,runtime,enabled,is_default,roles}' \
  .hy127web_global/models.json
```

导入或更新默认脚本配置：

```bash
export ARK_CODING_PLAN_API_KEY='你的 Coding Plan API Key'
.venv/bin/python scripts/import_ark_coding_models.py --default-model ark-code-latest
```

切默认模型：

```bash
.venv/bin/python scripts/import_ark_coding_models.py --default-model doubao-seed-code-preview-latest
.venv/bin/python scripts/import_ark_coding_models.py --default-model ark-code-latest
```

## 不等 3-5 分钟的切换办法

如果你要马上切换模型，不走控制台切换 `ark-code-latest`。

推荐命令：

```bash
bash scripts/claude-ark.sh kimi-k2.5 --model kimi-k2.5
bash scripts/claude-ark.sh deepseek-v3.2 --model deepseek-v3.2
bash scripts/claude-ark.sh doubao-seed-code-preview-latest --model doubao-seed-code-preview-latest
```

快速验证只跑一次短请求：

```bash
ENABLE_TOOL_SEARCH=0 bash scripts/claude-ark.sh kimi-k2.5 --model kimi-k2.5 -p '只输出 OK 两个字母，不要解释。' --output-format text --no-session-persistence
```

避免用会多轮重试的调试命令长时间等待。只有排障时才加：

```bash
--debug api --debug-file /tmp/claude-ark-debug.log
```

## 配置文件说明

| 文件 | 作用 | 是否建议迁移 |
| --- | --- | --- |
| `~/.claude/settings.json` | Claude Code 官方全局配置，适合所有项目共用 | 可以迁移，注意保护 Key |
| `.claude.env` | 本项目 Claude Code 启动器读取的项目级配置 | 可复制模板，不建议带真实 Key 入库 |
| `.hy127web_global/models.json` | Web 工作台模型元数据 | 可迁移 |
| `.hy127web_global/keys/api_keys.enc` | Web 工作台保存的 API Key | 可迁移但敏感，Windows DPAPI 场景可能不可跨机器 |
| `scripts/claude-ark.sh` | 本项目 Claude Code 方舟启动器 | 应随项目保留 |
| `scripts/import_ark_coding_models.py` | 导入/更新 Web 工作台方舟模型配置 | 应随项目保留 |

本项目 `.claude.env` 至少需要：

```bash
ANTHROPIC_BASE_URL=https://ark.cn-beijing.volces.com/api/coding
ANTHROPIC_AUTH_TOKEN=
```

如果 `ANTHROPIC_AUTH_TOKEN` 留空，`scripts/claude-ark.sh` 会尝试从 `.hy127web_global` 读取已导入的 Coding Plan Key。

## 迁移到其他项目

推荐迁移方式：使用共享全局目录，不把密钥散落到每个项目。

在 shell 配置里加入：

```bash
export HY127WEB_GLOBAL_DIR="$HOME/.hy127web_global"
```

首次导入：

```bash
export ARK_CODING_PLAN_API_KEY='你的 Coding Plan API Key'
.venv/bin/python scripts/import_ark_coding_models.py --global-dir "$HY127WEB_GLOBAL_DIR" --default-model ark-code-latest
```

其他项目只需要：

```bash
export HY127WEB_GLOBAL_DIR="$HOME/.hy127web_global"
cp .claude.env.example .claude.env
```

并确认 `.claude.env` 里有：

```bash
ANTHROPIC_BASE_URL=https://ark.cn-beijing.volces.com/api/coding
ANTHROPIC_AUTH_TOKEN=
```

如果想直接复制本项目的 Web 工作台配置，复制：

```text
.hy127web_global/models.json
.hy127web_global/keys/api_keys.enc
```

复制后检查权限：

```bash
chmod 700 .hy127web_global .hy127web_global/keys
chmod 600 .hy127web_global/models.json .hy127web_global/keys/api_keys.enc
```

## 排障记录

本项目实测中过的坑：

1. 旧 Key 复制时带入了不可见 `ESC` 控制字符，导致 Node/Claude Code 报：

```text
Invalid character in header content ["x-api-key"]
```

检查方式，只输出统计，不打印密钥：

```bash
.venv/bin/python - <<'PY'
import unicodedata
from hy127web.hub.models_manager import ModelsManager
m = ModelsManager('.hy127web_global/models.json', '.hy127web_global/keys')
for model in m.list_models():
    if 'ark.cn-beijing.volces.com' in (model.get('api_base') or ''):
        key = m.get_api_key(model['id']) or ''
        bad = [
            ch for ch in key
            if ord(ch) < 32 or ord(ch) == 127 or unicodedata.category(ch).startswith('C')
        ]
        print(f"{model.get('model_id')}: key_len={len(key)} bad_control_count={len(bad)}")
PY
```

正常结果应类似：

```text
ark-code-latest: key_len=46 bad_control_count=0
```

2. `API Error: 400 Bad Request` 不一定是网络问题。优先检查：

- `ANTHROPIC_BASE_URL` 是否是 `https://ark.cn-beijing.volces.com/api/coding`。
- 是否使用 Coding Plan 专属 API Key。
- 是否误用了 `ANTHROPIC_API_KEY` 或旧环境变量。
- 是否显式传了 `--model <目标模型>`。

3. 清洗掉控制字符后如果变成：

```text
401 AuthenticationError: The API key format is incorrect
```

说明 Key 本身不是有效 Coding Plan Key，或不是从官方 Coding Plan/API Key 管理页复制出来的完整 Key。

4. 最终通过的关键条件：

- 新 Key 长度正常，且无控制字符。
- 使用 `ANTHROPIC_AUTH_TOKEN`。
- Claude Code 走 `https://ark.cn-beijing.volces.com/api/coding`。
- 命令显式传入 `--model ark-code-latest` 或具体 Model Name。

## 参考

- 火山方舟官方 Claude Code 文档：`https://www.volcengine.com/docs/82379/1928262`
- 官方文档页面显示最近更新时间：`2026-05-07 10:57:47`
