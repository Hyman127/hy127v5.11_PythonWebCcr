
import ttkbootstrap as ttk
from ttkbootstrap.constants import *


class HY127_ScrollableFrame(ttk.Frame):
    """
    可滚动的Panel容器，类似WinForm的Panel (AutoScroll=True)
    支持内部使用pack/grid/place三种布局方式
    """
    
    def __init__(
        self,
        parent,
        width=None,
        height=None,
        autohide=True,
        shrink_inner_to_canvas=True,
        **kwargs,
    ):
        """
        参数:
            parent: 父容器
            width: 内容区域宽度（place布局时必须指定）
            height: 内容区域高度（place布局时必须指定）
            autohide: 是否自动隐藏滚动条
            shrink_inner_to_canvas: 为 True 时内部内容宽度至少与画布同宽；
                为 False 时保留内容实际请求宽度，允许按需出现横向滚动条
        """
        super().__init__(parent, **kwargs)
        
        self._content_width = width
        self._content_height = height
        self._autohide = autohide
        self._shrink_inner_to_canvas = shrink_inner_to_canvas
        
        self._setup_widgets()
        self._setup_bindins()
        
    def _setup_widgets(self):
        """创建内部组件"""
        # Canvas
        self._canvas = ttk.Canvas(self, highlightthickness=0)
        
        # 滚动条
        self._v_scrollbar = ttk.Scrollbar(
            self, 
            orient=VERTICAL, 
            command=self._canvas.yview
        )
        self._h_scrollbar = ttk.Scrollbar(
            self, 
            orient=HORIZONTAL, 
            command=self._canvas.xview
        )
        
        # 配置Canvas
        self._canvas.configure(
            yscrollcommand=self._on_v_scroll,
            xscrollcommand=self._on_h_scroll
        )
        
        # 内容Frame（用户在此添加控件）
        self.frame = ttk.Frame(self._canvas)
        
        # 将内容Frame嵌入Canvas
        self._canvas_window = self._canvas.create_window(
            (0, 0), 
            window=self.frame, 
            anchor="nw"
        )
        
        # 如果指定了固定尺寸（place布局需要）
        if self._content_width and self._content_height:
            self.set_content_size(self._content_width, self._content_height)
        
        # 布局
        self._canvas.grid(row=0, column=0, sticky=NSEW)
        self._v_scrollbar.grid(row=0, column=1, sticky=NS)
        self._h_scrollbar.grid(row=1, column=0, sticky=EW)
        
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
    def _setup_bindins(self):
        """设置事件绑定"""
        # 内容大小改变时更新（pack/grid布局自动触发）
        self.frame.bind("<Configure>", self._on_content_configure)
        
        # Canvas大小改变时
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        
        # 鼠标滚轮
        self._canvas.bind("<Enter>", self._bind_mousewheel)
        self._canvas.bind("<Leave>", self._unbind_mousewheel)
        
    def _on_content_configure(self, event):
        """内容大小改变时更新滚动区域"""
        self.refresh_scrollregion()
            
    def _on_canvas_configure(self, event):
        """Canvas大小改变时同步内容区域尺寸"""
        self.refresh_scrollregion(canvas_width=event.width, canvas_height=event.height)

    def _get_effective_content_size(self, canvas_width=0, canvas_height=0):
        """计算当前应使用的内容区尺寸。

        width/height 参数在这里作为内容区的初始/最小尺寸，而不是永远锁死。
        这样滚动面板既能保留 Place 布局需要的基准大小，也能在父窗口放大后继续弹性拉伸。
        """
        self.frame.update_idletasks()

        req_width = self.frame.winfo_reqwidth()
        req_height = self.frame.winfo_reqheight()

        base_width = self._content_width or 0
        base_height = self._content_height or 0

        if self._shrink_inner_to_canvas:
            width = max(base_width, req_width, canvas_width, 1)
        else:
            width = max(base_width, req_width, 1)
        height = max(base_height, req_height, canvas_height, 1)
        return width, height
            
    def _on_v_scroll(self, *args):
        """垂直滚动回调"""
        self._v_scrollbar.set(*args)
        if self._autohide:
            self._update_scrollbar_visibility()
            
    def _on_h_scroll(self, *args):
        """水平滚动回调"""
        self._h_scrollbar.set(*args)
        if self._autohide:
            self._update_scrollbar_visibility()
            
    def _update_scrollbar_visibility(self):
        """自动隐藏/显示滚动条"""
        # 垂直滚动条
        v_first, v_last = self._v_scrollbar.get()
        if v_first <= 0 and v_last >= 1:
            self._v_scrollbar.grid_remove()
        else:
            self._v_scrollbar.grid()
            
        # 水平滚动条
        h_first, h_last = self._h_scrollbar.get()
        if h_first <= 0 and h_last >= 1:
            self._h_scrollbar.grid_remove()
        else:
            self._h_scrollbar.grid()
            
    def _bind_mousewheel(self, event):
        """绑定鼠标滚轮"""
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self._canvas.bind_all("<Shift-MouseWheel>", self._on_shift_mousewheel)
        # Linux
        self._canvas.bind_all("<Button-4>", self._on_mousewheel_up)
        self._canvas.bind_all("<Button-5>", self._on_mousewheel_down)
        
    def _unbind_mousewheel(self, event):
        """解绑鼠标滚轮"""
        self._canvas.unbind_all("<MouseWheel>")
        self._canvas.unbind_all("<Shift-MouseWheel>")
        self._canvas.unbind_all("<Button-4>")
        self._canvas.unbind_all("<Button-5>")
        
    def _on_mousewheel(self, event):
        """垂直滚动"""
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
    def _on_shift_mousewheel(self, event):
        """Shift+滚轮水平滚动"""
        self._canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")
        
    def _on_mousewheel_up(self, event):
        """Linux向上滚动"""
        self._canvas.yview_scroll(-1, "units")
        
    def _on_mousewheel_down(self, event):
        """Linux向下滚动"""
        self._canvas.yview_scroll(1, "units")
    
    # ======================== 公开API ========================
    
    def set_content_size(self, width, height):
        """
        设置内容区域大小（place布局必须调用此方法）
        
        参数:
            width: 内容宽度
            height: 内容高度
        """
        self._content_width = width
        self._content_height = height
        self._canvas.configure(scrollregion=(0, 0, width, height))
        self._canvas.itemconfig(self._canvas_window, width=width, height=height)
        
    def update_content_size(self):
        """
        自动计算并更新内容大小（place布局添加控件后调用）
        """
        self.frame.update_idletasks()
        
        max_x, max_y = 0, 0
        
        for child in self.frame.winfo_children():
            # 获取控件边界
            x = child.winfo_x()
            y = child.winfo_y()
            
            # 优先使用实际宽度，如果未渲染则使用请求宽度
            w = child.winfo_width() if child.winfo_width() > 1 else child.winfo_reqwidth()
            h = child.winfo_height() if child.winfo_height() > 1 else child.winfo_reqheight()
            
            max_x = max(max_x, x + w)
            max_y = max(max_y, y + h)
        
        # 获取Canvas的实际可视区域大小
        canvas_width = self._canvas.winfo_width()
        canvas_height = self._canvas.winfo_height()
        
        # 只在内容超出可视区域时才添加padding
        # 横向：如果内容宽度超过canvas宽度，添加少量padding；否则使用canvas宽度
        if max_x > canvas_width:
            content_width = max_x + 5  # 只添加5像素的边距
        else:
            content_width = max(canvas_width, max_x)  # 使用canvas宽度或内容宽度的较大值
        
        # 纵向：如果内容高度超过canvas高度，添加少量padding
        if max_y > canvas_height:
            content_height = max_y + 5
        else:
            content_height = max(canvas_height, max_y)
        
        self.set_content_size(content_width, content_height)

    def refresh_scrollregion(self, canvas_width=None, canvas_height=None):
        """
        根据当前内容和画布尺寸刷新滚动区域。

        供依赖组件在批量更新内容后主动调用。
        """
        if canvas_width is None:
            canvas_width = self._canvas.winfo_width()
        if canvas_height is None:
            canvas_height = self._canvas.winfo_height()

        width, height = self._get_effective_content_size(canvas_width, canvas_height)
        self._canvas.configure(scrollregion=(0, 0, width, height))
        self._canvas.itemconfig(self._canvas_window, width=width, height=height)
        if self._autohide:
            self._update_scrollbar_visibility()
        
    def scroll_to_top(self):
        """滚动到顶部"""
        self._canvas.yview_moveto(0)
        
    def scroll_to_bottom(self):
        """滚动到底部"""
        self._canvas.yview_moveto(1)
        
    def scroll_to_widget(self, widget):
        """滚动到指定控件位置"""
        self.frame.update_idletasks()
        
        # 获取控件位置
        y = widget.winfo_y()
        content_height = self.frame.winfo_height()
        canvas_height = self._canvas.winfo_height()
        
        if content_height > canvas_height:
            fraction = y / content_height
            self._canvas.yview_moveto(fraction)


