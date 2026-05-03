# Code880 Web 工作台 — 多项目并行与稳定运行设计

> 本文档基于 `WEB端迁移方案.md` 和 `WEB端迁移方案_20260428_架构设计.md` 的已确认方向，深入解决一个核心问题：**如何在同一个浏览器中，一边浏览其他网页，一边同时打开多个 Code880 项目工作台，并保持稳定运行。**

生成时间：2026-04-28

---

## 一、问题本质分析

### 1.1 用户场景

```
浏览器同时打开：
  Tab 1: 百度搜索 / 在线文档
  Tab 2: Code880 项目 A 的 Web 工作台（办公自动化项目）
  Tab 3: Code880 项目 B 的 Web 工作台（数据分析项目）
  Tab 4: Code880 项目 C 的 Web 工作台（爬虫项目）
  Tab 5: 其他任意网页
```

### 1.2 技术挑战

| 挑战 | 说明 |
|------|------|
| 端口冲突 | 多个项目后端不能都用 `localhost:8880` |
| 进程隔离 | 一个项目的后端崩溃不应拖垮其他项目 |
| 资源竞争 | 多个 Python 进程同时运行的内存/CPU 控制 |
| 服务发现 | 用户如何知道/管理哪些项目已在运行 |
| 生命周期 | 浏览器关闭后进程如何清理 |
| 状态持久 | AI 对话历史、打开的文件标签等跨会话保留 |
| 浏览器限制 | 同源策略、localStorage 隔离、连接数上限 |

---

## 二、整体架构：Hub + Worker 模式

### 2.1 架构总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                        用户浏览器                                     │
│                                                                     │
│  ┌──────────────┐  ┌───────────────┐  ┌───────────────┐  ┌──────┐  │
│  │ 项目管理中心   │  │ 项目 A 工作台  │  │ 项目 B 工作台  │  │ 其他  │  │
│  │ (Hub 页面)    │  │ (独立 Tab)    │  │ (独立 Tab)    │  │ 网页  │  │
│  │ localhost:8800│  │ localhost:8801│  │ localhost:8802│  │      │  │
│  └──────┬───────┘  └───────┬───────┘  └───────┬───────┘  └──────┘  │
│         │                  │                  │                     │
└─────────┼──────────────────┼──────────────────┼─────────────────────┘
          │ HTTP             │ HTTP/WS          │ HTTP/WS
          │                  │                  │
┌─────────┼──────────────────┼──────────────────┼─────────────────────┐
│ 本机进程 │                  │                  │                     │
│         ▼                  ▼                  ▼                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │   Hub 主服务   │  │ Worker 进程 A │  │ Worker 进程 B │              │
│  │  (进程管理器)  │──│  (项目 A)    │  │  (项目 B)    │              │
│  │  port: 8800   │  │  port: 8801  │  │  port: 8802  │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
│         │                  │                  │                     │
│         ▼                  ▼                  ▼                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │ 全局配置/注册 │  │ 项目 A 目录   │  │ 项目 B 目录   │              │
│  │  workspace.db │  │ C:\...\项目A  │  │ D:\...\项目B  │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 两层分工

| 层级 | 职责 | 进程 | 端口 |
|------|------|------|------|
| **Hub（项目管理中心）** | 管理所有项目的注册、启动、停止、状态监控 | 1 个常驻进程 | 固定 `8800` |
| **Worker（项目工作台）** | 为单个项目提供文件树/预览/AI 对话/执行服务 | 每项目 1 个进程 | 动态分配 `8801~8899` |

**为什么不用单进程多路由？**

- 进程隔离：一个项目的 Python 执行崩溃不会影响其他项目
- 独立重启：可单独重启某个项目的后端
- 资源可控：每个 Worker 可设置内存上限
- 简单清理：关闭项目 = 终止对应进程

---

## 三、Hub 主服务设计

### 3.1 核心功能

```python
# Hub 主要职责：
# 1. 项目注册表：记录所有已注册的项目路径和状态
# 2. Worker 生命周期管理：启动、停止、重启 Worker 进程
# 3. 端口分配：自动为每个 Worker 分配可用端口
# 4. 健康监测：定时检查 Worker 是否存活
# 5. 全局配置：AI 模型配置共享（多项目复用同一个 API Key）
# 6. 前端入口：提供项目管理中心页面
```

