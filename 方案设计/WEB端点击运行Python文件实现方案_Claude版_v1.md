# WEB端点击运行 Python 文件实现方案 (Claude版)

> 目标：在 WEB 工作台（类似 VS Code 界面）中点击运行 `main.py` 等 Python 文件，输出实时回显到浏览器内置终端面板。
> 基于方案：`WEB端迁移方案_最终整合版_v3.md` + `v3.1.md`
> 生成时间：2026-04-29

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
  命令面板输入 "运行当前文件" → 执行
```

### 1.2 运行配置（对应 VSCode launch.json）

```json
// .web-workbench/run_profiles.json
{
  "profiles": [
    {
      "name": "运行当前文件",
      "type": "current_file",
      "description": "运行编辑器中打开的 .py 文件"
    },
    {
      "name": "运行 src/main.py",
      "type": "fixed_file",
      "file": "src/main.py",
      "description": "固定运行项目入口"
    }
  ],
  "default": "运行当前文件"
}
```

### 1.3 与 VSCode launch.json 对照

| VSCode 配置 | Web 工作台对应 |
|-------------|---------------|
| "Python: 当前文件(终端)" — 在终端运行当前打开的文件 | ▶ 按钮 / 右键"运行此文件"，输出到底部面板 |
| "Python: src/main.py" — 固定运行 main.py | 快捷运行栏预设配置，存 `run_profiles.json` |
| "Python: 当前文件(调试)" — 断点调试 | **MVP 不实现**，后续可通过 debugpy + DAP 协议扩展 |

---

## 二、界面布局

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

- 底部输出面板可折叠/展开，类似 VSCode 的终端面板
- 输入框仅在进程运行中时出现（支持 `input()` 交互）
- 显示运行命令、退出码、耗时

---

## 三、整体思路

```
VSCode 的体验:                        Web 工作台对应实现:
─────────────────                     ─────────────────────
▶ Run 按钮 / F5                  →   工具栏 ▶ 按钮 / 右键菜单"运行"
终端面板显示输出                   →   底部输出面板 (WebSocket 实时推送)
终端可输入 (stdin)                →   输入框 → WebSocket 发送 stdin
Ctrl+C 停止                      →   ⬛ Stop 按钮 → 终止子进程
launch.json 配置                  →   .web-workbench/run_profiles.json
```

---

## 四、后端实现

### 4.1 Worker 端：TaskRunner 服务

```python
# worker/services/task_runner.py

import subprocess
import asyncio
import os
import uuid
import signal
from pathlib import Path

