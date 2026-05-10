from hy127web.hub.ai_runtime import CliRuntime


def test_cli_runtime_injects_provider_and_openai_compatible_env(tmp_path):
    runtime = CliRuntime(
        runtime_id="codex_cli",
        cwd=str(tmp_path),
        provider="qwen",
        protocol="openai_chat",
        model="qwen3-coder-plus",
        api_key="sk-test",
        api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
        env_key="DASHSCOPE_API_KEY",
    )

    env = runtime._build_env({"PATH": ""})

    assert env["DASHSCOPE_API_KEY"] == "sk-test"
    assert env["QWEN_API_KEY"] == "sk-test"
    assert env["OPENAI_API_KEY"] == "sk-test"
    assert env["OPENAI_BASE_URL"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert env["HY127WEB_AI_MODEL"] == "qwen3-coder-plus"
    assert env["HY127WEB_AI_PROVIDER"] == "qwen"


def test_cli_runtime_injects_anthropic_env_for_claude_compatible_provider(tmp_path):
    runtime = CliRuntime(
        runtime_id="claude_cli",
        cwd=str(tmp_path),
        provider="deepseek",
        protocol="anthropic_messages",
        model="deepseek-v4-pro",
        api_key="deepseek-key",
        api_base="https://api.deepseek.com/anthropic",
        env_key="DEEPSEEK_API_KEY",
    )

    env = runtime._build_env({"PATH": ""})

    assert env["DEEPSEEK_API_KEY"] == "deepseek-key"
    assert env["ANTHROPIC_API_KEY"] == "deepseek-key"
    assert env["ANTHROPIC_BASE_URL"] == "https://api.deepseek.com/anthropic"
    assert env["DEEPSEEK_BASE_URL"] == "https://api.deepseek.com/anthropic"


def test_cli_runtime_does_not_export_non_http_base_url(tmp_path):
    runtime = CliRuntime(
        runtime_id="codex_cli",
        cwd=str(tmp_path),
        provider="openai_codex",
        protocol="openai_chat",
        model="gpt-5.3-codex",
        api_key="sk-openai",
        api_base="codex://cli",
    )

    env = runtime._build_env({"PATH": ""})

    assert env["OPENAI_API_KEY"] == "sk-openai"
    assert "OPENAI_BASE_URL" not in env


def test_cli_runtime_prompt_includes_project_and_roles(tmp_path):
    runtime = CliRuntime(runtime_id="claude_cli", cwd=str(tmp_path))

    prompt = runtime._messages_to_prompt([
        {"role": "system", "content": "系统提示"},
        {"role": "user", "content": "修复按钮"},
    ])

    assert str(tmp_path) in prompt
    assert "SYSTEM:\n系统提示" in prompt
    assert "USER:\n修复按钮" in prompt


def test_qwen_and_gemini_shell_presets_are_not_registered():
    assert not CliRuntime.is_supported_runtime("qwen_cli")
    assert not CliRuntime.is_supported_runtime("gemini_cli")
