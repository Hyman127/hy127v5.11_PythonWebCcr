#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
便携式 Python 开发环境一键安装工具 v2.0
功能: 自动下载并部署 Python + uv + VSCode，配置 PATH/环境变量/镜像源/右键菜单
可从任意位置运行，会自动下载所需工具到目标目录

打包: .venv\\Scripts\\python.exe -m PyInstaller --onefile --windowed --name 一键安装 src\\一键安装卸载.py
作者: hy127.cn 工程"猿"工具网 Python 办公自动化 学员专用
"""

import os
import sys
import winreg
import ctypes
import subprocess
import datetime
import traceback
import zipfile
import gzip
import zlib
import shutil
import stat
import tempfile
import urllib.request
import urllib.error
import urllib.parse
import ssl
import threading
import time
import json
import queue
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog

# ==================== 配置常量 ====================

INSTALL_DIR_DEFAULT = r"C:\PythonDev"
PYTHON_VERSION = "3.12"
PYTHON_OFFICIAL_URL = "https://www.python.org/"
UV_OFFICIAL_URL = "https://github.com/astral-sh/uv"
VSCODE_OFFICIAL_URL = "https://code.visualstudio.com/"
VSCODE_LICENSE_URL = "https://code.visualstudio.com/license"

UV_DOWNLOAD_URLS = [
    "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip",
]

VSCODE_DOWNLOAD_URLS = [
    "https://update.code.visualstudio.com/latest/win32-x64-archive/stable",
]
REQUIRED_VSCODE_EXTENSIONS = [
    "ms-python.python",
    "ms-python.debugpy",
]
OPTIONAL_VSCODE_EXTENSIONS = [
    "ms-python.vscode-pylance",
]
VSCODE_EXTENSION_CHECK_URLS = {
    "ms-python.python": "https://marketplace.visualstudio.com/_apis/public/gallery/publishers/ms-python/vsextensions/python/latest/vspackage",
    "ms-python.debugpy": "https://marketplace.visualstudio.com/_apis/public/gallery/publishers/ms-python/vsextensions/debugpy/latest/vspackage",
}
VSCODE_EXTENSION_QUERY_URL = "https://marketplace.visualstudio.com/_apis/public/gallery/extensionquery?api-version=7.2-preview.1"
VSCODE_EXTENSION_TARGETS_BY_ARCH = {
    "x64": ("win32-x64", ""),
    "arm64": ("win32-arm64", "win32-x64", ""),
    "ia32": ("win32-ia32", ""),
}
SUPPORTED_WINDOWS_ARCHES = ("x64",)
VSCODE_EXTENSION_LOCAL_INSTALL_TIMEOUT = 180
VSCODE_EXTENSION_MARKET_INSTALL_TIMEOUT = 300

MIRROR_URL = "https://mirrors.aliyun.com/pypi/simple/"
MIRROR_HOST = "mirrors.aliyun.com"
PYPI_OFFICIAL_URL = "https://pypi.org/simple/"
PYPI_OFFICIAL_HOST = "pypi.org"
MANAGED_INDEX_URLS = [MIRROR_URL, PYPI_OFFICIAL_URL]
PIP_CONFIG_MARKER = "# Managed by HY127 one-click installer"
LEGACY_PIP_CONFIG_MARKERS = ('# Managed by 工程"猿"一键安装',)
PYTHON_BUILD_STANDALONE_URL = "https://github.com/astral-sh/python-build-standalone/releases"
VSCODE_MARKETPLACE_URL = VSCODE_EXTENSION_CHECK_URLS["ms-python.python"]

RESOURCE_CANDIDATES = {
    "uv": [
        {
            "name": "uv 官方 GitHub",
            "url": UV_DOWNLOAD_URLS[0],
            "source": "official",
            "env": "HY127_UV_DOWNLOAD_URL",
        },
    ],
    "python": [
        {
            "name": "Python 官方 Astral 构建",
            "url": PYTHON_BUILD_STANDALONE_URL,
            "source": "official",
            "env": "HY127_UV_PYTHON_INSTALL_MIRROR",
        },
    ],
    "vscode": [
        {
            "name": "VSCode 官方 Microsoft",
            "url": VSCODE_DOWNLOAD_URLS[0],
            "source": "official",
            "env": "HY127_VSCODE_DOWNLOAD_URL",
        },
    ],
    "extensions": [
        {
            "name": "VSCode 扩展市场官方",
            "url": VSCODE_MARKETPLACE_URL,
            "source": "official",
            "env": "HY127_VSCODE_EXTENSION_MARKETPLACE",
        },
    ],
    "pypi": [
        {
            "name": "阿里云 PyPI 镜像",
            "url": MIRROR_URL,
            "source": "china",
            "env": "",
        },
        {
            "name": "官方 PyPI",
            "url": PYPI_OFFICIAL_URL,
            "source": "official",
            "env": "",
        },
    ],
}

RESOURCE_LABELS = {
    "uv": "uv 下载",
    "python": "Python 运行时",
    "vscode": "VSCode 下载",
    "extensions": "VSCode 扩展",
    "pypi": "Python 依赖源",
}


def _candidate_with_env_override(group, item):
    env_name = item.get("env", "")
    override = os.environ.get(env_name, "").strip() if env_name else ""
    if not override:
        return [item]
    custom = dict(item)
    custom["name"] = f"{RESOURCE_LABELS.get(group, group)} 自定义资源"
    custom["url"] = override
    custom["source"] = "custom"
    return [custom, item]


def get_resource_candidates():
    candidates = {}
    for group, items in RESOURCE_CANDIDATES.items():
        expanded = []
        for item in items:
            expanded.extend(_candidate_with_env_override(group, item))
        candidates[group] = expanded
    return candidates


def get_network_checks():
    checks = []
    for group, items in get_resource_candidates().items():
        for item in items:
            checks.append((group, item["name"], item["url"]))
    return checks


NETWORK_CHECKS = get_network_checks()


def _normalize_windows_arch(arch):
    arch = (arch or "").lower()
    if arch in ("amd64", "x86_64", "x64"):
        return "x64"
    if arch in ("arm64", "aarch64"):
        return "arm64"
    if arch in ("x86", "i386", "i686", "ia32"):
        return "ia32"
    return arch or "unknown"


def detect_windows_arch():
    try:
        system_info = ctypes.create_string_buffer(64)
        ctypes.windll.kernel32.GetNativeSystemInfo(ctypes.byref(system_info))
        native_arch = ctypes.c_ushort.from_buffer(system_info).value
        native_map = {
            0: "ia32",   # PROCESSOR_ARCHITECTURE_INTEL
            9: "x64",    # PROCESSOR_ARCHITECTURE_AMD64
            12: "arm64", # PROCESSOR_ARCHITECTURE_ARM64
        }
        if native_arch in native_map:
            return native_map[native_arch]
    except Exception:
        pass

    return _normalize_windows_arch(
        os.environ.get("PROCESSOR_ARCHITEW6432")
        or os.environ.get("PROCESSOR_ARCHITECTURE")
    )


def is_supported_windows_arch():
    return detect_windows_arch() in SUPPORTED_WINDOWS_ARCHES


def describe_windows_arch(arch=None):
    arch = arch or detect_windows_arch()
    labels = {
        "x64": "64 位 x64",
        "arm64": "ARM64",
        "ia32": "32 位 x86",
        "unknown": "未知架构",
    }
    return labels.get(arch, arch)


def get_vscode_extension_target_platforms():
    return VSCODE_EXTENSION_TARGETS_BY_ARCH.get(detect_windows_arch(), ("win32-x64", ""))


def resolve_vscode_extension_vsix_url(ext_id):
    ext_id = ext_id.lower()
    body = {
        "filters": [{"criteria": [{"filterType": 7, "value": ext_id}]}],
        "flags": 914,
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PythonInstaller/2.0",
        "Accept-Encoding": "identity",
    }
    try:
        req = urllib.request.Request(
            VSCODE_EXTENSION_QUERY_URL,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, context=_get_ssl_context(), timeout=DOWNLOAD_TIMEOUT) as resp:
            data = resp.read()
            if (resp.headers.get("Content-Encoding") or "").lower() == "gzip":
                data = gzip.decompress(data)
        payload = json.loads(data.decode("utf-8", "replace"))
    except Exception:
        return None

    candidates = []
    for result in payload.get("results", []):
        for extension in result.get("extensions", []):
            publisher = extension.get("publisher", {}).get("publisherName", "")
            name = extension.get("extensionName", "")
            if f"{publisher}.{name}".lower() != ext_id:
                continue
            for version in extension.get("versions", []):
                target = (version.get("targetPlatform") or "").lower()
                for file_info in version.get("files", []):
                    if file_info.get("assetType") == "Microsoft.VisualStudio.Services.VSIXPackage":
                        source = file_info.get("source")
                        if source:
                            candidates.append((target, source))
                        break

    for target in get_vscode_extension_target_platforms():
        for candidate_target, source in candidates:
            if candidate_target == target:
                return source
    return None

OLD_ENV_VARS = ["UV_CACHE_DIR", "UV_INDEX_URL", "UV_EXTRA_INDEX_URL"]
CONTEXT_MENU_PATHS = [
    r"Software\Classes\Directory\Background\shell\VSCode",
    r"Software\Classes\Directory\shell\VSCode",
    r"Software\Classes\Drive\shell\VSCode",
]
MANAGED_PATH_SUFFIXES = (
    ("python",),
    ("python", "python"),
    ("python", "python", "Scripts"),
    ("vscode", "bin"),
)
MANAGED_CONFIG_SUFFIXES = MANAGED_PATH_SUFFIXES + (
    ("python", "uv.exe"),
    ("python", "uvx.exe"),
    ("python", "python", "python.exe"),
    ("uv-cache",),
    ("vscode",),
)
MANAGED_DELETE_DIR_NAMES = ("python", "vscode", "uv-cache", ".download-cache")
MANAGED_DELETE_FILE_NAMES = ("安装日志.txt",)
SUBPROCESS_FLAGS = 0x08000000  # CREATE_NO_WINDOW
DOWNLOAD_TIMEOUT = 60
DOWNLOAD_RETRY_COUNT = 4
DOWNLOAD_RETRY_DELAY = 2

INSTALL_GUIDE_TITLE = "一键安装使用前说明"
INSTALL_GUIDE_TEXT = f"""请先阅读并确认以下说明。勾选同意后才会进入安装主界面。

【1. 本工具会做什么】
1. 检测当前 Windows 架构和网络资源可访问性。
2. 下载并部署 uv、Python {PYTHON_VERSION}、VSCode 便携版。
3. 安装 VSCode Python、debugpy 扩展；Pylance 可在 VSCode 扩展面板按需安装。
4. 写入当前用户的 PATH、UV 环境变量、pip 镜像配置和“Open with Code”右键菜单。
5. 生成安装日志；点击“彻底删除”时会清理本工具写入的配置和明确管理的安装目录。

【2. 需要联网访问】
1. uv：{UV_OFFICIAL_URL}
2. Python：通过 uv 获取 Python 运行环境，Python 官网 {PYTHON_OFFICIAL_URL}
3. VSCode：{VSCODE_OFFICIAL_URL}
4. VSCode 扩展市场：Microsoft 扩展市场
5. Python 依赖源：阿里云 PyPI 镜像或 pypi.org

如果网络需要代理、公司白名单或安全网关，请先确认上述资源可访问。

【3. 重要影响】
1. 本工具只面向当前用户写入配置，不主动修改系统级 PATH。
2. 安装过程中不会上传你的代码或个人文件。
3. 下载、扩展安装和依赖同步可能受代理、安全软件、公司网络策略影响。
4. 本工具当前内置 64 位下载策略，仅支持 Windows 64 位 x64。
5. 请不要在项目文件、日志或截图中写入 API Key、密码、Token 等敏感信息。

【4. 法律与安全边界】
1. 本工具仅面向个人学习、课程练习和本机开发环境初始化。
2. Python、uv、VSCode、VSCode 扩展和 PyPI 依赖均属于各自权利人，适用各自许可、隐私和安全条款。
3. 工程“猿”工具网仅提供信息咨询来源和安装流程指引，不提供第三方软件的所有权、授权转让、可用性或法律保证。
4. 本说明不构成法律意见。组织、培训机构、商业分发或批量部署前，请自行复核软件许可、隐私合规和网络安全要求。

