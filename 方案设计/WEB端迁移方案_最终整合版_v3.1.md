# Code880 Web 工作台 — 最终整合方案 v3.1

> 基于 v3 修订。v3 的整体架构、分层原则、分阶段计划保持不变，本版仅修复 v3 复核中发现的 7 个落地问题。**v3 + 本文 = 完整开发基准**，可进入 MVP 开发。

生成时间：2026-04-28
基于版本：v3 + 7 项复核修订

---

## 修订总览

| # | 问题 | 严重性 | 修复章节 |
|---|------|:------:|---------|
| 1 | Hub 端口自动探测与脚本硬编码 8800 矛盾 | 高 | 第一章 |
| 2 | 全局安装路径硬编码 `C:\PythonDev` 与"可自选安装目录"冲突 | 高 | 第二章 |
| 3 | Worker token 放命令行参数，同用户进程可见 | 中 | 第三章 |
| 4 | CSRF 描述与 HttpOnly Cookie 实现矛盾 | 中 | 第四章 |
| 5 | Worker stdout/stderr PIPE 缓冲区满导致进程卡死 | 高 | 第五章 |
| 6 | 路径安全应显式拒绝绝对路径输入 | 中 | 第六章 |
| 7 | 缺少 ONLYOFFICE 可选增强位说明 | 低 | 第七章 |

---

## 一、Hub 端口发现机制修复

> **问题**：v3 脚本硬编码 `$HubPort = 8800`，但文档说端口被占时会自动探测到其他端口。如果 Hub 实际运行在 8801，脚本找不到它。

### 1.1 修复方案：脚本从 runtime 文件发现实际端口

```powershell
# === v3.1 修复: 端口发现 ===
# 不再硬编码端口，而是从 hub_runtime.json 读取实际值

$RuntimeFile = "$env:LOCALAPPDATA\Code880Web\hub_runtime.json"

function Get-HubBaseUrl {
    # 1. 尝试从 runtime 文件读取
    if (Test-Path $RuntimeFile) {
        try {
            $runtime = Get-Content $RuntimeFile -Raw | ConvertFrom-Json
            $url = $runtime.base_url  # 例如 "http://127.0.0.1:8801"
            
            # 2. 验证该地址确实是 Code880 Hub
            $resp = Invoke-WebRequest "$url/api/hub/identity" -TimeoutSec 2 -UseBasicParsing
            if ($resp.StatusCode -eq 200) {
                return $url
            }
        } catch { }
    }
    
    # 3. runtime 文件不存在或验证失败 → Hub 未运行
    return $null
}

function Start-Hub {
    $installInfo = Get-InstallInfo  # 见第二章
    $hubPython = $installInfo.python_path
    $hubApp = $installInfo.hub_app_path
    
    # 启动 Hub (Hub 内部自行探测可用端口并写入 runtime 文件)
    Start-Process -FilePath $hubPython -ArgumentList "`"$hubApp`"" `
        -WindowStyle Hidden -PassThru | Out-Null
    
    # 等待 runtime 文件落盘 (Hub 启动后写入实际端口)
    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        if (Test-Path $RuntimeFile) {
            $url = Get-HubBaseUrl
            if ($null -ne $url) { $ready = $true; break }
        }
    }
    
    if (-not $ready) {
        Write-Host '  [!] Hub 启动超时'; exit 1
    }
    return $url
}

# === 主流程 ===
$hubUrl = Get-HubBaseUrl
if ($null -eq $hubUrl) {
    Write-Host '  [i] 正在启动项目管理中心...'
    $hubUrl = Start-Hub
}
# 后续所有调用使用 $hubUrl 而非硬编码端口
```

### 1.2 Hub 端内部：启动时写入 runtime 文件

```python
# Hub app.py 启动逻辑
import json, os, socket

def 探测可用端口(起始=8800, 范围=50) -> int:
    for 端口 in range(起始, 起始 + 范围):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", 端口))
                return 端口
            except OSError:
                continue
    raise RuntimeError("无可用端口")

实际端口 = 探测可用端口()

# 先写 runtime 文件，再启动服务（脚本等的是这个文件）
runtime_path = os.path.join(
    os.environ["LOCALAPPDATA"], "Code880Web", "hub_runtime.json"
)
os.makedirs(os.path.dirname(runtime_path), exist_ok=True)

