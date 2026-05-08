# 全球主流 AI 编程模型汇总（2026 年 5 月）

> 更新日期：2026-05-08
> 聚焦：编程 / Coding 能力，含 API 定价、模型 ID、上下文窗口、编程基准测试成绩。

---

## 编程能力排行速览

| 模型 | SWE-bench Verified | 输入价格 / M tokens | 输出价格 / M tokens | 上下文窗口 |
|------|-------------------|--------------------|--------------------|-----------|
| DeepSeek V4-Pro | 80.6% | $0.30 | $0.50 | 1M |
| Kimi K2.6 | 80.2% | $0.55~0.75 | $2.65~3.50 | 256K |
| DeepSeek V4-Flash | 79.0% | $0.14 | $0.28 | 1M |
| Qwen3.6 Plus | 78.8% | $0.325 | $1.95 | 1M |
| GLM-5.1 | 77.8% | $1.05 | $3.50 | 202K |
| Kimi K2.5 | 76.8% | $0.60 | $2.50 | 256K |
| 腾讯混元 Hy3 | 74.4% | ¥1.2 | ¥4.0 | 262K |

**性价比之王**：DeepSeek V4-Flash（$0.14/M）、StepFun Step 3.5 Flash（$0.10/M）
**编程最强**：DeepSeek V4-Pro（80.6% SWE-bench Verified）
**Agent 编排最强**：Kimi K2.6（原生 Agent Swarm 架构）
**编程专用最便宜**：Qwen3 Coder Next（$0.11/M 输入）

---

## 1. DeepSeek 深度求索

### DeepSeek V4-Pro

| 属性 | 值 |
|------|-----|
| 模型 ID | `deepseek-v4-pro` |
| 发布日期 | 2026-04-24 |
| 架构 | 1.6T 总参 / 49B 激活参数（MoE） |
| 上下文窗口 | 1,000,000 tokens（最大输出 384K） |
| 编程基准 | SWE-bench Verified 80.6%，LiveCodeBench 93.5% |
| API 定价 | 输入 $0.30/M，输出 $0.50/M |
| 折扣 | 75% 折扣至 2026/05/31（实际 $0.075/$0.125）；缓存命中 $0.03/M |
| 协议 | OpenAI-compatible |
| Base URL | `https://api.deepseek.com/v1` |
| 开源 | MIT |

### DeepSeek V4-Flash

| 属性 | 值 |
|------|-----|
| 模型 ID | `deepseek-v4-flash` |
| 发布日期 | 2026-04-24 |
| 架构 | 284B 总参 / 13B 激活参数（MoE） |
| 上下文窗口 | 1,000,000 tokens |
| 编程基准 | SWE-bench Verified 79.0% |
| API 定价 | 输入 $0.14/M，输出 $0.28/M；缓存命中 $0.014/M |
| 协议 | OpenAI-compatible |
| Base URL | `https://api.deepseek.com/v1` |

### DeepSeek V3.2（旧版，仍可用）

| 属性 | 值 |
|------|-----|
| 模型 ID | `deepseek-chat`（将于 2026/07/24 弃用） |
| 上下文窗口 | 128,000 tokens |
| API 定价 | 输入 $0.28/M，输出 $0.42/M |

> **注意**：`deepseek-chat` 和 `deepseek-reasoner` 将于 2026/07/24 弃用，目前映射到 V4-Flash 的非思考/思考模式。

---

## 2. Kimi / Moonshot AI 月之暗面

### Kimi K2.6（最新）

| 属性 | 值 |
|------|-----|
| 模型 ID | `kimi-k2.6` |
| 发布日期 | 2026 年 3-4 月 |
| 架构 | MoE，多模态 |
| 上下文窗口 | 256,000 tokens |
| 编程基准 | SWE-bench Verified 80.2%，SWE-bench Pro 58.6% |
| API 定价 | 输入 $0.55~0.75/M，输出 $2.65~3.50/M |
| 协议 | OpenAI-compatible |
| Base URL | `https://api.moonshot.ai/v1` |
| 核心优势 | Agent Swarm 架构，长周期编程任务，UI/UX 生成 |

