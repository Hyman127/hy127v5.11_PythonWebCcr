# __debugger_skip__ = True
"""
版本信息：
    作者：郑广学
    版本：1.0.1
    日期：2025.10.23 
    更新：修复了相对导入模块的问题
函数执行器 - UI与功能分离版本
支持GUI模式和命令行模式，支持通过行号定位函数
"""
import tkinter as tk
from tkinter import ttk
import ast
import sys
import io
from contextlib import redirect_stdout, redirect_stderr
import inspect
import json
import os
import warnings
warnings.filterwarnings('ignore')  # 禁用一些库的警告信息
os.environ['PYTHONWARNINGS'] = 'ignore'

# 第三方库导入
try:
    # 启用拼音搜索请安装pypinyin库
    # uv add pypinyin
    from pypinyin import lazy_pinyin, Style
except:
    pass

import ttkbootstrap as ttkb
from ttkbootstrap.constants import *
import re

# ==================== 核心功能模块 ====================


class 函数扫描器:
    """
    函数扫描器 - 负责扫描和分析Python文件中的函数
    """
    
    def __init__(self, 目标文件路径):
        """
        初始化函数扫描器
        
        Args:
            目标文件路径 (str): 目标Python文件路径
        """
        self.目标文件路径 = 目标文件路径
        self.函数列表 = []
        self.扫描函数()
    
    def 扫描函数(self):
        """扫描目标文件中的无参函数"""
        try:
            with open(self.目标文件路径, 'r', encoding='utf-8') as 文件:
                源代码 = 文件.read()
            
            语法树 = ast.parse(源代码)
            
            for 节点 in ast.walk(语法树):
                if isinstance(节点, ast.FunctionDef):
                    # 检查函数是否没有参数
                    if not 节点.args.args and not 节点.args.vararg and not 节点.args.kwarg:
                        函数名 = 节点.name
                        文档字符串 = ast.get_docstring(节点)
                        
                        # 只取第一行有效文字作为说明
                        说明文字 = "无函数说明"
                        if 文档字符串:
                            第一行 = 文档字符串.split('\n')[0].strip()
                            if 第一行:
                                说明文字 = 第一行
                        
                        # 添加拼音首字母信息
                        try:
                            拼音首字母 = ''.join(lazy_pinyin(函数名, style=Style.FIRST_LETTER))
                        except:
                            拼音首字母 = 函数名
                        
                        # 计算函数的结束行号
                        结束行号 = 节点.end_lineno if hasattr(节点, 'end_lineno') else 节点.lineno
                        
                        self.函数列表.append({
                            '名称': 函数名,
                            '说明': 说明文字,
                            '开始行号': 节点.lineno,
                            '结束行号': 结束行号,
                            '拼音首字母': 拼音首字母
                        })
        except Exception as 错误:
            print(f"扫描函数时出错: {错误}")
            raise
    
    def 获取函数列表(self):
        """获取扫描到的函数列表"""
        return self.函数列表
    
    def 根据名称获取函数(self, 函数名):
        """根据名称获取函数信息"""
        return next((函数 for 函数 in self.函数列表 if 函数['名称'] == 函数名), None)
    
    def 根据行号获取函数(self, 行号):
        """
        根据行号获取函数信息
        
        Args:
            行号 (int): 代码行号
            
        Returns:
            dict: 函数信息，如果找不到返回None
        """
        行号 = int(行号)
        
        # 查找包含该行号的函数
        for 函数 in self.函数列表:
            if 函数['开始行号'] <= 行号 <= 函数['结束行号']:
                return 函数
        return None


