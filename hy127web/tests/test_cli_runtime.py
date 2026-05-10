from hy127web.hub.ai_runtime import CliRuntime


def test_cli_runtime_injects_provider_and_openai_compatible_env(tmp_path):
    runtime = CliRuntime(
        runtime_id="qwen_cli",
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


def test_cli_runtime_injects_gemini_aliases(tmp_path):
    runtime = CliRuntime(
        runtime_id="gemini_cli",
        cwd=str(tmp_path),
        provider="gemini",
        protocol="openai_chat",
        model="gemini-2.5-flash",
        api_key="gemini-key",
        api_base="https://generativelanguage.googleapis.com/v1beta/openai",
        env_key="GEMINI_API_KEY",
    )

    env = runtime._build_env({"PATH": ""})

    assert env["GEMINI_API_KEY"] == "gemini-key"
    assert env["GOOGLE_API_KEY"] == "gemini-key"
    assert env["OPENAI_API_KEY"] == "gemini-key"


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
