# 第三方软件与许可提示

本项目模板和安装工具会帮助用户下载、安装或使用第三方软件。各软件均适用其权利人发布的许可条款，本项目不声称拥有这些第三方软件。

本“一键安装包”仅面向个人学习、课程练习和本机开发环境初始化。工程“猿”工具网仅提供信息咨询来源和安装流程指引，不提供第三方软件的所有权、授权转让或法律保证。

## 主要第三方组件

- Python: Python Software Foundation License Version 2
  - 官方许可: https://docs.python.org/3/license.html
- uv: Apache-2.0 或 MIT 双许可
  - 官方许可: https://docs.astral.sh/uv/reference/policies/license/
- Visual Studio Code: Microsoft Visual Studio Code 产品许可
  - 官方许可: https://code.visualstudio.com/license
- VSCode 扩展: Python、debugpy、Pylance 等扩展适用各自扩展许可和 Visual Studio Marketplace 条款
  - Marketplace 条款: https://aka.ms/vsmarketplace-ToU
- PyPI 依赖: arrow、pandas、psutil、pyinstaller、pywin32、screeninfo、ttkbootstrap 等适用各自包许可

## 分发建议

- 不要把 Microsoft VSCode 二进制文件直接重新打包进本项目模板或安装器。
- 安装器应在用户同意后从 Microsoft 官方地址下载 VSCode。
- Python 运行环境优先通过 uv 安装；项目依赖优先通过 uv sync 安装。
- 如果对外分发打包后的 exe，建议同时附带本文件和项目自身的许可说明。
- 商业分发、培训机构批量分发或企业内部分发前，请自行复核当地法律、出口管制、隐私合规和第三方软件许可要求。
