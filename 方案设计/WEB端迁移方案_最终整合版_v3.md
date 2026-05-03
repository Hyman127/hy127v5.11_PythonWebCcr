# Code880 Web 工作台 — 最终整合方案 v3

> 基于 v2 修订。本版修复了 v2 复核中发现的 8 个落地硬问题（进程隔离原则冲突、认证断点、路径转义、进程脱离、路径安全绕过、Worker 可达性、Office 能力标注、Hub 代码归属），并将文档分为 MVP / 正式稳定版两个目标层级。后续开发以本文为准。

生成时间：2026-04-28  
基于版本：v2 + 复核修订

---

## 一、设计原则（分层）

### 1.1 全版本不可妥协原则

| # | 原则 | 说明 |
|---|------|------|
| 1 | **VSCode 不必启动** | 后端直接服务项目目录，不依赖任何 VSCode 进程 |
| 2 | **浏览器即入口** | 双击 bat → 自动打开浏览器，非 IT 用户零学习成本 |
| 3 | **仅监听 127.0.0.1** | 本地服务不暴露网络，安全边界清晰 |
| 4 | **新增不破坏** | 所有 Web 代码放 `web/` 目录，原项目文件保持不变 |
| 5 | **一个固定 URL 入口** | 用户只看到 `http://127.0.0.1:8800`，不理解端口 |

### 1.2 正式稳定版原则（MVP 阶段目标达成但不强制验收）

| # | 原则 | 说明 |
|---|------|------|
| 6 | **多项目=多标签页** | 同一浏览器同时打开多个项目，与其他网页共存互不干扰 |
| 7 | **进程级隔离** | 每个项目独立 Worker 进程，一个崩溃不拖垮其他项目 |
| 8 | **认证闭环** | 启动 token → 会话 → CSRF 完整链路，恶意网页不可越权 |
| 9 | **文件版本校验** | 多标签/多进程写入同一文件时不会静默覆盖 |

> **v2→v3 修订 [问题1]**：v2 把"进程级隔离"列为不可妥协，同时又允许 MVP 单进程。此处明确分层：MVP 可用单进程多协程验证 UI 和功能流程，但不进入正式多项目稳定版验收。正式版必须 Worker 独立进程。

---

## 二、整体架构

### 2.1 架构图（正式稳定版）

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           用户浏览器                                      │
│                                                                         │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐  ┌───────┐ │
│  │ 项目管理控制台   │  │ 项目 A 工作台   │  │ 项目 B 工作台   │  │ 百度  │ │
│  │ /              │  │ /w/proj_a      │  │ /w/proj_b      │  │ 等网页 │ │
│  └───────┬────────┘  └───────┬────────┘  └───────┬────────┘  └───────┘ │
│          │                   │                   │                      │
└──────────┼───────────────────┼───────────────────┼──────────────────────┘
           │ 全部走 127.0.0.1:8800                  │
           ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│             Hub 主进程 (固定 port 8800, 全局唯一安装)                      │
│                                                                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐ │
│  │ 静态文件  │ │ 项目注册 │ │ 反向代理 │ │ AI 模型  │ │ 安全认证     │ │
│  │ 托管     │ │ 表管理   │ │ 到Worker │ │ 全局配置 │ │ Token/CSRF  │ │
│  └──────────┘ └──────────┘ └────┬─────┘ └──────────┘ └──────────────┘ │
│                                 │ 内部转发 (注入 Worker 内部 token)       │
└─────────────────────────────────┼───────────────────────────────────────┘
                                  │
           ┌──────────────────────┼──────────────────────┐
           ▼                      ▼                      ▼
┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐
│  Worker A          │  │  Worker B          │  │  Worker C          │
│  内部端口: 动态    │  │  内部端口: 动态     │  │  内部端口: 动态     │
│  内部 token 校验   │  │  内部 token 校验    │  │  内部 token 校验    │
│  独立 PID          │  │  独立 PID          │  │  独立 PID          │
└───────────────────┘  └───────────────────┘  └───────────────────┘
```

### 2.2 关键设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 多项目路由方式 | **单端口 + 路径路由** `/w/{id}` | 用户不理解多端口，收藏夹和历史记录整洁 |
| Worker 通信方式 | Hub 反向代理 + **Worker 内部 token** | 见 [问题6] 修复 |
| 浏览器存储隔离 | `code880:{workspace_id}:key` 命名空间 | 同源策略下多项目数据不互相污染 |
| AI 配置 | 全局模型 + 项目级上下文 | API Key 只配一次，上下文按项目独立 |
| Hub 代码归属 | **全局唯一安装** | 见 [问题8] 修复 |
| MVP Worker 模式 | 单进程多协程，UI 验证用 | 正式版必须多进程，见 [问题1] |

---

## 三、Hub 主服务设计

### 3.1 Hub 核心职责

```
Hub 主服务 (FastAPI, port=8800, bind=127.0.0.1):
    ├─ 托管前端静态文件 (Vue 打包后的 dist/)
    ├─ 项目注册表 CRUD
    ├─ Worker 生命周期管理 (start/stop/restart/health)
    ├─ 反向代理: /api/workspaces/{id}/* → Worker 内部端口
    │     └─ 代理时注入 X-Worker-Token 头 (见 [问题6])
    ├─ WebSocket 代理: /ws/workspaces/{id} → Worker WS
    ├─ 全局 AI 模型配置管理
    ├─ API Key 加密存储 (Windows DPAPI / keyring)
    ├─ 安全认证: 启动 token → 会话 Cookie → CSRF
    ├─ Hub 健康监测循环
    └─ 全局日志
```

### 3.2 Hub 全局唯一安装位置

> **v2→v3 修订 [问题8]**：v2 的目录结构把 Hub 放在每个项目的 `web/hub/`，同时全局启动脚本又指向 `C:\PythonDev\code880web\hub\app.py`，多项目模板版本不同时会互相抢 Hub 主导权。

**修正方案：**

```
Hub = 全局安装，只有一份
  位置: C:\PythonDev\code880web\
    ├── hub\           ← Hub 服务代码
    ├── worker\        ← Worker 服务代码（模板，由 Hub 调度）
    ├── static\        ← 前端打包产物
    └── requirements.txt

项目内 = 只保留启动脚本 + 项目运行时数据
  {项目根目录}\
    ├── 启动Web工作台.bat     ← 启动脚本（调用全局 Hub）
    ├── .web-workbench\       ← Worker 运行时数据（自动生成）
    └── (原有文件不动)
```

Hub 和 Worker 代码由**一键安装包**统一部署到 `C:\PythonDev\code880web\`，项目模板不携带 Hub/Worker 代码副本。这样：
- 所有项目共用同一版本的 Hub/Worker
- 升级只需更新一处
- 不存在多版本抢占问题

### 3.3 Hub 发现机制

```
%LOCALAPPDATA%\Code880Web\hub_runtime.json
{
    "pid": 12345,
    "port": 8800,
    "base_url": "http://127.0.0.1:8800",
    "launch_token_path": "...\\keys\\launch_token",
    "started_at": "2026-04-28T17:30:00+08:00",
    "version": "1.0.0"
}
```

启动脚本流程：
1. 读取 `hub_runtime.json`
2. 访问 `GET /api/hub/identity` 确认身份
3. 如已运行 → 复用现有 Hub
4. 如未运行或端口被占 → 启动新 Hub，端口自动探测
5. 更新 `hub_runtime.json`

---

## 四、认证设计（闭环修复）

> **v2→v3 修订 [问题2]**：v2 的认证章节描述了 `/bootstrap?launch_token=xxx` 建立会话，但启动脚本直接调用 API 且最后打开根地址时完全没有携带 token。这是安全设计断点。

### 4.1 完整认证流程

```
1. Hub 启动时
   → 生成随机 launch_token (32 字节 hex)
   → 写入 %LOCALAPPDATA%\Code880Web\keys\launch_token
   → 生成随机 internal_secret (用于内部 API 签名)

2. 启动脚本 (bat/ps1) 注册项目时
   → 从本机文件读取 launch_token
   → 调用 POST /api/hub/projects 时携带 Authorization: Bearer {launch_token}
   → 这是 internal API，只有本机脚本能读到 token 文件

3. 启动脚本打开浏览器时
   → 生成一次性 bootstrap_code (Hub 提供 API)
   → 打开 http://127.0.0.1:8800/bootstrap?code={bootstrap_code}
   → Hub 校验 code → 设置 HttpOnly + SameSite=Strict 会话 Cookie
   → 跳转到 / 或 /w/{workspace_id}

4. 后续浏览器请求
   → Cookie 中的会话 ID → 验证有效性
   → 写操作额外要求 X-Code880-CSRF 头 (值从 Cookie 中同步)
   → 读操作也要求 Cookie 有效（防止恶意网页 GET 读取）

5. Worker 内部通信
   → Hub 代理转发时注入 X-Worker-Token: {worker专属token}
   → Worker 校验该 token，拒绝所有不带 token 的直接请求
```

### 4.2 认证相关 API

```
POST /internal/bootstrap-code    ← 脚本调用，需 Authorization: Bearer {launch_token}
  → 返回一次性 bootstrap_code (60 秒有效)

GET  /bootstrap?code=xxx         ← 浏览器首次打开
  → 校验 code → 设置会话 Cookie → 302 跳转到目标页面

GET  /api/hub/identity           ← 无需认证，仅返回 {"service":"code880_hub","version":"x.x"}
  → 用于脚本判断 Hub 是否在运行（不暴露敏感信息）

其他所有 /api/* 和 /ws/*        ← 必须携带有效会话 Cookie
```

---

## 五、Worker 安全隔离

> **v2→v3 修订 [问题6]**：v2 表述"仅 Hub 可达 Worker"，但 Worker 绑定本机端口后，本机任意进程都能访问。

### 5.1 Worker 内部 token 机制

```python
# Hub 启动 Worker 时生成专属 token
import secrets
worker_token = secrets.token_hex(32)

# 通过命令行参数传给 Worker
subprocess.Popen([python路径, worker脚本,
    "--port", str(内部端口),
    "--internal-token", worker_token,
    "--project-root", 项目路径
])

# Worker 拒绝所有不带正确 token 的请求
@app.middleware("http")
async def 校验内部token(request, call_next):
    if request.headers.get("X-Worker-Token") != 预期token:
        return JSONResponse(status_code=403, content={"error": "forbidden"})
    return await call_next(request)

# Hub 代理时注入 token
async def 代理到Worker(workspace_id, request):
    worker = 查找Worker(workspace_id)
    headers = dict(request.headers)
    headers["X-Worker-Token"] = worker.internal_token  # Hub 注入
    return await httpx.request(
        method=request.method,
        url=f"http://127.0.0.1:{worker.port}{request.url.path}",
        headers=headers,
        content=await request.body()
    )
```

### 5.2 增强方案（后期可选）

```
更强隔离方案（正式版后期）:
  方案 A: Worker 使用 Windows Named Pipe 代替 TCP 端口
    → 管道名随机生成，只有创建者可连接
    → 彻底消除端口可达性问题
  
  方案 B: Hub 进程内以子线程调度 Worker（不开独立端口）
    → Worker 逻辑作为 Hub 的子模块运行
    → 简单但牺牲进程隔离
```

---

## 六、路径安全（修复前缀绕过）

> **v2→v3 修订 [问题5]**：v2 使用 `startswith` 判断目录边界，`C:\proj2` 会被误判为 `C:\proj` 内部。

### 6.1 修复后的路径校验

```python
import os

def 校验路径安全(项目根: str, 请求相对路径: str) -> bool:
    """
    防止路径穿越攻击 — 修复前缀绕过问题
    
    v2 问题: "C:\\proj2".startswith("C:\\proj") == True
    v3 修复: 使用 os.path.commonpath 做严格边界判断
    """
    # 1. 规范化项目根目录（解析符号链接、junction）
    规范根 = os.path.normcase(os.path.realpath(项目根))
    
    # 2. 确保根目录以分隔符结尾（防止前缀攻击）
    if not 规范根.endswith(os.sep):
        规范根 += os.sep
    
    # 3. 拼接并规范化目标路径
    目标绝对 = os.path.normcase(os.path.realpath(
        os.path.join(项目根, 请求相对路径)
    ))
    
    # 4. 使用 commonpath 做严格判断
    try:
        公共路径 = os.path.commonpath([规范根.rstrip(os.sep), 目标绝对])
        if os.path.normcase(公共路径) != 规范根.rstrip(os.sep):
            return False
    except ValueError:
        # 不同盘符 (如 C: vs D:)
        return False
    
    # 5. 拒绝 UNC 路径（除非明确配置允许）
    if 目标绝对.startswith('\\\\'):
        return False
    
    # 6. 检测是否为符号链接指向外部
    if os.path.islink(os.path.join(项目根, 请求相对路径)):
        链接目标 = os.path.realpath(os.path.join(项目根, 请求相对路径))
        链接目标规范 = os.path.normcase(链接目标)
        if not 链接目标规范.startswith(规范根):
            return False
    
    return True

# 测试用例:
# 校验路径安全("C:\\proj", "..\\secret")     → False (穿越)
# 校验路径安全("C:\\proj", "src\\main.py")   → True
# 校验路径安全("C:\\proj", "..\\proj2\\a")   → False (前缀绕过)
# 校验路径安全("C:\\proj", "D:\\other")       → False (跨盘)
```

---

## 七、启动脚本（修复路径转义 + 进程脱离）

> **v2→v3 修订 [问题3]**：v2 把 `%CD%` 直接嵌入 Python 字符串，`C:\Users\...` 中的 `\U` 会触发 Unicode escape；中文路径也容易出错。
>
> **v2→v3 修订 [问题4]**：v2 使用 `start /B` 启动 Hub，但关闭 CMD 窗口时子进程也会被终止。

### 7.1 项目内启动脚本（修复版）

```batch
:: {项目根目录}\启动Web工作台.bat
@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Code880 Web 工作台

echo.
echo   Code880 Web 工作台 启动中...
echo.

:: 1. 检查虚拟环境 (仅用于确认一键安装已完成)
if not exist ".venv\Scripts\python.exe" (
    echo   [!] 未检测到 Python 环境
    echo   [!] 请先运行 "一键安装.exe" 和 "重新初始化.bat"
    pause
    exit /b 1
)

:: 2. 定位全局 Hub
set "HUB_APP=C:\PythonDev\code880web\hub\app.py"
set "HUB_PYTHON=C:\PythonDev\Python312\python.exe"
set "HUB_RUNTIME=%LOCALAPPDATA%\Code880Web\hub_runtime.json"

if not exist "%HUB_APP%" (
    echo   [!] 未找到 Web 工作台组件
    echo   [!] 请更新一键安装包以获取 Web 功能
    pause
    exit /b 1
)

:: 3. 用 PowerShell 完成后续操作 (避免 batch 路径转义问题)
:: [问题3 修复] 不在 batch 中拼接 JSON/Python 字符串
:: [问题4 修复] 使用 Start-Process -WindowStyle Hidden 真正脱离控制台
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "& '%~dp0启动Web工作台.ps1' -ProjectRoot '%~dp0'"

if %errorlevel% neq 0 (
    echo   [!] 启动失败，请查看日志
    pause
    exit /b 1
)
```

### 7.2 PowerShell 启动脚本（核心逻辑）

```powershell
# {项目根目录}\启动Web工作台.ps1
param(
    [string]$ProjectRoot = (Get-Location).Path
)

$ErrorActionPreference = 'Stop'
$HubApp     = 'C:\PythonDev\code880web\hub\app.py'
$HubPython  = 'C:\PythonDev\Python312\python.exe'
$RuntimeFile = "$env:LOCALAPPDATA\Code880Web\hub_runtime.json"
$TokenFile   = "$env:LOCALAPPDATA\Code880Web\keys\launch_token"
$HubPort     = 8800

# === 确保全局数据目录存在 ===
$globalDir = "$env:LOCALAPPDATA\Code880Web\keys"
if (-not (Test-Path $globalDir)) { New-Item -ItemType Directory -Path $globalDir -Force | Out-Null }

# === 检查 Hub 是否已运行 ===
$hubAlive = $false
try {
    $resp = Invoke-WebRequest "http://127.0.0.1:$HubPort/api/hub/identity" -TimeoutSec 2 -UseBasicParsing
    if ($resp.StatusCode -eq 200) { $hubAlive = $true }
} catch { }

if (-not $hubAlive) {
    Write-Host '  [i] 正在启动项目管理中心...'
    
    # [问题4 修复] 使用 Start-Process -WindowStyle Hidden 真正脱离控制台
    # Hub 作为独立进程运行，关闭本窗口不影响服务
    Start-Process -FilePath $HubPython -ArgumentList "`"$HubApp`"" `
        -WindowStyle Hidden -PassThru | Out-Null
    
    # 等待 Hub 就绪 (最多 10 秒)
    $ready = $false
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Milliseconds 500
        try {
            $r = Invoke-WebRequest "http://127.0.0.1:$HubPort/api/hub/identity" -TimeoutSec 1 -UseBasicParsing
            if ($r.StatusCode -eq 200) { $ready = $true; break }
        } catch { }
    }
    if (-not $ready) {
        Write-Host '  [!] Hub 启动超时'; exit 1
    }
}

# === 读取 launch_token ===
if (-not (Test-Path $TokenFile)) {
    Write-Host '  [!] 认证文件不存在，Hub 可能未正常启动'; exit 1
}
$launchToken = (Get-Content $TokenFile -Raw).Trim()

# === [问题3 修复] 注册项目 — 用 PowerShell 原生对象序列化，避免路径转义 ===
$body = @{ root_path = $ProjectRoot } | ConvertTo-Json -Compress
$headers = @{ 'Authorization' = "Bearer $launchToken"; 'Content-Type' = 'application/json' }

try {
    $regResp = Invoke-RestMethod -Method POST -Uri "http://127.0.0.1:$HubPort/internal/projects/register" `
        -Body $body -Headers $headers -TimeoutSec 5
    $workspaceId = $regResp.workspace_id
} catch {
    Write-Host "  [!] 项目注册失败: $_"; exit 1
}

# === [问题2 修复] 获取一次性 bootstrap code，带认证打开浏览器 ===
try {
    $codeResp = Invoke-RestMethod -Method POST -Uri "http://127.0.0.1:$HubPort/internal/bootstrap-code" `
        -Body (@{ target = "/w/$workspaceId" } | ConvertTo-Json -Compress) `
        -Headers $headers -ContentType 'application/json' -TimeoutSec 5
    $bootstrapUrl = "http://127.0.0.1:$HubPort/bootstrap?code=$($codeResp.code)"
} catch {
    # 降级: 直接打开首页 (需要用户手动操作)
    $bootstrapUrl = "http://127.0.0.1:$HubPort"
}

# === 打开浏览器 ===
Start-Process $bootstrapUrl
Write-Host "  [OK] 启动完成！浏览器中操作即可。"
```

### 7.3 启动认证完整闭环图

```
bat 双击
  │
  └→ ps1 脚本
       │
       ├→ Hub 未运行? → Start-Process -WindowStyle Hidden 启动 Hub
       │                  Hub 启动时生成 launch_token 写入本机文件
       │
       ├→ 从本机文件读取 launch_token
       │
       ├→ POST /internal/projects/register
       │     Header: Authorization: Bearer {launch_token}
       │     Body: {"root_path": "实际路径"}     ← PowerShell 原生序列化
       │     Response: {"workspace_id": "xxx"}
       │
       ├→ POST /internal/bootstrap-code
       │     Header: Authorization: Bearer {launch_token}
       │     Body: {"target": "/w/xxx"}
       │     Response: {"code": "一次性code"}
       │
       └→ 打开浏览器: http://127.0.0.1:8800/bootstrap?code=yyy
             │
             └→ Hub 校验 code (60秒有效, 一次性)
                  → 设置 HttpOnly SameSite=Strict Cookie
                  → 302 跳转到 /w/xxx
                  → 后续请求走 Cookie + CSRF
```

---

## 八、Office 文件预览（能力标注修正）

> **v2→v3 修订 [问题7]**：v2 的预览策略表暗示 mammoth/python-pptx 能"按 Word/PPT 相应格式展示"，实际上 mammoth 只能提取基本段落/表格结构，python-pptx 无法真正渲染幻灯片。v3 明确标注各方案的保真度级别。

### 8.1 预览策略（保真度分级）

| 文件类型 | 方案 | 保真度 | 说明 |
|---------|------|:------:|------|
| `.py` `.js` `.json` `.toml` `.bat` `.ps1` `.csv` `.log` | Monaco Editor 只读 | ★★★★★ | 完美，代码高亮 + 行号 |
| `.md` | markdown-it + highlight.js | ★★★★★ | 完美 |
| `.txt` | 等宽文本 `<pre>` | ★★★★★ | 完美 |
| `.pdf` | PDF.js 前端渲染 | ★★★★★ | 完美，翻页/缩放/搜索 |
| 图片 | 前端 `<img>` | ★★★★★ | 完美 |
| `.xlsx` | openpyxl → JSON → 前端表格 | ★★★★☆ | 数据和基础格式准确，复杂图表/条件格式受限 |
| `.docx` | mammoth → HTML | ★★★☆☆ | **段落/表格/列表可还原，复杂排版/页眉页脚/图文混排会丢失** |
| `.pptx` | python-pptx 提取文本+图片 | ★★☆☆☆ | **只能提取内容，不等于幻灯片原始排版渲染** |
| `.doc` `.xls` `.ppt` (旧格式) | 提示"请转为新格式" | ☆☆☆☆☆ | 不支持旧二进制格式 |

### 8.2 增强预览方案（可选，不影响第一版）

```
当基础预览保真度不足时的增强路径:

增强方案 A（推荐）: LibreOffice Portable headless
  → 用户首次需要下载 LibreOffice 便携版 (~300MB)
  → 调用 soffice --headless --convert-to pdf xxx.docx
  → 转换后用 PDF.js 展示，保真度接近 ★★★★★
  → 可设计为"需要高清预览？点击下载增强组件"

增强方案 B: 检测本机 Office/WPS
  → 如果用户电脑已安装 MS Office 或 WPS
  → 通过 COM 接口调用转 PDF
  → 零额外下载，但依赖用户环境

增强方案 C: 在线转换 API（需网络）
  → 调用第三方转换 API
  → 适合对安全要求不高的场景

第一版策略:
  → 默认使用 mammoth/openpyxl/python-pptx (基础预览)
  → 对 Word/PPT 同时提供"提取文本"按钮作为保底
  → 在 UI 上标注: "当前为轻量预览，复杂格式请用 Office 打开"
  → 后续版本提供 LibreOffice 增强组件下载
```

---

## 九、Worker 服务设计

### 9.1 Worker 核心职责

```
Worker (FastAPI, 内部动态端口, 需 X-Worker-Token 校验):
    ├─ 文件树: 递归读取项目根目录, 懒加载, 默认隐藏系统目录
    ├─ 文件读写: 文本读取 + 保存(sha256版本校验) + 自动备份
    ├─ 文件预览:
    │     ├─ PDF: 返回原始字节流 → 前端 PDF.js
    │     ├─ Word: mammoth → HTML (标注: 轻量预览)
    │     ├─ Excel: openpyxl → JSON 表格 (分页)
    │     ├─ PPT: python-pptx → 文本+图片提取 (标注: 内容提取)
    │     └─ 图片: 直接返回
    ├─ AI 上下文引擎
    ├─ AI 对话代理: 调用全局模型 → SSE 流式输出
    ├─ 任务执行: Python 运行 / uv sync / 打包
    ├─ 文件监听: watchdog 节流
    ├─ 文件写入锁
    └─ 审计日志
```

### 9.2 Worker 进程启动（修复版）

```python
import subprocess
import secrets
import sys

def 启动Worker(项目路径: str, 内部端口: int) -> dict:
    """启动 Worker 为独立进程，注入内部 token"""
    
    # 全局 Worker 脚本位置
    worker脚本 = r"C:\PythonDev\code880web\worker\app.py"
    hub_python = r"C:\PythonDev\Python312\python.exe"
    
    # 生成 Worker 专属 token
    worker_token = secrets.token_hex(32)
    
    # [问题4 修复] 使用 CREATE_NEW_PROCESS_GROUP + CREATE_NO_WINDOW
    # 使 Worker 不依赖 Hub 的控制台窗口
    进程 = subprocess.Popen(
        [hub_python, worker脚本,
         "--port", str(内部端口),
         "--internal-token", worker_token,
         "--project-root", 项目路径],
        cwd=项目路径,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=(
            subprocess.CREATE_NO_WINDOW |
            subprocess.CREATE_NEW_PROCESS_GROUP
        )
    )
    
    return {
        "pid": 进程.pid,
        "port": 内部端口,
        "token": worker_token,
        "process": 进程
    }
```

---

## 十、URL 路由与 API 设计

### 10.1 前端页面路由

```
/                          → 项目管理控制台
/w/{workspace_id}          → 项目工作台 (三栏布局)
/bootstrap?code=xxx        → 认证入口 (一次性)
/settings                  → 全局设置
/help                      → 使用帮助
```

### 10.2 内部 API（仅脚本/Hub 内部调用，需 launch_token）

```
GET  /api/hub/identity               ← 无需认证，身份确认
POST /internal/projects/register     ← 需 Bearer launch_token
POST /internal/bootstrap-code        ← 需 Bearer launch_token
```

### 10.3 Hub API（需浏览器会话 Cookie）

| 方法 | 路径 | 用途 |
|------|------|------|
| `GET` | `/api/hub/projects` | 已注册项目列表 + 运行状态 |
| `DELETE` | `/api/hub/projects/{id}` | 移除项目注册 |
| `POST` | `/api/hub/projects/{id}/start` | 启动 Worker |
| `POST` | `/api/hub/projects/{id}/stop` | 停止 Worker |
| `POST` | `/api/hub/projects/{id}/restart` | 重启 Worker |
| `GET` | `/api/hub/status` | 全局资源统计 |
| `GET` | `/api/hub/models` | 全局 AI 模型列表 |
| `POST` | `/api/hub/models` | 新增/更新模型 |
| `POST` | `/api/hub/models/{id}/test` | 测试模型连通性 |

### 10.4 Workspace API（Hub 反向代理到 Worker）

| 方法 | 路径 | 用途 |
|------|------|------|
| `GET` | `/api/workspaces/{id}/info` | 项目状态 |
| `GET` | `/api/workspaces/{id}/files/tree` | 文件树 |
| `GET` | `/api/workspaces/{id}/files/content?path=` | 读取文件 (含 sha256) |
| `POST` | `/api/workspaces/{id}/files/save` | 保存 (带 base_sha256) |
| `GET` | `/api/workspaces/{id}/files/search?q=` | 搜索 |
| `GET` | `/api/workspaces/{id}/preview/*` | 文件预览 |
| `POST` | `/api/workspaces/{id}/ai/chat` | AI 对话 (SSE) |
| `GET/POST` | `/api/workspaces/{id}/ai/context/*` | 上下文管理 |
| `POST` | `/api/workspaces/{id}/tasks/run` | 运行任务 |
| `GET` | `/api/workspaces/{id}/tasks/{tid}` | 任务状态/日志 |

### 10.5 WebSocket

```
/ws/workspaces/{workspace_id}
  → 连接时校验会话 Cookie
  → 推送: file_changed, task_output, ai_stream, worker_status
```

---

## 十一、安全设计

### 11.1 多层防护

```
第 1 层: CORS — 不使用通配 *, 只允许 http://127.0.0.1:{hub_port}
第 2 层: Cookie — HttpOnly + SameSite=Strict, 恶意网页无法读取
第 3 层: CSRF — 写操作必须携带 X-Code880-CSRF 自定义头
第 4 层: Origin — 校验 Origin 头必须为本机
第 5 层: 路径 — commonpath 严格校验 (见第六章修复)
第 6 层: Worker — 内部 token 隔离 (见第五章修复)
第 7 层: 命令 — AI/用户只能执行白名单任务类型
```

### 11.2 API Key 管理

```
存储: %LOCALAPPDATA%\Code880Web\keys\api_keys.enc
加密: Windows DPAPI (CryptProtectData) 或 keyring
前端: 只显示 sk-****abcd
日志: Key 永远不写入日志
传输: 仅后端内存解密，直接调用 AI API
```

---

## 十二、目录结构（最终版 v3）

```
=== 全局安装 (由一键安装部署到 C:\PythonDev\) ===

C:\PythonDev\
├── Python312\                    ← Python 解释器
├── code880web\                   ← Web 工作台 (全局唯一)
│   ├── hub\                     ← Hub 服务代码
│   │   ├── app.py              ← FastAPI Hub 入口
│   │   ├── config.py           ← 配置管理
│   │   ├── registry.py         ← 项目注册表
│   │   ├── supervisor.py       ← Worker 生命周期
│   │   ├── proxy.py            ← 反向代理 (注入 Worker token)
│   │   ├── auth.py             ← 认证/CSRF/Token
│   │   └── models_manager.py   ← AI 模型全局配置
│   ├── worker\                  ← Worker 服务代码
│   │   ├── app.py              ← FastAPI Worker 入口
│   │   └── services\
│   │       ├── file_service.py
│   │       ├── preview_service.py
│   │       ├── ai_service.py
│   │       ├── task_runner.py
│   │       ├── watcher.py
│   │       └── security.py     ← 路径校验 (commonpath)
│   ├── static\                  ← 前端打包产物
│   │   └── index.html
│   └── requirements.txt
└── 启动项目管理中心.bat           ← 全局入口

=== 全局运行时数据 ===

%LOCALAPPDATA%\Code880Web\
├── hub.db                       ← 项目注册表
├── hub_runtime.json             ← Hub PID/端口
├── models.json                  ← AI 模型配置
├── keys\
│   ├── launch_token             ← 启动认证 token
│   └── api_keys.enc             ← 加密 API Key
└── logs\
    └── hub.log

=== 项目内 (每个项目模板) ===

{项目根目录}\
├── 启动Web工作台.bat              ← 启动脚本 (调用全局 Hub)
├── 启动Web工作台.ps1              ← PowerShell 核心逻辑
├── .web-workbench\               ← Worker 运行时 (自动生成)
│   ├── workspace.json
│   ├── state.json
│   ├── chat_history\
│   ├── backups\
│   ├── preview-cache\
│   └── worker.log
├── src\                          ← 原有: 不动
├── __hy127\                      ← 原有: 不动
├── .vscode\                      ← 原有: 不动
├── .venv\                        ← 原有: 不动
└── 重新初始化 V1.24.bat           ← 原有: 不动
```

---

## 十三、分阶段实施（MVP / 正式版分离）

### MVP 阶段（约 2 周）

```
目标: 单 Hub + 单进程多协程 + 核心功能跑通
  → 可用于演示和 UI 验证
  → 不进入正式多项目稳定版验收

功能:
  ✅ Hub 主进程 + 前端静态托管
  ✅ 单项目文件树 + 文本/代码查看 (Monaco)
  ✅ PDF 预览 (PDF.js)
  ✅ Excel 基础表格预览 (openpyxl → JSON)
  ✅ Word 轻量预览 (mammoth → HTML, 标注保真度)
  ✅ AI 模型配置 + 对话 (SSE 流式)
  ✅ 上下文选择 (勾选文件)
  ✅ 启动Web工作台.bat 一键启动
  ✅ Hub 基础认证 (launch_token + 会话)
  
  ⏳ 多项目注册 (页面有入口，但同一进程内服务)
  ⏳ 任务执行 (运行 Python 文件)

暂不实现:
  ❌ Worker 独立进程
  ❌ Worker 内部 token
  ❌ 文件版本校验/写入锁
  ❌ 文件监听 watchdog
  ❌ 休眠/唤醒
```

### 正式稳定版（MVP 后约 3 周）

```
目标: 真正的多项目并行 + 进程隔离 + 安全闭环

功能:
  ✅ Worker 独立进程 (subprocess + CREATE_NEW_PROCESS_GROUP)
  ✅ Worker 内部 token 校验
  ✅ Hub → Worker 反向代理
  ✅ 文件保存 sha256 版本校验
  ✅ 文件写入锁
  ✅ 完整认证闭环 (bootstrap code → Cookie → CSRF)
  ✅ 路径安全 commonpath 校验
  ✅ Hub 健康监测 + Worker 自动重启
  ✅ 任务队列 (读/预览/AI/写/命令 分级)
  ✅ 文件监听 watchdog + 节流
  ✅ Worker 空闲休眠/唤醒
  ✅ AI 工具调用 (read_file, generate_patch)
  ✅ AI 修改 diff 预览 + 确认 + 备份
  ✅ 审计日志

验收标准:
  ✅ 同时打开 3 个项目, 各自独立运行
  ✅ 杀掉 Worker A, 项目 B/C 无影响
  ✅ 恶意网页无法调用任何写 API
  ✅ 多标签保存同文件不会静默覆盖
  ✅ 30 分钟无人用 Worker 自动休眠
```

### 后续增强（按需）

```
  ⬜ LibreOffice Portable 高保真预览
  ⬜ xterm.js 终端输出
  ⬜ 代码编辑 (Monaco 读写模式)
  ⬜ 打包为 Web工作台.exe
  ⬜ 首次使用向导
  ⬜ 主题切换 (明/暗)
```

---

## 十四、v2→v3 修订清单

| # | v2 问题 | v3 修复 | 章节 |
|---|--------|--------|------|
| 1 | 进程级隔离原则与 MVP 单进程冲突 | 原则分层：全版本原则 vs 正式版原则 | 第一章 |
| 2 | 启动认证与启动脚本没有闭环 | 脚本读取 token → 注册项目 → 获取 bootstrap code → 带 code 打开浏览器 | 第四章 + 第七章 |
| 3 | Batch `%CD%` 路径 Unicode escape | 改用 PowerShell `ConvertTo-Json` 原生序列化 | 第七章 |
| 4 | `start /B` 关窗即杀进程 | 改用 `Start-Process -WindowStyle Hidden` + `CREATE_NEW_PROCESS_GROUP` | 第七章 + 第九章 |
| 5 | 路径 `startswith` 前缀绕过 | 改用 `os.path.commonpath` + 尾部分隔符 + 符号链接检测 | 第六章 |
| 6 | Worker 端口本机任意进程可达 | Worker 内部 token 机制，Hub 代理注入，Worker 拒绝裸请求 | 第五章 |
| 7 | Office 预览保真度被高估 | 标注 ★ 评级，明确基础方案局限，列出增强路径 | 第八章 |
| 8 | Hub 代码在项目内 vs 全局位置矛盾 | Hub/Worker 代码全局唯一安装在 `C:\PythonDev\code880web\`，项目内只保留启动脚本 | 第三章 + 第十二章 |

---

## 十五、总结

### 一句话架构

> 全局唯一 Hub (port 8800) 反向代理到每项目独立 Worker (内部 token 隔离)，浏览器通过一次性 bootstrap code 建立安全会话，路径路由 `/w/{id}` 区分项目。

### 与 v2 的核心区别

- v2 是"理想态设计"，v3 是"可落地的开发基准"
- v3 的每一个安全环节都有完整闭环，不存在"设计了但脚本没实现"的断点
- v3 明确区分 MVP 和正式版，避免"原则不可妥协但实现又妥协"的矛盾
- v3 的目录结构消除了"Hub 在项目内还是全局"的歧义

---

> 文档版本：v3.0 | 创建日期：2026-04-28
> 修订基础：v2 + 8 项复核修订
