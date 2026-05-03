import base64
import json
import logging
import os
import uuid
from dataclasses import dataclass, asdict


logger = logging.getLogger(__name__)


MODEL_OPTIONAL_DEFAULTS = {
    "protocol": "openai_chat",
    "runtime": "api",
    "roles": ["chat"],
    "reasoning_profile": "max",
    "is_default": False,
    "orchestration": {"enabled": False},
}

MODEL_FIELDS = {
    "id", "name", "provider", "api_base", "api_key_masked", "model_id",
    "enabled", *MODEL_OPTIONAL_DEFAULTS.keys(),
}


@dataclass
class AIModel:
    id: str
    name: str
    provider: str          # openai / anthropic / deepseek / custom
    api_base: str
    api_key_masked: str    # sk-****abcd
    model_id: str          # gpt-4o / claude-3.5-sonnet / deepseek-chat
    enabled: bool = True
    protocol: str = "openai_chat"
    runtime: str = "api"
    roles: list[str] | None = None
    reasoning_profile: str = "max"
    is_default: bool = False
    orchestration: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class ModelsManager:
    def __init__(self, models_path: str, keys_dir: str):
        self.models_path = models_path
        self.keys_dir = keys_dir
        models_dir = os.path.dirname(models_path)
        if models_dir:
            os.makedirs(models_dir, exist_ok=True)
        os.makedirs(keys_dir, exist_ok=True)
        self._models: dict[str, dict] = {}
        self._api_keys: dict[str, str] = {}
        self._load()

    @property
    def _keys_path(self) -> str:
        return os.path.join(self.keys_dir, "api_keys.enc")

    def _load(self):
        if os.path.isfile(self.models_path):
            with open(self.models_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._models = {
                m["id"]: self._normalize_model(m)
                for m in data.get("models", [])
                if m.get("id")
            }
            self._ensure_default_model()
        self._load_keys()

    def _save(self):
        data = {"models": list(self._models.values())}
        with open(self.models_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load_keys(self):
        if not os.path.isfile(self._keys_path):
            return
        try:
            with open(self._keys_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return
        for mid, record in data.get("keys", {}).items():
            key = self._unprotect_key(record)
            if key:
                self._api_keys[mid] = key

    def _save_keys(self):
        data = {
            "version": 1,
            "keys": {
                mid: self._protect_key(key)
                for mid, key in self._api_keys.items()
            },
        }
        with open(self._keys_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _protect_key(key: str) -> dict:
        raw = key.encode("utf-8")
        try:
            import win32crypt
            encrypted = win32crypt.CryptProtectData(
                raw, "Code880Web AI Key", None, None, None, 0
            )
            return {
                "scheme": "dpapi",
                "data": base64.b64encode(encrypted).decode("ascii"),
            }
        except Exception as exc:
            # Development fallback for environments without pywin32/DPAPI.
            # Production Windows installs should use the dpapi branch above.
            logger.warning(
                "DPAPI unavailable; using development API key fallback: %s",
                exc,
            )
            return {
                "scheme": "base64",
                "data": base64.b64encode(raw).decode("ascii"),
            }

    @staticmethod
    def _unprotect_key(record: dict) -> str | None:
        try:
            scheme = record.get("scheme")
            data = base64.b64decode(record.get("data", ""))
            if scheme == "dpapi":
                import win32crypt
                _desc, decrypted = win32crypt.CryptUnprotectData(
                    data, None, None, None, 0
                )
                return decrypted.decode("utf-8")
            if scheme == "base64":
                return data.decode("utf-8")
        except Exception:
            return None
        return None

    @staticmethod
    def _mask_key(key: str) -> str:
        if len(key) <= 8:
            return "****"
        return key[:3] + "****" + key[-4:]

    @staticmethod
    def infer_protocol(provider: str, api_base: str) -> str:
        provider_l = (provider or "").lower()
        base_l = (api_base or "").lower()
        if provider_l == "anthropic" or "anthropic" in base_l:
            return "anthropic_messages"
        if provider_l == "gemini" and "/openai" not in base_l:
            return "gemini_openai"
        return "openai_chat"

    @staticmethod
    def _normalize_roles(roles) -> list[str]:
        if isinstance(roles, list):
            cleaned = [str(role).strip() for role in roles if str(role).strip()]
            return cleaned or ["chat"]
        if isinstance(roles, str):
            cleaned = [r.strip() for r in roles.split(",") if r.strip()]
            return cleaned or ["chat"]
        return ["chat"]

    def _normalize_model(self, model: dict) -> dict:
        normalized = {k: v for k, v in model.items() if k in MODEL_FIELDS}
        for key, value in MODEL_OPTIONAL_DEFAULTS.items():
            if key not in normalized:
                if key == "protocol":
                    normalized[key] = self.infer_protocol(
                        normalized.get("provider", ""),
                        normalized.get("api_base", ""),
                    )
                elif isinstance(value, (list, dict)):
                    normalized[key] = value.copy()
                else:
                    normalized[key] = value
        normalized["roles"] = self._normalize_roles(normalized.get("roles"))
        normalized["enabled"] = bool(normalized.get("enabled", True))
        normalized["is_default"] = bool(normalized.get("is_default", False))
        if not isinstance(normalized.get("orchestration"), dict):
            normalized["orchestration"] = {"enabled": False}
        return normalized

    def _ensure_default_model(self):
        enabled = [m for m in self._models.values() if m.get("enabled")]
        if not enabled:
            return
        defaults = [m for m in enabled if m.get("is_default")]
        if defaults:
            keep_id = defaults[0]["id"]
            for model in self._models.values():
                model["is_default"] = model["id"] == keep_id
            return
        enabled[0]["is_default"] = True

    def get_default_model(self) -> dict | None:
        enabled = [m for m in self._models.values() if m.get("enabled")]
        if not enabled:
            return None
        for model in enabled:
            if model.get("is_default"):
                return model
        return enabled[0]

    def _set_default_flag(self, mid: str):
        for model in self._models.values():
            model["is_default"] = model["id"] == mid

    def add_model(
        self, name: str, provider: str, api_base: str,
        api_key: str, model_id: str, **kwargs
    ) -> dict:
        mid = uuid.uuid4().hex[:8]
        model = {
            "id": mid,
            "name": name,
            "provider": provider,
            "api_base": api_base,
            "api_key_masked": self._mask_key(api_key),
            "model_id": model_id,
            "enabled": True,
            "protocol": kwargs.get("protocol") or self.infer_protocol(provider, api_base),
            "runtime": kwargs.get("runtime") or "api",
            "roles": self._normalize_roles(kwargs.get("roles")),
            "reasoning_profile": kwargs.get("reasoning_profile") or "max",
            "is_default": bool(kwargs.get("is_default")) or not self._models,
            "orchestration": kwargs.get("orchestration") or {"enabled": False},
        }
        model = self._normalize_model(model)
        if model["is_default"]:
            self._set_default_flag(mid)
        self._models[mid] = model
        self._api_keys[mid] = api_key
        self._ensure_default_model()
        self._save()
        self._save_keys()
        return model

    def update_model(self, mid: str, **kwargs) -> dict | None:
        model = self._models.get(mid)
        if not model:
            return None
        if "api_key" in kwargs:
            key = kwargs.pop("api_key")
            if key:
                self._api_keys[mid] = key
                model["api_key_masked"] = self._mask_key(key)
        for k, v in kwargs.items():
            if k not in MODEL_FIELDS or k in {"id", "api_key_masked"}:
                continue
            if k == "roles":
                model[k] = self._normalize_roles(v)
            elif k == "orchestration":
                model[k] = v if isinstance(v, dict) else {"enabled": False}
            elif k == "is_default":
                model[k] = bool(v)
            elif k == "enabled":
                model[k] = bool(v)
            else:
                model[k] = v
        model = self._normalize_model(model)
        self._models[mid] = model
        if model.get("is_default"):
            self._set_default_flag(mid)
        self._ensure_default_model()
        self._save()
        self._save_keys()
        return self._models[mid]

    def remove_model(self, mid: str) -> bool:
        if mid not in self._models:
            return False
        del self._models[mid]
        self._api_keys.pop(mid, None)
        self._ensure_default_model()
        self._save()
        self._save_keys()
        return True

    def list_models(self) -> list[dict]:
        return list(self._models.values())

    def get_model(self, mid: str) -> dict | None:
        return self._models.get(mid)

    def get_api_key(self, mid: str) -> str | None:
        return self._api_keys.get(mid)

    async def test_model(self, mid: str) -> dict:
        model = self._models.get(mid)
        if not model:
            return {"ok": False, "error": "模型不存在"}
        api_key = self._api_keys.get(mid)
        if not api_key:
            return {"ok": False, "error": "API Key 未配置"}
        protocol = model.get("protocol") or "openai_chat"
        if protocol not in ("openai_chat", "openai_compatible"):
            return {"ok": False, "error": f"Protocol {protocol} is saved but not connected yet"}
        try:
            import httpx
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            body = {
                "model": model["model_id"],
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 5,
            }
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{model['api_base'].rstrip('/')}/chat/completions",
                    json=body,
                    headers=headers,
                )
            if resp.status_code == 200:
                return {"ok": True}
            return {"ok": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
