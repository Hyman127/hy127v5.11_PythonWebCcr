# Hy127 Web Python 编程辅助工作台优化方案

生成日期：2026-05-03  
适用项目：`Hy127v5.11_PythonWeb`  
核心对象：`Hy127 Web` 本地 Web 工作台

## 1. 结论先行

本项目当前的 `Hy127 Web` 不是简单的“OpenAI SDK 调用示例”，也不是“Claude 壳子”。它更准确的定位是：

> 面向 Python 项目的本地 Web 工作台本体。

它通过 Hub + Worker 架构，把一个 Python 项目目录抽象成浏览器可访问、可管理、可运行、可接入 AI 的工作区。

当前架构方向对 Python 编程辅助是有帮助的，原因是它已经把项目能力拆成了可复用的本地 API：

- 文件树
- 文件读取
- 文件保存接口
- 文档和图片预览
- Python 文件运行
- 实时运行日志
- AI 对话上下文
- 模型配置
- 多项目隔离

但是，当前实现还处在“Web 查看、预览、运行、问 AI”的阶段。若要成为真正高效的 Python 编程辅助工作台，需要继续补齐编辑、文件管理、Git、依赖环境、AI 工具调用和跨平台启动能力。

## 2. 当前项目结构判断

### 2.1 术语与命名约定

当前仓库仍有一批历史命名，必须先和代码事实对齐，再规划后续统一改名：

| 名称 | 当前代码事实 | 后续目标 |
|---|---|---|
| 产品名 | 文档中使用 `Hy127 Web` | 保持 `Hy127 Web` |
| Python 包 / 源码目录 | 当前为 `code880web/` | 后续统一重命名为 `hy127web/` |
| 环境变量 | 当前 `code880web/hub/config.py` 读取 `CODE880WEB_INSTALL_ROOT`、`CODE880WEB_PYTHON_PATH`、`CODE880WEB_GLOBAL_DIR` | 新增代码统一使用 `HY127WEB_INSTALL_ROOT`、`HY127WEB_PYTHON_PATH`、`HY127WEB_GLOBAL_DIR`；过渡期兼容旧变量 |
| 本机全局目录 | 当前默认 `Code880Web` | 后续迁移为 `Hy127Web`，迁移脚本负责读取旧目录并写入新目录 |
| 前端标题、Cookie、Header、日志名 | 当前仍有 `Code880` / `code880` 历史字样 | 新增和重命名时统一替换为 `Hy127` / `hy127` |

本文后续描述产品能力时统一使用 `Hy127 Web`。涉及当前文件路径和现有代码落点时，保留 `code880web/` 作为当前事实，并把重命名列入 P0 命名收敛任务。后续开发不再新增 `code880` 命名。

项目根目录中和 Web 工作台直接相关的核心结构如下：

```text
Hy127v5.11_PythonWeb/
├── code880web/                # 当前历史包名；后续目标为 hy127web/
│   ├── hub/
│   │   ├── app.py              # Hub 主服务入口
│   │   ├── auth.py             # 启动 token、session、CSRF
│   │   ├── config.py           # 端口、全局目录、安装信息发现
│   │   ├── models_manager.py   # AI 模型和 API Key 管理
│   │   ├── proxy.py            # Hub 到 Worker 的 HTTP/WS 代理
│   │   ├── registry.py         # 项目注册表
│   │   └── supervisor.py       # Worker 进程管理
│   ├── worker/
│   │   ├── app.py              # 单项目 Worker 服务入口
│   │   └── services/
│   │       ├── file_service.py     # 文件树、读取、保存、搜索
│   │       ├── task_runner.py      # 运行 Python 文件
│   │       ├── preview_service.py  # PDF/Excel/Word/PPT 预览
│   │       ├── ai_service.py       # Worker 侧 AI 对话
│   │       ├── entrypoints.py      # Python 入口文件发现
│   │       └── security.py         # 路径边界校验
│   ├── static/
│   │   └── index.html          # Vue + Monaco 单页前端
│   └── requirements.txt        # Web 工作台运行依赖
├── 启动Web工作台.bat
├── 启动Web工作台.ps1
├── src/
│   ├── main.py
│   └── 一键安装卸载.py
└── 方案设计/
```

其中：

- `code880web/` 是当前 Web 工作台本体源码目录，属于历史命名。
- `src/一键安装卸载.py` 负责 Windows 一键安装环境，并部署当前 Web 工作台组件。
- `启动Web工作台.ps1` 是 Windows 下正式启动路径。
- `方案设计/WEB端迁移方案_最终整合版_v4.md` 是当前设计基准。

### 2.2 路由与文档对齐原则

Hub 和 Worker 路由后续不建议手工维护长列表。应新增一个只读开发脚本，例如：

```text
scripts/export_routes.py
```

脚本扫描 `hy127web/hub/app.py`、`hy127web/worker/app.py` 中的 FastAPI 装饰器，输出 Markdown 路由表。命名收敛完成前，脚本同时兼容当前 `code880web/` 路径。方案文档中的路由表以后以脚本输出为准，避免代码改了、方案仍停留在旧版本。

## 3. 当前架构本质

当前架构可以概括为：