### 3.2 Hub 页面 — 项目管理中心

```
┌─────────────────────────────────────────────────────────────────┐
│          Code880 项目管理中心    http://localhost:8800            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─ 我的项目 ────────────────────────────────────────────────┐  │
│  │                                                           │  │
│  │  ┌─────────────────────────────────────────────────────┐  │  │
│  │  │ 📁 办公自动化项目                                     │  │  │
│  │  │    路径: D:\Projects\办公自动化                        │  │  │
│  │  │    状态: 🟢 运行中 (端口 8801)                        │  │  │
│  │  │    [打开工作台]  [停止]  [重启]  [移除]               │  │  │
│  │  └─────────────────────────────────────────────────────┘  │  │
│  │                                                           │  │
│  │  ┌─────────────────────────────────────────────────────┐  │  │
│  │  │ 📁 数据分析项目                                       │  │  │
│  │  │    路径: D:\Projects\数据分析                          │  │  │
│  │  │    状态: 🟡 已停止                                    │  │  │
│  │  │    [启动并打开]  [移除]                                │  │  │
│  │  └─────────────────────────────────────────────────────┘  │  │
│  │                                                           │  │
│  │  ┌─────────────────────────────────────────────────────┐  │  │
│  │  │ ＋ 添加项目                                           │  │  │
│  │  │    [选择项目文件夹]  或  [拖入文件夹]                   │  │  │
│  │  └─────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌─ 全局设置 ────────────────────────────────────────────────┐  │
│  │  AI 模型配置    [管理模型]                                  │  │
│  │  已配置: DeepSeek (默认) | 通义千问 (备用)                  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌─ 系统状态 ────────────────────────────────────────────────┐  │
│  │  运行中项目: 2/5    内存占用: 340 MB    端口范围: 8801-8899 │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 Hub API 设计

```
GET  /api/hub/projects              → 已注册项目列表及状态
POST /api/hub/projects/register     → 注册新项目 (传入项目根路径)
POST /api/hub/projects/{id}/start   → 启动项目 Worker
POST /api/hub/projects/{id}/stop    → 停止项目 Worker
POST /api/hub/projects/{id}/restart → 重启项目 Worker
DELETE /api/hub/projects/{id}       → 移除项目注册
GET  /api/hub/projects/{id}/health  → 单项目健康状态
GET  /api/hub/status                → 全局资源使用统计
GET  /api/hub/ports/available       → 查询下一个可用端口

# 全局 AI 配置（所有项目共享）
GET  /api/hub/ai/models             → 全局模型列表
POST /api/hub/ai/models             → 新增全局模型
PUT  /api/hub/ai/models/{id}        → 修改模型配置
```

### 3.4 项目注册数据结构

```json
{
  "id": "proj_a1b2c3",
  "name": "办公自动化项目",
  "root_path": "D:\\Projects\\办公自动化",
  "status": "running",
  "worker_port": 8801,
  "worker_pid": 12345,
  "registered_at": "2026-04-28T10:30:00",
  "last_active_at": "2026-04-28T14:22:15",
  "python_path": "D:\\Projects\\办公自动化\\.venv\\Scripts\\python.exe",
  "initialized": true,
  "auto_start": true,
  "resource_limit": {
    "max_memory_mb": 512,
    "max_task_concurrent": 3
  }
}
```

---

## 四、端口管理策略

### 4.1 端口分配规则

```
端口范围规划：
  8800        → Hub 主服务（固定，不可变）
  8801~8849   → 项目 Worker（自动分配，最多支持 49 个项目同时运行）
  8850~8899   → 预留（未来扩展：共享预览服务、AI 代理池等）
```

### 4.2 端口分配算法

```python
def 分配端口(已占用端口列表: list[int]) -> int:
    """从 8801 开始找第一个未占用的端口"""
    for 端口 in range(8801, 8850):
        if 端口 not in 已占用端口列表:
            if 检测端口可用(端口):
                return 端口
    raise Exception("没有可用端口，请先停止部分项目")

def 检测端口可用(端口: int) -> bool:
    """尝试绑定端口，检测是否被其他程序占用"""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", 端口))
            return True
        except OSError:
            return False