如你理解并同意以上内容，请勾选确认后继续。"""


# ==================== 下载工具 ====================


def _get_ssl_context():
    return ssl.create_default_context()


def _content_range_total(value):
    if not value or "/" not in value:
        return 0
    total = value.rsplit("/", 1)[-1].strip()
    if total == "*":
        return 0
    try:
        return int(total)
    except ValueError:
        return 0


def check_network_target(name, url, timeout=8):
    """快速检测地址是否可访问，不下载完整文件。"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PythonInstaller/2.0",
        "Accept-Encoding": "identity",
    }
    ctx = _get_ssl_context()
    last_err = None
    for method in ("HEAD", "GET"):
        req_headers = dict(headers)
        if method == "GET":
            req_headers["Range"] = "bytes=0-0"
        req = urllib.request.Request(url, headers=req_headers, method=method)
        started = time.time()
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
                if method == "GET":
                    resp.read(1)
                elapsed = time.time() - started
                code = getattr(resp, "status", None) or resp.getcode()
                return {
                    "name": name,
                    "url": url,
                    "ok": 200 <= int(code) < 400,
                    "code": code,
                    "elapsed": elapsed,
                    "error": "",
                }
        except Exception as exc:
            last_err = exc
            continue
    return {
        "name": name,
        "url": url,
        "ok": False,
        "code": "",
        "elapsed": 0,
        "error": str(last_err),
    }


def analyze_network_profile(results):
    candidates = get_resource_candidates()
    by_url = {item["url"]: item for item in results}
    selected = {}
    failed_groups = []
    china_score = 0
    international_score = 0
    custom_score = 0

    for group, items in candidates.items():
        available = []
        for item in items:
            result = by_url.get(item["url"], {})
            if not result.get("ok"):
                continue
            merged = dict(item)
            merged["elapsed"] = result.get("elapsed", 99) or 99
            merged["code"] = result.get("code", "")
            available.append(merged)

        if not available:
            failed_groups.append(group)
            continue

        available.sort(key=lambda item: (item["elapsed"], 0 if item["source"] == "official" else 1))
        chosen = available[0]
        selected[group] = chosen
        if chosen["source"] == "china":
            china_score += 2
        elif chosen["source"] == "official":
            international_score += 1
        elif chosen["source"] == "custom":
            custom_score += 1

    pypi_choice = selected.get("pypi", {})
    if pypi_choice.get("source") == "china":
        china_score += 2
    elif pypi_choice.get("source") == "official":
        international_score += 2

    official_binary_ok = all(
        selected.get(group, {}).get("source") in ("official", "custom")
        for group in ("uv", "python", "vscode", "extensions")
    )
    if official_binary_ok:
        international_score += 1

    if failed_groups:
        profile = "网络环境不确定"
        reason = "关键资源存在不可访问项，将按检测到的可用资源和默认资源继续安装。"
    elif china_score >= international_score + 2:
        profile = "中国网络环境"
        reason = "国内依赖源更适合当前网络，按检测结果选择各项下载/依赖资源。"
    elif international_score >= china_score + 2:
        profile = "国际网络环境"
        reason = "官方/国际资源访问表现更好，按检测结果选择各项下载/依赖资源。"
    else:
        profile = "网络环境不确定"
        reason = "中国网络与国际网络评分接近，将按检测到的最快可用资源继续安装。"

    pypi_index_url = selected.get("pypi", {}).get("url", MIRROR_URL)

    return {
        "profile": profile,
        "pypi_index_url": pypi_index_url,
        "reason": reason,
        "china_score": china_score,
        "international_score": international_score,
        "custom_score": custom_score,
        "selected": selected,
        "failed_groups": failed_groups,
        "can_install": True,
    }


def download_file(url, target, progress_fn=None, label=""):
    """下载文件，支持进度回调和断点续传。"""
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    if os.path.isfile(target) and os.path.getsize(target) > 0:
        size = os.path.getsize(target)
        if progress_fn:
            progress_fn(size, size, f"{label}: 使用已下载缓存")
        return target

    part_target = target + ".part"
    resume_from = os.path.getsize(part_target) if os.path.isfile(part_target) else 0
    ctx = _get_ssl_context()
    total = 0
    downloaded = resume_from

    while True:
        retry_full_download = False
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PythonInstaller/2.0",
            "Accept-Encoding": "identity",
        }
        if resume_from > 0:
            headers["Range"] = f"bytes={resume_from}-"
        req = urllib.request.Request(url, headers=headers)

        with urllib.request.urlopen(req, context=ctx, timeout=DOWNLOAD_TIMEOUT) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            if resume_from > 0 and status != 206:
                resume_from = 0
            encoding = (resp.headers.get("Content-Encoding") or "").lower()
            if encoding == "gzip" and resume_from > 0:
                retry_full_download = True
            else:
                content_length = int(resp.headers.get("Content-Length", 0))
                total = _content_range_total(resp.headers.get("Content-Range"))
                if encoding == "gzip":
                    total = content_length
                    downloaded = 0
                    mode = "wb"
                else:
                    if not total and content_length:
                        total = resume_from + content_length if status == 206 else content_length
                    downloaded = resume_from
                    mode = "ab" if resume_from > 0 and status == 206 else "wb"
                if progress_fn and resume_from > 0:
                    progress_fn(downloaded, total, f"{label}: 继续上次下载")
                with open(part_target, mode) as f:
                    if encoding == "gzip":
                        decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
                        while True:
                            raw_chunk = resp.read(65536)
                            if not raw_chunk:
                                break
                            downloaded += len(raw_chunk)
                            chunk = decompressor.decompress(raw_chunk)
                            if chunk:
                                f.write(chunk)
                            if progress_fn:
                                progress_fn(downloaded, total, label)
                        tail = decompressor.flush()
                        if tail:
                            f.write(tail)
                    else:
                        while True:
                            chunk = resp.read(65536)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded += len(chunk)
                            if progress_fn:
                                progress_fn(downloaded, total, label)
        if retry_full_download:
            try:
                os.remove(part_target)
            except OSError:
                pass
            resume_from = 0
            downloaded = 0
            if progress_fn:
                progress_fn(0, -1, f"{label}: gzip 传输不支持断点续传，重新下载")
            continue
        break
    if total and downloaded < total:
        raise RuntimeError(f"{label} 下载不完整: {downloaded}/{total} bytes")
    os.replace(part_target, target)
    return target


def _download_error_text(exc):
    reason = getattr(exc, "reason", None)
    if reason:
        return str(reason)
    return str(exc)


def _is_retryable_download_error(exc):
    text = _download_error_text(exc).lower()
    retry_tokens = (
        "timed out",
        "timeout",
        "10060",
        "10054",
        "10053",
        "connection reset",
        "connection aborted",
        "temporarily unavailable",
        "incomplete",
        "remote end closed",
    )
    if isinstance(exc, (TimeoutError, urllib.error.URLError, ConnectionError)):
        return True
    return any(token in text for token in retry_tokens)


def download_with_fallback(urls, target, progress_fn=None, label="", log_fn=None):
    """尝试多个官方 URL 下载，返回成功的文件路径。"""
    last_err = None
    for url in urls:
        for attempt in range(1, DOWNLOAD_RETRY_COUNT + 1):
            try:
                if attempt > 1:
                    if log_fn:
                        log_fn(f"  -> 下载重试 {attempt}/{DOWNLOAD_RETRY_COUNT}: {label}")
                    if progress_fn:
                        progress_fn(0, -1, f"{label}: 下载重试 {attempt}/{DOWNLOAD_RETRY_COUNT}")
                return download_file(url, target, progress_fn, label)
            except Exception as e:
                last_err = e
                can_retry = _is_retryable_download_error(e) and attempt < DOWNLOAD_RETRY_COUNT
                if log_fn:
                    detail = _download_error_text(e)
                    if can_retry:
                        log_fn(f"  [WARN] {label} 下载中断，将继续重试: {detail}")
                    else:
                        log_fn(f"  [WARN] {label} 下载失败: {detail}")
                if not can_retry:
                    break
                time.sleep(DOWNLOAD_RETRY_DELAY)
        continue
    raise RuntimeError(f"所有下载源均失败: {last_err}")


# ==================== 安装器核心 ====================


