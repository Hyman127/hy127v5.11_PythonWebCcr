"""  
汉化的日期选择器和自定义DateEntry控件 - 支持高DPI  
支持中文月份、星期显示，并可自由设置宽度和高度  
支持 Excel 风格日期格式 (如 yyyy-mm-dd, hh:mm:ss)  
version: 0.0.4 2026.1.23 - 修复时间格式初始化显示问题
"""  
import calendar  
import datetime  
from sys import maxsize
from tkinter import StringVar, Toplevel, Frame, Label, Button  
import ttkbootstrap as ttk  
from ttkbootstrap.utility import enable_high_dpi_awareness, scale_size  
from ttkbootstrap.constants import *  
try:
    from .HY127_DateTimePicker import HY127_DatePickerDialog, adjust_popup_position_to_screen
except ImportError:
    from HY127_DateTimePicker import HY127_DatePickerDialog, adjust_popup_position_to_screen


def Excel格式转Python格式(excel_format):
    """
    将 Excel 风格日期格式转换为 Python strftime 格式
    Excel 格式说明:
        yyyy - 4位年份 (2024) -> %Y
        yy   - 2位年份 (24) -> %y
        mm   - 2位月份 (01-12) -> %m
        m    - 月份不带前导零 (1-12) -> %m (需配合其他判断)
        dd   - 2位日期 (01-31) -> %d
        d    - 日期不带前导零 (1-31) -> %d
        hh   - 2位小时 (00-23) -> %H
        h    - 小时不带前导零 (0-23) -> %H
        ii   - 2位分钟 (00-59) -> %M (Excel用ii表示分钟避免和月份冲突)
        ss   - 2位秒 (00-59) -> %S
        AM/PM - 上午/下午 -> %p
        aaaa - 星期几全称 (星期一) -> %A
        aaa - 星期几缩写 (周一) -> %a
    参数:
        excel_format: Excel 风格的日期格式字符串
    返回:
        str: Python strftime 格式字符串
    """
    if not excel_format:
        return '%Y-%m-%d'
    
    # 转换映射表（按优先级排序，长模式在前避免短模式先匹配）
    转换规则 = [
        # Excel 特殊格式
        ('aaaa', '%A'),  # 星期几全称
        ('yyyyMMdd', '%Y%m%d'),  # 无分隔符完整日期
        ('yyyyMM', '%Y%m'),  # 年月
        ('MMdd', '%m%d'),  # 月日
        ('HHmmss', '%H%M%S'),  # 无分隔符时间
        ('HHmm', '%H%M'),  # Excel 用 ii 表示分钟
        ('AM/PM', '%p'),  # 上午下午
        ('am/pm', '%p'),  # 小写也可以
        # 标准格式
        ('yyyy', '%Y'),  # 4位年份
        ('yyy', '%Y'),   # 3位年份也当4位处理
        ('yy', '%y'),    # 2位年份
        ('HH', '%H'),    # 24小时制小时
        ('mm', '%M'),    # 分钟（时间格式）
        ('ss', '%S'),    # 秒
        # 月份和日期（需要小心处理顺序）
        ('mmmm', '%B'),   # 英文月份全称
        ('mmm', '%b'),    # 英文月份缩写
        ('MM', '%m'),     # 数字月份（两位的）
        ('dd', '%d'),     # 数字日期（两位的）
        # 注意：单字母的 m 和 d 在日期中很少单独使用，
        # 如果需要支持需要根据上下文判断，这里暂不处理
    ]
    
    result = excel_format
    for excel_pattern, python_pattern in 转换规则:
        result = result.replace(excel_pattern, python_pattern)
    
    return result


