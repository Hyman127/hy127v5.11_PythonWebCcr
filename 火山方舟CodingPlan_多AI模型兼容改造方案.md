# 火山方舟 Coding Plan 多 AI 模型兼容改造方案

> 范围：当前仓库 `hy127v5.11_multi-orchestration_CCR` 的 `ai_models_config.json`、`ai_providers.py`、`agent_role_binding.json`、`src/sub_agent_ccr_model_config.py`、`src/sub_agent_ccr_renderer.py` 与相关说明文档。
>
> 依据：`火山方舟CodingPlan_手工模型配置.md` 与当前仓库实际文件结构。当前仓库不存在 `scripts/claude-ark.sh`、`scripts/import_ark_coding_models.py`、`.hy127web_global`，因此这些内容不作为本仓库落地前提。

## 1. 总体结论

火山方舟 Coding Plan 必须作为独立 provider 接入，不能复用当前 `doubao` provider。

原因：

- 当前 `doubao` provider 使用普通方舟 API：`https://ark.cn-beijing.volces.com/api/v3`。
- 火山方舟 Coding Plan 的 OpenAI-compatible 入口是：`https://ark.cn-beijing.volces.com/api/coding/v3`。
- 火山方舟 Coding Plan 的 Claude Code / Anthropic-compatible 入口是：`https://ark.cn-beijing.volces.com/api/coding`。
- Coding Plan 需要 Coding Plan 专属 API Key；不能混用普通 ModelArk API Key。
- Claude Code 侧使用 `ANTHROPIC_AUTH_TOKEN`，不要让旧的 `ANTHROPIC_API_KEY` 影响鉴权路径。

本仓库的安全落地路径是：

1. 在 `ai_models_config.json` 新增独立 provider：`ark_coding_plan`。
2. 不修改现有 `doubao` provider。
3. 不把 Ark Coding Plan 模型加入 `native_models` 默认列表。
4. 通过 CCR 模式暴露 Ark Coding Plan 多模型选项：`ark_coding_plan,kimi-k2.5` 等。
5. 不写入任何 API Key、Token、真实用户路径或 CCR provider 配置。

## 2. 协议边界

| 使用场景 | 协议 | Base URL | 本仓库处理方式 |
|---|---|---|---|
| Claude Code 整体切到 Ark Coding Plan | Anthropic-compatible | `https://ark.cn-beijing.volces.com/api/coding` | 只写说明文档，不默认写入、不自动修改 `~/.claude/settings.json` |
| CCR / OpenAI-compatible provider | OpenAI-compatible | `https://ark.cn-beijing.volces.com/api/coding/v3` | 新增 `ark_coding_plan` provider 候选清单，由用户自行配置 CCR 鉴权 |
| 现有普通豆包 API | OpenAI-compatible | `https://ark.cn-beijing.volces.com/api/v3` | 保留现有 `doubao` provider，不混用 |

关键规则：

- `doubao` 与 `ark_coding_plan` 是两套 provider。
- `deepseek-v3.2` 是 Ark Coding Plan 提供的部署，不等于当前 `deepseek` provider 下的官方 API 模型列表。
- `kimi-k2.5` 会同时出现在 Moonshot API 与 Ark Coding Plan 中，UI label 必须区分来源。

## 3. native_models 策略

不建议把 Ark Coding Plan 模型加入 `native_models`。

原因：如果 agent frontmatter 写入：

```yaml
model: kimi-k2.5
```

