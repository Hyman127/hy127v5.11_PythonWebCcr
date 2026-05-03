# Code880 Web 工作台 — 最终整合方案 v4.4

> **本文是唯一完整开发基准**，合并了 v3（主架构）+ v3.1（7 项修复）+ 点击运行三方案 + v4 复核 6 项修正 + v4.2 复核 5 项修正 + v4.3 落地复核修正 + v4.4 启动验证修正。无需再交叉查阅其他文档。
>
> 生成时间：2026-04-30
> 基于版本：v4.3 + 启动入口验证修正

---

## 一、设计原则（分层）

### 1.1 全版本不可妥协原则

| # | 原则 | 说明 |
|---|------|------|
| 1 | **VSCode 不必启动** | 后端直接服务项目目录，不依赖任何 VSCode 进程 |
| 2 | **浏览器即入口** | 双击 bat → 自动打开浏览器，非 IT 用户零学习成本 |
| 3 | **仅监听 127.0.0.1** | 本地服务不暴露网络，安全边界清晰 |
| 4 | **新增不破坏** | 所有 Web 代码放全局 `code880web/` 目录，原项目文件保持不变 |
| 5 | **一个固定 URL 入口** | 用户只看到 `http://127.0.0.1:{port}`，不理解端口 |

### 1.2 正式稳定版原则（MVP 阶段目标达成但不强制验收）

| # | 原则 | 说明 |
|---|------|------|
| 6 | **多项目=多标签页** | 同一浏览器同时打开多个项目，与其他网页共存互不干扰 |
| 7 | **进程级隔离** | 每个项目独立 Worker 进程，一个崩溃不拖垮其他项目 |
| 8 | **认证闭环** | 启动 token → 会话 → CSRF 完整链路，恶意网页不可越权 |
| 9 | **文件版本校验** | 多标签/多进程写入同一文件时不会静默覆盖 |

> MVP 可用单进程多协程验证 UI 和功能流程，但不进入正式多项目稳定版验收。正式版必须 Worker 独立进程。

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
           │ 全部走 127.0.0.1:{Hub端口}              │
           ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│          Hub 主进程 (端口自动探测, 全局唯一安装)                            │
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
| Worker 通信方式 | Hub 反向代理 + **Worker 内部 token** | 防止本机其他进程直连 Worker |
| 浏览器存储隔离 | `code880:{workspace_id}:key` 命名空间 | 同源策略下多项目数据不互相污染 |
| AI 配置 | 全局模型 + 项目级上下文 | API Key 只配一次，上下文按项目独立 |
| Hub 代码归属 | **全局唯一安装** | 所有项目共用同一版本，升级只需更新一处 |
| MVP Worker 模式 | 单进程多协程，UI 验证用 | 正式版必须多进程 |
| Python 文件运行 | **Worker 内 TaskRunner** | 职责最清晰：Hub 管项目，Worker 跑代码 |

---

## 三、Hub 主服务设计

### 3.1 Hub 核心职责

```
Hub 主服务 (FastAPI, 端口自动探测, bind=127.0.0.1):
    ├─ 托管前端静态文件 (Vue 打包后的 dist/)
    ├─ 项目注册表 CRUD
    ├─ Worker 生命周期管理 (start/stop/restart/health)
    ├─ 反向代理: /api/workspaces/{id}/* → Worker 内部端口
    │     └─ 代理时注入 X-Worker-Token 头
    ├─ WebSocket 代理: /ws/workspaces/{id}/* → Worker WS
    ├─ 全局 AI 模型配置管理
    ├─ API Key 加密存储 (Windows DPAPI / keyring)
    ├─ AI Relay: Worker 调 Hub 内部接口，由 Hub 注入解密后的 API Key
    ├─ 安全认证: 启动 token → 会话 Cookie → CSRF
    ├─ Hub 健康监测循环
    └─ 全局日志
```

### 3.2 Hub 全局唯一安装位置

```
Hub = 全局安装，只有一份
  位置: {install_root}\code880web\
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

### 3.3 Hub 端口自动探测与 runtime 文件

```python
# Hub app.py 启动逻辑
import json, os, socket, secrets
from datetime import datetime

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
global_dir = os.path.join(os.environ["LOCALAPPDATA"], "Code880Web")

# [v4.1 修复问题3] 生成 launch_token 并写入文件（启动脚本依赖此文件）
keys_dir = os.path.join(global_dir, "keys")
os.makedirs(keys_dir, exist_ok=True)

launch_token = secrets.token_hex(32)
token_path = os.path.join(keys_dir, "launch_token")
with open(token_path, "w", encoding="utf-8") as f:
    f.write(launch_token)

# 内存中保存，用于校验 /internal/* API
LAUNCH_TOKEN = launch_token

# [v4.3 修正] main() 只探测一次端口，lifespan/启动逻辑禁止二次探测；
# runtime 文件必须在 token 写入后落盘，避免脚本读到 runtime 却读不到 token。
runtime_path = os.path.join(global_dir, "hub_runtime.json")
os.makedirs(os.path.dirname(runtime_path), exist_ok=True)

with open(runtime_path, "w", encoding="utf-8") as f:
    json.dump({
        "pid": os.getpid(),
        "port": 实际端口,
        "base_url": f"http://127.0.0.1:{实际端口}",
        "launch_token_path": token_path,
        "started_at": datetime.now().isoformat(),
        "version": "1.0.0"
    }, f, ensure_ascii=False, indent=2)

# 然后启动 uvicorn
uvicorn.run(app, host="127.0.0.1", port=实际端口)
```

> **启动时序硬约束**：`实际端口` 只能由一个入口函数决定；生成 `launch_token` 并写入 `keys/launch_token` 之后，才允许写入 `hub_runtime.json`。启动脚本看到 runtime 文件时，必须已经能读取 token 文件。

### 3.4 安装路径发现机制 (install.json)

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

一键安装器职责与写入时机：

1. 部署 Python/uv/VSCode 基础环境。
2. 将安装包内的 `code880web/` 复制到 `{install_root}\code880web\`。
3. 执行 `{python_path} -m pip install -r {install_root}\code880web\requirements.txt`。
4. 可选执行 `python {install_root}\code880web\download_vendor.py` 下载前端本地 vendor 资源；若未下载，前端可降级使用 CDN，但正式离线包必须包含 vendor。
5. 上述步骤全部成功后，写入 `%LOCALAPPDATA%\Code880Web\install.json`。

```python
# 一键安装卸载.py — 安装成功后追加写入
import json, os
from datetime import datetime

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

---

## 四、认证设计（闭环）

### 4.1 完整认证流程

```
1. Hub 启动时
   → 生成随机 launch_token (32 字节 hex)
   → 写入 %LOCALAPPDATA%\Code880Web\keys\launch_token
   → 生成随机 internal_secret (用于内部 API 签名)

2. 启动脚本 (bat/ps1) 注册项目时
   → 从本机文件读取 launch_token
   → 调用 POST /internal/projects/register 时携带 Authorization: Bearer {launch_token}
   → 这是 internal API，只有本机脚本能读到 token 文件

3. 启动脚本打开浏览器时
   → 生成一次性 bootstrap_code (Hub 提供 API)
   → 打开 http://127.0.0.1:{端口}/bootstrap?code={bootstrap_code}
   → Hub 校验 code → 设置双 Cookie (见 4.2) → 跳转到 /w/{workspace_id}

4. 后续浏览器请求
   → Cookie 中的 code880_session → 验证会话有效性
   → 写操作额外要求 X-Code880-CSRF 头 (值从 code880_csrf Cookie 读取)
   → 读操作也要求 Cookie 有效（防止恶意网页 GET 读取）

5. Worker 内部通信
   → Hub 代理转发时注入 X-Worker-Token: {worker专属token}
   → Worker 校验该 token，拒绝所有不带 token 的直接请求
```

### 4.2 双 Cookie 认证机制

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
```

### 4.3 后端 CSRF 校验代码

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

    # 3. Origin 校验：必须精确匹配当前 Hub 端口
    origin = request.headers.get("Origin")
    expected_origin = f"http://127.0.0.1:{hub_port}"
    if origin and origin != expected_origin:
        raise HTTPException(403, "来源不合法")
```

> **v4.3 安全口径**：不能使用 `startswith("http://127.0.0.1:")`。Cookie 不按端口隔离，恶意本机页面可能运行在另一个 127.0.0.1 端口，因此 HTTP 写操作、WebSocket 握手和 CORS 预检都必须精确匹配当前 Hub 的实际端口。

### 4.4 前端 CSRF 使用方式

```javascript
const csrfToken = document.cookie
    .split('; ')
    .find(c => c.startsWith('code880_csrf='))
    ?.split('=')[1];

fetch('/api/workspaces/xxx/files/save', {
    method: 'POST',
    headers: {
        'X-Code880-CSRF': csrfToken,
        'Content-Type': 'application/json'
    },
    credentials: 'same-origin',
    body: JSON.stringify(data)
});
```