### Kimi K2.5

| 属性 | 值 |
|------|-----|
| 模型 ID | `kimi-k2.5` |
| 发布日期 | 2026-01-27 |
| 上下文窗口 | 256,000 tokens |
| 编程基准 | SWE-bench 76.8%，BrowseComp 74.9% |
| API 定价 | 输入 $0.60/M，输出 $2.50/M |
| 协议 | OpenAI-compatible + Anthropic-compatible |
| 核心优势 | 开源，多模态，支持最多 100 个并行子代理 |

### Kimi K2

| 属性 | 值 |
|------|-----|
| 模型 ID | `kimi-k2` |
| 架构 | MoE 基座模型 |
| 核心优势 | 代码和 Agent 能力突出，GitHub 开源 |

---

## 3. Qwen 通义千问 / 阿里巴巴

### Qwen3.6 Max Preview（旗舰）

| 属性 | 值 |
|------|-----|
| 模型 ID | `qwen3.6-max-preview` |
| 发布日期 | 2026 年 4 月 |
| 上下文窗口 | 260,000 tokens |
| 编程基准 | 2026/04/20 六项编程榜单第一（SWE-bench Pro, Terminal-Bench 2.0, SkillsBench） |
| API 定价 | 输入 $1.30/M，输出 $7.80/M |
| 协议 | OpenAI-compatible |
| Base URL | `https://dashscope.aliyuncs.com/compatible-mode/v1` |

### Qwen3.6 Plus

| 属性 | 值 |
|------|-----|
| 模型 ID | `qwen3.6-plus` |
| 发布日期 | 2026-03-31 |
| 上下文窗口 | 1,000,000 tokens（最大输出 65,536） |
| 编程基准 | SWE-bench Verified 78.8% |
| API 定价 | 输入 $0.325/M，输出 $1.95/M |

### Qwen3 Coder Next（编程专用）

| 属性 | 值 |
|------|-----|
| 模型 ID | `qwen3-coder-next` |
| 发布日期 | 2026-02-04 |
| 架构 | 基于 Qwen3-Next-80B-A3B-Base，混合注意力 + MoE |
| 上下文窗口 | 262,144 tokens |
| API 定价 | 输入 $0.11/M，输出 $0.80/M |
| 核心优势 | 多轮工具调用，仓库级代码理解，Agent 工具兼容 |

### Qwen3 Coder Plus

| 属性 | 值 |
|------|-----|
| 模型 ID | `qwen3-coder-plus` |
| 发布日期 | 2025-09-23 |
| 上下文窗口 | 1,000,000 tokens |
| API 定价 | 输入 $0.65/M，输出 $3.25/M |
| 核心优势 | 极复杂编程任务最高质量 |

### 阿里云百炼 Coding Plan

| 属性 | 值 |
|------|-----|
| OpenAI Base URL | `https://coding.dashscope.aliyuncs.com/v1` |
| Anthropic Base URL | `https://coding.dashscope.aliyuncs.com/apps/anthropic` |
| 标准 API Base URL | `https://dashscope.aliyuncs.com/compatible-mode/v1` |

---

## 4. 字节豆包 Doubao / 火山方舟

### Doubao-Seed-2.0-Code（编程专用）

| 属性 | 值 |
|------|-----|
| 模型 ID | `doubao-seed-2.0-code` |
| 发布日期 | 2026-02-14 |
| 上下文窗口 | 256,000 tokens |
| API 定价 | 输入 ¥3.2/M（32K 内），输出 ¥16/M（约 $0.47/$2.37） |
| 协议 | OpenAI-compatible + Anthropic-compatible |
| 核心优势 | 代码仓库解读，项目规范代码生成，Agent 工作流纠错，视觉输入，函数调用，推理模式 |