with open(runtime_path, "w", encoding="utf-8") as f:
    json.dump({
        "pid": os.getpid(),
        "port": 实际端口,
        "base_url": f"http://127.0.0.1:{实际端口}",
        "launch_token_path": os.path.join(
            os.environ["LOCALAPPDATA"], "Code880Web", "keys", "launch_token"
        ),
        "started_at": datetime.now().isoformat(),
        "version": "1.0.0"
    }, f, ensure_ascii=False, indent=2)

# 然后启动 uvicorn
uvicorn.run(app, host="127.0.0.1", port=实际端口)
```

---

## 二、安装路径发现机制修复

> **问题**：v3 硬编码 `C:\PythonDev\code880web\` 和 `C:\PythonDev\Python312\`，但一键安装说明允许用户自选安装目录。

### 2.1 修复方案：install.json 注册表

一键安装器在安装完成后写入发现文件：

```
%LOCALAPPDATA%\Code880Web\install.json
{
    "install_root": "D:\\MyPythonDev",
    "python_path": "D:\\MyPythonDev\\Python312\\python.exe",
    "hub_app_path": "D:\\MyPythonDev\\code880web\\hub\\app.py",
    "worker_app_path": "D:\\MyPythonDev\\code880web\\worker\\app.py",
    "static_path": "D:\\MyPythonDev\\code880web\\static",
    "installed_at": "2026-04-28T10:00:00",
    "version": "5.11"
}
```

### 2.2 脚本从 install.json 发现路径

```powershell
# === v3.1 修复: 路径发现 ===
$InstallInfoFile = "$env:LOCALAPPDATA\Code880Web\install.json"

function Get-InstallInfo {
    if (-not (Test-Path $InstallInfoFile)) {
        Write-Host '  [!] 未找到安装信息，请先运行一键安装'
        exit 1
    }
    $info = Get-Content $InstallInfoFile -Raw | ConvertFrom-Json
    
    # 校验关键路径存在
    if (-not (Test-Path $info.python_path)) {
        Write-Host "  [!] Python 未找到: $($info.python_path)"
        exit 1
    }
    if (-not (Test-Path $info.hub_app_path)) {
        Write-Host "  [!] Hub 未找到: $($info.hub_app_path)"
        exit 1
    }
    return $info
}
```

### 2.3 一键安装器写入时机

```python
# 一键安装卸载.py — 安装成功后追加写入
import json, os

