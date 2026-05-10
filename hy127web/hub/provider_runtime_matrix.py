from __future__ import annotations

import copy
from urllib.parse import urlparse


MATRIX_VERSION = 1

RUNTIME_ALIASES = {
    "direct_api": "api",
    "api": "api",
    "claude": "claude_cli",
    "claude_code": "claude_cli",
    "claude_cli": "claude_cli",
    "codex": "codex_cli",
    "codex_cli": "codex_cli",
}

OPENAI_COMPATIBLE_PROTOCOLS = {"openai_chat", "openai_compatible"}


def _mapping(
    *,
    api_base: str,
    model_id: str,
    env_key: str,
    protocol: str = "openai_chat",
    supported: bool = True,
    compatibility: str = "openai_compatible",
    note: str = "",
    models: list[str] | None = None,
) -> dict:
    return {
        "supported": supported,
        "api_base": api_base,
        "protocol": protocol,
        "model_id": model_id,
        "env_key": env_key,
        "compatibility": compatibility,
        "note": note,
        "models": models or [model_id],
    }


def _unsupported(note: str) -> dict:
    return {
        "supported": False,
        "api_base": "",
        "protocol": "",
        "model_id": "",
        "env_key": "",
        "compatibility": "unsupported",
        "note": note,
        "models": [],
    }