```text
浏览器
  |
  | 访问 http://127.0.0.1:{hub_port}
  v
Hub 主服务
  |
  | 管理项目、认证、模型、Worker、代理
  v
Worker 项目服务
  |
  | 直接操作某个 Python 项目目录
  v
项目文件 / Python 解释器 / 运行日志 / 预览缓存
```

### 3.1 Hub 职责

Hub 是全局入口，负责：

- 托管前端页面
- 管理项目列表
- 注册项目目录
- 启动和停止 Worker
- 管理 AI 模型配置
- 存储和保护 API Key
- 处理启动认证、会话、CSRF、Origin 校验
- 将浏览器请求代理到对应 Worker

典型路由：

```text
/api/hub/identity
/api/hub/projects
/api/hub/models
/api/hub/runtimes
/internal/projects/register
/internal/bootstrap-code
/internal/ai/relay
/api/workspaces/{workspace_id}/{path}
/ws/workspaces/{workspace_id}/{path}
```

### 3.2 Worker 职责

Worker 是单项目服务，每个项目理论上一个独立 Worker 进程。

它负责：

- 获取项目文件树
- 读取文本和图片
- 保存文件
- 查找入口文件
- 预览 PDF、Excel、Word、PPT
- 运行 Python 文件
- 通过 WebSocket 推送运行输出
- 按选中文件构造 AI 上下文

典型路由：

```text
/api/info
/api/files/tree
/api/files/content
/api/files/save
/api/files/search
/api/preview/{path}
/api/preview-stream
/api/entrypoints
/api/run
/api/run/{run_id}
/api/run/{run_id}/stdin
/api/run/{run_id}/stop
/api/run/{run_id}/log
/ws/run/{run_id}
/api/ai/chat
/api/ai/context
/api/ai/history
```

### 3.3 前端职责

前端是当前 `code880web/static/index.html` 中的单页应用，命名收敛后迁移到 `hy127web/static/index.html`，当前使用：

- Vue 3
- Monaco Editor
- marked
- 原生 fetch
- 原生 WebSocket

界面结构：

```text
顶部栏
├── 项目名称
├── AI 显示/隐藏
└── 返回项目列表

左侧
└── 文件树

中间
├── 文件 Tab
├── Monaco 代码区域或文档预览区域
└── 运行输出终端

右侧
├── AI 接入中心
├── 模型配置
├── 上下文文件选择
└── 对话区
```

## 4. 与 OpenAI SDK 和 Claude 壳子的区别

### 4.1 三者不是同一层

| 对象 | 所属层级 | 本质 | 解决的问题 |
|---|---|---|---|
| Hy127 Web 路由架构 | 应用本体层 | 本地 Web 工作台 | 如何浏览、运行、管理 Python 项目 |
| OpenAI SDK | 模型调用层 | 官方 API 客户端 | 如何规范调用 OpenAI API |
| Claude 壳子 | 外部 Agent 适配层 | 调用 Claude CLI 的包装 | 如何把任务交给 Claude CLI 执行 |

更直观地说：

```text
Hy127 Web = 工作台骨架和手脚
OpenAI SDK  = 调 OpenAI 模型的客户端
Claude 壳子 = 调 Claude CLI 的桥接器
```

### 4.2 当前项目实际 AI 调用方式

当前代码没有真正接入 OpenAI SDK，也没有真正接入 Claude CLI。

当前 AI 链路是：

```text
前端 /api/workspaces/{id}/ai/chat
  -> Hub 代理到 Worker
  -> Worker /api/ai/chat
  -> Hub /internal/ai/relay
  -> httpx 请求 OpenAI-compatible /chat/completions
```

也就是说，当前是自写 HTTP 调用 OpenAI-compatible 接口。

### 4.3 OpenAI SDK 的价值

OpenAI SDK 能优化的是模型调用层，例如：

```text
认证
请求构造
响应解析
流式输出
工具调用协议
错误类型
多模态能力
Responses API
Agents SDK 对接
```

但它不会自动提供：

```text
项目文件树
浏览器工作台
文件保存
运行 Python
Git 状态
多项目隔离
Worker 管理
本地认证
文档预览
```

这些仍然需要 Hy127 Web 自己实现。

### 4.4 Claude 壳子的价值和风险

Claude 壳子通常是指：

```text
Hy127
  -> 启动 claude 命令
  -> 把用户任务和上下文交给 Claude CLI
  -> 读取 Claude CLI 输出
  -> 把结果显示到 Web 页面
```

它的价值是：

- 可以借用 Claude Code 已有的编程 Agent 能力
- 对代码理解、修改、命令执行可能更强
- 初期接入速度可能快

风险是：

- 权限边界复杂
- 文件改动不一定完全可控
- 命令执行安全需要额外审批
- 输出协议需要稳定封装
- 出错恢复和日志追踪要自己补
- 不同 CLI 版本行为可能变化

因此 Claude/Codex/Qwen/Gemini CLI 更适合作为可插拔运行时，而不是替代 Hy127 Web 的 Hub/Worker 架构。

## 5. 推荐总体架构

建议保持当前的工作台本体架构：

```text
浏览器 UI
  |
  v
Hub
  |
  |-- 项目管理
  |-- 模型管理
  |-- 认证
  |-- Worker 代理
  |-- AI Runtime 调度
  |
  v
Worker
  |
  |-- 文件工具
  |-- 运行工具
  |-- 预览工具
  |-- Git 工具
  |-- 环境工具
  |-- AI 上下文工具
```