### Doubao-Seed-2.0-Pro（通用）

| 属性 | 值 |
|------|-----|
| 模型 ID | `doubao-seed-2.0-pro` |
| 定价 | 同 Code 模型 |

### 火山方舟 Coding Plan（多模型订阅平台）

| 属性 | 值 |
|------|-----|
| Anthropic Base URL | `https://ark.cn-beijing.volces.com/api/coding` |
| OpenAI Base URL | `https://ark.cn-beijing.volces.com/api/coding/v3` |
| 可用模型 | doubao-seed-2.0-code, doubao-seed-2.0-pro, doubao-seed-2.0-lite, kimi-k2.6, kimi-k2.5, glm-5.1, glm-4.7, minimax-m2.7, minimax-m2.5, deepseek-v3.2 |
| 套餐 | Lite / Pro 两档，按额度计费 |
| 支持工具 | Claude Code, Cursor, Cline, VSCode 扩展等 10+ AI 编程工具 |

---

## 5. 智谱 GLM / Z.AI

### GLM-5.1

| 属性 | 值 |
|------|-----|
| 模型 ID | `glm-5.1` |
| 发布日期 | 2026-04-07 |
| 架构 | 754B MoE / 40B 激活参数 |
| 上下文窗口 | 202,752 tokens（最大输出 65,535） |
| 编程基准 | SWE-bench Pro 58.4%（开源权重 SOTA） |
| API 定价 | 输入 $1.05/M，输出 $3.50/M |
| 协议 | OpenAI-compatible + Anthropic-compatible |
| OpenAI Base URL | `https://api.z.ai/api/openai/v1` |
| Anthropic Base URL | `https://api.z.ai/api/anthropic` |
| 开源 | MIT |
| Coding Plan | Lite 套餐 $18/月起，含 GLM-5.1, GLM-5-Turbo, GLM-4.7, GLM-4.5-Air |
| 核心优势 | 8 小时自主任务执行，从规划到生产级交付 |

---

## 6. 腾讯混元 Hunyuan

### Hy3 Preview（混元 3）

| 属性 | 值 |
|------|-----|
| 模型 ID | `hy3-preview` |
| 发布日期 | 2026 年 2 月 |
| 架构 | 295B MoE / 21B 激活参数 |
| 上下文窗口 | 262,144 tokens |
| 编程基准 | SWE-bench Verified 74.4%，BrowseComp 67.1% |
| API 定价 | 输入 ¥1.2/M，输出 ¥4.0/M（约 $0.17/$0.57） |
| 协议 | OpenAI-compatible |
| 开源 | MIT |

---

## 7. 小米 MiMo

### MiMo-V2.5-Pro（最新）

| 属性 | 值 |
|------|-----|
| 模型 ID | `mimo-v2.5-pro` |
| 发布日期 | 2026-04-22 |
| 架构 | 1T 总参 / 42B 激活参数（MoE），多模态（文本/图像/音频/视频） |
| 上下文窗口 | 1,048,576 tokens（最大输出 131,072） |
| 编程基准 | SWE-bench Pro 57.2%，ClawEval 64% Pass3 |
| API 定价 | 输入 $1.00/M，输出 $3.00/M（1M 上下文 4 倍系数） |
| 协议 | OpenAI-compatible |
| Base URL | `platform.xiaomimimo.com`（OpenAI-compatible） |

### MiMo-V2-Pro

| 属性 | 值 |
|------|-----|
| 模型 ID | `mimo-v2-pro` |
| 发布日期 | 2026-03-18 |
| 编程基准 | Claw-Eval 75.7（全球前三） |

### MiMo-V2-Flash

| 属性 | 值 |
|------|-----|
| 开源 | GitHub（XiaomiMiMo/MiMo-V2-Flash），高效推理模型 |

---

## 8. MiniMax

