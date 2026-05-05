# Hy127 Web Python 编程辅助工作台优化方案复核修复清单

生成日期：2026-05-05  
复核对象：`方案设计/Hy127_Web_Python编程辅助工作台优化方案.md`  
项目根目录：`/home/ubuntu/hy127v5.11_PythonWeb`

## 0. 复核基线

当前方案文档仍可作为架构方向参考，但已经不能直接作为开发执行清单。主要原因是文档写于早期状态，而当前仓库已经落地了部分能力：

- 前端已接入 Monaco 可编辑、dirty 标记和 `/api/files/save`。
- Worker 已有文件管理 API：create、mkdir、rename、delete、copy。
- Worker 已有 PythonEnvService 和解释器 API。
- Worker 已有 GitService 和 Git 只读 API。
- Hub 已有 `ai_runtime` 抽象骨架和 `DirectHttpRuntime`。
- 已有 `scripts/dev_start_web.py` 开发启动脚本。

因此第一步不是继续按原 P0/P1 重复开发，而是先修正方案状态、补齐真实缺口、建立回归测试。

优先级定义：

| 优先级 | 含义 |
|---|---|
| P0 | 已影响核心功能或会误导后续开发，必须先处理 |
| P1 | 基础能力已存在，但需要补安全、兼容性、测试或产品闭环 |
| P2 | 下一阶段增强能力，需要先完成 API 合同和最小实现 |
| P3 | 长线增强，不应阻塞当前可用工作台 |

## 1. P0 修复项

### P0-1 修复 AI 流式协议错配

问题：

Hub `/internal/ai/relay` 已把模型流规范化成：

```json
{"type": "content", "data": "文本片段"}
```

位置：`code880web/hub/app.py` 的 `_stream_sse()`。

但 Worker `AIService.chat_stream()` 仍按 OpenAI 原始格式解析：

```python
delta = chunk["choices"][0].get("delta", {})
content = delta.get("content", "")
```

这会导致 Worker 吞掉 Hub 返回的正常内容，前端只拿到空 assistant 消息。

修复文件：

- `code880web/worker/services/ai_service.py`

建议修改 `chat_stream()` 中 `async for line in resp.aiter_lines()` 的解析分支：

```python
chunk = json.loads(data_str)

# Hub relay normalized format
if chunk.get("type") == "content":
    content = chunk.get("data", "")
elif chunk.get("type") == "error":
    err = chunk.get("data", "AI relay error")
    yield json.dumps({"type": "error", "data": err}, ensure_ascii=False) + "\n"
    return
else:
    # Provider raw OpenAI-compatible fallback, kept for compatibility
    delta = chunk.get("choices", [{}])[0].get("delta", {})
    content = delta.get("content", "")

if content:
    full_response += content
    yield json.dumps({"type": "content", "data": content}, ensure_ascii=False) + "\n"
```

同步补测试：

- 新增 `code880web/tests/test_ai_service.py`
- 覆盖 Hub relay normalized chunk：`data: {"type":"content","data":"hello"}`
- 覆盖 relay error：`data: {"type":"error","data":"bad key"}`
- 覆盖 `[DONE]`

验收：

```text
配置一个 OpenAI-compatible 模型后，右侧 AI 对话能流式显示内容，而不是空响应。
```

### P0-2 修复 Worker 读取 Hub runtime 路径不兼容

问题：

`scripts/dev_start_web.py` 设置了：

```python
HY127WEB_GLOBAL_DIR=/项目/.hy127web_global
CODE880WEB_GLOBAL_DIR=/项目/.hy127web_global
```

但 Worker 的 `_read_hub_base_url()` 只读：

```python
os.path.join(os.environ.get("LOCALAPPDATA", ""), "Code880Web", "hub_runtime.json")
```

Linux/Ubuntu 开发启动时，`LOCALAPPDATA` 为空，Worker 读不到 `.hy127web_global/hub_runtime.json`，进而 `AIService.hub_base_url` 为空，AI 对话会报“Hub 地址未配置”。

