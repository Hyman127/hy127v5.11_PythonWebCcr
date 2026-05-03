# WEB端点击运行 Python 文件实现方案 v1

> 目标：在 WEB 工作台（类似 VS Code 界面）中点击运行 `main.py` 等 Python 文件，输出实时回显到浏览器内置终端。
> 基于方案：`WEB端迁移方案_最终整合版_v3.1.md`
> 生成时间：2026-04-28

---

## 一、功能定义

### 1.1 交互方式

```
方式 A：文件树右键菜单
  右键 main.py → "▶ 运行" → 文件开始执行

方式 B：编辑器工具栏按钮
  打开 main.py → 编辑器右上角 ▶ 按钮 → 点击运行

方式 C：快捷键
  打开 main.py → Ctrl+F5 / F5（覆盖 VS Code 肌肉记忆）

方式 D：终端命令面板
  底部集成终端 → 输入 run main.py 或 python main.py
```

### 1.2 预期效果

```
┌──────────────────────────────────────────────┐
│  [文件树]  │  [编辑器] main.py              │
│            │                                │
│  📁 src/   │  1 │ def main():               │
│  ├─ main.py│  2 │     print("Hello")        │
│  ├─ util.py│  3 │                           │
│  └─ data/  │  4 │ if __name__ == "__main__":│
│            │  5 │     main()                │
│            │  ────────────────────────────── │
│            │  [终端输出]                     │
│            │  > python main.py              │
│            │  Hello                          │
│            │  Process exited with code 0     │
└──────────────────────────────────────────────┘
```

---

## 二、架构设计

### 2.1 执行模型

```
浏览器 (前端)
   │
   ├─ POST /api/workspaces/{ws_id}/run   ← 用户点击运行
   │    body: { "file": "src/main.py", "mode": "script" }
   │
   ▼
Hub (FastAPI)
   │
   ├─ 校验路径安全（v3.1 第六章）
   ├─ 转发请求到 Worker
   │
   ▼
Worker (项目专属子进程)
   │
   ├─ 派生新子进程执行 python <file>
   ├─ stdout/stderr 通过 WebSocket 实时推送
   ├─ 进程退出时发送 exit_code
   │
   ▼
浏览器 (前端)  ← WebSocket 实时接收输出
```

### 2.2 为什么不直接 Hub 执行

| 原因 | 说明 |
|------|------|
| 进程隔离 | 每个项目由 Worker 管理，Worker 在项目根目录 cwd 执行 |
| 环境隔离 | Worker 使用项目的虚拟环境 Python，而非全局 Python |
| 安全隔离 | 路径校验后只允许在项目根内执行 |
| 稳定性 | 一个项目的执行崩溃不影响其他项目或 Hub |

---

## 三、后端实现

### 3.1 Hub 端 API

```python
# hub/app.py — 新增 /run 端点

@router.post("/api/workspaces/{workspace_id}/run")
async def run_project_file(
    workspace_id: str,
    body: RunFileRequest,
    request: Request
):
    """
    执行项目内 Python 文件，返回 WebSocket 连接信息
    """
    校验CSRF(request)
    
    workspace = workspace_manager.get(workspace_id)
    if not workspace:
        raise HTTPException(404, "工作区不存在")
    
    file_path = body.file  # 相对路径，如 "src/main.py"
    
    # [v3.1 第六章] 路径安全校验
    if not 校验路径安全(workspace.root_path, file_path):
        raise HTTPException(403, "非法文件路径")
    
    # 完整路径
    full_path = os.path.join(workspace.root_path, file_path)
    if not os.path.isfile(full_path):
        raise HTTPException(404, "文件不存在")
    
    # 生成运行 ID 和 WebSocket token
    run_id = str(uuid.uuid4())
    ws_token = secrets.token_urlsafe(32)
    
    # 存储运行上下文
    run_contexts[run_id] = {
        "workspace_id": workspace_id,
        "file": full_path,
        "ws_token": ws_token,
        "status": "pending",
        "created_at": datetime.now()
    }
    
    # 通知 Worker 启动执行（通过现有的内部通信通道）
    worker = worker_manager.get(workspace_id)
    worker.send_command({
        "command": "run_file",
        "run_id": run_id,
        "file": file_path,          # 相对路径
        "mode": body.mode or "script",
        "args": body.args or [],
        "ws_token": ws_token
    })
    
    return {
        "run_id": run_id,
        "ws_url": f"ws://127.0.0.1:{workspace.hub_port}/ws/run/{run_id}?token={ws_token}"
    }
```