class 函数执行器:
    """
    函数执行器 - 负责执行Python文件中的函数
    """
    
    def __init__(self, 目标文件路径):
        """
        初始化函数执行器
        
        Args:
            目标文件路径 (str): 目标Python文件路径
        """
        self.目标文件路径 = 目标文件路径
    
    def 执行整个文件(self, 捕获输出=True):
        """
        执行整个Python文件
        
        Args:
            捕获输出 (bool): 是否捕获输出
            
        Returns:
            str: 文件执行的输出结果
        """
        # 获取目标文件所在目录
        目标文件目录 = os.path.dirname(os.path.abspath(self.目标文件路径))
        
        # 保存原始环境
        原始sys_path = sys.path.copy()
        原始工作目录 = os.getcwd()
        
        try:
            # 添加目标文件目录到 sys.path
            if 目标文件目录 not in sys.path:
                sys.path.insert(0, 目标文件目录)
            
            sys.path.insert(0, 原始工作目录)
            
            # 读取并执行目标文件
            with open(self.目标文件路径, 'r', encoding='utf-8') as 文件:
                源代码 = 文件.read()
            
            if 捕获输出:
                # 创建字符串IO对象来捕获输出
                标准输出捕获 = io.StringIO()
                错误输出捕获 = io.StringIO()
                
                # 执行代码并捕获输出
                with redirect_stdout(标准输出捕获), redirect_stderr(错误输出捕获):
                    # 创建一个新的命名空间来避免变量污染
                    执行命名空间 = {
                        '__name__': '__main__',
                        '__file__': os.path.abspath(self.目标文件路径),
                    }
                    exec(compile(源代码, self.目标文件路径, 'exec'), 执行命名空间)
                
                # 获取捕获的输出
                标准输出内容 = 标准输出捕获.getvalue()
                错误输出内容 = 错误输出捕获.getvalue()
                
                # 同时输出到控制台
                if 标准输出内容.strip():
                    print(标准输出内容, end='')
                if 错误输出内容.strip():
                    print(错误输出内容, end='', file=sys.stderr)
                
                # 构建完整的输出结果
                输出行列表 = []
                if 标准输出内容.strip():
                    输出行列表.append("标准输出:")
                    输出行列表.append(标准输出内容)
                if 错误输出内容.strip():
                    输出行列表.append("错误输出:")
                    输出行列表.append(错误输出内容)
                    
                if not 输出行列表:
                    return "文件执行完成，无输出"
                else:
                    return "\n".join(输出行列表)
            else:
                # 不捕获输出，直接执行
                执行命名空间 = {
                    '__name__': '__main__',
                    '__file__': os.path.abspath(self.目标文件路径),
                }
                exec(compile(源代码, self.目标文件路径, 'exec'), 执行命名空间)
                return "文件执行完成"
                
        finally:
            # 恢复原始环境
            sys.path = 原始sys_path
            os.chdir(原始工作目录)
            try:
                import pythoncom
                pythoncom.CoUninitialize()
                #print("清理COM资源")
            except:
                pass     
    
    def 过滤源代码(self, 源代码):
        """
        过滤掉源代码中的 if __name__ == "__main__": 块
        
        Args:
            源代码 (str): 原始Python源代码
            
        Returns:
            str: 过滤后的源代码
        """
        # 匹配 if __name__ == "__main__": 及其后面的所有内容
        # 支持多种写法：单引号、双引号、有无空格
        模式 = r'^\s*if\s+__name__\s*==\s*["\']__main__["\']\s*:\s*(?:#.*)?$.*'
        
        # 使用 MULTILINE 和 DOTALL 标志
        # MULTILINE: ^ 和 $ 匹配每行的开始和结束
        # DOTALL: . 匹配包括换行符在内的所有字符
        过滤后的代码 = re.sub(模式, '', 源代码, flags=re.MULTILINE | re.DOTALL)
        
        return 过滤后的代码
    
    def 执行函数(self, 函数名, 捕获输出=True):
        
        """
        执行指定的函数
        
        Args:
            函数名 (str): 函数名称
            捕获输出 (bool): 是否捕获输出
            
        Returns:
            str: 函数执行的输出结果
        """
        # 获取目标文件所在目录
        目标文件目录 = os.path.dirname(os.path.abspath(self.目标文件路径))
        
        # 保存原始环境
        原始sys_path = sys.path.copy()
        原始工作目录 = os.getcwd()
        
        try:
            # 添加目标文件目录到 sys.path 首位
            if 目标文件目录 not in sys.path:
                sys.path.insert(0, 目标文件目录)
            sys.path.insert(0, 原始工作目录)
            # 切换工作目录到目标文件所在目录
            #os.chdir(目标文件目录)
            
            # 读取并执行目标文件
            with open(self.目标文件路径, 'r', encoding='utf-8') as 文件:
                源代码 = 文件.read()
            源代码 = self.过滤源代码(源代码)
            
            # 创建执行命名空间来避免变量污染
            执行命名空间 = {
                '__name__': '__main__',
                '__file__': os.path.abspath(self.目标文件路径),
            }
            
            # 执行代码
            exec(compile(源代码, self.目标文件路径, 'exec'), 执行命名空间)
            
            if 捕获输出:
                # 创建字符串IO对象来捕获输出
                标准输出捕获 = io.StringIO()
                错误输出捕获 = io.StringIO()
                
                # 执行指定函数并捕获输出
                if 函数名 in 执行命名空间:
                    函数 = 执行命名空间[函数名]
                    if callable(函数):
                        with redirect_stdout(标准输出捕获), redirect_stderr(错误输出捕获):
                            结果 = 函数()
                    else:
                        结果 = 函数
                else:
                    return f"错误: 函数 '{函数名}' 未找到"
                
                # 获取捕获的输出
                标准输出内容 = 标准输出捕获.getvalue()
                错误输出内容 = 错误输出捕获.getvalue()
                
                # 同时输出到控制台
                if 标准输出内容.strip():
                    print(标准输出内容, end='')
                if 错误输出内容.strip():
                    print(错误输出内容, end='', file=sys.stderr)
                
                # 构建完整的输出结果
                输出行列表 = []
                if 标准输出内容.strip():
                    输出行列表.append("标准输出:")
                    输出行列表.append(标准输出内容)
                if 错误输出内容.strip():
                    输出行列表.append("错误输出:")
                    输出行列表.append(错误输出内容)
                if 结果 is not None:
                    输出行列表.append(f"函数返回值: {结果}")
                    
                if not 输出行列表:
                    return "函数执行完成，无输出"
                else:
                    return "\n".join(输出行列表)
            else:
                # 不捕获输出，直接执行
                if 函数名 in 执行命名空间:
                    函数 = 执行命名空间[函数名]
                    if callable(函数):
                        结果 = 函数()
                        return f"函数 '{函数名}' 执行完成"
                    else:
                        return f"错误: '{函数名}' 不是可调用对象"
                else:
                    return f"错误: 函数 '{函数名}' 未找到"
                    
        finally:
            # 恢复原始环境
            sys.path = 原始sys_path
            os.chdir(原始工作目录)
            
            try:
                import pythoncom
                pythoncom.CoUninitialize()
                #print("清理COM资源")
            except:
                pass     