它只有在用户已经把 Claude Code 整体配置为 Ark Coding Plan 时才有效，例如：

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "https://ark.cn-beijing.volces.com/api/coding",
    "ANTHROPIC_AUTH_TOKEN": "Coding Plan API Key",
    "ANTHROPIC_MODEL": "kimi-k2.5",
    "ANTHROPIC_SMALL_FAST_MODEL": "kimi-k2.5"
  }
}
```

如果用户仍使用默认 Anthropic 端点，Claude Code 会把 `kimi-k2.5` 当作 Anthropic 原生模型名请求，通常表现为 400 错误，错误信息不会自然指向“Base URL 配错”。

因此本仓库默认策略：

- `native_models` 不新增 `kimi-k2.5`、`deepseek-v3.2`、`doubao-seed-code-preview-latest`、`ark-code-latest`。
- Ark 模型只通过 `mode: ccr` 暴露。
- 若未来确实要提供 native Ark 选项，UI 必须做阻断性说明：“仅限已把 Claude Code 整体切换到 Ark Coding Plan 时使用”，不能只靠普通 label 提醒。

## 4. ai_models_config.json 改造

新增 provider：`ark_coding_plan`。

示例结构：

```json
{
  "providers": {
    "ark_coding_plan": {
      "display_name": "火山方舟 Coding Plan",
      "base_url": "https://ark.cn-beijing.volces.com/api/coding/v3",
      "api_type": "openai_compatible",
      "env_key": "ARK_CODING_PLAN_API_KEY",
      "requires_ccr": true,
      "models": [
        {
          "id": "kimi-k2.5",
          "label": "Ark Kimi K2.5（Coding Plan）",
          "roles": ["architect", "implementer"]
        },
        {
          "id": "deepseek-v3.2",
          "label": "Ark DeepSeek V3.2（Coding Plan）",
          "roles": ["reviewer", "implementer"]
        },
        {
          "id": "doubao-seed-code-preview-latest",
          "label": "Ark Doubao Seed Code Preview（Coding Plan）",
          "roles": ["implementer"]
        },
        {
          "id": "ark-code-latest",
          "label": "Ark Code Latest（控制台统一管理，约 3-5 分钟生效）",
          "roles": []
        }
      ]
    }
  }
}
```

说明：

- `base_url` / `env_key` 是 `AIProviderManager` 直接调用层字段，不写入 `agent_role_binding.json`，也不写入 agent frontmatter。
- Sub-agent + CCR 绑定层只读取 `provider`、`model`、`label`、`roles`、`requires_ccr`。
- `recommended_bindings` 保持全 `inherit`，不默认把任何角色绑到 Ark。
- **`env_key: ARK_CODING_PLAN_API_KEY` 不是 CCR 鉴权来源**。设置该环境变量对 CCR 没有任何自动效果；CCR 是否能路由到 Ark Coding Plan、使用哪个 Key，完全取决于用户自己的 CCR config。本仓库不保证、也不检查 CCR config 是否存在或正确。

## 5. 同名模型 label 规则

必须区分同名模型来源，尤其是 `kimi-k2.5`。

建议 label：

| provider | model id | label |
|---|---|---|
| `moonshot` | `kimi-k2.5` | `Kimi K2.5（Moonshot API）` |
| `ark_coding_plan` | `kimi-k2.5` | `Ark Kimi K2.5（Coding Plan）` |
| `deepseek` | `deepseek-*` | `DeepSeek ...（DeepSeek API）` |
| `ark_coding_plan` | `deepseek-v3.2` | `Ark DeepSeek V3.2（Coding Plan）` |

当前 UI 的 `list_route_options()` 已按 provider 展示候选项，因此大多数情况下只改配置 label 即可；如果 UI 后续改为只显示模型名，必须保留 provider 前缀。

## 6. agent_role_binding.json 表达方式

Ark Coding Plan 通过 CCR 绑定表达：

```json
{
  "mode": "ccr",
  "provider": "ark_coding_plan",
  "model": "kimi-k2.5"
}
```

渲染到 agent frontmatter：

```yaml
model: ark_coding_plan,kimi-k2.5
```

可选角色建议，不作为默认值：

```json
{
  "agents": {
    "architect": { "mode": "ccr", "provider": "ark_coding_plan", "model": "kimi-k2.5" },
    "implementer": { "mode": "ccr", "provider": "ark_coding_plan", "model": "doubao-seed-code-preview-latest" },
    "reviewer": { "mode": "ccr", "provider": "ark_coding_plan", "model": "deepseek-v3.2" },
    "tester": { "mode": "ccr", "provider": "ark_coding_plan", "model": "kimi-k2.5" },
    "docs-writer": { "mode": "inherit", "model": "inherit" }
  }
}
```

默认仍保持全 `inherit`，降低首次使用失败概率。

## 7. UI 改造

`src/sub_agent_ccr_model_config.py` 不需要接管 Ark API Key，也不需要写 CCR config。

需要保证：

1. 下拉选项明确显示 provider 来源。
2. `Ark Kimi K2.5（Coding Plan）` 与 `Kimi K2.5（Moonshot API）` 不会混淆。
3. CCR 模式旁继续提示：“需要已安装并启用 CCR，且 CCR config 中存在同名 provider/model”。
4. 对 `ark-code-latest` 增加说明：控制台切换后约 3-5 分钟生效，不推荐日常快速切换。
5. 不展示 API Key 输入框。
6. 不读取 `.claude/settings.json`、`.claude.env` 或任何密钥文件。

`validate_binding()` 不需要新增专门代码。它已经是配置驱动的：只要 `ark_coding_plan` 写入 `ai_models_config.json`，且模型 ID 在该 provider 的 `models` 中，就会自动通过校验。

## 8. 文档改造

需要补充说明文档，重点是“本仓库适用内容”和“不适用内容”。

应保留：

- 协议和 Base URL 对照表。
- Claude Code 官方手工配置路径：`~/.claude/settings.json`。
- `ANTHROPIC_AUTH_TOKEN` 与 `ANTHROPIC_API_KEY` 的区别。
- `ark-code-latest` 与具体模型名的切换差异。
- 排障记录：400、401、控制字符污染、Base URL 错误。

应明确不适用：

- 当前仓库没有 `scripts/claude-ark.sh`。
- 当前仓库没有 `scripts/import_ark_coding_models.py`。
- 当前仓库没有 `.hy127web_global`。
- 不要求实现模型创建这些文件。
- 不要求把 Web 工作台模型导入逻辑搬进本仓库。

建议更新文件：

| 文件 | 改动 |
|---|---|
| `一键安装说明.md` | 增加 Ark Coding Plan 只作为可选多模型 provider，安装器不写 Key、不写 Claude Code 全局配置 |
| `必须重新初始化说明.md` | 增加运行模型配置 UI 后可选择 `ark_coding_plan`，但用户需自行配置 CCR |
| `火山方舟CodingPlan_手工模型配置.md` | 标注哪些段落适用于本仓库，哪些段落来自其他项目/Web 工作台 |

可选新增：

```text
.claude.env.example
```

如果新增，只能作为人工参考模板，不应被当前代码默认读取或写入真实 Key：

```bash
ANTHROPIC_BASE_URL=https://ark.cn-beijing.volces.com/api/coding
ANTHROPIC_AUTH_TOKEN=
ANTHROPIC_MODEL=kimi-k2.5
ANTHROPIC_SMALL_FAST_MODEL=kimi-k2.5
```

## 9. 验证方案

无需真实 API Key 的本地验证：

1. JSON 格式检查：

```bash
python3 -m json.tool ai_models_config.json >/dev/null
```

2. UI 候选项检查：

```bash
python3 - <<'PY'
from ai_providers import load_models_config, list_route_options, validate_binding
c = load_models_config('ai_models_config.json')
opts = list_route_options(c)
for o in opts:
    if o.get('provider') == 'ark_coding_plan':
        print(o)
