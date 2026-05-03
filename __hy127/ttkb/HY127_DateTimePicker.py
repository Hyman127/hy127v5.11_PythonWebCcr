
"""  
汉化的日期选择器和自定义DateEntry控件 - 支持高DPI  
支持中文月份、星期显示，并可自由设置宽度和高度  
【优化版本】- 延迟加载面板，大幅提升加载速度
"""  
import calendar  
import datetime  
import sys
from sys import maxsize
from tkinter import StringVar, Toplevel, Frame, Label, Button, Canvas as tkCanvas  
import ttkbootstrap as ttk  
from ttkbootstrap.utility import enable_high_dpi_awareness, scale_size  
from ttkbootstrap.constants import *  

try:
    if sys.platform.startswith('win'):
        import ctypes
        from ctypes import wintypes
    else:
        ctypes = None
        wintypes = None
except ImportError:
    ctypes = None
    wintypes = None


_MonitorFromPoint = None
_GetMonitorInfoW = None

if ctypes and wintypes:
    class _POINT(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

    class _RECT(ctypes.Structure):
        _fields_ = [
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        ]

    class _MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", _RECT),
            ("rcWork", _RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    try:
        _user32 = ctypes.windll.user32
        _MonitorFromPoint = _user32.MonitorFromPoint
        _MonitorFromPoint.argtypes = [_POINT, wintypes.DWORD]
        _MonitorFromPoint.restype = wintypes.HANDLE
        _GetMonitorInfoW = _user32.GetMonitorInfoW
        _GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_MONITORINFO)]
        _GetMonitorInfoW.restype = wintypes.BOOL
    except Exception:
        _MonitorFromPoint = None
        _GetMonitorInfoW = None


def get_monitor_work_area(widget, x=None, y=None):
    """获取坐标所在显示器的可用工作区。"""
    if widget is not None:
        widget.update_idletasks()
        if x is None:
            x = widget.winfo_pointerx()
        if y is None:
            y = widget.winfo_pointery()

    if _MonitorFromPoint and _GetMonitorInfoW and x is not None and y is not None:
        try:
            monitor = _MonitorFromPoint(_POINT(int(x), int(y)), 2)
            if monitor:
                info = _MONITORINFO()
                info.cbSize = ctypes.sizeof(_MONITORINFO)
                if _GetMonitorInfoW(monitor, ctypes.byref(info)):
                    work = info.rcWork
                    return work.left, work.top, work.right, work.bottom
        except Exception:
            pass

    left = widget.winfo_vrootx() if widget is not None else 0
    top = widget.winfo_vrooty() if widget is not None else 0
    width = widget.winfo_vrootwidth() if widget is not None else 0
    height = widget.winfo_vrootheight() if widget is not None else 0

    if width <= 0 and widget is not None:
        width = widget.winfo_screenwidth()
    if height <= 0 and widget is not None:
        height = widget.winfo_screenheight()

    return left, top, left + width, top + height