class 配置管理器:
    """
    配置管理器 - 负责加载和保存配置
    """
    
    def __init__(self, 配置文件="函数调试助手_config.json"):
        """
        初始化配置管理器
        
        Args:
            配置文件 (str): 配置文件路径
        """
        # 获取当前脚本所在目录
        当前脚本目录 = os.path.dirname(os.path.abspath(__file__))
        # 将配置文件保存在当前脚本目录下
        self.配置文件 = os.path.join(当前脚本目录, 配置文件)
        self.默认配置 = {
            "theme": "darkly",
            "font_size": 10
        }
    
    def 加载配置(self):
        """加载配置文件"""
        if os.path.exists(self.配置文件):
            try:
                with open(self.配置文件, 'r', encoding='utf-8') as 文件:
                    配置 = json.load(文件)
                    return 配置
            except Exception as 错误:
                print(f"加载配置文件出错: {错误}")
                return self.默认配置.copy()
        else:
            return self.默认配置.copy()
    
    def 保存配置(self, 配置):
        """保存配置到文件"""
        try:
            with open(self.配置文件, 'w', encoding='utf-8') as 文件:
                json.dump(配置, 文件, ensure_ascii=False, indent=4)
        except Exception as 错误:
            print(f"保存配置文件出错: {错误}")