### 4.5 认证相关 API

```
POST /internal/bootstrap-code    ← 脚本调用，需 Authorization: Bearer {launch_token}
  → 返回一次性 bootstrap_code (60 秒有效)

POST /internal/ai/relay          ← Worker 调用，需 X-Worker-Token
  → Hub 校验 Worker token → 读取已启用模型 → 解密 API Key → 流式代理到模型供应商

GET  /bootstrap?code=xxx         ← 浏览器首次打开
  → 校验 code → 设置双 Cookie → 302 跳转到目标页面

GET  /api/hub/identity           ← 无需认证，仅返回 {"service":"code880_hub","version":"x.x"}
  → 用于脚本判断 Hub 是否在运行（不暴露敏感信息）

其他所有 /api/* 和 /ws/*        ← 必须携带有效会话 Cookie
```

---

## 五、Worker 安全隔离

### 5.1 Worker 内部 token 机制（临时文件传递）

```python
import secrets, os, stat, subprocess

def 启动Worker(项目路径: str, 内部端口: int) -> dict:
    install_info = 读取安装信息()
    worker脚本 = install_info["worker_app_path"]
    安装根目录 = install_info["install_root"]
    hub_python = install_info["python_path"]

    # 生成 Worker 专属 token
    worker_token = secrets.token_hex(32)

    # 写入临时文件传递 token，而非命令行参数（防 WMI 可见）
    token_dir = os.path.join(
        os.environ["LOCALAPPDATA"], "Code880Web", "worker_tokens"
    )
    os.makedirs(token_dir, exist_ok=True)

    token_file = os.path.join(token_dir, f"worker_{内部端口}.token")
    with open(token_file, "w") as f:
        f.write(worker_token)
    os.chmod(token_file, stat.S_IRUSR | stat.S_IWUSR)

    # 日志文件（stdout 直接写文件，避免 PIPE 缓冲区满卡死）
    workbench_dir = os.path.join(项目路径, ".web-workbench")
    os.makedirs(workbench_dir, exist_ok=True)
    log_path = os.path.join(workbench_dir, "worker.log")
    log_file = open(log_path, "a", encoding="utf-8")

    # [v4.3 修正] 命令行不再传 token 文件路径，避免进程列表/WMI 暴露 token 文件位置。
    # token 文件路径通过子进程环境变量传递。
    env = os.environ.copy()
    env["CODE880_WORKER_TOKEN_FILE"] = token_file

    # [v4.4 修正] Worker 使用包内相对导入，必须以 -m 模块方式启动。
    进程 = subprocess.Popen(
        [hub_python, "-m", "code880web.worker.app",
         "--port", str(内部端口),
         "--project-root", 项目路径],
        cwd=安装根目录,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        creationflags=(
            subprocess.CREATE_NO_WINDOW |
            subprocess.CREATE_NEW_PROCESS_GROUP
        ),
        env=env,
    )

    return {
        "pid": 进程.pid,
        "port": 内部端口,
        "token": worker_token,
        "token_file": token_file,
        "process": 进程,
        "log_file_handle": log_file,
        "log_path": log_path
    }
```

### 5.2 Worker 端读取 token

```python
# worker/app.py
import argparse, os

parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, required=True)
parser.add_argument("--project-root", required=True)
args = parser.parse_args()

# 从环境变量指定的文件读取 token，然后立即删除文件（缩小暴露窗口）
token_file = os.environ.get("CODE880_WORKER_TOKEN_FILE")
if not token_file:
    raise RuntimeError("CODE880_WORKER_TOKEN_FILE 未设置")

with open(token_file, "r") as f:
    INTERNAL_TOKEN = f.read().strip()
os.remove(token_file)
```

### 5.3 Worker 请求校验中间件

```python
@app.middleware("http")
async def 校验内部token(request, call_next):
    if request.headers.get("X-Worker-Token") != INTERNAL_TOKEN:
        return JSONResponse(status_code=403, content={"error": "forbidden"})
    return await call_next(request)
```

### 5.4 Hub 代理：路径重写 + 注入 token

```python
import re

# [v4.1 修复问题1] Hub 转发时必须剥离 /api/workspaces/{id} 前缀
# 公开 URL: /api/workspaces/proj_a/run        → Worker 实际: /api/run
# 公开 URL: /api/workspaces/proj_a/files/tree  → Worker 实际: /api/files/tree

def 重写路径(原始路径: str, workspace_id: str) -> str:
    """剥离 /api/workspaces/{id} 前缀，保留 query string"""
    prefix = f"/api/workspaces/{workspace_id}"
    if 原始路径.startswith(prefix):
        剩余 = 原始路径[len(prefix):]
        return f"/api{剩余}" if 剩余 else "/api"
    return 原始路径

## [v4.2 修复问题4] 改用流式代理，支持 SSE/AI 聊天、大文件下载、预览等场景
# 原 httpx.request() 会将 Worker 响应全部读入内存再转发，
# SSE 流（AI 对话）、大文件预览/下载会被缓冲到完成才到前端。

from starlette.responses import StreamingResponse

# 逐跳头不应由代理转发
HOP_BY_HOP = frozenset({
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
})

async def 代理到Worker(workspace_id: str, request: Request):
    worker = 查找Worker(workspace_id)
    headers = dict(request.headers)
    headers["X-Worker-Token"] = worker.internal_token

    # 路径重写: /api/workspaces/{id}/xxx → /api/xxx
    worker_path = 重写路径(request.url.path, workspace_id)
    worker_url = f"http://127.0.0.1:{worker.port}{worker_path}"
    if request.url.query:
        worker_url += f"?{request.url.query}"

    client = httpx.AsyncClient()
    req = client.build_request(
        method=request.method,
        url=worker_url,
        headers=headers,
        content=await request.body(),
    )
    worker_resp = await client.send(req, stream=True)

    # 过滤逐跳头
    resp_headers = {
        k: v for k, v in worker_resp.headers.items()
        if k.lower() not in HOP_BY_HOP
    }

    async def 流式转发():
        try:
            async for chunk in worker_resp.aiter_bytes():
                yield chunk
        finally:
            await worker_resp.aclose()
            await client.aclose()

    return StreamingResponse(
        流式转发(),
        status_code=worker_resp.status_code,
        headers=resp_headers,
    )
```

### 5.4.1 WebSocket 代理：会话校验 + 路径重写 + token 注入 + 安全生命周期

```python
# [v4.1 修复问题1+2] WS 代理需要路径重写和 token 传递
# [v4.2 修复问题1] WS 代理必须在 accept 前校验浏览器会话，否则恶意网页可直连
# [v4.2 修复问题5] 双向转发用 FIRST_COMPLETED 替代 gather，避免一侧关闭后另一侧悬挂
# 公开 WS: /ws/workspaces/proj_a/run/abc123 → Worker WS: /ws/run/abc123

import websockets

def 重写WS路径(原始路径: str, workspace_id: str) -> str:
    prefix = f"/ws/workspaces/{workspace_id}"
    if 原始路径.startswith(prefix):
        剩余 = 原始路径[len(prefix):]
        return f"/ws{剩余}" if 剩余 else "/ws"
    return 原始路径

@app.websocket("/ws/workspaces/{workspace_id}/{path:path}")
async def ws代理(ws_client: WebSocket, workspace_id: str, path: str):
    # [v4.2 修复问题1] 在 accept 之前校验浏览器会话 Cookie + Origin
    # WebSocket 握手是 HTTP Upgrade，Cookie 和 Origin 在握手头中可用
    session_id = ws_client.cookies.get("code880_session")
    if not session_id or not 验证会话(session_id):
        await ws_client.close(code=4001)
        return

    origin = ws_client.headers.get("origin")
    expected_origin = f"http://127.0.0.1:{hub_port}"
    if origin and origin != expected_origin:
        await ws_client.close(code=4003)
        return

    worker = 查找Worker(workspace_id)
    if not worker:
        await ws_client.close(code=4004)
        return

    await ws_client.accept()

    # 连接 Worker WS，携带内部 token
    worker_ws_url = f"ws://127.0.0.1:{worker.port}/ws/{path}"
    extra_headers = {"X-Worker-Token": worker.internal_token}

    try:
        async with websockets.connect(worker_ws_url, extra_headers=extra_headers) as ws_worker:
            # [v4.2 修复问题5] 用 FIRST_COMPLETED 替代 gather
            # gather 的问题: 一侧断开(如浏览器关闭)后另一侧 task 悬挂，
            # 直到超时或 Worker 端也断开才清理，中间可能泄漏资源
            async def 客户端到Worker():
                async for msg in ws_client.iter_text():
                    await ws_worker.send(msg)

            async def Worker到客户端():
                async for msg in ws_worker:
                    await ws_client.send_text(msg)

            task_c2w = asyncio.create_task(客户端到Worker())
            task_w2c = asyncio.create_task(Worker到客户端())

            done, pending = await asyncio.wait(
                {task_c2w, task_w2c},
                return_when=asyncio.FIRST_COMPLETED,
            )
            # 一侧结束 → 取消另一侧 → 关闭两端连接
            for t in pending:
                t.cancel()
            # 收集取消异常，避免 unhandled
            for t in pending:
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass
    except (websockets.exceptions.ConnectionClosed, Exception):
        pass
    finally:
        try:
            await ws_client.close()
        except Exception:
            pass
```