assert any(o.get('provider') == 'ark_coding_plan' and o.get('model_id') == 'kimi-k2.5' for o in opts)
assert validate_binding(c, {'mode':'ccr','provider':'ark_coding_plan','model':'kimi-k2.5'}).ok
assert validate_binding(c, {'mode':'ccr','provider':'ark_coding_plan','model':'deepseek-v3.2'}).ok
PY
```

3. 渲染器隔离验证 — 基础模板（inherit 绑定）：

```bash
tmp="$(mktemp -d)"
HY127_TEST_AGENTS_DIR="$tmp" python3 src/sub_agent_ccr_renderer.py --bindings agent_role_binding.json
find "$tmp" -maxdepth 1 -type f -name '*.md' -print
rm -rf "$tmp"
```

4. 渲染器隔离验证 — Ark CCR 绑定（必须确认 `ark_coding_plan,model` 真实写入 frontmatter）：

```bash
tmp="$(mktemp -d)"
bindings="$(mktemp)"
cat > "$bindings" <<'JSON'
{
  "agents": {
    "architect":   { "mode": "ccr", "provider": "ark_coding_plan", "model": "kimi-k2.5" },
    "implementer": { "mode": "ccr", "provider": "ark_coding_plan", "model": "doubao-seed-code-preview-latest" },
    "reviewer":    { "mode": "ccr", "provider": "ark_coding_plan", "model": "deepseek-v3.2" },
    "tester":      { "mode": "ccr", "provider": "ark_coding_plan", "model": "kimi-k2.5" },
    "docs-writer": { "mode": "inherit", "model": "inherit" }
  }
}
JSON
HY127_TEST_AGENTS_DIR="$tmp" python3 src/sub_agent_ccr_renderer.py --bindings "$bindings"
grep -n "model: ark_coding_plan,kimi-k2.5"                      "$tmp/architect.md"   && echo "architect ✓"
grep -n "model: ark_coding_plan,doubao-seed-code-preview-latest" "$tmp/implementer.md" && echo "implementer ✓"
grep -n "model: ark_coding_plan,deepseek-v3.2"                  "$tmp/reviewer.md"    && echo "reviewer ✓"
grep -n "model: ark_coding_plan,kimi-k2.5"                      "$tmp/tester.md"      && echo "tester ✓"
grep -n "model: inherit"                                         "$tmp/docs-writer.md" && echo "docs-writer ✓"
rm -rf "$tmp" "$bindings"
```

预期：5 个 agent 均 grep 命中，输出 5 行 `✓`。此步骤才能证明 Ark CCR 绑定被正确写入 agent frontmatter。仅用默认 `agent_role_binding.json`（全 inherit）的验证无法覆盖该场景。

真实联通性验证不放进自动测试。需要用户已完成以下任一配置：

- CCR 中已有 `ark_coding_plan` provider，指向 `https://ark.cn-beijing.volces.com/api/coding/v3` 并使用 Coding Plan API Key。
- 或用户手工把 Claude Code 全局切换到 Ark Coding Plan，再手工测试 native 模型名。