修复文件：

- `code880web/worker/app.py`
- `code880web/hub/config.py`
- `code880web/worker/services/task_runner.py`
- `code880web/worker/services/python_env_service.py`

建议先在 `code880web/hub/config.py` 增加统一目录解析函数：

```python
def first_env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def get_global_dir() -> str:
    override = first_env("HY127WEB_GLOBAL_DIR", "CODE880WEB_GLOBAL_DIR")
    if override:
        return override

    # Windows installed compatibility
    localappdata = os.environ.get("LOCALAPPDATA", "").strip()
    if localappdata:
        hy127_dir = os.path.join(localappdata, "Hy127Web")
        code880_dir = os.path.join(localappdata, "Code880Web")
        if os.path.exists(hy127_dir):
            return hy127_dir
        return code880_dir

    # Linux/macOS dev fallback
    state_home = os.environ.get("XDG_STATE_HOME", "").strip()
    if not state_home:
        state_home = os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(state_home, "hy127web")
```

然后 `worker/app.py` 中改成使用同一候选目录：

```python
def _read_hub_base_url() -> str:
    candidates = []
    for env_name in ("HY127WEB_GLOBAL_DIR", "CODE880WEB_GLOBAL_DIR"):
        value = os.environ.get(env_name, "").strip()
        if value:
            candidates.append(value)

    localappdata = os.environ.get("LOCALAPPDATA", "").strip()
    if localappdata:
        candidates.append(os.path.join(localappdata, "Hy127Web"))
        candidates.append(os.path.join(localappdata, "Code880Web"))

    state_home = os.environ.get("XDG_STATE_HOME", "").strip()
    if not state_home:
        state_home = os.path.join(os.path.expanduser("~"), ".local", "state")
    candidates.append(os.path.join(state_home, "hy127web"))

    for global_dir in candidates:
        runtime_path = os.path.join(global_dir, "hub_runtime.json")
        if os.path.isfile(runtime_path):
            with open(runtime_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("base_url", "")
    return ""
```

同时把 `TaskRunner.detect_python()` 和 `PythonEnvService.list_interpreters()` 中只读 `CODE880WEB_GLOBAL_DIR` 的逻辑改为先读 `HY127WEB_GLOBAL_DIR`，再兼容 `CODE880WEB_GLOBAL_DIR`。

验收：

```text
python scripts/dev_start_web.py --port 8800
打开工作台，AIService 不再返回 “Hub 地址未配置”。
```

### P0-3 给 AI 上下文文件增加路径边界校验

问题：

`AIService.set_context_files()` 当前直接保存前端传入的路径，`_build_context()` 直接：

```python
abs_path = os.path.join(self.project_root, rel_path)
```

没有复用 `validate_path()`。恶意请求可以传入 `../`，在某些部署/代理条件下存在越界读取风险。

修复文件：

- `code880web/worker/services/ai_service.py`

建议代码：

```python
from .security import validate_path


def set_context_files(self, files: list[str]):
    safe_files = []
    for rel_path in files:
        if not isinstance(rel_path, str):
            continue
        if not validate_path(self.project_root, rel_path):
            continue
        abs_path = os.path.join(self.project_root, rel_path)
        if os.path.isfile(abs_path):
            safe_files.append(rel_path.replace("\\", "/"))
    self._context_files = safe_files[:50]


def _build_context(self) -> str:
    parts = []
    for rel_path in self._context_files:
        if not validate_path(self.project_root, rel_path):
            continue
        abs_path = os.path.join(self.project_root, rel_path)
        if not os.path.isfile(abs_path):
            continue
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(50000)
        parts.append(f"=== {rel_path} ===\n{content}")
    return "\n\n".join(parts)
```

同步补测试：

- `test_ai_service_rejects_context_traversal`
- `test_ai_service_limits_context_file_count`
- `test_ai_service_skips_missing_context_file`

验收：

```text
POST /api/ai/context {"files":["../secret.txt"]} 不会进入上下文列表。
```