### 5.5 日志轮转

```python
import shutil

def 轮转Worker日志(log_path: str, 最大保留=3):
    if not os.path.exists(log_path):
        return
    if os.path.getsize(log_path) < 10 * 1024 * 1024:  # 小于 10MB 不轮转
        return
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

### 5.6 Worker 停止时清理

```python
def 停止Worker(worker_info: dict):
    worker_info["process"].terminate()
    worker_info["process"].wait(timeout=10)
    worker_info["log_file_handle"].close()
    if os.path.exists(worker_info["token_file"]):
        os.remove(worker_info["token_file"])
```

---

## 六、路径安全

```python
import os
from pathlib import Path

def 校验路径安全(项目根: str, 请求相对路径: str) -> bool:
    """
    完整版路径安全校验
    """
    # === 第 0 层: 输入清理 ===
    if not 请求相对路径 or not 请求相对路径.strip():
        return False

    # 显式拒绝绝对路径
    if os.path.isabs(请求相对路径):
        return False

    # 拒绝包含盘符的变体
    if len(请求相对路径) >= 2 and 请求相对路径[1] == ':':
        return False

    # 拒绝 UNC 路径
    if 请求相对路径.startswith('\\\\') or 请求相对路径.startswith('//'):
        return False

    # === 第 1 层: 规范化 ===
    try:
        根路径 = Path(项目根).resolve(strict=True)
        目标路径 = (根路径 / 请求相对路径).resolve()
    except (OSError, ValueError):
        return False

    # === 第 2 层: 边界判断 ===
    try:
        目标路径.relative_to(根路径)
    except ValueError:
        return False

    # === 第 3 层: 符号链接检测 ===
    实际路径 = Path(项目根) / 请求相对路径
    if 实际路径.exists() and 实际路径.is_symlink():
        链接目标 = 实际路径.resolve()
        try:
            链接目标.relative_to(根路径)
        except ValueError:
            return False

    return True

# 测试用例:
# 校验路径安全("C:\\proj", "src\\main.py")       → True
# 校验路径安全("C:\\proj", "..\\secret")          → False
# 校验路径安全("C:\\proj", "D:\\hack\\file.py")   → False
# 校验路径安全("C:\\proj", "..\\proj2\\a.py")     → False
# 校验路径安全("C:\\proj", "\\\\server\\share")   → False
# 校验路径安全("C:\\proj", "")                    → False
```

---

## 七、启动脚本

### 7.1 启动Web工作台.bat

```batch
@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Code880 Web 工作台

echo.
echo   Code880 Web 工作台 启动中...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0启动Web工作台.ps1" -ProjectRoot "%~dp0"

if %errorlevel% neq 0 (
    echo.
    echo   [!] 启动失败，请查看错误信息
    pause
    exit /b 1
)
```

### 7.2 启动Web工作台.ps1（最终版）

```powershell
param(
    [string]$ProjectRoot = (Get-Location).Path
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = $ProjectRoot.TrimEnd('\')

$GlobalDir    = "$env:LOCALAPPDATA\Code880Web"
$RuntimeFile  = "$GlobalDir\hub_runtime.json"
$InstallFile  = "$GlobalDir\install.json"
$TokenDir     = "$GlobalDir\keys"

# ======================================================
# 1. 发现安装路径 (install.json)
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
$installRoot = $install.install_root
if ([string]::IsNullOrWhiteSpace($installRoot)) {
    $installRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $install.hub_app_path))
}
if (-not (Test-Path $installRoot)) {
    Write-Host "  [!] Web 工作台根目录未找到: $installRoot"
    exit 1
}

# ======================================================
# 2. 检查 Hub 是否已运行 (hub_runtime.json)
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
# 3. Hub 未运行则启动
# ======================================================
if ($null -eq $hubUrl) {
    Write-Host '  [i] 正在启动项目管理中心...'

    Start-Process -FilePath $install.python_path `
        -ArgumentList @("-m", "code880web.hub.app") `
        -WorkingDirectory $installRoot `
        -WindowStyle Hidden -PassThru | Out-Null

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
# 4. 读取 launch_token
# ======================================================
$tokenFile = "$TokenDir\launch_token"
if (-not (Test-Path $tokenFile)) {
    Write-Host '  [!] 认证文件不存在'
    exit 1
}
$launchToken = (Get-Content $tokenFile -Raw).Trim()

# ======================================================
# 5. 注册项目 (PowerShell 原生序列化，避免路径转义)
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
# 6. 获取一次性 bootstrap code 并打开浏览器
# ======================================================
try {
    $codeBody = @{ target = "/w/$workspaceId" } | ConvertTo-Json -Compress
    $codeResp = Invoke-RestMethod -Method POST `
        -Uri "$hubUrl/internal/bootstrap-code" `
        -Body $codeBody -Headers $regHeaders `
        -ContentType 'application/json' -TimeoutSec 5
    $openUrl = "$hubUrl/bootstrap?code=$($codeResp.code)"
} catch {
    $openUrl = $hubUrl
}

Start-Process $openUrl
Write-Host ''
Write-Host '  [OK] 启动完成！请在浏览器中操作。'
Write-Host '  [OK] 关闭此窗口不影响 Web 工作台运行。'
```

### 7.3 启动认证完整闭环图

```
bat 双击
  │
  └→ ps1 脚本
       │
       ├→ 读取 install.json → 发现 Python/Hub 实际安装路径
       │
       ├→ 读取 hub_runtime.json → 发现 Hub 是否在运行及实际端口
       │
       ├→ Hub 未运行? → Start-Process -WindowStyle Hidden 启动 Hub
       │                  Hub 启动时: 探测可用端口 → 生成 launch_token → 写 runtime 文件
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
       └→ 打开浏览器: http://127.0.0.1:{实际端口}/bootstrap?code=yyy
             │
             └→ Hub 校验 code (60秒有效, 一次性)
                  → 设置双 Cookie (session HttpOnly + csrf 可读)
                  → 302 跳转到 /w/xxx
                  → 后续请求走 Cookie + CSRF
```

---

## 八、Office 文件预览

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

| 层级 | 方案 | 何时使用 | 进入安装包 |
|------|------|---------|:---------:|
| 默认 | mammoth + openpyxl + python-pptx | 第一版即有 | 是 |
| 增强 A | LibreOffice Portable headless → 转 PDF | 用户点击"下载增强组件" | 可选下载 |
| 增强 B | 本机 Office/WPS COM → 转 PDF | 自动检测已装 Office | 否 |
| 增强 C | 在线转换 API | 需联网，可配置 | 否 |
| 增强 D | ONLYOFFICE (编辑级) | 需手动装 Docker，仅当需要浏览器内编辑时 | 否 |

第一版策略：
- 默认使用 mammoth/openpyxl/python-pptx (基础预览)
- 对 Word/PPT 同时提供"提取文本"按钮作为保底
- 在 UI 上标注: "当前为轻量预览，复杂格式请用 Office 打开"

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
    ├─ Python 文件运行 (TaskRunner, 见第十章)
    ├─ AI 上下文引擎
    ├─ AI 对话代理: 调用全局模型 → SSE 流式输出
    ├─ 文件监听: watchdog 节流
    ├─ 文件写入锁
    └─ 审计日志
```

---

## 十、Python 文件运行（点击运行）

> 合并自 Claude版 TaskRunner + DeepSeek v1版 Hub/前端 + 截图分析汇总 API/日志/入口发现。

### 10.1 职责划分

```
Hub:
  负责鉴权(CSRF)、反向代理到 Worker
  不参与 Python 执行过程

Worker (TaskRunner):
  负责执行 Python 文件、管理子进程生命周期
  stdout/stderr 通过 WebSocket 实时推送到前端
  每次运行写入日志文件

前端:
  ▶ 运行按钮 / 右键菜单 / 快捷键 → 发起运行请求
  底部终端面板 → 实时显示输出
  stdin 输入框 → WebSocket 发送用户输入
  ⬛ 停止按钮 → 终止运行
```

### 10.2 前端交互入口

```
入口 A：文件树右键菜单
  右键 main.py → "▶ 运行此文件"

入口 B：编辑器工具栏按钮
  打开 .py 文件后，顶部出现 ▶ 按钮

入口 C：快捷键
  Ctrl+F5 / F5（覆盖 VS Code 肌肉记忆）

入口 D：快捷运行下拉
  选择预设配置（"运行当前文件" / "运行 src/main.py"）→ 点击 ▶
```