```

### 4.3 端口冲突防护

| 场景 | 处理策略 |
|------|---------|
| 端口被其他软件占用 | 自动跳过，尝试下一个端口 |
| 旧 Worker 未正常退出占用端口 | Hub 检测到 PID 不存在后释放端口记录 |
| 用户手动杀进程 | Hub 健康检查发现后标记为 `stopped` |
| 系统重启后 | Hub 启动时重置所有 Worker 状态为 `stopped` |

---

## 五、进程隔离与生命周期管理

### 5.1 Worker 进程启动

```python
import subprocess
import sys

def 启动Worker(项目路径: str, 分配端口: int) -> subprocess.Popen:
    """每个项目启动为独立子进程"""
    python路径 = os.path.join(项目路径, ".venv", "Scripts", "python.exe")
    worker脚本 = os.path.join(项目路径, "web", "backend", "worker.py")
    
    进程 = subprocess.Popen(
        [python路径, worker脚本,
         "--port", str(分配端口),
         "--project-root", 项目路径,
         "--hub-port", "8800"],
        cwd=项目路径,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW  # Windows: 无黑窗
    )
    return 进程
```

### 5.2 生命周期状态机

```
                    注册
 ┌──────────┐  ───────────→  ┌──────────┐
 │  未注册   │                │  已停止   │
 └──────────┘  ←───────────  └────┬─────┘
                    移除           │ 启动
                                  ▼
                           ┌──────────┐
                      ┌────│  启动中   │
                      │    └────┬─────┘
                      │         │ 就绪
                失败   │         ▼
                      │    ┌──────────┐
                      │    │  运行中   │←─── 重启
                      │    └────┬─────┘
                      │         │ 停止/崩溃
                      ▼         ▼
                    ┌──────────────┐
                    │  已停止/异常   │
                    └──────────────┘
```

### 5.3 健康监测机制

```python
# Hub 每 15 秒检查一次所有 Worker
async def 健康检查循环():
    while True:
        for 项目 in 获取运行中项目():
            try:
                响应 = await httpx.get(
                    f"http://127.0.0.1:{项目.worker_port}/health",
                    timeout=5.0
                )
                if 响应.status_code == 200:
                    项目.last_active_at = datetime.now()
                else:
                    项目.连续失败次数 += 1
            except Exception:
                项目.连续失败次数 += 1
            
            # 连续 3 次失败，标记为异常
            if 项目.连续失败次数 >= 3:
                await 处理Worker异常(项目)
        
        await asyncio.sleep(15)

async def 处理Worker异常(项目):
    """Worker 异常处理策略"""
    if 项目.auto_restart and 项目.重启次数 < 3:
        await 重启Worker(项目)
        项目.重启次数 += 1
    else:
        项目.status = "异常停止"
        # 通知前端（如果有 WebSocket 连接）
        await 推送通知(项目.id, "项目服务异常停止，请手动重启")
```

### 5.4 进程资源限制（Windows）

```python
import psutil

def 监控Worker资源(进程pid: int, 内存上限_MB: int = 512):
    """监控并限制 Worker 内存使用"""
    try:
        进程 = psutil.Process(进程pid)
        内存使用_MB = 进程.memory_info().rss / (1024 * 1024)
        
        if 内存使用_MB > 内存上限_MB:
            # 先发警告，不立即杀进程
            return {"warning": f"内存使用 {内存使用_MB:.0f}MB 超过限制 {内存上限_MB}MB"}
        
        return {
            "pid": 进程pid,
            "memory_mb": round(内存使用_MB, 1),
            "cpu_percent": 进程.cpu_percent(interval=0.1),
            "status": 进程.status()
        }
    except psutil.NoSuchProcess:
        return {"error": "进程不存在"}
```

---

## 六、浏览器端多项目管理

### 6.1 Tab 隔离策略

```
每个项目 = 一个独立浏览器 Tab
  - 独立的 origin (不同端口 = 不同源)
  - 独立的 localStorage / sessionStorage
  - 独立的 WebSocket 连接
  - 独立的 Service Worker (离线缓存)
  - 一个 Tab 崩溃不影响其他 Tab