# =============================================================================
# 测试演示
# =============================================================================

class DemoApp(ttk.Window):
    def __init__(self):
        super().__init__(themename="cosmo")
        self.title("ScrollablePanel 演示 - 支持Place布局")
        self.geometry("1000x700")
        
        notebook = ttk.Notebook(self)
        notebook.pack(fill=BOTH, expand=YES, padx=5, pady=5)
        
        self.demo_pack_layout(notebook)
        self.demo_grid_layout(notebook)
        self.demo_place_layout(notebook)
        self.demo_place_auto_size(notebook)
        self.demo_dynamic_place(notebook)
        self.demo_multiple_scrollable_frames(notebook)
        
    def demo_pack_layout(self, notebook):
        """Pack布局演示"""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Pack布局")
        
        # 不指定尺寸，自动计算
        panel = HY127_ScrollableFrame(tab, autohide=True)
        panel.pack(fill=BOTH, expand=YES, padx=10, pady=10)
        
        # 提取内容frame，方便布局
        内容框架 = panel.frame
        
        ttk.Label(
            内容框架,
            text="Pack布局 - 自动计算滚动区域",
            font=("Arial", 14, "bold"),
            bootstyle="primary"
        ).pack(pady=10)
        
        for i in range(40):
            行框架 = ttk.Frame(内容框架)
            行框架.pack(fill=X, padx=10, pady=2)
            
            ttk.Label(行框架, text=f"第 {i+1} 行:", width=10).pack(side=LEFT)
            ttk.Entry(行框架, width=30).pack(side=LEFT, padx=5)
            ttk.Button(行框架, text="确定", bootstyle="success-outline").pack(side=LEFT, padx=2)
            ttk.Button(行框架, text="取消", bootstyle="danger-outline").pack(side=LEFT)
            
    def demo_grid_layout(self, notebook):
        """Grid布局演示"""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Grid布局")
        
        panel = HY127_ScrollableFrame(tab)
        panel.pack(fill=BOTH, expand=YES, padx=10, pady=10)
        
        # 提取内容frame，方便布局
        内容框架 = panel.frame
        
        ttk.Label(
            内容框架,
            text="Grid布局 - 自动计算滚动区域",
            font=("Arial", 14, "bold"),
            bootstyle="success"
        ).grid(row=0, column=0, columnspan=5, pady=10)
        
        # 表头
        headers = ["ID", "名称", "数量", "单价", "操作"]
        for col, h in enumerate(headers):
            ttk.Label(
                内容框架, 
                text=h, 
                font=("Arial", 10, "bold"),
                bootstyle="inverse-secondary"
            ).grid(row=1, column=col, padx=5, pady=5, sticky=EW)
        
        # 数据行
        for i in range(35):
            ttk.Label(内容框架, text=f"{i+1001}").grid(row=i+2, column=0, padx=5, pady=2)
            ttk.Entry(内容框架, width=15).grid(row=i+2, column=1, padx=5, pady=2)
            ttk.Spinbox(内容框架, from_=0, to=100, width=8).grid(row=i+2, column=2, padx=5, pady=2)
            ttk.Entry(内容框架, width=10).grid(row=i+2, column=3, padx=5, pady=2)
            ttk.Button(内容框架, text="删除", bootstyle="danger-outline").grid(row=i+2, column=4, padx=5, pady=2)
            
    def demo_place_layout(self, notebook):
        """Place布局演示 - 预设尺寸"""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Place布局(预设尺寸)")
        
        # Place布局：必须指定内容区域大小
        panel = HY127_ScrollableFrame(tab, width=800, height=1500)
        panel.pack(fill=BOTH, expand=YES, padx=10, pady=10)
        
        # 提取内容frame，方便布局
        内容框架 = panel.frame
        
        # 标题
        ttk.Label(
            内容框架,
            text="Place布局 - 预设内容区域尺寸",
            font=("Arial", 14, "bold"),
            bootstyle="warning"
        ).place(x=20, y=10)
        
        ttk.Label(
            内容框架,
            text="创建时指定: ScrollablePanel(parent, width=800, height=1500)",
            font=("Arial", 10),
            bootstyle="secondary"
        ).place(x=20, y=40)
        
        # 放置控件
        y_pos = 80
        for i in range(30):
            ttk.Label(
                内容框架, 
                text=f"标签 {i+1}:"
            ).place(x=20, y=y_pos, width=80, height=30)
            
            ttk.Entry(
                内容框架
            ).place(x=110, y=y_pos, width=200, height=30)
            
            ttk.Button(
                内容框架, 
                text="浏览...",
                bootstyle="warning-outline"
            ).place(x=320, y=y_pos, width=80, height=30)
            
            ttk.Progressbar(
                内容框架,
                value=(i+1)*3,
                bootstyle="warning-striped"
            ).place(x=410, y=y_pos, width=150, height=30)
            
            y_pos += 45
        
        # 底部标记
        ttk.Label(
            内容框架,
            text="✓ 已滚动到底部",
            font=("Arial", 12, "bold"),
            bootstyle="success"
        ).place(x=300, y=1420)
        
    def demo_place_auto_size(self, notebook):
        """Place布局演示 - 自动计算尺寸"""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Place布局(自动尺寸)")
        
        # 先不指定尺寸
        panel = HY127_ScrollableFrame(tab)
        
        panel.pack(fill=BOTH, expand=YES, padx=10, pady=10)
        # 提取内容frame，方便布局
        内容框架 = panel.frame
        
        # 标题
        ttk.Label(
            内容框架,
            text="Place布局 - 自动计算内容区域尺寸",
            font=("Arial", 14, "bold"),
            bootstyle="info"
        ).place(x=20, y=10)
        
        ttk.Label(
            内容框架,
            text="添加控件后调用: panel.update_content_size()",
            font=("Arial", 10),
            bootstyle="secondary"
        ).place(x=20, y=40)
        
        # 放置控件
        y_pos = 80
        for i in range(25):
            x_offset = (i % 2) * 350  # 两列布局
            
            ttk.Label(
                内容框架, 
                text=f"字段 {i+1}:"
            ).place(x=20 + x_offset, y=y_pos, width=80, height=30)
            
            ttk.Entry(
                内容框架
            ).place(x=100 + x_offset, y=y_pos, width=180, height=30)
            
            ttk.Button(
                内容框架, 
                text="...",
                bootstyle="info-outline"
            ).place(x=285 + x_offset, y=y_pos, width=40, height=30)
            
            if i % 2 == 1:
                y_pos += 45
        
        # 添加完控件后，自动计算尺寸
        panel.after(100, panel.update_content_size)
        
    def demo_dynamic_place(self, notebook):
        """动态添加Place控件演示"""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="动态Place")
        
        # 控制面板
        control_frame = ttk.Frame(tab)
        control_frame.pack(fill=X, padx=10, pady=5)
        
        panel = HY127_ScrollableFrame(tab, width=800, height=400)
        panel.pack(fill=BOTH, expand=YES, padx=10, pady=10)
        
        # 提取内容frame，方便布局
        内容框架 = panel.frame
        
        # 状态变量
        state = {"count": 0, "y": 10}
        
        def add_widget():
            state["count"] += 1
            
            # 创建一行控件
            ttk.Label(
                内容框架,
                text=f"动态控件 {state['count']}:"
            ).place(x=20, y=state["y"], width=120, height=30)
            
            ttk.Entry(
                内容框架
            ).place(x=150, y=state["y"], width=200, height=30)
            
            ttk.Button(
                内容框架,
                text="删除",
                bootstyle="danger-outline"
            ).place(x=360, y=state["y"], width=60, height=30)
            
            state["y"] += 40
            
            # 更新滚动区域
            new_height = state["y"] + 50
            if new_height > 400:
                panel.set_content_size(800, new_height)
                
            count_label.configure(text=f"已添加: {state['count']} 个控件")
            
        def add_many():
            for _ in range(10):
                add_widget()
        
        def clear_all():
            for child in 内容框架.winfo_children():
                child.destroy()
            state["count"] = 0
            state["y"] = 10
            panel.set_content_size(800, 400)
            count_label.configure(text="已清空")
        
        ttk.Button(
            control_frame, 
            text="添加一个", 
            command=add_widget,
            bootstyle="success"
        ).pack(side=LEFT, padx=5)
        
        ttk.Button(
            control_frame, 
            text="添加十个", 
            command=add_many,
            bootstyle="info"
        ).pack(side=LEFT, padx=5)
        
        ttk.Button(
            control_frame, 
            text="清空全部", 
            command=clear_all,
            bootstyle="danger"
        ).pack(side=LEFT, padx=5)
        
        ttk.Button(
            control_frame,
            text="滚动到顶部",
            command=panel.scroll_to_top,
            bootstyle="secondary-outline"
        ).pack(side=LEFT, padx=5)
        
        ttk.Button(
            control_frame,
            text="滚动到底部",
            command=panel.scroll_to_bottom,
            bootstyle="secondary-outline"
        ).pack(side=LEFT, padx=5)
        
        count_label = ttk.Label(
            control_frame,
            text="点击按钮添加控件",
            font=("Arial", 10)
        )
        count_label.pack(side=LEFT, padx=20)
        
    def demo_multiple_scrollable_frames(self, notebook):
        """多个带边框的滚动框架演示"""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="多滚动框架")
        
        主框架 = ttk.Frame(tab)
        主框架.pack(fill=BOTH, expand=YES, padx=10, pady=10)
        
        ttk.Label(
            主框架,
            text="多个带边框的滚动框架",
            font=("Arial", 14, "bold"),
            bootstyle="primary"
        ).pack(pady=(0, 10))
        
        左右分割框架 = ttk.Panedwindow(主框架, orient=HORIZONTAL)
        左右分割框架.pack(fill=BOTH, expand=YES)
        
        左侧面板 = ttk.Frame(左右分割框架)
        右侧面板 = ttk.Frame(左右分割框架)
        
        左右分割框架.add(左侧面板, weight=1)
        左右分割框架.add(右侧面板, weight=1)
        
        左侧标签框架 = ttk.Labelframe(
            左侧面板,
            text="左侧滚动区域",
            bootstyle="info"
        )
        左侧标签框架.pack(fill=BOTH, expand=YES, padx=5, pady=5)
        
        左侧滚动框架 = HY127_ScrollableFrame(左侧标签框架, autohide=True)
        左侧滚动框架.pack(fill=BOTH, expand=YES, padx=5, pady=5)
        
        左侧内容框架 = 左侧滚动框架.frame
        
        for i in range(30):
            行框架 = ttk.Frame(左侧内容框架)
            行框架.pack(fill=X, padx=5, pady=3)
            
            ttk.Label(行框架, text=f"项目 {i+1}:", width=12, bootstyle="inverse-info").pack(side=LEFT)
            ttk.Entry(行框架, width=25).pack(side=LEFT, padx=5)
            ttk.Button(行框架, text="编辑", bootstyle="info-outline").pack(side=LEFT, padx=2)
            ttk.Button(行框架, text="删除", bootstyle="danger-outline").pack(side=LEFT)
        
        右侧标签框架 = ttk.Frame(
            右侧面板,
        )
        右侧标签框架.pack(fill=BOTH, expand=YES, padx=5, pady=5)
        
        右侧滚动框架 = HY127_ScrollableFrame(右侧标签框架, borderwidth=1, relief="solid")
        右侧滚动框架.pack(fill=BOTH, expand=YES, padx=5, pady=5)
        
       #右侧滚动框架 添加边框
        
        右侧内容框架 = 右侧滚动框架.frame
        
        ttk.Label(
            右侧内容框架,
            text="详细信息列表",
            font=("Arial", 12, "bold"),
            bootstyle="warning"
        ).pack(pady=10)
        
        for i in range(25):
            信息框架 = ttk.Frame(右侧内容框架, bootstyle="warning")
            信息框架.pack(fill=X, padx=5, pady=5)
            
            ttk.Label(
                信息框架,
                text=f"记录 #{i+1001}",
                font=("Arial", 10, "bold")
            ).pack(anchor=W, padx=5, pady=(5, 2))
            
            ttk.Label(
                信息框架,
                text=f"这是第 {i+1} 条记录的详细描述信息，可以包含多行文本内容。",
                wraplength=280
            ).pack(anchor=W, padx=5, pady=(0, 5))
            
            ttk.Progressbar(
                信息框架,
                value=(i+1) * 4,
                bootstyle="warning-striped"
            ).pack(fill=X, padx=5, pady=(0, 5))


if __name__ == "__main__":
    app = DemoApp()
    app.mainloop()