class 任务管理器:
    def __init__(self, 项目根: str):
        self.项目根 = 项目根
        self.运行中任务: dict[str, dict] = {}  # task_id → 任务信息

    def 获取项目Python(self) -> str:
        """使用项目自身的 .venv Python，而非系统 Python"""
        venv_python = Path(self.项目根) / ".venv" / "Scripts" / "python.exe"
        if venv_python.exists():
            return str(venv_python)
        raise FileNotFoundError("项目虚拟环境未找到，请先运行初始化")

    async def 启动任务(self, 文件相对路径: str, ws_send) -> str:
        """
        启动 Python 文件执行
        ws_send: WebSocket 发送回调，用于实时推送输出
        """
        # 1. 安全校验
        from .security import 校验路径安全
        if not 校验路径安全(self.项目根, 文件相对路径):
            raise ValueError("路径不合法")
        if not 文件相对路径.endswith(".py"):
            raise ValueError("只能运行 .py 文件")

        目标文件 = Path(self.项目根) / 文件相对路径
        if not 目标文件.exists():
            raise FileNotFoundError(f"文件不存在: {文件相对路径}")

        # 2. 同一时刻只允许一个任务运行（MVP 限制）
        if self.运行中任务:
            raise RuntimeError("已有任务运行中，请先停止")

        # 3. 启动子进程
        task_id = uuid.uuid4().hex[:8]
        python路径 = self.获取项目Python()

        进程 = await asyncio.create_subprocess_exec(
            python路径, str(目标文件),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,  # 合并 stderr 到 stdout
            cwd=self.项目根,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            env={
                **os.environ,
                "PYTHONUNBUFFERED": "1",        # 关键：禁用缓冲，实时输出
                "PYTHONIOENCODING": "utf-8",
            }
        )

        self.运行中任务[task_id] = {
            "process": 进程,
            "file": 文件相对路径,
            "pid": 进程.pid,
        }

        # 4. 异步读取输出并推送到前端
        asyncio.create_task(self._读取输出(task_id, 进程, ws_send))

        return task_id

    async def _读取输出(self, task_id, 进程, ws_send):
        """逐行读取子进程输出，通过 WebSocket 实时推送"""
        try:
            while True:
                line = await 进程.stdout.readline()
                if not line:
                    break
                await ws_send({
                    "type": "task_output",
                    "task_id": task_id,
                    "data": line.decode("utf-8", errors="replace"),
                })

            exit_code = await 进程.wait()
            await ws_send({
                "type": "task_finished",
                "task_id": task_id,
                "exit_code": exit_code,
            })
        finally:
            self.运行中任务.pop(task_id, None)

    async def 发送输入(self, task_id: str, 内容: str):
        """处理用户在 Web 输入框输入的内容 → 写入子进程 stdin"""
        任务 = self.运行中任务.get(task_id)
        if not 任务:
            raise ValueError("任务不存在")
        进程 = 任务["process"]
        if 进程.stdin:
            进程.stdin.write((内容 + "\n").encode("utf-8"))
            await 进程.stdin.drain()

    async def 停止任务(self, task_id: str):
        """用户点击 ⬛ Stop → 终止子进程"""
        任务 = self.运行中任务.get(task_id)
        if not 任务:
            return
        进程 = 任务["process"]
        try:
            # Windows: 向进程组发送 CTRL_BREAK_EVENT
            os.kill(进程.pid, signal.CTRL_BREAK_EVENT)
            # 等待 3 秒，仍未退出则强杀
            try:
                await asyncio.wait_for(进程.wait(), timeout=3)
            except asyncio.TimeoutError:
                进程.kill()
        except ProcessLookupError:
            pass
        finally:
            self.运行中任务.pop(task_id, None)
```

### 4.2 Worker API 端点

```python
# worker/app.py 中添加

@app.post("/tasks/run")
async def 运行任务(request: Request):
    body = await request.json()
    文件路径 = body["file_path"]   # 相对路径，如 "src/main.py"
    task_id = await 任务管理器.启动任务(文件路径, ws_send=None)
    return {"task_id": task_id, "status": "running"}

@app.post("/tasks/{task_id}/stop")
async def 停止任务(task_id: str):
    await 任务管理器.停止任务(task_id)
    return {"status": "stopped"}

@app.post("/tasks/{task_id}/stdin")
async def 发送输入(task_id: str, request: Request):
    body = await request.json()
    await 任务管理器.发送输入(task_id, body["input"])
    return {"status": "ok"}
```

### 4.3 WebSocket 实时推送

```python
# worker/app.py WebSocket 处理

@app.websocket("/ws")
async def websocket端点(ws: WebSocket):
    await ws.accept()

    async def ws_send(msg: dict):
        await ws.send_json(msg)

    # 绑定到任务管理器，供输出推送使用
    任务管理器.ws_send = ws_send

    try:
        while True:
            data = await ws.receive_json()
            # 处理前端发来的消息
            if data["type"] == "task_stdin":
                await 任务管理器.发送输入(data["task_id"], data["input"])
    except Exception:
        pass