### 3.2 Worker 端：子进程执行

```python
# worker/app.py — 处理 run_file 命令

import asyncio
import subprocess
import os
import signal

class RunManager:
    """管理运行中的进程"""
    
    def __init__(self):
        self.running_processes: dict[str, asyncio.subprocess.Process] = {}
    
    async def run_file(
        self,
        run_id: str,
        file: str,          # 相对路径，如 "src/main.py"
        project_root: str,
        ws_token: str,
        args: list[str] = [],
        hub_port: int = None
    ):
        """启动 Python 文件执行"""
        
        # 完整路径
        full_path = os.path.join(project_root, file)
        
        # 选择 Python 解释器
        python_exe = self._detect_python(project_root)
        
        # 构建命令
        cmd = [python_exe, full_path] + args
        
        # === 关键：使用 asyncio subprocess 以支持实时输出 ===
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=project_root,           # 工作目录 = 项目根
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._build_env(project_root)  # 继承虚拟环境等
        )
        
        self.running_processes[run_id] = process
        
        # 启动 WebSocket 输出中继
        await self._relay_output(run_id, process, ws_token, hub_port)
    
    async def _relay_output(
        self,
        run_id: str,
        process: asyncio.subprocess.Process,
        ws_token: str,
        hub_port: int
    ):
        """实时读取 stdout/stderr 并推送"""

        # [v3.1 第五章] 注意：这里是 asyncio PIPE，内存缓冲区足够大
        # 但仍然要及时读取，不然可能阻塞子进程
        # 最大缓冲区: 默认 64KB，我们以 1024 字节为单位读取

        async with aiohttp.ClientSession() as session:
            ws = await session.ws_connect(
                f"http://127.0.0.1:{hub_port}/ws/run/{run_id}",
                headers={"Authorization": f"Bearer {ws_token}"}
            )
            
            async def read_stream(stream, stream_name: str):
                """读取一个流并发送到 WebSocket"""
                try:
                    while True:
                        line = await stream.readline()
                        if not line:
                            break
                        await ws.send_json({
                            "event": "output",
                            "stream": stream_name,
                            "data": line.decode("utf-8", errors="replace"),
                            "run_id": run_id
                        })
                except Exception as e:
                    await ws.send_json({
                        "event": "error",
                        "data": f"读取{stream_name}错误: {e}",
                        "run_id": run_id
                    })
            
            # 并发读取 stdout 和 stderr
            await asyncio.gather(
                read_stream(process.stdout, "stdout"),
                read_stream(process.stderr, "stderr"),
            )
            
            # 等待进程结束
            exit_code = await process.wait()
            
            # 发送结束事件
            await ws.send_json({
                "event": "exit",
                "exit_code": exit_code,
                "run_id": run_id
            })
            
            await ws.close()
            del self.running_processes[run_id]
    
    def stop_run(self, run_id: str):
        """终止运行中的进程"""
        process = self.running_processes.get(run_id)
        if process:
            try:
                process.terminate()
            except Exception:
                pass
    
    def _detect_python(self, project_root: str) -> str:
        """检测项目使用的 Python 解释器"""

        # 优先级:
        # 1. 项目 .venv/Scripts/python.exe
        # 2. 项目 .web-workbench/config.json 中指定的 python
        # 3. install.json 中的 python_path
        # 4. 系统 PATH 中的 python
        
        venv_python = os.path.join(project_root, ".venv", "Scripts", "python.exe")
        if os.path.isfile(venv_python):
            return venv_python
        
        config_file = os.path.join(project_root, ".web-workbench", "config.json")
        if os.path.isfile(config_file):
            with open(config_file) as f:
                config = json.load(f)
                python = config.get("python_path")
                if python and os.path.isfile(python):
                    return python
        
        # 回退到全局安装的 Python
        install_file = os.path.join(
            os.environ["LOCALAPPDATA"], "Code880Web", "install.json"
        )
        if os.path.isfile(install_file):
            with open(install_file) as f:
                install = json.load(f)
                return install.get("python_path", "python")
        
        return "python"
    
    def _build_env(self, project_root: str) -> dict:
        """构建子进程环境变量"""
        env = os.environ.copy()
        
        # 确保 PATH 包含可能的虚拟环境
        venv_bin = os.path.join(project_root, ".venv", "Scripts")
        if os.path.isdir(venv_bin):
            env["PATH"] = f"{venv_bin};{env.get('PATH', '')}"
        
        # 设置 PYTHONPATH
        env["PYTHONPATH"] = project_root
        
        return env
```

