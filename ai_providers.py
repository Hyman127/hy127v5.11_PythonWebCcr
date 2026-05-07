#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
可移植 AI 提供商管理模块 (ai_providers.py)
==========================================

功能
----
• 多 AI 提供商统一管理 (Anthropic/Claude, Moonshot/Kimi, DeepSeek, 通义千问, 可扩展)
• 外部 JSON 配置文件维护模型列表 — 增删模型只需编辑 JSON
• 从提供商 API 自动拉取最新模型列表 (GET /v1/models)
• 多源 API 密钥管理 (Windows 凭据管理器 / 代码传入)
• Claude CLI 订阅凭证自动检测
• 提供商连接测试

移植到其他项目
--------------
1. 复制本文件到项目的 src/ (或任意包目录)
2. 首次 import 自动在 config_dir 下生成 ai_models_config.json
3. 按需编辑该 JSON 增删提供商和模型
4. 集成示例::

       from ai_providers import AIProviderManager
       mgr = AIProviderManager(config_dir="./")
       result = mgr.call_ai([{"role":"user","content":"你好"}], model="deepseek-chat")
       print(result["text"])
       print(result["usage"])

依赖: 仅 Python 标准库 (无第三方包)
"""

import os
import sys
import json
import time
import re
import subprocess
import shutil
import tempfile
import urllib.request
import urllib.error
import ssl
import ctypes
from pathlib import Path

if sys.platform == "win32":
    from ctypes import wintypes

# ═══════════════════════════════════════════════════════════
# 1. 内置默认提供商配置 (代码级兜底, 可被 JSON 配置覆盖)
# ═══════════════════════════════════════════════════════════

BUILTIN_PROVIDERS = {
    "anthropic": {
        "display_name": "Anthropic/Claude",
        "base_url": "https://api.anthropic.com",
        "api_type": "anthropic",
        "env_key": "ANTHROPIC_API_KEY",
        "cli_command": "claude",
        "models": [
            "claude-opus-4-7",
            "claude-sonnet-4-6",
            "claude-opus-4-6",
            "claude-haiku-4-5-20251001",
        ],
    },
    "moonshot": {
        "display_name": "Moonshot/Kimi",
        "base_url": "https://api.moonshot.cn/v1",
        "api_type": "openai_compatible",
        "env_key": "MOONSHOT_API_KEY",
        "models": [
            "kimi-k2.6",
            "kimi-k2.6-thinking",
            "kimi-k2.5",
            "kimi-k2",
            "moonshot-v1-auto",
            "moonshot-v1-128k",
            "moonshot-v1-32k",
            "moonshot-v1-8k",
        ],
    },
    "deepseek": {
        "display_name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "api_type": "openai_compatible",
        "env_key": "DEEPSEEK_API_KEY",
        "models": [
            "deepseek-v4-pro",
            "deepseek-v4-flash",
            "deepseek-chat",
            "deepseek-reasoner",
        ],
    },
    "qwen": {
        "display_name": "阿里云/通义千问",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_type": "openai_compatible",
        "env_key": "DASHSCOPE_API_KEY",
        "models": [
            "qwen3.6-max-preview",
            "qwen3.6-plus",
            "qwen3.6-flash",
            "qwen3.5-plus",
            "qwen3.5-flash",
            "qwen3.5-omni-plus",
            "qwen3.5-omni-flash",
            "qwen3-max-2026-01-23",
            "qwen3-coder-plus-2025-09-23",
            "qwq-plus-2025-03-05",
            "qwen-max-latest",
            "qwen-plus-latest",
            "qwen-turbo-latest",
            "qwen-long",
        ],
    },
    "hunyuan": {
        "display_name": "腾讯混元",
        "base_url": "https://api.hunyuan.cloud.tencent.com/v1",
        "api_type": "openai_compatible",
        "env_key": "HUNYUAN_API_KEY",
        "models": [
            "hy3-preview",
            "hunyuan-t1-latest",
            "hunyuan-turbos-latest",
            "hunyuan-turbo",
            "hunyuan-pro",
            "hunyuan-large",
            "hunyuan-a13b",
            "hunyuan-lite",
        ],
    },
    "mimo": {
        "display_name": "小米MiMo",
        "base_url": "https://api.xiaomimimo.com/v1",
        "api_type": "openai_compatible",
        "env_key": "XIAOMI_API_KEY",
        "models": [
            "mimo-v2.5-pro",
            "mimo-v2.5",
            "mimo-v2-pro",
            "mimo-v2-flash",
        ],
    },
    "doubao": {
        "display_name": "字节豆包",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "api_type": "openai_compatible",
        "env_key": "ARK_API_KEY",
        "models": [
            "doubao-seed-2-0-pro-260215",
            "doubao-seed-2-0-lite-260215",
            "doubao-seed-2-0-mini-260215",
            "doubao-seed-2-0-code-preview-260215",
            "doubao-seed-1-6-251015",
            "doubao-1.5-pro-256k",
            "doubao-1.5-lite-32k",
        ],
    },
    "openai_codex": {
        "display_name": "OpenAI/Codex",
        "base_url": "codex://cli",
        "api_type": "codex_cli",
        "env_key": "",
        "cli_command": "codex",
        "models": [
            "gpt-5.5",
            "gpt-5.4",
            "gpt-5.4-mini",
            "gpt-5.3-codex",
            "gpt-5.3-codex-spark",
            "gpt-5.2",
        ],
    },
}

CONFIG_FILENAME = "ai_models_config.json"
默认凭据服务名 = "Code880.AIProviders"

# ═══════════════════════════════════════════════════════════
# 2. 凭证文件路径
# ═══════════════════════════════════════════════════════════

CLAUDE_CREDENTIALS_FILE = Path.home() / ".claude" / ".credentials.json"
KIMI_CREDENTIAL_FILES = [
    Path.home() / ".kimi" / ".credentials.json",
    Path.home() / ".kimicode" / ".credentials.json",
    Path.home() / ".moonshot" / ".credentials.json",
]

# ═══════════════════════════════════════════════════════════
# 3. 工具函数
# ═══════════════════════════════════════════════════════════

def 命令可用(命令):
    return shutil.which(命令) is not None


def _Codex命令候选():
    candidates = []
    for name in ("codex.cmd", "codex.exe", "codex"):
        path = shutil.which(name)
        if path:
            candidates.append(path)
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        candidates.append(str(Path(appdata) / "npm" / "codex.cmd"))
    for path_item in os.environ.get("PATH", "").split(os.pathsep):
        if not path_item:
            continue
        for filename in ("codex.exe", "codex.cmd"):
            candidates.append(str(Path(path_item) / filename))
    seen = set()
    result = []
    for candidate in candidates:
        key = os.path.normcase(os.path.abspath(candidate))
        if key in seen or not os.path.exists(candidate):
            continue
        seen.add(key)
        result.append(candidate)
    return result


if sys.platform == "win32":
    CRED_TYPE_GENERIC = 1
    CRED_PERSIST_LOCAL_MACHINE = 2
    ERROR_NOT_FOUND = 1168

    LPBYTE = ctypes.POINTER(ctypes.c_ubyte)

    class FILETIME(ctypes.Structure):
        _fields_ = [
            ("dwLowDateTime", wintypes.DWORD),
            ("dwHighDateTime", wintypes.DWORD),
        ]


    class CREDENTIAL_ATTRIBUTEW(ctypes.Structure):
        _fields_ = [
            ("Keyword", wintypes.LPWSTR),
            ("Flags", wintypes.DWORD),
            ("ValueSize", wintypes.DWORD),
            ("Value", LPBYTE),
        ]


    class CREDENTIALW(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", LPBYTE),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.POINTER(CREDENTIAL_ATTRIBUTEW)),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]


    PCREDENTIALW = ctypes.POINTER(CREDENTIALW)
    _advapi32 = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    _CredReadW = _advapi32.CredReadW
    _CredReadW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
        ctypes.POINTER(PCREDENTIALW),
    ]
    _CredReadW.restype = wintypes.BOOL

    _CredWriteW = _advapi32.CredWriteW
    _CredWriteW.argtypes = [ctypes.POINTER(CREDENTIALW), wintypes.DWORD]
    _CredWriteW.restype = wintypes.BOOL

    _CredDeleteW = _advapi32.CredDeleteW
    _CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    _CredDeleteW.restype = wintypes.BOOL

    _CredFree = _advapi32.CredFree
    _CredFree.argtypes = [ctypes.c_void_p]
    _CredFree.restype = None


def _安全转整数(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0


def 脱敏显示密钥(密钥值):
    if not 密钥值:
        return ""
    if len(密钥值) <= 8:
        return "*" * len(密钥值)
    return f"{密钥值[:3]}***{密钥值[-4:]}"


def 获取默认密钥存储说明():
    if sys.platform == "win32":
        return "Windows凭据管理器"
    return "系统密钥库"


def _构造凭据目标名(provider_key):
    return f"{默认凭据服务名}:{provider_key}"


def 保存密钥到凭据管理器(target_name, 密钥值, 用户名="api_key", 注释=""):
    """将密钥保存到 Windows 凭据管理器。"""
    if sys.platform != "win32":
        return False, "当前系统不支持 Windows 凭据管理器"
    if not target_name or not 密钥值:
        return False, "目标名或密钥为空"

    blob = 密钥值.encode("utf-16-le")
    blob_buffer = ctypes.create_string_buffer(blob)
    credential = CREDENTIALW()
    credential.Type = CRED_TYPE_GENERIC
    credential.TargetName = target_name
    credential.Comment = 注释
    credential.CredentialBlobSize = len(blob)
    credential.CredentialBlob = ctypes.cast(blob_buffer, LPBYTE)
    credential.Persist = CRED_PERSIST_LOCAL_MACHINE
    credential.AttributeCount = 0
    credential.Attributes = None
    credential.TargetAlias = None
    credential.UserName = 用户名

    if not _CredWriteW(ctypes.byref(credential), 0):
        err = ctypes.get_last_error()
        return False, f"CredWriteW 失败: {err}"
    return True, f"已写入 {target_name}"


def 读取凭据管理器密钥(target_name):
    """从 Windows 凭据管理器读取密钥。"""
    if sys.platform != "win32":
        return False, "当前系统不支持 Windows 凭据管理器", ""

    p_credential = PCREDENTIALW()
    if not _CredReadW(target_name, CRED_TYPE_GENERIC, 0, ctypes.byref(p_credential)):
        err = ctypes.get_last_error()
        if err == ERROR_NOT_FOUND:
            return False, "未找到已保存密钥", ""
        return False, f"CredReadW 失败: {err}", ""

    try:
        credential = p_credential.contents
        if credential.CredentialBlobSize <= 0 or not credential.CredentialBlob:
            return True, "读取成功", ""
        raw = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
        return True, "读取成功", raw.decode("utf-16-le")
    finally:
        _CredFree(p_credential)


def 删除凭据管理器密钥(target_name):
    """删除 Windows 凭据管理器中的密钥。"""
    if sys.platform != "win32":
        return False, "当前系统不支持 Windows 凭据管理器"
    if not _CredDeleteW(target_name, CRED_TYPE_GENERIC, 0):
        err = ctypes.get_last_error()
        if err == ERROR_NOT_FOUND:
            return True, "密钥原本不存在"
        return False, f"CredDeleteW 失败: {err}"
    return True, f"已删除 {target_name}"


def 规范化Usage(usage=None, source="unknown", available=None):
    """统一整理各家接口返回的 usage 字段。

    返回格式固定为:
        {
            "input_tokens": int,
            "output_tokens": int,
            "total_tokens": int,
            "available": bool,
            "source": str,
        }
    """
    usage = usage if isinstance(usage, dict) else {}

    input_tokens = 0
    for key in (
        "input_tokens", "prompt_tokens", "prompt_token_count",
        "inputTokenCount", "prompt_eval_count",
    ):
        if key in usage:
            input_tokens = _安全转整数(usage.get(key))
            break
    for key in ("cache_creation_input_tokens", "cache_read_input_tokens"):
        input_tokens += _安全转整数(usage.get(key))

    output_tokens = 0
    for key in (
        "output_tokens", "completion_tokens", "completion_token_count",
        "outputTokenCount", "candidates_token_count", "eval_count",
    ):
        if key in usage:
            output_tokens = _安全转整数(usage.get(key))
            break

    total_tokens = 0
    for key in ("total_tokens", "totalTokenCount", "token_count"):
        if key in usage:
            total_tokens = _安全转整数(usage.get(key))
            break
    if total_tokens <= 0:
        total_tokens = input_tokens + output_tokens

    if available is None:
        available = bool(usage) and total_tokens > 0

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "available": bool(available),
        "source": source,
    }


def 生成统一AI结果(text, usage=None, source="unknown", available=None, provider="", model=""):
    return {
        "text": text,
        "usage": 规范化Usage(usage, source=source, available=available),
        "provider": provider,
        "model": model,
    }


def _递归提取令牌(obj):
    if isinstance(obj, dict):
        for k in ("accessToken", "token", "apiKey", "refreshToken"):
            v = obj.get(k)
            if isinstance(v, str) and len(v.strip()) >= 12:
                return v.strip()
        for v in obj.values():
            token = _递归提取令牌(v)
            if token:
                return token
    elif isinstance(obj, list):
        for v in obj:
            token = _递归提取令牌(v)
            if token:
                return token
    return None

# ═══════════════════════════════════════════════════════════
# 4. 凭证读取
# ═══════════════════════════════════════════════════════════

def 读取Claude订阅凭证():
    if not CLAUDE_CREDENTIALS_FILE.exists():
        return None
    try:
        with open(CLAUDE_CREDENTIALS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        oauth = data.get("claudeAiOauth", {})
        if not oauth.get("accessToken"):
            return None
        expires_at = oauth.get("expiresAt", 0)
        is_expired = expires_at < (time.time() * 1000) if expires_at else False
        return {
            "access_token": oauth["accessToken"],
            "expires_at": expires_at,
            "is_expired": is_expired,
            "subscription_type": oauth.get("subscriptionType", "unknown"),
            "rate_limit_tier": oauth.get("rateLimitTier", ""),
        }
    except Exception:
        return None


def 读取Kimi订阅凭证():
    for 路径 in KIMI_CREDENTIAL_FILES:
        if not 路径.exists():
            continue
        try:
            with open(路径, "r", encoding="utf-8") as f:
                data = json.load(f)
            token = _递归提取令牌(data)
            if token:
                return {"token": token, "source": str(路径)}
        except Exception:
            continue
    return None


def 读取Codex登录状态():
    candidates = _Codex命令候选()
    last_status = ""
    last_version = ""
    for command in candidates:
        version = ""
        try:
            version_proc = subprocess.run(
                [command, "--version"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=10,
            )
            version = (version_proc.stdout or version_proc.stderr or "").strip()
            last_version = version or last_version
        except Exception:
            version = ""
        try:
            proc = subprocess.run(
                [command, "login", "status"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=15,
            )
            output = (proc.stdout or proc.stderr or "").strip()
            last_status = output or last_status
            logged_in = proc.returncode == 0 and "logged in" in output.lower()
            if logged_in:
                return {
                    "logged_in": True,
                    "status": output or "Logged in using ChatGPT",
                    "version": version,
                    "command": command,
                }
        except Exception as e:
            last_status = str(e)

    auth_path = Path.home() / ".codex" / "auth.json"
    if auth_path.exists():
        try:
            data = json.loads(auth_path.read_text(encoding="utf-8", errors="ignore"))
            tokens = data.get("tokens") if isinstance(data, dict) else {}
            if data.get("auth_mode") == "chatgpt" and isinstance(tokens, dict) and tokens.get("access_token"):
                return {
                    "logged_in": True,
                    "status": "Logged in using ChatGPT (auth.json)",
                    "version": last_version,
                    "command": candidates[0] if candidates else "",
                }
        except Exception as e:
            last_status = f"auth.json 检测失败: {e}"

    if not candidates:
        return {
            "logged_in": False,
            "status": "未检测到 codex 命令",
            "version": "",
        }
    return {
        "logged_in": False,
        "status": last_status or "Codex CLI 未登录",
        "version": last_version,
        "command": candidates[0],
    }


def 读取模型文档密钥(doc_path):
    """从 Markdown 文档解析 API 密钥。

    文档格式示例::

        kimi: sk-xxxxxx
        DEEPSEEK: sk-xxxxxx
        QWEN: sk-xxxxxx
        HUNYUAN: sk-xxxxxx
        MIMO: sk-xxxxxx
        DOUBAO: sk-xxxxxx
    """
    密钥映射 = {}
    doc_path = Path(doc_path)
    if not doc_path.exists():
        return 密钥映射
    try:
        内容 = doc_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return 密钥映射
    _KEY_PAT = r"(?im)^[\s\d.]*{}\s*[:：]\s*([A-Za-z0-9_-]{{12,}})\s*$"
    匹配列表 = [
        ("moonshot", re.search(_KEY_PAT.format(r"kimi"), 内容)),
        ("deepseek", re.search(_KEY_PAT.format(r"deepseek"), 内容)),
        ("qwen", re.search(_KEY_PAT.format(r"qwen"), 内容)),
        ("hunyuan", re.search(_KEY_PAT.format(r"hunyuan|混元"), 内容)),
        ("mimo", re.search(_KEY_PAT.format(r"(?:(?:小米)?mimo|小米(?:mimo)?)"), 内容)),
        ("doubao", re.search(_KEY_PAT.format(r"doubao|豆包"), 内容)),
    ]
    for provider, m in 匹配列表:
        if m:
            密钥映射[provider] = m.group(1).strip()
    return 密钥映射

def 保存密钥到环境变量(变量名, 密钥值):
    """兼容保留: 将 API Key 持久化写入用户级环境变量。

    - Windows: 通过 setx 写入注册表 (HKCU\\Environment)
    - Linux/macOS: 追加到 ~/.bashrc 或 ~/.zshrc

    同时更新当前进程的 os.environ, 使本次运行立即生效。
    返回 (成功, 消息)。
    """
    if not 变量名 or not 密钥值:
        return False, "变量名或密钥为空"
    os.environ[变量名] = 密钥值
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["setx", 变量名, 密钥值],
                capture_output=True, timeout=10, check=True,
            )
            return True, f"已写入用户环境变量 {变量名}"
        except Exception as e:
            return False, f"setx 失败: {e}"
    else:
        rc_file = Path.home() / (".zshrc" if os.path.exists(Path.home() / ".zshrc") else ".bashrc")
        export_line = f'\nexport {变量名}="{密钥值}"\n'
        try:
            content = rc_file.read_text(encoding="utf-8") if rc_file.exists() else ""
            import re as _re
            pattern = rf'^export {_re.escape(变量名)}=.*$'
            if _re.search(pattern, content, _re.MULTILINE):
                content = _re.sub(pattern, f'export {变量名}="{密钥值}"', content, flags=_re.MULTILINE)
            else:
                content += export_line
            rc_file.write_text(content, encoding="utf-8")
            return True, f"已写入 {rc_file}"
        except Exception as e:
            return False, f"写入失败: {e}"


def 读取环境变量密钥(变量名):
    """兼容保留: 从环境变量读取 API Key, 无则返回空字符串。"""
    return os.environ.get(变量名, "").strip()


# ═══════════════════════════════════════════════════════════
# 5. AI 调用函数 (纯逻辑, 不依赖 GUI)
# ═══════════════════════════════════════════════════════════

def 调用Claude_API(
    api_key, base_url, model, messages,
    max_tokens=8192, timeout=180,
    on_response_change=None, should_cancel=None,
    return_usage=False,
):
    url = f"{base_url.rstrip('/')}/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = json.dumps({
        "model": model, "max_tokens": max_tokens, "messages": messages,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    ctx = ssl.create_default_context()
    resp = None
    try:
        resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
        if on_response_change:
            on_response_change(resp)
        if should_cancel and should_cancel():
            raise RuntimeError("请求已取消")
        result = json.loads(resp.read().decode("utf-8"))
        text = result["content"][0]["text"]
        if not return_usage:
            return text
        return 生成统一AI结果(
            text,
            usage=result.get("usage", {}),
            source="anthropic_response",
            provider="anthropic",
            model=model,
        )
    finally:
        if on_response_change:
            on_response_change(None)
        if resp is not None:
            resp.close()


def _提取OpenAI文本片段(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(_提取OpenAI文本片段(item) for item in value)
    if isinstance(value, dict):
        for key in ("text", "content", "output_text"):
            text = _提取OpenAI文本片段(value.get(key))
            if text:
                return text
    return ""


def _提取OpenAI选择文本(choice):
    if not isinstance(choice, dict):
        return "", ""
    正文片段 = []
    推理片段 = []
    delta = choice.get("delta")
    if isinstance(delta, dict):
        for key in ("content", "text"):
            text = _提取OpenAI文本片段(delta.get(key))
            if text:
                正文片段.append(text)
        for key in ("reasoning_content", "reasoning", "reasoning_text"):
            text = _提取OpenAI文本片段(delta.get(key))
            if text:
                推理片段.append(text)
    message = choice.get("message")
    if isinstance(message, dict):
        text = _提取OpenAI文本片段(message.get("content"))
        if text:
            正文片段.append(text)
        for key in ("reasoning_content", "reasoning"):
            text = _提取OpenAI文本片段(message.get(key))
            if text:
                推理片段.append(text)
    for key in ("text", "content"):
        text = _提取OpenAI文本片段(choice.get(key))
        if text:
            正文片段.append(text)
    return "".join(正文片段), "".join(推理片段)


def _提取OpenAI非流式文本(data):
    if not isinstance(data, dict):
        return ""
    choices = data.get("choices") or []
    文本片段 = []
    推理片段 = []
    for choice in choices:
        text, reasoning = _提取OpenAI选择文本(choice)
        if text:
            文本片段.append(text)
        if reasoning:
            推理片段.append(reasoning)
    if 文本片段:
        return "".join(文本片段).strip()
    text = _提取OpenAI文本片段(data.get("output_text") or data.get("content"))
    if text:
        return text.strip()
    return "".join(推理片段).strip()


def 调用OpenAI兼容API(
    api_key, base_url, model, messages,
    max_tokens=8192, timeout=180,
    on_response_change=None, should_cancel=None,
    return_usage=False,
):
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "content-type": "application/json",
    }
    body = {
        "model": model, "messages": messages,
        "max_tokens": max_tokens, "stream": True,
    }
    if return_usage:
        body["stream_options"] = {"include_usage": True}
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    ctx = ssl.create_default_context()
    resp = None
    try:
        resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
        if on_response_change:
            on_response_change(resp)
        full_content = []
        reasoning_content = []
        non_sse_lines = []
        usage_info = None
        for line in resp:
            if should_cancel and should_cancel():
                raise RuntimeError("请求已取消")
            line = line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            if not line.startswith("data:"):
                if line.startswith("{") or line.startswith("["):
                    non_sse_lines.append(line)
                continue
            data_str = line[5:].strip()
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                choices = chunk.get("choices") or []
                if choices:
                    text, reasoning = _提取OpenAI选择文本(choices[0])
                    if text:
                        full_content.append(text)
                    if reasoning:
                        reasoning_content.append(reasoning)
                if return_usage:
                    chunk_usage = chunk.get("usage")
                    if chunk_usage:
                        usage_info = chunk_usage
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
        result = "".join(full_content).strip()
        if not result and non_sse_lines:
            try:
                result = _提取OpenAI非流式文本(json.loads("".join(non_sse_lines)))
            except json.JSONDecodeError:
                result = ""
        if not result:
            result = "".join(reasoning_content).strip()
        if not result:
            raise RuntimeError("API返回数据异常: 流式响应未包含有效文本")
        if not return_usage:
            return result
        return 生成统一AI结果(
            result,
            usage=usage_info,
            source="openai_stream_usage" if usage_info else "usage_unavailable",
            available=bool(usage_info),
            provider="",
            model=model,
        )
    finally:
        if on_response_change:
            on_response_change(None)
        if resp is not None:
            resp.close()


def 调用命令行AI(
    命令名, 提示文本, 超时=300, 工具名="CLI",
    on_process_change=None, should_cancel=None,
):
    process = None
    命令候选 = [命令名]
    if 命令名 == "kimi":
        命令候选.extend(["kimi-code", "kimicode"])
    最后错误 = ""
    try:
        真实命令 = next((cmd for cmd in 命令候选 if 命令可用(cmd)), None)
        if not 真实命令:
            raise FileNotFoundError("/".join(命令候选))
        尝试命令列表 = [
            [真实命令, "-p", "--output-format", "text"],
            [真实命令, "-p"],
        ]
        for i, cmd in enumerate(尝试命令列表):
            process = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True,
                encoding="utf-8", errors="replace",
            )
            if on_process_change:
                on_process_change(process)
            stdout, stderr = process.communicate(input=提示文本, timeout=超时)
            if should_cancel and should_cancel():
                raise RuntimeError("任务已停止")
            if process.returncode == 0:
                output = (stdout or "").strip()
                if output:
                    return output
                最后错误 = f"{工具名}返回空结果"
            else:
                最后错误 = (stderr or "").strip() or f"{工具名}调用失败"
                if i == 0 and "output-format" in (stderr or "").lower():
                    continue
            break
        raise RuntimeError(最后错误 or f"{工具名}调用失败")
    except FileNotFoundError:
        raise RuntimeError(f"未找到{命令名}命令，请确保已安装并完成登录")
    except subprocess.TimeoutExpired:
        if process and process.poll() is None:
            process.kill()
            process.communicate()
        raise RuntimeError(f"{工具名}调用超时({超时}秒)，请减少输入规模")
    finally:
        if on_process_change:
            on_process_change(None)


def _整理Codex_CLI错误(错误文本, model):
    text = (错误文本 or "").strip()
    if not text:
        return "Codex CLI 调用失败"

    提示 = []
    if "requires a newer version of Codex" in text:
        提示.append(
            f"{model} 需要更新版本的 Codex CLI；请升级 Codex CLI，或临时换用 gpt-5.3-codex / gpt-5.2"
        )
    if "[features].web_search" in text or "features.web_search" in text:
        配置路径 = Path.home() / ".codex" / "config.toml"
        提示.append(
            f"{配置路径} 中仍有旧配置 [features] web_search = true；新版 Codex 请改为顶层 web_search = \"live\" 或 \"disabled\""
        )

    if 提示:
        原始错误 = re.sub(r"\s+", " ", text)
        return "；".join(提示) + f"。原始错误: {原始错误[:360]}"
    return text[:500]


def 调用Codex_CLI(
    提示文本, model,
    超时=300, on_process_change=None, should_cancel=None,
):
    codex_command = next(iter(_Codex命令候选()), "")
    if not codex_command:
        raise RuntimeError("未找到 codex 命令，请确保 VSCode/Codex CLI 已安装并完成登录")
    output_path = None
    process = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".txt", delete=False,
        ) as tmp:
            output_path = tmp.name
        cmd = [
            codex_command, "exec",
            "-m", model,
            "--skip-git-repo-check",
            "--sandbox", "read-only",
            "--color", "never",
            "-o", output_path,
            "-",
        ]
        process = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace",
        )
        if on_process_change:
            on_process_change(process)
        stdout, stderr = process.communicate(input=提示文本, timeout=超时)
        if should_cancel and should_cancel():
            raise RuntimeError("任务已停止")
        if process.returncode != 0:
            err = "\n".join(x.strip() for x in [stderr or "", stdout or ""] if x.strip())
            raise RuntimeError(_整理Codex_CLI错误(err, model))
        if output_path and os.path.exists(output_path):
            text = Path(output_path).read_text(encoding="utf-8", errors="replace").strip()
            if text:
                return text
        text = (stdout or "").strip()
        if text:
            return text
        raise RuntimeError("Codex CLI 返回空结果")
    except subprocess.TimeoutExpired:
        if process and process.poll() is None:
            process.kill()
            process.communicate()
        raise RuntimeError(f"Codex CLI 调用超时({超时}秒)，请减少输入规模")
    finally:
        if on_process_change:
            on_process_change(None)
        if output_path:
            try:
                os.unlink(output_path)
            except Exception:
                pass

# ═══════════════════════════════════════════════════════════
# 6. 从 API 获取模型列表
# ═══════════════════════════════════════════════════════════

def 获取API模型列表(base_url, api_key, api_type="openai_compatible", timeout=15):
    """向提供商 API 请求可用模型列表。

    大多数 OpenAI 兼容平台支持 GET /models；Anthropic 也支持 GET /v1/models。
    返回 model id 列表, 失败返回空列表。
    """
    ctx = ssl.create_default_context()
    if api_type == "anthropic":
        url = f"{base_url.rstrip('/')}/v1/models"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
    else:
        url = f"{base_url.rstrip('/')}/models"
        headers = {"Authorization": f"Bearer {api_key}"}
    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return sorted(
            item["id"] for item in data.get("data", []) if item.get("id")
        )
    except Exception:
        return []

# ═══════════════════════════════════════════════════════════
# 7. AIProviderManager — 核心管理器
# ═══════════════════════════════════════════════════════════

class AIProviderManager:
    """AI 提供商管理器。

    Parameters
    ----------
    config_dir : str | Path
        配置文件 (ai_models_config.json) 所在目录, 默认为本文件上一级目录。
    key_doc_path : str | Path | None
        为兼容旧调用保留，当前默认不再作为 API Key 来源。
    """

    def __init__(self, config_dir=None, key_doc_path=None):
        if config_dir is None:
            if getattr(sys, "frozen", False):
                config_dir = Path(sys.executable).parent
            else:
                config_dir = Path(__file__).parent.parent
        self.config_dir = Path(config_dir)
        self.config_path = self.config_dir / CONFIG_FILENAME
        self.key_doc_path = Path(key_doc_path) if key_doc_path else None

        self.providers = {}
        self.provider_display = {}
        self.provider_key_from_display = {}
        self.provider_defaults = {}

        self.status = {}
        self.doc_keys = {}
        self.cli_credentials = None

        self._load_config()
        self.cli_credentials = 读取Claude订阅凭证()

    # ── 配置文件 ──────────────────────────────────────

    def _load_config(self):
        providers = None
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                providers = data.get("providers")
            except Exception:
                pass

        if providers:
            self.providers = {}
            for pkey, builtin in BUILTIN_PROVIDERS.items():
                if pkey in providers:
                    merged = {**builtin}
                    cfg = providers[pkey]
                    if cfg.get("display_name"):
                        merged["display_name"] = cfg["display_name"]
                    if cfg.get("base_url"):
                        merged["base_url"] = cfg["base_url"]
                    if cfg.get("api_type"):
                        merged["api_type"] = cfg["api_type"]
                    if cfg.get("env_key"):
                        merged["env_key"] = cfg["env_key"]
                    if "models" in cfg and isinstance(cfg["models"], list):
                        merged["models"] = cfg["models"]
                    self.providers[pkey] = merged
                else:
                    self.providers[pkey] = dict(builtin)
            for pkey, pdata in providers.items():
                if pkey not in self.providers:
                    self.providers[pkey] = pdata
        else:
            self.providers = {k: dict(v) for k, v in BUILTIN_PROVIDERS.items()}
            self.save_config()

        self._rebuild_maps()

    def _rebuild_maps(self):
        self.provider_display = {
            k: v["display_name"] for k, v in self.providers.items()
        }
        self.provider_key_from_display = {
            v: k for k, v in self.provider_display.items()
        }
        self.provider_defaults = {
            k: (v["base_url"], v["models"]) for k, v in self.providers.items()
        }

    def save_config(self):
        data = {
            "_说明": "AI模型配置文件 — 直接编辑 models 列表来增删模型",
            "_模型维护": (
                "方法1: 直接在下方 models 数组中增删模型名; "
                "方法2: 在应用中使用'刷新模型列表'从API自动获取"
            ),
            "providers": {},
        }
        for pkey, pdata in self.providers.items():
            data["providers"][pkey] = {
                "display_name": pdata["display_name"],
                "base_url": pdata["base_url"],
                "api_type": pdata.get("api_type", "openai_compatible"),
                "env_key": pdata.get("env_key", ""),
                "models": pdata["models"],
            }
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def reload_config(self):
        self._load_config()
        self.cli_credentials = 读取Claude订阅凭证()

    # ── 密钥存储 ────────────────────────────────────────

    def _get_provider_secret_target(self, provider_key):
        return _构造凭据目标名(provider_key)

    def _get_provider_secret_info(self, provider_key, include_key=False):
        p = self.providers.get(provider_key, {})
        display_name = p.get("display_name", provider_key)
        info = {
            "provider": provider_key,
            "display_name": display_name,
            "target_name": self._get_provider_secret_target(provider_key),
            "backend": "",
            "source": "",
            "message": "",
            "has_key": False,
            "masked_key": "",
            "api_key": "",
        }

        ok, msg, key = 读取凭据管理器密钥(info["target_name"])
        if ok and key:
            info.update({
                "backend": "credential_manager",
                "source": "credential_manager",
                "message": msg,
                "has_key": True,
                "masked_key": 脱敏显示密钥(key),
                "api_key": key if include_key else "",
            })
            return info

        if sys.platform == "win32":
            info["message"] = "未在 Windows 凭据管理器中找到已保存密钥"
        else:
            info["message"] = "当前系统未实现凭据管理器读写"
        return info

    # ── 模型列表管理 ──────────────────────────────────

    def get_models(self, provider_key):
        p = self.providers.get(provider_key)
        return list(p["models"]) if p else []

    def get_all_models(self):
        models = []
        for p in self.providers.values():
            models.extend(p["models"])
        return models

    def update_models(self, provider_key, model_list, save=True):
        if provider_key in self.providers:
            self.providers[provider_key]["models"] = list(model_list)
            self._rebuild_maps()
            if save:
                self.save_config()

    def fetch_and_update_models(self, provider_key, api_key):
        """从提供商 API 拉取最新模型列表并更新配置。

        返回 (新模型列表, 是否成功)。
        """
        p = self.providers.get(provider_key)
        if not p:
            return [], False
        fetched = 获取API模型列表(
            p["base_url"], api_key, p.get("api_type", "openai_compatible"),
        )
        if fetched:
            self.update_models(provider_key, fetched)
            return fetched, True
        return p["models"], False

    # ── 模型→提供商解析 ───────────────────────────────

    def resolve_model(self, model_name, ui_key=None, current_provider=None):
        """给定模型名, 返回 (provider_key, api_key, base_url)。

        api_key 查找优先级: ui_key (当前UI) > 凭据管理器。
        """
        for pkey, pdata in self.providers.items():
            if model_name in pdata["models"]:
                key = self.load_api_key(pkey)
                if pkey == current_provider and ui_key:
                    key = ui_key
                return pkey, key, pdata["base_url"]
        return (current_provider or ""), (ui_key or ""), ""

    def is_provider_model(self, provider_key, model_name):
        p = self.providers.get(provider_key)
        return model_name in p["models"] if p else False

    # ── AI 调用 (统一入口) ─────────────────────────────

    def call_ai(
        self, messages, model, api_key=None, auth_mode="api_key",
        max_tokens=8192, timeout=300,
        should_cancel_fn=None, on_process_fn=None, on_response_fn=None,
        provider_override=None, base_url_override=None,
    ):
        """统一 AI 调用入口。

        Parameters
        ----------
        auth_mode : "api_key" | "claude_cli" | "codex_cli"
        model : 模型名
        api_key : 传入的 API Key (可选, 若 CLI 模式则忽略)

        Returns
        -------
        dict
            统一返回:
                {
                    "text": str,
                    "usage": {
                        "input_tokens": int,
                        "output_tokens": int,
                        "total_tokens": int,
                        "available": bool,
                        "source": str,
                    },
                    "provider": str,
                    "model": str,
                }
        """
        provider, resolved_key, base_url = self.resolve_model(
            model,
            ui_key=api_key,
            current_provider=provider_override,
        )
        provider = provider_override or provider
        use_key = api_key or resolved_key
        if base_url_override:
            base_url = base_url_override

        if auth_mode == "claude_cli" and self.is_provider_model("anthropic", model):
            prompt_parts = []
            for m in messages:
                c = m.get("content", "")
                if isinstance(c, list):
                    for block in c:
                        if isinstance(block, dict) and block.get("type") == "text":
                            prompt_parts.append(block["text"])
                elif isinstance(c, str):
                    prompt_parts.append(c)
            text = 调用命令行AI(
                "claude", "\n\n".join(prompt_parts), 超时=timeout, 工具名="Claude",
                on_process_change=on_process_fn, should_cancel=should_cancel_fn,
            )
            return 生成统一AI结果(
                text,
                usage={},
                source="claude_cli",
                available=False,
                provider="anthropic",
                model=model,
            )

        if auth_mode == "codex_cli" and self.is_provider_model("openai_codex", model):
            prompt_parts = []
            for m in messages:
                c = m.get("content", "")
                if isinstance(c, list):
                    for block in c:
                        if isinstance(block, dict) and block.get("type") == "text":
                            prompt_parts.append(block["text"])
                elif isinstance(c, str):
                    prompt_parts.append(c)
            text = 调用Codex_CLI(
                "\n\n".join(prompt_parts), model,
                超时=timeout,
                on_process_change=on_process_fn,
                should_cancel=should_cancel_fn,
            )
            return 生成统一AI结果(
                text,
                usage={},
                source="codex_cli",
                available=False,
                provider="openai_codex",
                model=model,
            )

        if not use_key:
            raise ValueError(f"未找到模型 {model} 所属提供商的 API Key")

        p = self.providers.get(provider, {})
        api_type = p.get("api_type", "openai_compatible")

        if api_type == "anthropic":
            result = 调用Claude_API(
                use_key, base_url, model, messages,
                max_tokens=max_tokens, timeout=timeout,
                on_response_change=on_response_fn, should_cancel=should_cancel_fn,
                return_usage=True,
            )
        else:
            result = 调用OpenAI兼容API(
                use_key, base_url, model, messages,
                max_tokens=max_tokens, timeout=timeout,
                on_response_change=on_response_fn, should_cancel=should_cancel_fn,
                return_usage=True,
            )
        result["provider"] = provider
        result["model"] = model
        return result

    # ── 提供商连接测试 ────────────────────────────────

    def test_provider(self, provider_key, api_key):
        """测试提供商连接, 返回 (成功与否, 消息)。"""
        p = self.providers.get(provider_key)
        if not p:
            return False, f"未知提供商: {provider_key}"
        model = p["models"][0] if p["models"] else ""
        if not model:
            return False, "无可用模型"
        try:
            test_msg = [{"role": "user", "content": "请回复两个字: 成功"}]
            api_type = p.get("api_type", "openai_compatible")
            if api_type == "anthropic":
                调用Claude_API(api_key, p["base_url"], model, test_msg,
                              max_tokens=32, timeout=15)
            else:
                调用OpenAI兼容API(api_key, p["base_url"], model, test_msg,
                                max_tokens=32, timeout=15)
            return True, "连接成功"
        except Exception as e:
            return False, str(e)[:200]

    def save_api_key(self, provider_key, api_key):
        """将 API Key 持久化到系统安全存储。

        当前实现使用 Windows 凭据管理器。
        返回 (成功, 消息)。
        """
        p = self.providers.get(provider_key)
        if not p:
            return False, f"未知提供商: {provider_key}"
        if sys.platform != "win32":
            return False, "当前系统暂未实现凭据管理器存储"
        return 保存密钥到凭据管理器(
            self._get_provider_secret_target(provider_key),
            api_key,
            用户名=p.get("display_name", provider_key),
            注释=f"{p.get('display_name', provider_key)} API Key",
        )

    def load_api_key(self, provider_key):
        """读取指定 provider 的 API Key。"""
        info = self._get_provider_secret_info(
            provider_key,
            include_key=True,
        )
        return info.get("api_key", "")

    def delete_api_key(self, provider_key):
        """删除指定 provider 的已保存 API Key。"""
        p = self.providers.get(provider_key)
        if not p:
            return False, f"未知提供商: {provider_key}"
        if sys.platform != "win32":
            return False, "当前系统暂未实现凭据管理器删除"
        return 删除凭据管理器密钥(self._get_provider_secret_target(provider_key))

    def get_api_key_info(self, provider_key, include_key=False):
        """返回指定 provider 的密钥状态信息，适合前端展示。"""
        return self._get_provider_secret_info(
            provider_key,
            include_key=include_key,
        )

    def get_secret_storage_label(self):
        return 获取默认密钥存储说明()


# ═══════════════════════════════════════════════════════════
# 8. 向后兼容: 模块级常量 (从内置默认值导出, 便于迁移)
# ═══════════════════════════════════════════════════════════

CLAUDE_DEFAULT_BASE_URL = BUILTIN_PROVIDERS["anthropic"]["base_url"]
KIMI_DEFAULT_BASE_URL = BUILTIN_PROVIDERS["moonshot"]["base_url"]
DEEPSEEK_DEFAULT_BASE_URL = BUILTIN_PROVIDERS["deepseek"]["base_url"]
QWEN_DEFAULT_BASE_URL = BUILTIN_PROVIDERS["qwen"]["base_url"]
CODEX_DEFAULT_BASE_URL = BUILTIN_PROVIDERS["openai_codex"]["base_url"]

CLAUDE_MODELS = BUILTIN_PROVIDERS["anthropic"]["models"]
KIMI_API_MODELS = BUILTIN_PROVIDERS["moonshot"]["models"]
DEEPSEEK_MODELS = BUILTIN_PROVIDERS["deepseek"]["models"]
QWEN_MODELS = BUILTIN_PROVIDERS["qwen"]["models"]
CODEX_MODELS = BUILTIN_PROVIDERS["openai_codex"]["models"]
KIMI_MODELS = ["kimi-k2.6", "kimi-k2.6-thinking", "kimi-k2.5", "kimi-k2"]

API_PROVIDER_DISPLAY = {k: v["display_name"] for k, v in BUILTIN_PROVIDERS.items()}
API_PROVIDER_KEY_FROM_DISPLAY = {v: k for k, v in API_PROVIDER_DISPLAY.items()}
API_PROVIDER_DEFAULTS = {
    k: (v["base_url"], v["models"]) for k, v in BUILTIN_PROVIDERS.items()
}