# ==================== UI模块 ====================


class 设置窗口:
    """设置窗口类"""
    
    def __init__(self, 父窗口, 主题变量, 字体大小变量, 更改主题回调, 更改字体回调):
        """
        初始化设置窗口
        
        Args:
            父窗口: 父窗口
            主题变量: 主题变量
            字体大小变量: 字体大小变量
            更改主题回调: 更改主题回调函数
            更改字体回调: 更改字体回调函数
        """
        self.父窗口 = 父窗口
        self.主题变量 = 主题变量
        self.字体大小变量 = 字体大小变量
        self.更改主题回调 = 更改主题回调
        self.更改字体回调 = 更改字体回调
        
        self.窗口 = None
        self.创建设置窗口()
    
    def 创建设置窗口(self):
        """创建设置窗口"""
        self.窗口 = ttkb.Toplevel(self.父窗口)
        self.窗口.title("设置")
        self.窗口.geometry("300x180")
        self.窗口.resizable(False, False)
        
        # 相对于主窗体居中显示
        self.窗口.transient(self.父窗口)
        self.窗口.grab_set()
        
        # 计算居中位置
        主窗体x = self.父窗口.winfo_x()
        主窗体y = self.父窗口.winfo_y()
        主窗体宽度 = self.父窗口.winfo_width()
        主窗体高度 = self.父窗口.winfo_height()
        设置窗体宽度 = 300
        设置窗体高度 = 150
        
        x位置 = 主窗体x + (主窗体宽度 - 设置窗体宽度) // 2
        y位置 = 主窗体y + (主窗体高度 - 设置窗体高度) // 2
        
        self.窗口.geometry(f"{设置窗体宽度}x{设置窗体高度}+{x位置}+{y位置}")
        
        # 创建主框架
        主框架 = ttkb.Frame(self.窗口, padding="20")
        主框架.pack(fill=BOTH, expand=YES)
        
        # 使用网格布局
        主框架.columnconfigure(1, weight=1)
        
        # 主题设置
        主题标签 = ttkb.Label(主框架, text="主题:")
        主题标签.grid(row=0, column=0, sticky=W, padx=(0, 10), pady=(0, 10))
        
        主题选项 = ["darkly", "superhero", "solar", "cyborg"]
        主题下拉框 = ttkb.Combobox(主框架, textvariable=self.主题变量,
                                     values=主题选项, state="readonly", width=15)
        主题下拉框.grid(row=0, column=1, sticky=W, pady=(0, 10))
        
        # 绑定主题选择事件
        主题下拉框.bind('<<ComboboxSelected>>', lambda e: self.更改主题回调())
        
        # 字体大小设置
        字体标签 = ttkb.Label(主框架, text="字体大小:")
        字体标签.grid(row=1, column=0, sticky=W, padx=(0, 10), pady=(0, 15))
        
        字体选项 = list(range(8, 21))
        字体下拉框 = ttkb.Combobox(主框架, textvariable=self.字体大小变量,
                                    values=字体选项, state="readonly", width=15)
        字体下拉框.grid(row=1, column=1, sticky=W, pady=(0, 15))
        
        # 绑定字体大小选择事件
        字体下拉框.bind('<<ComboboxSelected>>', lambda e: self.更改字体回调())
        
        # 按钮框架
        按钮框架 = ttkb.Frame(主框架)
        按钮框架.grid(row=2, column=0, columnspan=2, sticky=E)
        
        # 确定按钮
        确定按钮 = ttkb.Button(按钮框架, text="确定", command=self.窗口.destroy)
        确定按钮.pack(side=RIGHT, padx=(5, 0))
        
        # 取消按钮
        取消按钮 = ttkb.Button(按钮框架, text="取消", command=self.窗口.destroy)
        取消按钮.pack(side=RIGHT)


