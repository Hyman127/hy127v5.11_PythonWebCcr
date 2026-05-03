# Code880 VSCode 项目交互界面 → WEB 端迁移方案

> 目标：让不懂 IT 的用户通过浏览器即可查看项目文件、预览文档、与 AI 对话分析代码，无需安装或手动启动 VSCode。

---

## 一、整体架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                    用户浏览器 (前端)                          │
│  ┌──────────┐  ┌──────────────────┐  ┌───────────────────┐  │
│  │ 文件树面板 │  │  文件内容/预览面板  │  │   AI 对话面板     │  │
│  │ (左侧)    │  │  (中间主区域)      │  │   (右侧/底部)    │  │
│  └──────────┘  └──────────────────┘  └───────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │ HTTP/WebSocket
┌─────────────────────────────────────────────────────────────┐
│                   Python 后端服务 (FastAPI)                   │
│  ┌──────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │文件系统API│  │文档转换服务   │  │  AI 对话代理服务       │ │
│  │(读取/浏览)│  │(Office/PDF)  │  │  (调用大模型API)       │ │
│  └──────────┘  └──────────────┘  └────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│              本地项目目录 (code880 项目根目录)                 │
│  src/ | __hy127/ | .vscode/ | *.py | *.md | ...             │
└─────────────────────────────────────────────────────────────┘
```

### 核心理念

- **VSCode 不需要启动**：后端直接读取项目文件系统，无需依赖 VSCode 进程
- **浏览器即入口**：用户双击一个 `启动Web.bat` 即可自动打开浏览器访问
- **本地运行**：所有服务跑在本机 `localhost`，无需联网部署服务器（AI 对话需联网调 API）
- **一键启动**：延续项目"一键"哲学，用户零配置即用

---

## 二、功能模块详细设计

### 2.1 文件树面板（模拟 VSCode 资源管理器）

| 特性 | 说明 |
|------|------|
| 目录树展示 | 递归展示项目根目录下的文件夹和文件，支持展开/折叠 |
| 智能过滤 | 默认隐藏 `.venv/`、`.uv-cache/`、`__pycache__/`、`.git/` 等非用户文件 |
| 文件图标 | 根据文件扩展名显示对应图标（.py=Python图标、.md=文档图标等） |
| 搜索功能 | 支持按文件名搜索过滤 |
| 右键菜单 | 提供"发送到AI对话"、"在新标签打开"等快捷操作 |

**后端 API 设计：**

```
GET /api/files/tree              → 返回目录树结构 (JSON)
GET /api/files/content?path=xxx  → 返回文件内容 (文本/二进制)
```

**前端实现：**
- 使用 Vue 3 + Element Plus 或 React + Ant Design 的 Tree 组件
- 懒加载：首次只加载顶层目录，点击展开时再请求子目录

---

### 2.2 文件内容/预览面板

根据文件类型提供不同展示方式：

| 文件类型 | 展示方式 | 实现方案 |
|---------|---------|---------|
| `.py` `.js` `.json` `.bat` `.ps1` `.toml` `.cfg` | 代码高亮文本展示 | Monaco Editor (只读模式) 或 Prism.js/Highlight.js |
| `.md` | Markdown 渲染 | markdown-it 或 marked.js |
| `.txt` `.log` `.csv` | 纯文本展示 | 等宽字体文本区域 |
| `.docx` (Word) | Word 格式预览 | 后端 python-docx → HTML 转换，前端 iframe 渲染 |
| `.xlsx` (Excel) | 表格格式预览 | 后端 openpyxl → JSON 表格数据，前端用 Handsontable/AG Grid 渲染 |
| `.pptx` (PPT) | 幻灯片预览 | 后端 python-pptx → 图片/HTML，前端幻灯片浏览 |
| `.pdf` | PDF 内嵌预览 | PDF.js 前端直接渲染 |
| `.png` `.jpg` `.gif` `.svg` | 图片预览 | `<img>` 标签直接展示 |
| 其他二进制 | 提示不可预览 | 显示文件基本信息（大小、类型、修改时间） |

**后端 API 设计：**

```
GET /api/preview/text?path=xxx      → 返回文本内容 + 语言类型
GET /api/preview/office?path=xxx    → 返回 Office 文件的 HTML 转换结果
GET /api/preview/raw?path=xxx       → 返回原始文件（用于 PDF.js / 图片）
```

---

### 2.3 AI 对话面板

| 特性 | 说明 |
|------|------|
| 对话界面 | 类 ChatGPT 风格的对话框，支持 Markdown 渲染回复 |
| 上下文选择 | 可从左侧文件树勾选文件作为 AI 对话上下文 |
| 模型配置 | 用户在 Web 设置页面填入 API Key 和选择模型 |
| 流式输出 | SSE/WebSocket 流式返回 AI 响应，实时显示打字效果 |
| 对话历史 | 本地保存对话记录，支持新建/切换对话 |
| 预设提示词 | 内置"解释代码"、"优化建议"、"找 Bug"等快捷提示模板 |

**支持的 AI 模型接口：**

| 提供商 | 模型 | 接入方式 |
|--------|------|---------|
| OpenAI | GPT-4o / GPT-4o-mini | OpenAI API (兼容格式) |
| Anthropic | Claude 4 Sonnet/Opus | Anthropic API |
| 通义千问 | Qwen-Plus/Qwen-Max | 阿里云 DashScope API |
| DeepSeek | DeepSeek-V3/R1 | DeepSeek API (OpenAI 兼容) |
| 本地模型 | Ollama 部署的模型 | 本地 OpenAI 兼容接口 |

**后端 API 设计：**

```
POST /api/ai/chat                → 发送对话请求 (支持 SSE 流式)
GET  /api/ai/models              → 获取可用模型列表
POST /api/ai/config              → 保存 API 配置
GET  /api/ai/history             → 获取对话历史
```

**上下文构建逻辑：**

```python
# 当用户选择了文件作为上下文时
系统提示 = """你是一个 Python 代码助手。
以下是用户项目中的相关文件内容，请基于这些内容回答问题。"""