class EnvironmentInstaller:

    def __init__(self, install_dir, log_fn=None, progress_fn=None, resource_strategy=None, pypi_index_url=None):
        self.dir = os.path.normpath(install_dir)
        self._log_fn = log_fn or print
        self._progress_fn = progress_fn
        self.resource_strategy = resource_strategy or {}
        selected = self.resource_strategy.get("selected", {})
        self.pypi_index_url = pypi_index_url or selected.get("pypi", {}).get("url") or MIRROR_URL
        self.pypi_host = urllib.parse.urlparse(self.pypi_index_url).hostname or ""
        self.log_lines = []
        self.changes = {
            "path_added": [], "path_removed": [],
            "env_set": {}, "env_removed": [],
            "registry_added": [], "pip_removed": [],
            "files_removed": [], "dirs_removed": [], "remove_failed": [],
        }
        self.extension_status = {
            "required_ok": False,
            "missing": list(REQUIRED_VSCODE_EXTENSIONS),
            "failed": [],
            "warnings": [],
        }

    def _log(self, msg):
        self.log_lines.append(msg)
        self._log_fn(msg)

    def _resource_url(self, group, default_url):
        return self.resource_strategy.get("selected", {}).get(group, {}).get("url") or default_url

    # ---- 路径定义 ----

    @property
    def python_dir(self):
        return os.path.join(self.dir, "python", "python")

    @property
    def python_exe(self):
        return os.path.join(self.python_dir, "python.exe")

    @property
    def uv_exe(self):
        return os.path.join(self.dir, "python", "uv.exe")

    @property
    def vscode_exe(self):
        return os.path.join(self.dir, "vscode", "Code.exe")

    @property
    def vscode_cli(self):
        code_cmd = os.path.join(self.dir, "vscode", "bin", "code.cmd")
        return code_cmd if os.path.isfile(code_cmd) else self.vscode_exe

    @property
    def has_python(self):
        return os.path.isfile(self.python_exe)

    @property
    def has_uv(self):
        return os.path.isfile(self.uv_exe)

    @property
    def has_vscode(self):
        return os.path.isfile(self.vscode_exe)

    # ---- 注册表底层操作 ----

    def _read_user_path(self):
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_READ)
            val, _ = winreg.QueryValueEx(k, "Path")
            winreg.CloseKey(k)
            return val
        except (FileNotFoundError, OSError):
            return ""

    def _read_user_env(self, name):
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_READ)
            val, _ = winreg.QueryValueEx(k, name)
            winreg.CloseKey(k)
            return val
        except (FileNotFoundError, OSError):
            return None

    def _write_user_path(self, val):
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(k, "Path", 0, winreg.REG_EXPAND_SZ, val)
        winreg.CloseKey(k)

    def _set_user_env(self, name, val):
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(k, name, 0, winreg.REG_SZ, val)
        winreg.CloseKey(k)

    def _del_user_env(self, name):
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_SET_VALUE)
            winreg.DeleteValue(k, name)
            winreg.CloseKey(k)
            return True
        except (FileNotFoundError, OSError):
            return False

    def _broadcast(self):
        result = ctypes.c_long()
        ctypes.windll.user32.SendMessageTimeoutW(
            0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, ctypes.byref(result)
        )

    def _progress_percent(self, percent, label):
        if self._progress_fn:
            self._progress_fn(percent, -100, label)

    def _progress_busy(self, label):
        if self._progress_fn:
            self._progress_fn(0, -1, label)

    def _progress_clear(self):
        if self._progress_fn:
            self._progress_fn(0, 0, "")

    def _managed_paths(self, include_config_dirs=False):
        suffixes = MANAGED_CONFIG_SUFFIXES if include_config_dirs else MANAGED_PATH_SUFFIXES
        paths = []
        seen = set()
        for root in self._managed_roots():
            for parts in suffixes:
                path = os.path.normcase(os.path.abspath(os.path.join(root, *parts)))
                if path not in seen:
                    seen.add(path)
                    paths.append(path)
        return paths

    def _is_managed_path(self, entry, include_config_dirs=False):
        try:
            path = os.path.normcase(os.path.abspath(os.path.expandvars(entry)))
            return any(
                path == managed_path or path.startswith(managed_path + os.sep)
                for managed_path in self._managed_paths(include_config_dirs)
            )
        except Exception:
            return False

    def _extract_code_exe_paths(self, value):
        if not value:
            return []
        paths = []
        chunks = value.split('"') if '"' in value else value.split()
        for chunk in chunks:
            text = chunk.strip()
            lower = text.lower()
            marker = "code.exe"
            idx = lower.find(marker)
            if idx < 0:
                continue
            candidate = text[: idx + len(marker)]
            if os.path.isabs(candidate):
                paths.append(candidate)
        return paths

    def _managed_roots(self):
        roots = []
        candidates = [self.dir, INSTALL_DIR_DEFAULT]
        parent = os.path.dirname(os.path.normpath(self.dir))
        if parent and parent != os.path.normpath(self.dir):
            candidates.append(parent)

        for entry in self._read_user_path().split(";"):
            entry = entry.strip()
            if not entry:
                continue
            norm = os.path.normpath(os.path.expandvars(entry))
            parts = norm.split(os.sep)
            for idx in range(len(parts), 0, -1):
                candidate = os.sep.join(parts[:idx])
                if candidate and self._looks_like_managed_root(candidate):
                    candidates.append(candidate)
                    break

        for name in OLD_ENV_VARS:
            value = self._read_user_env(name)
            if not value:
                continue
            norm = os.path.normpath(os.path.expandvars(value))
            parts = norm.split(os.sep)
            for idx in range(len(parts), 0, -1):
                candidate = os.sep.join(parts[:idx])
                if candidate and self._looks_like_managed_root(candidate):
                    candidates.append(candidate)
                    break

        for reg_path in CONTEXT_MENU_PATHS:
            for suffix in ("", r"\command"):
                try:
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path + suffix, 0, winreg.KEY_READ)
                    try:
                        value, _ = winreg.QueryValueEx(key, "")
                    finally:
                        winreg.CloseKey(key)
                except OSError:
                    continue
                for code_exe in self._extract_code_exe_paths(value):
                    candidate = os.path.dirname(os.path.dirname(code_exe))
                    if self._looks_like_managed_root(candidate):
                        candidates.append(candidate)

        for candidate in candidates:
            if not candidate:
                continue
            try:
                normalized = os.path.normcase(os.path.abspath(candidate))
            except Exception:
                continue
            if normalized in roots:
                continue
            if normalized == os.path.normcase(os.path.abspath(self.dir)) or self._looks_like_managed_root(candidate):
                roots.append(normalized)
        return roots

    def _roots_for_paths(self, paths, roots=None):
        roots = roots or self._managed_roots()
        found = []
        seen = set()
        for item in paths:
            try:
                path = os.path.normcase(os.path.abspath(os.path.expandvars(item)))
            except Exception:
                continue
            for root in roots:
                if path == root or path.startswith(root + os.sep):
                    if root not in seen:
                        seen.add(root)
                        found.append(root)
                    break
        return found

    def get_uninstall_summary(self):
        all_roots = self._managed_roots()
        path_items = [p for p in self._read_user_path().split(";") if p.strip() and self._is_managed_path(p.strip())]
        env_items = []
        env_paths = []
        for name in OLD_ENV_VARS:
            value = self._read_user_env(name)
            if not value:
                continue
            if (name == "UV_CACHE_DIR" and self._is_managed_path(value, include_config_dirs=True)) or (
                name in ("UV_INDEX_URL", "UV_EXTRA_INDEX_URL") and value in MANAGED_INDEX_URLS
            ):
                env_items.append(f"{name} = {value}")
                if name == "UV_CACHE_DIR":
                    env_paths.append(value)
        reg_items = []
        reg_paths = []
        for path in CONTEXT_MENU_PATHS:
            if not self._is_managed_registry_entry(path):
                continue
            reg_items.append(path)
            reg_paths.extend(self._extract_code_exe_paths(self._read_registry_default(path)))
            reg_paths.extend(self._extract_code_exe_paths(self._read_registry_default(path + r"\command")))
        pip_ini = os.path.join(os.environ.get("APPDATA", ""), "pip", "pip.ini")
        pip_items = []
        if os.path.isfile(pip_ini):
            try:
                with open(pip_ini, "r", encoding="utf-8-sig", errors="replace") as f:
                    content = f.read()
                if self._is_managed_pip_config(content):
                    pip_items.append(pip_ini)
            except Exception:
                pass
        roots = self._roots_for_paths(path_items + env_paths + reg_paths, all_roots)
        selected_dir = os.path.normcase(os.path.abspath(self.dir))
        if self._looks_like_managed_root(self.dir) and selected_dir not in roots:
            roots.append(selected_dir)
        return {
            "roots": roots,
            "path_items": path_items,
            "env_items": env_items,
            "reg_items": reg_items,
            "pip_items": pip_items,
        }

    def _delete_all_roots(self):
        summary = self.get_uninstall_summary()
        roots = list(summary["roots"])
        selected_dir = os.path.normcase(os.path.abspath(self.dir))
        default_dir = os.path.normcase(os.path.abspath(INSTALL_DIR_DEFAULT))
        if selected_dir not in roots and (selected_dir == default_dir or self._looks_like_managed_root(self.dir)):
            roots.append(selected_dir)
        return roots

    def _is_inside_root(self, root, path):
        try:
            root_abs = os.path.normcase(os.path.abspath(root))
            path_abs = os.path.normcase(os.path.abspath(path))
            return os.path.commonpath([root_abs, path_abs]) == root_abs
        except Exception:
            return False

    def _managed_process_roots(self, roots):
        process_roots = []
        seen = set()
        for root in roots:
            vscode_dir = os.path.join(root, "vscode")
            if not os.path.isdir(vscode_dir):
                continue
            normalized = os.path.normcase(os.path.abspath(vscode_dir))
            if normalized not in seen:
                seen.add(normalized)
                process_roots.append(normalized)
        return process_roots

    def _query_managed_processes(self, roots):
        process_roots = self._managed_process_roots(roots)
        if not process_roots:
            return [], ""
        script = r"""
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$roots = @($env:HY127_PROCESS_ROOTS | ConvertFrom-Json)
$matched = @()
Get-CimInstance Win32_Process | ForEach-Object {
    $path = $_.ExecutablePath
    if ($path) {
        $lower = $path.ToLowerInvariant()
        $hit = $false
        foreach ($root in $roots) {
            $prefix = ([string]$root).TrimEnd('\').ToLowerInvariant() + '\'
            if ($lower.StartsWith($prefix)) {
                $hit = $true
                break
            }
        }
        if ($hit) {
            $matched += [pscustomobject]@{
                pid = [int]$_.ProcessId
                name = [string]$_.Name
                path = [string]$path
            }
        }
    }
}
$matched | ConvertTo-Json -Compress
"""
        env = os.environ.copy()
        env["HY127_PROCESS_ROOTS"] = json.dumps(process_roots, ensure_ascii=False)
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=12,
                env=env,
                creationflags=SUBPROCESS_FLAGS,
            )
        except Exception as exc:
            return [], str(exc)
        if result.returncode != 0:
            return [], (result.stderr or result.stdout or f"PowerShell 退出码 {result.returncode}").strip()
        output = (result.stdout or "").strip()
        if not output:
            return [], ""
        try:
            payload = json.loads(output)
        except Exception as exc:
            return [], f"进程检测结果解析失败: {exc}"
        if isinstance(payload, dict):
            payload = [payload]
        processes = []
        for item in payload or []:
            try:
                processes.append({
                    "pid": int(item.get("pid", 0)),
                    "name": str(item.get("name", "")),
                    "path": str(item.get("path", "")),
                })
            except Exception:
                continue
        return processes, ""

    def _format_process_line(self, item):
        return f"PID {item.get('pid')} {item.get('name')} - {item.get('path')}"

    def _terminate_managed_processes(self, roots):
        processes, error = self._query_managed_processes(roots)
        if error:
            self._log(f"     [WARN] VSCode 占用进程检测失败: {error}")
            return
        if not processes:
            self._log("     [进程检测] 未发现本工具 VSCode 目录下的占用进程")
            return
        self._log("     [进程检测] 发现可能占用 VSCode 目录的进程，将尝试结束:")
        for item in processes:
            self._log(f"        {self._format_process_line(item)}")
        script = r"""
$ErrorActionPreference = 'SilentlyContinue'
$ids = @($env:HY127_PROCESS_IDS | ConvertFrom-Json)
foreach ($id in $ids) {
    Stop-Process -Id ([int]$id) -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Milliseconds 800
"""
        env = os.environ.copy()
        env["HY127_PROCESS_IDS"] = json.dumps([item["pid"] for item in processes])
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=12,
                env=env,
                creationflags=SUBPROCESS_FLAGS,
            )
            if result.returncode != 0:
                details = (result.stderr or result.stdout or f"PowerShell 退出码 {result.returncode}").strip()
                self._log(f"     [WARN] 尝试结束 VSCode 占用进程失败: {details}")
        except Exception as exc:
            self._log(f"     [WARN] 尝试结束 VSCode 占用进程失败: {exc}")
            return
        remaining, error = self._query_managed_processes(roots)
        if error:
            self._log(f"     [WARN] 复查 VSCode 占用进程失败: {error}")
        elif remaining:
            self._log("     [WARN] 仍有 VSCode 相关进程未结束，后续删除可能失败:")
            for item in remaining:
                self._log(f"        {self._format_process_line(item)}")
        else:
            self._log("     [OK] VSCode 占用进程已结束或已自行退出")

    def get_delete_all_summary(self):
        summary = self.get_uninstall_summary()
        roots = self._delete_all_roots()
        delete_dirs = []
        delete_files = []
        for root in roots:
            for name in MANAGED_DELETE_DIR_NAMES:
                path = os.path.join(root, name)
                if os.path.exists(path) and self._is_inside_root(root, path):
                    delete_dirs.append(path)
            for name in MANAGED_DELETE_FILE_NAMES:
                path = os.path.join(root, name)
                if os.path.isfile(path) and self._is_inside_root(root, path):
                    delete_files.append(path)
        summary["roots"] = roots
        summary["delete_dirs"] = delete_dirs
        summary["delete_files"] = delete_files
        processes, process_error = self._query_managed_processes(roots)
        summary["managed_processes"] = [self._format_process_line(item) for item in processes]
        summary["process_check_error"] = process_error
        return summary

    def _registry_path_exists(self, reg_path):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_READ)
            winreg.CloseKey(key)
            return True
        except OSError:
            return False

    def _read_registry_default(self, reg_path):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_READ)
            try:
                value, _ = winreg.QueryValueEx(key, "")
                return value
            finally:
                winreg.CloseKey(key)
        except OSError:
            return ""

    def _is_managed_registry_entry(self, reg_path):
        values = [
            self._read_registry_default(reg_path),
            self._read_registry_default(reg_path + r"\command"),
        ]
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_READ)
            try:
                icon, _ = winreg.QueryValueEx(key, "Icon")
                values.append(icon)
            finally:
                winreg.CloseKey(key)
        except OSError:
            pass
        code_paths = []
        for value in values:
            code_paths.extend(self._extract_code_exe_paths(value))
        return any(self._is_managed_path(code_path, include_config_dirs=True) for code_path in code_paths)

    def _looks_like_managed_root(self, path):
        try:
            uv_path = os.path.join(path, "python", "uv.exe")
            python_path = os.path.join(path, "python", "python", "python.exe")
            vscode_path = os.path.join(path, "vscode", "Code.exe")
            return (
                os.path.isfile(uv_path)
                or os.path.isfile(python_path)
                or os.path.isfile(vscode_path)
            )
        except Exception:
            return False

    def _download_cache_dir(self):
        cache_dir = os.path.join(self.dir, ".download-cache")
        os.makedirs(cache_dir, exist_ok=True)
        return cache_dir

    def _download_cached_zip(self, filename, urls, label):
        cache_path = os.path.join(self._download_cache_dir(), filename)
        if os.path.isfile(cache_path):
            if zipfile.is_zipfile(cache_path):
                self._log(f"  -> 使用已下载缓存: {cache_path}")
                if self._progress_fn:
                    size = os.path.getsize(cache_path)
                    self._progress_fn(size, size, f"{label}: 使用已下载缓存")
                return cache_path
            self._log(f"  -> 发现不完整或损坏缓存，重新下载: {cache_path}")
            try:
                os.remove(cache_path)
            except OSError:
                pass
        part_path = cache_path + ".part"
        if os.path.isfile(part_path) and os.path.getsize(part_path) > 0:
            if zipfile.is_zipfile(part_path):
                os.replace(part_path, cache_path)
                self._log(f"  -> 上次下载已完成，使用缓存: {cache_path}")
                return cache_path
            size = os.path.getsize(part_path) / 1048576
            self._log(f"  -> 发现上次未完成下载，尝试继续: {part_path} ({size:.1f} MB)")
        path = download_with_fallback(urls, cache_path, self._progress_fn, label, self._log)
        if not zipfile.is_zipfile(path):
            try:
                os.remove(path)
            except OSError:
                pass
            raise RuntimeError(f"{label} 下载文件不是有效 zip，已删除缓存，请重试")
        return path

    def _download_cached_vsix(self, ext_id):
        url = resolve_vscode_extension_vsix_url(ext_id)
        if not url:
            self._log(f"  -> 未解析到适合当前平台的 VSIX: {ext_id}")
            return None
        platform_suffix = get_vscode_extension_target_platforms()[0] or "universal"
        filename = ext_id.lower().replace(".", "-") + f"-{platform_suffix}.vsix"
        cache_path = os.path.join(self._download_cache_dir(), filename)
        label = f"VSCode 扩展 {ext_id}"
        if os.path.isfile(cache_path):
            if zipfile.is_zipfile(cache_path):
                self._log(f"  -> 使用已下载扩展缓存: {cache_path}")
                if self._progress_fn:
                    size = os.path.getsize(cache_path)
                    self._progress_fn(size, size, f"{label}: 使用已下载缓存")
                return cache_path
            self._log(f"  -> 发现损坏扩展缓存，重新下载: {cache_path}")
            try:
                os.remove(cache_path)
            except OSError:
                pass
        part_path = cache_path + ".part"
        if os.path.isfile(part_path) and os.path.getsize(part_path) > 0:
            if zipfile.is_zipfile(part_path):
                os.replace(part_path, cache_path)
                self._log(f"  -> 上次扩展下载已完成，使用缓存: {cache_path}")
                return cache_path
            size = os.path.getsize(part_path) / 1048576
            self._log(f"  -> 发现上次未完成扩展下载，尝试继续: {part_path} ({size:.1f} MB)")
        self._log(f"  -> 正在下载 VSIX 扩展包: {ext_id}")
        self._log(f"     {url}")
        path = download_with_fallback([url], cache_path, self._progress_fn, label, self._log)
        if not zipfile.is_zipfile(path):
            try:
                os.remove(path)
            except OSError:
                pass
            raise RuntimeError(f"{label} 下载文件不是有效 VSIX，已删除缓存，请重试")
        return path

    # ---- 步骤1: 下载并部署 uv ----

    def ensure_uv(self):
        if self.has_uv:
            self._log(f"  [OK] uv 已存在: {self.uv_exe}")
            return
        uv_url = self._resource_url("uv", UV_DOWNLOAD_URLS[0])
        self._log(f"  -> 正在从推荐资源下载 uv 包管理器: {uv_url}")
        zip_path = self._download_cached_zip("uv-x86_64-pc-windows-msvc.zip", [uv_url], "uv")

        uv_dir = os.path.join(self.dir, "python")
        os.makedirs(uv_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as z:
            for member in z.namelist():
                basename = os.path.basename(member)
                if basename in ("uv.exe", "uvx.exe"):
                    with z.open(member) as src, open(os.path.join(uv_dir, basename), "wb") as dst:
                        dst.write(src.read())
        self._log(f"  [OK] uv 已安装到: {self.uv_exe}")

    # ---- 步骤2: 使用 uv 安装 Python ----

    def ensure_python(self):
        if self.has_python:
            self._log(f"  [OK] Python 已存在: {self.python_exe}")
            return

        self._log(f"  -> 正在使用 uv 下载 Python {PYTHON_VERSION}，请耐心等待...")
        python_base = os.path.join(self.dir, "python")
        os.makedirs(python_base, exist_ok=True)

        env = os.environ.copy()
        env["UV_PYTHON_INSTALL_DIR"] = python_base
        uv_cache = os.path.join(self.dir, "uv-cache")
        os.makedirs(uv_cache, exist_ok=True)
        env["UV_CACHE_DIR"] = uv_cache
        python_source = self.resource_strategy.get("selected", {}).get("python", {})
        if python_source.get("source") == "custom":
            env["UV_PYTHON_INSTALL_MIRROR"] = python_source["url"]
            self._log(f"  -> 使用推荐 Python 下载资源: {python_source['url']}")
        else:
            self._log(f"  -> 使用推荐 Python 下载资源: {python_source.get('url', PYTHON_BUILD_STANDALONE_URL)}")

        completed = threading.Event()
        result_holder = [None, None]

        def _run():
            try:
                r = subprocess.run(
                    [self.uv_exe, "python", "install", PYTHON_VERSION, "--no-bin"],
                    capture_output=True, text=True, timeout=600,
                    env=env, creationflags=SUBPROCESS_FLAGS,
                )
                result_holder[0] = r
            except Exception as e:
                result_holder[1] = e
            finally:
                completed.set()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        start = time.time()

        while not completed.wait(timeout=0.15):
            elapsed = int(time.time() - start)
            if self._progress_fn:
                self._progress_fn(0, -1, f"Python: downloading... {elapsed}s")

        if self._progress_fn:
            self._progress_fn(0, 0, "")

        if result_holder[1]:
            if isinstance(result_holder[1], subprocess.TimeoutExpired):
                raise RuntimeError("Python download timed out (10 minutes), please check network.")
            raise result_holder[1]

        r = result_holder[0]
        if r.stdout.strip():
            for line in r.stdout.strip().splitlines():
                self._log(f"    {line}")
        if r.stderr.strip():
            for line in r.stderr.strip().splitlines():
                self._log(f"    {line}")
        if r.returncode != 0:
            raise RuntimeError(f"uv python install 失败 (exit {r.returncode})")

        target_dir = os.path.join(python_base, "python")
        if not os.path.isdir(target_dir):
            for name in os.listdir(python_base):
                candidate = os.path.join(python_base, name)
                if name.startswith("cpython-") and os.path.isdir(candidate):
                    if os.path.isfile(os.path.join(candidate, "python.exe")):
                        self._log(f"  -> 重命名 {name} -> python")
                        os.rename(candidate, target_dir)
                        break
                    install_sub = os.path.join(candidate, "install")
                    if os.path.isdir(install_sub) and os.path.isfile(os.path.join(install_sub, "python.exe")):
                        self._log(f"  -> 重命名 {name}/install -> python")
                        os.rename(install_sub, target_dir)
                        shutil.rmtree(candidate, ignore_errors=True)
                        break

        if not os.path.isfile(self.python_exe):
            raise RuntimeError(f"Python 安装后未找到 {self.python_exe}，请手动检查 {python_base}")

        self._log(f"  [OK] Python 已安装到: {self.python_dir}")

    # ---- 步骤3: 下载并部署 VSCode ----

    def ensure_vscode(self):
        if self.has_vscode:
            self._log(f"  [OK] VSCode 已存在: {self.vscode_exe}")
            return

        vscode_url = self._resource_url("vscode", VSCODE_DOWNLOAD_URLS[0])
        self._log(f"  -> 正在从推荐资源下载 VSCode 便携版: {vscode_url}")
        zip_path = self._download_cached_zip("vscode-win32-x64-archive-stable.zip", [vscode_url], "VSCode")

        vscode_dir = os.path.join(self.dir, "vscode")
        os.makedirs(vscode_dir, exist_ok=True)

        self._log("  -> 正在解压 VSCode...")
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(vscode_dir)

        # 创建 data 目录，使 VSCode 进入便携模式。
        data_dir = os.path.join(vscode_dir, "data")
        os.makedirs(data_dir, exist_ok=True)

        if not os.path.isfile(self.vscode_exe):
            raise RuntimeError(f"VSCode 解压后未找到 {self.vscode_exe}")
        self._log(f"  [OK] VSCode 已安装到: {vscode_dir}")

    def _extension_dirs_by_id(self, extensions_dir):
        """Return extension id -> extension directories by reading VSCode package.json."""
        result = {}
        known_ids = REQUIRED_VSCODE_EXTENSIONS + OPTIONAL_VSCODE_EXTENSIONS
        if not os.path.isdir(extensions_dir):
            return result
        for name in os.listdir(extensions_dir):
            full_path = os.path.join(extensions_dir, name)
            if not name or name.startswith(".") or not os.path.isdir(full_path):
                continue
            ext_id = ""
            package_json = os.path.join(full_path, "package.json")
            if os.path.isfile(package_json):
                try:
                    with open(package_json, "r", encoding="utf-8-sig", errors="replace") as f:
                        package = json.load(f)
                    publisher = str(package.get("publisher", "")).strip()
                    ext_name = str(package.get("name", "")).strip()
                    if publisher and ext_name:
                        ext_id = f"{publisher}.{ext_name}".lower()
                except Exception:
                    ext_id = ""
            if not ext_id:
                lower_name = name.lower()
                for known_id in known_ids:
                    if lower_name == known_id.lower() or lower_name.startswith(known_id.lower() + "-"):
                        ext_id = known_id.lower()
                        break
            if ext_id:
                result.setdefault(ext_id, []).append(full_path)
        return result

    def _list_installed_extensions(self, user_data_dir, extensions_dir):
        """Return installed extension ids for portable VSCode (lowercase)."""
        exts = set(self._extension_dirs_by_id(extensions_dir))
        args = [
            self.vscode_cli,
            "--list-extensions",
            "--user-data-dir",
            user_data_dir,
            "--extensions-dir",
            extensions_dir,
        ]
        try:
            process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=SUBPROCESS_FLAGS,
            )
            started = time.time()
            while process.poll() is None:
                elapsed = int(time.time() - started)
                if elapsed > 30:
                    process.kill()
                    process.communicate()
                    raise subprocess.TimeoutExpired(args, 30)
                self._progress_busy(f"VSCode 扩展: 正在检测已安装扩展... {elapsed}s")
                time.sleep(0.2)
            stdout, _ = process.communicate()
            self._progress_clear()
            if process.returncode == 0:
                exts.update(line.strip().lower() for line in stdout.splitlines() if line.strip())
        except Exception:
            self._progress_clear()
            pass
        return exts

    def _import_extensions_from_previous_install(self, extensions_dir, missing):
        current_root = os.path.normcase(os.path.abspath(self.dir))
        copied = []
        for root in self._managed_roots():
            if os.path.normcase(os.path.abspath(root)) == current_root:
                continue
            source_extensions = os.path.join(root, "vscode", "data", "extensions")
            if not os.path.isdir(source_extensions):
                continue
            mapping = self._extension_dirs_by_id(source_extensions)
            reusable = [ext for ext in missing if ext.lower() in mapping]
            if not reusable:
                continue
            self._log(f"  -> 发现旧安装目录中的 VSCode 扩展: {source_extensions}")
            for ext in reusable:
                source_dirs = sorted(mapping[ext.lower()], key=lambda p: os.path.getmtime(p), reverse=True)
                if not source_dirs:
                    continue
                src = source_dirs[0]
                dst = os.path.join(extensions_dir, os.path.basename(src))
                if os.path.exists(dst):
                    copied.append(ext)
                    continue
                try:
                    shutil.copytree(src, dst)
                    self._log(f"  [OK] 已从旧目录复用扩展 {ext}: {os.path.basename(src)}")
                    copied.append(ext)
                except Exception as exc:
                    self._log(f"  [WARN] 复用旧扩展失败 {ext}: {exc}")
        return copied

    def _vscode_cli_details(self, stdout, stderr):
        details = (stderr or stdout or "").strip()
        if len(details) > 1200:
            details = details[:1200] + "\n...输出已截断..."
        return details

    def _install_vscode_extension_target(self, install_target, user_data_dir, extensions_dir, label, timeout):
        args = [
            self.vscode_cli,
            "--install-extension",
            install_target,
            "--force",
            "--user-data-dir",
            user_data_dir,
            "--extensions-dir",
            extensions_dir,
        ]
        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=SUBPROCESS_FLAGS,
        )
        started = time.time()
        try:
            while process.poll() is None:
                elapsed = int(time.time() - started)
                if elapsed > timeout:
                    process.kill()
                    stdout, stderr = process.communicate()
                    raise subprocess.TimeoutExpired(args, timeout, output=stdout, stderr=stderr)
                self._progress_busy(f"{label}: 安装中... {elapsed}s")
                time.sleep(0.2)
            stdout, stderr = process.communicate()
            if process.returncode != 0:
                details = self._vscode_cli_details(stdout, stderr)
                raise RuntimeError(details or "VSCode CLI 返回非 0 状态")
            return stdout, stderr
        finally:
            self._progress_clear()

    def ensure_vscode_extensions(self):
        """Ensure essential Python debug extensions required by F5 are installed."""
        if not self.has_vscode:
            raise RuntimeError("VSCode 未安装，无法安装扩展")

        vscode_dir = os.path.dirname(self.vscode_exe)
        user_data_dir = os.path.join(vscode_dir, "data")
        extensions_dir = os.path.join(user_data_dir, "extensions")
        os.makedirs(user_data_dir, exist_ok=True)
        os.makedirs(extensions_dir, exist_ok=True)

        self._log("  -> 正在检测 VSCode 已安装扩展...")
        installed = self._list_installed_extensions(user_data_dir, extensions_dir)
        missing = [ext for ext in REQUIRED_VSCODE_EXTENSIONS if ext.lower() not in installed]
        if missing:
            copied = self._import_extensions_from_previous_install(extensions_dir, missing)
            if copied:
                installed = self._list_installed_extensions(user_data_dir, extensions_dir)
                missing = [ext for ext in REQUIRED_VSCODE_EXTENSIONS if ext.lower() not in installed]
        if not missing:
            self.extension_status = {"required_ok": True, "missing": [], "failed": [], "warnings": []}
            self._log("  [OK] VSCode Python 调试扩展已就绪")
            return

        extension_source = self.resource_strategy.get("selected", {}).get("extensions", {})
        if extension_source:
            self._log(f"  -> 推荐 VSCode 扩展资源: {extension_source.get('url')}")
            self._log("     将优先下载 VSIX 到本地缓存安装；失败后再尝试 VSCode 扩展市场在线安装。")

        failed = []
        warnings = []
        for ext in missing:
            self._log(f"  -> 正在安装 VSCode 扩展: {ext}")
            installed_ok = False
            vsix_path = None
            try:
                vsix_path = self._download_cached_vsix(ext)
                if vsix_path:
                    self._log(f"  -> 使用本地 VSIX 安装: {vsix_path}")
                    self._install_vscode_extension_target(
                        vsix_path,
                        user_data_dir,
                        extensions_dir,
                        f"VSCode 扩展 {ext} 本地安装",
                        VSCODE_EXTENSION_LOCAL_INSTALL_TIMEOUT,
                    )
                    self._log(f"  [OK] 已通过本地 VSIX 安装 {ext}")
                    installed_ok = True
            except subprocess.TimeoutExpired as exc:
                details = self._vscode_cli_details(getattr(exc, "output", ""), getattr(exc, "stderr", ""))
                warnings.append(f"{ext}: 本地 VSIX 安装超时")
                self._log(f"  [WARN] 本地 VSIX 安装超时，尝试扩展市场在线安装: {ext}")
                if details:
                    self._log(f"         {details}")
            except Exception as exc:
                warnings.append(f"{ext}: 本地 VSIX 下载/安装失败")
                self._log(f"  [WARN] 本地 VSIX 下载/安装失败，尝试扩展市场在线安装: {ext}")
                self._log(f"         {exc}")

            if installed_ok:
                continue

            try:
                self._log(f"  -> 正在通过 VSCode 扩展市场在线安装: {ext}")
                self._install_vscode_extension_target(
                    ext,
                    user_data_dir,
                    extensions_dir,
                    f"VSCode 扩展 {ext} 在线安装",
                    VSCODE_EXTENSION_MARKET_INSTALL_TIMEOUT,
                )
                self._log(f"  [OK] 已安装 {ext}")
            except subprocess.TimeoutExpired as exc:
                details = self._vscode_cli_details(getattr(exc, "output", ""), getattr(exc, "stderr", ""))
                failed.append(f"{ext}: 在线安装超过 {VSCODE_EXTENSION_MARKET_INSTALL_TIMEOUT} 秒")
                self._log(f"  [WARN] 扩展市场在线安装超时，已跳过: {ext}")
                if details:
                    self._log(f"         {details}")
                continue
            except Exception as exc:
                failed.append(f"{ext}: {exc}")
                self._log(f"  [WARN] 扩展安装失败，已跳过: {ext}")
                self._log(f"         {exc}")
                continue

        installed_after = self._list_installed_extensions(user_data_dir, extensions_dir)
        still_missing = [ext for ext in REQUIRED_VSCODE_EXTENSIONS if ext.lower() not in installed_after]
        if still_missing:
            self._log(f"  [WARN] 以下 VSCode 扩展暂未安装成功: {', '.join(still_missing)}")
            self._log("         不影响 Python/uv 环境安装；可稍后在 VSCode 扩展面板搜索安装，或在网络稳定后重试。")
            self._log("         手动命令示例:")
            for ext in still_missing:
                self._log(f"         code --install-extension {ext} --force")
        else:
            self._log(f"  [OK] VSCode 必需扩展最终复核通过: {', '.join(REQUIRED_VSCODE_EXTENSIONS)}")
            if warnings:
                self._log("  [INFO] 本地 VSIX 下载/安装曾出现告警，但已通过扩展市场在线安装完成兜底。")
        self.extension_status = {
            "required_ok": not still_missing,
            "missing": still_missing,
            "failed": failed,
            "warnings": warnings,
        }
        if failed:
            self._log("  [WARN] VSCode 扩展安装存在网络或市场访问问题，安装流程继续。")
        self._log("  [INFO] Pylance 扩展较大且容易受扩展市场网络影响，本工具不再强制安装。")
        self._log("         如需代码智能提示，可稍后在 VSCode 扩展面板搜索 Pylance 安装。")
        self._progress_clear()

    # ---- 步骤4: 清理旧安装 ----

    def clean_old_installation(self):
        managed_roots = self._managed_roots()
        if managed_roots:
            self._log("     [识别安装根目录] " + "; ".join(managed_roots))

        # 清理 PATH
        cur = self._read_user_path()
        entries = [p.strip() for p in cur.split(";") if p.strip()]
        keep, removed = [], []
        for entry in entries:
            if self._is_managed_path(entry):
                removed.append(entry)
                self._log(f"     [删除 PATH] {entry}")
            else:
                keep.append(entry)
        if removed:
            self._write_user_path(";".join(keep))
            self._log(f"  -> 已从用户 PATH 中移除 {len(removed)} 个旧条目")
            self.changes["path_removed"] = removed

        # 清理环境变量
        for name in OLD_ENV_VARS:
            current_value = self._read_user_env(name)
            should_delete = False
            if name == "UV_CACHE_DIR" and current_value:
                should_delete = self._is_managed_path(current_value, include_config_dirs=True)
            elif name in ("UV_INDEX_URL", "UV_EXTRA_INDEX_URL"):
                should_delete = current_value in MANAGED_INDEX_URLS

            if should_delete and self._del_user_env(name):
                self._log(f"     [删除环境变量] {name}")
                self.changes["env_removed"].append(name)

        # 清理注册表
        registry_removed = False
        for reg_path in CONTEXT_MENU_PATHS:
            if not self._is_managed_registry_entry(reg_path):
                continue
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, reg_path + r"\command")
            except OSError:
                pass
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, reg_path)
                registry_removed = True
            except OSError:
                pass
        if registry_removed:
            self._log("  -> 旧右键菜单注册表项已清理")
        else:
            self._log("  -> 未发现本工具写入的右键菜单注册表项")
        self.cleanup_pip_mirror()

    # ---- 步骤5: 配置系统环境 ----

    def setup_path(self):
        new_paths = [
            os.path.join(self.dir, "python"),
            os.path.join(self.dir, "python", "python"),
            os.path.join(self.dir, "python", "python", "Scripts"),
            os.path.join(self.dir, "vscode", "bin"),
        ]
        cur = self._read_user_path()
        entries = [p.strip() for p in cur.split(";") if p.strip()]
        added = []
        for p in new_paths:
            norm = os.path.normpath(p).lower()
            if not any(os.path.normpath(e).lower() == norm for e in entries):
                entries.append(p)
                added.append(p)
                self._log(f"     [新增 PATH] {p}")
        if added:
            self._write_user_path(";".join(entries))
            self.changes["path_added"] = added

    def setup_env_vars(self):
        uv_cache = os.path.join(self.dir, "uv-cache")
        os.makedirs(uv_cache, exist_ok=True)
        env_map = {
            "UV_CACHE_DIR": uv_cache,
            "UV_INDEX_URL": self.pypi_index_url,
            "UV_EXTRA_INDEX_URL": self.pypi_index_url,
        }
        for name, val in env_map.items():
            self._set_user_env(name, val)
            self._log(f"     [环境变量] {name} = {val}")
            self.changes["env_set"][name] = val

    def _is_managed_pip_config(self, content):
        if PIP_CONFIG_MARKER in content:
            return True
        if any(marker in content for marker in LEGACY_PIP_CONFIG_MARKERS):
            return True
        lines = []
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if line and not line.startswith("#"):
                lines.append(line)
        if not lines or lines[0].lower() != "[global]":
            return False
        has_managed_index = False
        for line in lines[1:]:
            key, sep, value = line.partition("=")
            if not sep:
                return False
            key = key.strip().lower()
            value = value.strip()
            if key == "index-url" and value in MANAGED_INDEX_URLS:
                has_managed_index = True
                continue
            if key == "trusted-host" and value == MIRROR_HOST:
                continue
            return False
        return has_managed_index

    def setup_pip_mirror(self):
        appdata = os.environ.get("APPDATA", "")
        if not appdata:
            return
        pip_dir = os.path.join(appdata, "pip")
        os.makedirs(pip_dir, exist_ok=True)
        pip_ini = os.path.join(pip_dir, "pip.ini")
        with open(pip_ini, "w", encoding="utf-8") as f:
            f.write(f"{PIP_CONFIG_MARKER}\n[global]\nindex-url = {self.pypi_index_url}\n")
            if self.pypi_host and self.pypi_host != PYPI_OFFICIAL_HOST:
                f.write(f"trusted-host = {self.pypi_host}\n")
        self._log(f"     [写入文件] {pip_ini}")
        self._log(f"     [配置内容] index-url = {self.pypi_index_url}")

    def cleanup_pip_mirror(self):
        appdata = os.environ.get("APPDATA", "")
        if not appdata:
            return
        pip_ini = os.path.join(appdata, "pip", "pip.ini")
        if not os.path.isfile(pip_ini):
            return
        try:
            with open(pip_ini, "r", encoding="utf-8-sig", errors="replace") as f:
                content = f.read()
            if not self._is_managed_pip_config(content):
                return
            os.remove(pip_ini)
            self.changes["pip_removed"].append(pip_ini)
            self._log(f"     [删除 pip 镜像配置] {pip_ini}")
        except Exception as exc:
            self._log(f"     [WARN] pip 镜像配置清理失败: {pip_ini} - {exc}")

    def setup_context_menu(self):
        if not self.has_vscode:
            self._log("  -> VSCode 未安装，跳过右键菜单配置")
            return
        for reg_path in CONTEXT_MENU_PATHS:
            k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, reg_path)
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "Open with Code")
            winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, self.vscode_exe)
            winreg.CloseKey(k)
            cmd_key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, reg_path + r"\command")
            winreg.SetValueEx(cmd_key, "", 0, winreg.REG_SZ, f'"{self.vscode_exe}" "%V"')
            winreg.CloseKey(cmd_key)
            self._log(f"     [注册表] HKCU\\{reg_path}")
            self.changes["registry_added"].append(reg_path)

    # ---- Web 工作台部署 ----

    def _web_source_candidates(self):
        here = os.path.abspath(os.path.dirname(__file__))
        candidates = [
            os.path.join(os.path.dirname(here), "code880web"),
            os.path.join(os.path.dirname(sys.executable), "code880web"),
        ]
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            candidates.insert(0, os.path.join(meipass, "code880web"))
        return candidates

    def _find_web_source_dir(self):
        for candidate in self._web_source_candidates():
            app_py = os.path.join(candidate, "hub", "app.py")
            worker_py = os.path.join(candidate, "worker", "app.py")
            if os.path.isfile(app_py) and os.path.isfile(worker_py):
                return os.path.normpath(candidate)
        return ""

    @staticmethod
    def _ignore_web_copy(_dir, names):
        ignored = {"__pycache__", ".pytest_cache", ".test-tmp"}
        return [name for name in names if name in ignored or name.endswith(".pyc")]

    def _deploy_web_workbench(self):
        source_dir = self._find_web_source_dir()
        if not source_dir:
            raise RuntimeError("未找到 code880web 源目录，请确认安装包包含 Web 工作台组件")

        target_dir = os.path.join(self.dir, "code880web")
        if os.path.normcase(os.path.abspath(source_dir)) == os.path.normcase(os.path.abspath(target_dir)):
            self._log(f"  [OK] Web 工作台已在安装目录: {target_dir}")
            return target_dir

        self._log(f"  -> 正在部署 Web 工作台: {target_dir}")
        os.makedirs(os.path.dirname(target_dir), exist_ok=True)
        shutil.copytree(
            source_dir,
            target_dir,
            dirs_exist_ok=True,
            ignore=self._ignore_web_copy,
        )
        self._log("  [OK] Web 工作台组件已部署")
        return target_dir

    def _install_web_requirements(self, web_dir):
        requirements = os.path.join(web_dir, "requirements.txt")
        if not os.path.isfile(requirements):
            raise RuntimeError(f"Web 依赖清单不存在: {requirements}")

        self._log("  -> 正在安装 Web 工作台依赖...")
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        cmd = [
            self.python_exe, "-m", "pip", "install",
            "-r", requirements,
            "--index-url", self.pypi_index_url,
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=600,
            creationflags=SUBPROCESS_FLAGS,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        output = self._subprocess_output(result)
        if output:
            for line in output.splitlines()[-30:]:
                self._log(f"    {line}")
        if result.returncode != 0:
            raise RuntimeError(f"Web 依赖安装失败 (exit {result.returncode})")
        self._log("  [OK] Web 工作台依赖已安装")

    # ---- 步骤6: 测试 ----

    def _subprocess_output(self, result):
        text = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part and part.strip())
        return text.strip()

    def _log_command_result(self, name, result):
        output = self._subprocess_output(result)
        if result.returncode == 0 and output:
            self._log(f"  [OK] {output}")
            return True
        if result.returncode == 0:
            self._log(f"  [WARN] {name} 命令返回成功，但未输出版本信息")
            return True
        self._log(f"  [FAIL] {name} 退出码 {result.returncode}: {output or '无输出'}")
        return False

    def test_installation(self):
        ok = True
        test_env = os.environ.copy()
        test_env["PYTHONIOENCODING"] = "utf-8"
        kw = {"capture_output": True, "timeout": 15, "creationflags": SUBPROCESS_FLAGS,
              "encoding": "utf-8", "errors": "replace", "env": test_env}
        self._log("\n[1/3] 正在检查 Python...")
        try:
            r = subprocess.run([self.python_exe, "--version"], **kw)
            ok = self._log_command_result("Python", r) and ok
            r2 = subprocess.run([self.python_exe, "-c", "print('>>> Python 运行环境正常!')"], **kw)
            ok = self._log_command_result("Python 运行环境", r2) and ok
        except Exception as e:
            ok = False
            self._log(f"  [FAIL] Python: {e}")

        self._log("[2/3] 正在检查 Pip...")
        try:
            r = subprocess.run([self.python_exe, "-m", "pip", "--version"], **kw)
            ok = self._log_command_result("Pip", r) and ok
        except Exception as e:
            ok = False
            self._log(f"  [FAIL] Pip: {e}")

        self._log("[3/3] 正在检查 uv...")
        try:
            r = subprocess.run([self.uv_exe, "--version"], **kw)
            ok = self._log_command_result("uv", r) and ok
        except Exception as e:
            ok = False
            self._log(f"  [FAIL] uv: {e}")
        return ok

    def _expected_path_entries(self):
        return [
            os.path.join(self.dir, "python"),
            os.path.join(self.dir, "python", "python"),
            os.path.join(self.dir, "python", "python", "Scripts"),
            os.path.join(self.dir, "vscode", "bin"),
        ]

    def _path_config_status(self):
        entries = [p.strip() for p in self._read_user_path().split(";") if p.strip()]
        normalized = {os.path.normcase(os.path.normpath(p)) for p in entries}
        missing = [
            p for p in self._expected_path_entries()
            if os.path.normcase(os.path.normpath(p)) not in normalized
        ]
        return not missing, missing

    def _env_config_status(self):
        expected = {
            "UV_CACHE_DIR": os.path.join(self.dir, "uv-cache"),
            "UV_INDEX_URL": self.pypi_index_url,
            "UV_EXTRA_INDEX_URL": self.pypi_index_url,
        }
        missing = []
        for name, value in expected.items():
            if self._read_user_env(name) != value:
                missing.append(name)
        return not missing, missing

    def _pip_config_status(self):
        appdata = os.environ.get("APPDATA", "")
        if not appdata:
            return False, "APPDATA 未设置，无法确认 pip.ini"
        pip_ini = os.path.join(appdata, "pip", "pip.ini")
        if not os.path.isfile(pip_ini):
            return False, f"未找到 {pip_ini}"
        try:
            with open(pip_ini, "r", encoding="utf-8-sig", errors="replace") as f:
                content = f.read()
        except Exception as exc:
            return False, f"读取失败: {exc}"
        if PIP_CONFIG_MARKER not in content or f"index-url = {self.pypi_index_url}" not in content:
            return False, f"{pip_ini} 内容不是本次推荐源"
        return True, pip_ini

    def _context_menu_status(self):
        missing = [path for path in CONTEXT_MENU_PATHS if not self._is_managed_registry_entry(path)]
        return not missing, missing

    def log_install_summary(self, tests_ok):
        statuses = []

        def add(status, item, detail):
            statuses.append(status)
            self._log(f"  [{status}] {item}: {detail}")

        self._log("")
        self._log("=======================================================")
        self._log("    安装关键事项结果总结")
        self._log("=======================================================")

        arch = detect_windows_arch()
        if is_supported_windows_arch():
            add("PASS", "系统架构", f"Windows {describe_windows_arch(arch)}")
        else:
            add("FAIL", "系统架构", f"当前为 {describe_windows_arch(arch)}，本工具仅支持 Windows 64 位 x64")

        profile = self.resource_strategy.get("profile", "未检测")
        failed_groups = self.resource_strategy.get("failed_groups", [])
        selected_count = len(self.resource_strategy.get("selected", {}))
        if failed_groups:
            labels = ", ".join(RESOURCE_LABELS.get(group, group) for group in failed_groups)
            add("WARN", "网络检测", f"{profile}，以下资源组存在不可访问项: {labels}")
        elif self.resource_strategy:
            if profile == "网络环境不确定":
                add("WARN", "网络检测", f"{profile}，已选择 {selected_count} 项推荐资源并继续安装")
            else:
                add("PASS", "网络检测", f"{profile}，已选择 {selected_count} 项推荐资源")
        else:
            add("WARN", "网络检测", "未取得网络检测结果，按默认资源策略继续")

        add("PASS" if self.has_uv else "FAIL", "uv 包管理器", self.uv_exe if self.has_uv else "未找到 uv.exe")
        add("PASS" if self.has_python else "FAIL", "Python 运行时", self.python_exe if self.has_python else "未找到 python.exe")
        add("PASS" if self.has_vscode else "FAIL", "VSCode 便携版", self.vscode_exe if self.has_vscode else "未找到 Code.exe")

        ext_status = self.extension_status
        if ext_status.get("required_ok"):
            detail = "必需扩展已就绪: " + ", ".join(REQUIRED_VSCODE_EXTENSIONS)
            if ext_status.get("warnings"):
                detail += "；本地 VSIX 通道出现告警，已由在线安装兜底并最终复核通过"
            add("PASS", "VSCode Python 调试扩展", detail)
        else:
            missing = ext_status.get("missing") or REQUIRED_VSCODE_EXTENSIONS
            add("WARN", "VSCode Python 调试扩展", "未全部就绪: " + ", ".join(missing))

        path_ok, missing_paths = self._path_config_status()
        if path_ok:
            add("PASS", "PATH 配置", "Python / Scripts / uv / VSCode CLI 路径已写入用户 PATH")
        else:
            add("FAIL", "PATH 配置", "缺少: " + "; ".join(missing_paths))

        env_ok, missing_env = self._env_config_status()
        if env_ok:
            add("PASS", "UV 环境变量", f"UV_CACHE_DIR / UV_INDEX_URL / UV_EXTRA_INDEX_URL 已配置为 {self.pypi_index_url}")
        else:
            add("FAIL", "UV 环境变量", "缺少或值不匹配: " + ", ".join(missing_env))

        pip_ok, pip_detail = self._pip_config_status()
        add("PASS" if pip_ok else "WARN", "pip 镜像配置", pip_detail if pip_ok else pip_detail)

        menu_ok, missing_menu = self._context_menu_status()
        if menu_ok:
            add("PASS", "右键菜单", "Open with Code 已写入当前用户注册表")
        else:
            add("WARN", "右键菜单", "未全部写入: " + "; ".join(missing_menu))

        add("PASS" if tests_ok else "FAIL", "最终环境测试", "Python / pip / uv 全部通过" if tests_ok else "存在 [FAIL] 项，请查看上方测试日志")

        self._log("-------------------------------------------------------")
        if "FAIL" in statuses:
            self._log("  [FAIL] 整体结论: 安装未完全通过，请优先处理上方 FAIL 项。")
        elif "WARN" in statuses:
            self._log("  [WARN] 整体结论: 基础环境已通过，但存在不阻断安装的提醒项。")
        else:
            self._log("  [PASS] 整体结论: 一键安装关键事项全部通过。")
        self._log("=======================================================")

    # ---- 日志输出 ----

    def write_log_file(self):
        log_file = os.path.join(self.dir, "安装日志.txt")
        now = datetime.datetime.now()
        txt = f"""=======================================================
    Deploying Portable Python & VS Code Environment
      工程"猿"工具网 Python 办公自动化 学员专用 hy127.cn {now.year}
=======================================================

Environment location: {self.dir}
Install time: {now.strftime('%Y-%m-%d %H:%M:%S')}

""" + "\n".join(self.log_lines) + f"""

=======================================================
      安装完成!
=======================================================

>>> 本次安装修改内容汇总

  [用户 PATH 环境变量] 新增以下路径:
"""
        for i, p in enumerate(self.changes["path_added"], 1):
            txt += f"    {i}. {p}\n"
        txt += "\n  [用户环境变量] 新增/修改:\n"
        for n, v in self.changes["env_set"].items():
            txt += f"    {n} = {v}\n"
        txt += "\n  [注册表] 添加右键菜单 'Open with Code':\n"
        for rp in self.changes["registry_added"]:
            txt += f"    HKCU\\{rp}\n"
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            txt += "\n  [配置文件] pip 镜像源\n"
            txt += f"    {os.path.join(appdata, 'pip', 'pip.ini')}\n"
            txt += f"    索引源: {self.pypi_index_url}\n"
        txt += f"""
you can use 'python', 'pip', 'uv' in any command prompt.
提示: 请新开命令行窗口，使环境变量生效。
"""
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(txt)
        self._log(f"\n日志已保存: {log_file}")

    # ---- 主安装流程 ----

    def install(self):
        self._log("=======================================================")
        self._log("    Deploying Portable Python & VS Code Environment")
        self._log('      工程"猿"工具网 Python 办公自动化 学员专用 hy127.cn')
        self._log("=======================================================")
        self._log(f"\n安装目录: {self.dir}\n")
        self._log(f"下载缓存: {self._download_cache_dir()}")
        self._log("提示: 下载中断后保留 .part 缓存，再次点击一键安装会尝试继续下载。\n")

        # 创建安装目录
        os.makedirs(self.dir, exist_ok=True)

        # 1. 安装前先清理旧配置，避免旧 PATH/环境变量影响后续命令识别。
        self._log("[1/8] 清理旧安装配置...")
        self._progress_busy("[1/8] 正在清理旧配置...")
        self.clean_old_installation()
        self._progress_percent(8, "[1/8] 旧配置清理完成")
        self._log("")

        # 2. 下载并部署工具
        self._log("[2/8] 部署 uv 包管理器...")
        self._progress_percent(10, "[2/8] 正在准备 uv 包管理器...")
        self.ensure_uv()
        self._progress_percent(16, "[2/8] uv 包管理器完成")
        self._log("")

        self._log("[3/8] 部署 Python...")
        self._progress_percent(18, "[3/8] 正在准备 Python...")
        self.ensure_python()
        self._progress_percent(30, "[3/8] Python 完成")
        self._log("")

        self._log("[4/8] 部署 VSCode 编辑器...")
        self._progress_percent(34, "[4/8] 正在准备 VSCode...")
        self.ensure_vscode()
        self._progress_percent(50, "[4/8] VSCode 完成")
        self._log("")

        self._log("[5/8] 安装 VSCode Python 调试扩展...")
        self._progress_busy("[5/8] 正在准备 VSCode 扩展...")
        self.ensure_vscode_extensions()
        self._progress_percent(65, "[5/8] VSCode 扩展处理完成")
        self._log("")

        # 3. 配置系统环境
        self._log("[6/8] 配置 PATH 和环境变量...")
        self._progress_busy("[6/8] 正在配置 PATH / 环境变量 / pip 镜像...")
        self.setup_path()
        self.setup_env_vars()
        self.setup_pip_mirror()
        self._progress_percent(78, "[6/8] 系统环境配置完成")
        self._log("")

        self._log("[7/9] 配置右键菜单 'Open with Code'...")
        self._progress_busy("[7/9] 正在配置右键菜单...")
        self.setup_context_menu()
        self._progress_percent(84, "[7/9] 右键菜单配置完成")
        self._log("")

        self._log("[8/9] 部署 Web 工作台...")
        self._progress_busy("[8/9] 正在部署 Web 工作台组件和依赖...")
        web_dir = self._deploy_web_workbench()
        self._install_web_requirements(web_dir)
        self._progress_percent(92, "[8/9] Web 工作台部署完成")
        self._log("")

        self._broadcast()

        # 4. 测试
        self._log("[9/9] 测试环境...")
        self._progress_busy("[9/9] 正在测试 Python / pip / uv...")
        self._log("=======================================================")
        tests_ok = self.test_installation()
        self._log("=======================================================")

        self.log_install_summary(tests_ok)
        self.write_log_file()
        if not tests_ok:
            raise RuntimeError("环境测试未全部通过，请查看上方 [FAIL] 项和安装日志。")
        self._progress_percent(100, "[9/9] 安装完成")

        # ── Web 工作台安装信息写入 ──
        self._write_web_install_info()

        self._log("")
        self._log("=======================================================")
        self._log("  [OK] Install completed! Open a new terminal for updated env vars.")
        self._log("=======================================================")
        self._log("")
        self._log("下一步:")
        self._log("  1. 解压项目模板 (code880_temp_xxx.zip)")
        self._log("  2. 运行 '重新初始化 V1.24.bat'")
        self._log("  3. 右键项目文件夹 -> Open with Code")
        self._log("  4. 双击 '启动Web工作台.bat' 打开 Web 工作台!")
        return True

    def _write_web_install_info(self):
        """写入 Web 工作台安装信息到 %LOCALAPPDATA%\\Code880Web\\install.json"""
        try:
            import json as _json
            from datetime import datetime as _dt

            global_dir = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Code880Web")
            os.makedirs(global_dir, exist_ok=True)

            code880web_dir = os.path.join(self.dir, "code880web")
            info = {
                "install_root": self.dir,
                "python_path": self.python_exe,
                "hub_app_path": os.path.join(code880web_dir, "hub", "app.py"),
                "worker_app_path": os.path.join(code880web_dir, "worker", "app.py"),
                "static_path": os.path.join(code880web_dir, "static"),
                "installed_at": _dt.now().isoformat(),
                "version": "5.11",
            }

            install_json_path = os.path.join(global_dir, "install.json")
            with open(install_json_path, "w", encoding="utf-8") as f:
                _json.dump(info, f, ensure_ascii=False, indent=2)

            self._log(f"  [OK] Web 工作台安装信息已写入: {install_json_path}")
        except Exception as e:
            self._log(f"  [WARN] Web 安装信息写入失败 (不影响桌面版使用): {e}")

    def uninstall(self):
        self._log("=======================================================")
        self._log("    开始卸载环境配置...")
        self._log("=======================================================")
        self._log(f"\n目标目录: {self.dir}\n")
        self._log("[+] 清理 PATH / 环境变量 / 右键菜单...")
        self.clean_old_installation()
        self._broadcast()
        self._log("")
        self._log("  [OK] 卸载完成! 文件未删除，如需删除请手动处理安装目录。")
        return True

    def _remove_readonly(self, func, path, _exc_info):
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception:
            raise

    def _remove_file(self, root, path):
        if not self._is_inside_root(root, path) or not os.path.isfile(path):
            return
        try:
            os.remove(path)
            self.changes["files_removed"].append(path)
            self._log(f"     [删除文件] {path}")
        except Exception as exc:
            self.changes["remove_failed"].append(f"{path} - {exc}")
            self._log(f"     [WARN] 删除文件失败: {path} - {exc}")

    def _remove_dir(self, root, path):
        if not self._is_inside_root(root, path) or not os.path.exists(path):
            return
        try:
            if os.path.islink(path):
                os.unlink(path)
            else:
                shutil.rmtree(path, onerror=self._remove_readonly)
            self.changes["dirs_removed"].append(path)
            self._log(f"     [删除目录] {path}")
        except Exception as exc:
            self.changes["remove_failed"].append(f"{path} - {exc}")
            self._log(f"     [WARN] 删除目录失败: {path} - {exc}")

    def _remove_empty_root(self, root):
        try:
            if os.path.isdir(root) and not any(os.scandir(root)):
                os.rmdir(root)
                self.changes["dirs_removed"].append(root)
                self._log(f"     [删除空根目录] {root}")
        except Exception as exc:
            self.changes["remove_failed"].append(f"{root} - {exc}")
            self._log(f"     [WARN] 删除空根目录失败: {root} - {exc}")

    def delete_all(self, summary=None):
        summary = summary or self.get_delete_all_summary()
        self._log("=======================================================")
        self._log("    开始彻底删除本工具环境...")
        self._log("=======================================================")
        roots = summary.get("roots", [])
        if roots:
            self._log("     [识别安装根目录] " + "; ".join(roots))
        else:
            self._log("     [识别安装根目录] 未识别到可删除的安装根目录")
        self._log("")
        self._log("[1/3] 清理 PATH / 环境变量 / pip / 右键菜单...")
        self.clean_old_installation()
        self._broadcast()
        self._log("")
        self._log("[2/3] 检测并结束 VSCode 占用进程...")
        self._terminate_managed_processes(roots)
        self._log("")
        self._log("[3/3] 删除安装器管理的文件目录...")
        for path in summary.get("delete_files", []):
            for root in roots:
                if self._is_inside_root(root, path):
                    self._remove_file(root, path)
                    break
        for path in sorted(summary.get("delete_dirs", []), key=len, reverse=True):
            for root in roots:
                if self._is_inside_root(root, path):
                    self._remove_dir(root, path)
                    break
        for root in roots:
            self._remove_empty_root(root)
        if not summary.get("delete_files") and not summary.get("delete_dirs"):
            self._log("  -> 未发现可删除的安装器管理目录或文件")
        self._log("")
        if self.changes["remove_failed"]:
            self._log("  [WARN] 彻底删除部分文件未删除成功，请关闭 VSCode、Python、终端后重试或手动删除。")
        else:
            self._log("  [OK] 彻底删除完成。")
        return not self.changes["remove_failed"]