AI 层做成可插拔：

```text
AI Runtime
├── direct_api_httpx          # 当前已有
├── direct_api_openai_sdk     # 建议新增
├── openai_agents_sdk         # 中后期接入
├── claude_cli                # 后续可选
├── codex_cli                 # 后续可选
├── qwen_cli                  # 后续可选
└── gemini_cli                # 后续可选
```

这样做的好处：

- 工作台能力不依赖某一个模型供应商。
- OpenAI、Claude、Codex、Qwen 都只是“大脑”。
- 文件、运行、预览、Git 等能力统一由 Worker 提供。
- 后续可比较不同模型在同一套工具上的效果。

## 6. 对 Python 编程辅助的价值

### 6.1 已经具备的价值

当前项目已经具备以下 Python 编程辅助基础：

| 能力 | 当前状态 | 对 Python 编程的价值 |
|---|---|---|
| 项目文件树 | 已有 | 快速理解项目结构 |
| 文本文件读取 | 已有 | 查看 `.py`、`.md`、`.json` 等文件 |
| Monaco 高亮 | 已有 | Python 代码可读性较好 |
| Python 入口发现 | 已有 | 自动发现 `main.py`、`src/main.py` 等 |
| Python 文件运行 | 已有后端 | 可直接运行当前文件或入口文件 |
| WebSocket 输出 | 已有 | 实时查看程序输出 |
| 文档预览 | 已有 | 适合办公自动化场景 |
| AI 上下文选择 | 已有 | 可让 AI 基于选中文件回答 |
| 多项目隔离 | 架构已有 | 多个 Python 项目互不干扰 |

### 6.2 当前主要短板

| 短板 | 当前表现 | 影响 |
|---|---|---|
| 编辑闭环未打通 | Monaco 当前 `readOnly: true` | 不能直接在 Web 中改代码 |
| 保存前端缺失 | 后端有 `/api/files/save`，前端未接入 | 文件修改能力没有形成产品闭环 |
| 文件管理不足 | 缺少新建、删除、重命名 | 项目维护能力不足 |
| Git 辅助缺失 | 无 status、diff、commit 相关接口 | 不利于真实开发 |
| 依赖环境管理不足 | 无 `.venv` 检测、依赖安装、解释器选择 UI | Python 项目运行稳定性不足 |
| 终端能力不足 | 当前只支持运行 `.py` | 不能覆盖常见开发命令 |
| AI 只能聊天 | 不能主动读写、运行、验证 | 还不是编程 Agent |
| Linux 兼容不足 | Worker 启动和运行有 Windows 专属代码 | Ubuntu 服务器上无法原样完整启动，部分路径会因 Windows 常量不存在而失败 |

## 7. 分阶段优化路线

## 阶段一：打通 Web 编辑闭环

目标：让工作台从“查看器”升级为“可编辑工作台”。

### 7.1 后端现状

后端已经有：

```text
POST /api/files/save
```

支持：

- 路径合法性校验
- `sha256` 版本冲突检测
- 保存前备份
- UTF-8 写入

### 7.2 前端需要补齐

建议改造当前 `code880web/static/index.html`，命名收敛后对应 `hy127web/static/index.html`：

- 将 Monaco `readOnly: true` 改为可编辑。
- 监听内容变化，标记文件为 dirty。
- 文件 Tab 显示未保存标记。
- 支持 `Ctrl+S` 保存当前文件。
- 保存时提交 `path`、`content`、`base_sha256`。
- 保存成功后更新 `sha256`。
- 保存失败时提示冲突，不静默覆盖。
- `base_sha256` 必须来自文件首次读取响应，随打开文件对象一起保存；不能在切换焦点或保存前用本地内容重新计算代替。
- 保存成功后用服务端返回的新 `sha256` 覆盖当前文件对象的 `base_sha256`，并清除 dirty 状态。
- 切换文件 Tab 时保留 dirty 缓冲，不强制保存；关闭 Tab、返回项目列表、刷新页面或关闭浏览器时提示未保存变更。
- 增加大文件保护，默认不允许前端直接编辑和保存超过 2 MB 的文本文件；`.csv`、`.log` 等大文本只读预览，避免整体误回写。

建议新增前端函数：

```text
saveActiveFile()
markDirty(file)
confirmReloadOnConflict(file)
```

### 7.3 验收标准

- 能打开 `src/main.py`。
- 能修改内容。
- 按 `Ctrl+S` 保存。
- 刷新页面后内容仍存在。
- 另一个进程改动文件后，Web 保存会提示冲突。
- 保存前自动备份到 `.web-workbench/backups/`。
- 打开两个文件并分别修改，切换 Tab 不丢失未保存缓冲。
- 大于阈值的文件不会进入可保存编辑状态。
- 自动化检查建议：`pytest code880web/tests/test_file_service.py`，后续补 `tests/e2e/test_edit_save.py::test_persist_after_reload`。

## 阶段二：补齐文件管理能力

目标：让用户可以在 Web 里完成基础项目维护。

### 7.4 建议新增 Worker API

```text
POST   /api/files/create
POST   /api/files/mkdir
POST   /api/files/rename
DELETE /api/files/delete
POST   /api/files/copy
```

### 7.5 安全要求

所有文件操作必须复用：

```python
validate_path(project_root, relative_path)
```