### 10.3 界面布局

```
┌─────────────────────────────────────────────────────────┐
│ 文件树 │         代码预览 (Monaco)              │ AI 聊天 │
│        │                                       │        │
│        │  ▶ 运行  ⬛ 停止   src/main.py        │        │
│        │                                       │        │
│        ├───────────────────────────────────────┤        │
│        │ 输出 ▾                                │        │
│        │ > python src/main.py                  │        │
│        │ code880 测试                          │        │
│        │ 请输入姓名: [________] ⏎              │        │
│        │                                       │        │
│        │ [进程已结束, 退出码: 0]  耗时: 0.3s    │        │
└─────────────────────────────────────────────────────────┘
```

### 10.4 运行配置 (launch.json)

```json
// .web-workbench/launch.json — 对齐 VSCode launch.json 概念
{
  "version": 1,
  "configurations": [
    {
      "name": "运行当前文件",
      "type": "current_file",
      "description": "运行编辑器中打开的 .py 文件"
    },
    {
      "name": "运行 src/main.py",
      "type": "fixed_file",
      "program": "src/main.py",
      "args": [],
      "cwd": "."
    }
  ]
}
```

与 VSCode launch.json 对照:

| VSCode 配置 | Web 工作台对应 |
|-------------|---------------|
| "Python: 当前文件(终端)" | ▶ 按钮 / 右键"运行此文件" |
| "Python: src/main.py" | 快捷运行下拉预设 |
| "Python: 当前文件(调试)" | **MVP 不实现**，后续可通过 debugpy + DAP 协议扩展 |

### 10.5 Worker 端 TaskRunner 实现

```python
# worker/services/task_runner.py

import subprocess, asyncio, os, uuid, signal, time, json
from pathlib import Path
from datetime import datetime

class TaskRunner:
    MAX_OUTPUT_LINES = 10000
    DEFAULT_TIMEOUT = 300  # 5 分钟
    COMPLETED_TTL = 300    # [v4.2] 已完成任务保留 5 分钟，供 WS 晚连/重连时回放

    def __init__(self, 项目根: str):
        self.项目根 = 项目根
        self.运行中任务: dict[str, dict] = {}
        self.已完成任务: dict[str, dict] = {}  # [v4.2 修复问题2] run_id → 最终状态+日志路径

    def 检测Python(self) -> str:
        """
        Python 检测优先级:
        1. 项目 .venv/Scripts/python.exe
        2. .web-workbench/config.json 中指定的 python
        3. install.json 中的 python_path (全局安装)
        4. 系统 PATH 中的 python (兜底)
        """
        # 1. 项目虚拟环境
        venv_python = Path(self.项目根) / ".venv" / "Scripts" / "python.exe"
        if venv_python.exists():
            return str(venv_python)

        # 2. 项目配置
        config_file = Path(self.项目根) / ".web-workbench" / "config.json"
        if config_file.exists():
            with open(config_file) as f:
                config = json.load(f)
                python = config.get("python_path")
                if python and os.path.isfile(python):
                    return python

        # 3. 全局安装
        install_file = os.path.join(
            os.environ.get("LOCALAPPDATA", ""), "Code880Web", "install.json"
        )
        if os.path.isfile(install_file):
            with open(install_file) as f:
                install = json.load(f)
                python = install.get("python_path")
                if python and os.path.isfile(python):
                    return python

        # 4. 兜底
        return "python"

    async def 启动运行(self, 文件相对路径: str, args: list[str] = None) -> str:
        """启动 Python 文件执行，返回 run_id"""
        from .security import 校验路径安全

        # 安全校验
        if not 校验路径安全(self.项目根, 文件相对路径):
            raise ValueError("路径不合法")
        if not 文件相对路径.endswith(".py"):
            raise ValueError("只能运行 .py 文件")

        目标文件 = Path(self.项目根) / 文件相对路径
        if not 目标文件.exists():
            raise FileNotFoundError(f"文件不存在: {文件相对路径}")

        # MVP: 同一时刻只允许一个任务运行
        if self.运行中任务:
            raise RuntimeError("已有任务运行中，请先停止")

        run_id = uuid.uuid4().hex[:8]
        python路径 = self.检测Python()

        # 构建环境变量
        env = os.environ.copy()
        venv_bin = os.path.join(self.项目根, ".venv", "Scripts")
        if os.path.isdir(venv_bin):
            env["PATH"] = f"{venv_bin};{env.get('PATH', '')}"
        env["PYTHONUNBUFFERED"] = "1"       # 禁用缓冲，实时输出
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONPATH"] = self.项目根

        # 启动子进程 (python -u 双重保证无缓冲)
        cmd_args = args or []
        进程 = await asyncio.create_subprocess_exec(
            python路径, "-u", str(目标文件), *cmd_args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=self.项目根,
            env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )

        # 准备日志文件
        runs_dir = os.path.join(self.项目根, ".web-workbench", "runs")
        os.makedirs(runs_dir, exist_ok=True)
        log_path = os.path.join(runs_dir, f"{run_id}.log")

        self.运行中任务[run_id] = {
            "process": 进程,
            "file": 文件相对路径,
            "pid": 进程.pid,
            "started_at": datetime.now().isoformat(),
            "log_path": log_path,
            "ws_clients": [],  # 每个运行有独立的 WS 客户端列表
        }

        return run_id

    async def 读取输出并推送(self, run_id: str):
        """
        [v4.1 修复问题5] 改用 chunk 读取 + 独立超时看门狗
        - readline() 会阻塞到换行符，input("提示: ") 无换行时提示不会显示
        - 改用 read(4096) + asyncio.wait_for，解决两个问题:
          a) 超时在 read 等待时也能触发
          b) input() 的无换行提示符能被 chunk 读取捕获
        """
        任务 = self.运行中任务.get(run_id)
        if not 任务:
            return

        进程 = 任务["process"]
        log_path = 任务["log_path"]
        output_bytes = 0
        MAX_OUTPUT_BYTES = self.MAX_OUTPUT_LINES * 200  # 约 2MB 上限
        start_time = time.time()

        with open(log_path, "w", encoding="utf-8") as log_file:
            try:
                while True:
                    # 用 wait_for 包裹 read，超时可中断
                    remaining = self.DEFAULT_TIMEOUT - (time.time() - start_time)
                    if remaining <= 0:
                        await self._广播(run_id, {
                            "type": "run_error",
                            "run_id": run_id,
                            "data": "执行超时，已自动终止\n"
                        })
                        进程.kill()
                        break

                    try:
                        chunk = await asyncio.wait_for(
                            进程.stdout.read(4096),
                            timeout=min(remaining, 30)  # 每 30 秒也检查一次
                        )
                    except asyncio.TimeoutError:
                        # 30 秒无输出不代表超时，继续循环（外层 remaining 判断真超时）
                        continue

                    if not chunk:
                        break  # EOF，进程已结束

                    text = chunk.decode("utf-8", errors="replace")
                    output_bytes += len(chunk)

                    # 输出量限制
                    if output_bytes >= MAX_OUTPUT_BYTES:
                        await self._广播(run_id, {
                            "type": "run_error",
                            "run_id": run_id,
                            "data": "\n[输出截断：超过最大输出量限制]\n"
                        })
                        进程.kill()
                        break

                    log_file.write(text)
                    log_file.flush()

                    await self._广播(run_id, {
                        "type": "run_output",
                        "run_id": run_id,
                        "data": text,
                    })

                # [v4.1 修复问题4] 统一在此处等待进程结束并发送 run_finished
                # 无论是正常结束、超时 kill、还是外部 停止运行() 发信号
                exit_code = await 进程.wait()
                elapsed = round(time.time() - start_time, 1)
                finished_msg = {
                    "type": "run_finished",
                    "run_id": run_id,
                    "exit_code": exit_code,
                    "elapsed": elapsed,
                }
                await self._广播(run_id, finished_msg)

            finally:
                # [v4.2 修复问题2] 将已完成任务快照保留到 已完成任务 字典
                # 解决：POST /api/run 返回 run_id 后前端才建立 WS 连接，
                # 快速脚本在 WS 连上之前就执行完毕，前端丢失全部输出。
                # WS 连接时检查 已完成任务，若有则回放日志+最终状态。
                任务 = self.运行中任务.get(run_id)
                if 任务:
                    self.已完成任务[run_id] = {
                        "exit_code": exit_code if 'exit_code' in dir() else -1,
                        "elapsed": elapsed if 'elapsed' in dir() else 0,
                        "log_path": 任务.get("log_path"),
                        "file": 任务.get("file"),
                        "finished_at": time.time(),
                    }
                # 定期清理过期的已完成任务
                self._清理过期任务()
                # 只有输出读取循环负责清理，停止运行() 不 pop
                self.运行中任务.pop(run_id, None)

    async def 发送输入(self, run_id: str, 内容: str):
        """用户 Web 输入 → 写入子进程 stdin"""
        任务 = self.运行中任务.get(run_id)
        if not 任务:
            raise ValueError("任务不存在或已结束")
        进程 = 任务["process"]
        if 进程.stdin:
            进程.stdin.write((内容 + "\n").encode("utf-8"))
            await 进程.stdin.drain()

    async def 停止运行(self, run_id: str):
        """
        [v4.1 修复问题4] 只发信号，不 pop 任务
        最终状态和清理统一由 读取输出并推送() 的 finally 处理
        这样 run_finished 消息始终能正确广播到前端
        """
        任务 = self.运行中任务.get(run_id)
        if not 任务:
            return
        进程 = 任务["process"]
        try:
            os.kill(进程.pid, signal.CTRL_BREAK_EVENT)
            try:
                await asyncio.wait_for(进程.wait(), timeout=3)
            except asyncio.TimeoutError:
                进程.kill()
        except ProcessLookupError:
            pass
        # 注意：不在这里 pop，由输出读取循环统一清理

    def 注册ws客户端(self, run_id: str, ws):
        任务 = self.运行中任务.get(run_id)
        if 任务:
            任务["ws_clients"].append(ws)

    def 移除ws客户端(self, run_id: str, ws):
        任务 = self.运行中任务.get(run_id)
        if 任务 and ws in 任务["ws_clients"]:
            任务["ws_clients"].remove(ws)
            # 无客户端时自动终止进程
            if not 任务["ws_clients"]:
                asyncio.create_task(self.停止运行(run_id))

    async def _广播(self, run_id: str, msg: dict):
        任务 = self.运行中任务.get(run_id)
        if not 任务:
            return
        dead = []
        for ws in 任务["ws_clients"]:
            try:
                await ws.send_json(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            任务["ws_clients"].remove(ws)

    def _清理过期任务(self):
        """[v4.2] 清理超过 COMPLETED_TTL 的已完成任务快照"""
        now = time.time()
        过期ids = [
            rid for rid, info in self.已完成任务.items()
            if now - info["finished_at"] > self.COMPLETED_TTL
        ]
        for rid in 过期ids:
            del self.已完成任务[rid]

    def 查询已完成(self, run_id: str) -> dict | None:
        """[v4.2] 查询已完成任务快照（供 WS 连接时回放）"""
        self._清理过期任务()
        return self.已完成任务.get(run_id)
```