### 3.3 Hub 端：WebSocket 中继

```python
# hub/app.py — WebSocket 端点：前端连接到此，Hub 中继 Worker 输出

from fastapi import WebSocket, WebSocketDisconnect

@router.websocket("/ws/run/{run_id}")
async def websocket_run_output(websocket: WebSocket, run_id: str):
    """前端连接此 WebSocket 接收运行输出"""
    
    # 验证 token
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001)
        return
    
    run_ctx = run_contexts.get(run_id)
    if not run_ctx or run_ctx["ws_token"] != token:
        await websocket.close(code=4003)
        return
    
    await websocket.accept()
    
    # 启动：通知 Worker 已连接，可以开始执行
    worker = worker_manager.get(run_ctx["workspace_id"])
    worker.send_command({"command": "run_start", "run_id": run_id})
    
    # 中继：Worker → Hub → 前端
    # 方式 1: Hub 内部再建一条 WebSocket 到 Worker
    # 方式 2: Worker 直接写 HTTP SSE 到 Hub，Hub 转 WS 到前端
    # 以下采用方式 2（更简单，避免双层 WS）
    
    try:
        # Hub 内部队列接收 Worker 的输出
        while True:
            output = await run_ctx["output_queue"].get()
            
            if output is None:  # 结束信号
                break
            
            try:
                await websocket.send_json(output)
            except WebSocketDisconnect:
                break
    except WebSocketDisconnect:
        pass
    finally:
        # 清理
        run_contexts.pop(run_id, None)
```

---

## 四、前端实现

### 4.1 HTML/CSS：运行按钮与终端面板

```html
<!-- static/index.html — 编辑器工具栏 -->

<div class="editor-toolbar">
    <button id="btn-run" class="toolbar-btn run-btn" title="运行 (Ctrl+F5)">
        <span class="icon">▶</span>
        <span>运行</span>
    </button>
    <button id="btn-stop" class="toolbar-btn stop-btn" disabled title="停止运行">
        <span class="icon">■</span>
        <span>停止</span>
    </button>
</div>

<!-- 底部终端面板 -->
<div class="terminal-panel" id="terminal-panel">
    <div class="terminal-header">
        <span>终端输出</span>
        <button id="btn-clear-terminal">清除</button>
        <button id="btn-toggle-terminal">▼</button>
    </div>
    <div class="terminal-body" id="terminal-output">
        <!-- 输出行动态插入 -->
    </div>
</div>
```

```css
/* static/css/terminal.css */

.terminal-panel {
    border-top: 2px solid var(--border-color);
    background: #1e1e1e;
    color: #d4d4d4;
    font-family: 'Cascadia Code', 'Consolas', monospace;
    font-size: 13px;
    min-height: 150px;
    max-height: 40vh;
    display: flex;
    flex-direction: column;
}

.terminal-header {
    display: flex;
    justify-content: space-between;
    padding: 4px 12px;
    background: #2d2d2d;
    font-size: 12px;
    cursor: row-resize;
}

.terminal-body {
    flex: 1;
    overflow-y: auto;
    padding: 8px 12px;
    white-space: pre-wrap;
    word-break: break-all;
}

.terminal-body .stdout {}
.terminal-body .stderr {
    color: #f48771;
}
.terminal-body .exit-info {
    color: #6a9955;
    margin-top: 4px;
    border-top: 1px dashed #444;
    padding-top: 4px;
}
```