class 函数运行器界面:
    """
    函数运行器UI类 - 负责UI展示和交互
    """
    
    def __init__(self, 扫描器, 执行器, 配置管理器):
        """
        初始化UI
        
        Args:
            扫描器 (函数扫描器): 函数扫描器
            执行器 (函数执行器): 函数执行器
            配置管理器 (配置管理器): 配置管理器
        """
        self.扫描器 = 扫描器
        self.执行器 = 执行器
        self.配置管理器 = 配置管理器
        self.函数列表 = 扫描器.获取函数列表()
        self.过滤后的函数列表 = self.函数列表.copy()
        
        # 加载配置
        self.配置 = 配置管理器.加载配置()
        self.字体大小 = self.配置.get("font_size", 10)
        self.主题 = self.配置.get("theme", "darkly")
        
        self.窗口 = None
        self.函数树 = None
        self.主题变量 = None
        self.字体大小变量 = None
    
    def 过滤函数列表(self, 搜索词):
        """根据搜索词过滤函数列表"""
        if not 搜索词:
            self.过滤后的函数列表 = self.函数列表.copy()
        else:
            self.过滤后的函数列表 = [
                函数 for 函数 in self.函数列表 
                if 搜索词.lower() in 函数['名称'].lower() or 
                   搜索词.lower() in 函数['拼音首字母'].lower()
            ]
        
        # 更新树形视图
        for 项目 in self.函数树.get_children():
            self.函数树.delete(项目)
            
        for 函数信息 in self.过滤后的函数列表:
            self.函数树.insert('', tk.END, values=(函数信息['名称'], 函数信息['说明']))
    
    def 更新字体大小(self, 大小):
        """更新界面字体大小"""
        self.字体大小 = 大小
        样式 = ttkb.Style()
        样式.configure('.', font=('微软雅黑', 大小))
        样式.configure('Treeview', rowheight=8 + 大小)
    
    def 打开设置(self):
        """打开设置窗口"""
        设置窗口(
            self.窗口,
            self.主题变量,
            self.字体大小变量,
            self.更改主题,
            self.更改字体大小回调
        )
    
    def 更改主题(self):
        """更改主题"""
        self.窗口.style.theme_use(self.主题变量.get())
        self.保存配置()
    
    def 更改字体大小回调(self):
        """更改字体大小回调"""
        self.更新字体大小(self.字体大小变量.get())
        self.保存配置()
    
    def 保存配置(self):
        """保存配置"""
        配置 = {
            "theme": self.主题变量.get(),
            "font_size": self.字体大小变量.get()
        }
        self.配置管理器.保存配置(配置)
    
    def 显示(self):
        """显示UI界面"""
        # 创建主窗口
        self.窗口 = ttkb.Window(themename=self.主题)
        窗口 = self.窗口
        窗口.title("函数执行器")
        窗口.geometry("500x600")
        ttkb.LabelFrame=ttkb.Labelframe
        # 尝试定位窗体到鼠标所在屏幕
        try:
            from hy127 import dialogs
            dialogs.z定位窗体到鼠标所在屏幕(窗口, "1920*1080")
        except:
            pass  # 如果导入失败，使用默认位置
        
        # 设置默认置顶
        窗口.attributes('-topmost', True)
        
        # 创建主框架
        主框架 = ttkb.Frame(窗口, padding="10")
        主框架.pack(fill=BOTH, expand=YES)
        
        # 创建函数列表框架
        列表框架 = ttkb.LabelFrame(主框架, text="函数列表", padding="5")
        列表框架.pack(fill=BOTH, expand=YES, pady=(0, 10))
        
        # 添加搜索框
        搜索框架 = ttkb.Frame(列表框架)
        搜索框架.pack(fill=X, pady=(0, 5))
        
        搜索变量 = tk.StringVar()
        搜索输入框 = ttkb.Entry(搜索框架, textvariable=搜索变量)
        搜索输入框.pack(side=LEFT, fill=X, expand=YES, padx=(0, 5))
        
        # 设置按钮
        设置按钮 = ttkb.Button(搜索框架, text="设置", command=self.打开设置, bootstyle="info")
        设置按钮.pack(side=RIGHT)
        
        # 创建树形视图
        列表列 = ('函数名', '说明')
        self.函数树 = ttkb.Treeview(列表框架, columns=列表列, show='headings', height=10)
        self.函数树.heading('函数名', text='函数名', anchor=W)
        self.函数树.heading('说明', text='说明', anchor=W)
        self.函数树.column('函数名', width=150)
        self.函数树.column('说明', width=300)
        
        # 设置标题栏颜色
        样式 = ttkb.Style()
        样式.configure("Treeview.Heading", background="#222222", foreground="white")
        
        # 添加滚动条
        列表滚动条 = ttkb.Scrollbar(列表框架, orient=VERTICAL, command=self.函数树.yview)
        列表滚动条.pack(side=RIGHT, fill=Y)
        self.函数树.configure(yscrollcommand=列表滚动条.set)
        
        # 填充函数列表
        for 函数信息 in self.过滤后的函数列表:
            self.函数树.insert('', tk.END, values=(函数信息['名称'], 函数信息['说明']))
        
        self.函数树.pack(fill=BOTH, expand=YES)
        
        # 绑定搜索事件
        搜索变量.trace('w', lambda *args: self.过滤函数列表(搜索变量.get()))
        
        # 创建输出结果显示框架
        输出框架 = ttkb.LabelFrame(主框架, text="函数输出结果", padding="5")
        输出框架.pack(fill=BOTH, expand=YES, pady=(0, 10))
        
        # 创建文本框和滚动条
        输出文本框 = tk.Text(输出框架, wrap=tk.WORD, height=5)
        输出滚动条 = ttkb.Scrollbar(输出框架, orient=VERTICAL, command=输出文本框.yview)
        输出文本框.configure(yscrollcommand=输出滚动条.set)
        
        输出文本框.pack(side=LEFT, fill=BOTH, expand=YES)
        输出滚动条.pack(side=RIGHT, fill=Y)
        
        # 创建按钮框架
        按钮框架 = ttkb.Frame(主框架)
        按钮框架.pack(fill=X)
        
        # 置顶功能
        def 切换置顶():
            当前状态 = 窗口.attributes('-topmost')
            窗口.attributes('-topmost', not 当前状态)
            置顶复选框_var.set(not 当前状态)
        
        置顶复选框_var = tk.BooleanVar(value=True)
        置顶复选框 = ttkb.Checkbutton(
            按钮框架, 
            text="窗口置顶", 
            variable=置顶复选框_var, 
            command=切换置顶
        )
        置顶复选框.pack(side=LEFT, padx=(0, 5))
        
        # 执行函数按钮
        def 执行选择函数():
            选择 = self.函数树.selection()
            if not 选择:
                from ttkbootstrap.dialogs import Messagebox
                Messagebox.show_info("请先选择函数", "提示")
                return
            
            选择项目 = self.函数树.item(选择[0])
            选择函数名 = 选择项目['values'][0]
            
            # 清空输出文本框
            输出文本框.delete(1.0, tk.END)
            
            # 执行函数
            try:
                结果 = self.执行器.执行函数(选择函数名)
                输出文本框.insert(tk.END, 结果)
                输出文本框.see(tk.END)
            except Exception as 错误:
                from ttkbootstrap.dialogs import Messagebox
                Messagebox.show_error(f"执行函数时出错: {str(错误)}", "错误")
        
        # 双击执行
        self.函数树.bind('<Double-Button-1>', lambda e: 执行选择函数())
        
        # 创建执行按钮
        执行按钮 = ttkb.Button(按钮框架, text="执行选中函数", command=执行选择函数)
        执行按钮.pack(side=LEFT, fill=X, expand=YES, padx=(0, 5))
        
        # 创建关闭按钮
        关闭按钮 = ttkb.Button(按钮框架, text="关闭", command=窗口.destroy)
        关闭按钮.pack(side=LEFT, fill=X, expand=YES, padx=(5, 0))
        
        # 初始化主题和字体变量
        self.主题变量 = tk.StringVar(value=self.主题)
        self.字体大小变量 = tk.IntVar(value=self.字体大小)
        
        # 应用保存的字体大小
        self.更新字体大小(self.字体大小)
        
        # 主循环
        窗口.mainloop()