### 10.6 入口文件自动发现

```python
# worker/services/entrypoints.py

import os
from pathlib import Path

KNOWN_ENTRIES = ["main.py", "src/main.py", "app.py", "src/app.py", "run.py"]

def 发现入口文件(项目根: str) -> list[dict]:
    """自动发现项目中可运行的 Python 入口文件"""
    结果 = []

    # 1. 从 launch.json 读取配置
    launch_file = Path(项目根) / ".web-workbench" / "launch.json"
    if launch_file.exists():
        import json
        with open(launch_file) as f:
            launch = json.load(f)
        for cfg in launch.get("configurations", []):
            if cfg.get("type") == "fixed_file" and cfg.get("program"):
                full = Path(项目根) / cfg["program"]
                if full.exists():
                    结果.append({
                        "name": cfg.get("name", cfg["program"]),
                        "path": cfg["program"],
                        "source": "launch.json"
                    })

    # 2. 自动发现已知入口
    for entry in KNOWN_ENTRIES:
        full = Path(项目根) / entry
        if full.exists():
            已有 = any(r["path"] == entry for r in 结果)
            if not 已有:
                结果.append({
                    "name": entry,
                    "path": entry,
                    "source": "auto"
                })

    return 结果
```

### 10.7 Worker API 端点

```python
# worker/app.py — 运行相关端点

@app.get("/api/entrypoints")
async def 获取入口文件():
    """自动发现可运行的 Python 入口文件"""
    return {"entrypoints": 发现入口文件(PROJECT_ROOT)}

@app.post("/api/run")
async def 发起运行(request: Request):
    body = await request.json()
    program = body["program"]       # 相对路径，如 "src/main.py"
    args = body.get("args", [])
    run_id = await task_runner.启动运行(program, args)
    # 启动后台输出读取（不阻塞响应）
    asyncio.create_task(task_runner.读取输出并推送(run_id))
    return {"run_id": run_id, "status": "running"}

@app.get("/api/run/{run_id}")
async def 查询运行状态(run_id: str):
    # [v4.2 修复问题3] run_id 格式校验
    if not RUN_ID_RE.match(run_id):
        raise HTTPException(400, "run_id 格式不合法")
    任务 = task_runner.运行中任务.get(run_id)
    if 任务:
        return {
            "status": "running",
            "file": 任务["file"],
            "pid": 任务["pid"],
            "started_at": 任务["started_at"],
        }
    # [v4.2 修复问题2] 也查询已完成任务
    已完成 = task_runner.查询已完成(run_id)
    if 已完成:
        return {
            "status": "finished",
            "file": 已完成["file"],
            "exit_code": 已完成["exit_code"],
            "elapsed": 已完成["elapsed"],
        }
    return {"status": "not_found"}

@app.post("/api/run/{run_id}/stdin")
async def 发送输入(run_id: str, request: Request):
    if not RUN_ID_RE.match(run_id):
        raise HTTPException(400, "run_id 格式不合法")
    body = await request.json()
    await task_runner.发送输入(run_id, body["input"])
    return {"status": "ok"}

@app.post("/api/run/{run_id}/stop")
async def 停止运行(run_id: str):
    if not RUN_ID_RE.match(run_id):
        raise HTTPException(400, "run_id 格式不合法")
    await task_runner.停止运行(run_id)
    return {"status": "stopped"}

# [v4.1 修复问题6] 运行日志读取 API（支持历史输出恢复）
# [v4.2 修复问题3] run_id 格式校验：必须为 8 位十六进制，防止 Windows 路径穿越
# Windows 下 %5C 被解码为 \，run_id 若不校验则可构造如 "..%5C..%5Csecret" 穿越
import re
RUN_ID_RE = re.compile(r"^[a-f0-9]{8}$")

@app.get("/api/run/{run_id}/log")
async def 读取运行日志(run_id: str):
    """读取历史运行日志，用于浏览器刷新后恢复输出"""
    if not RUN_ID_RE.match(run_id):
        raise HTTPException(400, "run_id 格式不合法")
    log_path = os.path.join(PROJECT_ROOT, ".web-workbench", "runs", f"{run_id}.log")
    if not os.path.exists(log_path):
        raise HTTPException(404, "日志不存在")
    with open(log_path, "r", encoding="utf-8") as f:
        content = f.read()
    return {"run_id": run_id, "log": content}
```

### 10.8 WebSocket 端点（每 run_id 独立，含 token 校验 + 已完成回放）

```python
# worker/app.py — 每次运行独立的 WebSocket

@app.websocket("/ws/run/{run_id}")
async def ws_运行输出(ws: WebSocket, run_id: str):
    # [v4.2 修复问题3] WS 路径中的 run_id 同样需要格式校验
    if not RUN_ID_RE.match(run_id):
        await ws.close(code=4002)
        return

    # [v4.1 修复问题2] WS 握手阶段校验内部 token，与 HTTP 中间件对齐
    # Hub WS 代理会在 extra_headers 中注入 X-Worker-Token
    token = ws.headers.get("X-Worker-Token")
    if token != INTERNAL_TOKEN:
        await ws.close(code=4003)
        return

    await ws.accept()

    # [v4.2 修复问题2] 如果任务已完成（快速脚本在 WS 连上前就结束），回放日志+最终状态
    已完成 = task_runner.查询已完成(run_id)
    if 已完成:
        # 回放日志内容
        log_path = 已完成.get("log_path")
        if log_path and os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as f:
                log_content = f.read()
            if log_content:
                await ws.send_json({
                    "type": "run_output",
                    "run_id": run_id,
                    "data": log_content,
                })
        # 回放最终状态
        await ws.send_json({
            "type": "run_finished",
            "run_id": run_id,
            "exit_code": 已完成["exit_code"],
            "elapsed": 已完成["elapsed"],
        })
        await ws.close()
        return

    # 任务仍在运行中，正常注册并接收实时输出
    task_runner.注册ws客户端(run_id, ws)

    try:
        while True:
            data = await ws.receive_json()
            if data.get("type") == "stdin":
                await task_runner.发送输入(run_id, data["input"])
    except Exception:
        pass
    finally:
        task_runner.移除ws客户端(run_id, ws)
```

> **安全说明**：前端浏览器不能直连 Worker WS 端口（不知道端口号，也没有 token）。前端连的是 Hub 的 `/ws/workspaces/{id}/run/{run_id}`，Hub WS 代理在转发时注入 `X-Worker-Token`（见 §5.4.1）。

### 10.9 WebSocket 消息流