### P0-4 先修方案文档基线，避免重复开发

问题：

原方案第 6.2、7、8、9 节仍把已实现项写成“当前短板”或“建议新增”，会直接误导后续开发。

修复文件：

- `方案设计/Hy127_Web_Python编程辅助工作台优化方案.md`

建议新增一个“当前代码基线”表，放在第 6 节前或替换第 6.2 表：

```markdown
| 能力 | 方案原判断 | 当前代码事实 | 后续动作 |
|---|---|---|---|
| Monaco 编辑保存 | 未打通 | 已有 dirty、Ctrl+S、/api/files/save | 补 beforeunload、E2E 测试、服务端大文件限制 |
| 文件管理 | 缺少 API | 已有 create/mkdir/rename/delete/copy | 补 rename 叶子名校验、强确认、前端体验 |
| Python 环境 | 缺解释器 API | 已有 PythonEnvService 和 3 个 API | 补 install/history/config |
| Git 辅助 | 缺 status/diff | 已有 GitService 和只读 API | 补未跟踪文件 diff、错误状态、前端面板完整性 |
| AIRuntime | 建议新增 | 已有 base/direct_http/errors | 修 chat relay 协议，补测试 |
| Ubuntu dev 启动 | 建议新增 | 已有 scripts/dev_start_web.py | 修 runtime 路径和依赖验证 |
```

同时重排第 8 节优先级：

```markdown
P0:
- AI relay 协议错配
- Worker runtime 路径兼容
- AI context 路径校验
- 方案状态重基线
- 测试环境可运行

P1:
- 文件服务安全加固
- 前端未保存变更保护
- GitService 边界和 diff 完整性
- PythonEnvService 与 TaskRunner 去重
- run history / run config
```

验收：

```text
方案文档中不再把已落地能力写成“建议新增”。
```

### P0-5 恢复本地测试可运行能力

问题：

当前环境执行：

```text
python3 -m pytest code880web/tests/test_security.py
```

失败：

```text
No module named pytest
```

路由导出也因缺少 `fastapi` 无法导入。后续所有修复都缺少基本验证闭环。

修复方式：

1. 明确项目依赖安装入口。
2. 不把 `.venv` 提交到仓库。
3. 增加一条开发环境检查脚本或文档。

建议新增脚本：

- `scripts/dev_check.py`

最小实现：

```python
import importlib.util
import sys

required = ["fastapi", "uvicorn", "httpx", "pytest"]
missing = [name for name in required if importlib.util.find_spec(name) is None]
if missing:
    print("Missing Python packages:", ", ".join(missing))
    print("Suggested:")
    print("  python -m pip install -r code880web/requirements.txt pytest")
    sys.exit(1)
print("dev dependencies ok")
```

验证命令：

```text
python3 scripts/dev_check.py
python3 -m pytest code880web/tests/test_security.py
python3 scripts/export_routes.py --check
```

## 2. P1 修复项

### P1-1 加固 FileService 的服务端写入和重命名校验

当前前端已经限制大文件编辑：

```javascript
const largeFile = (file.size || 0) > MAX_EDITABLE_SIZE;
const readOnly = largeFile || !file.editable;
```

但后端 `save_file()` 仍没有服务端大小限制。API 不能完全依赖前端。

修复文件：

- `code880web/worker/services/file_service.py`

建议增加常量：

```python
MAX_TEXT_SAVE_BYTES = 2 * 1024 * 1024
```

在 `save_file()` 中写入前校验：

```python
raw = content.encode("utf-8")
if len(raw) > MAX_TEXT_SAVE_BYTES:
    raise ValueError("文件超过 2 MB，禁止通过 Web 编辑保存")
```

`rename()` 当前允许 `new_name` 中带路径分隔符，只要最终路径仍在项目根目录。重命名语义应只接受叶子文件名。

建议新增：