CHINA_PROVIDER_RUNTIME_MATRIX = {
    "deepseek": {
        "display_name": "DeepSeek",
        "models": ["deepseek-v4-pro", "deepseek-v4-flash", "deepseek-v3.2", "deepseek-chat", "deepseek-reasoner"],
        "runtimes": {
            "api": _mapping(
                api_base="https://api.deepseek.com/v1",
                model_id="deepseek-v4-pro",
                env_key="DEEPSEEK_API_KEY",
                models=["deepseek-v4-pro", "deepseek-v4-flash", "deepseek-v3.2", "deepseek-chat", "deepseek-reasoner"],
            ),
            "codex_cli": _mapping(
                api_base="https://api.deepseek.com/v1",
                model_id="deepseek-v4-pro",
                env_key="DEEPSEEK_API_KEY",
                note="Codex CLI 通过 OpenAI-compatible 环境变量访问 DeepSeek。",
                models=["deepseek-v4-pro", "deepseek-v4-flash", "deepseek-v3.2", "deepseek-chat", "deepseek-reasoner"],
            ),
            "claude_cli": _mapping(
                api_base="https://api.deepseek.com/anthropic",
                model_id="deepseek-v4-pro",
                env_key="DEEPSEEK_API_KEY",
                protocol="anthropic_messages",
                compatibility="anthropic_compatible",
                note="Claude Code 使用 DeepSeek Anthropic-compatible 入口。",
                models=["deepseek-v4-pro", "deepseek-v4-flash"],
            ),
        },
    },
    "moonshot": {
        "display_name": "Moonshot/Kimi",
        "models": ["kimi-k2.6", "kimi-k2.6-thinking", "kimi-k2.5", "kimi-k2"],
        "runtimes": {
            "api": _mapping(
                api_base="https://api.moonshot.ai/v1",
                model_id="kimi-k2.6",
                env_key="MOONSHOT_API_KEY",
                models=["kimi-k2.6", "kimi-k2.6-thinking", "kimi-k2.5", "kimi-k2"],
            ),
            "codex_cli": _mapping(
                api_base="https://api.moonshot.ai/v1",
                model_id="kimi-k2.6",
                env_key="MOONSHOT_API_KEY",
                note="Codex CLI 通过 OpenAI-compatible 环境变量访问 Moonshot。",
                models=["kimi-k2.6", "kimi-k2.6-thinking", "kimi-k2.5", "kimi-k2"],
            ),
            "claude_cli": _unsupported(
                "AI模型-最新.md 仅确认 Kimi K2.5 支持 Anthropic-compatible，未给出 Moonshot 官方 Anthropic Base URL；Claude Code 请优先使用火山方舟 Coding Plan 的 kimi-k2.6/kimi-k2.5。"
            ),
        },
    },
    "qwen": {
        "display_name": "阿里云/通义千问",
        "models": [
            "qwen3.6-max-preview",
            "qwen3.6-plus",
            "qwen3-coder-next",
            "qwen3-coder-plus",
            "qwen3-coder-plus-2025-09-23",
        ],
        "runtimes": {
            "api": _mapping(
                api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
                model_id="qwen3-coder-next",
                env_key="DASHSCOPE_API_KEY",
                models=[
                    "qwen3.6-max-preview",
                    "qwen3.6-plus",
                    "qwen3-coder-next",
                    "qwen3-coder-plus",
                    "qwen3-coder-plus-2025-09-23",
                ],
            ),
            "codex_cli": _mapping(
                api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
                model_id="qwen3-coder-next",
                env_key="DASHSCOPE_API_KEY",
                note="Codex CLI 通过 OpenAI-compatible 环境变量访问百炼标准 API。",
                models=[
                    "qwen3.6-max-preview",
                    "qwen3.6-plus",
                    "qwen3-coder-next",
                    "qwen3-coder-plus",
                    "qwen3-coder-plus-2025-09-23",
                ],
            ),
            "claude_cli": _mapping(
                api_base="https://coding.dashscope.aliyuncs.com/apps/anthropic",
                model_id="qwen3-coder-plus",
                env_key="DASHSCOPE_API_KEY",
                protocol="anthropic_messages",
                compatibility="anthropic_compatible",
                note="Claude Code 走百炼 Coding Plan Anthropic 入口；账号需开通对应套餐。",
                models=["qwen3-coder-plus", "qwen3-coder-next"],
            ),
        },
    },
    "doubao": {
        "display_name": "字节豆包",
        "models": ["doubao-seed-2.0-code", "doubao-seed-2.0-pro", "doubao-seed-2.0-lite"],
        "runtimes": {
            "api": _mapping(
                api_base="https://ark.cn-beijing.volces.com/api/v3",
                model_id="doubao-seed-2-0-code-preview-260215",
                env_key="ARK_API_KEY",
                models=[
                    "doubao-seed-2-0-code-preview-260215",
                    "doubao-seed-2-0-pro-260215",
                    "doubao-seed-2-0-lite-260215",
                    "doubao-seed-2.0-code",
                    "doubao-seed-2.0-pro",
                    "doubao-seed-2.0-lite",
                ],
            ),
            "codex_cli": _mapping(
                api_base="https://ark.cn-beijing.volces.com/api/v3",
                model_id="doubao-seed-2-0-code-preview-260215",
                env_key="ARK_API_KEY",
                note="Codex CLI 通过 OpenAI-compatible 环境变量访问火山方舟标准 API。",
                models=[
                    "doubao-seed-2-0-code-preview-260215",
                    "doubao-seed-2-0-pro-260215",
                    "doubao-seed-2-0-lite-260215",
                    "doubao-seed-2.0-code",
                    "doubao-seed-2.0-pro",
                    "doubao-seed-2.0-lite",
                ],
            ),
            "claude_cli": _mapping(
                api_base="https://ark.cn-beijing.volces.com/api/coding",
                model_id="doubao-seed-2.0-code",
                env_key="ARK_CODING_PLAN_API_KEY",
                protocol="anthropic_messages",
                compatibility="anthropic_compatible",
                note="Claude Code 走火山方舟 Coding Plan Anthropic 入口；需使用 Coding Plan Key。",
                models=["doubao-seed-2.0-code", "doubao-seed-2.0-pro", "doubao-seed-2.0-lite"],
            ),
        },
    },
    "ark_coding_plan": {
        "display_name": "火山方舟 Coding Plan",
        "models": [
            "doubao-seed-2.0-code",
            "doubao-seed-2.0-pro",
            "doubao-seed-2.0-lite",
            "kimi-k2.6",
            "kimi-k2.5",
            "glm-5.1",
            "glm-4.7",
            "minimax-m2.7",
            "minimax-m2.5",
            "deepseek-v3.2",
        ],
        "runtimes": {
            "api": _mapping(
                api_base="https://ark.cn-beijing.volces.com/api/coding/v3",
                model_id="doubao-seed-2.0-code",
                env_key="ARK_CODING_PLAN_API_KEY",
                note="火山方舟 Coding Plan 的 OpenAI-compatible 入口。",
                models=[
                    "doubao-seed-2.0-code",
                    "doubao-seed-2.0-pro",
                    "doubao-seed-2.0-lite",
                    "kimi-k2.6",
                    "kimi-k2.5",
                    "glm-5.1",
                    "glm-4.7",
                    "minimax-m2.7",
                    "minimax-m2.5",
                    "deepseek-v3.2",
                ],
            ),
            "codex_cli": _mapping(
                api_base="https://ark.cn-beijing.volces.com/api/coding/v3",
                model_id="doubao-seed-2.0-code",
                env_key="ARK_CODING_PLAN_API_KEY",
                note="Codex CLI 通过 OpenAI-compatible 环境变量访问火山方舟 Coding Plan。",
                models=[
                    "doubao-seed-2.0-code",
                    "doubao-seed-2.0-pro",
                    "doubao-seed-2.0-lite",
                    "kimi-k2.6",
                    "kimi-k2.5",
                    "glm-5.1",
                    "glm-4.7",
                    "minimax-m2.7",
                    "minimax-m2.5",
                    "deepseek-v3.2",
                ],
            ),
            "claude_cli": _mapping(
                api_base="https://ark.cn-beijing.volces.com/api/coding",
                model_id="doubao-seed-2.0-code",
                env_key="ARK_CODING_PLAN_API_KEY",
                protocol="anthropic_messages",
                compatibility="anthropic_compatible",
                note="Claude Code 走火山方舟 Coding Plan Anthropic 入口，可选 Doubao/Kimi/GLM/MiniMax/DeepSeek。",
                models=[
                    "doubao-seed-2.0-code",
                    "doubao-seed-2.0-pro",
                    "doubao-seed-2.0-lite",
                    "kimi-k2.6",
                    "kimi-k2.5",
                    "glm-5.1",
                    "glm-4.7",
                    "minimax-m2.7",
                    "minimax-m2.5",
                    "deepseek-v3.2",
                ],
            ),
        },
    },
    "glm": {
        "display_name": "智谱/GLM",
        "models": ["glm-5.1", "glm-4.7"],
        "runtimes": {
            "api": _mapping(
                api_base="https://api.z.ai/api/openai/v1",
                model_id="glm-5.1",
                env_key="ZHIPU_API_KEY",
                models=["glm-5.1", "glm-4.7"],
            ),
            "codex_cli": _mapping(
                api_base="https://api.z.ai/api/openai/v1",
                model_id="glm-5.1",
                env_key="ZHIPU_API_KEY",
                note="Codex CLI 通过 OpenAI-compatible 环境变量访问 Z.AI。",
                models=["glm-5.1", "glm-4.7"],
            ),
            "claude_cli": _mapping(
                api_base="https://api.z.ai/api/anthropic",
                model_id="glm-5.1",
                env_key="ZHIPU_API_KEY",
                protocol="anthropic_messages",
                compatibility="anthropic_compatible",
                note="Claude Code 使用 Z.AI Anthropic-compatible 入口。",
                models=["glm-5.1", "glm-4.7"],
            ),
        },
    },
    "hunyuan": {
        "display_name": "腾讯混元",
        "models": ["hy3-preview"],
        "runtimes": {
            "api": _mapping(
                api_base="https://api.hunyuan.cloud.tencent.com/v1",
                model_id="hy3-preview",
                env_key="HUNYUAN_API_KEY",
                models=["hy3-preview", "hunyuan-t1-latest", "hunyuan-turbos-latest"],
            ),
            "codex_cli": _mapping(
                api_base="https://api.hunyuan.cloud.tencent.com/v1",
                model_id="hy3-preview",
                env_key="HUNYUAN_API_KEY",
                note="Codex CLI 通过 OpenAI-compatible 环境变量访问腾讯混元。",
                models=["hy3-preview", "hunyuan-t1-latest", "hunyuan-turbos-latest"],
            ),
            "claude_cli": _unsupported("AI模型-最新.md 未提供腾讯混元 Anthropic-compatible 入口，Claude Code 暂不自动映射。"),
        },
    },
    "mimo": {
        "display_name": "小米 MiMo",
        "models": ["mimo-v2.5-pro", "mimo-v2.5", "mimo-v2-pro", "mimo-v2-flash"],
        "runtimes": {
            "api": _mapping(
                api_base="https://api.xiaomimimo.com/v1",
                model_id="mimo-v2.5-pro",
                env_key="XIAOMI_API_KEY",
                models=["mimo-v2.5-pro", "mimo-v2.5", "mimo-v2-pro", "mimo-v2-flash"],
            ),
            "codex_cli": _mapping(
                api_base="https://api.xiaomimimo.com/v1",
                model_id="mimo-v2.5-pro",
                env_key="XIAOMI_API_KEY",
                note="Codex CLI 通过 OpenAI-compatible 环境变量访问小米 MiMo。",
                models=["mimo-v2.5-pro", "mimo-v2.5", "mimo-v2-pro", "mimo-v2-flash"],
            ),
            "claude_cli": _unsupported("AI模型-最新.md 未提供小米 MiMo Anthropic-compatible 入口，Claude Code 暂不自动映射。"),
        },
    },
    "minimax": {
        "display_name": "MiniMax",
        "models": ["MiniMax-M2.7", "MiniMax-M2.5"],
        "runtimes": {
            "api": _mapping(
                api_base="https://api.minimax.io",
                model_id="MiniMax-M2.7",
                env_key="MINIMAX_API_KEY",
                models=["MiniMax-M2.7", "MiniMax-M2.5"],
            ),
            "codex_cli": _mapping(
                api_base="https://api.minimax.io",
                model_id="MiniMax-M2.7",
                env_key="MINIMAX_API_KEY",
                note="Codex CLI 通过 OpenAI-compatible 环境变量访问 MiniMax。",
                models=["MiniMax-M2.7", "MiniMax-M2.5"],
            ),
            "claude_cli": _unsupported("MiniMax 模型可通过火山方舟 Coding Plan 使用 Claude Code；直连 MiniMax 未预设 Anthropic-compatible 入口。"),
        },
    },
    "stepfun": {
        "display_name": "阶跃星辰/StepFun",
        "models": ["step-3.5-flash", "step3"],
        "runtimes": {
            "api": _mapping(
                api_base="https://api.stepfun.com/v1",
                model_id="step-3.5-flash",
                env_key="STEPFUN_API_KEY",
                models=["step-3.5-flash", "step3"],
            ),
            "codex_cli": _mapping(
                api_base="https://api.stepfun.com/v1",
                model_id="step-3.5-flash",
                env_key="STEPFUN_API_KEY",
                note="Codex CLI 通过 OpenAI-compatible 环境变量访问 StepFun。",
                models=["step-3.5-flash", "step3"],
            ),
            "claude_cli": _unsupported("AI模型-最新.md 未提供 StepFun Anthropic-compatible 入口，Claude Code 暂不自动映射。"),
        },
    },
    "ernie": {
        "display_name": "百度文心/ERNIE",
        "models": ["ernie-5.0"],
        "runtimes": {
            "api": _mapping(
                api_base="https://qianfan.baidubce.com/v2",
                model_id="ernie-5.0",
                env_key="QIANFAN_API_KEY",
                note="AI模型-最新.md 确认千帆兼容 OpenAI SDK；具体 Base URL 仍需以千帆控制台为准。",
                models=["ernie-5.0"],
            ),
            "codex_cli": _mapping(
                api_base="https://qianfan.baidubce.com/v2",
                model_id="ernie-5.0",
                env_key="QIANFAN_API_KEY",
                note="Codex CLI 通过 OpenAI-compatible 环境变量访问千帆；Base URL 需以控制台为准。",
                models=["ernie-5.0"],
            ),
            "claude_cli": _unsupported("AI模型-最新.md 未提供百度千帆 Anthropic-compatible 入口，Claude Code 暂不自动映射。"),
        },
    },
}

