
# dialogs.py
"""
轻量级对话框封装 - 支持中文别名和所有常用对话框
多屏幕定位优化版本 多显示器时可以正确出现在鼠标所在屏幕中央
创建者：郑广学 2025-10-6 vbayyds.com
"""

import tkinter as tk
from tkinter import messagebox, simpledialog, filedialog
import atexit
from screeninfo import get_monitors

# 延迟初始化_root
_root = None
_root_initialized = False

def _get_root():
    """获取或创建根窗口 - 延迟初始化"""
    global _root, _root_initialized
    if _root is None or not _root_initialized:
        _root = tk.Tk()
        _root.withdraw()
        _root_initialized = True
        # 注册退出清理
        if not hasattr(_root, "_cleanup_registered"):
            atexit.register(lambda: _root.quit() or _root.destroy())
            _root._cleanup_registered = True
    return _root

def _get_mouse_monitor_info(_root):
    """获取鼠标所在监视器的信息 - 精确版"""
    # temp = tk.Toplevel(_root)
    # temp.withdraw()
    # temp.geometry("1x1+0+0")
    # temp.update_idletasks()
    # mouse_x = temp.winfo_pointerx()
    # mouse_y = temp.winfo_pointery()
    # temp.destroy()
    if _root==None: 
        _root=_get_root()
    mouse_x,mouse_y= _get_mouse_position(_root)
   
    
    # 获取所有监视器信息 (x, y 是物理坐标)
    monitors = get_monitors()
    for m in monitors:
        if (m.x <= mouse_x < m.x + m.width) and (m.y <= mouse_y < m.y + m.height):
            # 找到鼠标所在的监视器
            return m.x,m.y, m.width,m.height
    # 没找到，返回主显示器
    m = monitors[0]
    return m.x,m.y, m.width,m.height

def _position_dialog_at_mouse(dialog):
    """通用的对话框定位函数 - 定位到鼠标所在监视器中央"""
    dialog.update_idletasks()
    
    # 获取鼠标所在监视器的信息
    monitor_x, monitor_y, monitor_width, monitor_height = _get_mouse_monitor_info(dialog)
    
    # 获取对话框尺寸
    dialog_width = dialog.winfo_reqwidth()
    dialog_height = dialog.winfo_reqheight()
    
    # 计算监视器中央位置
    center_x = monitor_x + (monitor_width - dialog_width) // 2
    center_y = monitor_y + (monitor_height - dialog_height) // 2
    
    dialog.geometry(f"+{center_x}+{center_y}")

def _setup_dialog_style(dialog):
    """设置对话框样式 - 只显示x按钮"""
    dialog.resizable(False, False)
    # 移除最小化和最大化按钮，只保留关闭按钮
    dialog.attributes('-toolwindow', True)  # Windows下生效
    dialog.withdraw()

def _get_mouse_position(_root):
    """获取鼠标位置 - 更简单的方式"""
    # 直接使用_root获取鼠标位置，无需创建临时窗口
    if _root==None:
        root = _get_root()
    else:
        root = _root
    mouse_x = root.winfo_pointerx()
    mouse_y = root.winfo_pointery()
    return mouse_x, mouse_y
def _calculate_scaled_size(current_width, current_height,current_screen_width,current_screen_height, target_resolution):
    """
    根据目标分辨率计算窗口的缩放尺寸（保持原始宽高比）
    :param current_width: 当前窗口宽度
    :param current_height: 当前窗口高度
    :param current_screen_width: 当前屏幕宽度
    :param current_screen_height: 当前屏幕高度
    :param target_resolution: 目标分辨率字符串，格式如 "1920*1080"
    :return: (scaled_width, scaled_height) 缩放后的尺寸
    """
    try:
        # 解析目标分辨率
        target_width, target_height = map(int, target_resolution.split('*'))
        
        # 计算缩放比例（保持原始宽高比）
        # 使用较小的比例，确保窗口不会超出屏幕
        width_ratio = current_screen_width / target_width
        height_ratio = current_screen_height / target_height
        scale_ratio = max(width_ratio, height_ratio)
        
        # 应用统一的缩放比例
        scaled_width = int(current_width * scale_ratio)
        scaled_height = int(current_height * scale_ratio)
        
        return scaled_width, scaled_height
    except Exception:
        # 如果解析失败，返回原始尺寸
        pass
    
    return current_width, current_height