```python
def _check_leaf_name(self, name: str):
    if not name or not name.strip():
        raise ValueError("名称不能为空")
    if "/" in name or "\\" in name:
        raise ValueError("名称不能包含路径分隔符")
    if name in (".", ".."):
        raise ValueError("名称不合法")
    if "\0" in name:
        raise ValueError("名称不能包含空字符")
```

并在 `rename()` 开头调用：

```python
self._check_leaf_name(new_name)
```

同步补测试：

- `test_rename_rejects_path_separator`
- `test_save_rejects_large_content`
- `test_delete_rejects_protected_case_insensitive`

### P1-2 增加前端未保存变更的全局保护

当前 `closeFile()` 对单文件关闭有确认，但返回项目列表、浏览器刷新、关闭标签页仍需补全局保护。

修复文件：

- `code880web/static/index.html`

建议新增函数：

```javascript
function hasDirtyFiles() {
  return openFiles.value.some(f => f._dirty);
}

function confirmLeaveDirty() {
  if (!hasDirtyFiles()) return true;
  return confirm('当前有未保存的文件，确定离开吗？');
}
```

在返回项目列表逻辑中调用：

```javascript
function backToProjects() {
  if (!confirmLeaveDirty()) return;
  if (runWs) runWs.close();
  currentView.value = 'projects';
  history.pushState(null, '', '/');
}
```

增加 browser unload 保护：

```javascript
function handleBeforeUnload(e) {
  if (!hasDirtyFiles()) return;
  e.preventDefault();
  e.returnValue = '';
}

window.addEventListener('beforeunload', handleBeforeUnload);
```

如果后续改成 Vue `onMounted/onBeforeUnmount`，要在卸载时移除监听：

```javascript
window.removeEventListener('beforeunload', handleBeforeUnload);
```

同步补 E2E：

- 打开文件，修改不保存，刷新页面应触发浏览器离开提示。
- 修改文件 A，切换到文件 B，回到 A 内容仍在编辑缓冲。

### P1-3 统一 PythonEnvService 和 TaskRunner 的解释器选择逻辑

问题：

`PythonEnvService` 已实现解释器发现，但 `TaskRunner.detect_python()` 仍有一套独立逻辑。双逻辑容易在后续 HY127/CODE880 环境变量迁移时分叉。

修复文件：

- `code880web/worker/services/task_runner.py`
- `code880web/worker/services/python_env_service.py`

建议在 `TaskRunner.detect_python()` 中改用服务：

```python
from .python_env_service import PythonEnvService


def detect_python(self) -> str:
    selected = PythonEnvService(self.project_root).get_selected_interpreter()
    path = selected.get("path", "")
    if selected.get("exists") and path:
        return path
    if path:
        return path
    return "python"
```

然后删除 `TaskRunner.detect_python()` 中重复读取 `.web-workbench/config.json`、`.venv`、`install.json`、`sys.executable` 的代码。

同步补测试：

- `TaskRunner.detect_python()` 显式配置优先于 `.venv`。
- Linux 下 `.venv/bin/python` 优先于 `sys.executable`。
- 配置路径失效时能回退并返回诊断。

### P1-4 补齐运行历史和运行配置 API

方案列了以下 API，但当前 Worker 还没有对应实现：

```text
GET  /api/run/history
POST /api/run/config
```

修复文件：

- `code880web/worker/app.py`
- `code880web/worker/services/task_runner.py`
- 新增 `code880web/worker/services/run_config_service.py`

建议 `GET /api/run/history` 从 `.web-workbench/runs/*.log` 和 `TaskRunner.completed_tasks` 返回：

```json
{
  "runs": [
    {
      "run_id": "deadbeef",
      "file": "src/main.py",
      "exit_code": 0,
      "elapsed": 1.2,
      "log_path": ".web-workbench/runs/deadbeef.log",
      "finished_at": "2026-05-05T10:00:00"
    }
  ]
}
```

建议 `POST /api/run/config` 只允许保存项目内 `.web-workbench/launch.json`：

