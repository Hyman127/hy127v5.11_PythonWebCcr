import json

from hy127web.hub.models_manager import ModelsManager


def test_api_key_persists_outside_models_json(tmp_path):
    models_path = tmp_path / "models.json"
    keys_dir = tmp_path / "keys"

    manager = ModelsManager(str(models_path), str(keys_dir))
    model = manager.add_model(
        name="test",
        provider="openai",
        api_base="https://api.example.test/v1",
        api_key="sk-test-secret",
        model_id="gpt-test",
    )

    with open(models_path, "r", encoding="utf-8") as f:
        models_json = json.load(f)
    assert "sk-test-secret" not in json.dumps(models_json, ensure_ascii=False)

    keys_path = keys_dir / "api_keys.enc"
    assert keys_path.exists()

    reloaded = ModelsManager(str(models_path), str(keys_dir))
    assert reloaded.get_api_key(model["id"]) == "sk-test-secret"


def test_api_key_update_and_remove_persist(tmp_path):
    manager = ModelsManager(str(tmp_path / "models.json"), str(tmp_path / "keys"))
    model = manager.add_model(
        name="test",
        provider="openai",
        api_base="https://api.example.test/v1",
        api_key="sk-old",
        model_id="gpt-test",
    )

    manager.update_model(model["id"], api_key="sk-new")
    reloaded = ModelsManager(str(tmp_path / "models.json"), str(tmp_path / "keys"))
    assert reloaded.get_api_key(model["id"]) == "sk-new"

    reloaded.remove_model(model["id"])
    reloaded_again = ModelsManager(str(tmp_path / "models.json"), str(tmp_path / "keys"))
    assert reloaded_again.get_api_key(model["id"]) is None


def test_model_optional_fields_default_to_api_profile(tmp_path):
    manager = ModelsManager(str(tmp_path / "models.json"), str(tmp_path / "keys"))
    model = manager.add_model(
        name="deepseek",
        provider="deepseek",
        api_base="https://api.deepseek.com",
        api_key="sk-test",
        model_id="deepseek-reasoner",
    )

    assert model["protocol"] == "openai_chat"
    assert model["runtime"] == "api"
    assert model["roles"] == ["chat"]
    assert model["reasoning_profile"] == "max"
    assert model["is_default"] is True
    assert model["orchestration"] == {"enabled": False}
    assert model["env_key"] == ""


def test_default_model_switch_is_exclusive(tmp_path):
    manager = ModelsManager(str(tmp_path / "models.json"), str(tmp_path / "keys"))
    first = manager.add_model(
        name="first",
        provider="openai",
        api_base="https://api.example.test/v1",
        api_key="sk-first",
        model_id="gpt-test",
    )
    second = manager.add_model(
        name="second",
        provider="openai",
        api_base="https://api.example.test/v1",
        api_key="sk-second",
        model_id="gpt-test-2",
        is_default=True,
        roles=["chat", "planner"],
    )

    reloaded = ModelsManager(str(tmp_path / "models.json"), str(tmp_path / "keys"))
    assert reloaded.get_default_model()["id"] == second["id"]
    assert reloaded.get_model(first["id"])["is_default"] is False
    assert reloaded.get_model(second["id"])["roles"] == ["chat", "planner"]


def test_model_env_key_persists(tmp_path):
    manager = ModelsManager(str(tmp_path / "models.json"), str(tmp_path / "keys"))
    model = manager.add_model(
        name="qwen",
        provider="qwen",
        api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key="sk-qwen",
        model_id="qwen3-coder-plus",
        env_key="DASHSCOPE_API_KEY",
    )

    reloaded = ModelsManager(str(tmp_path / "models.json"), str(tmp_path / "keys"))

    assert reloaded.get_model(model["id"])["env_key"] == "DASHSCOPE_API_KEY"