def _position_root_at_mouse():
    """将根窗口定位到鼠标所在监视器中央（完全无闪烁）"""
    root = _get_root()
    # 获取鼠标所在监视器的信息
    monitor_x, monitor_y, monitor_width, monitor_height = _get_mouse_monitor_info(root)
    
    #root.withdraw()
    # 计算监视器中央位置 左上角为起点
    center_x = monitor_x + 100#monitor_width // 2-100
    center_y = monitor_y + 100#monitor_height // 2-100
    
    # 将根窗口放到该监视器中央附近但保持隐藏
    root.geometry(f"1x1+{center_x}+{center_y}")

def MsgBox(message, title="提示", icon="info"):
    """自定义消息框，支持多屏幕定位"""
    # 创建主窗口并立即隐藏
    root = tk.Tk()
    root.withdraw()
    
    # 创建对话框
    dialog = tk.Toplevel(root)
    dialog.title(title)
    _setup_dialog_style(dialog)
    
    # 设置内容 - 更大的字体和间距
    label = tk.Label(dialog, text=message, justify=tk.LEFT, 
                    padx=50, pady=30, font=("Microsoft YaHei UI", 11))
    label.pack()
    
    button = tk.Button(dialog, text="确定", command=dialog.destroy, 
                      width=12, font=("Microsoft YaHei UI", 10))
    button.pack(pady=15)
    
    # 设置最小宽度
    dialog.update_idletasks()
    current_width = dialog.winfo_reqwidth()
    min_width = 300  # 设置最小宽度为300像素
    if current_width < min_width:
        dialog.geometry(f"{min_width}x{dialog.winfo_reqheight()}")
    
    # 定位到鼠标所在屏幕
    _position_dialog_at_mouse(dialog)
    dialog.deiconify()
    
    # 设置焦点和键盘事件
    button.focus_set()
    dialog.bind("<Return>", lambda e: dialog.destroy())
    dialog.bind("<Escape>", lambda e: dialog.destroy())
    
    # 等待对话框关闭
    dialog.wait_window(dialog)
    dialog.destroy()
    root.destroy()

def MsgBoxYesNo(message, title="确认", default_is_yes=True):
    """自定义是/否对话框，支持多屏幕定位"""
    result = [None]
    
    root = tk.Tk()
    root.withdraw()
    
    dialog = tk.Toplevel(root)
    dialog.title(title)
    _setup_dialog_style(dialog)
    
    # 内容 - 更大的字体和间距
    label = tk.Label(dialog, text=message, justify=tk.LEFT, 
                    padx=50, pady=30, font=("Microsoft YaHei UI", 11))
    label.pack()
    
    # 按钮框架
    button_frame = tk.Frame(dialog)
    button_frame.pack(pady=15)
    
    def on_yes():
        result[0] = True
        dialog.destroy()
    
    def on_no():
        result[0] = False
        dialog.destroy()
    
    yes_btn = tk.Button(button_frame, text="是", command=on_yes, 
                       width=10, font=("Microsoft YaHei UI", 10))
    no_btn = tk.Button(button_frame, text="否", command=on_no, 
                      width=10, font=("Microsoft YaHei UI", 10))
    
    yes_btn.pack(side="left", padx=8)
    no_btn.pack(side="left", padx=8)
    
    # 设置最小宽度
    dialog.update_idletasks()
    current_width = dialog.winfo_reqwidth()
    min_width = 350  # 设置最小宽度为350像素
    if current_width < min_width:
        dialog.geometry(f"{min_width}x{dialog.winfo_reqheight()}")
    
    # 键盘事件
    dialog.bind("<Return>", lambda e: on_yes() if default_is_yes else on_no())
    dialog.bind("<Escape>", lambda e: dialog.destroy())
    
    # 定位并显示
    _position_dialog_at_mouse(dialog)
    dialog.deiconify()
    
    # 设置焦点
    if default_is_yes:
        yes_btn.focus_set()
    else:
        no_btn.focus_set()
    
    dialog.wait_window(dialog)
    root.destroy()
    killroot()
    return result[0]