# ==================== 主控制器 ====================


class 函数运行器:
    """
    函数运行器主控制器
    协调各个模块，提供统一接口
    """
    
    def __init__(self, 目标文件路径):
        """
        初始化函数运行器
        
        Args:
            目标文件路径 (str): 目标Python文件路径
        """
        self.目标文件路径 = 目标文件路径
        self.扫描器 = 函数扫描器(目标文件路径)
        self.执行器 = 函数执行器(目标文件路径)
        self.配置管理器 = 配置管理器()
    
    def 列出函数列表(self):
        """列出所有可用的函数"""
        函数列表 = self.扫描器.获取函数列表()
        if not 函数列表:
            print("没有找到可执行的无参函数")
            return
        
        print(f"\n在文件 '{self.目标文件路径}' 中找到 {len(函数列表)} 个可执行函数:\n")
        for 序号, 函数 in enumerate(函数列表, 1):
            print(f"{序号}. {函数['名称']}")
            print(f"   说明: {函数['说明']}")
            print(f"   行号: {函数['开始行号']}-{函数['结束行号']}\n")
    
    def 执行函数(self, 函数名, 捕获输出=False):
        """
        执行指定函数
        
        Args:
            函数名 (str): 函数名称
            捕获输出 (bool): 是否捕获输出（命令行模式下通常为False）
        """
        # 检查函数是否存在
        函数信息 = self.扫描器.根据名称获取函数(函数名)
        if not 函数信息:
            print(f"错误: 函数 '{函数名}' 不存在或不是无参函数")
            print("尝试执行整个文件...")
            结果 = self.执行器.执行整个文件(捕获输出)
            if 捕获输出:
                print(结果)
            return False
        
        print(f"\n执行函数: {函数名}")
        print(f"说明: {函数信息['说明']}")
        print(f"位置: 行 {函数信息['开始行号']}-{函数信息['结束行号']}")
        print("-" * 50)
        
        结果 = self.执行器.执行函数(函数名, 捕获输出)
        
        if 捕获输出:
            print(结果)
        
        print("-" * 50)
        print("执行完成\n")
        return True
    
    def 根据行号执行函数(self, 行号, 捕获输出=False):
        """
        根据行号执行函数
        
        Args:
            行号 (int): 代码行号
            捕获输出 (bool): 是否捕获输出
        """
        函数信息 = self.扫描器.根据行号获取函数(行号)
        
        if not 函数信息:
            print(f"错误: 在行号 {行号} 附近没有找到可执行的函数")
            print("直接运行整个文件...")
            结果 = self.执行器.执行整个文件(捕获输出)
            if 捕获输出:
                print(结果)
            return False
        
        函数名 = 函数信息['名称']
        
        print(f"正在运行函数: {函数名}...")
        结果 = self.执行器.执行函数(函数名, 捕获输出)
        
        if 捕获输出:
            print(结果)
        
        print("-" * 50)
        print(f"{函数名} 运行完成\n")
        return True
    
    def 显示界面(self):
        """显示图形界面"""
        界面 = 函数运行器界面(self.扫描器, self.执行器, self.配置管理器)
        界面.显示()