```
前端                            Worker
  │                                │
  │── POST /api/run ─────────────→│  启动子进程
  │←── {run_id, status} ─────────│
  │                                │
  │── WS /ws/run/{run_id} ──────→│  连接
  │                                │
  │←── {type:run_output, data} ──│  逐行推送 stdout
  │←── {type:run_output, data} ──│
  │                                │
  │  (用户在输入框输入)              │
  │── WS {type:stdin, input} ───→ │  写入子进程 stdin
  │                                │
  │←── {type:run_output, data} ──│  继续输出
  │←── {type:run_finished} ──────│  exit_code + elapsed
  │                                │
  │  (或用户点 Stop)                │
  │── POST /api/run/{id}/stop ──→ │  CTRL_BREAK → kill
  │←── WS: {type:run_finished} ──│  exit_code: -1
  │                                │
  │  (或用户关闭标签页)              │
  │── WS 断连 ──────────────────→ │  无客户端 → 自动 kill
```

### 10.10 关键技术点

| 问题 | 解决方案 |
|------|---------|
| 输出不实时 | `PYTHONUNBUFFERED=1` + `python -u` 双重保证无缓冲 |
| `input("提示:")` 无换行不显示 | [v4.1] 改用 `read(4096)` chunk 读取替代 `readline()`，无换行提示符也能被捕获 |
| `input()` 交互 | 前端输入框 → WebSocket `{type:stdin}` → 子进程 stdin |
| 浏览器标签关闭进程残留 | Worker 检测 WS 断连 → 无客户端时自动 kill |
| 停止无响应 | `CTRL_BREAK_EVENT` → 等 3 秒 → `kill()` 强杀 |
| 停止后 UI 卡在"运行中" | [v4.1] `停止运行()` 只发信号不 pop，`读取输出并推送()` 统一发 run_finished 并清理 |
| 脚本死循环无输出时超时不触发 | [v4.1] `asyncio.wait_for(read, timeout=30)` 包裹，超时可中断读取 |
| 用哪个 Python | .venv → config.json → install.json → 系统 (4 级 fallback) |
| 恶意路径 | 复用第六章路径校验 + 只允许 `.py` 后缀 |
| 超时保护 | 默认 5 分钟自动终止 |
| 输出爆炸 | 约 2MB 上限，超出自动截断并终止 |
| 多标签同看输出 | 每个 run_id 维护独立的 ws_clients 列表，广播模式 |
| 历史输出恢复 | 每次运行写入 `.web-workbench/runs/{run_id}.log`，提供 `GET /api/run/{id}/log` 读取 |
| 快速脚本 WS 来不及连 | [v4.2] 已完成任务保留 5 分钟，WS 连接时自动回放日志+最终状态 |
| run_id 路径穿越 | [v4.2] 所有 run_id 参数强制 `^[a-f0-9]{8}$` 校验，拒绝 Windows `%5C` 穿越 |

### 10.11 安全约束

| 约束 | 说明 |
|------|------|
| 路径校验 | 执行前必须过第六章完整校验 |
| 只允许 .py | 拒绝 `.bat`/`.ps1`/`.exe` 等 |
| 项目隔离 | Worker 以项目根为 cwd，子进程继承 |
| 并发限制 | MVP 同一项目同时只允许 1 个任务 |
| 超时 | 默认 5 分钟，可在 launch.json 中配置 |
| 输出截断 | 10000 行上限 |

### 10.12 重要边界说明

如果原项目 `main.py` 是 Tkinter / ttkbootstrap 桌面 GUI 入口，Web 端点击运行它会在本机后台弹出原生窗口，不会自动变成网页。推荐迁移结构：

```
src/main.py          # 保留旧桌面入口
src/core/            # 抽离业务逻辑
code880web/worker/   # Web API 调用业务逻辑
```

---

## 十一、URL 路由与 API 设计

### 11.1 前端页面路由

```
/                          → 项目管理控制台
/w/{workspace_id}          → 项目工作台 (三栏布局)
/bootstrap?code=xxx        → 认证入口 (一次性)
/settings                  → 全局设置
/help                      → 使用帮助
```

### 11.2 内部 API（仅脚本/Hub 内部调用，需 launch_token）

```
GET  /api/hub/identity               ← 无需认证，身份确认
POST /internal/projects/register     ← 需 Bearer launch_token
POST /internal/bootstrap-code        ← 需 Bearer launch_token
POST /internal/ai/relay              ← 需 X-Worker-Token，仅 Worker 可调
```

### 11.3 Hub API（需浏览器会话 Cookie）

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

### 11.4 Workspace API（Hub 反向代理到 Worker）

| 方法 | 路径 | 用途 |
|------|------|------|
| `GET` | `/api/workspaces/{id}/info` | 项目状态 |
| `GET` | `/api/workspaces/{id}/files/tree` | 文件树 |
| `GET` | `/api/workspaces/{id}/files/content?path=` | 读取文件 (含 sha256) |
| `POST` | `/api/workspaces/{id}/files/save` | 保存 (带 base_sha256) |
| `GET` | `/api/workspaces/{id}/files/search?q=` | 搜索 |
| `GET` | `/api/workspaces/{id}/preview/*` | 文件预览 |
| `GET` | `/api/workspaces/{id}/entrypoints` | 可运行入口文件 |
| `POST` | `/api/workspaces/{id}/run` | 运行 Python 文件 |
| `GET` | `/api/workspaces/{id}/run/{run_id}` | 运行状态 |
| `POST` | `/api/workspaces/{id}/run/{run_id}/stdin` | 发送输入 |
| `POST` | `/api/workspaces/{id}/run/{run_id}/stop` | 停止运行 |
| `GET` | `/api/workspaces/{id}/run/{run_id}/log` | 读取运行日志（历史恢复） |
| `POST` | `/api/workspaces/{id}/ai/chat` | AI 对话 (SSE) |
| `GET/POST` | `/api/workspaces/{id}/ai/context/*` | 上下文管理 |

### 11.5 WebSocket

```
/ws/workspaces/{workspace_id}
  → 文件变更推送: file_changed
  → Worker 状态推送: worker_status

/ws/workspaces/{workspace_id}/run/{run_id}
  → 运行输出推送: run_output, run_error, run_finished
  → 接收 stdin 输入: {type: "stdin", input: "..."}
```

---

## 十二、安全设计

### 12.1 多层防护

```
第 1 层: CORS — 不使用通配 *, 只允许精确的 http://127.0.0.1:{hub_port}
第 2 层: Cookie — HttpOnly session + 非 HttpOnly csrf (双 Cookie)
第 3 层: CSRF — 写操作必须携带 X-Code880-CSRF 自定义头
第 4 层: Origin — 校验 Origin 头必须精确等于当前 Hub origin (HTTP + WS 均校验)
第 5 层: WS 会话 — [v4.2] Hub WS 代理在 accept 前校验 session Cookie
第 6 层: 路径 — 4 层校验: 绝对路径拒绝 → Path.resolve → relative_to → 符号链接
第 7 层: Worker — 内部 token 隔离 (临时文件传递, 读后即删)
第 8 层: 命令 — 只允许运行 .py 文件, 不允许 bat/ps1/exe
第 9 层: ID 校验 — [v4.2] run_id 强制 ^[a-f0-9]{8}$ 格式，防 Windows 路径穿越
第 10 层: 限流 — 超时 5 分钟, 输出 10000 行, 并发 1 个
```

### 12.2 API Key 管理

```
存储: %LOCALAPPDATA%\Code880Web\keys\api_keys.enc
加密: Windows DPAPI (CryptProtectData)；无 DPAPI 的开发环境才允许降级为受限 fallback，并必须在日志中标注
前端: 只显示 sk-****abcd
日志: Key 永远不写入日志
传输: Worker 不保存 Key；Worker 调 `/internal/ai/relay` 并携带 `X-Worker-Token`，Hub 校验后在内存中解密并流式代理 AI API
```

---

## 十三、目录结构（最终版）

