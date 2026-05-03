# Code880 Web Python 编程辅助工作台优化方案

生成日期：2026-05-03  
适用项目：`hy127v5.11_PythonWeb`  
核心对象：`hy127web` 本地 Web 工作台

## 1. 结论先行

本项目当前的 `hy127web` 不是简单的“OpenAI SDK 调用示例”，也不是“Claude 壳子”。它更准确的定位是：

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

项目根目录中和 Web 工作台直接相关的核心结构如下：

```text
hy127v5.11_PythonWeb/
├── hy127web/
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

- `hy127web` 是 Web 工作台本体。
- `src/一键安装卸载.py` 负责 Windows 一键安装环境，并部署 `hy127web`。
- `启动Web工作台.ps1` 是 Windows 下正式启动路径。
- `方案设计/WEB端迁移方案_最终整合版_v4.md` 是当前设计基准。

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

前端是 `hy127web/static/index.html` 中的单页应用，当前使用：

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
| Code880 Web 路由架构 | 应用本体层 | 本地 Web 工作台 | 如何浏览、运行、管理 Python 项目 |
| OpenAI SDK | 模型调用层 | 官方 API 客户端 | 如何规范调用 OpenAI API |
| Claude 壳子 | 外部 Agent 适配层 | 调用 Claude CLI 的包装 | 如何把任务交给 Claude CLI 执行 |

更直观地说：

```text
Code880 Web = 工作台骨架和手脚
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

这些仍然需要 Code880 Web 自己实现。

### 4.4 Claude 壳子的价值和风险

Claude 壳子通常是指：

```text
Code880
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

因此 Claude/Codex/Qwen/Gemini CLI 更适合作为可插拔运行时，而不是替代 Code880 Web 的 Hub/Worker 架构。

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
| Linux 兼容不足 | Worker 启动和运行有 Windows 专属代码 | Ubuntu 服务器上无法原样完整启动 |

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

建议改造 `hy127web/static/index.html`：

- 将 Monaco `readOnly: true` 改为可编辑。
- 监听内容变化，标记文件为 dirty。
- 文件 Tab 显示未保存标记。
- 支持 `Ctrl+S` 保存当前文件。
- 保存时提交 `path`、`content`、`base_sha256`。
- 保存成功后更新 `sha256`。
- 保存失败时提示冲突，不静默覆盖。

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
- 删除操作默认只允许项目根目录内文件
- 删除目录时必须显式确认
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

### 7.9 需要优化的点

#### 解释器识别

当前偏 Windows：

```text
.venv/Scripts/python.exe
```

建议兼容：

```text
.venv/Scripts/python.exe       # Windows
.venv/bin/python               # Linux/macOS
.web-workbench/config.json
install.json 中 python_path
当前 sys.executable
python3
python
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

### 7.10 建议新增 API

```text
GET  /api/python/interpreters
GET  /api/python/env
POST /api/python/install
GET  /api/run/history
POST /api/run/config
```

### 7.11 验收标准

- Windows 和 Linux 都能识别解释器。
- 能运行 `src/main.py`。
- 能停止长时间运行的程序。
- 能查看历史运行日志。
- 运行报错能完整显示 traceback。

## 阶段四：补齐 Git 开发辅助

目标：让用户知道自己改了什么，并能让 AI 基于改动辅助总结。

### 7.12 建议新增 Worker API

```text
GET  /api/git/status
GET  /api/git/diff
GET  /api/git/diff/{path}
GET  /api/git/branch
GET  /api/git/log
POST /api/git/add
POST /api/git/commit-message
```

初期只建议做只读能力：

- status
- diff
- branch
- log

写操作如 add、commit 应放到后续，并加明确确认。

### 7.13 前端建议

新增一个 Git 面板：

```text
已修改文件
未跟踪文件
当前分支
Diff 查看
AI 生成提交说明
```

### 7.14 验收标准

- 能显示当前分支。
- 能显示 modified/untracked 文件。
- 能查看单文件 diff。
- AI 能基于 diff 生成中文提交说明草稿。

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
write_file(path, content, base_sha256)
search_files(query)
list_tree(path, depth)
run_python(program, args)
get_run_log(run_id)
git_status()
git_diff(path)
preview_file(path)
```

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
| Git commit | 强确认 |
| 任意 shell 命令 | 默认禁用或强确认 |

### 7.19 AI Runtime 分层

建议设计统一接口：

```python
class AIRuntime:
    async def chat(self, messages, tools=None, model=None):
        ...

    async def run_task(self, task, tools, permissions):
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

### 7.20 验收标准

- AI 能读取指定文件并解释代码。
- AI 能基于用户确认修改文件。
- 修改前能展示 diff。
- 修改后能运行测试或运行入口文件。
- AI 能基于运行结果继续修复。
- 所有写入和执行动作都有日志。

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

在 Ubuntu 上直接运行会有兼容问题。

### 7.22 建议新增开发启动脚本

建议新增：

```text
scripts/dev_start_web.py
```

职责：

- 设置 `hy127web_INSTALL_ROOT`
- 设置 `hy127web_PYTHON_PATH`
- 设置 `hy127web_GLOBAL_DIR`
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

## 8. 推荐开发优先级

综合收益和风险，建议优先级如下：

| 优先级 | 项目 | 原因 |
|---|---|---|
| P0 | Linux/dev 启动适配 | 当前你在 Ubuntu 服务器上开发，需要先能呈现 |
| P0 | Monaco 编辑保存 | 没有编辑闭环就不是开发工作台 |
| P1 | 文件新建/删除/重命名 | 基础项目维护必需 |
| P1 | Python 解释器跨平台识别 | Python 项目运行稳定性基础 |
| P1 | Git status/diff | 真实开发必需 |
| P2 | AI 工具调用 | 从聊天升级到编程助手 |
| P2 | OpenAI SDK Runtime | 标准化模型调用 |
| P3 | Claude/Codex CLI Runtime | 作为可选增强，不应先替代本体 |

## 9. 建议的近期实施清单

### 9.1 第一批改动

建议第一批只做“可访问、可编辑、可运行”：

```text
1. 新增 Ubuntu/dev 启动脚本
2. 修复 WorkerSupervisor 的跨平台 subprocess flags
3. 修复 TaskRunner 的跨平台 Python 解释器查找
4. 修复 TaskRunner 的跨平台停止进程逻辑
5. 前端 Monaco 改为可编辑
6. 前端接入 /api/files/save
7. 增加 Ctrl+S 保存
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

这会削弱 Code880 自己的产品价值。

更稳妥的做法是：

```text
先做强 Code880 Worker 工具
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

## 11. 最终建议

本项目的正确演进方向是：

```text
Code880 Web 工作台本体
  -> 做强项目文件、运行、预览、Git、环境能力
  -> 把这些能力抽象成稳定工具
  -> 接入 OpenAI SDK / Agents SDK / Claude CLI / Codex CLI 等运行时
  -> 形成可控、可验证、可审计的 Python 编程辅助系统
```

一句话总结：

> OpenAI SDK 和 Claude 壳子是可替换的大脑，Code880 Hub + Worker + 路由 + 文件/运行 API 才是这个 Python 编程工作台真正的身体。

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