# ==================== 外部接口函数 ====================


def 函数调试助手(目标文件路径=None, 函数名=None, 行号=None, 显示UI=True):
    """
    函数调试助手 - 统一入口函数
    
    Args:
        目标文件路径 (str, optional): 目标文件路径，默认为当前文件
        函数名 (str, optional): 要执行的函数名，如果指定则不显示UI
        行号 (int, optional): 代码行号，根据行号定位并执行函数
        显示UI (bool, optional): 是否显示UI，默认为True
    
    Examples:
        # 显示UI模式
        函数调试助手("test.py")
        
        # 命令行模式 - 执行指定函数
        函数调试助手("test.py", 函数名="测试函数", 显示UI=False)
        
        # 命令行模式 - 根据行号执行函数
        函数调试助手("test.py", 行号=25, 显示UI=False)
        
        # 列出所有函数
        函数调试助手("test.py", 显示UI=False)
    """
    # 如果没有指定目标文件，使用当前文件
    if 目标文件路径 is None:
        目标文件路径 = os.path.abspath(__file__)
    
    # 检查文件是否存在
    if not os.path.exists(目标文件路径):
        print(f"错误: 文件 '{目标文件路径}' 不存在")
        return False
    
    # 创建运行器
    运行器 = 函数运行器(目标文件路径)
    
    # 优先处理行号参数
    if 行号 is not None:
        return 运行器.根据行号执行函数(行号, 捕获输出=False)
    
    # 如果指定了函数名，直接执行
    if 函数名:
        return 运行器.执行函数(函数名, 捕获输出=False)
    
    # 如果不显示UI，列出所有函数
    if not 显示UI:
        运行器.列出函数列表()
        # 如果没有找到可执行函数，则执行整个文件
        if not 运行器.扫描器.获取函数列表():
            print("\n没有找到可执行的无参函数，正在执行整个文件...")
            运行器.执行器.执行整个文件(捕获输出=False)
        return True
    
    # 显示UI
    运行器.显示界面()
    return True