def InputBox(prompt, title="输入", default=""):
    """自定义输入框，支持多屏幕定位"""
    result = [None]
    
    root = tk.Tk()
    root.withdraw()
    
    dialog = tk.Toplevel(root)
    dialog.title(title)
    _setup_dialog_style(dialog)
    
    # 内容 - 更大的字体和间距
    label = tk.Label(dialog, text=prompt, justify=tk.LEFT, 
                    padx=30, pady=20, font=("Microsoft YaHei UI", 11))
    label.pack()
    
    # 修改输入框宽度从35增加到50，使其更宽
    entry = tk.Entry(dialog, width=40, font=("Microsoft YaHei UI", 10))
    entry.insert(0, default)
    entry.pack(padx=30, pady=10)
    entry.focus_set()
    
    # 按钮框架
    button_frame = tk.Frame(dialog)
    button_frame.pack(pady=20)
    
    def on_ok():
        result[0] = entry.get()
        dialog.destroy()
    
    def on_cancel():
        dialog.destroy()
    
    ok_btn = tk.Button(button_frame, text="确定", command=on_ok, 
                      width=10, font=("Microsoft YaHei UI", 10))
    cancel_btn = tk.Button(button_frame, text="取消", command=on_cancel, 
                          width=10, font=("Microsoft YaHei UI", 10))
    
    ok_btn.pack(side="left", padx=8)
    cancel_btn.pack(side="left", padx=8)
    
    # 键盘事件
    dialog.bind("<Return>", lambda e: on_ok())
    dialog.bind("<Escape>", lambda e: on_cancel())
    
    # 定位并显示
    _position_dialog_at_mouse(dialog)
    dialog.deiconify()
    
    dialog.wait_window(dialog)
    root.destroy()
    killroot()
    return result[0]

def OpenFileDialog(title="选择文件", filetypes=None):
    """单文件选择 - 优化多屏显示"""
    # 将根窗口定位到鼠标附近（无闪烁）
    _position_root_at_mouse()
    
    root = _get_root()
    rs= filedialog.askopenfilename(
        title=title,
        filetypes=filetypes or [("所有文件", "*.*")],
        parent=root
    )
    killroot()
    return rs
def killroot():
    global _root_initialized
    _root_initialized=False
    if not _root is None : _root.destroy()
def OpenMultipleFilesDialog(title="选择多个文件", filetypes=None):
    """多文件选择 - 优化多屏显示"""
    _position_root_at_mouse()
    
    root = _get_root()
    paths = filedialog.askopenfilenames(
        title=title,
        filetypes=filetypes or [("所有文件", "*.*")],
        parent=root
    )
    killroot()
    return list(paths) if paths else []

def SaveFileDialog(title="保存文件", defaultext="", filetypes=None):
    """保存文件对话框 - 优化多屏显示"""
    _position_root_at_mouse()
    
    root = _get_root()
    rs= filedialog.asksaveasfilename(
        title=title,
        defaultextension=defaultext,
        filetypes=filetypes or [("所有文件", "*.*")],
        parent=root
    )
    killroot()
    return rs

def FolderBrowserDialog(title="选择文件夹"):
    """选择文件夹对话框 - 优化多屏显示"""
    _position_root_at_mouse()
    
    root = _get_root()
    rs= filedialog.askdirectory(title=title, parent=root)
    killroot()
    return rs
def position_window_at_mousescreen(window,target_resolution=None): #代码放在目标窗体显示之前
    """通用的窗体定位函数 - 定位到鼠标所在监视器中央"""
    # 先将窗口显示在极远的负坐标上，确保布局完成
    #position_window_at_mousescreen(root,"1920*1080")
    window.geometry(f"-9999-9999") #定位
    # window.deiconify()
    window.update_idletasks()
    # 获取窗体实际尺寸
    window_width = window.winfo_width()
    window_height = window.winfo_height()

    # 再隐藏窗口避免闪烁
    window.withdraw()

    # 获取鼠标所在监视器的信息
    monitor_x, monitor_y, monitor_width, monitor_height = _get_mouse_monitor_info(window)
        # 如果提供了目标分辨率，则计算缩放后的尺寸
    if target_resolution:
        window_width, window_height = _calculate_scaled_size(window_width, window_height,monitor_width,monitor_height, target_resolution)
    
    # 计算监视器中央位置
    center_x = monitor_x + (monitor_width - window_width) // 2
    center_y = monitor_y + (monitor_height - window_height) // 2 

    # 设置最终位置
    window.geometry(f"{window_width}x{window_height}+{center_x}+{center_y}")
    # 定位完成后再显示窗口
    window.deiconify()