额外要求：

- 禁止操作 `.git`
- 禁止操作 `.venv`
- 禁止操作 `.web-workbench`
- `validate_path` 必须解析符号链接后再次确认目标仍在 `project_root` 内。
- Windows 下路径比较要做大小写归一和真实路径归一，避免 `.GIT`、短路径名等绕过。
- 拒绝空文件名、包含 `..`、包含 `\0`、Windows 保留名 `CON` / `PRN` / `AUX` / `NUL` / `COM1` 等非法名称。
- 删除操作默认只允许项目根目录内文件
- 删除分为软删和真删：单文件默认软删到 `.web-workbench/trash/` 并轻确认；真删和目录删除必须强确认。
- 重命名不得跨出项目根目录

### 7.6 前端交互

建议在文件树右键菜单中加入：

```text
新建文件
新建文件夹
重命名
删除
复制相对路径
复制绝对路径
在终端中运行
```

### 7.7 验收标准

- 能新建 `.py` 文件。
- 能新建目录。
- 能重命名文件。
- 能删除普通文件。
- 删除受保护目录会被拒绝。
- 文件树操作后自动刷新。

## 阶段三：增强 Python 运行和环境管理

目标：让工作台更适合真实 Python 项目运行。

### 7.8 当前运行能力

当前 `TaskRunner` 支持：

- 运行 `.py`
- 单任务限制
- 运行超时
- 输出截断
- stdin 输入
- WebSocket 实时输出
- 运行日志保存

当前限制也要作为阶段三的起点处理：

- 当前 `TaskRunner.detect_python()` 优先硬编码 `.venv/Scripts/python.exe`，没有 Linux/macOS 的 `.venv/bin/python` 回退。
- 当前 `TaskRunner` 使用 `subprocess.CREATE_NEW_PROCESS_GROUP` 和 `signal.CTRL_BREAK_EVENT`，Linux 上会因常量不存在而在运行路径崩溃。
- 当前 `WorkerSupervisor` 使用 `subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP`，Linux 上同样需要平台分支。
- 当前缺少解释器候选列表接口，前端无法显示“当前选中解释器”和“可切换解释器”。

### 7.9 需要优化的点

#### 解释器识别

当前偏 Windows：

```text
.venv/Scripts/python.exe
```

建议按以下优先级查找解释器：

```text
1. .web-workbench/config.json 中的 python_path
   - 项目级显式配置，最高优先级
   - 若文件不存在或路径失效，返回诊断信息并继续查找候选
2. .venv/bin/python             # Linux/macOS
   .venv/Scripts/python.exe     # Windows
3. install.json 中 python_path
   - 当前代码来自全局目录安装信息
   - 命名收敛后使用 Hy127Web 全局目录
4. sys.executable
5. shutil.which("python3")
6. shutil.which("python")
```

建议新增 `PythonEnvService`，避免把解释器查找逻辑继续堆在 `TaskRunner` 中：

```text
hy127web/worker/services/python_env_service.py
```

命名收敛前实际落点可以先放在当前 `code880web/worker/services/python_env_service.py`。职责：

- `list_interpreters()`：返回候选解释器列表。
- `get_selected_interpreter()`：返回当前实际使用的解释器。
- `set_project_interpreter(path)`：校验并写入 `.web-workbench/config.json`。
- `inspect_environment()`：返回 Python 版本、pip 可用性、虚拟环境状态、项目根目录。

`.web-workbench/config.json` 建议结构：

```json
{
  "python_path": "/abs/path/to/python",
  "updated_at": "2026-05-04T12:00:00",
  "source": "user"
}
```

`GET /api/python/interpreters` 返回示例：

```json
{
  "selected": {
    "path": "/home/user/project/.venv/bin/python",
    "source": ".venv",
    "exists": true,
    "version": "Python 3.12.10"
  },
  "candidates": [
    {
      "path": "/home/user/project/.venv/bin/python",
      "source": ".venv",
      "exists": true,
      "selected": true
    }
  ],
  "config_path": ".web-workbench/config.json"
}
```

#### 进程控制

当前使用 Windows 专属：

```python
subprocess.CREATE_NEW_PROCESS_GROUP
signal.CTRL_BREAK_EVENT
```

建议封装跨平台进程控制：

```text
Windows: CREATE_NEW_PROCESS_GROUP + CTRL_BREAK_EVENT
Linux: start_new_session=True + os.killpg
```

最小改造方式：

```python
import os
import signal
import subprocess
import sys


def build_popen_kwargs() -> dict:
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


async def stop_process(process):
    if sys.platform == "win32":
        os.kill(process.pid, signal.CTRL_BREAK_EVENT)
    else:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
```

`WorkerSupervisor.start_worker()` 也要做同样分支：

```python
if sys.platform == "win32":
    creation_flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    popen_kwargs = {"creationflags": creation_flags}
else:
    popen_kwargs = {"start_new_session": True}
```

阶段三第一步必须先修这些平台分支，再写 Ubuntu/dev 启动脚本；否则脚本能启动 Hub，也会在启动 Worker 或运行 Python 时失败。

#### 运行配置

建议增强 `.web-workbench/launch.json`：

```json
{
  "configurations": [
    {
      "name": "运行主程序",
      "type": "python",
      "program": "src/main.py",
      "args": [],
      "cwd": ".",
      "env": {}
    }
  ]
}
```

