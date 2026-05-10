from hy127web.hub.provider_runtime_matrix import (
    CHINA_PROVIDER_RUNTIME_MATRIX,
    get_provider_runtime_matrix,
    infer_provider,
    normalize_runtime_id,
    resolve_model_runtime,
)


def _model(provider: str, api_base: str, model_id: str) -> dict:
    return {
        "id": "m1",
        "name": provider,
        "provider": provider,
        "api_base": api_base,
        "model_id": model_id,
        "protocol": "openai_chat",
        "env_key": "",
    }


def test_deepseek_claude_runtime_uses_anthropic_mapping():
    resolved = resolve_model_runtime(
        _model("deepseek", "https://api.deepseek.com/v1", "deepseek-chat"),
        "claude_cli",
    )

    assert resolved["supported"] is True
    assert resolved["mapping_applied"] is True
    assert resolved["model"]["api_base"] == "https://api.deepseek.com/anthropic"
    assert resolved["model"]["protocol"] == "anthropic_messages"
    assert resolved["model"]["model_id"] == "deepseek-v4-pro"
    assert resolved["model"]["env_key"] == "DEEPSEEK_API_KEY"


def test_qwen_claude_runtime_uses_bailian_coding_plan_mapping():
    resolved = resolve_model_runtime(
        _model("qwen", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen3.6-plus"),
        "claude",
    )

    assert resolved["runtime"] == "claude_cli"
    assert resolved["supported"] is True
    assert resolved["model"]["api_base"] == "https://coding.dashscope.aliyuncs.com/apps/anthropic"
    assert resolved["model"]["protocol"] == "anthropic_messages"
    assert resolved["model"]["model_id"] == "qwen3-coder-plus"


def test_openai_compatible_only_provider_rejects_claude_runtime():
    resolved = resolve_model_runtime(
        _model("hunyuan", "https://api.hunyuan.cloud.tencent.com/v1", "hy3-preview"),
        "claude_cli",
    )

    assert resolved["supported"] is False
    assert "Anthropic-compatible" in resolved["warnings"][0]


def test_custom_model_infers_provider_from_api_base():
    model = _model("custom", "https://api.z.ai/api/openai/v1", "glm-5.1")

    assert infer_provider(model) == "glm"
    resolved = resolve_model_runtime(model, "claude_cli")

    assert resolved["provider"] == "glm"
    assert resolved["model"]["api_base"] == "https://api.z.ai/api/anthropic"


def test_all_china_providers_have_api_and_claude_entries():
    matrix = get_provider_runtime_matrix()

    for provider_key in CHINA_PROVIDER_RUNTIME_MATRIX:
        runtimes = matrix["providers"][provider_key]["runtimes"]
        assert "api" in runtimes
        assert "claude_cli" in runtimes


def test_runtime_aliases_keep_removed_shells_out_of_supported_list():
    matrix = get_provider_runtime_matrix()

    assert normalize_runtime_id("direct_api") == "api"
    assert "qwen_cli" not in matrix["supported_runtimes"]
    assert "gemini_cli" not in matrix["supported_runtimes"]