```

**为什么不用单 Tab + iframe/路由切换？**

| 方案 | 优点 | 缺点 |
|------|------|------|
| 多 Tab (推荐) | 完全隔离、可独立关闭、支持操作系统级标签管理 | 需要在 Hub 页面跳转 |
| 单 Tab + 路由 | 看似统一 | 一个项目卡死整个页面冻结 |
| 单 Tab + iframe | 视觉统一 | 跨域通信复杂、性能差、焦点冲突 |

### 6.2 浏览器资源优化

```javascript
// 前端 Worker 页面 — 当 Tab 不可见时降低活动频率
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        // Tab 在后台时：停止文件树轮询、降低 WebSocket 心跳频率
        文件树轮询.暂停();
        WebSocket心跳间隔 = 60000; // 60秒
    } else {
        // Tab 恢复前台时：刷新文件树、恢复正常频率
        文件树轮询.恢复();
        WebSocket心跳间隔 = 15000; // 15秒
        刷新文件树();
    }
});
```

### 6.3 跨 Tab 通信（Hub ↔ Worker Tab）

```javascript
// 使用 BroadcastChannel 在同一浏览器的多个 Tab 间通信
const 频道 = new BroadcastChannel('code880_hub');

// Hub 页面广播消息
频道.postMessage({ type: 'worker_stopped', project_id: 'proj_a1b2' });

// Worker Tab 接收消息
频道.onmessage = (event) => {
    if (event.data.type === 'worker_stopped' && event.data.project_id === 当前项目ID) {
        显示断连提示("项目服务已停止，请返回管理中心重新启动");
    }
};
```

---

## 七、稳定性保障设计

### 7.1 故障恢复机制

| 故障场景 | 自动恢复策略 | 用户感知 |
|---------|------------|---------|
| Worker 进程崩溃 | Hub 自动重启（最多 3 次） | 页面显示"重新连接中..."后恢复 |
| Hub 进程崩溃 | Windows 任务计划程序自动重启 | 约 5 秒后 Hub 页面恢复 |
| 浏览器 Tab 被关闭 | Worker 后端继续运行，下次打开恢复状态 | 无感 |
| 浏览器全部关闭 | Worker 后端持续运行，Hub 保持监控 | 重新打开浏览器即可继续 |
| 电脑重启 | Hub 设为开机自启（可选），Worker 按需手动启动 | 双击 Hub 入口恢复 |
| 网络断开 | AI 对话暂停，其他功能正常（本地服务） | AI 面板提示"网络不可用" |
| 磁盘满 | Worker 写入操作失败提示，不崩溃 | 显示磁盘空间警告 |

### 7.2 数据持久化策略

```
全局数据（Hub 管理）:
  C:\Users\{用户}\AppData\Local\Code880Web\
    ├── hub.db              ← 项目注册表、全局配置
    ├── ai_models.json      ← AI 模型配置（加密的 API Key）
    ├── hub.log             ← Hub 服务日志
    └── hub.pid             ← Hub 进程 PID 文件

项目数据（Worker 管理，存在项目目录内）:
  {项目根目录}/
    └── .web-workbench/
        ├── state.json      ← 打开的文件标签、面板布局
        ├── chat_history/   ← AI 对话历史
        ├── backups/        ← 文件修改备份
        ├── preview_cache/  ← Office 预览缓存
        └── worker.log      ← Worker 服务日志
```

### 7.3 优雅关闭机制

```python
# Worker 接收到停止信号时的清理流程
async def 优雅关闭(信号=None):
    """确保数据完整性"""
    # 1. 停止接受新请求
    正在运行的任务 = 获取执行中任务()
    
    # 2. 等待正在执行的任务完成（最多 30 秒）
    for 任务 in 正在运行的任务:
        await 任务.等待完成(超时=30)
    
    # 3. 保存工作状态
    await 保存会话状态()
    
    # 4. 关闭 WebSocket 连接
    for 连接 in 活跃WebSocket连接:
        await 连接.close(code=1001, reason="服务正在关闭")
    
    # 5. 清理临时文件
    清理预览缓存()
    
    # 6. 向 Hub 报告已停止
    await 通知Hub("stopped")
```

### 7.4 防止"僵尸进程"

```python
# Hub 启动时的清理逻辑
def Hub启动时清理():
    """系统重启或异常退出后的清理"""
    for 项目 in 读取注册表():
        if 项目.status == "running":
            if 项目.worker_pid and 进程是否存在(项目.worker_pid):
                # 进程还在，检查是否真的是我们的 Worker
                if 验证进程身份(项目.worker_pid, 项目.worker_port):
                    continue  # 正常运行中
                else:
                    # PID 被复用为其他进程，标记为停止
                    项目.status = "stopped"
            else:
                # 进程不存在，标记为停止
                项目.status = "stopped"
                项目.worker_pid = None
                项目.worker_port = None
    保存注册表()