def scale_window_size(window, target_resolution=None):
    """缩放窗体尺寸工具函数 - 保持原始位置和比例
    
    Args:
        window: 目标窗体
        target_resolution: 目标分辨率字符串，格式如 "1920*1080"，可选
    """
    # 获取窗体当前位置（不改变）
    位置X = window.winfo_x()
    位置Y = window.winfo_y()
    
    # 获取窗体实际尺寸
    窗体宽度 = window.winfo_width()
    窗体高度 = window.winfo_height()
    
    # 如果提供了目标分辨率，则计算缩放后的尺寸
    if target_resolution:
        # 获取鼠标所在监视器的信息用于计算缩放比例
        监视器X, 监视器Y, 监视器宽度, 监视器高度 = _get_mouse_monitor_info(window)
        
        # 计算缩放比例（保持原始比例）
        窗体宽度, 窗体高度 = _calculate_scaled_size(
            窗体宽度, 窗体高度,
            监视器宽度, 监视器高度,
            target_resolution
        )
    
    # 设置新尺寸，保持原始位置
    window.geometry(f"{窗体宽度}x{窗体高度}+{位置X}+{位置Y}")


# --- 快捷别名（中文命名） ---
z确定消息框 = MsgBox
z是否消息框 = MsgBoxYesNo
z输入框 = InputBox
z选择文件对话框 = OpenFileDialog
z选择多文件对话框 = OpenMultipleFilesDialog
z保存文件对话框 = SaveFileDialog
z选择文件夹对话框 = FolderBrowserDialog
z定位窗体到鼠标所在屏幕=position_window_at_mousescreen 
z缩放窗体尺寸=scale_window_size
# --- 测试代码 ---
def 控制台测试():
    """测试所有对话框功能"""
    print("🚀 开始测试所有对话框...")

    # 1. 消息框（信息）
    MsgBox("欢迎使用对话框测试程序！", "启动")

    # 2. 是/否对话框
    if MsgBoxYesNo("是否继续？", "确认"):
        print("✅ 用户选择了【是】")
    else:
        print("❌ 用户选择了【否】")
        return

    # 3. 输入框
    name = InputBox("请输入你的姓名：", "用户信息", default="张三")
    if name:
        print(f"👤 姓名：{name}")
    else:
        print("🟡 用户取消输入")

    # 4. 单文件选择
    file_path = OpenFileDialog("请选择一个配置文件", filetypes=[("文本文件", "*.txt"), ("Python文件", "*.py")])
    if file_path:
        print(f"📄 文件路径：{file_path}")
    else:
        print("🟡 未选择文件")

    # 5. 多文件选择
    files = OpenMultipleFilesDialog("请选择多个图片文件", filetypes=[("图片", "*.jpg;*.png")])
    if files:
        print(f"🖼️ 选择了 {len(files)} 个文件：")
        for f in files:
            print(f"   - {f}")
    else:
        print("🟡 未选择任何文件")

    # 6. 保存文件
    save_path = SaveFileDialog("另存为", defaultext=".txt", filetypes=[("文本文件", "*.txt")])
    if save_path:
        print(f"💾 保存路径：{save_path}")
    else:
        print("🟡 取消保存")

    # 7. 选择文件夹
    folder = FolderBrowserDialog("请选择工作目录")
    if folder:
        print(f"📂 文件夹路径：{folder}")
    else:
        print("🟡 未选择文件夹")

    print("🎉 所有测试完成！")