建议支持字段：

| 字段 | 说明 |
|---|---|
| `name` | 前端显示名称 |
| `type` | 初期只支持 `python`，保留后续 `module` / `command` |
| `program` | 相对项目根目录的 `.py` 文件 |
| `args` | 参数数组，不通过 shell 拼接 |
| `cwd` | 相对项目根目录工作目录，默认 `.` |
| `env` | 追加环境变量字典 |
| `timeout_seconds` | 单次运行超时，默认 300 |

运行命令必须继续使用 `asyncio.create_subprocess_exec`，不要改成 shell 字符串。所有 `program`、`cwd` 都必须复用路径边界校验。

### 7.10 建议新增 API

```text
GET  /api/python/interpreters
POST /api/python/interpreters/select
GET  /api/python/env
POST /api/python/install
GET  /api/run/history
POST /api/run/config
```

API 细节：

| API | 初期权限 | 说明 |
|---|---|---|
| `GET /api/python/interpreters` | 允许 | 返回当前选中解释器和候选列表 |
| `POST /api/python/interpreters/select` | 需要确认 | 校验解释器路径，写入项目级配置 |
| `GET /api/python/env` | 允许 | 返回版本、pip、venv、平台、项目配置 |
| `POST /api/python/install` | 强确认 | 只允许安装到选中解释器；记录日志；默认禁用网络直到用户确认 |
| `GET /api/run/history` | 允许 | 从 `.web-workbench/runs/` 返回最近运行记录 |
| `POST /api/run/config` | 需要确认 | 保存 launch 配置 |

`POST /api/python/install` 第一版建议只支持明确包名数组：

```json
{
  "packages": ["pandas", "openpyxl"],
  "upgrade": false
}
```

不要支持任意 pip 参数透传；需要额外参数时逐项白名单化。

### 7.11 验收标准

- Windows 和 Linux 都能识别解释器。
- 能运行 `src/main.py`。
- 能停止长时间运行的程序。
- 能查看历史运行日志。
- 运行报错能完整显示 traceback。
- 用户在 `.web-workbench/config.json` 中显式配置解释器后，优先使用该解释器，即使项目存在 `.venv`。
- Linux 上导入 Worker、Hub Supervisor、TaskRunner 不再因 Windows 专属常量崩溃。
- 停止长时间运行的子进程后，子进程组内的子进程也能被清理。
- 自动化检查建议：

```text
pytest code880web/tests/test_run_id.py
pytest code880web/tests/test_python_env_service.py
pytest code880web/tests/test_task_runner_cross_platform.py
```

## 阶段四：补齐 Git 开发辅助

目标：让用户知道自己改了什么，并能让 AI 基于改动辅助总结。

### 7.12 建议新增 Worker API

```text
GET  /api/git/available
GET  /api/git/status
GET  /api/git/diff
GET  /api/git/diff/{path}
GET  /api/git/branch
GET  /api/git/log
POST /api/git/add
POST /api/git/commit-message
```

初期只建议做只读能力：

- available
- status
- diff
- branch
- log

写操作如 add、commit 应放到后续，并加明确确认。

`GET /api/git/available` 是关键前置接口，返回：

```json
{
  "git_installed": true,
  "is_repo": true,
  "root": "/abs/path/to/repo",
  "branch": "master",
  "error": ""
}
```

如果 `is_repo=false`，前端 Git 面板直接置灰并显示空状态，不再逐个请求 `status` / `diff` / `log`。很多 Python 学习项目不是 Git 仓库，这个接口可以避免无意义的 500。

建议新增 `GitService`：

```text
hy127web/worker/services/git_service.py
```

命名收敛前实际落点可以先放在当前 `code880web/worker/services/git_service.py`。实现要求：

- 所有 Git 命令使用 `subprocess.run([...], cwd=project_root, shell=False)`。
- 每个命令设置短超时，例如 5 秒。
- 所有路径参数必须先通过 `validate_path`，并拒绝绝对路径。
- 不把任意用户字符串拼成 shell 命令。
- 仓库根目录必须通过 `git rev-parse --show-toplevel` 确认，且仍在 `project_root` 边界内。

只读接口建议响应结构：

```text
GET /api/git/status
-> branch, staged[], unstaged[], untracked[], conflicted[]

GET /api/git/diff
-> files[], truncated, summary, hunks_preview

GET /api/git/diff/{path}
-> path, diff, truncated

GET /api/git/log
-> commits[{hash, short_hash, subject, author, date}]
```

diff 限流规则：

- 默认返回 `git diff --stat` 摘要。
- 每个文件最多返回前 3 个 hunk。
- 总字符数默认限制 80 KB。
- 超限时设置 `truncated=true`，并提示用户按文件查看。
- AI 生成提交说明时使用 stat 摘要 + 每文件前 N 行 hunk，不直接灌入完整 diff。

### 7.13 前端建议

新增一个 Git 面板：

```text
已修改文件
未跟踪文件
当前分支
Diff 查看
AI 生成提交说明
```

前端状态：

- `git_installed=false`：提示未检测到 Git，隐藏 diff 操作。
- `git_installed=true && is_repo=false`：显示“当前项目不是 Git 仓库”，提供初始化建议，但不默认执行 `git init`。
- `is_repo=true`：显示分支、变更列表和 diff。
- 大 diff 默认折叠，按文件懒加载。
- “AI 生成提交说明”只生成草稿，不直接 commit。