```
=== 全局安装 (由一键安装部署到用户选择的目录) ===

{install_root}\
├── Python312\                    ← Python 解释器
├── code880web\                   ← Web 工作台 (全局唯一)
│   ├── hub\                     ← Hub 服务代码
│   │   ├── app.py              ← FastAPI Hub 入口
│   │   ├── config.py           ← 配置管理 (读取 install.json)
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
│   │       ├── task_runner.py   ← Python 文件运行
│   │       ├── entrypoints.py   ← 入口文件发现
│   │       ├── watcher.py
│   │       └── security.py      ← 路径校验
│   ├── static\                  ← 前端打包产物
│   │   └── index.html
│   └── requirements.txt
└── 启动项目管理中心.bat           ← 全局入口

=== 全局运行时数据 ===

%LOCALAPPDATA%\Code880Web\
├── install.json                 ← 安装路径发现
├── hub_runtime.json             ← Hub PID/端口
├── hub.db                       ← 项目注册表
├── models.json                  ← AI 模型配置
├── keys\
│   ├── launch_token             ← 启动认证 token
│   └── api_keys.enc             ← 加密 API Key
├── worker_tokens\               ← Worker 临时 token 文件 (用后即删)
└── logs\
    └── hub.log

=== 项目内 (每个项目模板) ===

{项目根目录}\
├── 启动Web工作台.bat              ← 启动脚本 (调用全局 Hub)
├── 启动Web工作台.ps1              ← PowerShell 核心逻辑
├── .web-workbench\               ← Worker 运行时 (自动生成)
│   ├── workspace.json
│   ├── state.json
│   ├── config.json              ← 项目级配置 (可选, 含 python_path)
│   ├── launch.json              ← 运行配置 (对齐 VSCode)
│   ├── chat_history\
│   ├── backups\
│   ├── preview-cache\
│   ├── runs\                    ← 每次运行的日志
│   │   ├── a1b2c3d4.log
│   │   └── e5f6g7h8.log
│   └── worker.log
├── src\                          ← 原有: 不动
├── __hy127\                      ← 原有: 不动
├── .vscode\                      ← 原有: 不动
├── .venv\                        ← 原有: 不动
└── 重新初始化 V1.24.bat           ← 原有: 不动
```

---

## 十四、分阶段实施

### MVP 阶段（约 2-3 周）

```
目标: 单 Hub + 单进程多协程 + 核心功能跑通
  → 可用于演示和 UI 验证
  → 不进入正式多项目稳定版验收

功能:
  ✅ Hub 主进程 + 前端静态托管
  ✅ 端口自动探测 + hub_runtime.json
  ✅ install.json 路径发现
  ✅ 单项目文件树 + 文本/代码查看 (Monaco)
  ✅ PDF 预览 (PDF.js)
  ✅ Excel 基础表格预览 (openpyxl → JSON)
  ✅ Word 轻量预览 (mammoth → HTML, 标注保真度)
  ✅ AI 模型配置 + 对话 (SSE 流式)
  ✅ 上下文选择 (勾选文件)
  ✅ 启动Web工作台.bat 一键启动
  ✅ Hub 基础认证 (launch_token + 会话)
  ✅ 点击运行 Python 文件 (▶ 按钮 / 右键 / 快捷键)
  ✅ 运行输出实时推送 (WebSocket)
  ✅ stdin 输入支持 (input() 交互)
  ✅ 停止运行 (⬛ 按钮)
  ✅ 入口文件自动发现

  ⏳ 多项目注册 (页面有入口，但同一进程内服务)

暂不实现:
  ❌ Worker 独立进程
  ❌ Worker 内部 token
  ❌ 文件版本校验/写入锁
  ❌ 文件监听 watchdog
  ❌ 休眠/唤醒
  ❌ 断点调试
```

### 正式稳定版（MVP 后约 3 周）

```
目标: 真正的多项目并行 + 进程隔离 + 安全闭环

功能:
  ✅ Worker 独立进程 (subprocess + CREATE_NEW_PROCESS_GROUP)
  ✅ Worker 内部 token (临时文件, 读后即删)
  ✅ Hub → Worker 反向代理
  ✅ 完整双 Cookie 认证 (session HttpOnly + csrf 可读)
  ✅ 路径安全 4 层校验
  ✅ 文件保存 sha256 版本校验
  ✅ 文件写入锁
  ✅ Hub 健康监测 + Worker 自动重启
  ✅ 任务队列 (读/预览/AI/写/命令 分级)
  ✅ 文件监听 watchdog + 节流
  ✅ Worker 空闲休眠/唤醒
  ✅ AI 工具调用 (read_file, generate_patch)
  ✅ AI 修改 diff 预览 + 确认 + 备份
  ✅ 审计日志
  ✅ Worker stdout 重定向到日志文件 + 日志轮转

验收标准:
  ✅ 同时打开 3 个项目, 各自独立运行
  ✅ 杀掉 Worker A, 项目 B/C 无影响
  ✅ 恶意网页无法调用任何写 API
  ✅ 多标签保存同文件不会静默覆盖
  ✅ 30 分钟无人用 Worker 自动休眠
  ✅ 点击运行 main.py 输出实时可见
```

### 正式稳定版子系统规格（v4.3 补齐）

| 子系统 | 必须实现的状态/接口 | 验收点 |
|------|------------------|------|
| Worker 健康监测 | Hub 每 10 秒检查 Worker `poll()` 与 `/api/info`；状态为 `running/exited/restarting/sleeping` | 杀掉 Worker 后 10 秒内 UI 显示异常；配置为自动重启的 Worker 30 秒内恢复 |
| 任务队列 | 每项目维护 `read/preview/ai/write/run` 5 类队列；`write/run` 串行，`read/preview` 可并行 | 大文件预览不能阻塞保存；运行任务不能并发覆盖同一项目状态 |
| 文件写入锁 | 每个规范化绝对路径一把锁；保存必须校验 `base_sha256`，失败返回 409 | 两个标签页编辑同一文件，后保存者收到冲突提示 |
| 文件监听 | watchdog 监听项目根，忽略 `.git/.venv/.web-workbench/node_modules`；300ms 节流聚合 | 外部编辑文件后，前端 1 秒内收到 `file_changed` |
| Worker 休眠/唤醒 | 30 分钟无 WS/HTTP 活跃且无运行任务则停止 Worker；访问工作区自动拉起 | 休眠后打开 `/w/{id}` 能自动恢复文件树 |
| 审计日志 | 写入 `%LOCALAPPDATA%\Code880Web\logs\audit.log`；记录项目注册、保存、运行、停止、AI 调用元数据 | 日志不含 API Key、CSRF、Worker token、文件正文 |
| AI 工具调用 | 第一版只允许 `read_file`；`generate_patch` 必须走 diff 预览、备份、确认 | AI 不能直接写盘；用户确认前项目文件不变化 |
| Workspace WS | `/ws/workspaces/{id}` 发送 `file_changed`、`worker_status`、`project_error` | 关闭浏览器标签后 WS 资源释放，无后台泄漏 |

### 自动化验收矩阵（v4.3 补齐）

| 类型 | 覆盖内容 | 最低要求 |
|------|---------|---------|
| 单元测试 | 路径穿越、run_id、Auth/CSRF/Origin、注册表、文件保存冲突、API Key 加密持久化 | 每项至少 1 个正例 + 2 个反例 |
| 集成测试 | 启动脚本 → Hub → 注册项目 → Worker → 文件树 → 运行 Python | Windows 本机一键通过 |
| 安全测试 | 不同 127.0.0.1 端口 Origin、缺 CSRF、伪 Worker token、WS 未登录 | 必须返回 401/403/关闭 WS |
| 回归测试 | 快速脚本 WS 迟连回放、停止运行、输出超限、超时 kill | 前端状态不能卡在运行中 |
| 编码检查 | Markdown/PS1/Python/HTML 均按 UTF-8 读取；扫描 `å|æ|ç|�` 等 mojibake 特征 | 命中即失败，除非在测试样本中显式白名单 |

### 后续增强（按需）

```
  ⬜ LibreOffice Portable 高保真预览
  ⬜ ONLYOFFICE 可选插件 (编辑级, Docker)
  ⬜ xterm.js 终端输出 (替代简易输出面板)
  ⬜ 代码编辑 (Monaco 读写模式)
  ⬜ debugpy + DAP 断点调试
  ⬜ 打包为 Web工作台.exe
  ⬜ 首次使用向导
  ⬜ 主题切换 (明/暗)
  ⬜ 运行历史记录查看
  ⬜ 多任务并行运行
```

---

## 十五、全部修订记录

