# Code880 Web 端 vs VSCode 端 — 全维度对比

日期: 2026-05-01

---

## 一、分发与触达

| 维度 | Web 端 | VSCode 端 |
|---|---|---|
| 安装门槛 | 运行一个脚本，浏览器打开即用 | 用户必须先装 VSCode，再装扩展 |
| 目标用户 | 零基础用户、非程序员、教学场景 | 已经使用 VSCode 的开发者 |
| 首次体验 | 秒开，心智负担低 | 需要理解 VSCode 界面 |
| 离线能力 | 本地服务，天然离线（AI 除外） | 天然离线 |
| 多设备 | 同一局域网内任意设备浏览器访问 | 只能在装了 VSCode 的机器上用 |
| 更新机制 | 替换服务端文件即可，用户无感 | 走 VSCode Marketplace 审核流程 |
| 卸载 | 删目录即可 | 需要在 VSCode 中卸载扩展 |

**结论**：Web 端触达面更广，特别是非程序员用户。VSCode 端更适合已有 VSCode 习惯的开发者。

---

## 二、Office 文档能力

| 维度 | Web 端 | VSCode 端 |
|---|---|---|
| Word 预览 | 可以做。mammoth.js 转 HTML 在浏览器渲染，格式还原度高 | 困难。VSCode Webview 渲染 HTML 有诸多限制（CSP、样式隔离） |
| Excel 预览 | 可以做。SheetJS 解析 + HTML table 渲染，支持多 sheet 切换 | 困难。Webview 中表格交互受限，滚动和大数据量体验差 |
| PPT 预览 | 可以做。python-pptx 提取 + 浏览器幻灯片渲染 | 非常困难。Webview 不适合做幻灯片翻页体验 |
| PDF 预览 | 可以做。pdf.js 浏览器原生级体验 | 可以，但需要在 Webview 中嵌入 pdf.js，体验不如浏览器 |
| 图片预览 | 浏览器原生支持，零成本 | Webview 支持，但路径和 CSP 需要额外处理 |
| Markdown 预览 | marked.js 实时渲染，完全可控 | VSCode 自带 Markdown 预览，且生态更成熟 |
| 文档编辑 | 理论上可做富文本编辑，但工程量大 | 不适合做 Office 编辑 |
| 文件导出 | 浏览器原生下载，支持导出 PDF/HTML | 需要调用系统文件对话框，流程更长 |

**结论**：Office 文档处理是 Web 端的绝对优势。浏览器天生就是文档渲染引擎，VSCode Webview 在这方面处处受限。

---

## 三、代码编辑能力

| 维度 | Web 端 | VSCode 端 |
|---|---|---|
| 编辑器 | Monaco Editor（VSCode 的内核），但功能是子集 | VSCode 完整编辑器，功能完整 |
| 语法高亮 | 支持，但语言覆盖有限 | 完整支持所有语言 |
| 智能补全 | 需要自己实现或接 LSP，工程量大 | VSCode + Pylance/Pyright 开箱即用 |
| 跳转定义 | 需要自己接 LSP，非常复杂 | 原生支持 |
| 重构 | 不支持 | 原生支持（重命名、提取函数等） |
| Git 集成 | 需要自己实现 | VSCode 内置 Git 面板 |
| 调试器 | 不支持 | 完整的 Python 调试器 |
| 多光标编辑 | Monaco 支持 | 完整支持 |
| 终端 | 浏览器 Web 终端，能力有限 | 完整的系统终端 |
| 扩展生态 | 无 | 数万个扩展 |

**结论**：代码编辑是 VSCode 端的绝对优势。Web 端的 Monaco 只是轻量编辑器，无法替代 VSCode 的完整开发体验。

---

## 四、AI 多模型能力

| 维度 | Web 端 | VSCode 端 |
|---|---|---|
| 模型配置自由度 | 完全自主。自建设置页，想支持多少 Provider 都可以 | 受限于 VSCode 扩展 API。设置走 contributes.configuration，UI 不灵活 |
| 多模型切换 | 可以做漂亮的下拉选择、角色分配、一键切换 | 只能用 VSCode 设置项或命令面板，交互生硬 |
| 模型角色分工 | 完全可控。规划用模型A，执行用模型B，审核用模型C | 技术上可以，但 UI 展示很难做好 |
| API Key 管理 | 自建加密存储（DPAPI），统一管理页面 | 存在 VSCode settings.json 或 SecretStorage，管理分散 |
| 流式输出展示 | 浏览器渲染完全可控，Markdown 实时渲染、代码高亮 | Webview 中可以做，但更新频繁时性能不如浏览器 |
| AI 对话 UI | 完全自定义。气泡、卡片、折叠、工具调用展示随意设计 | Webview 可以做，但和 VSCode 原生 UI 割裂 |
| Agent 任务面板 | 可以做完整的步骤流、审批卡片、进度条、实时日志 | Webview 可以做，但体验受限于面板大小和交互 |
| 模型连通性测试 | 可以做一键测试按钮，结果实时显示 | 可以做，但 UI 不如 Web 直观 |
| 上下文文件选择 | 可以做勾选树、拖拽、预览，交互自由 | 可以用 VSCode TreeView，但自定义程度低 |
| 成本显示 | 可以实时显示 token 用量、估算费用 | 技术上可以，但 UI 空间有限 |