### MiniMax M2.7

| 属性 | 值 |
|------|-----|
| 模型 ID | `MiniMax-M2.7` |
| 发布日期 | 2026-03-18 |
| 上下文窗口 | 204,800 tokens（最大输出 131,072） |
| 编程基准 | SWE-Pro 56.2%，Terminal Bench 2 57.0% |
| API 定价 | 输入 $0.30/M，输出 $1.20/M |
| 协议 | OpenAI-compatible |
| Base URL | `https://api.minimax.io`（API Key）/ `https://api.minimaxi.com`（OAuth） |
| 核心优势 | 原生多 Agent 协作，技能编排 |

---

## 9. 阶跃星辰 StepFun

### Step 3.5 Flash

| 属性 | 值 |
|------|-----|
| 模型 ID | `step-3.5-flash` |
| 发布日期 | 2026-01-29 |
| 架构 | 196B MoE / 11B 激活参数 |
| 上下文窗口 | 256,000 tokens |
| API 定价 | 输入 $0.10/M，输出 $0.30/M（最便宜之一） |
| 协议 | OpenAI-compatible |
| 核心优势 | 推理速度 350 tokens/s，工具调用，函数调用 |

### Step 3

| 属性 | 值 |
|------|-----|
| 模型 ID | `step3` |
| API 定价 | 输入 $0.57/M，输出 $1.42/M |

---

## 10. 百度文心 ERNIE

### ERNIE 5.0

| 属性 | 值 |
|------|-----|
| 发布日期 | 2026-01-22 |
| 架构 | 2.4T 参数，原生全模态统一模型 |
| 综合排名 | LMArena 国内第一（1460 分），全球第八 |
| API 定价 | 输入约 $0.55/M |
| API 平台 | 百度千帆 `qianfan.cloud.baidu.com`，兼容 OpenAI Python SDK |
| 说明 | 通用能力强，但编程专项基准（SWE-bench）未公开分数 |

---

## 火山方舟 Coding Plan 可用模型汇总

一个 Key，多个模型，适合 Claude Code / Cursor / Cline 等工具：

| 模型 | 来源 | 特点 |
|------|------|------|
| doubao-seed-2.0-code | 字节 | 编程专用，Anthropic 协议原生支持 |
| doubao-seed-2.0-pro | 字节 | 通用旗舰 |
| doubao-seed-2.0-lite | 字节 | 轻量快速 |
| kimi-k2.6 | 月之暗面 | Agent 编排最强 |
| kimi-k2.5 | 月之暗面 | 性能稳定 |
| glm-5.1 | 智谱 | 开源权重 SOTA |
| glm-4.7 | 智谱 | 性价比高 |
| minimax-m2.7 | MiniMax | 多 Agent 协作 |
| minimax-m2.5 | MiniMax | 稳定可靠 |
| deepseek-v3.2 | 深度求索 | 经典款 |

---

---

# 美国 / 西方主流 AI 编程模型（2026 年 5 月）

---

## 编程能力排行速览（美国模型）

| 模型 | SWE-bench Verified | SWE-bench Pro | 输入价格 / M tokens | 输出价格 / M tokens | 上下文窗口 |
|------|-------------------|--------------|--------------------|--------------------|-----------|
| Claude Opus 4.7 | 87.6% | 64.3% | $5.00 | $25.00 | 1M |
| GPT-5.5 | — | 58.6% | $5.00 | $30.00 | 1M |
| Gemini 3.1 Pro | 80.6% | 54.2% | $2.00 | $12.00 | 2M |
| Claude Sonnet 4.6 | 79.6% | — | $3.00 | $15.00 | 1M |
| Gemini 3 Flash | ~78% | — | $0.50 | $3.00 | 1M |
| Claude Haiku 4.5 | 73.3% | — | $1.00 | $5.00 | 200K |
| Gemini 2.5 Pro | 63.8% | — | $1.25 | $10.00 | 1M |