### 4.2 JavaScript：运行逻辑

```javascript
// static/js/run.js

class RunManager {
    constructor() {
        this.ws = null;
        this.isRunning = false;
        this.currentRunId = null;
        this.terminal = document.getElementById('terminal-output');
    }

    async runFile(filePath) {
        if (this.isRunning) {
            alert('已有脚本正在运行，请先停止');
            return;
        }

        const workspaceId = this.getCurrentWorkspaceId();

        try {
            // 1. 发起运行请求
            const resp = await fetch(
                `/api/workspaces/${workspaceId}/run`,
                {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Code880-CSRF': this.getCsrfToken()
                    },
                    credentials: 'same-origin',
                    body: JSON.stringify({
                        file: filePath,
                        mode: 'script'
                    })
                }
            );

            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || '启动失败');
            }

            const { run_id, ws_url } = await resp.json();

            // 2. 清空终端并显示启动信息
            this.clearTerminal();
            this.appendOutput('system', `> python ${filePath}\n`);

            // 3. 连接 WebSocket 接收输出
            this.currentRunId = run_id;
            this.isRunning = true;
            this.setRunButtonsState(true);

            this.ws = new WebSocket(ws_url);

            this.ws.onmessage = (event) => {
                const msg = JSON.parse(event.data);

                switch (msg.event) {
                    case 'output':
                        this.appendOutput(msg.stream, msg.data);
                        break;
                    case 'exit':
                        this.appendOutput(
                            'exit',
                            `\n进程已退出，退出码: ${msg.exit_code}\n`
                        );
                        this.onRunEnd();
                        break;
                    case 'error':
                        this.appendOutput('stderr', msg.data);
                        break;
                }

                // 自动滚动到底部
                this.terminal.scrollTop = this.terminal.scrollHeight;
            };

            this.ws.onerror = (err) => {
                this.appendOutput('stderr', `WebSocket 错误: ${err}\n`);
                this.onRunEnd();
            };

            this.ws.onclose = () => {
                this.onRunEnd();
            };

        } catch (err) {
            this.appendOutput('stderr', `启动失败: ${err.message}\n`);
        }
    }

    stopRun() {
        if (this.ws && this.isRunning) {
            // 通过 HTTP API 通知后端终止进程
            fetch(`/api/workspaces/${this.getCurrentWorkspaceId()}/run/${this.currentRunId}/stop`, {
                method: 'POST',
                headers: {
                    'X-Code880-CSRF': this.getCsrfToken()
                },
                credentials: 'same-origin'
            });
        }
    }

    onRunEnd() {
        this.isRunning = false;
        this.currentRunId = null;
        this.setRunButtonsState(false);
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }

    appendOutput(type, text) {
        const span = document.createElement('span');
        span.className = type;
        span.textContent = text;
        this.terminal.appendChild(span);
    }

    clearTerminal() {
        this.terminal.innerHTML = '';
    }

    setRunButtonsState(running) {
        document.getElementById('btn-run').disabled = running;
        document.getElementById('btn-stop').disabled = !running;
    }

    getCsrfToken() {
        return document.cookie
            .split('; ')
            .find(c => c.startsWith('code880_csrf='))
            ?.split('=')[1] || '';
    }

    getCurrentWorkspaceId() {
        const match = location.pathname.match(/\/w\/([^/]+)/);
        return match ? match[1] : null;
    }
}

// 初始化
const runManager = new RunManager();

// 按钮绑定
document.getElementById('btn-run').addEventListener('click', () => {
    const currentFile = editorManager.getCurrentFile();  // 获取当前打开的文件
    if (currentFile) {
        runManager.runFile(currentFile);
    }
});

document.getElementById('btn-stop').addEventListener('click', () => {
    runManager.stopRun();
});

// 快捷键绑定
document.addEventListener('keydown', (e) => {
    // Ctrl+F5 运行
    if (e.ctrlKey && e.key === 'F5') {
        e.preventDefault();
        const currentFile = editorManager.getCurrentFile();
        if (currentFile) {
            runManager.runFile(currentFile);
        }
    }
});

// 文件树右键菜单绑定
document.querySelector('.file-tree').addEventListener('contextmenu', (e) => {
    const fileItem = e.target.closest('.file-item');
    if (fileItem && fileItem.dataset.path?.endsWith('.py')) {
        e.preventDefault();
        showContextMenu(e.clientX, e.clientY, [
            {
                label: '▶ 运行',
                action: () => runManager.runFile(fileItem.dataset.path)
            },
            { type: 'separator' },
            { label: '重命名', action: () => renameFile(fileItem) },
            { label: '删除', action: () => deleteFile(fileItem) }
        ]);
    }
});
```