```python
class RunConfigService:
    CONFIG_REL_PATH = ".web-workbench/launch.json"

    def save(self, config: dict) -> dict:
        configurations = config.get("configurations", [])
        for item in configurations:
            if item.get("type") != "python":
                raise ValueError("当前只支持 python 类型")
            program = item.get("program", "")
            if not validate_path(self.project_root, program) or not program.endswith(".py"):
                raise ValueError("program 不合法")
            args = item.get("args", [])
            if not isinstance(args, list) or not all(isinstance(x, str) for x in args):
                raise ValueError("args 必须是字符串数组")
        ...
```

### P1-5 GitService 边界和 diff 完整性补强

当前 GitService 已实现只读 API，但还需要补几个细节。

修复文件：

- `code880web/worker/services/git_service.py`

建议增加统一命令 helper，减少重复：

```python
def _run_git(self, args: list[str], *, timeout: int = 5, text: bool = True):
    return subprocess.run(
        ["git", *args],
        cwd=self.project_root,
        capture_output=True,
        text=text,
        timeout=timeout,
        shell=False,
    )
```

修复 `_is_within_project()` 捕获异常范围：

```python
def _is_within_project(self, repo_root: str) -> bool:
    try:
        Path(repo_root).resolve().relative_to(Path(self.project_root).resolve())
        return True
    except (ValueError, OSError):
        return False
```

修复 `git status --porcelain` rename 路径显示：

```python
fname = line[3:].strip()
if " -> " in fname:
    old_name, new_name = fname.split(" -> ", 1)
    fname = new_name
```

补单文件 diff 的 `--` 已有，但建议对空 path 明确分支，避免未来改动拼接 shell。

补未跟踪文件展示策略：

- `status()` 已返回 `untracked`。
- `diff()` 当前 `git diff` 不包含 untracked 内容，这是合理的，但前端和提交说明必须明确“未跟踪文件不含 diff 内容”。
- 如果要支持未跟踪文本预览，应通过 `FileService.read_file()` 限制大小后展示，而不是 `git diff`。

同步补测试：

- rename 状态解析。
- repo root 不在项目内时 `available()` 返回 `is_repo=false`。
- 大 diff 截断不超过 80 KB。

### P1-6 命名收敛必须先做兼容层，不要一次性大重命名

问题：

当前仍有大量 `code880` 命名存在于包名、Cookie、Header、安装器、PowerShell、测试和模型密钥描述中。直接把目录 `code880web/` 改成 `hy127web/` 会破坏导入、安装和已有用户状态。

修复策略：

1. 第一阶段只加 HY127 环境变量兼容，不改包名。
2. 第二阶段新增 `hy127web` 包别名或迁移目录。
3. 第三阶段迁移 Cookie/Header，全程兼容旧 Cookie/Header。

第一阶段代码细节：

- `code880web/hub/config.py`：所有环境变量读取都用 `HY127WEB_*` 优先，`CODE880WEB_*` 兜底。
- `scripts/dev_start_web.py`：继续同时写两套环境变量。
- `启动Web工作台.ps1`：新增 HY127WEB 环境变量，同时保留 CODE880WEB。

Cookie/Header 迁移建议：

```python
SESSION_COOKIE_NAMES = ("hy127_session", "code880_session")
CSRF_COOKIE_NAMES = ("hy127_csrf", "code880_csrf")
CSRF_HEADER_NAMES = ("X-Hy127-CSRF", "X-Code880-CSRF")
```

读取时兼容：

```python
def _first_cookie(request, names):
    for name in names:
        value = request.cookies.get(name)
        if value:
            return value
    return ""
```

写入时可以双写一个过渡版本：

```python
response.set_cookie("hy127_session", session_id, httponly=True, samesite="strict", path="/")
response.set_cookie("code880_session", session_id, httponly=True, samesite="strict", path="/")
```

前端 `getCsrf()` 改为：

```javascript
function getCookie(name) {
  const found = document.cookie.split('; ').find(c => c.startsWith(`${name}=`));
  return found ? decodeURIComponent(found.split('=').slice(1).join('=')) : '';
}

function getCsrf() {
  return getCookie('hy127_csrf') || getCookie('code880_csrf') || '';
}
```