> **注意**：SWE-bench Verified 存在训练数据污染问题，SWE-bench Pro 更可靠。Claude Opus 4.7 在 Pro 上以 64.3% 大幅领先。

---

## 11. Anthropic Claude

### Claude Opus 4.7（旗舰，编程最强）

| 属性 | 值 |
|------|-----|
| 模型 ID | `claude-opus-4-7` |
| 发布日期 | 2026-04-16 |
| 上下文窗口 | 1,000,000 输入 / 128,000 输出 |
| 编程基准 | SWE-bench Verified 87.6%，SWE-bench Pro 64.3%，Terminal-Bench 2.0 69.4% |
| API 定价 | 输入 $5.00/M，输出 $25.00/M |
| Base URL | `https://api.anthropic.com` |
| 核心优势 | xhigh effort 模式，自验证 Agent 任务，代码品味和 bug 嗅觉业界最强 |

### Claude Sonnet 4.6

| 属性 | 值 |
|------|-----|
| 模型 ID | `claude-sonnet-4-6` |
| 发布日期 | 2026-02-17 |
| 上下文窗口 | 1,000,000 输入 / 64,000 输出 |
| 编程基准 | SWE-bench Verified 79.6%，SWE-bench Multilingual 75.9% |
| API 定价 | 输入 $3.00/M，输出 $15.00/M |
| 核心优势 | 接近 Opus 的编程能力，价格低 40%，性价比最优 |

### Claude Haiku 4.5

| 属性 | 值 |
|------|-----|
| 模型 ID | `claude-haiku-4-5-20251001` |
| 发布日期 | 2025-10 |
| 上下文窗口 | 200,000 输入 / 64,000 输出 |
| 编程基准 | SWE-bench Verified 73.3% |
| API 定价 | 输入 $1.00/M，输出 $5.00/M |
| 核心优势 | 支持扩展思考，适合高并发低成本编程任务 |

---

## 12. OpenAI

### GPT-5.5（旗舰）

| 属性 | 值 |
|------|-----|
| 模型 ID | `gpt-5.5-2026-04-23` |
| 发布日期 | 2026-04-24 |
| 上下文窗口 | ~922,000 输入 / 128,000 输出（1M 总量） |
| 编程基准 | SWE-bench Pro 58.6%，Terminal-Bench 2.0 82.7%（SOTA） |
| API 定价 | 输入 $5.00/M，输出 $30.00/M；>272K 输入 2 倍价 |
| Base URL | `https://api.openai.com/v1/` |
| 核心优势 | Terminal-Bench 2.0 最高分，Batch/Flex 可享 50% 折扣 |

### GPT-5.5 Pro

| 属性 | 值 |
|------|-----|
| 模型 ID | `gpt-5.5-pro` |
| 发布日期 | 2026-04-24 |
| API 定价 | 输入 $30.00/M，输出 $180.00/M |
| 核心优势 | 最高能力变体，极复杂任务 |

### GPT-5.3-Codex（编程专用）

| 属性 | 值 |
|------|-----|
| 模型 ID | `gpt-5.3-codex` |
| 发布日期 | 2026-02-24 |
| 编程基准 | SWE-bench Pro 56.8%，Terminal-Bench 2.0 77.3% |
| API 定价 | 输入 $1.75/M，输出 $14.00/M |
| 核心优势 | 编程专用，Codex 原生 Agent，性价比优于 GPT-5.5 |

### GPT-5.4 Mini

| 属性 | 值 |
|------|-----|
| 模型 ID | `gpt-5.4-mini` |
| 发布日期 | 2026 年 3 月 |
| API 定价 | 输入 $0.75/M，输出 $4.50/M |
| 核心优势 | 快速高效，适合编程子任务 |

### GPT-5.4 Nano