---

## 五、文件树右键菜单实现

```javascript
// static/js/context-menu.js

function showContextMenu(x, y, items) {
    // 移除已有菜单
    const existing = document.querySelector('.context-menu');
    if (existing) existing.remove();

    const menu = document.createElement('div');
    menu.className = 'context-menu';
    menu.style.cssText = `
        position: fixed;
        left: ${x}px;
        top: ${y}px;
        background: #252526;
        border: 1px solid #454545;
        border-radius: 4px;
        padding: 4px 0;
        min-width: 160px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.5);
        z-index: 10000;
    `;

    items.forEach(item => {
        if (item.type === 'separator') {
            const sep = document.createElement('div');
            sep.className = 'context-separator';
            sep.style.cssText = 'border-top: 1px solid #454545; margin: 4px 0;';
            menu.appendChild(sep);
        } else {
            const menuItem = document.createElement('div');
            menuItem.className = 'context-item';
            menuItem.textContent = item.label;
            menuItem.style.cssText = `
                padding: 6px 16px;
                cursor: pointer;
                font-size: 13px;
                color: #d4d4d4;
            `;
            menuItem.onmouseenter = () => menuItem.style.background = '#094771';
            menuItem.onmouseleave = () => menuItem.style.background = '';
            menuItem.onclick = () => {
                menu.remove();
                item.action();
            };
            menu.appendChild(menuItem);
        }
    });

    document.body.appendChild(menu);

    // 点击其他地方关闭
    const closeHandler = () => {
        menu.remove();
        document.removeEventListener('click', closeHandler);
    };
    setTimeout(() => document.addEventListener('click', closeHandler), 0);
}
```

---

## 六、Terminal 增强：命令模式

### 6.1 支持 `python <file>` 命令

除了点击运行，终端也支持直接输入命令：

```javascript
// static/js/terminal-command.js

class TerminalCommands {
    constructor(runManager) {
        this.runManager = runManager;
        this.input = document.getElementById('terminal-input');
    }

    async executeCommand(inputText) {
        const trimmed = inputText.trim();
        
        // 解析：python <file> [args...]
        const pythonFileMatch = trimmed.match(/^python\s+(.+?)(?:\s+(.*))?$/);
        if (pythonFileMatch) {
            const file = pythonFileMatch[1].replace(/^['"]|['"]$/g, ''); // 去掉引号
            const args = pythonFileMatch[2] 
                ? pythonFileMatch[2].split(/\s+/) 
                : [];
            
            // 转为调用 runFile
            await this.runManager.runFile(file);
            return;
        }

        // 其他命令...
        switch (trimmed) {
            case 'clear':
            case 'cls':
                this.runManager.clearTerminal();
                break;
            case 'help':
                this.appendOutput('system', '支持的命令:\n');
                this.appendOutput('system', '  python <file>  - 运行 Python 文件\n');
                this.appendOutput('system', '  clear           - 清屏\n');
                this.appendOutput('system', '  run <file>      - 运行文件\n');
                break;
            default:
                this.appendOutput('stderr', `未知命令: ${trimmed}\n`);
        }
    }
}
```

---

## 七、安全考量

| 层级 | 措施 | 说明 |
|------|------|------|
| 路径校验 | v3.1 第六章完整校验 | 拒绝绝对路径、路径穿越、符号链接外指 |
| 执行范围 | Worker 以项目根为 cwd | 即使路径校验被绕过，也限制在项目根 |
| 进程隔离 | 独立子进程 | 崩溃不影响 Worker/Hub |
| 超时限制 | 可选：n 秒后自动终止 | 防止无限循环耗尽资源 |
| 输出限制 | 最大输出行数限制（如 10000 行） | 防止恶意无限输出 |
| 并发限制 | 每个 Worker 同时只允许 1 个运行 | 防止资源耗尽 |