def 窗体测试界面():
    """创建图形化测试界面"""
    import tkinter as tk
    from tkinter import ttk
    
    root = tk.Tk()
    root.title("对话框功能演示")
    root.geometry("500x650")
    root.resizable(False, False)
    
    # 使用通用定位函数将窗体定位到鼠标所在屏幕
    
    position_window_at_mousescreen(root)
   
    z缩放窗体尺寸(root,"1920*1080")
    # 设置黑色主题样式
    root.configure(bg="#1e1e1e")
    
    # 设置整体样式
    style = ttk.Style()
    style.configure("TButton", font=("Microsoft YaHei UI", 10), padding=6)
    style.configure("TLabel", font=("Microsoft YaHei UI", 12))
    
    # 标题
    title_label = tk.Label(root, text="对话框功能演示", font=("Microsoft YaHei UI", 16, "bold"), pady=20, 
                          fg="white", bg="#1e1e1e")
    title_label.pack()
    
    # 创建按钮框架
    button_frame = tk.Frame(root, bg="#1e1e1e")
    button_frame.pack(pady=20, padx=50, fill="both", expand=True)
    
    # 按钮列表
    buttons = [
        ("消息框 MsgBox", lambda: MsgBox("这是一个消息框演示", "消息框")),
        ("是/否对话框 MsgBoxYesNo", lambda: z是否消息框("这是一个是/否对话框演示，是否选择是？", "确认")),
        ("输入框 InputBox", lambda: show_input_result()),
        ("选择文件 OpenFileDialog", lambda: show_file_result(OpenFileDialog("选择文件"))),
        ("选择多文件 OpenMultipleFilesDialog", lambda: show_files_result(OpenMultipleFilesDialog("选择多个文件"))),
        ("保存文件 SaveFileDialog", lambda: show_file_result(SaveFileDialog("保存文件", ".txt", [("文本文件", "*.txt")]))),
        ("选择文件夹 FolderBrowserDialog", lambda: show_file_result(FolderBrowserDialog("选择文件夹"))),
        ("中文别名测试", lambda: z确定消息框("这是使用中文别名的消息框", "中文别名测试")),
        ("退出", root.destroy)
    ]
    
    # 创建并布局按钮
    for i, (text, command) in enumerate(buttons):
        btn = tk.Button(button_frame, text=text, command=command, width=30,
                       font=("Microsoft YaHei UI", 10), bg="#2d2d2d", fg="white",
                       activebackground="#3e3e3e", activeforeground="white",
                       relief="flat", bd=1, highlightthickness=0)
        btn.pack(pady=8, ipady=5)
        # 鼠标悬停效果
        btn.bind("<Enter>", lambda e, b=btn: b.configure(bg="#3e3e3e"))
        btn.bind("<Leave>", lambda e, b=btn: b.configure(bg="#2d2d2d"))
    
    # 结果显示区域
    result_frame = tk.LabelFrame(root, text="执行结果", font=("Microsoft YaHei UI", 10), 
                                padx=10, pady=10, bg="#1e1e1e", fg="white")
    result_frame.pack(padx=50, pady=20, fill="both", expand=True)
    
    result_text = tk.Text(result_frame, height=8, font=("Microsoft YaHei UI", 9), wrap=tk.WORD,
                         bg="#2d2d2d", fg="white", insertbackground="white")
    result_text.pack(side="left", fill="both", expand=True)
    
    scrollbar = tk.Scrollbar(result_frame, orient="vertical", command=result_text.yview,
                            bg="#2d2d2d", troughcolor="#1e1e1e", activebackground="#3e3e3e")
    scrollbar.pack(side="right", fill="y")
    
    result_text.config(yscrollcommand=scrollbar.set)
    
    # 显示结果的函数
    def show_result(text):
        result_text.insert(tk.END, text + "\n")
        result_text.see(tk.END)
        result_text.update()
    
    def show_input_result():
        result = InputBox("请输入测试内容：", "输入框测试", "默认文本")
        if result is not None:
            show_result(f"输入框返回：{result}")
        else:
            show_result("输入框被取消")
    
    def show_file_result(path):
        if path:
            show_result(f"文件路径：{path}")
        else:
            show_result("文件选择被取消")
    
    def show_files_result(paths):
        if paths:
            show_result(f"选择了 {len(paths)} 个文件：")
            for path in paths:
                show_result(f"  - {path}")
        else:
            show_result("文件选择被取消")
    
    # 添加清空结果按钮
    clear_btn = tk.Button(root, text="清空结果", 
                         command=lambda: result_text.delete(1.0, tk.END),
                         font=("Microsoft YaHei UI", 10), bg="#2d2d2d", fg="white",
                         activebackground="#3e3e3e", activeforeground="white",
                         relief="flat", bd=1, highlightthickness=0)
    clear_btn.pack(pady=10)
    clear_btn.bind("<Enter>", lambda e: clear_btn.configure(bg="#3e3e3e"))
    clear_btn.bind("<Leave>", lambda e: clear_btn.configure(bg="#2d2d2d"))
    
    root.mainloop()

if __name__ == "__main__":
    # test_all_dialogs()
    窗体测试界面()