| 版本 | # | 问题 | 修复 |
|------|---|------|------|
| v2→v3 | 1 | 进程隔离原则与 MVP 单进程冲突 | 原则分层：全版本 vs 正式版 |
| v2→v3 | 2 | 启动认证与脚本没有闭环 | 完整 bootstrap 流程 |
| v2→v3 | 3 | Batch `%CD%` Unicode escape | PowerShell `ConvertTo-Json` |
| v2→v3 | 4 | `start /B` 关窗即杀进程 | `Start-Process -WindowStyle Hidden` + `CREATE_NEW_PROCESS_GROUP` |
| v2→v3 | 5 | 路径 `startswith` 前缀绕过 | `commonpath` + 尾部分隔符 |
| v2→v3 | 6 | Worker 端口本机任意进程可达 | Worker 内部 token |
| v2→v3 | 7 | Office 预览保真度被高估 | 标注 ★ 评级 |
| v2→v3 | 8 | Hub 代码在项目内 vs 全局矛盾 | 全局唯一安装 |
| v3→v3.1 | 1 | Hub 端口硬编码与自动探测矛盾 | 脚本从 `hub_runtime.json` 读实际端口 |
| v3→v3.1 | 2 | 安装路径硬编码 `C:\PythonDev` | `install.json` 路径发现 |
| v3→v3.1 | 3 | Worker token 命令行可见 | 临时文件传递, 读后即删 |
| v3→v3.1 | 4 | HttpOnly Cookie 与 CSRF 矛盾 | 双 Cookie 模式 |
| v3→v3.1 | 5 | Worker PIPE 缓冲区满卡死 | stdout 直接写日志文件 |
| v3→v3.1 | 6 | 路径校验未拒绝绝对路径 | 4 层校验: isabs + Path.resolve + relative_to + 符号链接 |
| v3→v3.1 | 7 | 缺少 ONLYOFFICE 可选增强 | 追加增强方案 D |
| v4 新增 | 1 | 缺少"点击运行 Python 文件"完整设计 | 新增第十章，合并三方案取长补短 |
| v4 新增 | 2 | v3.1 为补丁需交叉查阅 v3 | 合并为单一完整文档 |
| v4→v4.1 | 1 | Hub 代理路径没有重写，Workspace API 对不上 Worker API | Hub 代理剥离 `/api/workspaces/{id}` 前缀，WS 代理同步重写 |
| v4→v4.1 | 2 | Worker WebSocket 没有内部 token 校验 | WS 握手阶段校验 `X-Worker-Token`，Hub WS 代理注入 token |
| v4→v4.1 | 3 | Hub 启动代码没有实际生成 launch_token | 在端口探测后、runtime 文件写入前生成 token 并写入 keys/ |
| v4→v4.1 | 4 | TaskRunner stop/finish 竞态，前端可能收不到 run_finished | `停止运行()` 只发信号不 pop，`读取输出并推送()` 统一清理 |
| v4→v4.1 | 5 | readline() 阻塞导致超时不触发 + input() 提示不显示 | 改用 `read(4096)` chunk 读取 + `asyncio.wait_for` 超时包裹 |
| v4→v4.1 | 6 | 运行日志无读取 API，"历史输出恢复"过度承诺 | 新增 `GET /api/run/{run_id}/log` 端点 |
| v4.1→v4.2 | 1 | Hub WS 代理未校验浏览器会话 Cookie/Origin，恶意网页可直连 | WS 代理在 `accept()` 前校验 `code880_session` Cookie + Origin |
| v4.1→v4.2 | 2 | 快速脚本在 WS 连接前完成，前端丢失全部输出 | 已完成任务保留 5 分钟（`已完成任务` 字典），WS 连接时回放日志+最终状态 |
| v4.1→v4.2 | 3 | `run_id` 路径参数无格式校验，Windows `%5C` 可穿越 | 所有含 `run_id` 的端点（HTTP + WS）强制 `^[a-f0-9]{8}$` 正则校验 |
| v4.1→v4.2 | 4 | HTTP 代理 `httpx.request()` 缓冲全部响应，SSE/大文件/预览阻塞 | 改用 `httpx.stream()` + `StreamingResponse` 流式转发，过滤逐跳头 |
| v4.1→v4.2 | 5 | WS 双向转发用 `asyncio.gather()`，一侧断开另一侧悬挂泄漏 | 改用 `asyncio.wait(FIRST_COMPLETED)` + 取消 pending + 关闭两端 |
| v4.2→v4.3 | 1 | Origin 校验仍允许任意 127.0.0.1 端口 | HTTP/WS/CORS 统一精确匹配当前 Hub origin |
| v4.2→v4.3 | 2 | Worker token 文件路径仍在命令行参数中 | 改为 `CODE880_WORKER_TOKEN_FILE` 环境变量传递，Worker 读后即删 |
| v4.2→v4.3 | 3 | 一键安装缺少 Web 部署闭环 | 明确复制 `code880web/`、安装 `requirements.txt`、可选下载 vendor 后再写 `install.json` |
| v4.2→v4.3 | 4 | API Key 存储/Worker 使用链路不完整 | 明确 `api_keys.enc` + DPAPI + Hub `/internal/ai/relay`，Worker 不保存 Key |
| v4.2→v4.3 | 5 | 正式稳定版只列功能，缺可开发规格 | 补充健康监测、任务队列、锁、watchdog、休眠、审计、AI 工具和 WS 验收矩阵 |
| v4.3→v4.4 | 1 | 启动脚本按文件路径运行 `app.py`，包内相对导入会失败 | Hub/Worker 均改为 `python -m code880web.*.app`，工作目录设为安装根目录 |
| v4.4 补充 | 2 | 开发验证目录与全局 `install.json` 指向目录不一致，可能启动旧代码 | 启动脚本检测本地 `.venv + code880web` 时优先当前目录，并通过 `CODE880WEB_INSTALL_ROOT` 传递给 Hub/Worker |
| v4.4 补充 | 3 | `python -m` 后 `uvicorn.run("module:app")` 二次导入模块，导致端口状态丢失 | Hub 启动改为 `uvicorn.run(app, ...)`，复用已设置端口的当前模块对象 |
| v4.4 补充 | 4 | Windows 下 `%LOCALAPPDATA%` 旧日志文件可能拒绝访问，Hub 因日志打开失败退出 | Hub 日志初始化容错：`hub.log` 打不开则写 `hub_{pid}.log`，仍失败则仅控制台输出 |
| v4.4 补充 | 5 | Windows 下旧 `keys\launch_token` 可能拒绝覆盖，Hub 因 token 写入失败退出 | AuthManager 写 token 时主路径失败则生成进程专属 token 文件，并通过 runtime 暴露真实路径 |
| v4.4 补充 | 6 | 开发机 `%LOCALAPPDATA%\Code880Web` 可能被旧进程/沙箱 ACL 污染，导致 runtime/token/logs 无法写入 | 本地开发版启动时设置 `CODE880WEB_GLOBAL_DIR=.web-workbench\global`，隔离开发验证运行时 |
| v4.4 补充 | 7 | PowerShell 5.1 默认编码读取含中文路径的 runtime JSON 可能损坏转义 | 启动脚本读取 JSON 统一 `-Encoding UTF8`，Hub runtime 使用 ASCII-safe JSON |
| v4.4 补充 | 8 | PowerShell 5.1 发送 JSON 字符串可能损坏中文项目路径，导致注册项目 500 | 启动脚本用 UTF-8 bytes 发送 JSON；本地开发版默认注册脚本所在目录；路径不存在时返回 400 |
| v4.4 补充 | 9 | 开发验证时可能复用上一次旧 Hub 进程，导致新修复不生效 | 本地开发版启动时读取 runtime PID 并强制重启 Hub，确保使用当前代码 |
| v4.4 补充 | 10 | 本地 vendor 缺失时 SPA fallback 把 `/vendor/*.js` 返回成 `index.html`，浏览器拿 HTML 当 JS 执行导致黑屏 | 缺失静态资源返回 404，让 script `onerror` 正常走 CDN fallback；正式包仍应内置 vendor |

---

## 十六、总结

### 一句话架构

> 全局唯一 Hub (端口自动探测) 流式反向代理到每项目独立 Worker (临时文件 token 隔离)，浏览器通过一次性 bootstrap code 建立双 Cookie 安全会话（WS 同样校验会话），路径路由 `/w/{id}` 区分项目，Worker 内 TaskRunner 支持点击运行 Python 文件并通过 WebSocket 实时推送输出（已完成任务保留 5 分钟支持延迟连接回放）。

### 发现链

```
一键安装.exe
  → 部署 code880web 到用户选择的目录
  → 安装 code880web\requirements.txt
  → 可选下载/内置 static\vendor 前端离线资源
  → 写入 %LOCALAPPDATA%\Code880Web\install.json (安装路径)

双击 启动Web工作台.bat
  → ps1 读取 install.json 发现 Python/Hub 路径
  → 若脚本所在目录存在 `.venv` 与 `code880web`，开发验证优先使用当前目录，并将运行时写入 `.web-workbench\global`
  → 检查 hub_runtime.json 发现 Hub 是否已运行及实际端口
  → Hub 未运行? → Start-Process Hidden 以 `python -m code880web.hub.app` 启动 → 等待 runtime 文件落盘
  → 从本机文件读取 launch_token
  → POST /internal/projects/register (PowerShell 序列化，无路径转义)
  → POST /internal/bootstrap-code (获取一次性 code)
  → 打开 http://127.0.0.1:{实际端口}/bootstrap?code=xxx
  → Hub 校验 → 设置双 Cookie → 跳转 → Worker 就绪
  → 用户点击 ▶ 运行 → Worker TaskRunner 启动子进程
  → stdout 实时推送到浏览器终端面板
  → 同步写入 .web-workbench/runs/{run_id}.log
```

---

> 文档版本：v4.4 | 创建日期：2026-04-30
> 定位：**唯一完整开发基准**，合并 v3 + v3.1 + 点击运行三方案 + v4 复核 6 项修正 + v4.2 复核 5 项修正 + v4.3 落地复核修正 + v4.4 启动验证修正
> 废弃：v3.md / v3.1.md / v4.md(未修正版) / v4.1 仅作历史参考，开发以本文为准