# ==================== GUI 界面 ====================


class InstallerApp:

    def __init__(self):
        self._main_thread = threading.current_thread()
        self._ui_queue = queue.Queue()
        self._worker_thread = None
        self._install_active = False
        self._active_log_key = "install"
        self._task_log_key = None
        self._log_widgets = {}
        self._log_tab_indexes = {}
        self._network_strategy = {
            "profile": "未检测",
            "pypi_index_url": MIRROR_URL,
            "reason": "一键安装时会自动检测网络，默认使用阿里云 PyPI 索引。",
            "china_score": 0,
            "international_score": 0,
            "custom_score": 0,
            "selected": {},
            "failed_groups": [],
            "can_install": True,
        }
        self.root = tk.Tk()
        self.root.title("一键安装向导 - 使用前确认")
        self.root.geometry("920x720")
        self.root.minsize(820, 640)
        self.root.after(100, self._process_ui_queue)
        self._build_wizard_ui()

    def _clear_root(self):
        for child in self.root.winfo_children():
            child.destroy()

    def _build_wizard_ui(self):
        self._clear_root()
        self.root.title("一键安装向导 - 使用前确认")

        agree_var = tk.BooleanVar(value=False)

        main = ttk.Frame(self.root, padding=(16, 14, 16, 16))
        main.pack(fill=tk.BOTH, expand=True)

        lbl_title = ttk.Label(
            main,
            text=INSTALL_GUIDE_TITLE,
            font=("Microsoft YaHei UI", 16, "bold"),
        )
        lbl_title.pack(anchor=tk.W, pady=(0, 8))

        text = scrolledtext.ScrolledText(main, wrap=tk.WORD, font=("Microsoft YaHei UI", 10), height=24)
        text.pack(fill=tk.BOTH, expand=True)
        text.insert("1.0", INSTALL_GUIDE_TEXT)
        text.configure(state="disabled")

        chk_agree = ttk.Checkbutton(
            main,
            text="我已阅读并同意上述安装影响、安全提醒和法律许可说明",
            variable=agree_var,
        )
        chk_agree.pack(anchor=tk.W, pady=(10, 8))

        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X)

        btn_accept = ttk.Button(btn_frame, text="同意并进入安装")
        btn_cancel = ttk.Button(btn_frame, text="不同意并退出", command=self.root.destroy)

        def accept():
            if not agree_var.get():
                messagebox.showwarning("请先确认", "继续前需要勾选同意说明。", parent=self.root)
                return
            self._clear_root()
            self.root.title("Python 开发环境一键安装 v2.0 - hy127.cn")
            self._build_ui()

        btn_accept.configure(command=accept)

        btn_accept.pack(side=tk.RIGHT, padx=(8, 0))
        btn_cancel.pack(side=tk.RIGHT)

        self.root.update_idletasks()
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _build_ui(self):
        style = ttk.Style()
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass

        main = ttk.Frame(self.root, padding=(16, 14, 16, 16))
        main.pack(fill=tk.BOTH, expand=True)

        # 标题
        ttk.Label(main, text='工程"猿"工具网 Python 办公自动化 学员专用',
                  font=("Microsoft YaHei UI", 15, "bold")).pack(pady=(0, 2))
        ttk.Label(main, text="便携式 Python + VSCode 开发环境一键安装工具  hy127.cn",
                  font=("Microsoft YaHei UI", 9)).pack(pady=(0, 12))

        # 安装目录
        dir_frame = ttk.Frame(main)
        dir_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(dir_frame, text="安装到:").pack(side=tk.LEFT)
        self.dir_var = tk.StringVar(value=INSTALL_DIR_DEFAULT)
        self.dir_entry = ttk.Entry(dir_frame, textvariable=self.dir_var, font=("Consolas", 10))
        self.dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 6))
        self.btn_browse = ttk.Button(dir_frame, text="浏览...", command=self._browse_dir, width=8)
        self.btn_browse.pack(side=tk.LEFT)

        # 进度条
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_label = ttk.Label(main, text="", font=("Consolas", 8))
        self.progress_label.pack(fill=tk.X)
        self.progress_bar = ttk.Progressbar(main, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=(0, 6))

        # 日志区域
        log_frame = ttk.LabelFrame(main, text="安装日志", padding=4)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 14))

        self.log_notebook = ttk.Notebook(log_frame)
        self.log_notebook.pack(fill=tk.BOTH, expand=True)
        self.log_notebook.enable_traversal()
        for key, title in (
            ("install", "一键安装"),
            ("delete_all", "彻底删除"),
        ):
            tab = ttk.Frame(self.log_notebook)
            text = scrolledtext.ScrolledText(
                tab, wrap=tk.WORD, font=("Consolas", 9),
                bg="#0d1117", fg="#58a6ff", insertbackground="#58a6ff",
                selectbackground="#1f6feb", relief=tk.FLAT, borderwidth=0,
            )
            text.pack(fill=tk.BOTH, expand=True)
            self._log_widgets[key] = text
            self._log_tab_indexes[key] = len(self._log_tab_indexes)
            self.log_notebook.add(tab, text=title)
        self.log_text = self._log_widgets[self._active_log_key]
        self.log_notebook.bind("<<NotebookTabChanged>>", self._on_log_tab_changed)

        log_tools = ttk.Frame(log_frame)
        log_tools.place(relx=1.0, y=0, anchor=tk.NE)
        ttk.Button(log_tools, text="复制日志", command=self._copy_log, width=10).pack(side=tk.RIGHT)

        # 按钮
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=(0, 2))
        self.btn_install = ttk.Button(btn_frame, text="一键安装", command=self._do_install)
        self.btn_install.pack(side=tk.LEFT, padx=(0, 4), fill=tk.X, expand=True)
        self.btn_delete_all = ttk.Button(btn_frame, text="彻底删除", command=self._do_delete_all)
        self.btn_delete_all.pack(side=tk.LEFT, padx=(0, 4), fill=tk.X, expand=True)
        ttk.Button(btn_frame, text="退出", command=self.root.destroy).pack(
            side=tk.LEFT, fill=tk.X, expand=True)

    def _browse_dir(self):
        d = filedialog.askdirectory(initialdir=self.dir_var.get(), title="选择安装目录")
        if d:
            self.dir_var.set(os.path.normpath(d))

    def _on_log_tab_changed(self, _event=None):
        if not hasattr(self, "log_notebook"):
            return
        selected = self.log_notebook.index(self.log_notebook.select())
        for key, index in self._log_tab_indexes.items():
            if index == selected:
                self._active_log_key = key
                self.log_text = self._log_widgets[key]
                break

    def _set_log_context(self, key, clear=False):
        self._active_log_key = key
        if hasattr(self, "log_notebook") and key in self._log_tab_indexes:
            self.log_notebook.select(self._log_tab_indexes[key])
        if key in self._log_widgets:
            self.log_text = self._log_widgets[key]
            if clear:
                self.log_text.delete("1.0", tk.END)

    def _log(self, msg):
        key = self._task_log_key or self._active_log_key
        if threading.current_thread() is not self._main_thread:
            self._ui_queue.put(("log", key, msg))
            return
        self._log_direct(msg, key)

    def _log_direct(self, msg, key=None):
        key = key or self._active_log_key
        text_widget = self._log_widgets.get(key, self.log_text)
        text_widget.insert(tk.END, msg + "\n")
        text_widget.see(tk.END)
        self.root.update()

    def _copy_log(self):
        text_widget = self._log_widgets.get(self._active_log_key, self.log_text)
        content = text_widget.get("1.0", tk.END).strip()
        if not content:
            messagebox.showinfo("复制日志", "当前日志为空。", parent=self.root)
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        self.root.update()
        self.progress_label.config(text="  安装日志已复制到剪贴板")

    def _progress(self, downloaded, total, label=""):
        if threading.current_thread() is not self._main_thread:
            self._ui_queue.put(("progress", downloaded, total, label))
            return
        self._progress_direct(downloaded, total, label)

    def _progress_percent(self, percent, label):
        self._progress(percent, -100, label)

    def _progress_busy(self, label):
        self._progress(0, -1, label)

    def _progress_clear(self):
        self._progress(0, 0, "")

    def _progress_direct(self, downloaded, total, label=""):
        if total == -100:
            if getattr(self, '_indeterminate', False):
                self.progress_bar.stop()
                self.progress_bar.configure(mode='determinate')
                self._indeterminate = False
            pct = max(0, min(100, float(downloaded)))
            self.progress_var.set(pct)
            self.progress_label.config(text=f"  {label} ({pct:.0f}%)")
            self.root.update()
            return
        if total < 0:
            if not getattr(self, '_indeterminate', False):
                self.progress_bar.configure(mode='indeterminate')
                self.progress_bar.start(20)
                self._indeterminate = True
            self.progress_label.config(text=f"  {label}")
            self.root.update()
            return
        if getattr(self, '_indeterminate', False):
            self.progress_bar.stop()
            self.progress_bar.configure(mode='determinate')
            self.progress_var.set(0)
            self._indeterminate = False
        if total > 0:
            pct = max(0, min(100, downloaded / total * 100))
            self.progress_var.set(pct)
            mb_done = downloaded / 1048576
            mb_total = total / 1048576
            self.progress_label.config(text=f"  {label}: {mb_done:.1f} / {mb_total:.1f} MB ({pct:.0f}%)")
        else:
            mb_done = downloaded / 1048576
            self.progress_label.config(text=f"  {label}: 已下载 {mb_done:.1f} MB")
        self.root.update()

    def _reset_progress(self):
        if getattr(self, '_indeterminate', False):
            self.progress_bar.stop()
            self.progress_bar.configure(mode='determinate')
            self._indeterminate = False
        self.progress_var.set(0)
        self.progress_label.config(text="")

    def _set_buttons(self, state):
        self.btn_install.configure(state=state)
        if hasattr(self, "btn_delete_all"):
            self.btn_delete_all.configure(state=state)
        self.dir_entry.configure(state=state)
        self.btn_browse.configure(state=state)

    def _process_ui_queue(self):
        try:
            while True:
                item = self._ui_queue.get_nowait()
                kind = item[0]
                if kind == "log":
                    self._log_direct(item[2], item[1])
                elif kind == "progress":
                    self._progress_direct(item[1], item[2], item[3])
                elif kind == "install_done":
                    self._finish_install(*item[1:])
        except queue.Empty:
            pass
        try:
            self.root.after(100, self._process_ui_queue)
        except tk.TclError:
            pass

    def _run_network_checks(self):
        self._log("=======================================================")
        self._log("    开始检测网络环境...")
        self._log("=======================================================")
        failed = []
        results = []
        checks = get_network_checks()
        for index, (group, name, url) in enumerate(checks, 1):
            self._progress_percent(index / len(checks) * 100, f"网络检测: {name}")
            self._log(f"[{index}/{len(checks)}] {RESOURCE_LABELS.get(group, group)} - {name}")
            result = check_network_target(name, url)
            result["group"] = group
            results.append(result)
            if result["ok"]:
                self._log(f"  [OK] 可访问 ({result['elapsed']:.1f}s, HTTP {result['code']})")
            else:
                failed.append(result)
                self._log(f"  [WARN] 暂不可访问: {result['error']}")
            self._log(f"       {url}")
        self._progress_clear()
        strategy = analyze_network_profile(results)
        self._network_strategy = strategy
        self._log("")
        arch = detect_windows_arch()
        self._log(f"  [系统架构] Windows {describe_windows_arch(arch)}")
        if arch not in SUPPORTED_WINDOWS_ARCHES:
            self._log("  [WARN] 当前安装包仅内置 64 位 Python / uv / VSCode 下载策略，不支持此系统架构。")
        self._log(f"  [网络环境] {strategy['profile']}")
        self._log(f"  [推荐依赖源] {strategy['pypi_index_url']}")
        self._log(f"  [推荐原因] {strategy['reason']}")
        self._log(
            f"  [评分] 中国网络 {strategy['china_score']} / 国际网络 {strategy['international_score']} / 自定义资源 {strategy['custom_score']}"
        )
        self._log("  [推荐资源]")
        for group, item in strategy["selected"].items():
            self._log(
                f"     {RESOURCE_LABELS.get(group, group)}: {item['name']} ({item['elapsed']:.1f}s)"
            )
        self._log("  [说明] 所有资源按网络检测结果推荐；未配置可信替代源的项目会在候选中选择可用资源。")
        if strategy["profile"] == "网络环境不确定":
            self._log("  [继续] 网络环境不确定，但将按推荐资源继续执行一键安装。")
        if failed:
            self._log("")
            self._log("  [WARN] 网络检测发现不可访问项。")
            self._log("         可检查代理、公司网络白名单、安全软件，或稍后重试。")
        else:
            self._log("")
            self._log("  [OK] 网络检测通过。")
        self._log("")
        return failed, strategy

    def _format_delete_all_summary(self, summary):
        def block(title, items, empty):
            lines = [title]
            if items:
                lines.extend(f"  - {item}" for item in items)
            else:
                lines.append(f"  - {empty}")
            return "\n".join(lines)

        lines = [
            "彻底删除前确认",
            "",
            "本操作会先清理本工具写入的配置，然后删除安装器明确管理的目录和文件。",
            "请先关闭 VSCode、Python、uv、终端窗口，避免文件占用导致删除失败。",
            "根目录仅在清空后才会自动删除；如果里面还有其他文件，会保留。",
            "",
            block("识别到的安装根目录:", summary["roots"], "暂未识别到可删除的安装根目录"),
            "",
            block("将删除的目录:", summary.get("delete_dirs", []), "未发现安装器管理目录"),
            "",
            block("将删除的文件:", summary.get("delete_files", []), "未发现安装器管理文件"),
            "",
            block("将尝试结束的 VSCode 相关进程:", summary.get("managed_processes", []), "暂未检测到本工具 VSCode 目录下的占用进程"),
            "",
            block("同时会清理的 PATH 条目:", summary["path_items"], "未发现需要清理的 PATH 条目"),
            "",
            block("同时会删除的用户环境变量:", summary["env_items"], "未发现需要删除的环境变量"),
            "",
            block("同时会清理的右键菜单注册表项:", summary["reg_items"], "未发现本工具的右键菜单项"),
            "",
            block("同时会清理的 pip 镜像配置:", summary["pip_items"], "未发现本工具写入的 pip 镜像配置"),
            "",
            "请确认上面的删除范围和影响；点击“我已了解影响，确认彻底删除”后会立即执行。",
        ]
        if summary.get("process_check_error"):
            lines.insert(
                9,
                f"进程占用检测提示: {summary['process_check_error']}；执行时仍会尝试复查，若删除失败请关闭 VSCode 后重试。",
            )
        return "\n".join(lines)

    def _confirm_delete_all(self, summary):
        dialog = tk.Toplevel(self.root)
        dialog.title("确认彻底删除")
        dialog.geometry("760x580")
        dialog.minsize(600, 420)
        dialog.transient(self.root)
        dialog.grab_set()

        main = ttk.Frame(dialog, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main, text="请确认彻底删除范围", font=("Microsoft YaHei UI", 12, "bold")).pack(
            anchor=tk.W, pady=(0, 8)
        )

        text = scrolledtext.ScrolledText(main, wrap=tk.WORD, font=("Microsoft YaHei UI", 10), height=20)
        text.pack(fill=tk.BOTH, expand=True)
        text.insert("1.0", self._format_delete_all_summary(summary))
        text.configure(state="disabled")

        result = {"ok": False}

        def confirm():
            result["ok"] = True
            dialog.destroy()

        def cancel():
            dialog.destroy()

        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(btn_frame, text="取消", command=cancel).pack(side=tk.RIGHT)
        btn_confirm = ttk.Button(btn_frame, text="我已了解影响，确认彻底删除", command=confirm)
        btn_confirm.pack(side=tk.RIGHT, padx=(0, 8))
        dialog.protocol("WM_DELETE_WINDOW", cancel)
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        btn_confirm.focus_set()
        dialog.wait_window()
        return result["ok"]

    def _do_install(self):
        if self._install_active:
            messagebox.showinfo("安装中", "安装任务正在执行，请等待当前任务结束。", parent=self.root)
            return
        ver = sys.getwindowsversion()
        if ver.major < 10:
            messagebox.showerror(
                "系统版本不支持",
                f"当前系统: Windows {ver.major}.{ver.minor}\n\n"
                "本工具需要 Windows 10 或更高版本。\n"
                "Python 3.12 与新版 VSCode 不再适合 Windows 7/8。"
            )
            return
        arch = detect_windows_arch()
        if not is_supported_windows_arch():
            messagebox.showerror(
                "系统架构不支持",
                f"检测到当前 Windows 架构: {describe_windows_arch(arch)}\n\n"
                "本工具当前内置的是 64 位 Python / uv / VSCode 下载策略，"
                "仅支持 64 位 x64 Windows。\n\n已停止执行一键安装。",
                parent=self.root,
            )
            return
        self._set_log_context("install", clear=True)
        self._task_log_key = "install"
        self._reset_progress()
        install_dir = self.dir_var.get().strip()
        if not install_dir:
            self._task_log_key = None
            messagebox.showerror("错误", "请填写安装目录", parent=self.root)
            return

        self._install_active = True
        self._set_buttons("disabled")
        self.btn_install.configure(text="安装中...")

        def worker():
            success = False
            err_text = ""
            err_msg = ""
            try:
                failed_checks, strategy = self._run_network_checks()
                installer = EnvironmentInstaller(
                    install_dir,
                    self._log,
                    self._progress,
                    resource_strategy=strategy,
                )
                success = installer.install()
            except Exception as exc:
                err_msg = str(exc)
                err_text = traceback.format_exc()
                self._log(f"\n[ERROR] {err_text}")
            finally:
                self._ui_queue.put(("install_done", success, install_dir, err_msg, err_text))

        self._worker_thread = threading.Thread(target=worker, daemon=True)
        self._worker_thread.start()

    def _finish_install(self, success, install_dir, err_msg, err_text):
        self._install_active = False
        self._task_log_key = None
        self.btn_install.configure(text="一键安装")
        self._set_buttons("normal")
        self._reset_progress()
        if success:
            messagebox.showinfo(
                "安装完成",
                "安装完成!\n\n"
                f"安装位置: {install_dir}\n\n"
                "请新开命令行窗口，使环境变量生效。\n\n"
                "下一步:\n"
                "  1. 解压项目模板 -> 运行 重新初始化 V1.24.bat\n"
                "  2. 右键项目文件夹 -> Open with Code\n"
                "  3. 按 F5 运行!",
                parent=self.root,
            )
        elif err_msg:
            if "timed out" in err_msg.lower() or "timeout" in err_msg.lower():
                hint = (
                    "\n\n网络下载超时。已下载的 .part 缓存会保留在安装目录的 .download-cache 中，"
                    "网络恢复后再次点击一键安装会尝试继续下载。"
                )
            else:
                hint = ""
            messagebox.showerror("安装失败", f"安装异常:\n{err_msg}{hint}\n\n请查看安装日志。", parent=self.root)

    def _do_delete_all(self):
        try:
            self._set_log_context("delete_all", clear=False)
            self._task_log_key = "delete_all"
            install_dir = self.dir_var.get().strip() or INSTALL_DIR_DEFAULT
            installer = EnvironmentInstaller(install_dir, self._log)
            summary = installer.get_delete_all_summary()
            if not self._confirm_delete_all(summary):
                self._task_log_key = None
                return

            self._set_log_context("delete_all", clear=True)
            self._reset_progress()
            self._set_buttons("disabled")
            self._progress_busy("正在彻底删除...")
            ok = installer.delete_all(summary)
            self._progress_clear()
            if ok:
                messagebox.showinfo(
                    "完成",
                    "彻底删除完成。\n\n"
                    "本工具管理的 Python、uv、VSCode 便携目录、下载缓存和配置已清理。",
                    parent=self.root,
                )
            else:
                messagebox.showwarning(
                    "部分文件未删除",
                    "彻底删除已执行，但部分文件可能被占用未删除。\n\n"
                    "请关闭 VSCode、Python、终端后重试，或根据日志手动删除。",
                    parent=self.root,
                )
        except Exception as e:
            self._progress_clear()
            self._log(f"\n[ERROR] {traceback.format_exc()}")
            messagebox.showerror("错误", f"彻底删除异常: {e}", parent=self.root)
        finally:
            self._task_log_key = None
            self._set_buttons("normal")

    def run(self):
        if self.root is None:
            return
        self.root.update_idletasks()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        x = (self.root.winfo_screenwidth() - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"+{x}+{y}")
        self.root.mainloop()


# ==================== 入口 ====================


def write_startup_error(exc_text):
    log_path = os.path.join(tempfile.gettempdir(), "一键安装_启动错误.log")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(exc_text)
    return log_path


def main():
    try:
        InstallerApp().run()
    except Exception:
        exc_text = traceback.format_exc()
        log_path = write_startup_error(exc_text)
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("启动失败", f"一键安装工具启动失败。\n\n错误日志:\n{log_path}")
            root.destroy()
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()