## 10. 验收标准

改造完成后应满足：

1. `ai_models_config.json` 中存在 `ark_coding_plan` provider。
2. 现有 `doubao` provider 不被改成 `/api/coding/v3`。
3. `native_models` 默认不包含 Ark Coding Plan 模型。
4. UI 中能看到 `Ark Kimi K2.5（Coding Plan）`、`Ark DeepSeek V3.2（Coding Plan）`、`Ark Doubao Seed Code Preview（Coding Plan）`。
5. `agent_role_binding.json` 可保存：

```json
{ "mode": "ccr", "provider": "ark_coding_plan", "model": "kimi-k2.5" }
```

6. renderer 输出：

```yaml
model: ark_coding_plan,kimi-k2.5
```

7. 不新增任何真实 Key。
8. 不要求存在 `scripts/claude-ark.sh`、`.hy127web_global` 或 Web 工作台导入脚本。
9. `ark-code-latest` 的 UI label 必须包含"控制台统一管理"或"约 3-5 分钟生效"字样，不能只保留 model ID。文档同样明确不推荐作为日常快速切换默认值。

## 11. 实施顺序

1. 更新 `ai_models_config.json`：新增 `ark_coding_plan`，不动 `doubao`。
2. 调整同名模型 label：尤其是 `moonshot/kimi-k2.5` 与 `ark_coding_plan/kimi-k2.5`。
3. 保持 `native_models` 不加入 Ark Coding Plan 模型。
4. 更新说明文档，明确两个 Base URL、认证方式、当前仓库不存在的脚本和 Web 工作台目录。
5. 运行本地配置驱动验证，确认 `validate_binding()` 自动接受 `ark_coding_plan`。
6. 可选新增 `.claude.env.example`，但不把它接入自动写入流程。

## 12. 不做事项

- 不写 `~/.claude/settings.json`。
- 不写 CCR `config.json`。
- 不保存 Coding Plan API Key。
- 不创建 `scripts/claude-ark.sh`。
- 不创建 `.hy127web_global`。
- 不把普通 `doubao` provider 改成 Coding Plan。
- 不把 Ark Coding Plan 模型默认写入 `native_models`。