```

---

## 八、多项目之间的资源共享

### 8.1 AI 模型配置共享

```
问题：每个项目都需要 AI 模型，是否每次都要配置 API Key？
方案：全局 AI 配置 + 项目级覆盖

Hub 全局配置:
  - DeepSeek API Key: sk-xxx（所有项目默认使用）
  - 通义千问 API Key: sk-yyy（备用）

项目 A 配置:
  - 使用全局默认（DeepSeek）

项目 B 配置:
  - 覆盖为特定模型（自定义 base_url）
```

### 8.2 预览服务共享（可选优化）

```
场景：3 个项目都需要 Word 转 PDF 预览
方案 A（默认）：每个 Worker 自行转换 ← 简单、隔离好
方案 B（优化）：Hub 提供共享预览服务 ← 减少内存，LibreOffice 只加载一次

# 方案 B 仅在资源紧张时启用
# 共享预览服务 API：
POST http://localhost:8850/convert
  Body: { "source": "D:/project/report.docx", "format": "pdf" }
  Response: { "output": "临时路径/report.pdf" }
```

### 8.3 对话历史隔离

```
项目 A 的对话历史 ← 只存在项目 A 的 .web-workbench/ 下
项目 B 的对话历史 ← 只存在项目 B 的 .web-workbench/ 下

不跨项目共享对话，避免 AI 上下文混乱。
但用户可在 Hub 页面看到"最近的 AI 对话"汇总视图。
```

---

## 九、启动方式设计

### 9.1 两种启动入口

**入口 1：从项目内启动（单项目快捷）**

```batch
:: 项目根目录\启动Web.bat
:: 启动单个项目的工作台（如果 Hub 未运行则先启动 Hub）
@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在启动 Code880 Web 工作台...

:: 检查 Hub 是否已运行
powershell -NoProfile -Command "try { (Invoke-WebRequest http://127.0.0.1:8800/health -TimeoutSec 2).StatusCode } catch { exit 1 }"
if %errorlevel% neq 0 (
    echo [信息] 正在启动项目管理中心...
    start /B "" ".venv\Scripts\python.exe" "web\backend\hub.py"
    timeout /t 3 /nobreak >nul
)

:: 向 Hub 注册并启动当前项目
powershell -NoProfile -Command ^
    "Invoke-RestMethod -Method POST -Uri 'http://127.0.0.1:8800/api/hub/projects/register-and-start' -Body (ConvertTo-Json @{root_path='%CD%'}) -ContentType 'application/json'"

:: 打开浏览器
start "" "http://localhost:8800"
```

**入口 2：从管理中心启动（多项目管理）**

```batch
:: C:\PythonDev\启动项目管理中心.bat （一键安装时放置）
@echo off
chcp 65001 >nul
echo 正在启动 Code880 项目管理中心...
"C:\PythonDev\Python312\python.exe" "C:\PythonDev\code880web\hub.py"
start "" "http://localhost:8800"
```

### 9.2 启动流程图

```
用户双击 "启动Web.bat"（项目内）
       │
       ├── Hub 已运行？
       │      │
       │      ├── 是 → 向 Hub 注册当前项目 → 分配端口 → 启动 Worker
       │      │
       │      └── 否 → 先启动 Hub → 等待就绪 → 注册 → 分配端口 → 启动 Worker
       │
       ▼
浏览器自动打开 → Hub 管理中心页面
       │
       └── 页面显示当前项目状态为"运行中" → 点击"打开工作台" → 新 Tab 打开项目
```

---

## 十、浏览器兼容与性能优化

### 10.1 浏览器兼容性

| 浏览器 | 支持情况 | 备注 |
|--------|---------|------|
| Chrome 90+ | 完全支持 | 推荐 |
| Edge 90+ | 完全支持 | Windows 默认浏览器，首选 |
| Firefox 90+ | 完全支持 | |
| Safari 15+ | 基本支持 | Mac 用户 |
| IE | 不支持 | 明确提示升级 |

### 10.2 多 Tab 性能预算

```
单个项目 Tab 的资源预算（浏览器端）：
  - 初始加载 JS: < 2 MB (gzip 后)
  - 运行时内存: < 150 MB
  - WebSocket 连接: 1 条
  - HTTP 长连接: 最多 6 条（浏览器限制）