| 属性 | 值 |
|------|-----|
| 模型 ID | `gpt-5.4-nano-2026-03-17` |
| 发布日期 | 2026-03-17 |
| API 定价 | 输入 $0.20/M，输出 $1.25/M |
| 核心优势 | OpenAI 最便宜选项，适合分类和轻量编程子 Agent |

---

## 13. Google Gemini

### Gemini 3.1 Pro（旗舰）

| 属性 | 值 |
|------|-----|
| 模型 ID | `gemini-3.1-pro-preview` |
| 发布日期 | 2026-02-19 |
| 上下文窗口 | 2,000,000 输入 / 65,000 输出 |
| 编程基准 | SWE-bench Verified 80.6%，SWE-bench Pro 54.2%，Terminal-Bench 2.0 68.5% |
| API 定价 | 输入 $2.00/M，输出 $12.00/M（<=200K）；>200K 时 $4.00/$18.00；缓存 $0.20/M（90% 折扣） |
| Base URL | `https://generativelanguage.googleapis.com/v1beta/` |
| 核心优势 | 2M 超长上下文，缓存折扣极高 |

### Gemini 3 Flash

| 属性 | 值 |
|------|-----|
| 模型 ID | `gemini-3-flash-preview` |
| 发布日期 | 2025-12-17 |
| 上下文窗口 | 1,000,000 输入 / 64,000 输出 |
| 编程基准 | SWE-bench Verified ~78% |
| API 定价 | 输入 $0.50/M，输出 $3.00/M |
| 核心优势 | 高速思考模型，Agent 工作流和编程任务 |

### Gemini 2.5 Pro

| 属性 | 值 |
|------|-----|
| 模型 ID | `gemini-2.5-pro-preview-03-25` |
| 发布日期 | 2025 年 3 月 |
| 上下文窗口 | 1,000,000 输入 / 65,000 输出 |
| 编程基准 | SWE-bench Verified 63.8%，Aider Polyglot 74.0% |
| API 定价 | 输入 $1.25/M，输出 $10.00/M（<=200K）；>200K 时 $2.50/$15.00 |

### Gemini 2.5 Flash

| 属性 | 值 |
|------|-----|
| 模型 ID | `gemini-2.5-flash` |
| 上下文窗口 | 1,000,000 输入 / 65,000 输出 |
| API 定价 | 输入 $0.15~0.30/M，输出 $0.60~2.50/M |
| 核心优势 | 高吞吐量编程任务，极致性价比 |

---

## 14. Meta Llama（开源）

### Llama 4 Maverick

| 属性 | 值 |
|------|-----|
| 模型 ID | `meta-llama/llama-4-maverick` |
| 发布日期 | 2025-04-05 |
| 架构 | 400B 总参 / 17B 激活（MoE，128 experts） |
| 上下文窗口 | 1,000,000 tokens |
| API 定价（托管） | 输入 $0.15/M，输出 $0.60/M（自部署免费） |
| 开源 | 开放权重（Meta 自定义许可，700M MAU 条款） |
| 核心优势 | 可自部署（Ollama / vLLM / NVIDIA NIM），无 token 成本 |

### Llama 4 Scout

| 属性 | 值 |
|------|-----|
| 模型 ID | `meta-llama/llama-4-scout` |
| 架构 | 109B 总参 / 17B 激活（MoE，16 experts） |
| 上下文窗口 | 10,000,000 tokens（所有模型中最大） |
| API 定价（托管） | 输入 $0.08/M，输出 $0.30/M |
| 核心优势 | 千万级上下文，适合超大代码仓库分析 |

---

# 全球编程模型综合对比

## SWE-bench Pro 排行榜（更可靠，无污染）