```

---

## 五、前端实现

### 5.1 输出面板组件

```vue
<!-- OutputPanel.vue 核心逻辑 -->
<template>
  <div class="output-panel">
    <div class="toolbar">
      <el-button @click="运行当前文件" type="primary" :icon="CaretRight"
                 :disabled="运行中">运行</el-button>
      <el-button @click="停止运行" type="danger" :icon="VideoPause"
                 :disabled="!运行中">停止</el-button>
      <span class="file-name">{{ 当前文件 }}</span>
    </div>

    <!-- 输出区域：滚动到底部 -->
    <div class="output-content" ref="outputRef">
      <pre v-for="line in 输出行" :key="line.id">{{ line.text }}</pre>
    </div>

    <!-- stdin 输入框：仅在进程运行中时出现 -->
    <div class="stdin-bar" v-if="运行中">
      <el-input v-model="输入内容" placeholder="程序等待输入..."
                @keyup.enter="发送输入" />
      <el-button @click="发送输入">发送</el-button>
    </div>

    <div class="status-bar" v-if="退出信息">
      {{ 退出信息 }}
    </div>
  </div>
</template>
```

### 5.2 WebSocket 消息流

```
前端                        后端 Worker
  │                              │
  │──POST /tasks/run ──────────→ │  启动子进程
  │←── {task_id} ───────────────│
  │                              │
  │←── WS: task_output ────────│  逐行推送 stdout
  │←── WS: task_output ────────│
  │←── WS: task_output ────────│
  │                              │
  │  (用户在输入框输入)            │
  │──WS: task_stdin ───────────→│  写入子进程 stdin
  │                              │
  │←── WS: task_output ────────│  继续输出
  │←── WS: task_finished ──────│  进程结束 + 退出码
  │                              │
  │  (或用户点 Stop)              │
  │──POST /tasks/{id}/stop ───→ │  CTRL_BREAK + kill
  │←── WS: task_finished ──────│  exit_code: -1
```

---

## 六、关键技术点

| 问题 | 解决方案 |
|------|---------|
| 输出不实时，等进程结束才出现 | `PYTHONUNBUFFERED=1` 环境变量禁用 Python 输出缓冲 |
| `input()` 等待用户输入 | 前端输入框 → WebSocket → 写入子进程 `stdin` |
| 用户关闭浏览器标签，进程还在跑 | Worker 检测 WebSocket 断连后自动 kill 子进程 |
| 停止按钮无响应 | `CTRL_BREAK_EVENT` → 等 3 秒 → `kill()` 强杀 |
| 使用哪个 Python | 项目自带的 `.venv/Scripts/python.exe`，非系统 Python |
| 安全：用户构造恶意路径 | 复用 v3.1 路径校验 + 只允许 `.py` 后缀 |
| 长时间运行的脚本 | 输出面板持续滚动，显示运行时长，可随时 Stop |
| 停止/超时限制 | 支持停止按钮，默认 5 分钟超时，最多 10000 行输出截断 |

---

## 七、安全约束

| 约束 | 说明 |
|------|------|
| 路径校验 | 执行前必须过 v3.1 路径安全校验（拒绝绝对路径/穿越/符号链接外指） |
| 只允许 .py | 只允许运行 `.py` 后缀文件，不允许 `.bat`/`.ps1`/`.exe` 等 |
| 项目隔离 | Worker 以项目根为 cwd，派生子进程继承该 cwd |
| Python 检测 | 自动优先使用项目 `.venv` → 配置文件 → 全局安装 |
| 并发限制 | MVP 阶段同一项目同时只允许 1 个任务运行 |
| 超时保护 | 默认 5 分钟自动终止，可在运行配置中调整 |
| 输出截断 | 单次运行最多保留 10000 行输出，超出自动截断旧行 |

---

## 八、MVP 工作量估计

| 子任务 | 估时 |
|--------|------|
| Worker TaskRunner 服务 | 1 天 |
| Worker API 端点 (run/stop/stdin) | 0.5 天 |
| WebSocket 任务输出推送 | 0.5 天 |
| 前端输出面板组件 | 1 天 |
| 前端运行按钮/右键菜单集成 | 0.5 天 |
| 运行配置 (run_profiles.json) | 0.5 天 |
| 路径安全校验集成 | 0.5 天 |
| 快捷键绑定 | 0.5 天 |
| 联调测试 | 1 天 |
| **合计** | **约 6 天** |

---

> 文档版本：Claude版 v1 | 创建日期：2026-04-29
> 定位：v3 + v3.1 设计基线的补充方案，专注"点击运行 Python 文件"功能
