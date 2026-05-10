# AI 模型与运行模式映射实施方案

## 目标

根据 `方案设计/方案参考/AI模型-最新.md` 增设“模型与运行模式映射”（Provider Runtime Compatibility Matrix），让普通用户在选择 Provider 与运行方式（直接 API / Claude Code / Codex / Gemini / Qwen Code）时，不需要理解底层协议差异，系统自动切换 `api_base`、协议、模型 ID 与提示信息。

## 设计原则

1. 运行方式是用户意图，协议与入口地址是底层实现细节。
2. 不同 Provider 对同一个运行方式的支持分三类：
   - 官方兼容：例如 DeepSeek + Claude Code 走 DeepSeek Anthropic API。
   - API 壳兼容：例如 Codex/Qwen Code 运行方式走 OpenAI-compatible API，并使用对应运行方式提示词。
   - 不建议或缺资料：前端展示提示，允许用户手工改映射。
3. 映射表必须可视化、可编辑、可恢复默认值。
4. 聊天请求必须在后端按映射生成“有效模型配置”，避免用户只切换运行方式但模型仍旧走旧 `api_base`。
5. 连通测试是必要能力：Provider 文档、模型 ID、区域与账号权限经常变动，必须给用户一个按当前映射实际请求的测试入口。

## 后端实现

新增 `hy127web/hub/provider_runtime_matrix.py`：

1. 内置默认矩阵：
   - DeepSeek：
     - `api/codex/qwen/gemini` 默认走 `https://api.deepseek.com/v1` + `openai_chat` + `deepseek-v4-pro`。
     - `claude` 走 `https://api.deepseek.com/anthropic` + `anthropic_messages` + `deepseek-v4-pro[1m]`。
   - Doubao / Volcano Ark Coding：
     - OpenAI-compatible 走 `https://ark.cn-beijing.volces.com/api/coding/v3`。
     - Claude Code 走 `https://ark.cn-beijing.volces.com/api/coding` + `anthropic_messages`。
   - Qwen：
     - 标准 API 走 `https://dashscope.aliyuncs.com/compatible-mode/v1`。
     - Claude Code 可走百炼 Coding Plan 的 `https://coding.dashscope.aliyuncs.com/apps/anthropic`。
   - GLM/Z.AI：
     - OpenAI-compatible 走 `https://api.z.ai/api/openai/v1`。
     - Claude Code 走 `https://api.z.ai/api/anthropic`。
   - OpenAI、Anthropic、Gemini、Kimi、MiniMax、Hunyuan、StepFun、OpenRouter 等按当前可确认协议配置默认入口，并对非官方运行壳显示提示。
2. 持久化用户覆盖：
   - 文件路径：`<global_dir>/provider_runtime_matrix.json`。
   - 保存完整矩阵，不存 API Key。
   - 支持重置为默认。
3. Provider 推断：
   - 对历史 `custom` 模型，根据 `api_base` 自动推断 DeepSeek、Ark、DashScope、Z.AI、Moonshot、OpenRouter 等 Provider，从而让旧模型也能套用映射。
4. 请求时自动套用：
   - `/internal/ai/relay` 收到 `runtime` 后，使用矩阵把原模型转换为有效模型配置。
   - API Key 仍沿用用户当前模型保存的 Key。
   - 只覆盖 `api_base`、`protocol`、`model_id` 等运行必要字段，不改写用户模型文件。
5. 新增接口：
   - `GET /api/hub/provider-runtime-matrix`：读取当前矩阵。
   - `PUT /api/hub/provider-runtime-matrix`：保存矩阵。
   - `POST /api/hub/provider-runtime-matrix/reset`：恢复默认矩阵。
   - `POST /api/hub/provider-runtime-matrix/resolve`：查看某 Provider + Runtime 的实际映射。
   - `POST /api/hub/models/{id}/test-runtime`：按指定 Runtime 与映射测试当前模型连通性。

## 前端实现

在模型配置弹窗中新增“映射”页：

1. 展示 Provider + Runtime 组合的矩阵。
2. 允许手工修改：
   - 是否启用。
   - 是否自动套用。
   - 是否官方兼容。
   - API Base。
   - 协议。
   - 模型 ID。
   - 模型名称。
   - 角色能力。
   - 提示说明。
3. 支持保存与恢复默认。
4. 在“编辑模型”页增加当前映射提示：
   - 显示该 Provider + Runtime 将使用的 `api_base / protocol / model_id`。
   - 提供“套用映射到表单”按钮。
   - 提供“测试映射”按钮，调用后端 `test-runtime`。
5. Provider 或 Runtime 变更时自动套用对应映射到表单，降低用户手工配置成本。

## 连通测试与提示

有必要增加，原因：

1. 多 Provider 的“兼容”经常有账号权限、区域、套餐、模型 ID 后缀差异。
2. Claude Code 壳与 Anthropic-compatible API 对 `thinking/tool_use/tool_result` 字段更敏感，必须能用实际链路验证。
3. 连接失败时，用户需要看到是 HTTP、协议、模型 ID、Key 权限，还是空响应问题。

测试策略：

1. “编辑模型”页测试当前保存模型。
2. “映射”相关测试按指定 Runtime 自动套用矩阵后测试。
3. 测试不保存 API Key，不把 Key 写入映射文件。

## 验证计划

1. 增加后端单元测试覆盖：
   - DeepSeek + Claude Code 映射到 Anthropic API。
   - 历史 custom 模型根据 `api_base` 推断 Provider。
   - 用户覆盖矩阵可保存、读取、重置。
2. 执行 Python 编译检查。
3. 执行现有 pytest。
4. 执行前端脚本语法检查。