### 7.14 验收标准

- 能显示当前分支。
- 能显示 modified/untracked 文件。
- 能查看单文件 diff。
- AI 能基于 diff 生成中文提交说明草稿。
- 非 Git 项目打开 Git 面板不会报错。
- 未安装 Git 时接口返回可解释状态，而不是抛出未处理异常。
- 大 diff 会截断并提示，不会阻塞 UI。
- 自动化检查建议：

```text
pytest code880web/tests/test_git_service.py
pytest code880web/tests/test_git_api.py
```

## 阶段五：把 AI 从聊天升级为编程助手

目标：让 AI 不只回答问题，而是能在用户授权下执行项目任务。

### 7.15 当前 AI 能力

当前 AI 能力是：

```text
用户选择打开的文件作为上下文
用户发送问题
Worker 构造 system prompt
Hub 注入 API Key
调用 OpenAI-compatible chat/completions
流式返回
```

这是“上下文聊天”，不是“编程 Agent”。

### 7.16 推荐工具化能力

应把 Worker 能力抽象为 AI 可调用工具：

```text
read_file(path)
write_file(path, content, base_sha256, task_id, iteration)
search_files(query)
list_tree(path, depth)
run_python(program, args)
get_run_log(run_id)
git_status()
git_diff(path)
preview_file(path)
```

工具接口不要直接暴露 FastAPI 路由给 AI。建议先做一层 `ToolRegistry`：

```text
hy127web/worker/services/ai_tools/
├── __init__.py
├── registry.py
├── file_tools.py
├── run_tools.py
├── git_tools.py
└── preview_tools.py
```

命名收敛前实际落点可以先放在当前 `code880web/worker/services/ai_tools/`。每个工具定义必须包含：

| 字段 | 说明 |
|---|---|
| `name` | 工具名 |
| `description` | 给模型看的简短说明 |
| `input_schema` | JSON Schema |
| `permission` | 默认权限级别 |
| `handler` | 实际执行函数 |
| `audit_fields` | 需要写入审计日志的字段 |

工具执行结果统一结构：

```json
{
  "ok": true,
  "data": {},
  "error": "",
  "audit_id": "task_abc_iter_1_tool_3"
}
```

`write_file` 必须强制携带 `task_id` 和 `iteration`。这两个字段用于：

- 审计本次写入属于哪个 AI 任务。
- 把写入归档到 `.web-workbench/task_snapshots/{task_id}/`。
- 任务失败后支持一键回滚。

`run_python` 第一版只能运行项目内 `.py` 文件或 launch 配置，不支持任意 shell。`git_diff` 默认走阶段四的 diff 限流规则。

### 7.17 推荐任务模式

右侧 AI 面板建议拆成：

```text
对话模式
任务模式
设置模式
```

对话模式：

- 只读上下文
- 不改文件
- 不运行命令

任务模式：

- AI 先生成计划
- 用户确认计划
- AI 读取文件
- AI 生成补丁
- 用户确认补丁
- Worker 写入文件
- AI 请求运行验证
- 用户确认运行
- AI 汇报结果

任务模式必须有明确的执行状态机：

```text
created
  -> planning
  -> waiting_plan_confirm
  -> reading_context
  -> proposing_patch
  -> waiting_patch_confirm
  -> applying_patch
  -> waiting_run_confirm
  -> running
  -> analyzing_result
  -> succeeded | failed | cancelled | rolled_back
```

每个任务建议结构：

```json
{
  "task_id": "task_20260504_001",
  "goal": "修复运行错误",
  "status": "running",
  "iteration": 2,
  "max_iterations": 5,
  "created_at": "2026-05-04T12:00:00",
  "permissions": {
    "write_file": "confirm",
    "run_python": "confirm",
    "network": "strong_confirm"
  }
}
```

失败修复循环必须设置上限：

```text
AI 生成补丁
-> 用户确认
-> 写入
-> 运行
-> 失败
-> AI 分析日志
-> 下一轮补丁
```

默认 `max_iterations=5`。达到上限后停止自动推进，要求用户明确选择继续、回滚或结束。不要让 AI 无限循环修改代码。

快照和回滚要求：

- 任务开始前创建基线快照：`.web-workbench/task_snapshots/{task_id}/baseline/`。
- 每轮写入前创建迭代快照：`.web-workbench/task_snapshots/{task_id}/iter_{N}/`。
- 如果项目是 Git 仓库，可以额外记录 `git diff`；不要默认执行 `git stash`，避免影响用户未提交工作区。
- 任务结束后前端提供“回滚到任务开始前”按钮。
- 回滚前展示将被恢复的文件列表，并要求强确认。

审计日志建议写入：

```text
.web-workbench/tasks/{task_id}.jsonl
```

每行记录一次事件：计划、用户确认、工具调用、文件写入、运行结果、回滚。

设置模式：

- 模型配置
- 运行方式
- 权限配置

### 7.18 权限模型

建议采用最小权限：