多项目并行建议上限：
  - 同时运行 Worker: ≤ 5 个（默认）
  - 同时打开 Tab: ≤ 8 个
  - 超出后 Hub 提示"建议停止不活跃的项目以节省资源"
```

### 10.3 后端内存预算

```
Hub 进程:       ~30 MB（常驻，轻量）
Worker 进程:    ~80-150 MB/个（基础）
  - 文件树缓存:  ~5 MB
  - Office 预览: ~50-100 MB（转换时临时）
  - AI 对话:    ~10 MB（对话历史）
  - Python 执行: ~50-200 MB（取决于用户代码）

5 个项目同时运行: ~500-800 MB 总内存（可接受）
```

---

## 十一、同一浏览器中与其他网页共存

### 11.1 为什么不会互相干扰

```
Code880 Web 工作台使用 localhost 不同端口：
  - 与外网站点完全隔离（不同源）
  - 不会触发 CORS 拦截（浏览器对 localhost 宽松）
  - 不会争抢外网请求带宽（本地回环网络，延迟 < 1ms）
  - Cookie/Storage 按端口隔离，互不污染
  - 即使外网断了，本地工作台照常运行（只有 AI 需要网络）
```

### 11.2 避免占用浏览器连接池

```
浏览器对同一 origin 的并发连接数限制：6 条（HTTP/1.1）
  → 每个项目占一个端口 = 一个独立 origin
  → 6 条连接只给自己的 Worker 用，不影响其他网站

WebSocket 连接数限制：通常 200+ 条
  → 每个项目只用 1 条 WebSocket，完全无压力

Service Worker / Cache API：
  → 每个端口有独立的 SW 作用域，互不影响
```

### 11.3 与常见本地开发工具的端口避让

```
常见占用端口：
  3000  → React/Next.js 开发服务器
  5173  → Vite 开发服务器
  8000  → Django / uvicorn 默认
  8080  → 通用 HTTP 代理
  8888  → Jupyter Notebook

Code880 使用 8800-8899 范围：
  → 与上述工具不冲突
  → 如果用户恰好占用了 8800，Hub 可配置为其他端口
```

---

## 十二、高级特性：项目间切换体验

### 12.1 快速切换

```javascript
// Hub 页面提供全局快捷键 Ctrl+Shift+P 打开项目快速切换面板
// 类似 VSCode 的 Ctrl+R "切换窗口"

快速切换面板:
  ┌─────────────────────────────────┐
  │ 🔍 切换项目...                   │
  │ ─────────────────────────────── │
  │  🟢 办公自动化  (端口 8801)      │
  │  🟢 数据分析    (端口 8802)      │
  │  🟡 爬虫项目    (已停止)         │
  └─────────────────────────────────┘
  
  回车 → 切换到对应 Tab / 打开新 Tab
```

### 12.2 统一通知中心

```
Hub 页面侧边栏"通知"：
  - 14:20  项目 A: AI 建议已生成
  - 14:18  项目 B: main.py 运行完成
  - 14:15  项目 C: 依赖安装完成
  - 14:10  系统: Worker 内存使用达到 80%

浏览器原生通知（用户授权后）：
  → 当 Tab 在后台时，任务完成通过 Notification API 通知
```

---

## 十三、部署形态与启动部署

### 13.1 最终交付形态

```
方案 A（推荐 - 纯脚本启动）：
  C:\PythonDev\
    ├── code880web\         ← Hub 服务代码 + 共享前端
    │   ├── hub.py
    │   ├── worker.py
    │   ├── static\         ← 前端打包文件
    │   └── requirements.txt
    └── 启动项目管理中心.bat

  各项目根目录\
    └── 启动Web.bat         ← 单项目快捷入口

方案 B（进阶 - 打包为 exe）：
  C:\PythonDev\
    └── Code880Web.exe      ← PyInstaller 打包的 Hub（含前端）

  各项目根目录\
    └── 启动Web.bat         ← 调用 Code880Web.exe --project=当前路径
```

### 13.2 一键安装集成

```
现有安装流程（不改动）：
  一键安装.exe → Python + uv + VSCode + 环境配置