### 7.1 超时与输出限制

```python
# worker/app.py — RunManager 新增

class RunManager:
    MAX_OUTPUT_LINES = 10000
    DEFAULT_TIMEOUT = 300  # 默认 5 分钟超时
    
    async def _relay_output(self, ...):
        line_count = 0
        start_time = time.time()
        
        async def read_stream(stream, stream_name: str):
            nonlocal line_count
            while True:
                # 超时检查
                if time.time() - start_time > self.DEFAULT_TIMEOUT:
                    await ws.send_json({
                        "event": "error",
                        "data": "执行超时，已终止\n"
                    })
                    process.terminate()
                    break
                
                # 输出行数限制
                if line_count >= self.MAX_OUTPUT_LINES:
                    await ws.send_json({
                        "event": "error",
                        "data": "\n[输出截断：超过最大行数限制]\n"
                    })
                    process.terminate()
                    break
                
                line = await stream.readline()
                if not line:
                    break
                line_count += 1
                await ws.send_json({...})
```

---

## 八、停止运行 API

```python
# hub/app.py

@router.post("/api/workspaces/{workspace_id}/run/{run_id}/stop")
async def stop_run(
    workspace_id: str,
    run_id: str,
    request: Request
):
    """终止运行中的进程"""
    校验CSRF(request)
    
    run_ctx = run_contexts.get(run_id)
    if not run_ctx or run_ctx["workspace_id"] != workspace_id:
        raise HTTPException(404, "运行实例不存在")
    
    worker = worker_manager.get(workspace_id)
    worker.send_command({"command": "stop_run", "run_id": run_id})
    
    return {"status": "stopped"}


# worker/app.py — 处理停止命令
@worker.on_command("stop_run")
def handle_stop(run_id: str):
    run_manager.stop_run(run_id)
```

---

## 九、实施步骤

### MVP 阶段 (第一版)

| 步骤 | 内容 | 工作量 |
|------|------|:------:|
| 1 | Worker: 子进程执行 + asyncio PIPE 读取 | 2h |
| 2 | Hub: `/run` API + 路径校验 | 1h |
| 3 | Hub: WebSocket 中继端点 | 1.5h |
| 4 | 前端: 运行按钮 + 终端面板 UI | 2h |
| 5 | 前端: WebSocket 输出展示 | 1h |
| 6 | 前端: 停止按钮 + 快捷键 | 0.5h |
| 7 | 集成测试 + 异常处理 | 1h |
| **合计** | | **9h** |

### 增强阶段 (后续版本)

| 功能 | 说明 | 优先级 |
|------|------|:------:|
| 终端命令面板 | 支持交互式命令输入 | P2 |
| 断点/调试 | 集成 debugpy 远程调试 | P3 |
| 参数输入 | 运行前弹窗输入命令行参数 | P2 |
| 环境变量配置 | 项目级 env 配置 | P2 |
| 运行历史 | 查看历史运行记录 | P3 |
| 多文件运行 | 同时运行多个任务 | P3 |
| Jupyter 风格 | 逐单元格运行 Python | P4 |

---

## 十、与现有方案的关系

本方案建立在 `WEB端迁移方案_最终整合版_v3.1.md` 基础上：

| v3.1 章节 | 本方案依赖 | 关联说明 |
|-----------|-----------|---------|
| 第一章 | Hub 端口发现 | Worker 启动 Python 子进程前需知道 Hub 端口 |
| 第二章 | 安装路径发现 | 检测项目 Python 解释器 |
| 第三章 | Worker Token | Worker 已认证，直接接收 run 命令 |
| 第四章 | CSRF | 运行 API 需要 CSRF 校验 |
| 第五章 | 输出重定向 | 本方案用 asyncio PIPE（内存），非文件 PIPE |
| 第六章 | 路径安全 | 运行前必须校验路径安全 |

---

> 文档版本：v1
> 创建日期：2026-04-28
> 定位：WEB 工作台"点击运行 Python 文件"功能实现方案