## 3. P2 修复项

### P2-1 给 AI 任务模式补正式 API 合同

方案中已有任务状态机和快照思路，但缺少 FastAPI 合同。建议先定义接口，再实现 UI。

新增 Worker API 草案：

```text
POST   /api/ai/tasks
GET    /api/ai/tasks
GET    /api/ai/tasks/{task_id}
POST   /api/ai/tasks/{task_id}/confirm-plan
POST   /api/ai/tasks/{task_id}/confirm-patch
POST   /api/ai/tasks/{task_id}/cancel
POST   /api/ai/tasks/{task_id}/rollback
GET    /api/ai/tasks/{task_id}/events
GET    /api/ai/tasks/{task_id}/diff
```

建议新增服务目录：

```text
code880web/worker/services/ai_tasks/
├── __init__.py
├── models.py
├── task_store.py
├── task_runner.py
├── permissions.py
├── snapshots.py
└── events.py
```

`models.py` 最小结构：

```python
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class AITask:
    task_id: str
    goal: str
    status: str = "created"
    iteration: int = 0
    max_iterations: int = 5
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    permissions: dict = field(default_factory=lambda: {
        "read_file": "allow",
        "write_file": "confirm",
        "run_python": "confirm",
        "network": "strong_confirm",
    })
```

事件日志写入：

```text
.web-workbench/tasks/{task_id}.jsonl
```

每行示例：

```json
{"ts":"2026-05-05T10:00:00","type":"tool_call","tool":"write_file","path":"src/main.py","iteration":1}
```

### P2-2 实现 ToolRegistry，但不要直接让模型调用 FastAPI

新增目录：

```text
code880web/worker/services/ai_tools/
├── __init__.py
├── registry.py
├── file_tools.py
├── run_tools.py
├── git_tools.py
└── preview_tools.py
```

`registry.py` 示例：

```python
@dataclass
class ToolDef:
    name: str
    description: str
    input_schema: dict
    permission: str
    handler: Callable
    audit_fields: list[str]


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolDef] = {}

    def register(self, tool: ToolDef):
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDef | None:
        return self._tools.get(name)

    async def call(self, name: str, payload: dict, audit: dict) -> dict:
        tool = self.get(name)
        if not tool:
            return {"ok": False, "data": {}, "error": f"未知工具: {name}"}
        return await tool.handler(payload, audit)
```

`write_file` 必须包含：

```python
required = ["path", "content", "base_sha256", "task_id", "iteration"]
```

并在写入前调用快照：

```python
snapshot_service.snapshot_file(task_id, iteration, path)
file_service.save_file(path, content, base_sha256)
```

### P2-3 补依赖安装 API，但默认强确认

方案中列出 `POST /api/python/install`，当前未实现。建议放在 P2，不要抢在编辑/AI 基础 bug 前。

新增 API：

```text
POST /api/python/install
GET  /api/python/install/{install_id}
GET  /api/python/install/{install_id}/log
```

请求体只允许白名单字段：

```json
{
  "packages": ["pandas", "openpyxl"],
  "upgrade": false
}
```

代码限制：

```python
if not isinstance(packages, list) or not packages:
    raise HTTPException(400, "packages 必须是非空数组")
if not all(re.match(r"^[A-Za-z0-9_.\\-\\[\\]]+$", p) for p in packages):
    raise HTTPException(400, "包名不合法")
```

命令必须使用数组，不允许 shell：

```python
cmd = [python_path, "-m", "pip", "install", *packages]
if upgrade:
    cmd.insert(4, "--upgrade")
```

### P2-4 OpenAI SDK Runtime 后置到 DirectHttpRuntime 稳定之后

当前 `DirectHttpRuntime` 已可用于 OpenAI-compatible `/chat/completions`。先修 P0-1 后再接 SDK。

新增文件：

```text
code880web/hub/ai_runtime/openai_sdk.py
```