| 排名 | 模型 | SWE-bench Pro | 来源 | 定价（输入/输出 /M） |
|------|------|--------------|------|---------------------|
| 1 | Claude Opus 4.7 | 64.3% | Anthropic | $5.00 / $25.00 |
| 2 | Kimi K2.6 | 58.6% | 月之暗面 | $0.55 / $2.65 |
| 3 | GPT-5.5 | 58.6% | OpenAI | $5.00 / $30.00 |
| 4 | GLM-5.1 | 58.4% | 智谱 | $1.05 / $3.50 |
| 5 | MiMo-V2.5-Pro | 57.2% | 小米 | $1.00 / $3.00 |
| 6 | GPT-5.3-Codex | 56.8% | OpenAI | $1.75 / $14.00 |
| 7 | MiniMax M2.7 | 56.2% | MiniMax | $0.30 / $1.20 |
| 8 | Gemini 3.1 Pro | 54.2% | Google | $2.00 / $12.00 |

## SWE-bench Verified 排行榜（含中美所有模型）

| 排名 | 模型 | SWE-bench Verified | 来源 | 定价（输入 /M） |
|------|------|-------------------|------|----------------|
| 1 | Claude Opus 4.7 | 87.6% | Anthropic | $5.00 |
| 2 | DeepSeek V4-Pro | 80.6% | 深度求索 | $0.30 |
| 3 | Gemini 3.1 Pro | 80.6% | Google | $2.00 |
| 4 | Kimi K2.6 | 80.2% | 月之暗面 | $0.55 |
| 5 | Claude Sonnet 4.6 | 79.6% | Anthropic | $3.00 |
| 6 | DeepSeek V4-Flash | 79.0% | 深度求索 | $0.14 |
| 7 | Qwen3.6 Plus | 78.8% | 阿里巴巴 | $0.325 |
| 8 | Gemini 3 Flash | ~78% | Google | $0.50 |
| 9 | GLM-5.1 | 77.8% | 智谱 | $1.05 |
| 10 | Kimi K2.5 | 76.8% | 月之暗面 | $0.60 |
| 11 | 腾讯混元 Hy3 | 74.4% | 腾讯 | ¥1.2 |
| 12 | Claude Haiku 4.5 | 73.3% | Anthropic | $1.00 |
| 13 | Gemini 2.5 Pro | 63.8% | Google | $1.25 |

## 美国模型 API 端点汇总

| 厂商 | Base URL |
|------|----------|
| Anthropic | `https://api.anthropic.com` |
| OpenAI | `https://api.openai.com/v1/` |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta/` |

---

## CCR / Sub-agent 选型建议（中美综合）

| 场景 | 推荐模型 | 理由 |
|------|---------|------|
| 代码实现（高性价比） | DeepSeek V4-Flash | $0.14/M，SWE-bench 79%，百万上下文 |
| 代码实现（最强） | Claude Opus 4.7 | SWE-bench Pro 64.3%，编程品质业界最高 |
| 代码实现（国产最强） | DeepSeek V4-Pro | SWE-bench 80.6%，5 月底前 75% 折扣 |
| 代码审查（终极兜底） | Claude Opus 4.7 | bug 嗅觉、安全审查、代码品味不可替代 |
| 代码审查（高性价比） | Kimi K2.6 / GLM-5.1 | 跨阵营互审效果最佳 |
| 编程专用模型 | GPT-5.3-Codex | $1.75/M，OpenAI 编程专精，Agent 原生 |
| 前端 UI | Kimi K2.6 | Agent Swarm + UI/UX 生成 |
| 写测试（量大便宜） | Qwen3 Coder Next | $0.11/M，编程专用 |
| 中文文档 | Qwen3.6 Plus | 中文流畅，百万上下文 |
| 快速原型（极致速度） | Step 3.5 Flash | 350 tokens/s，$0.10/M |
| 超长上下文代码分析 | Gemini 3.1 Pro / Llama 4 Scout | 2M / 10M 上下文 |
| 本地 / 离线部署 | Llama 4 Maverick | 开放权重，自部署免费 |
| 一个 Key 搞定多模型 | 火山方舟 Coding Plan | 10+ 模型一站式接入 |