新增可选步骤（未来版本）：
  一键安装.exe → ... → 询问"是否安装 Web 工作台？"
    → 是 → 部署 code880web 到 C:\PythonDev\code880web\
         → 创建桌面快捷方式"Code880 项目管理中心"
         → 安装 Web 依赖到全局或共享 .venv
    → 否 → 跳过，只有 VSCode 流程
```

---

## 十四、与架构设计文档的亮点融合

从 `WEB端迁移方案_20260428_架构设计.md` 中吸收的关键设计：

| 架构文档亮点 | 在多项目方案中的融合 |
|-------------|-------------------|
| Security Guard（路径限制、命令白名单） | 每个 Worker 只能访问自己的项目根目录，Hub 不能越权访问 Worker |
| Context Engine（Token 控制、文件分块） | 每个项目独立的上下文引擎，互不干扰 |
| Task Runner（受控任务执行） | Worker 内的任务执行有独立队列，一个项目的长任务不阻塞其他项目 |
| SQLite 存储 | Hub 用 SQLite 管理注册表，Worker 用 SQLite 管理本地状态 |
| Windows DPAPI 加密 API Key | 全局唯一存储，Worker 通过 Hub API 获取解密后的 Key（仅内存） |
| watchdog 文件监听 | 每个 Worker 独立监听自己项目目录 |
| 初始化状态检测 | Hub 注册项目时自动检测初始化状态，提示用户是否需要初始化 |
| LibreOffice headless 转换 | 共享预览服务（8850 端口），避免每个 Worker 都加载 LibreOffice |
| 非 IT 用户文案 | Hub 页面所有文案面向零基础用户 |
| 审计日志 | Hub 层面的全局审计 + Worker 层面的项目审计 |
| `重新初始化.ps1` 解耦 | 新增 `-WebMode` 参数，Worker 可调用初始化能力但不启动 VSCode |

---

## 十五、稳定性测试场景清单

| # | 测试场景 | 预期行为 |
|---|---------|---------|
| 1 | 同时启动 5 个项目 | 全部正常运行，各自独立 Tab 可操作 |
| 2 | 关闭其中 1 个项目 Tab | 对应 Worker 继续运行，下次打开恢复 |
| 3 | 从任务管理器杀掉 1 个 Worker | Hub 检测到后标记异常，自动重启 |
| 4 | 杀掉 Hub 进程 | Worker 继续独立运行，Hub 重启后重新发现 |
| 5 | 浏览器全部关闭 | 所有服务继续运行，重新打开浏览器恢复 |
| 6 | 电脑休眠唤醒 | Hub 和 Worker 恢复正常（TCP 重连） |
| 7 | 同时在 2 个项目中执行 AI 对话 | 各自独立流式输出，互不阻塞 |
| 8 | 项目 A 的 Python 脚本死循环 | 只影响项目 A 的 Worker，其他项目不受影响 |
| 9 | 磁盘空间不足 | Worker 写入时报错，不崩溃，显示友好提示 |
| 10 | API Key 过期 | AI 对话返回明确错误提示，其他功能正常 |
| 11 | 两个项目使用相同目录 | Hub 检测到重复，提示"该目录已注册" |
| 12 | OneDrive 同步锁定文件 | Worker 读取时重试，写入时提示稍后再试 |

---

## 十六、总结

### 核心设计决策

1. **Hub + Worker 两层架构**：Hub 管理全局，Worker 服务单项目，进程级隔离
2. **动态端口分配**：8800 固定给 Hub，8801-8849 动态分配给 Worker
3. **多 Tab 天然隔离**：每个项目一个独立 Tab，利用浏览器自身的 Tab 隔离机制
4. **服务独立于浏览器**：关闭 Tab/浏览器不影响后端，重新打开即恢复
5. **全局 AI 配置共享**：API Key 只配一次，所有项目复用
6. **自动健康监测**：Hub 定时检查 Worker，异常自动重启
7. **渐进式资源使用**：不活跃项目可停止 Worker 释放资源

### 用户最终体验

```
普通用户视角：
  1. 双击"启动Web.bat" → 浏览器打开
  2. 看到项目管理中心，显示所有项目
  3. 点击"打开工作台" → 新标签页打开项目
  4. 可以同时打开多个项目标签
  5. 可以正常使用其他网页
  6. 关闭浏览器后重新打开，一切都还在
```

---

> 文档版本：v1.0 | 创建日期：2026-04-28 | 定位：多项目并行运行与稳定性保障专项设计