上下文内容 = ""
for 文件路径 in 用户选择的文件列表:
    文件内容 = 读取文件(文件路径)
    上下文内容 += f"\n--- 文件: {文件路径} ---\n{文件内容}\n"

# 拼接为完整的 AI 请求
消息列表 = [
    {"role": "system", "content": 系统提示 + 上下文内容},
    *历史对话消息,
    {"role": "user", "content": 用户输入}
]
```

---

### 2.4 初始化与启动流程

```
用户双击 "启动Web.bat"
       │
       ▼
检查 Python 虚拟环境 (.venv)
       │
       ├── 不存在 → 提示用户先运行"一键安装.exe"
       │
       ▼
安装/更新 Web 依赖 (uv add fastapi uvicorn ...)
       │
       ▼
启动 FastAPI 后端服务 (localhost:8880)
       │
       ▼
自动打开默认浏览器访问 http://localhost:8880
       │
       ▼
用户看到 Web 界面，即刻可用
```

---

## 三、技术栈选型

### 3.1 后端 (Python)

| 组件 | 选型 | 理由 |
|------|------|------|
| Web 框架 | **FastAPI** | 异步高性能、自动生成 API 文档、Python 原生 |
| ASGI 服务器 | **Uvicorn** | 轻量、适合本地开发 |
| 文件监控 | **watchdog** | 监听文件变化实时更新前端 |
| Word 转换 | **python-docx + mammoth** | Word → HTML |
| Excel 转换 | **openpyxl** | 已在项目依赖中 |
| PPT 转换 | **python-pptx** | PPT → 图片/HTML |
| PDF 处理 | 前端 PDF.js | 不需要后端转换 |
| AI 接口 | **httpx** (异步) | 统一调用各 AI 提供商 API |
| 配置存储 | **JSON 文件** | 简单、无需数据库、符合项目风格 |

### 3.2 前端

| 组件 | 选型 | 理由 |
|------|------|------|
| 框架 | **Vue 3** | 学习曲线平缓、中文生态好 |
| UI 库 | **Element Plus** | 成熟的 Tree/Table/Dialog 组件 |
| 代码高亮 | **Monaco Editor** (只读) | 就是 VSCode 的编辑器内核 |
| Markdown 渲染 | **markdown-it** | 轻量、插件丰富 |
| PDF 预览 | **PDF.js** | Mozilla 出品、功能完整 |
| 表格展示 | **Handsontable** 或 **AG Grid** | Excel 级别的表格渲染 |
| 布局 | **Splitpanes** | 可拖拽分割面板（模拟 VSCode 布局） |
| 打包 | **Vite** | 开发快、打包小 |

### 3.3 打包方式（最终交付形态）

**方案 A：纯 Python 启动（推荐）**

前端打包为静态文件 → 嵌入到 FastAPI 的 static 目录 → 用户只需启动一个 Python 进程

```
启动Web.bat → python web_server.py → 同时提供 API + 前端静态文件
```

**方案 B：Electron/Tauri 打包（备选）**

如果需要桌面应用体验（无地址栏、类原生窗口），可用 Tauri 打包前端 + 本地 Python 后端

---

## 四、项目目录结构（新增部分）

```
项目根目录/
├── web/                          ← 新增：Web 端全部代码
│   ├── backend/                  ← Python 后端
│   │   ├── main.py              ← FastAPI 入口
│   │   ├── api/
│   │   │   ├── files.py         ← 文件系统 API
│   │   │   ├── preview.py       ← 文件预览 API
│   │   │   └── ai_chat.py      ← AI 对话 API
│   │   ├── services/
│   │   │   ├── file_service.py  ← 文件读取/过滤逻辑
│   │   │   ├── office_converter.py ← Office 文件转换
│   │   │   └── ai_service.py   ← AI 模型调用封装
│   │   ├── config/
│   │   │   ├── settings.py      ← 服务器配置
│   │   │   └── ai_config.json   ← AI API 密钥配置（用户填写）
│   │   └── static/              ← 前端打包后的静态文件
│   │       └── index.html
│   ├── frontend/                 ← 前端源码（开发用）
│   │   ├── src/
│   │   │   ├── App.vue
│   │   │   ├── components/
│   │   │   │   ├── FileTree.vue       ← 文件树组件
│   │   │   │   ├── FileViewer.vue     ← 文件预览组件
│   │   │   │   ├── CodeViewer.vue     ← 代码展示组件
│   │   │   │   ├── OfficeViewer.vue   ← Office 文件预览
│   │   │   │   ├── AiChat.vue        ← AI 对话组件
│   │   │   │   └── SettingsPanel.vue  ← 设置面板
│   │   │   ├── stores/
│   │   │   │   └── fileStore.js       ← 文件状态管理
│   │   │   └── utils/
│   │   │       └── api.js             ← API 请求封装
│   │   ├── package.json
│   │   └── vite.config.js
│   └── requirements.txt          ← Web 模块的 Python 依赖
├── 启动Web.bat                   ← 新增：一键启动 Web 服务
├── 启动Web.ps1                   ← 新增：PowerShell 启动脚本
├── src/                          ← 原有代码不变
├── __hy127/                      ← 原有代码不变
├── .vscode/                      ← 原有代码不变
└── ...
```

---

## 五、核心接口详细设计

### 5.1 文件树 API

```python
# GET /api/files/tree?root=.&depth=2
# 返回示例：
{
    "name": "项目根目录",
    "path": ".",
    "type": "directory",
    "children": [
        {
            "name": "src",
            "path": "src",
            "type": "directory",
            "children": [
                {"name": "main.py", "path": "src/main.py", "type": "file", "size": 64, "ext": ".py"},
                {"name": "一键安装卸载.py", "path": "src/一键安装卸载.py", "type": "file", "size": 89200, "ext": ".py"}
            ]
        },
        {"name": "一键安装说明.md", "path": "一键安装说明.md", "type": "file", "size": 3200, "ext": ".md"}
    ]
}
```

### 5.2 文件过滤规则

```python
# 默认隐藏的目录/文件（可在 Web 设置中调整）
默认隐藏列表 = [
    ".venv",
    ".uv-cache", 
    "__pycache__",
    ".git",
    "*.pyc",
    "node_modules",
    ".DS_Store",
    "Thumbs.db",
]
```

### 5.3 AI 对话请求格式

```python
# POST /api/ai/chat
{
    "message": "请解释这个函数的作用",
    "context_files": ["src/main.py", "__hy127/__init__.py"],
    "conversation_id": "conv_001",
    "model": "deepseek-chat",
    "stream": true
}
```

---

## 六、安全性考虑

| 风险点 | 防护措施 |
|--------|---------|
| 文件路径遍历攻击 | 后端严格校验路径，禁止 `..` 跳出项目根目录 |
| API Key 泄露 | 密钥存在本地 JSON 文件，不上传/不嵌入前端代码 |
| 只读访问 | 默认只提供文件读取，不提供文件写入/删除接口 |
| 仅本地访问 | 服务绑定 `127.0.0.1`，不对外网暴露 |
| CORS 限制 | 仅允许 `localhost` 来源的请求 |

---

## 七、用户体验设计

### 7.1 界面布局（参考 VSCode）

```
┌─────────────────────────────────────────────────────────────────┐
│  [logo] Code880 Web IDE          [设置⚙] [AI配置🤖] [帮助❓]    │
├───────────┬───────────────────────────────┬─────────────────────┤
│           │  ┌─ 标签页 ─────────────────┐ │                     │
│  资源管理器 │  │ main.py × │ 说明.md ×   │ │    AI 助手          │
│           │  ├─────────────────────────────┤│                     │
│  ▼ src/   │  │                           ││  ┌─────────────────┐ │
│    main.py│  │   文件内容展示区域         ││  │ 对话历史...      │ │
│    安装.py │  │   (代码高亮/文档预览)     ││  │                 │ │
│  ▼ __hy127│  │                           ││  │ 用户: 解释main  │ │
│    init.py│  │                           ││  │ AI: 这是入口... │ │
│  ▶ .vscode│  │                           ││  │                 │ │
│           │  │                           ││  ├─────────────────┤ │
│  [搜索🔍]  │  │                           ││  │ [输入框...]  发送│ │
│           │  └───────────────────────────┘│  └─────────────────┘ │
├───────────┴───────────────────────────────┴─────────────────────┤
│  状态栏: Python 3.12 | 文件数: 15 | AI: DeepSeek (已连接)        │
└─────────────────────────────────────────────────────────────────┘
```

### 7.2 交互流程

1. **首次使用**：双击 `启动Web.bat` → 浏览器打开 → 显示"AI 配置向导"（填 API Key）→ 进入主界面
2. **日常使用**：双击 `启动Web.bat` → 浏览器打开 → 直接进入主界面 → 浏览文件 / AI 对话
3. **AI 对话**：左侧勾选文件 → 右侧输入问题 → AI 基于文件内容回答
4. **查看文档**：左侧点击 `.docx` 文件 → 中间区域 Word 格式渲染展示

---

## 八、是否需要 VSCode 运行？

### 结论：完全不需要

| 对比项 | VSCode 方式 | Web 方式 |
|--------|------------|----------|
| 文件浏览 | VSCode 资源管理器 | Web 文件树组件 |
| 代码高亮 | VSCode 编辑器 | Monaco Editor (只读) |
| AI 对话 | VSCode 插件 (如 Copilot) | 自建 AI 对话面板 |
| 文件预览 | VSCode 预览插件 | 自建 Office/PDF 预览 |
| 运行依赖 | 需要 VSCode 进程 | 只需 Python 进程 |

本方案的"底层"是一个 **Python FastAPI 服务进程**（非 VSCode），它：
- 直接读取项目文件系统（和 VSCode 读文件的方式一样，只是换了个程序来读）
- 通过 HTTP API 将文件内容传给前端浏览器渲染
- 通过调用 AI API 实现对话功能

**类比**：就像把 VSCode 的"文件浏览+代码查看+AI插件"三个功能用 Web 技术重新实现了一遍，但更简单、更面向非 IT 用户。

---

## 九、实施计划（分阶段）

### 第一阶段：基础框架（约 3-5 天）

- [ ] 搭建 FastAPI 后端骨架
- [ ] 实现文件树 API（目录递归 + 过滤）
- [ ] 实现文本文件读取 API
- [ ] 前端搭建 Vue 3 项目 + 三栏布局
- [ ] 实现文件树组件（点击展开/折叠）
- [ ] 实现代码/文本文件展示（Monaco Editor 只读）
- [ ] 编写 `启动Web.bat` 一键启动脚本

### 第二阶段：文档预览（约 3-5 天）

- [ ] 后端 Word → HTML 转换
- [ ] 后端 Excel → JSON 表格数据
- [ ] 后端 PPT → 图片序列
- [ ] 前端 PDF.js 集成
- [ ] 前端 Office 预览组件
- [ ] 图片预览支持

### 第三阶段：AI 对话（约 5-7 天）

- [ ] 后端 AI 服务封装（支持多模型）
- [ ] AI 配置页面（API Key、模型选择）
- [ ] 前端对话组件（流式输出）
- [ ] 上下文选择功能（文件勾选 → 加入对话）
- [ ] 对话历史本地存储
- [ ] 预设提示词模板

### 第四阶段：优化与打磨（约 3-5 天）

- [ ] 前端打包嵌入后端 static 目录
- [ ] 文件搜索功能
- [ ] 界面主题切换（明/暗）
- [ ] 文件变更实时刷新（WebSocket）
- [ ] 错误处理与友好提示
- [ ] 使用说明文档

---

## 十、依赖安装清单

### Python 后端依赖 (web/requirements.txt)

```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
python-docx>=1.1.0
openpyxl>=3.1.0
python-pptx>=0.6.23
mammoth>=1.8.0
httpx>=0.27.0
watchdog>=4.0.0
python-multipart>=0.0.9
```

### 前端依赖 (web/frontend/package.json 主要部分)

```json
{
  "dependencies": {
    "vue": "^3.5",
    "element-plus": "^2.8",
    "monaco-editor": "^0.50",
    "markdown-it": "^14.0",
    "pdfjs-dist": "^4.0",
    "splitpanes": "^3.1",
    "axios": "^1.7",
    "pinia": "^2.2"
  }
}
```

---

## 十一、启动脚本示例

### 启动Web.bat

```batch
@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ===================================
echo   Code880 Web 界面启动中...
echo ===================================
echo.