**结论**：多模型 AI 能力是 Web 端的显著优势。Web 端对 UI 的完全控制权让它能做出远超 VSCode 扩展的 AI 交互体验。

---

## 五、Agent / 任务执行能力

| 维度 | Web 端 | VSCode 端 |
|---|---|---|
| 任务状态展示 | 可以做完整的状态机可视化 | 受限于 Webview 或 TreeView |
| 工具调用审批 | 可以弹出漂亮的确认卡片，展示 diff 预览 | 可以用 showInformationMessage，但太简陋 |
| Diff 预览 | 可以自己渲染 diff（类似 GitHub 的并排对比） | 可以调用 VSCode 原生 diff 编辑器，这一点 VSCode 更好 |
| 文件写入 | 通过 Worker API 写入，有备份机制 | 通过 VSCode workspace API 写入，更安全 |
| Python 执行 | 通过 TaskRunner 子进程执行 | 可以用 VSCode 终端或 Task API |
| 实时日志流 | WebSocket 推送，浏览器渲染 | OutputChannel 或终端，体验不如 Web |
| 多任务并行 | 可以设计多任务面板 | 面板空间有限 |

**结论**：Agent 任务执行两者各有所长。Web 端展示更灵活，VSCode 端和编辑器集成更自然（比如 diff 直接在编辑器中打开）。

---

## 六、安全模型

| 维度 | Web 端 | VSCode 端 |
|---|---|---|
| 文件访问控制 | 自建 validate_path，4 层校验 | VSCode workspace API 自带沙箱 |
| API Key 存储 | 自建 DPAPI 加密 | VSCode SecretStorage（底层也是 DPAPI/Keychain） |
| 会话认证 | 自建 bootstrap → session → CSRF 链 | VSCode 扩展天然受信，无需认证 |
| 网络暴露面 | 本地 HTTP 服务，需要防 CORS、防端口劫持 | 无网络暴露，进程内通信 |
| 浏览器安全 | 受浏览器同源策略保护 | 不涉及浏览器 |

**结论**：VSCode 端安全模型更简单。Web 端需要自建完整的认证和安全体系。

---

## 七、性能与资源

| 维度 | Web 端 | VSCode 端 |
|---|---|---|
| 内存占用 | Hub + Worker 进程 + 浏览器标签页 | VSCode 本身 + 扩展进程 |
| 启动速度 | 启动服务 + 打开浏览器，约 3-5 秒 | VSCode 启动 + 扩展激活，约 5-10 秒 |
| 大文件处理 | 受浏览器内存限制 | 受 VSCode 编辑器优化，大文件体验更好 |
| 并发连接 | 支持多个浏览器标签同时连接 | 单实例 |

---

## 八、产品形态定位

| 维度 | Web 端 | VSCode 端 |
|---|---|---|
| 适合场景 | 教学、非程序员使用、Office 文档处理、AI 工作台 | 日常编程、代码开发、调试 |
| 竞品对标 | Manus（本地化）、Cursor（轻量版）、Replit | VSCode + Copilot、Cursor、Windsurf |
| 差异化空间 | 大。市场上没有"本地化的轻量 Manus" | 小。VSCode AI 扩展已经非常拥挤 |
| 长期价值 | 独立产品，不依赖任何平台 | 依附于 VSCode 生态 |

---

## 九、总结矩阵

| 能力 | Web 端 | VSCode 端 | 胜出方 |
|---|---|---|---|
| 分发触达 | ★★★★★ | ★★★ | Web |
| Office 文档 | ★★★★★ | ★ | Web 碾压 |
| 代码编辑 | ★★ | ★★★★★ | VSCode 碾压 |
| AI 多模型 | ★★★★★ | ★★★ | Web 明显优势 |
| Agent 任务 | ★★★★ | ★★★ | Web |
| 安全模型 | ★★★ | ★★★★ | VSCode |
| 扩展生态 | ★ | ★★★★★ | VSCode |
| 调试能力 | ★ | ★★★★★ | VSCode |
| UI 自由度 | ★★★★★ | ★★ | Web 碾压 |
| 差异化空间 | ★★★★★ | ★★ | Web |

---

## 十、结论

VSCode 端做"代码开发"更强，Web 端做"AI 工作台 + 文档处理"更强。

如果目标是本地化 Manus（任务驱动、多模型、文档处理、非程序员友好），Web 端是正确的载体。VSCode 端永远不可能做出好的 Office 预览和灵活的 AI 任务面板。