# ==================== 测试函数 ====================


def testfun():
    """测试函数"""
    print("testfun")


# ==================== 命令行入口 ====================


def main():
    """命令行入口函数"""
    import argparse
    
    解析器 = argparse.ArgumentParser(description='函数执行器 - 扫描并执行Python文件中的无参函数')
    解析器.add_argument('file', nargs='?', help='目标Python文件路径（可选，默认为当前文件）')
    解析器.add_argument('-f', '--function', help='要执行的函数名（指定后不显示UI）')
    解析器.add_argument('-L', '--line', type=int, help='代码行号，根据行号定位并执行函数')
    解析器.add_argument('-l', '--list', action='store_true', help='列出所有可用函数')
    解析器.add_argument('--no-ui', action='store_true', help='不显示UI界面')
    
    参数 = 解析器.parse_args()
    
    # 确定目标文件
    目标文件 = 参数.file if 参数.file else os.path.abspath(__file__)
    
    # 检查文件是否存在
    if not os.path.exists(目标文件):
        print(f"错误: 文件 '{目标文件}' 不存在")
        sys.exit(1)
    
    # 根据参数决定运行模式
    if 参数.line is not None:
        # 根据行号执行函数
        函数调试助手(目标文件, 行号=参数.line, 显示UI=False)
    elif 参数.function:
        # 执行指定函数
        函数调试助手(目标文件, 函数名=参数.function, 显示UI=False)
    elif 参数.list or 参数.no_ui:
        # 列出所有函数
        函数调试助手(目标文件, 显示UI=False)
    else:
        print("启动函数列表调试界面...")
        # 显示UI
        函数调试助手(目标文件)


if __name__ == "__main__":
    main()