REM 检查虚拟环境
if not exist ".venv\Scripts\python.exe" (
    echo [错误] 未检测到 Python 虚拟环境
    echo 请先运行"一键安装.exe"安装开发环境
    pause
    exit /b 1
)

REM 安装 Web 依赖（首次自动安装）
if not exist "web\backend\.web_deps_installed" (
    echo [信息] 首次启动，正在安装 Web 依赖...
    .venv\Scripts\python.exe -m uv pip install -r web\requirements.txt -q
    echo installed > web\backend\.web_deps_installed
)

REM 启动 Web 服务
echo [信息] 正在启动 Web 服务...
echo [信息] 浏览器将自动打开 http://localhost:8880
echo [信息] 按 Ctrl+C 停止服务
echo.
start "" http://localhost:8880
.venv\Scripts\python.exe web\backend\main.py
```

---

## 十二、与现有项目的兼容性

| 方面 | 兼容策略 |
|------|---------|
| 目录结构 | Web 代码放在新增的 `web/` 目录，不修改任何已有文件 |
| Python 环境 | 复用项目已有的 `.venv` 虚拟环境 |
| VSCode 使用 | Web 端与 VSCode 可共存，不冲突 |
| 一键安装 | 原 `一键安装.exe` 流程不变，Web 端为可选增强 |
| 函数调试助手 | 原有桌面 GUI 功能保留，Web 端为额外入口 |

---

## 十三、后续扩展方向（可选）

1. **代码编辑功能**：将 Monaco Editor 从只读升级为可编辑，支持保存文件
2. **终端模拟**：集成 xterm.js 提供 Web 终端，可运行 Python 脚本
3. **多人协作**：如果部署到服务器，支持多人同时查看/对话
4. **插件系统**：允许用户自定义文件预览方式
5. **代码执行**：在 Web 端直接运行 Python 代码并展示输出（类似 Jupyter）
6. **版本对比**：集成文件 diff 展示功能

---

## 十四、总结

本方案将 VSCode 的"文件浏览 + 代码查看 + AI 对话"能力迁移到 Web 端，核心优势：

1. **零门槛**：用户不需要懂 VSCode，打开浏览器就能用
2. **一键启动**：延续 code880 的"一键"哲学
3. **无需 VSCode 运行**：底层是轻量级 Python 服务，非 VSCode 进程
4. **保留兼容**：不动现有任何代码和配置，新增 `web/` 目录独立运行
5. **AI 原生**：从设计之初就集成 AI 对话能力，比 VSCode 插件更简单直接

---

> 文档版本：v1.0 | 创建日期：2026-04-28 | 作者：AI 辅助设计