def 写入Web安装信息(安装根目录: str):
    info = {
        "install_root": 安装根目录,
        "python_path": os.path.join(安装根目录, "Python312", "python.exe"),
        "hub_app_path": os.path.join(安装根目录, "code880web", "hub", "app.py"),
        "worker_app_path": os.path.join(安装根目录, "code880web", "worker", "app.py"),
        "static_path": os.path.join(安装根目录, "code880web", "static"),
        "installed_at": datetime.now().isoformat(),
        "version": "5.11"
    }
    
    目标目录 = os.path.join(os.environ["LOCALAPPDATA"], "Code880Web")
    os.makedirs(目标目录, exist_ok=True)
    
    with open(os.path.join(目标目录, "install.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
```

### 2.4 v3 目录结构更新

```
v3 写法 (硬编码):
  C:\PythonDev\code880web\hub\app.py
  C:\PythonDev\Python312\python.exe

v3.1 写法 (动态发现):
  {install.json → install_root}\code880web\hub\app.py
  {install.json → python_path}
  
  发现链: %LOCALAPPDATA%\Code880Web\install.json → 实际路径
```

---

## 三、Worker Token 传递方式修复

> **问题**：v3 通过 `--internal-token xxx` 命令行参数传递 token，Windows 下任务管理器/WMI 可查看进程命令行。

### 3.1 修复方案：临时文件 + ACL 保护

```python
import secrets
import os
import tempfile
import stat

def 启动Worker(项目路径: str, 内部端口: int) -> dict:
    install_info = 读取安装信息()
    worker脚本 = install_info["worker_app_path"]
    hub_python = install_info["python_path"]
    
    # 生成 Worker 专属 token
    worker_token = secrets.token_hex(32)
    
    # [v3.1 修复] 写入临时文件传递 token，而非命令行参数
    token_dir = os.path.join(
        os.environ["LOCALAPPDATA"], "Code880Web", "worker_tokens"
    )
    os.makedirs(token_dir, exist_ok=True)
    
    token_file = os.path.join(token_dir, f"worker_{内部端口}.token")
    with open(token_file, "w") as f:
        f.write(worker_token)
    
    # 设置仅当前用户可读（Windows ACL 简化版）
    os.chmod(token_file, stat.S_IRUSR | stat.S_IWUSR)
    
    # 命令行只传 token 文件路径（不包含 token 本身）
    进程 = subprocess.Popen(
        [hub_python, worker脚本,
         "--port", str(内部端口),
         "--token-file", token_file,      # 改为文件路径
         "--project-root", 项目路径],
        cwd=项目路径,
        stdout=open(os.path.join(项目路径, ".web-workbench", "worker.log"), "a"),
        stderr=subprocess.STDOUT,         # 见第五章修复
        creationflags=(
            subprocess.CREATE_NO_WINDOW |
            subprocess.CREATE_NEW_PROCESS_GROUP
        )
    )
    
    return {
        "pid": 进程.pid,
        "port": 内部端口,
        "token": worker_token,
        "token_file": token_file,
        "process": 进程
    }

def 清理Worker(worker_info: dict):
    """Worker 停止后删除 token 文件"""
    if os.path.exists(worker_info["token_file"]):
        os.remove(worker_info["token_file"])
```

```python
# Worker 端读取 token
# worker/app.py

import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, required=True)
parser.add_argument("--token-file", required=True)
parser.add_argument("--project-root", required=True)
args = parser.parse_args()

# 从文件读取 token，然后立即删除文件（进一步缩小暴露窗口）
with open(args.token_file, "r") as f:
    INTERNAL_TOKEN = f.read().strip()
os.remove(args.token_file)  # 读后即删
```

### 3.2 后期更强方案

```
正式版后期可选升级:
  方案 A: stdin 握手 — Hub 通过 subprocess.PIPE 的 stdin 发送 token
  方案 B: Windows Named Pipe — 彻底不走 TCP，管道名随机
  方案 C: 环境变量传递 — 比命令行安全但仍非完美
  
  第一版用临时文件 + 读后即删已足够安全。
```

---

## 四、CSRF 双 Cookie 机制修复

> **问题**：v3 说 Cookie 是 HttpOnly，又说 CSRF token 值"从 Cookie 同步"。HttpOnly Cookie 不能被前端 JS 读取，无法提取 CSRF token。

### 4.1 修复方案：双 Cookie 模式

```
/bootstrap?code=xxx 认证成功后设置两个 Cookie:

Cookie 1 (会话): 
  Set-Cookie: code880_session=xxx; HttpOnly; SameSite=Strict; Path=/
  → 纯后端用，前端 JS 不可读取
  → 用于验证用户身份

Cookie 2 (CSRF):
  Set-Cookie: code880_csrf=yyy; SameSite=Strict; Path=/
  → 注意: 没有 HttpOnly 标志
  → 前端 JS 可以读取此值
  → 前端在写操作时取出放入请求头

前端写操作:
  const csrfToken = document.cookie
      .split('; ')
      .find(c => c.startsWith('code880_csrf='))
      ?.split('=')[1];
  
  fetch('/api/workspaces/xxx/files/save', {
      method: 'POST',
      headers: {
          'X-Code880-CSRF': csrfToken,  // 从非 HttpOnly cookie 取出
          'Content-Type': 'application/json'
      },
      credentials: 'same-origin',  // 自动携带 HttpOnly session cookie
      body: JSON.stringify(data)
  });

后端校验:
  1. 检查 code880_session Cookie → 验证会话有效性
  2. 检查 X-Code880-CSRF 头 → 必须与 code880_csrf Cookie 值匹配
  3. 恶意网页: 可以触发浏览器自动携带 Cookie，但无法读取 Cookie 值
     → 无法构造正确的 X-Code880-CSRF 头
     → 请求被拒绝
```

### 4.2 后端校验代码

```python
from fastapi import Request, HTTPException

async def 校验CSRF(request: Request):
    """写操作中间件"""
    # 1. 会话校验 (HttpOnly cookie)
    session_id = request.cookies.get("code880_session")
    if not session_id or not 验证会话(session_id):
        raise HTTPException(401, "会话无效")
    
    # 2. CSRF 校验 (双 Cookie 验证)
    csrf_cookie = request.cookies.get("code880_csrf")
    csrf_header = request.headers.get("X-Code880-CSRF")
    
    if not csrf_cookie or not csrf_header:
        raise HTTPException(403, "缺少 CSRF 凭证")
    
    if csrf_cookie != csrf_header:
        raise HTTPException(403, "CSRF 验证失败")
    
    # 3. Origin 校验
    origin = request.headers.get("Origin")
    if origin and not origin.startswith(f"http://127.0.0.1:"):
        raise HTTPException(403, "来源不合法")
```

### 4.3 v3 原文对照修正

```
v3 原文:
  "写操作额外要求 X-Code880-CSRF 头 (值从 Cookie 中同步)"

v3.1 修正:
  "后端设置两个 Cookie: 
   code880_session (HttpOnly, 纯后端会话) + 
   code880_csrf (非 HttpOnly, 前端可读取)。
   写操作要求前端从 csrf Cookie 读取值，
   放入 X-Code880-CSRF 请求头。"
```

---

## 五、Worker 输出重定向修复

> **问题**：v3 使用 `stdout=subprocess.PIPE, stderr=subprocess.PIPE`，如果 Hub 不持续读取管道，缓冲区满后 Worker 会永久阻塞。

### 5.1 修复方案：输出直接写入日志文件

```python
import os

def 启动Worker(项目路径: str, 内部端口: int) -> dict:
    # 确保日志目录存在
    workbench_dir = os.path.join(项目路径, ".web-workbench")
    os.makedirs(workbench_dir, exist_ok=True)
    
    log_path = os.path.join(workbench_dir, "worker.log")
    
    # [v3.1 修复] stdout/stderr 直接写文件，不用 PIPE
    log_file = open(log_path, "a", encoding="utf-8")
    
    进程 = subprocess.Popen(
        [hub_python, worker脚本,
         "--port", str(内部端口),
         "--token-file", token_file,
         "--project-root", 项目路径],
        cwd=项目路径,
        stdout=log_file,           # 直接写文件
        stderr=subprocess.STDOUT,  # stderr 合并到 stdout
        creationflags=(
            subprocess.CREATE_NO_WINDOW |
            subprocess.CREATE_NEW_PROCESS_GROUP
        )
    )
    
    # 注意: log_file 句柄由子进程继承，Hub 可关闭自己的引用
    # 但不要在 Worker 运行期间关闭，否则日志中断
    
    return {
        "pid": 进程.pid,
        "port": 内部端口,
        "token": worker_token,
        "process": 进程,
        "log_file_handle": log_file,  # Hub 保留引用，Worker 停止后关闭
        "log_path": log_path
    }

def 停止Worker(worker_info: dict):
    worker_info["process"].terminate()
    worker_info["process"].wait(timeout=10)
    worker_info["log_file_handle"].close()  # Worker 停止后关闭句柄
    清理Worker(worker_info)
```

### 5.2 日志轮转

```python
# Worker 日志可能很大，需要轮转
# Hub 在 Worker 重启时执行:

import shutil

def 轮转Worker日志(log_path: str, 最大保留=3):
    if not os.path.exists(log_path):
        return
    大小 = os.path.getsize(log_path)
    if 大小 < 10 * 1024 * 1024:  # 小于 10MB 不轮转
        return
    
    # worker.log → worker.log.1 → worker.log.2 → 删除
    for i in range(最大保留 - 1, 0, -1):
        旧 = f"{log_path}.{i}"
        新 = f"{log_path}.{i+1}"
        if os.path.exists(旧):
            if i + 1 >= 最大保留:
                os.remove(旧)
            else:
                shutil.move(旧, 新)
    if os.path.exists(log_path):
        shutil.move(log_path, f"{log_path}.1")
```

---

## 六、路径安全增强：显式拒绝绝对路径

> **问题**：`os.path.join("C:\\proj", "D:\\hack")` 的结果是 `D:\\hack`（绝对路径覆盖前缀），虽然 commonpath 多数情况能挡住，但应在最前面显式拒绝。

### 6.1 修复后的完整路径校验

```python
import os
from pathlib import Path

def 校验路径安全(项目根: str, 请求相对路径: str) -> bool:
    """
    v3.1 完整版路径安全校验
    修复链: v2(startswith) → v3(commonpath) → v3.1(+绝对路径拒绝+Path.resolve)
    """
    
    # === 第 0 层: 输入清理 ===
    if not 请求相对路径 or not 请求相对路径.strip():
        return False
    
    # [v3.1 新增] 显式拒绝绝对路径
    if os.path.isabs(请求相对路径):
        return False
    
    # 拒绝包含盘符的变体 (如 "C:" "C:/" "\\?\C:")
    if len(请求相对路径) >= 2 and 请求相对路径[1] == ':':
        return False
    
    # 拒绝 UNC 路径
    if 请求相对路径.startswith('\\\\') or 请求相对路径.startswith('//'):
        return False
    
    # === 第 1 层: 规范化 (使用 pathlib 更可靠) ===
    try:
        根路径 = Path(项目根).resolve(strict=True)
        目标路径 = (根路径 / 请求相对路径).resolve()
    except (OSError, ValueError):
        return False
    
    # === 第 2 层: 边界判断 (relative_to 比 commonpath 更直观) ===
    try:
        目标路径.relative_to(根路径)
    except ValueError:
        return False  # 不在根目录内
    
    # === 第 3 层: 符号链接检测 ===
    实际路径 = Path(项目根) / 请求相对路径
    if 实际路径.exists() and 实际路径.is_symlink():
        链接目标 = 实际路径.resolve()
        try:
            链接目标.relative_to(根路径)
        except ValueError:
            return False  # 符号链接指向外部
    
    return True


# === 测试用例 ===
# 校验路径安全("C:\\proj", "src\\main.py")       → True
# 校验路径安全("C:\\proj", "..\\secret")          → False (穿越)
# 校验路径安全("C:\\proj", "D:\\hack\\file.py")   → False (绝对路径)
# 校验路径安全("C:\\proj", "..\\proj2\\a.py")     → False (前缀绕过)
# 校验路径安全("C:\\proj", "C:\\proj\\ok.py")     → False (绝对路径)
# 校验路径安全("C:\\proj", "\\\\server\\share")   → False (UNC)
# 校验路径安全("C:\\proj", "")                    → False (空)
```

---

## 七、Office 预览增强路径补充

> **问题**：v3 的 Office 增强方案只列了 LibreOffice 和本机 Office/WPS，结合前面 Office 选型分析，应补充 ONLYOFFICE 作为"可选插件"位置。

### 7.1 v3 第八章 8.2 节追加

```
v3 原有增强方案:
  增强方案 A: LibreOffice Portable headless → 转 PDF
  增强方案 B: 检测本机 Office/WPS → COM 转 PDF
  增强方案 C: 在线转换 API

v3.1 追加:
  增强方案 D: ONLYOFFICE 可选插件 (仅当需要浏览器内编辑时)
    → 用户手动安装 ONLYOFFICE Document Server (Docker)
    → Hub 配置 ONLYOFFICE 接入地址
    → 预览/编辑请求转发到 ONLYOFFICE
    → 不进入默认一键安装，不增加基础版复杂度
    → 适用场景: 培训机构统一部署、需要在线编辑 Office 的高级用户
    → 实施优先级: 最低，仅当有明确编辑需求时再做
```

### 7.2 最终 Office 预览方案总表

| 层级 | 方案 | 何时使用 | 进入安装包 |
|------|------|---------|:---------:|
| 默认 | mammoth + openpyxl + python-pptx | 第一版即有 | 是 |
| 增强 A | LibreOffice Portable headless | 用户点击"下载增强组件" | 可选下载 |
| 增强 B | 本机 Office/WPS COM | 自动检测已装 Office | 否 |
| 增强 C | 在线转换 API | 需联网，可配置 | 否 |
| 增强 D | ONLYOFFICE (编辑级) | 需手动装 Docker | 否 |

---

## 八、完整启动脚本（整合所有修复）

以下是整合第一~五章全部修复后的最终启动脚本：

### 8.1 启动Web工作台.bat

```batch
@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Code880 Web 工作台

echo.
echo   Code880 Web 工作台 启动中...
echo.

:: 用 PowerShell 执行核心逻辑（避免 batch 路径转义问题）
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0启动Web工作台.ps1" -ProjectRoot "%~dp0"

if %errorlevel% neq 0 (
    echo.
    echo   [!] 启动失败，请查看错误信息
    pause
    exit /b 1
)
```

### 8.2 启动Web工作台.ps1（最终版）

```powershell
param(
    [string]$ProjectRoot = (Get-Location).Path
)

$ErrorActionPreference = 'Stop'
# 去掉尾部反斜杠（batch %~dp0 会带尾部 \）
$ProjectRoot = $ProjectRoot.TrimEnd('\')

$GlobalDir    = "$env:LOCALAPPDATA\Code880Web"
$RuntimeFile  = "$GlobalDir\hub_runtime.json"
$InstallFile  = "$GlobalDir\install.json"
$TokenDir     = "$GlobalDir\keys"

# ======================================================
# 1. 发现安装路径 [v3.1 问题2 修复]
# ======================================================
if (-not (Test-Path $InstallFile)) {
    Write-Host '  [!] 未找到安装信息'
    Write-Host '  [!] 请先运行 "一键安装.exe"'
    exit 1
}
$install = Get-Content $InstallFile -Raw | ConvertFrom-Json

if (-not (Test-Path $install.python_path)) {
    Write-Host "  [!] Python 未找到: $($install.python_path)"
    exit 1
}
if (-not (Test-Path $install.hub_app_path)) {
    Write-Host "  [!] Web 工作台组件未找到"
    Write-Host "  [!] 请更新一键安装包以获取 Web 功能"
    exit 1
}

# ======================================================
# 2. 检查 Hub 是否已运行 [v3.1 问题1 修复]
# ======================================================
$hubUrl = $null

if (Test-Path $RuntimeFile) {
    try {
        $runtime = Get-Content $RuntimeFile -Raw | ConvertFrom-Json
        $testUrl = "$($runtime.base_url)/api/hub/identity"
        $resp = Invoke-WebRequest $testUrl -TimeoutSec 2 -UseBasicParsing
        if ($resp.StatusCode -eq 200) {
            $hubUrl = $runtime.base_url
            Write-Host "  [i] 已连接到项目管理中心 ($hubUrl)"
        }
    } catch { }
}

# ======================================================
# 3. Hub 未运行则启动 [v3.1 问题4 修复: WindowStyle Hidden]
# ======================================================
if ($null -eq $hubUrl) {
    Write-Host '  [i] 正在启动项目管理中心...'
    
    Start-Process -FilePath $install.python_path `
        -ArgumentList "`"$($install.hub_app_path)`"" `
        -WindowStyle Hidden -PassThru | Out-Null
    
    # 等待 runtime 文件落盘（Hub 启动后写入实际端口）
    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        if (Test-Path $RuntimeFile) {
            try {
                $runtime = Get-Content $RuntimeFile -Raw | ConvertFrom-Json
                $testUrl = "$($runtime.base_url)/api/hub/identity"
                $r = Invoke-WebRequest $testUrl -TimeoutSec 1 -UseBasicParsing
                if ($r.StatusCode -eq 200) {
                    $hubUrl = $runtime.base_url
                    $ready = $true
                    break
                }
            } catch { }
        }
    }
    
    if (-not $ready) {
        Write-Host '  [!] 项目管理中心启动超时'
        exit 1
    }
    Write-Host "  [OK] 项目管理中心已启动 ($hubUrl)"
}

# ======================================================
# 4. 读取 launch_token [v3.1 认证闭环]
# ======================================================
$tokenFile = "$TokenDir\launch_token"
if (-not (Test-Path $tokenFile)) {
    Write-Host '  [!] 认证文件不存在'
    exit 1
}
$launchToken = (Get-Content $tokenFile -Raw).Trim()

# ======================================================
# 5. 注册项目 [v3.1 问题2+3 修复: PowerShell 原生序列化]
# ======================================================
Write-Host '  [i] 正在注册当前项目...'
$regBody = @{ root_path = $ProjectRoot } | ConvertTo-Json -Compress
$regHeaders = @{
    'Authorization' = "Bearer $launchToken"
    'Content-Type'  = 'application/json'
}

try {
    $regResp = Invoke-RestMethod -Method POST `
        -Uri "$hubUrl/internal/projects/register" `
        -Body $regBody -Headers $regHeaders -TimeoutSec 10
    $workspaceId = $regResp.workspace_id
    Write-Host "  [OK] 项目已注册 (ID: $workspaceId)"
} catch {
    Write-Host "  [!] 项目注册失败: $_"
    exit 1
}

# ======================================================
# 6. 获取一次性 bootstrap code 并打开浏览器 [v3.1 问题2 修复]
# ======================================================
try {
    $codeBody = @{ target = "/w/$workspaceId" } | ConvertTo-Json -Compress
    $codeResp = Invoke-RestMethod -Method POST `
        -Uri "$hubUrl/internal/bootstrap-code" `
        -Body $codeBody -Headers $regHeaders `
        -ContentType 'application/json' -TimeoutSec 5
    $openUrl = "$hubUrl/bootstrap?code=$($codeResp.code)"
} catch {
    $openUrl = $hubUrl  # 降级: 打开首页
}

Start-Process $openUrl
Write-Host ''
Write-Host '  [OK] 启动完成！请在浏览器中操作。'
Write-Host '  [OK] 关闭此窗口不影响 Web 工作台运行。'
```

---

## 九、v3.1 修订清单

| # | v3 问题 | v3.1 修复 | 章节 |
|---|--------|----------|------|
| 1 | Hub 端口硬编码与自动探测矛盾 | 脚本从 `hub_runtime.json` 读实际端口，Hub 启动后先写 runtime 再启动服务 | 第一章 |
| 2 | 安装路径硬编码 `C:\PythonDev` | 一键安装写入 `install.json`，脚本从中发现实际路径 | 第二章 |
| 3 | Worker token 命令行可见 | 改为临时文件传递，Worker 读后即删 | 第三章 |
| 4 | HttpOnly Cookie 与 CSRF 读取矛盾 | 双 Cookie 模式：HttpOnly session + 非 HttpOnly csrf | 第四章 |
| 5 | Worker PIPE 缓冲区满致卡死 | stdout/stderr 直接写日志文件，附带日志轮转 | 第五章 |
| 6 | 路径校验未拒绝绝对路径输入 | 首先拒绝 `os.path.isabs`/盘符/UNC，改用 `Path.resolve` + `relative_to` | 第六章 |
| 7 | 缺少 ONLYOFFICE 可选增强位 | 追加为"增强方案 D"，明确不进入默认安装 | 第七章 |

---

## 十、总结

v3.1 修复后的启动发现链：

```
一键安装.exe
  → 写入 %LOCALAPPDATA%\Code880Web\install.json (安装路径)
  → 部署 code880web 到用户选择的目录

双击 启动Web工作台.bat
  → ps1 读取 install.json 发现 Python/Hub 路径
  → 检查 hub_runtime.json 发现 Hub 是否已运行及实际端口
  → Hub 未运行? → Start-Process Hidden 启动 → 等待 runtime 文件落盘
  → 从本机文件读取 launch_token
  → POST /internal/projects/register (PowerShell 序列化，无路径转义)
  → POST /internal/bootstrap-code (获取一次性 code)
  → 打开 http://127.0.0.1:{实际端口}/bootstrap?code=xxx
  → Hub 校验 → 设置双 Cookie (session HttpOnly + csrf 可读) → 跳转
  → Worker 启动时 token 通过临时文件传递 (读后即删)
  → Worker 输出写日志文件 (不阻塞)
```

**至此，v3 复核的全部 7 个问题已修复，可进入 MVP 开发。**

---

> 文档版本：v3.1 | 创建日期：2026-04-28
> 定位：v3 的补丁文档，v3 + v3.1 = 完整开发基准