| 操作 | 默认权限 |
|---|---|
| 读取文件 | 允许，但限制在项目目录 |
| 搜索文件 | 允许，但限制结果数量 |
| 写文件 | 需要用户确认 |
| 删除文件 | 强确认 |
| 运行 Python | 需要用户确认 |
| 安装依赖 | 强确认 |
| 网络访问（pip / requests / 自定义 URL） | 强确认 |
| Git commit | 强确认 |
| 任意 shell 命令 | 默认禁用或强确认 |

权限规则：

- 对话模式默认只读。
- 任务模式可以申请写入、运行、网络等权限，但每类高风险操作都要单独确认。
- 权限确认需要显示操作对象，例如文件路径、运行入口、包名、URL。
- 用户可以对单次操作确认，也可以对当前任务的同类操作临时授权。
- 所有确认结果写入任务审计日志。
- 默认禁用任意 shell；即使后续开放，也必须通过白名单或强确认。

### 7.19 AI Runtime 分层

建议设计统一接口：

```python
class AIRuntime:
    async def chat(self, messages, tools=None, model=None, stream=True):
        ...

    async def run_task(self, task, tools, permissions, callbacks):
        ...
```

可实现：

```text
DirectHttpRuntime
OpenAISDKRuntime
OpenAIAgentsRuntime
ClaudeCliRuntime
CodexCliRuntime
QwenCliRuntime
```

这样不会把系统绑死在某一个模型或 CLI 上。

建议把 `AIRuntime` 抽象骨架提前到 P1 完成，即使阶段五任务模式还没完整实现，也先把当前 direct API 调用迁入首个实现：

```text
hy127web/hub/ai_runtime/
├── __init__.py
├── base.py
├── direct_http.py
└── errors.py
```

职责划分：

- Hub 仍负责模型配置、API Key 解密和外部模型调用。
- Worker 负责项目工具、权限检查、审计和上下文读取。
- Runtime 只负责“如何和模型说话”，不直接读写项目文件。
- CLI Runtime 后续作为可插拔实现，不替代 Hub + Worker 本体。

`DirectHttpRuntime` 第一版继续兼容 OpenAI-compatible `/chat/completions`。`OpenAISDKRuntime` 后续再接 OpenAI SDK / Responses API。这样阶段五做工具调用时，不需要大幅重写现有 `ai_service.py`。

### 7.20 验收标准

- AI 能读取指定文件并解释代码。
- AI 能基于用户确认修改文件。
- 修改前能展示 diff。
- 修改后能运行测试或运行入口文件。
- AI 能基于运行结果继续修复。
- 所有写入和执行动作都有日志。
- 达到 `max_iterations` 后任务停止，并要求用户选择下一步。
- 每轮写入前都有快照，任务可一键回滚到开始前状态。
- 网络访问和安装依赖需要强确认。
- `write_file` 审计记录包含 `task_id`、`iteration`、路径、旧 sha、新 sha。
- 大 diff、大日志会截断并提示，不会全部塞进模型上下文。
- 自动化检查建议：

```text
pytest code880web/tests/test_ai_tools.py
pytest code880web/tests/test_task_snapshots.py
pytest code880web/tests/test_ai_task_permissions.py
pytest code880web/tests/test_ai_runtime_base.py
```

## 阶段六：跨平台开发启动能力

目标：让该项目不仅能在 Windows 一键安装环境运行，也能在 Ubuntu 服务器开发调试。

### 7.21 当前限制

当前正式启动流程依赖 Windows：

- `启动Web工作台.bat`
- `启动Web工作台.ps1`
- `%LOCALAPPDATA%`
- `.venv\Scripts\python.exe`
- `subprocess.CREATE_NO_WINDOW`
- `subprocess.CREATE_NEW_PROCESS_GROUP`
- `signal.CTRL_BREAK_EVENT`

在 Ubuntu 上直接运行不只是行为不对，部分路径会因为 Windows 专属常量不存在而崩溃。因此阶段六的前置任务不是先写启动脚本，而是先修 `TaskRunner` 和 `WorkerSupervisor` 的跨平台进程分支。

前置修复顺序：

```text
1. 修复 WorkerSupervisor.start_worker() 的 subprocess 平台分支
2. 修复 TaskRunner.start_run() 的 subprocess 平台分支
3. 修复 TaskRunner.stop_run() 的 Windows / Linux 进程组停止逻辑
4. 修复解释器查找顺序和 Linux/macOS .venv/bin/python 支持
5. 再新增 Ubuntu/dev 启动脚本
```

### 7.22 建议新增开发启动脚本

建议新增：

```text
scripts/dev_start_web.py
```

职责：

- 设置 `HY127WEB_INSTALL_ROOT`
- 设置 `HY127WEB_PYTHON_PATH`
- 设置 `HY127WEB_GLOBAL_DIR`
- 过渡期同时设置当前代码仍读取的 `CODE880WEB_INSTALL_ROOT`、`CODE880WEB_PYTHON_PATH`、`CODE880WEB_GLOBAL_DIR`
- 启动 Hub
- 读取 runtime
- 读取 launch token
- 注册当前项目
- 输出 bootstrap URL
- 不自动打开 GUI 浏览器

### 7.23 Ubuntu 本地浏览器访问方式

服务器上启动后，仍然建议 Hub 只监听：

```text
127.0.0.1:{port}
```

本地电脑通过 SSH 隧道访问：

```powershell
ssh -L 18800:127.0.0.1:8800 ubuntu@服务器IP
```

然后本地浏览器打开：

