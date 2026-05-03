#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
项目打包脚本
用于将Python项目打包为可执行文件
支持打包说明文件、许可提示文件和必要资源到 exe 使用
本文件末尾的获取资源路径函数可放到 main.py 中，用于加载被 PyInstaller 打包的资源
作者: 郑广学 hy127.cn 2025.11.25
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

def 打包项目():
    """打包项目为可执行文件"""
    # 项目配置字典
    配置 = {
        "exe名称": "一键安装", # 打包后的exe名称
        "入口文件": "src/一键安装卸载.py", #顶层是当前项目目录 src/代表在src目录下
        "图标路径": "",
        "文件夹": [],
        "文件": ["一键安装说明.md", "THIRD_PARTY_NOTICES.md"]
    }
    
    # 获取项目根目录
    项目根目录 = Path(__file__).parent.parent
    主程序文件 = 项目根目录 / 配置["入口文件"]  # 直接在根目录查找
    图标文件 = 项目根目录 / 配置["图标路径"] if 配置["图标路径"] else None
    exe文件名 = 配置["exe名称"]
    if not 主程序文件.exists():
        print(f"错误: 找不到主程序文件 {主程序文件}")
        return False

    try:
        源码内容 = 主程序文件.read_text(encoding="utf-8")
        compile(源码内容, str(主程序文件), "exec")
        print(f"语法检查通过: {主程序文件}")
    except SyntaxError as 错误:
        print("错误: 主程序语法检查失败，已停止打包。")
        print(错误)
        return False
        
    # 构建打包命令
    命令 = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--windowed",  # 窗口模式，不显示控制台
        "--onefile",   # 打包为单个可执行文件
        "--clean",     # 清理缓存
        "--name", exe文件名,
        str(主程序文件)
    ]
    
    # 如果图标文件存在，则添加图标参数
    if 图标文件 and 图标文件.exists():
        命令.extend(["--icon", str(图标文件)])
    
    # 添加项目根目录，确保所有模块都能被打包
    命令.extend(["--paths", str(项目根目录)])
    
    # 添加文件
    for 额外路径 in 配置["文件"]:
        额外路径对象 = 项目根目录 / 额外路径
        if 额外路径对象.exists():
            命令.extend(["--add-data", f"{额外路径对象}{os.pathsep}."])
            print(f"已添加额外文件: {额外路径对象}")
    
    # 添加资源文件夹列表
    for 资源目录名 in 配置["文件夹"]:
        资源目录 = 项目根目录 / 资源目录名
        if 资源目录.exists():
            命令.extend(["--add-data", f"{资源目录}{os.pathsep}{资源目录名}"])
            print(f"已添加资源文件夹: {资源目录}")
        else:
            print(f"警告: 未找到资源文件夹 {资源目录}")
    
    # 指定打包输出目录为 package
    package目录 = 项目根目录 / "package"
    package目录.mkdir(exist_ok=True)
    for 待清理路径 in (package目录 / "build", package目录 / "dist", package目录 / f"{exe文件名}.spec"):
        if 待清理路径.exists():
            if 待清理路径.is_dir():
                shutil.rmtree(待清理路径)
            else:
                待清理路径.unlink()
            print(f"已清理旧打包产物: {待清理路径}")
    命令.extend(["--distpath", str(package目录 / "dist")])
    命令.extend(["--workpath", str(package目录 / "build")])
    spec文件路径 = package目录 / f"{exe文件名}.spec"
    命令.extend(["--specpath", str(package目录)])
    
    print("正在执行打包命令:")
    print(" ".join(命令))
    
    try:
        # 执行打包命令
        print("提示: --onefile 打包阶段可能需要几分钟，请等待完成，不要中断。")
        subprocess.check_call(命令, cwd=项目根目录)
        print("打包完成!")
        print(f"可执行文件位置: {package目录 / 'dist' / f'{exe文件名}.exe'}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"打包失败: {e}")
        return False
    except FileNotFoundError:
        print("找不到PyInstaller，请确保已正确安装")
        return False

def 清理打包文件():
    """清理打包过程中生成的临时文件"""
    项目根目录 = Path(__file__).parent.parent
    # 清理 package 目录下的打包文件
    package目录 = 项目根目录 / "package"
    清理目录列表 = [package目录 / "build", package目录 / "dist"]
    清理文件列表 = [f for f in package目录.glob("*.spec")]
    
    for 目录路径 in 清理目录列表:
        if 目录路径.exists():
            import shutil
            shutil.rmtree(目录路径)
            print(f"已删除目录: {目录路径}")
    
    for 文件 in 清理文件列表:
        文件.unlink()
        print(f"已删除文件: {文件}")

    # 如果 package 目录为空，则删除它
    try:
        if package目录.exists() and not any(package目录.iterdir()):
            package目录.rmdir()
            print(f"已删除空目录: {package目录}")
    except Exception:
        pass  # 忽略删除空目录时可能发生的错误

def 显示帮助():
    """显示帮助信息"""
    print("使用方法:")
    print("  python pyinstaller_build.py     - 直接打包项目")
    print("  python pyinstaller_build.py clean - 清理打包文件")

def 安装打包工具():
    """安装PyInstaller打包工具"""
    print("检查PyInstaller是否已安装...")
    try:
        import PyInstaller
        print("PyInstaller已安装!")
        return True
    except ImportError:
        print("正在安装PyInstaller...")
        try:
            # 直接使用uv命令安装
            subprocess.check_call(["uv", "add", "pyinstaller"])
            print("PyInstaller安装成功!")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("PyInstaller安装失败!请手动运行: uv add pyinstaller")
            return False

def 主函数():
    """主函数"""
    # 检查是否有参数传入
    if len(sys.argv) > 1:
        操作 = sys.argv[1].lower()
        if 操作 == "clean":
            清理打包文件()
            return
        elif 操作 == "help":
            显示帮助()
            return
        else:
            print(f"未知操作: {操作}")
            显示帮助()
            return
    
    # 默认操作：直接打包项目
    print("开始打包项目...")
    if 安装打包工具():
        打包项目()
    else:
        print("打包工具安装失败，无法继续打包")

# 获取资源文件的正确路径 这个代码放到main函数里加载资源时使用
def 获取资源路径(相对路径):
    """获取资源文件的绝对路径，兼容PyInstaller打包后的环境"""
    try:
        # PyInstaller创建临时文件夹，并将路径存储在_MEIPASS中
        基础路径 = sys._MEIPASS
    except Exception:
        基础路径 = os.path.abspath(".")
    
    return os.path.join(基础路径, 相对路径)
    ##图标文件路径 = 获取资源路径("资源\\标题栏图标.png")

if __name__ == "__main__":
    主函数()