NON_CHINA_PROVIDER_RUNTIME_MATRIX = {
    "anthropic": {
        "display_name": "Anthropic/Claude",
        "models": ["claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
        "runtimes": {
            "claude_cli": _mapping(
                api_base="https://api.anthropic.com",
                model_id="claude-sonnet-4-6",
                env_key="ANTHROPIC_API_KEY",
                protocol="anthropic_messages",
                compatibility="native",
                note="Claude Code 原生 Claude 入口。",
                models=["claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
            ),
        },
    },
    "gemini": {
        "display_name": "Google/Gemini",
        "models": ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite"],
        "runtimes": {
            "api": _mapping(
                api_base="https://generativelanguage.googleapis.com/v1beta/openai",
                model_id="gemini-2.5-flash",
                env_key="GEMINI_API_KEY",
                models=["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite"],
            ),
            "codex_cli": _mapping(
                api_base="https://generativelanguage.googleapis.com/v1beta/openai",
                model_id="gemini-2.5-flash",
                env_key="GEMINI_API_KEY",
                note="Gemini CLI 壳子已取消预设；如需通过壳子执行，使用 Codex CLI 的 OpenAI-compatible 环境变量。",
                models=["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite"],
            ),
            "claude_cli": _unsupported("Gemini CLI 壳子已取消预设，Gemini 未预设 Claude Code 兼容入口。"),
        },
    },
}

DEFAULT_PROVIDER_RUNTIME_MATRIX = {
    **CHINA_PROVIDER_RUNTIME_MATRIX,
    **NON_CHINA_PROVIDER_RUNTIME_MATRIX,
}

PROVIDER_HOST_HINTS = [
    ("deepseek", ("api.deepseek.com",)),
    ("moonshot", ("api.moonshot.ai",)),
    ("qwen", ("dashscope.aliyuncs.com", "coding.dashscope.aliyuncs.com")),
    ("doubao", ("ark.cn-beijing.volces.com",)),
    ("glm", ("api.z.ai", "open.bigmodel.cn")),
    ("hunyuan", ("api.hunyuan.cloud.tencent.com",)),
    ("mimo", ("xiaomimimo.com", "platform.xiaomimimo.com")),
    ("minimax", ("api.minimax.io", "api.minimaxi.com")),
    ("stepfun", ("api.stepfun.com",)),
    ("ernie", ("qianfan.baidubce.com", "qianfan.cloud.baidu.com")),
    ("anthropic", ("api.anthropic.com",)),
    ("gemini", ("generativelanguage.googleapis.com",)),
]


def normalize_runtime_id(runtime_id: str) -> str:
    return RUNTIME_ALIASES.get((runtime_id or "api").strip(), (runtime_id or "api").strip())


def get_provider_runtime_matrix() -> dict:
    return {
        "version": MATRIX_VERSION,
        "providers": copy.deepcopy(DEFAULT_PROVIDER_RUNTIME_MATRIX),
        "supported_runtimes": ["api", "claude_cli", "codex_cli"],
        "primary_cli_runtime": "claude_cli",
    }


def infer_provider(model: dict) -> str:
    provider = (model.get("provider") or "").strip()
    if provider and provider != "custom":
        return provider

    api_base = model.get("api_base") or ""
    host = urlparse(api_base).netloc.lower()
    for provider_key, host_hints in PROVIDER_HOST_HINTS:
        if any(hint in host for hint in host_hints):
            return provider_key
    return provider or "custom"


def _select_model_id(saved_model_id: str, mapping: dict) -> str:
    models = mapping.get("models") or []
    if saved_model_id and saved_model_id in models:
        return saved_model_id
    return mapping.get("model_id") or saved_model_id


def resolve_model_runtime(model: dict, runtime_id: str) -> dict:
    """Return the effective model config for a selected runtime.

    The returned config is derived at request time and must not be written back
    to the saved model. API keys remain attached to the user's selected model.
    """

    runtime = normalize_runtime_id(runtime_id)
    provider = infer_provider(model)
    provider_entry = DEFAULT_PROVIDER_RUNTIME_MATRIX.get(provider)
    runtime_mapping = (provider_entry or {}).get("runtimes", {}).get(runtime)

    saved_protocol = model.get("protocol") or "openai_chat"
    warnings: list[str] = []
    effective = dict(model)

    if runtime_mapping and runtime_mapping.get("supported"):
        effective.update({
            "provider": provider,
            "api_base": runtime_mapping.get("api_base") or model.get("api_base", ""),
            "protocol": runtime_mapping.get("protocol") or saved_protocol,
            "model_id": _select_model_id(model.get("model_id", ""), runtime_mapping),
            "env_key": runtime_mapping.get("env_key") or model.get("env_key", ""),
        })
        if runtime_mapping.get("note"):
            warnings.append(runtime_mapping["note"])
        return {
            "runtime": runtime,
            "provider": provider,
            "supported": True,
            "mapping_applied": True,
            "compatibility": runtime_mapping.get("compatibility", ""),
            "display_name": (provider_entry or {}).get("display_name", provider),
            "mapping": copy.deepcopy(runtime_mapping),
            "model": effective,
            "warnings": warnings,
        }

    if runtime_mapping and not runtime_mapping.get("supported"):
        return {
            "runtime": runtime,
            "provider": provider,
            "supported": False,
            "mapping_applied": False,
            "compatibility": runtime_mapping.get("compatibility", "unsupported"),
            "display_name": (provider_entry or {}).get("display_name", provider),
            "mapping": copy.deepcopy(runtime_mapping),
            "model": effective,
            "warnings": [runtime_mapping.get("note") or "该模型服务暂不支持所选运行方式。"],
        }

    if runtime == "api" and saved_protocol in OPENAI_COMPATIBLE_PROTOCOLS:
        return {
            "runtime": runtime,
            "provider": provider,
            "supported": True,
            "mapping_applied": False,
            "compatibility": "saved_openai_compatible",
            "display_name": provider,
            "mapping": None,
            "model": effective,
            "warnings": [],
        }

    if runtime == "claude_cli" and provider == "anthropic":
        effective["protocol"] = "anthropic_messages"
        effective["env_key"] = effective.get("env_key") or "ANTHROPIC_API_KEY"
        return {
            "runtime": runtime,
            "provider": provider,
            "supported": True,
            "mapping_applied": False,
            "compatibility": "native",
            "display_name": "Anthropic/Claude",
            "mapping": None,
            "model": effective,
            "warnings": [],
        }

    return {
        "runtime": runtime,
        "provider": provider,
        "supported": False,
        "mapping_applied": False,
        "compatibility": "unsupported",
        "display_name": provider,
        "mapping": None,
        "model": effective,
        "warnings": ["该模型服务尚未预设所选运行方式映射。"],
    }