def adjust_popup_position_to_screen(
    widget,
    desired_x,
    desired_y,
    popup_width,
    popup_height,
    anchor_x=None,
    anchor_y=None,
    anchor_width=0,
    anchor_height=0,
    padding=4,
):
    """根据当前显示器工作区调整弹窗位置，避免超出边界。"""
    probe_x = desired_x
    probe_y = desired_y
    if anchor_x is not None:
        probe_x = anchor_x + max(anchor_width // 2, 0)
    if anchor_y is not None:
        probe_y = anchor_y + max(anchor_height // 2, 0)

    left, top, right, bottom = get_monitor_work_area(widget, probe_x, probe_y)

    max_x = max(left + padding, right - padding - popup_width)
    max_y = max(top + padding, bottom - padding - popup_height)

    x = desired_x
    if x + popup_width > right - padding and anchor_x is not None:
        x = anchor_x + anchor_width - popup_width
    x = min(max(x, left + padding), max_x)

    y = desired_y
    if y + popup_height > bottom - padding and anchor_y is not None:
        # 下方避让时额外上提一个锚点高度，避免遮挡输入框
        y = anchor_y - popup_height - max(anchor_height, 0) - 1
    y = min(max(y, top + padding), max_y)

    return int(x), int(y)


class HY127_DatePickerDialog(Toplevel):  
    """完全汉化的日期选择器对话框 - 支持高DPI，支持年月分离选择【优化版】"""  
    # 语言配置
    LANGUAGE_CONFIG = {
        'zh': {
            'month_names': ['1月', '2月', '3月', '4月', '5月', '6月',   
                           '7月', '8月', '9月', '10月', '11月', '12月'],
            'day_abbr': ['一', '二', '三', '四', '五', '六', '日'],
            'year_suffix': '年',
            'today': '今天',
            'now': '现在',
            'cancel': '取消',
            'confirm': '确定',
            'time_period': '时间段',
            'hour': '时',
            'minute': '分',
            'second': '秒',
            'title': '选择日期时间',
        },
        'en': {
            'month_names': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                           'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
            'day_abbr': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
            'year_suffix': '',
            'today': 'Today',
            'now': 'Now',
            'cancel': 'Cancel',
            'confirm': 'OK',
            'time_period': 'Period',
            'hour': 'Hr',
            'minute': 'Min',
            'second': 'Sec',
            'title': 'Select Date Time',
        }
    }
    
    # 面板类型
    PANEL_YEAR = 'year'
    PANEL_MONTH = 'month'
    PANEL_DAY = 'day'
    PANEL_TIME = 'time'
    
    def __init__(self, parent=None, title="选择日期", firstweekday=0,   
                 startdate=None, bootstyle="success", position=None, anchor_rect=None,
                 date_selected_callback=None, starttime=None,
                 initial_panel=None, language='zh'):  
        """  
        初始化汉化的日期选择器  
        参数:  
            parent: 父窗口  
            title: 对话框标题  
            firstweekday: 每周第一天 (0=周一, 6=周日)  
            startdate: 起始日期  
            bootstyle: 主题样式  
            position: 弹出位置 (x, y) 元组
            anchor_rect: 触发控件区域 (x, y, width, height)
            date_selected_callback: 日期选择回调函数  
            starttime: 起始时间
            initial_panel: 启动时显示的面板 ('day', 'time', 'year', 'month')
            language: 语言 ('zh' 中文, 'en' 英文)
        """  
        enable_high_dpi_awareness()  
        super().__init__(parent)  
        
        # 设置语言
        self._language = language if language in self.LANGUAGE_CONFIG else 'zh'
        self._lang_config = self.LANGUAGE_CONFIG[self._language]
        
        # 使用语言配置中的标题
        if title == "选择日期":
            title = self._lang_config['title']
        
        self.title(title)  
        
        # 【优化1】预计算所有缩放尺寸，避免重复调用 scale_size()
        self._scaled_sizes = {
            'padding': scale_size(self, 5),
            'font_nav': min(scale_size(self, 12), 12),
            'font_year_month': min(scale_size(self, 10), 11),
            'font_year': min(scale_size(self, 12), 12),
            'font_month': min(scale_size(self, 12), 12),
            'font_weekday': min(scale_size(self, 9), 12),
            'font_time': min(scale_size(self, 10), 12),
            'font_time_title': min(scale_size(self, 10), 11),
            'font_time_period': min(scale_size(self, 9), 10),
            'time_item_height': scale_size(self, 25),
            'btn_padding': scale_size(self, 2),
            'day_padding': scale_size(self, 0),
            'nav_padding': scale_size(self, -2),
            'canvas_width': scale_size(self, 70),
        }
          
        self._scaled_width = scale_size(self, 242)  
        self._scaled_height = scale_size(self, 245)  
        self.geometry(f"{self._scaled_width}x{self._scaled_height}")  
        self.withdraw()    
        self.transient(parent)  
        self.resizable(False, False)  
        self._bootstyle = bootstyle  
        self._firstweekday = firstweekday  
        
        # 确定初始面板（必须在使用前设置）
        self._initial_panel = initial_panel or self.PANEL_DAY
        
        # 根据初始面板类型初始化日期和时间
        # 如果是时间模式，优先使用 starttime，否则使用默认值
        if self._initial_panel == self.PANEL_TIME:
            # 时间模式：也需要初始化 startdate
            self._startdate = startdate or datetime.date.today()
            # 然后处理 starttime
            if starttime is not None:
                self._starttime = starttime
            elif startdate is not None:
                # startdate 可能是 date 或 datetime，从 datetime 获取时间
                if hasattr(startdate, 'hour'):
                    self._starttime = startdate.time()
                else:
                    self._starttime = datetime.time(0, 0, 0)
            else:
                self._starttime = datetime.time(0, 0, 0)
        else:
            # 非时间模式：使用 startdate 和当前时间
            self._startdate = startdate or datetime.date.today()  
            self._starttime = starttime or datetime.datetime.now().time()  
        
        self._current_year = self._startdate.year if hasattr(self._startdate, 'year') else self._startdate.year
        self._current_month = self._startdate.month if hasattr(self._startdate, 'month') else self._startdate.month
        self._current_date = self._startdate
        self._selected_date = None  
        self._selected_time = self._starttime  
        self.date_selected = None  
        self._date_selected_callback = date_selected_callback  
        self._year_range_start = self._current_year - 6
        self._anchor_rect = anchor_rect
        
        # 【优化2】面板延迟加载标志 - 只在需要时才创建
        self._year_panel_created = False
        self._month_panel_created = False
        self._day_panel_created = False
        self._time_panel_created = False
        
        # 【优化3】缓存背景颜色，只获取一次
        self._bg_color = None
        
        # 面板引用占位
        self.day_panel = None
        self.year_panel = None
        self.month_panel = None
        self.time_panel = None
        self.day_buttons = []
        self.year_buttons = []
        self.month_buttons = []
        self.hour_buttons = []
        self.minute_buttons = []
        self.second_buttons = []
        
        # 确定初始面板
        self._initial_panel = initial_panel or self.PANEL_DAY
        self._current_panel = self._initial_panel
          
        # 创建UI（只创建框架和头部）
        self._create_widgets()  
          
        # 设置位置（使用已知的缩放尺寸，立即定位）
        if position:
            anchor_x = anchor_y = None
            anchor_width = anchor_height = 0
            if anchor_rect:
                anchor_x, anchor_y, anchor_width, anchor_height = anchor_rect
            x, y = adjust_popup_position_to_screen(
                self,
                position[0],
                position[1],
                self._scaled_width,
                self._scaled_height,
                anchor_x=anchor_x,
                anchor_y=anchor_y,
                anchor_width=anchor_width,
                anchor_height=anchor_height,
            )
            self.geometry(f"{self._scaled_width}x{self._scaled_height}+{x}+{y}")
        else:
            self._center_window()
        
        # 【优化4】使用 after_idle 延迟完成初始化，避免阻塞
        self.after_idle(self._finalize_init)
        
        self.bind('<Escape>', lambda e: self._cancel())
        self.wait_window()
    
    def _finalize_init(self):
        """【优化】延迟完成初始化 - 避免阻塞主线程"""
        self.update_idletasks()
        self.deiconify()
        self.grab_set()
      
    def _create_widgets(self):
        """创建控件 - 【优化】使用层叠展示，所有面板预先布局在同一位置"""
        style = ttk.Style()
        style.configure(
            'NavButton.TButton',
            font=('Arial', self._scaled_sizes['font_nav'], 'bold'),
            padding=(0, 0)
        )
        
        # 主容器
        self.main_container = ttk.Frame(self, padding=self._scaled_sizes['padding'])
        self.main_container.pack(fill=BOTH, expand=YES)
        
        # 头部和底部是固定的
        self._create_header()
        self._create_footer_buttons()
        
        # 中间面板区域：所有的面板都会 place 在同一个位置
        self.content_area = ttk.Frame(self.main_container)
        self.content_area.place(relx=0, rely=0.1111, relwidth=1.0, relheight=0.7778)
        
        # 初始加载
        self._switch_panel(self._initial_panel)
    
    def _create_header(self):
        """创建头部导航控件"""
        font_nav = self._scaled_sizes['font_nav']
        font_ym = self._scaled_sizes['font_year_month']
        nav_padding = self._scaled_sizes['nav_padding']
        
        # 容器
        header = ttk.Frame(self.main_container)
        header.place(relx=0, rely=0, relwidth=1.0, relheight=0.1111)
        
        # 上个月/年标签
        self.lbl上个月 = ttk.Label(
            header,
            text="◀",
            anchor="center",
            font=("微软雅黑", font_nav),
            justify="center",
            bootstyle="secondary",
            padding=(0, nav_padding, 0, 0)
        )
        self.lbl上个月.place(relx=0.0, rely=0.0, relwidth=0.08, relheight=1.0)
        self.lbl上个月.bind("<Button-1>", lambda e: self._prev())
        self.lbl上个月.config(cursor="hand2")
        
        # 年份显示
        self.lbl年份 = ttk.Label(
            header,
            text=f"{self._current_year}{self._lang_config['year_suffix']}",
            anchor="center",
            font=("微软雅黑", font_ym, "bold"),
            justify="center",
            bootstyle=self._bootstyle,
        )
        self.lbl年份.place(relx=0.08, rely=0.0, relwidth=0.24, relheight=1.0)
        self.lbl年份.bind("<Button-1>", self._on_year_label_click)
        self.lbl年份.config(cursor="hand2")
        
        # 月份显示
        self.lbl月份 = ttk.Label(
            header,
            text=self._lang_config['month_names'][self._current_month - 1],
            anchor="center",
            font=("微软雅黑", font_ym, "bold"),
            justify="center",
            bootstyle=self._bootstyle,
        )
        self.lbl月份.place(relx=0.31, rely=0.0, relwidth=0.16, relheight=1.0)
        self.lbl月份.bind("<Button-1>", self._on_month_label_click)
        self.lbl月份.config(cursor="hand2")
        
        # 日期显示
        self.lbl日期 = ttk.Label(
            header,
            text=self._get_day_text(),
            anchor="center",
            font=("微软雅黑", font_ym, "bold"),
            justify="center",
            bootstyle=self._bootstyle,
        )
        self.lbl日期.place(relx=0.45, rely=0.0, relwidth=0.16, relheight=1.0)
        self.lbl日期.bind("<Button-1>", self._on_day_label_click)
        self.lbl日期.config(cursor="hand2")
        
        # 时间显示
        self.lbl时间 = ttk.Label(
            header,
            text=self._get_time_text(),
            anchor="w",
            font=("微软雅黑", font_ym, "bold"),
            justify="left",
            bootstyle=self._bootstyle,
        )
        self.lbl时间.place(relx=0.63, rely=0.0, relwidth=0.32, relheight=1.0)
        self.lbl时间.bind("<Button-1>", self._on_time_label_click)
        self.lbl时间.config(cursor="hand2")
        
        # 下个月/年标签
        self.下个月 = ttk.Label(
            header,
            bootstyle="secondary",
            text="▶",
            anchor="w",
            font=("微软雅黑", font_nav),
            justify="left",
            padding=(0, nav_padding, 0, 0)
        )
        self.下个月.place(relx=0.93, rely=0.0, relwidth=0.10, relheight=1.0)
        self.下个月.bind("<Button-1>", lambda e: self._next())
        self.下个月.config(cursor="hand2")
    
    def _create_footer_buttons(self):
        """创建底部按钮"""
        btn_padding = self._scaled_sizes['btn_padding']
        
        f = ttk.Frame(self.main_container)
        f.place(relx=0, rely=0.8889, relwidth=1.0, relheight=0.1111)
        
        self.btn今天 = ttk.Button(
            f,
            text=self._lang_config['today'],
            padding=btn_padding,
            command=self._select_today,
            bootstyle=f"{self._bootstyle}-outline" # bootstyle=f"{self._bootstyle}-outline"
        )
        self.btn今天.place(relx=0, relwidth=0.3)
        # 添加右键事件，只更新显示而不确认选择
        self.btn今天.bind("<Button-3>", self._update_to_today_without_confirm)
        
        self.btn现在 = ttk.Button(
            f,
            text=self._lang_config['now'],
            padding=btn_padding,
            command=self._select_now,
            bootstyle="secondary-outline"
        )
        self.btn现在.place(relx=0.35, relwidth=0.3)
        # 添加右键事件，只更新显示而不确认选择
        self.btn现在.bind("<Button-3>", self._update_to_now_without_confirm)
        
        self.btn取消 = ttk.Button(
            f,
            text=self._lang_config['cancel'],
            padding=btn_padding,
            command=self._cancel,
            bootstyle="secondary-outline"
        )
        self.btn取消.place(relx=0.7, relwidth=0.3)
    
    def _create_year_panel(self):
        """【延迟加载】创建年选择面板 - 使用层叠展示"""
        if self._year_panel_created:
            return
        
        self.year_panel = ttk.Frame(self.content_area)
        self.year_panel.place(relx=0, rely=0, relwidth=1.0, relheight=1.0)
        self.year_buttons = []
        font_size = self._scaled_sizes['font_year']
        
        for i in range(12):
            year = self._year_range_start + i
            btn = ttk.Label(
                self.year_panel,
                text=str(year),
                bootstyle="secondary",
                font=("微软雅黑", font_size, "bold"),
                anchor="center",
                justify="center"
            )
            row, col = i // 3, i % 3
            btn.place(relx=col * 0.3333, rely=row * 0.25, relwidth=0.3333, relheight=0.25, x=3, y=3, width=-6, height=-6)
            btn.bind("<Button-1>", lambda e, y=year: self._on_year_click(y))
            btn.bind("<Enter>", lambda e, b=btn: b.configure(bootstyle="primary"))
            btn.bind("<Leave>", lambda e, b=btn: b.configure(bootstyle="secondary"))
            btn.config(cursor="hand2")
            self.year_buttons.append(btn)
        
        self._year_panel_created = True
    
    def _create_month_panel(self):
        """【延迟加载】创建月选择面板 - 使用层叠展示"""
        if self._month_panel_created:
            return
        
        self.month_panel = ttk.Frame(self.content_area)
        self.month_panel.place(relx=0, rely=0, relwidth=1.0, relheight=1.0)
        self.month_buttons = []
        font_size = self._scaled_sizes['font_month']
        
        for i in range(12):
            month = i + 1
            btn = ttk.Label(
                self.month_panel,
                text=str(month),
                bootstyle="secondary",
                font=("微软雅黑", font_size, "bold"),
                anchor="center",
                justify="center"
            )
            row, col = i // 3, i % 3
            btn.place(relx=col * 0.3333, rely=row * 0.25, relwidth=0.3333, relheight=0.25, x=3, y=3, width=-6, height=-6)
            btn.bind("<Button-1>", lambda e, m=month: self._on_month_click(m))
            btn.bind("<Enter>", lambda e, b=btn: b.configure(bootstyle="primary"))
            btn.bind("<Leave>", lambda e, b=btn: b.configure(bootstyle="secondary"))
            btn.config(cursor="hand2")
            self.month_buttons.append(btn)
        
        self._month_panel_created = True
    
    def _create_day_panel(self):
        """【延迟加载】创建日选择面板 - 使用层叠展示"""
        if self._day_panel_created:
            return
        
        self.day_panel = ttk.Frame(self.content_area)
        self.day_panel.place(relx=0, rely=0, relwidth=1.0, relheight=1.0)
        
        # 创建星期标题
        self._create_weekday_headers()
        
        # 创建日历网格
        self.day_buttons = []
        self._create_calendar_grid()
        
        self._day_panel_created = True
    
    def _create_weekday_headers(self):
        """创建星期标题行"""
        days = self._lang_config['day_abbr'][self._firstweekday:] + self._lang_config['day_abbr'][:self._firstweekday]
        weekday_labels = ['lbl一', 'lbl二', 'lbl三', 'lbl四', 'lbl五', 'lbl六', 'lbl日']
        font_size = self._scaled_sizes['font_weekday']
        
        for day_idx, day_name in enumerate(days):
            label_name = weekday_labels[day_idx]
            lbl = ttk.Label(
                self.day_panel, text=day_name, anchor="center",
                font=("微软雅黑", font_size), justify="center", bootstyle="secondary"
            )
            setattr(self, label_name, lbl)
            lbl.place(relx=day_idx * 0.1429, rely=0, relwidth=0.1429, relheight=0.125)
    
    def _create_calendar_grid(self):
        """创建日历网格"""
        day_padding = self._scaled_sizes['day_padding']
        
        for week in range(6):
            week_buttons = []
            for day in range(7):
                btn = ttk.Button(self.day_panel, text="", padding=day_padding)
                rely = 0.125 + week * 0.145
                relx = day * 0.1429
                btn.place(relx=relx, rely=rely, relwidth=0.1429, relheight=0.145)
                btn.configure(command=lambda w=week, d=day: self._on_day_click(w, d))
                btn._week, btn._day = week, day
                btn._is_today, btn._is_enabled, btn._day_number = False, True, 0
                week_buttons.append(btn)
            self.day_buttons.append(week_buttons)
        
        self._update_calendar()
    
    def _create_time_panel(self):
        """【延迟加载】创建时间选择面板 - 使用层叠展示"""
        if self._time_panel_created:
            return
        
        self.time_panel = ttk.Frame(self.content_area)
        self.time_panel.place(relx=0, rely=0, relwidth=1.0, relheight=1.0)
        self._create_time_columns()
        self._time_panel_created = True
    
    def _create_time_columns(self):
        """创建时间选择列 - 使用Canvas绘制文本"""
        self.hour_buttons = []
        self.minute_buttons = []
        self.second_buttons = []
        
        time_config = [
            (self._lang_config['hour'], self.hour_buttons, 24, 'hour'),
            (self._lang_config['minute'], self.minute_buttons, 60, 'minute'),
            (self._lang_config['second'], self.second_buttons, 60, 'second')
        ]
        
        font_time = self._scaled_sizes['font_time']
        font_title = self._scaled_sizes['font_time_title']
        canvas_width = self._scaled_sizes['canvas_width']
        
        for col_idx, (label_text, button_list, item_count, time_type) in enumerate(time_config):
            col_frame = ttk.Frame(self.time_panel)
            col_frame.place(relx=col_idx * 0.25, rely=0.0, relwidth=0.25, relheight=1.0, x=2, y=2, width=-4, height=-4)
            
            # 列标题
            lbl_title = ttk.Label(
                col_frame, text=label_text, anchor="w",padding=(15, 0, 0, 0),
                font=("微软雅黑", font_title), bootstyle="secondary"
            )
            lbl_title.pack(fill=X, pady=(0, 2))
            
            # Canvas
            canvas = tkCanvas(col_frame, bg=self._get_bg_color(), highlightthickness=0, width=canvas_width)
            canvas.pack(fill=BOTH, expand=YES, side=LEFT)
            
            # Scrollbar
            scrollbar = ttk.Scrollbar(col_frame, orient=VERTICAL, command=canvas.yview)
            scrollbar.pack(fill=Y, side=RIGHT)
            canvas.configure(yscrollcommand=self._create_scroll_handler(scrollbar, canvas))
            
            # 存储canvas引用
            setattr(self, f'{time_type}_canvas', canvas)
            
            # 计算每个项目的高度 - 使用自动缩放的行高
            item_height = self._scaled_sizes['time_item_height']
            total_height = item_count * item_height
            
            # 配置滚动区域
            canvas.configure(scrollregion=(0, 0, canvas_width, total_height))
            
            # 当Canvas尺寸改变时更新滚动区域
            def on_canvas_resize(event, cv=canvas, cnt=item_count, h=item_height):
                new_total_height = cnt * h  # 使用缩放后的行高
                cv.configure(scrollregion=(0, 0, cv.winfo_width(), new_total_height))
            
            # 绘制时间选项
            self._draw_time_options(canvas, item_count, item_height, time_type)
            
            # 绑定点击事件
            canvas.bind("<Button-1>", lambda e, c=canvas, t=time_type: self._on_canvas_time_click(e, c, t))
            canvas.bind("<MouseWheel>", lambda e, c=canvas: self._on_mouse_wheel(e, c))
            
            # 鼠标悬停事件
            canvas.bind("<Motion>", lambda e, c=canvas, tt=time_type: self._on_canvas_hover(e, c, tt))
            canvas.bind("<Leave>", lambda e, c=canvas: self._on_canvas_leave(e, c))
            
            # 当Canvas尺寸改变时重绘
            def on_canvas_resize(event, cv=canvas, cnt=item_count, h=item_height, tt=time_type):
                cv.delete("time_item")
                self._draw_time_options(cv, cnt, h, tt)
            
            canvas.bind("<Configure>", on_canvas_resize)
            
            # 存储canvas相关信息
            canvas.item_data = {'item_count': item_count, 'item_height': item_height, 'time_type': time_type, 'hover_item': None}
        
        # 创建时间段快速选择按钮列
        self._create_time_period_buttons()
        
        self._time_panel_created = True
    
    def _draw_time_options(self, canvas, item_count, item_height, time_type):
        """绘制时间选项到Canvas"""
        selected_value = getattr(self._selected_time, time_type)
        
        for i in range(item_count):
            y = i * item_height + item_height // 2  # 居中位置
            text = str(i).zfill(2)
            
            # 获取ttkbootstrap样式的颜色
            if i == selected_value:
                # 选中状态使用bootstyle
                bg_color = self._get_bootstyle_color(self._bootstyle)
                #fg_color = "white"
                fg_color = self._get_bootstyle_color(self._bootstyle)
            else:
                # 未选中状态使用secondary样式 - 使用更精确的颜色
                bg_color = "#e9ecef"  # secondary背景色
                fg_color = "#495057"  # secondary前景色，稍微深一点
                
            # 绘制文本（无背景色）
            text_id = canvas.create_text(
                canvas.winfo_width()//2, y, text=text, fill=fg_color, 
                font=("Arial", self._scaled_sizes['font_time'], "bold"),
                tags=f"time_{time_type}_{i}"
            )
            
            # 存储数据
            canvas.addtag_withtag(f"time_item", f"time_{time_type}_{i}")
    
    def _get_bootstyle_color(self, bootstyle):
        """获取bootstyle对应的颜色 - 尝试从ttkbootstrap样式中获取，否则使用默认值"""
        try:
            # 尝试从ttkbootstrap样式系统获取实际颜色
            style = ttk.Style()
            color = style.colors.get(bootstyle, None)
            if color:
                return color
        except Exception:
            pass
        
        # 默认颜色映射
        color_map = {
            'primary': '#0d6efd',
            'secondary': '#6c757d',
            'success': '#198754',
            'info': '#0dcaf0',
            'warning': '#ffc107',
            'danger': '#dc3545',
            'light': '#f8f9fa',
            'dark': '#212529'
        }
        return color_map.get(bootstyle, '#0d6efd')  # 默认primary颜色
    
    def _refresh_time_display(self):
        """刷新时间显示"""
        item_height = self._scaled_sizes['time_item_height']
        for time_type in ['hour', 'minute', 'second']:
            canvas = getattr(self, f'{time_type}_canvas', None)
            if canvas:
                canvas.delete("time_item")
                item_count = 24 if time_type == 'hour' else 60
                self._draw_time_options(canvas, item_count, item_height, time_type)
    
    def _create_time_period_buttons(self):
        """创建时间段快速选择标签列"""
        period_frame = ttk.Frame(self.time_panel)
        period_frame.place(relx=0.75, rely=0.0, relwidth=0.25, relheight=1.0, x=2, y=2, width=-4, height=-4)
        
        # 标题
        lbl_title = ttk.Label(
            period_frame, text=self._lang_config['time_period'], anchor="center",
            font=("微软雅黑", self._scaled_sizes['font_time_title']), bootstyle="secondary"
        )
        lbl_title.pack(fill=X, pady=(0, 3))
        
        # 时间段配置
        if self._language == 'zh':
            periods = [
                ('凌晨 03', self._select_early_morning),
                ('上午 08', self._select_morning),
                ('下午 14', self._select_afternoon),
                ('晚上 20', self._select_evening),
            ]
        else:
            periods = [
                ('EAL 03', self._select_early_morning),
                ('AM 08', self._select_morning),
                ('PM 14', self._select_afternoon),
                ('EVE 20', self._select_evening),
            ]
        
        for text, callback in periods:
            lbl = ttk.Label(
                period_frame, text=text, anchor="center",
                font=("微软雅黑", self._scaled_sizes['font_time_period']),
                bootstyle="secondary"
            )
            lbl.pack(fill=X, padx=3, pady=4)
            lbl.config(cursor="hand2")
            lbl.bind("<Button-1>", lambda e, cb=callback: cb())
            lbl.bind("<Enter>", lambda e, l=lbl: l.configure(bootstyle="primary"))
            lbl.bind("<Leave>", lambda e, l=lbl: l.configure(bootstyle="secondary"))
        
        # 确定按钮
        btn_padding = self._scaled_sizes['btn_padding']
        btn确定 = ttk.Button(
            period_frame, text=self._lang_config['confirm'], command=self._confirm_selection,
            bootstyle=f"{self._bootstyle}-outline", width=8, padding=btn_padding
        )
        btn确定.pack(fill=X, padx=3, pady=(8, 3))
        btn确定.config(cursor="hand2")
    
    def _select_early_morning(self):
        """选择凌晨时间 00:00-05:59"""
        self._selected_time = datetime.time(3, 0, 0)
        self.lbl时间.configure(text=self._get_time_text())
        self._update_time_panel()
    
    def _select_morning(self):
        """选择上午时间 06:00-11:59"""
        self._selected_time = datetime.time(8, 0, 0)
        self.lbl时间.configure(text=self._get_time_text())
        self._update_time_panel()
    
    def _select_afternoon(self):
        """选择下午时间 12:00-17:59"""
        self._selected_time = datetime.time(14, 0, 0)
        self.lbl时间.configure(text=self._get_time_text())
        self._update_time_panel()
    
    def _select_evening(self):
        """选择晚上时间 18:00-23:59"""
        self._selected_time = datetime.time(20, 0, 0)
        self.lbl时间.configure(text=self._get_time_text())
        self._update_time_panel()
    
    def _get_bg_color(self):
        """获取背景颜色 - 【优化】缓存结果"""
        if self._bg_color is None:
            try:
                style = ttk.Style()
                self._bg_color = style.lookup('TFrame', 'background') or '#F0F0F0'
            except Exception:
                self._bg_color = '#F0F0F0'
        return self._bg_color
    
    def _create_scroll_handler(self, scrollbar, canvas):
        """创建滚动条处理函数"""
        item_height = self._scaled_sizes['time_item_height']
        
        def scroll_handler(*args):
            canvas_height = canvas.winfo_height()
            total_items = canvas.item_data['item_count'] if hasattr(canvas, 'item_data') and canvas.item_data else 60
            content_height = total_items * item_height
            
            if content_height <= canvas_height:
                # 内容小于等于可见区域，隐藏滚动条并重置位置
                scrollbar.set(0, 0)
                scrollbar.pack_forget()
                canvas.yview_moveto(0)  # 重置滚动位置
                return
            else:
                # 显示滚动条
                scrollbar.pack(fill=Y, side=RIGHT, before=canvas)
                
                # 限制滚动范围，防止出现空白区域
                if args[0] == 'moveto':
                    # 移动操作，需要限制范围
                    fraction = float(args[1])
                    # 计算最大允许的滚动比例，确保底部内容不会留白
                    max_fraction = max(0, 1 - canvas_height / content_height) if content_height > canvas_height else 0
                    # 限制在有效范围内
                    limited_fraction = max(0, min(fraction, max_fraction))
                    # 设置滚动条位置
                    visible_fraction = min(1, canvas_height / content_height)
                    scrollbar.set(limited_fraction, limited_fraction + visible_fraction)
                    # 应用滚动位置
                    canvas.yview_moveto(limited_fraction)
                else:
                    # 其他滚动操作（如 units），应用原始参数后再限制边界
                    scrollbar.set(*args)
                    # 然后确保当前位置在有效范围内
                    try:
                        # 获取当前滚动位置
                        current_view = canvas.yview()
                        if len(current_view) >= 2:
                            current_fraction = current_view[0]
                            max_fraction = max(0, 1 - canvas_height / content_height) if content_height > canvas_height else 0
                            limited_fraction = max(0, min(current_fraction, max_fraction))
                            if abs(current_fraction - limited_fraction) > 0.001:  # 如果位置被调整
                                canvas.yview_moveto(limited_fraction)
                                # 重新设置滚动条
                                visible_fraction = min(1, canvas_height / content_height)
                                scrollbar.set(limited_fraction, limited_fraction + visible_fraction)
                    except Exception:
                        pass
        return scroll_handler
    
    def _on_mouse_wheel(self, event, canvas):
        """鼠标滚轮滚动"""
        try:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass
        
    def _update_calendar(self):  
        """更新日历显示"""  
        first_day = datetime.date(self._current_year, self._current_month, 1)  
        first_weekday = (first_day.weekday() - self._firstweekday) % 7  
        _, days_in_month = calendar.monthrange(self._current_year, self._current_month)  
        
        if self._current_month == 1:  
            _, days_in_prev_month = calendar.monthrange(self._current_year - 1, 12)  
        else:  
            _, days_in_prev_month = calendar.monthrange(self._current_year, self._current_month - 1)  
        
        today = datetime.date.today()
        day_counter = 1  
        next_month_counter = 1  
        
        for week in range(6):  
            for day in range(7):  
                btn = self.day_buttons[week][day]  
                cell_index = week * 7 + day  
                  
                if cell_index < first_weekday:  
                    prev_day = days_in_prev_month - first_weekday + cell_index + 1  
                    btn.configure(text=str(prev_day), bootstyle="secondary-link", state=DISABLED)  
                    btn._is_today, btn._is_enabled, btn._day_number = False, False, 0  
                elif day_counter <= days_in_month:  
                    current_day = day_counter  
                    is_today = (self._current_year == today.year and 
                               self._current_month == today.month and current_day == today.day)  
                    is_selected = (self._startdate and self._current_year == self._startdate.year and
                                  self._current_month == self._startdate.month and current_day == self._startdate.day)  
                    
                    if is_selected:  
                        bootstyle = self._bootstyle  
                    elif is_today:  
                        bootstyle = f"{self._bootstyle}-outline"  
                    else:  
                        bootstyle = "link"  
                    
                    btn.configure(text=str(current_day), bootstyle=bootstyle, state=NORMAL)  
                    btn._is_today, btn._is_enabled, btn._day_number = is_today, True, current_day  
                    day_counter += 1  
                else:  
                    btn.configure(text=str(next_month_counter), bootstyle="secondary-link", state=DISABLED)  
                    btn._is_today, btn._is_enabled, btn._day_number = False, False, 0  
                    next_month_counter += 1  
      
    def _get_date_text(self):
        """获取日期文本"""
        if self._language == 'zh':
            return f"{self._current_year}年{self._current_month}月"
        else:
            return f"{self._current_year} {self._lang_config['month_names'][self._current_month - 1]}"
    
    def _get_day_text(self):
        """获取日期文本"""
        if self._language == 'zh':
            return f"{self._current_date.day}日"
        else:
            return str(self._current_date.day)
    
    def _get_time_text(self):
        """获取时间文本"""
        return f"{self._selected_time.hour:02d}:{self._selected_time.minute:02d}:{self._selected_time.second:02d}"
    
    def _on_time_select(self, time_type, value):
        """时间选择事件"""
        if time_type == 'hour':
            self._selected_time = datetime.time(value, self._selected_time.minute, self._selected_time.second)
        elif time_type == 'minute':
            self._selected_time = datetime.time(self._selected_time.hour, value, self._selected_time.second)
        elif time_type == 'second':
            self._selected_time = datetime.time(self._selected_time.hour, self._selected_time.minute, value)
        
        self.lbl时间.configure(text=self._get_time_text())
        self._update_time_panel()
    
    def _on_time_double_click(self, time_type, value):
        """时间数字双击事件 - 双击确认选择"""
        self._on_time_select(time_type, value)
        self._confirm_selection()
    
    def _on_canvas_time_click(self, event, canvas, time_type):
        """Canvas上时间选项点击事件"""
        # 获取点击位置
        y = canvas.canvasy(event.y)
        
        # 计算点击的是哪个项目
        item_height = canvas.item_data['item_height']
        clicked_index = int(y // item_height)
        
        # 确保在有效范围内
        if 0 <= clicked_index < canvas.item_data['item_count']:
            self._on_time_select(time_type, clicked_index)
    
    def _on_canvas_hover(self, event, canvas, time_type):
        """Canvas上鼠标悬停事件"""
        # 获取鼠标位置
        y = canvas.canvasy(event.y)
        
        # 计算鼠标在哪个项目上
        item_height = canvas.item_data['item_height']
        hover_index = int(y // item_height)
        
        # 检查是否在有效范围内
        if 0 <= hover_index < canvas.item_data['item_count']:
            # 检查是否是新悬停的项目
            if canvas.item_data['hover_item'] != hover_index:
                # 恢复之前悬停项目的颜色
                if canvas.item_data['hover_item'] is not None:
                    self._restore_item_color(canvas, canvas.item_data['hover_item'], time_type)
                
                # 高亮当前悬停项目
                self._highlight_item(canvas, hover_index, time_type)
                
                # 更新记录
                canvas.item_data['hover_item'] = hover_index
        else:
            # 鼠标不在有效项目上，恢复之前的项目
            if canvas.item_data['hover_item'] is not None:
                self._restore_item_color(canvas, canvas.item_data['hover_item'], time_type)
                canvas.item_data['hover_item'] = None
    
    def _on_canvas_leave(self, event, canvas):
        """Canvas上鼠标离开事件"""
        # 恢复悬停项目的颜色
        if canvas.item_data['hover_item'] is not None:
            time_type = canvas.item_data['time_type']
            self._restore_item_color(canvas, canvas.item_data['hover_item'], time_type)
            canvas.item_data['hover_item'] = None
    
    def _highlight_item(self, canvas, index, time_type):
        """高亮指定项目"""
        selected_value = getattr(self._selected_time, time_type)
        
        # 使用主题色配置，与年月选择面板保持一致
        highlight_color = self._get_bootstyle_color(self._bootstyle)
        
        # 查找对应的文字项目并更改颜色
        for item_id in canvas.find_withtag(f"time_{time_type}_{index}"):
            if canvas.type(item_id) == "text":
                canvas.itemconfig(item_id, fill=highlight_color)
    
    def _restore_item_color(self, canvas, index, time_type):
        """恢复指定项目的颜色"""
        selected_value = getattr(self._selected_time, time_type)
        
        if index == selected_value:
            # 选中项恢复为白色
            restore_color =self._get_bootstyle_color(self._bootstyle) #"white"
        else:
            # 非选中项恢复为灰色
            restore_color =   "#495057"
        
        # 查找对应的文字项目并恢复颜色
        for item_id in canvas.find_withtag(f"time_{time_type}_{index}"):
            if canvas.type(item_id) == "text":
                canvas.itemconfig(item_id, fill=restore_color)
    
    def _update_time_panel(self):
        """更新时间面板选择状态"""
        if not self._time_panel_created:
            return
        
        # 重新绘制时间选项以反映选中状态
        self._refresh_time_display()
        
        # 延迟滚动到选中项
        self.after(10, self._scroll_to_current_time)
    
    def _scroll_to_current_time(self):
        """滚动到当前选中的时间项"""
        if hasattr(self, 'hour_canvas') and self.hour_canvas:
            self._scroll_canvas_to_index(self.hour_canvas, self._selected_time.hour, 24)
        if hasattr(self, 'minute_canvas') and self.minute_canvas:
            self._scroll_canvas_to_index(self.minute_canvas, self._selected_time.minute, 60)
        if hasattr(self, 'second_canvas') and self.second_canvas:
            self._scroll_canvas_to_index(self.second_canvas, self._selected_time.second, 60)
    
    def _scroll_canvas_to_index(self, canvas, index, total_items):
        """滚动Canvas到指定索引位置"""
        try:
            canvas.update_idletasks()
            item_height = 25  # 使用新的固定高度
            content_height = total_items * item_height
            canvas_height = canvas.winfo_height()
            
            if content_height > canvas_height:
                # 计算目标位置（选中项在中间）
                target_y = index * item_height - canvas_height / 2 + item_height / 2
                # 限制滚动边界，防止出现空白区域
                target_y = max(0, min(target_y, content_height - canvas_height))
                
                # 转换为滚动比例
                fraction = target_y / content_height
                canvas.yview_moveto(fraction)
        except Exception:
            pass
    
    def _update_year_panel(self):
        """更新年选择面板"""
        if not self._year_panel_created:
            return
        for i, btn in enumerate(self.year_buttons):
            year = self._year_range_start + i
            btn.configure(text=str(year))
            btn.unbind("<Button-1>")
            btn.bind("<Button-1>", lambda e, y=year: self._on_year_click(y))
            btn.configure(bootstyle=self._bootstyle if year == self._current_year else "secondary")
    
    def _update_month_panel(self):
        """更新月选择面板"""
        if not self._month_panel_created:
            return
        for i, btn in enumerate(self.month_buttons):
            btn.configure(bootstyle=self._bootstyle if i + 1 == self._current_month else "secondary")
    
    def _switch_panel(self, panel_type):
        """切换面板显示 - 【优化】使用 lift() 切换，不再销毁布局"""
        self._current_panel = panel_type
        
        target = None
        if panel_type == self.PANEL_DAY:
            if not self.day_panel: self._create_day_panel()
            target = self.day_panel
            self._update_calendar()
        elif panel_type == self.PANEL_YEAR:
            if not self.year_panel: self._create_year_panel()
            target = self.year_panel
            self._update_year_panel()
        elif panel_type == self.PANEL_MONTH:
            if not self.month_panel: self._create_month_panel()
            target = self.month_panel
            self._update_month_panel()
        elif panel_type == self.PANEL_TIME:
            if not self.time_panel: self._create_time_panel()
            target = self.time_panel
            self._update_time_panel()
            
        if target:
            target.lift()
    
    def _on_year_label_click(self, event=None):
        """年份标签点击"""
        if self._current_panel == self.PANEL_YEAR:
            self._switch_panel(self.PANEL_DAY)
        else:
            self._year_range_start = self._current_year - 6
            self._switch_panel(self.PANEL_YEAR)
    
    def _on_month_label_click(self, event=None):
        """月份标签点击"""
        if self._current_panel == self.PANEL_MONTH:
            self._switch_panel(self.PANEL_DAY)
        else:
            self._switch_panel(self.PANEL_MONTH)
    
    def _on_day_label_click(self, event=None):
        """日期标签点击"""
        if self._current_panel == self.PANEL_DAY:
            self._switch_panel(self.PANEL_DAY)
        else:
            self._switch_panel(self.PANEL_DAY)
    
    def _on_time_label_click(self, event=None):
        """时间标签点击"""
        if self._current_panel == self.PANEL_TIME:
            self._switch_panel(self.PANEL_DAY)
        else:
            self._switch_panel(self.PANEL_TIME)
    
    def _on_year_click(self, year):
        """年份选择"""
        self._current_year = year
        self.lbl年份.configure(text=f"{self._current_year}{self._lang_config['year_suffix']}")
        self.lbl日期.configure(text=self._get_day_text())
        self._switch_panel(self.PANEL_DAY)
        self._update_calendar()
    
    def _on_month_click(self, month):
        """月份选择"""
        self._current_month = month
        self.lbl月份.configure(text=self._lang_config['month_names'][self._current_month - 1])
        self.lbl日期.configure(text=self._get_day_text())
        self._switch_panel(self.PANEL_DAY)
        self._update_calendar()
    
    def _on_day_click(self, week, day):
        """日期点击"""
        btn = self.day_buttons[week][day]
        if btn._is_enabled and btn._day_number > 0:
            self._selected_date = datetime.date(self._current_year, self._current_month, btn._day_number)
            self._current_date = self._selected_date
            self.lbl日期.configure(text=self._get_day_text())
            self._confirm_selection()
    
    def _prev(self):
        """上一个（根据当前面板类型）"""
        if self._current_panel == self.PANEL_YEAR:
            self._year_range_start -= 12
            self._update_year_panel()
        elif self._current_panel == self.PANEL_TIME:
            pass  # 时间面板不需要上下翻页
        else:
            self._current_month -= 1
            if self._current_month < 1:
                self._current_month = 12
                self._current_year -= 1
            self.lbl年份.configure(text=f"{self._current_year}{self._lang_config['year_suffix']}")
            self.lbl月份.configure(text=self._lang_config['month_names'][self._current_month - 1])
            self.lbl日期.configure(text=self._get_day_text())
            if self._day_panel_created:
                self._update_calendar()
    
    def _next(self):
        """下一个（根据当前面板类型）"""
        if self._current_panel == self.PANEL_YEAR:
            self._year_range_start += 12
            self._update_year_panel()
        elif self._current_panel == self.PANEL_TIME:
            pass  # 时间面板不需要上下翻页
        else:
            self._current_month += 1
            if self._current_month > 12:
                self._current_month = 1
                self._current_year += 1
            self.lbl年份.configure(text=f"{self._current_year}{self._lang_config['year_suffix']}")
            self.lbl月份.configure(text=self._lang_config['month_names'][self._current_month - 1])
            self.lbl日期.configure(text=self._get_day_text())
            if self._day_panel_created:
                self._update_calendar()
    
    def _select_today(self):
        """选择今天"""
        today = datetime.date.today()
        self._current_year = today.year
        self._current_month = today.month
        self.lbl年份.configure(text=f"{self._current_year}{self._lang_config['year_suffix']}")
        self.lbl月份.configure(text=self._lang_config['month_names'][self._current_month - 1])
        self.lbl日期.configure(text=self._get_day_text())
        self._selected_date = today
        self._confirm_selection()
    
    def _select_now(self):
        """选择现在的时间 - 直接输入当前日期时间并确认"""
        now = datetime.datetime.now()
        # 更新日期显示
        self._current_year = now.year
        self._current_month = now.month
        self.lbl年份.configure(text=f"{self._current_year}{self._lang_config['year_suffix']}")
        self.lbl月份.configure(text=self._lang_config['month_names'][self._current_month - 1])
        self.lbl日期.configure(text=self._get_day_text())
        # 更新日期面板（如果已创建）
        if self._day_panel_created:
            self._update_calendar()
        # 更新时间显示
        self._selected_time = now.time()
        self.lbl时间.configure(text=self._get_time_text())
        # 设置当前日期
        self._selected_date = now.date()
        # 更新时间面板以同步滚动条位置
        self._update_time_panel()
        # 直接确认选择
        self._confirm_selection()
    
    def _update_to_today_without_confirm(self, event):
        """右键点击今天按钮 - 只更新显示不确认选择"""
        today = datetime.date.today()
        # 更新当前年月
        self._current_year = today.year
        self._current_month = today.month
        self.lbl年份.configure(text=f"{self._current_year}{self._lang_config['year_suffix']}")
        self.lbl月份.configure(text=self._lang_config['month_names'][self._current_month - 1])
        self.lbl日期.configure(text=self._get_day_text())
        # 更新日期面板（如果已创建）
        if self._day_panel_created:
            self._update_calendar()
        # 设置选中日期
        self._selected_date = today
        # 更新时间显示
        self.lbl时间.configure(text=self._get_time_text())
        # 不调用确认选择，保持对话框开启
    
    def _update_to_now_without_confirm(self, event):
        """右键点击现在按钮 - 只更新显示不确认选择"""
        now = datetime.datetime.now()
        # 更新日期显示
        self._current_year = now.year
        self._current_month = now.month
        self.lbl年份.configure(text=f"{self._current_year}{self._lang_config['year_suffix']}")
        self.lbl月份.configure(text=self._lang_config['month_names'][self._current_month - 1])
        self.lbl日期.configure(text=self._get_day_text())
        # 更新日期面板（如果已创建）
        if self._day_panel_created:
            self._update_calendar()
        # 更新时间显示
        self._selected_time = now.time()
        self.lbl时间.configure(text=self._get_time_text())
        # 设置当前日期
        self._selected_date = now.date()
        # 更新时间面板以同步滚动条位置
        self._update_time_panel()
        # 不调用确认选择，保持对话框开启
    
    def _confirm_selection(self):
        """确认选择"""
        if self._selected_date:
            self.date_selected = datetime.datetime.combine(self._selected_date, self._selected_time)
        else:
            self.date_selected = datetime.datetime.combine(self._startdate, self._selected_time)
        
        if self._date_selected_callback:
            self._date_selected_callback(self.date_selected)
        self.destroy()
    
    def _cancel(self):
        """取消选择"""
        self.date_selected = None
        self.destroy()
    
    def _center_window(self):
        """窗口居中"""
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry(f"+{x}+{y}")