class HY127_DateEntry(ttk.Frame):
    """
    自定义日期输入控件，支持自由设置宽度、高度和字体
    Grid布局版：按钮宽度始终等于高度，文本框填充剩余空间
    """
    
    def __init__(self, master=None, width=None, height=None, entry_width=None,
                 dateformat='%Y-%m-%d', firstweekday=0, 
                 startdate=None, bootstyle=PRIMARY, 
                 chinese=True, font=None, command=None, state=NORMAL, language='zh', **kwargs):
        """
        初始化自定义日期输入控件
        参数:
            master: 父容器
            width: 组件整体宽度（像素），包含文本框和按钮
            height: 组件整体高度（像素）
            entry_width: 内部文本框宽度（像素），不含右侧按钮；为空时自动按整体宽度计算
            dateformat: 日期格式
            firstweekday: 每周第一天 (0=周一, 6=周日)
            startdate: 起始日期
            bootstyle: 主题样式
            chinese: 是否使用中文日期选择器
            font: 字体配置，格式为 ("字体名", 大小) 或 ("字体名", 大小, "样式")
            command: 日期选择后的回调函数
            state: 控件状态 (NORMAL 或 DISABLED)
            language: 语言 ('zh' 中文, 'en' 英文)
            **kwargs: 其他Frame参数
        """
        super().__init__(master, **kwargs)
        self._width = width or 200
        self._height = height or 35
        self._entry_width = entry_width
        
        # 转换 Excel 格式为 Python 格式
        self._dateformat = Excel格式转Python格式(dateformat)
        self._原始格式 = dateformat  # 保存原始格式用于显示
        self._firstweekday = firstweekday
        
        # 检测格式类型
        self._只显示时间 = self._检测是否只显示时间(self._dateformat)
        self._只显示日期 = self._检测是否只显示日期(self._dateformat)
        
        # 设置起始日期：根据格式类型决定
        if self._只显示时间:
            # 只显示时间模式：如果用户提供了startdate，使用它；否则使用当前时间
            if startdate:
                if isinstance(startdate, datetime.datetime):
                    self._startdate = startdate
                elif isinstance(startdate, datetime.time):
                    # 如果是 time 对象，组合成 datetime
                    today = datetime.date.today()
                    self._startdate = datetime.datetime.combine(today, startdate)
                else:
                    self._startdate = datetime.datetime.now()
            else:
                self._startdate = datetime.datetime.now()
        elif self._只显示日期:
            # 只显示日期模式：使用 datetime.date
            if startdate:
                if isinstance(startdate, datetime.datetime):
                    self._startdate = startdate.date()
                else:
                    self._startdate = startdate
            else:
                self._startdate = datetime.date.today()
        else:
            # 日期+时间模式：使用 datetime.datetime 支持完整时间
            if startdate:
                if isinstance(startdate, datetime.date) and not isinstance(startdate, datetime.datetime):
                    self._startdate = datetime.datetime.combine(startdate, datetime.time())
                else:
                    self._startdate = startdate
            else:
                self._startdate = datetime.datetime.now()
        
        self._bootstyle = bootstyle
        self._chinese = chinese
        self._font = font
        self._command = command
        self._state = state
        self._language = language
        
        self._date_var = StringVar(value=self._startdate.strftime(self._dateformat))
        
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0, minsize=35)
        
        # 使用固定像素尺寸控制内部布局，避免 Entry 因 width=1 被压缩到只显示少量字符
        self.grid_propagate(False)
        self.pack_propagate(False)
        super().configure(width=self._width, height=self._height)
        
        # 创建控件
        self._create_widgets()
        self._apply_size_layout()
        
        # 应用初始状态
        self._update_state()
        
        # 绑定尺寸变化事件
        self.bind('<Configure>', self._on_configure)

    def _create_widgets(self):
        """创建内部控件 - 使用 grid 布局"""
        self._更新控件样式()
        
        self.entry = ttk.Entry(
            self,
            textvariable=self._date_var,
            font=self._font if self._font else None,
            style=self._entry_style,
            width=1
        )
        self.entry.grid(row=0, column=0, sticky='nsew', padx=(0, 0))
        
        self.button = ttk.Button(
            self,
            text="📅",
            command=self._on_date_button_click,
            style=self._button_style,
            padding=(0, 0),
            takefocus=False
        )
        self.button.grid(row=0, column=1, sticky='nsew')
        self.bind('<<ThemeChanged>>', self._更新主题样式)

    def _on_configure(self, event=None):
        """响应尺寸变化事件，动态调整内部 Entry / Button 宽度。"""
        if event and event.widget == self:
            self._apply_size_layout(width=event.width, height=event.height)

    def _apply_size_layout(self, width=None, height=None):
        """按像素重新分配内部输入框与按钮宽度。"""
        if not hasattr(self, 'entry') or not hasattr(self, 'button'):
            return

        total_width = int(width if width and width > 1 else self._width)
        total_height = int(height if height and height > 1 else self._height)

        button_width = max(30, total_height)
        if self._entry_width is not None:
            entry_width = max(40, int(self._entry_width))
            total_width = max(total_width, entry_width + button_width)
            super().configure(width=total_width)
        else:
            entry_width = max(40, total_width - button_width)

        # width 仍需给 ttk.Entry 一个字符宽兜底，真正像素宽度由 grid minsize 控制
        approx_chars = max(4, entry_width // 12)
        self.entry.configure(width=approx_chars)
        self.button.configure(width=max(2, button_width // 14))

        self.grid_columnconfigure(0, minsize=entry_width, weight=1)
        self.grid_columnconfigure(1, minsize=button_width, weight=0)
    
    def _update_state(self):
        """根据状态更新控件的启用/禁用状态"""
        if not hasattr(self, 'entry') or not hasattr(self, 'button'):
            return
        
        if self._state == DISABLED:
            self.entry.configure(state=DISABLED)
            self.button.configure(state=DISABLED)
        else:
            self.entry.configure(state=NORMAL)
            self.button.configure(state=NORMAL)
    
    def _更新控件样式(self):
        """根据当前主题更新控件样式"""
        # 根据 bootstyle 生成对应的样式名称
        if self._bootstyle:
            self._entry_style = f'{self._bootstyle}.TEntry'
            self._button_style = f'{self._bootstyle}.TButton'
        else:
            self._entry_style = 'TEntry'
            self._button_style = 'TButton'
    
    def _检测是否只显示时间(self, dateformat):
        """
        检测日期格式是否只包含时间部分（没有日期部分）
        参数:
            dateformat: 日期格式字符串
        返回:
            bool: 如果格式只包含时间部分（%H, %M, %S等）返回True，否则返回False
        """
        # 日期格式符号
        日期格式符号 = ['%Y', '%y', '%m', '%d', '%B', '%b', '%A', '%a', '%w', '%u', '%U', '%W', '%V', '%G', '%j', '%G', '%C']
        # 时间格式符号
        时间格式符号 = ['%H', '%I', '%M', '%S', '%f', '%p', '%z', '%Z']
        
        # 清理格式字符串中的转义字符
        清理后的格式 = dateformat.replace('%%', '')
        
        # 检查是否包含任何日期格式符号
        包含日期 = any(符号 in 清理后的格式 for 符号 in 日期格式符号)
        
        # 如果不包含日期格式符号，且包含时间格式符号，则认为是只显示时间
        if not 包含日期:
            包含时间 = any(符号 in 清理后的格式 for 符号 in 时间格式符号)
            return 包含时间
        
        return False
    
    def _检测是否只显示日期(self, dateformat):
        """
        检测日期格式是否只包含日期部分（没有时间部分）
        参数:
            dateformat: 日期格式字符串
        返回:
            bool: 如果格式只包含日期部分（%Y, %m, %d等）且不包含时间部分返回True，否则返回False
        """
        # 日期格式符号
        日期格式符号 = ['%Y', '%y', '%m', '%d', '%B', '%b', '%A', '%a', '%w', '%u', '%U', '%W', '%V', '%G', '%j', '%G', '%C']
        # 时间格式符号
        时间格式符号 = ['%H', '%I', '%M', '%S', '%f', '%p', '%z', '%Z']
        
        # 清理格式字符串中的转义字符
        清理后的格式 = dateformat.replace('%%', '')
        
        # 检查是否包含任何日期格式符号
        包含日期 = any(符号 in 清理后的格式 for 符号 in 日期格式符号)
        
        # 检查是否包含时间格式符号
        包含时间 = any(符号 in 清理后的格式 for 符号 in 时间格式符号)
        
        # 如果包含日期且不包含时间，则认为是只显示日期
        if 包含日期 and not 包含时间:
            return True
        
        return False
    
    def _更新主题样式(self, event=None):
        """响应主题变更事件，更新控件样式"""
        self._更新控件样式()
        self.entry.configure(style=self._entry_style)
        self.button.configure(style=self._button_style)
    
    def _format_date_on_focus_out(self, event=None):
        """
        焦点离开时自动格式化日期
        参数:
            event: 事件对象
        """
        date_str = self._date_var.get().strip()
        if not date_str:
            return
        # 尝试解析日期
        date_obj = self.get_date()
        if date_obj is not None:
            # 如果解析成功，格式化为统一格式
            formatted_date = date_obj.strftime(self._dateformat)
            self._date_var.set(formatted_date)

    def _on_date_button_click(self):
        """点击日历按钮时的回调"""
        # 获取当前日期，支持多种格式
        current_date = self.get_date()
        if current_date is None:
            current_date = self._startdate
        
        button_x = self.button.winfo_rootx()
        button_y = self.button.winfo_rooty()
        button_width = self.button.winfo_width()
        button_height = self.button.winfo_height()

        # 计算弹出位置（在按钮下方）
        x = button_x - 7
        y = button_y + button_height + 1
        
        # 确保窗口已经完全显示
        self.update_idletasks()
        
        # 定义日期选择回调函数，实时更新文本框
        def on_date_selected(selected_date):
            """日期选择时的回调函数"""
            self._date_var.set(selected_date.strftime(self._dateformat))
            # 触发自定义事件
            self.event_generate("<<DateEntrySelected>>")
            # 调用 command 回调
            if self._command:
                self._command()
        
        # 使用汉化或标准的日期选择器
        if self._chinese:
            # 根据格式判断初始面板和初始时间
            initial_panel = 'time' if self._只显示时间 else 'day'
            # 如果是纯日期模式，时间传入 0:0:0；否则传入当前时间
            初始时间 = datetime.time(0, 0, 0) if self._只显示日期 else current_date.time()
            
            dialog = HY127_DatePickerDialog(
                parent=self.winfo_toplevel(),
                title="选择日期",
                firstweekday=self._firstweekday,
                startdate=current_date,
                bootstyle=self._bootstyle,
                position=(x, y),
                anchor_rect=(button_x, button_y, button_width, button_height),
                date_selected_callback=on_date_selected,
                initial_panel=initial_panel,
                language=self._language,
                starttime=初始时间
            )
        else:
            # 标准对话框
            from ttkbootstrap.dialogs import DatePickerDialog
            # 如果是纯日期模式，设置时间为 0:0:0
            对话框初始日期 = current_date
            if self._只显示日期 and 对话框初始日期:
                对话框初始日期 = datetime.datetime.combine(current_date, datetime.time(0, 0, 0))
            
            dialog = DatePickerDialog(
                parent=self.winfo_toplevel(),
                title="Choose Date",
                firstweekday=self._firstweekday,
                startdate=对话框初始日期,
                bootstyle=self._bootstyle
            )
            # 移动到按钮位置
            dialog.update_idletasks()
            popup_width = dialog.winfo_reqwidth() or dialog.winfo_width()
            popup_height = dialog.winfo_reqheight() or dialog.winfo_height()
            x, y = adjust_popup_position_to_screen(
                dialog,
                x,
                y,
                popup_width,
                popup_height,
                anchor_x=button_x,
                anchor_y=button_y,
                anchor_width=button_width,
                anchor_height=button_height,
            )
            dialog.geometry(f"+{x}+{y}")
            # 获取选择的日期并更新
            if dialog.date_selected:
                self._date_var.set(dialog.date_selected.strftime(self._dateformat))
                # 触发自定义事件
                self.event_generate("<<DateEntrySelected>>")
                # 调用 command 回调
                if self._command:
                    self._command()

    def get_date(self):
        """
        获取选中的日期对象，支持多种日期格式
        根据格式类型返回：
        - 只显示时间模式：返回 datetime.datetime 对象（使用文本框中的时间）
        - 只显示日期模式：返回 datetime.date 对象
        - 日期+时间模式：返回 datetime.datetime 对象
        返回:
            datetime.date 或 datetime.datetime 对象，如果解析失败返回 None
        """
        date_str = self._date_var.get().strip()
        if not date_str:
            if self._只显示时间:
                return self._startdate if self._startdate else datetime.datetime.now()
            elif self._只显示日期:
                return datetime.date.today()
            else:
                return None
        
        if self._只显示时间:
            # 只显示时间：解析时间字符串，组合成完整的datetime对象
            time_formats = [self._dateformat, '%H:%M:%S', '%H:%M', '%I:%M:%S %p', '%I:%M %p']
            for fmt in time_formats:
                try:
                    # 解析时间部分
                    time_obj = datetime.datetime.strptime(date_str, fmt).time()
                    # 使用 _startdate 的日期部分（如果有的话），否则使用今天
                    if self._startdate and isinstance(self._startdate, datetime.datetime):
                        return datetime.datetime.combine(self._startdate.date(), time_obj)
                    else:
                        return datetime.datetime.combine(datetime.date.today(), time_obj)
                except ValueError:
                    continue
            # 如果解析失败，返回 _startdate
            return self._startdate if self._startdate else datetime.datetime.now()
        
        if self._只显示日期:
            date_formats = [
                self._dateformat,
                '%Y-%m-%d',
                '%Y/%m/%d',
                '%Y年%m月%d日',
                '%m/%d/%Y',
                '%d/%m/%Y',
            ]
            for fmt in date_formats:
                try:
                    return datetime.datetime.strptime(date_str, fmt).date()
                except ValueError:
                    continue
        else:
            datetime_formats = [
                self._dateformat,
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d %H:%M',
                '%Y/%m/%d %H:%M:%S',
                '%Y/%m/%d %H:%M',
                '%Y年%m月%d日 %H:%M:%S',
            ]
            for fmt in datetime_formats:
                try:
                    return datetime.datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
        
        try:
            from dateutil import parser
            result = parser.parse(date_str)
            if self._只显示时间:
                # 保持 _startdate 的日期部分
                if self._startdate and isinstance(self._startdate, datetime.datetime):
                    return result.replace(year=self._startdate.year, 
                                        month=self._startdate.month, 
                                        day=self._startdate.day)
                else:
                    today = datetime.date.today()
                    return result.replace(year=today.year, month=today.month, day=today.day)
            return result
        except Exception:
            return None

    def set_date(self, date):
        """
        设置日期
        参数:
            date: datetime.date 对象、datetime.datetime 对象或字符串
        """
        if isinstance(date, datetime.datetime):
            self._startdate = date
            self._date_var.set(date.strftime(self._dateformat))
        elif isinstance(date, datetime.date):
            if self._只显示时间:
                # 如果是时间模式，需要转换为datetime
                self._startdate = datetime.datetime.combine(date, datetime.time())
            else:
                self._startdate = date
            self._date_var.set(date.strftime(self._dateformat))
        elif isinstance(date, str):
            self._date_var.set(date)

    def get(self):
        """获取日期字符串"""
        return self._date_var.get()

    def set(self, value):
        """设置日期字符串"""
        self._date_var.set(value)

    def enable(self):
        """启用控件"""
        self.entry.configure(state=NORMAL)
        self.button.configure(state=NORMAL)

    def disable(self):
        """禁用控件"""
        self.entry.configure(state=DISABLED)
        self.button.configure(state=DISABLED)

    def configure(self, **kwargs):
        """
        配置控件样式
        参数:
            **kwargs: 样式配置参数
                - entry_style: 文本框样式名称
                - button_style: 按钮样式名称
                - bootstyle: 整体主题样式（会同时应用到entry和button）
                - font: 字体配置
                - width: 组件宽度
                - entry_width: 内部文本框宽度（像素）
                - height: 组件高度
                - dateformat: 日期格式
                - firstweekday: 每周第一天
                - startdate: 起始日期
                - chinese: 是否使用中文
        """
        if 'entry_style' in kwargs:
            self._entry_style = kwargs.pop('entry_style')
            if hasattr(self, 'entry'):
                self.entry.configure(style=self._entry_style)
        
        if 'button_style' in kwargs:
            self._button_style = kwargs.pop('button_style')
            if hasattr(self, 'button'):
                self.button.configure(style=self._button_style)
        
        if 'bootstyle' in kwargs:
            self._bootstyle = kwargs.pop('bootstyle')
            self._更新控件样式()
            if hasattr(self, 'entry'):
                self.entry.configure(style=self._entry_style)
            if hasattr(self, 'button'):
                self.button.configure(style=self._button_style)
        
        if 'font' in kwargs:
            self._font = kwargs.pop('font')
            if hasattr(self, 'entry'):
                self.entry.configure(font=self._font)
        
        if 'width' in kwargs:
            self._width = kwargs.pop('width')
            super().configure(width=self._width)
            self._apply_size_layout()
        
        if 'entry_width' in kwargs:
            self._entry_width = kwargs.pop('entry_width')
            self._apply_size_layout()
        
        if 'height' in kwargs:
            self._height = kwargs.pop('height')
            super().configure(height=self._height)
            self._apply_size_layout()
        
        if 'dateformat' in kwargs:
            self._dateformat = kwargs.pop('dateformat')
            if hasattr(self, 'entry'):
                date_str = self._date_var.get().strip()
                if date_str:
                    date_obj = self.get_date()
                    if date_obj:
                        self._date_var.set(date_obj.strftime(self._dateformat))
        
        if 'firstweekday' in kwargs:
            self._firstweekday = kwargs.pop('firstweekday')
        
        if 'startdate' in kwargs:
            new_startdate = kwargs.pop('startdate')
            if hasattr(self, 'entry'):
                if self._只显示时间:
                    if isinstance(new_startdate, datetime.datetime):
                        self._startdate = new_startdate
                    elif isinstance(new_startdate, datetime.time):
                        self._startdate = datetime.datetime.combine(datetime.date.today(), new_startdate)
                    else:
                        self._startdate = datetime.datetime.combine(new_startdate, datetime.time())
                elif self._只显示日期:
                    if isinstance(new_startdate, datetime.datetime):
                        self._startdate = new_startdate.date()
                    else:
                        self._startdate = new_startdate
                else:
                    if isinstance(new_startdate, datetime.date) and not isinstance(new_startdate, datetime.datetime):
                        self._startdate = datetime.datetime.combine(new_startdate, datetime.time())
                    else:
                        self._startdate = new_startdate
                self._date_var.set(self._startdate.strftime(self._dateformat))
        
        if 'chinese' in kwargs:
            self._chinese = kwargs.pop('chinese')
        
        if 'command' in kwargs:
            self._command = kwargs.pop('command')
        
        if 'state' in kwargs:
            self._state = kwargs.pop('state')
            self._update_state()
        
        super().configure(**kwargs)

        
# ==================== 演示程序 ====================
def demo():
    """演示程序 - 展示place和grid布局效果"""
    import tkinter as tk
    from tkinter import StringVar, CENTER
    
    root = ttk.Window(themename="darkly")
    root.title("HY127_DateEntry布局演示 - Place和Grid布局对比")
    root.geometry("1000x700")
    try:
        from .. import dialogs
    except ImportError:
        import dialogs
    dialogs.z定位窗体到鼠标所在屏幕(root)
    # 当前主题变量
    current_theme = StringVar(value="darkly")
    
    # 标题区域
    header_frame = ttk.Frame(root)
    header_frame.place(relx=0.0, rely=0.0, relwidth=1.0, height=60, x=0, y=0)
    
    title_label = ttk.Label(
        header_frame, 
        text="📅 HY127_DateEntry 布局效果演示",
        font=("Microsoft YaHei", 18, "bold"),
        bootstyle="primary"
    )
    title_label.place(relx=0.5, rely=0.5, anchor=CENTER)
    
    # 主题选择下拉框
    theme_label = ttk.Label(header_frame, text="主题切换：", font=("Microsoft YaHei", 10))
    theme_label.place(relx=0.95, rely=0.3, anchor=E)
    
    themes = [
        "darkly",      # 深色
        "superhero",   # 深色
        "cyborg",      # 深色
        "litera",      # 浅色
        "cosmo",       # 浅色
        "flatly",      # 浅色
    ]
    
    def change_theme(event=None):
        """切换主题"""
        selected = theme_combo.get()
        root.style.theme_use(selected)
        current_theme.set(selected)
    
    theme_combo = ttk.Combobox(
        header_frame,
        values=themes,
        state="readonly",
        width=12,
        textvariable=current_theme
    )
    theme_combo.place(relx=0.98, rely=0.5, anchor=E, x=-10)
    theme_combo.bind("<<ComboboxSelected>>", change_theme)
    
    # 分隔线
    ttk.Separator(root, orient=HORIZONTAL).place(relx=0.0, rely=0.09, relwidth=1.0, height=1, x=0, y=0)
    
    # ==================== 第一部分：Place布局演示 ====================
    place_frame = ttk.Labelframe(root, text="📍 Place布局演示（相对位置）", padding=15)
    place_frame.place(relx=0.02, rely=0.11, relwidth=0.46, relheight=0.42, x=0, y=0)
    
    # Place布局说明
    place_info = ttk.Label(
        place_frame,
        text="使用 relx/rely + relwidth/relheight 实现相对定位\n窗口缩放时自动适应",
        font=("Microsoft YaHei", 9),
        bootstyle="info"
    )
    place_info.place(relx=0.0, rely=0.0, relwidth=1.0, height=40, x=0, y=0)
    
    # Place布局示例1：标准高度
    label_p1 = ttk.Label(place_frame, text="标准高度 (height=35)：", font=("Microsoft YaHei", 10))
    label_p1.place(relx=0.0, rely=0.18, relwidth=0.4, height=25, x=0, y=0)
    
    date_entry_p1 = HY127_DateEntry(
        place_frame,
        width=200,
        height=35,
        dateformat='HH:mm:ss',
         language="en",
        bootstyle=PRIMARY
    )
    date_entry_p1.place(relx=0.42, rely=0.18, relwidth=0.55, height=35, x=0, y=0)
    
    # Place布局示例2：中等高度
    label_p2 = ttk.Label(place_frame, text="中等高度 (height=45)：", font=("Microsoft YaHei", 10))
    label_p2.place(relx=0.0, rely=0.38, relwidth=0.4, height=25, x=0, y=0)
    
    date_entry_p2 = HY127_DateEntry(
        place_frame,
        width=200,
        height=45,
        dateformat='%Y年%m月%d日',
        language="en",
        bootstyle=SUCCESS
    )
    date_entry_p2.place(relx=0.42, rely=0.38, relwidth=0.55, height=45, x=0, y=0)
    
    # Place布局示例3：大高度
    label_p3 = ttk.Label(place_frame, text="大高度 (height=60)：", font=("Microsoft YaHei", 10))
    label_p3.place(relx=0.0, rely=0.58, relwidth=0.4, height=25, x=0, y=0)
    
    date_entry_p3 = HY127_DateEntry(
        place_frame,
        width=200,
        height=60,
        dateformat='%Y/%m/%d',
        bootstyle=INFO
    )
    date_entry_p3.place(relx=0.42, rely=0.58, relwidth=0.55, height=60, x=0, y=0)
    
    # Place布局示例4：特大高度
    label_p4 = ttk.Label(place_frame, text="特大高度 (height=80)：", font=("Microsoft YaHei", 10))
    label_p4.place(relx=0.0, rely=0.78, relwidth=0.4, height=25, x=0, y=0)
    
    date_entry_p4 = HY127_DateEntry(
        place_frame,
        width=200,
        height=80,
        dateformat='%d/%m/%Y',
        bootstyle=WARNING
    )
    date_entry_p4.place(relx=0.42, rely=0.78, relwidth=0.55, height=80, x=0, y=0)
    
    # ==================== 第二部分：Grid布局演示 ====================
    grid_frame = ttk.Labelframe(root, text="🔲 Grid布局演示（网格布局）", padding=15)
    grid_frame.place(relx=0.52, rely=0.11, relwidth=0.46, relheight=0.42, x=0, y=0)
    
    # Grid布局说明
    grid_info = ttk.Label(
        grid_frame,
        text="使用 grid(row=行, column=列, padx/pady=间距) 实现网格布局\n支持 sticky 对齐方式",
        font=("Microsoft YaHei", 9),
        bootstyle="info"
    )
    grid_info.grid(row=0, column=0, columnspan=2, sticky=EW, pady=(0, 10))
    
    # 配置grid列权重
    grid_frame.grid_columnconfigure(0, weight=1)
    grid_frame.grid_columnconfigure(1, weight=2)
    
    # Grid布局示例1
    label_g1 = ttk.Label(grid_frame, text="标准高度 (35px)：", font=("Microsoft YaHei", 10))
    label_g1.grid(row=1, column=0, sticky=W, padx=5, pady=8)
    
    date_entry_g1 = HY127_DateEntry(
        grid_frame,
        width=150,
        height=35,
        dateformat='%Y-%m-%d',
        bootstyle=PRIMARY
    )
    date_entry_g1.grid(row=1, column=1, sticky=EW, padx=5, pady=8)
    
    # Grid布局示例2
    label_g2 = ttk.Label(grid_frame, text="中等高度 (45px)：", font=("Microsoft YaHei", 10))
    label_g2.grid(row=2, column=0, sticky=W, padx=5, pady=8)
    
    date_entry_g2 = HY127_DateEntry(
        grid_frame,
        width=150,
        height=45,
        dateformat='%Y年%m月%d日',
        bootstyle=SUCCESS
    )
    date_entry_g2.grid(row=2, column=1, sticky=EW, padx=5, pady=8)
    
    # Grid布局示例3
    label_g3 = ttk.Label(grid_frame, text="大高度 (60px)：", font=("Microsoft YaHei", 10))
    label_g3.grid(row=3, column=0, sticky=W, padx=5, pady=8)
    
    date_entry_g3 = HY127_DateEntry(
        grid_frame,
        width=150,
        height=60,
        dateformat='yyyy年MM月dd日 HH:mm:ss',
        bootstyle=INFO
    )
    date_entry_g3.grid(row=3, column=1, sticky=EW, padx=5, pady=8)
    
    # Grid布局示例4
    label_g4 = ttk.Label(grid_frame, text="特大高度 (80px)：", font=("Microsoft YaHei", 10))
    label_g4.grid(row=4, column=0, sticky=W, padx=5, pady=8)
    
    date_entry_g4 = HY127_DateEntry(
        grid_frame,
        width=150,
        height=80,
        dateformat='HH:mm:ss',
        bootstyle=WARNING
    )
    date_entry_g4.grid(row=4, column=1, sticky=EW, padx=5, pady=8)
    
   
    
    # ==================== 底部状态栏 ====================
    status_frame = ttk.Frame(root)
    status_frame.place(relx=0.0, rely=0.96, relwidth=1.0, relheight=0.04, x=0, y=0)
    
    status_label = ttk.Label(
        status_frame,
        text="💡 提示：拖动窗口边缘调整大小，观察不同布局的响应效果",
        font=("Microsoft YaHei", 9),
        bootstyle="inverse-secondary"
    )
    status_label.place(relx=0.5, rely=0.5, anchor=CENTER)
    
    # 绑定事件显示选中结果
    def on_date_selected(entry_widget, name):
        def handler(event):
            selected = entry_widget.get()
            date_obj = entry_widget.get_date()
            status_label.configure(
                text=f"📅 {name}: {selected} | 日期对象: {date_obj} | 主题: {current_theme.get()}"
            )
        return handler
    
    # 绑定所有控件
    for idx, entry in enumerate([date_entry_p1, date_entry_p2, date_entry_p3, date_entry_p4]):
        try:
            entry.bind("<<DateEntrySelected>>", on_date_selected(entry, f"Place{idx}"))
        except Exception:
            pass
    
    for idx, entry in enumerate([date_entry_g1, date_entry_g2, date_entry_g3, date_entry_g4]):
        try:
            entry.bind("<<DateEntrySelected>>", on_date_selected(entry, f"Grid{idx}"))
        except Exception:
            pass
    
    
    # 鼠标滚轮绑定
    def on_mousewheel(event):
        canvas.yview_scroll(int(-1*(event.delta/120)), "units")
    
    root.mainloop()
if __name__ == "__main__":
    demo()