```text
http://127.0.0.1:18800/bootstrap?code=...
```

### 7.24 验收标准

- Ubuntu 上能启动 Hub。
- Ubuntu 上能启动 Worker。
- 本地 Windows 浏览器能通过 SSH 隧道访问。
- 页面能显示项目文件树。
- 能打开 `src/main.py`。
- 能运行 `src/main.py` 并看到输出。
- Linux 上导入 `TaskRunner` 和 `WorkerSupervisor` 不报 Windows 常量错误。

## 8. 推荐开发优先级

综合收益和风险，建议优先级如下：

| 优先级 | 项目 | 原因 |
|---|---|---|
| P0-1 | 命名收敛方案 | 后续新增代码统一 Hy127，旧 `code880` 命名只做兼容迁移 |
| P0-2 | subprocess 跨平台修补 | 当前 Linux 上 Worker 启动和运行路径会因 Windows 常量失败 |
| P0-3 | Python 解释器查找顺序修正 | 项目级显式配置必须优先于 `.venv`，并支持 Linux/macOS |
| P0-4 | Ubuntu/dev 启动脚本 | 依赖前两项，脚本本身不是第一步 |
| P0 | Monaco 编辑保存 | 没有编辑闭环就不是开发工作台 |
| P1 | 文件新建/删除/重命名 | 基础项目维护必需 |
| P1 | Git status/diff | 真实开发必需 |
| P1 | AIRuntime 抽象骨架 | 成本低，能避免阶段五再大改 AI 调用链 |
| P2 | AI 工具调用 | 从聊天升级到编程助手 |
| P2 | OpenAI SDK Runtime | 标准化模型调用 |
| P3 | Claude/Codex CLI Runtime | 作为可选增强，不应先替代本体 |

## 9. 建议的近期实施清单

### 9.1 第一批改动

建议第一批只做“可访问、可编辑、可运行”：

```text
1. 明确 Hy127 命名收敛清单，新增代码不再使用 code880 命名
2. 修复 WorkerSupervisor 的跨平台 subprocess flags
3. 修复 TaskRunner 的跨平台启动和停止进程逻辑
4. 修复 TaskRunner / PythonEnvService 的解释器查找顺序
5. 新增 Ubuntu/dev 启动脚本
6. 前端 Monaco 改为可编辑
7. 前端接入 /api/files/save
8. 增加 Ctrl+S 保存
```

### 9.2 第二批改动

```text
1. 新建文件
2. 新建目录
3. 重命名
4. 删除
5. 内容搜索
6. Git status
7. Git diff
8. AIRuntime 抽象骨架
```

### 9.3 第三批改动

```text
1. AI 工具接口抽象
2. OpenAI SDK Runtime
3. 任务模式 UI
4. 补丁确认机制
5. 运行验证闭环
```

## 10. 风险和注意事项

### 10.1 不要过早把系统变成某个模型的壳

如果先接 Claude/Codex，而不完善 Worker 工具能力，系统会变成：

```text
Web 页面只是 CLI 输出显示器
```

这会削弱 Hy127 自己的产品价值。

更稳妥的做法是：

```text
先做强 Hy127 Worker 工具
再让不同 AI Runtime 调这些工具
```

### 10.2 文件写入必须严格控制

文件写入必须满足：

- 路径边界校验
- 版本冲突校验
- 写入前备份
- AI 写入前用户确认
- 写入后可查看 diff

### 10.3 命令执行要谨慎

运行 Python 文件是合理能力，但任意 shell 命令风险更高。

建议分级：

```text
运行当前 .py              默认允许或轻确认
运行 launch.json 配置     轻确认
pip install               强确认
任意 shell                默认禁用或强确认
删除文件                  强确认
Git commit/push           强确认
```

### 10.4 不要直接暴露公网

该工作台具备读写文件和运行代码能力，只应默认监听：

```text
127.0.0.1
```

远程访问建议使用 SSH 隧道，不建议直接绑定 `0.0.0.0` 暴露公网。

代码层建议做成硬约束：

- Hub 默认只允许 `127.0.0.1`。
- 如果配置为非 `127.0.0.1` 或 `localhost`，开发启动脚本必须拒绝启动，除非用户显式传入强确认参数。
- Worker 永远只监听 `127.0.0.1`，不接受外部绑定。
- 前端和后端错误提示都应建议使用 SSH 隧道，而不是改成公网监听。

## 11. 最终建议

本项目的正确演进方向是：

```text
Hy127 Web 工作台本体
  -> 做强项目文件、运行、预览、Git、环境能力
  -> 把这些能力抽象成稳定工具
  -> 接入 OpenAI SDK / Agents SDK / Claude CLI / Codex CLI 等运行时
  -> 形成可控、可验证、可审计的 Python 编程辅助系统
```

一句话总结：

> OpenAI SDK 和 Claude 壳子是可替换的大脑，Hy127 Hub + Worker + 路由 + 文件/运行 API 才是这个 Python 编程工作台真正的身体。

因此，近期不建议把主要精力放在“套 Claude 壳子”上。更应该先把本体打牢：

```text
能启动
能看文件
能编辑保存
能运行 Python
能看日志
能看 Git diff
AI 能在用户确认下读写和验证
```

这些完成后，接 OpenAI、Claude、Codex、Qwen 都会更自然，也更可控。