建议接口保持与 `DirectHttpRuntime.chat()` 完全一致：

```python
class OpenAISDKRuntime(AIRuntime):
    def __init__(self, api_key: str, timeout: float = 120):
        self.client = AsyncOpenAI(api_key=api_key, timeout=timeout)

    async def chat(self, messages, tools=None, model="", stream=True):
        ...
```

接入点：

- `ModelsManager` 增加 runtime/protocol 组合校验。
- `hub/app.py` 的 `/internal/ai/relay` 按模型 runtime 选择 Runtime。
- 保持 `DirectHttpRuntime` 默认路径不变，避免影响 DeepSeek/OpenRouter/Ollama 兼容。

## 4. P3 修复项

### P3-1 Claude/Codex/Qwen/Gemini CLI Runtime

这些应作为可选增强，不应先替代 Hub/Worker 本体。

前置条件：

- ToolRegistry 已有。
- 任务状态机已有。
- 权限确认和审计日志已有。
- 文件写入快照和回滚已有。

CLI Runtime 第一版只做受控任务：

```text
用户任务 -> 生成计划 -> 用户确认 -> CLI 执行只读分析 -> 展示建议
```

不要第一版就允许 CLI 任意改文件或运行 shell。

## 5. 建议执行顺序

第一批，修核心断点：

```text
1. P0-1 AI 流式协议错配
2. P0-2 Worker runtime 路径兼容
3. P0-3 AI context 路径校验
4. P0-5 测试环境可运行
5. P0-4 更新方案文档基线
```

第二批，补安全和体验：

```text
1. P1-1 FileService 服务端限制
2. P1-2 前端未保存变更保护
3. P1-3 PythonEnvService / TaskRunner 去重
4. P1-5 GitService 补强
5. P1-6 命名兼容层
```

第三批，补运行能力：

```text
1. P1-4 run history
2. P1-4 run config
3. P2-3 python install
```

第四批，AI 编程助手：

```text
1. P2-1 AI task API
2. P2-2 ToolRegistry
3. P2-4 OpenAI SDK Runtime
4. P3-1 CLI Runtime
```

## 6. 回归测试清单

当前最低回归组合：

```text
python3 scripts/dev_check.py
python3 -m pytest code880web/tests/test_security.py
python3 -m pytest code880web/tests/test_file_service.py
python3 -m pytest code880web/tests/test_file_management.py
python3 -m pytest code880web/tests/test_python_env_service.py
python3 -m pytest code880web/tests/test_platform_utils.py
python3 -m pytest code880web/tests/test_git_service.py
python3 scripts/export_routes.py --check
```

新增测试建议：

```text
code880web/tests/test_ai_service.py
code880web/tests/test_ai_context_security.py
code880web/tests/test_run_history.py
code880web/tests/test_run_config_service.py
code880web/tests/test_hy127_compat_config.py
```

前端手工验收：

```text
1. 启动 scripts/dev_start_web.py。
2. 浏览器打开 bootstrap URL。
3. 打开 src/main.py。
4. 修改一行，Ctrl+S 保存。
5. 刷新页面后确认内容仍在。
6. 打开两个文件，分别修改，切换 Tab 不丢缓冲。
7. 未保存时刷新浏览器触发离开确认。
8. 新建文件、重命名、删除普通文件。
9. 查看 Git status/diff。
10. 运行 src/main.py 并看到实时输出。
11. 配置 AI 模型后，对话能流式输出。
```

## 7. 不建议做的事

- 不要直接把 `code880web/` 整体重命名为 `hy127web/`，必须先做兼容层。
- 不要把任意 shell 命令作为第一版运行能力开放。
- 不要让 AI 直接调用 FastAPI 路由，必须经过 ToolRegistry、权限和审计。
- 不要把 Hub/Worker 改成公网监听。默认必须是 `127.0.0.1`。
- 不要只修前端保存限制，后端必须也限制大文件和非法路径。
- 不要在没有测试环境的情况下继续做大功能合并。

