# -*- coding: utf-8 -*-
"""
可搜索的下拉选择组件。

特性:
1. `multiselect=True` 时为下拉多选，支持搜索与批量读取选中项
2. `multiselect=False` 时退化为普通下拉单选
3. 折叠态使用标签形式展示已选项，标签右侧可点 x 取消
4. 颜色跟随 ttkbootstrap 主题，在深浅主题下自动调整
"""
import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

try:
    from .HY127_ScrollableFrame import HY127_ScrollableFrame
except ImportError:
    from HY127_ScrollableFrame import HY127_ScrollableFrame


EVENT_DROPDOWNSELECT_CHANGED = "<<HY127DropdownSelectChanged>>"
EVENT_DROPDOWNSELECT_OPENED = "<<HY127DropdownSelectOpened>>"
EVENT_DROPDOWNSELECT_CLOSED = "<<HY127DropdownSelectClosed>>"


def _normalize_item(raw, default_selected=False):
    """把 str / dict 统一为标准结构。"""
    if isinstance(raw, dict):
        text = str(raw.get("text", raw.get("label", "")))
        selected = bool(raw.get("selected", raw.get("checked", default_selected)))
        user_data = raw.get("user_data", raw.get("value", raw.get("data", text)))
        keywords = raw.get("keywords", "")
        enabled = not bool(raw.get("disabled", False))
        return {
            "text": text,
            "selected": selected,
            "user_data": user_data,
            "keywords": keywords,
            "enabled": enabled,
        }
    text = str(raw)
    return {
        "text": text,
        "selected": bool(default_selected),
        "user_data": raw,
        "keywords": "",
        "enabled": True,
    }


class _DropdownButtonProxy:
    """兼容代理：为外部代码暴露原 ttk.Button 的最小接口。"""

    def __init__(self, owner):
        self._owner = owner

    def configure(self, **kwargs):
        if "state" in kwargs:
            self._owner._set_btn_state(kwargs.pop("state"))
        if "style" in kwargs:
            kwargs.pop("style")  # 已不使用 ttk 样式
        return None

    config = configure

    def cget(self, key):
        if key == "state":
            return DISABLED if self._owner._state == DISABLED else NORMAL
        return None


class HY127_DropdownSelect(ttk.Frame):
    """
    可搜索的下拉选择组件。

    参数:
        master: 父容器
        items / values: 初始数据，元素可为 str 或 dict
            dict 支持键:
                text / label
                selected / checked
                user_data / value / data
                keywords
                disabled
        multiselect: 是否多选，False 时退化为单选下拉
        searchable: 是否启用搜索框
        bootstyle: 主题样式
        font: 字体
        command: 选中变化后的回调，无参数
        on_selection_changed: 同 command，无参数
        placeholder: 无选中时的显示文本
        separator: 多选模式下显示文本分隔符
        max_display_items: 折叠态最多展示多少个标签，超出后显示 `+N`
        width / height: 控件宽高
        state: NORMAL / DISABLED / READONLY
        dropdown_height: 弹出层高度
        dropdown_width: 弹出层宽度，默认跟随控件宽度
        auto_close_on_select:
            单选默认 True，多选默认 False
    """

    def __init__(
        self,
        master=None,
        items=None,
        values=None,
        multiselect=True,
        searchable=True,
        bootstyle=PRIMARY,
        font=None,
        command=None,
        on_selection_changed=None,
        placeholder="请选择",
        separator=", ",
        max_display_items=2,
        width=None,
        height=None,
        state=READONLY,
        dropdown_height=260,
        dropdown_width=None,
        auto_close_on_select=None,
        button_size=None,
        triangle_scale=0.42,
        **kwargs,
    ):
        super().__init__(master, **kwargs)

        self._bootstyle = bootstyle
        self._font = font
        self._command = command
        self._on_selection_changed = on_selection_changed
        self._multiselect = bool(multiselect)
        self._searchable = bool(searchable)
        self._placeholder = placeholder
        self._separator = separator
        self._max_display_items = max(1, int(max_display_items))
        self._width = width
        self._height = height
        self._state = state
        self._dropdown_height = max(120, int(dropdown_height))
        self._dropdown_width = dropdown_width
        self._auto_close_on_select = (
            bool(auto_close_on_select)
            if auto_close_on_select is not None
            else (not self._multiselect)
        )

        self._items = []
        self._display_var = tk.StringVar()
        self._search_var = tk.StringVar()
        self._single_choice_var = tk.StringVar()

        self._popup = None
        self._popup_body = None
        self._popup_scroll = None
        self._popup_search_entry = None
        self._popup_rows = []
        self._outside_click_binding = None
        self._escape_binding = None
        self._search_placeholder = "搜索筛选..."
        self._search_placeholder_active = False
        self._hover_row_bg = None
        self._active_row_index = None
        self._popup_widgets = []

        self._visuals_refresh_pending = False
        self._suppress_host_configure = False
        self._last_configure_width = None
        self._chip_relayout_pending = False

        self._style_engine = None
        self._entry_style = None
        self._button_style = None
        self._field_bg = "#ffffff"
        self._field_fg = "#000000"
        self._field_border = "#cccccc"
        self._placeholder_fg = "#7a7a7a"
        self._disabled_bg = "#efefef"
        self._disabled_fg = "#8a8a8a"
        self._search_placeholder_fg = "#8a8a8a"
        self._chip_bg = "#dff5ea"
        self._chip_fg = "#1f6f53"
        self._chip_border = "#84cfab"
        self._summary_bg = "#eef2f7"
        self._summary_fg = "#48566a"
        self._summary_border = "#cad3df"
        self._surface_bg = "#f8f9fa"

        # 右侧下拉按钮：默认正方形（按字段高度自适应），button_size 显式传入则固定
        self._btn_size_explicit = button_size
        self._btn_size = int(button_size) if button_size else 28
        self._btn_auto_square = button_size is None
        self._triangle_scale = max(0.2, min(0.8, float(triangle_scale)))
        self._btn_canvas = None
        self._btn_triangle = None
        self._btn_pressed = False

        self._create_widgets()
        self._update_theme_colors()
        self.set_items(items if items is not None else (values or []), silent=True)
        self._apply_state()

        if self._width is not None:
            super().configure(width=self._width)
        if self._height is not None:
            super().configure(height=self._height)
            self.pack_propagate(False)
            self.grid_propagate(False)
            self._field_frame.configure(height=self._height)
            self._field_frame.grid_propagate(False)

        self.bind("<Configure>", self._on_host_configure)
        self.bind("<Destroy>", self._on_destroy, add="+")
        self.bind("<<ThemeChanged>>", self._on_theme_changed, add="+")

    def _create_widgets(self):
        self._button_style = f"{self._bootstyle}.TButton" if self._bootstyle else "TButton"
        self._entry_style = f"{self._bootstyle}.TEntry" if self._bootstyle else "TEntry"

        self._field_frame = tk.Frame(self, bd=0, highlightthickness=1, cursor="hand2")
        self._field_frame.pack(fill=BOTH, expand=YES)
        self._field_frame.grid_columnconfigure(0, weight=1)
        self._field_frame.grid_columnconfigure(1, weight=0, minsize=self._btn_size)
        self._field_frame.grid_rowconfigure(0, weight=1)

        self._chip_area = tk.Frame(self._field_frame, bd=0, padx=6, pady=4, cursor="hand2")
        self._chip_area.grid(row=0, column=0, sticky="nsew")

        self._btn_frame = tk.Frame(self._field_frame, width=self._btn_size, bd=0)
        self._btn_frame.grid(row=0, column=1, sticky="nsew")
        self._btn_frame.pack_propagate(False)
        self._btn_frame.grid_propagate(False)

        # 用 Canvas 自绘正方形下拉按钮（背景色 + 居中三角形），保证三角形大小可控
        self._btn_canvas = tk.Canvas(
            self._btn_frame,
            bd=0,
            highlightthickness=0,
            takefocus=0,
            cursor="hand2",
        )
        self._btn_canvas.pack(fill=BOTH, expand=YES)
        # 兼容旧代码：self.button 仍指向一个具有 configure(state=...) 接口的对象
        self.button = _DropdownButtonProxy(self)

        self._btn_canvas.bind("<Configure>", self._on_btn_configure)
        self._btn_canvas.bind("<Button-1>", self._on_btn_press)
        self._btn_canvas.bind("<ButtonRelease-1>", self._on_btn_release)
        self._btn_canvas.bind("<Enter>", self._on_btn_enter)
        self._btn_canvas.bind("<Leave>", self._on_btn_leave)
        # 字段区域 <Configure>：用于把按钮做成正方形
        self._field_frame.bind("<Configure>", self._on_field_frame_configure, add="+")

        self._bind_open_click(self)
        self._bind_open_click(self._field_frame)
        self._bind_open_click(self._chip_area)

        self.bind("<Down>", self._on_open_key)
        self.bind("<Return>", self._on_open_key)
        self.bind("<space>", self._on_open_key)
        self._field_frame.bind("<Down>", self._on_open_key)
        self._field_frame.bind("<Return>", self._on_open_key)
        self._field_frame.bind("<space>", self._on_open_key)

    def _bind_open_click(self, widget):
        widget.bind("<Button-1>", self._on_entry_click, add="+")

    # ---------------- 下拉按钮（Canvas 自绘） ----------------
    def _on_field_frame_configure(self, event=None):
        if not self._btn_auto_square:
            return
        try:
            h = self._field_frame.winfo_height()
        except tk.TclError:
            return
        if h <= 1:
            return
        # 字段外有 1px 高亮边框，正方形按钮按内部高度对齐
        size = max(20, h - 2)
        if size != self._btn_size:
            self._btn_size = size
            try:
                self._field_frame.grid_columnconfigure(1, weight=0, minsize=size)
                self._btn_frame.configure(width=size)
            except tk.TclError:
                pass

    def _on_btn_configure(self, event=None):
        self._redraw_btn()

    def _on_btn_enter(self, event=None):
        if self._state == DISABLED:
            return
        self._redraw_btn(state="hover")

    def _on_btn_leave(self, event=None):
        self._btn_pressed = False
        if self._state == DISABLED:
            self._redraw_btn(state="disabled")
        else:
            self._redraw_btn(state="normal")

    def _on_btn_press(self, event=None):
        if self._state == DISABLED:
            return
        self._btn_pressed = True
        self._redraw_btn(state="pressed")

    def _on_btn_release(self, event=None):
        if self._state == DISABLED:
            return
        was_pressed = self._btn_pressed
        self._btn_pressed = False
        self._redraw_btn(state="hover")
        if was_pressed:
            try:
                # 仅当 release 仍在按钮范围内才触发
                x, y = event.x, event.y
                w = self._btn_canvas.winfo_width()
                h = self._btn_canvas.winfo_height()
                if 0 <= x <= w and 0 <= y <= h:
                    self._toggle_dropdown()
            except (tk.TclError, AttributeError):
                self._toggle_dropdown()

    def _set_btn_state(self, state):
        # 由 _DropdownButtonProxy.configure(state=...) 调用
        self._redraw_btn(state="disabled" if state == DISABLED else "normal")

    def _redraw_btn(self, state=None):
        if self._btn_canvas is None:
            return
        try:
            w = self._btn_canvas.winfo_width()
            h = self._btn_canvas.winfo_height()
        except tk.TclError:
            return
        if w <= 1 or h <= 1:
            return
        if state is None:
            state = "disabled" if self._state == DISABLED else "normal"

        bg = {
            "normal": getattr(self, "_btn_bg_normal", "#0d6efd"),
            "hover": getattr(self, "_btn_bg_hover", "#0a58ca"),
            "pressed": getattr(self, "_btn_bg_pressed", "#084298"),
            "disabled": getattr(self, "_btn_bg_disabled", "#adb5bd"),
        }.get(state, getattr(self, "_btn_bg_normal", "#0d6efd"))
        fg = getattr(self, "_btn_fg", "#ffffff")

        try:
            self._btn_canvas.configure(bg=bg)
            self._btn_canvas.delete("all")
        except tk.TclError:
            return

        # 居中绘制三角形
        size = min(w, h) * self._triangle_scale
        cx = w / 2.0
        cy = h / 2.0
        # 三角形高度按等边比例 ≈ size * 0.866，并向上轻微偏移让视觉重心居中
        half_w = size / 2.0
        tri_h = size * 0.78
        offset_y = tri_h * 0.18  # 向下微调让视觉重心更稳
        x1, y1 = cx - half_w, cy - tri_h / 2.0 + offset_y
        x2, y2 = cx + half_w, cy - tri_h / 2.0 + offset_y
        x3, y3 = cx,         cy + tri_h / 2.0 + offset_y

        self._btn_triangle = self._btn_canvas.create_polygon(
            x1, y1, x2, y2, x3, y3,
            fill=fg,
            outline=fg,
            width=1,
            joinstyle="round",
        )

    def _get_style_instance(self):
        try:
            self._style_engine = ttk.Style.get_instance()
        except Exception:
            self._style_engine = ttk.Style()
        return self._style_engine

    def _lookup_style(self, style_name, option, fallback=None):
        style = self._get_style_instance()
        try:
            value = style.lookup(style_name, option)
            if value not in ("", None):
                return value
        except Exception:
            pass
        return fallback

    def _hex_to_rgb(self, color):
        try:
            r, g, b = self.winfo_rgb(color)
            return (r // 256, g // 256, b // 256)
        except tk.TclError:
            return (255, 255, 255)

    def _rgb_to_hex(self, rgb):
        r, g, b = rgb
        return f"#{int(max(0, min(255, r))):02x}{int(max(0, min(255, g))):02x}{int(max(0, min(255, b))):02x}"

    def _mix_color(self, c1, c2, weight=0.5):
        weight = max(0.0, min(1.0, float(weight)))
        r1, g1, b1 = self._hex_to_rgb(c1)
        r2, g2, b2 = self._hex_to_rgb(c2)
        return self._rgb_to_hex(
            (
                r1 * (1.0 - weight) + r2 * weight,
                g1 * (1.0 - weight) + g2 * weight,
                b1 * (1.0 - weight) + b2 * weight,
            )
        )

    def _shift_color(self, color, amount=0.1):
        r, g, b = self._hex_to_rgb(color)
        if amount >= 0:
            r = r + (255 - r) * amount
            g = g + (255 - g) * amount
            b = b + (255 - b) * amount
        else:
            factor = 1.0 + amount
            r = r * factor
            g = g * factor
            b = b * factor
        return self._rgb_to_hex((r, g, b))

    def _luminance(self, color):
        r, g, b = self._hex_to_rgb(color)
        return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0

    def _is_dark_theme(self):
        style = self._get_style_instance()
        bg = self._lookup_style("TFrame", "background", None)
        if not bg:
            try:
                bg = style.colors.bg
            except Exception:
                bg = "#ffffff"
        return self._luminance(bg) < 0.5

    def _resolve_bootstyle_color(self):
        style = self._get_style_instance()
        try:
            colors = style.colors
            color_name = str(self._bootstyle).split("-")[0]
            return getattr(colors, color_name, colors.primary)
        except Exception:
            return "#0d6efd"

    def _update_theme_colors(self):
        style = self._get_style_instance()
        self._entry_style = f"{self._bootstyle}.TEntry" if self._bootstyle else "TEntry"
        self._button_style = f"{self._bootstyle}.TButton" if self._bootstyle else "TButton"

        try:
            colors = style.colors
            theme_bg = getattr(colors, "bg", "#ffffff")
            theme_fg = getattr(colors, "fg", "#212529")
            border = getattr(colors, "border", self._mix_color(theme_fg, theme_bg, 0.75))
            select_fg = getattr(colors, "selectfg", "#ffffff")
        except Exception:
            theme_bg = "#ffffff"
            theme_fg = "#212529"
            border = "#ced4da"
            select_fg = "#ffffff"

        field_bg = self._lookup_style(self._entry_style, "fieldbackground", None)
        if not field_bg:
            field_bg = self._lookup_style("TEntry", "fieldbackground", theme_bg)
        field_fg = self._lookup_style(self._entry_style, "foreground", None)
        if not field_fg:
            field_fg = self._lookup_style("TEntry", "foreground", theme_fg)

        self._surface_bg = self._mix_color(theme_bg, field_bg, 0.50)
        self._field_bg = field_bg
        self._field_fg = field_fg
        self._field_border = self._lookup_style(self._entry_style, "bordercolor", None) or border
        self._placeholder_fg = self._mix_color(field_fg, field_bg, 0.55)
        self._search_placeholder_fg = self._mix_color(field_fg, field_bg, 0.60)
        self._disabled_bg = self._mix_color(field_bg, theme_bg, 0.45)
        self._disabled_fg = self._mix_color(field_fg, field_bg, 0.65)

        accent = self._resolve_bootstyle_color()
        dark_theme = self._is_dark_theme()
        self._hover_row_bg = self._mix_color(field_bg, accent, 0.10 if dark_theme else 0.06)
        if dark_theme:
            self._chip_bg = self._mix_color(field_bg, accent, 0.35)
            self._chip_fg = select_fg
            self._chip_border = self._mix_color(field_bg, accent, 0.55)
            self._summary_bg = self._mix_color(field_bg, theme_fg, 0.18)
            self._summary_fg = self._mix_color(theme_fg, field_bg, 0.10)
            self._summary_border = self._mix_color(field_bg, theme_fg, 0.30)
        else:
            self._chip_bg = self._mix_color(field_bg, accent, 0.18)
            self._chip_fg = self._shift_color(accent, -0.35)
            self._chip_border = self._mix_color(field_bg, accent, 0.42)
            self._summary_bg = self._mix_color(field_bg, theme_fg, 0.08)
            self._summary_fg = self._mix_color(theme_fg, field_bg, 0.18)
            self._summary_border = self._mix_color(field_bg, theme_fg, 0.20)

        # 下拉按钮颜色：默认填充 = 主色；hover/pressed = 主色微暗；禁用 = 灰
        self._btn_bg_normal = accent
        self._btn_bg_hover = self._shift_color(accent, -0.10)
        self._btn_bg_pressed = self._shift_color(accent, -0.20)
        self._btn_bg_disabled = self._mix_color(accent, theme_bg, 0.65)
        self._btn_fg = "#ffffff"

        self.button.configure(style=self._button_style)
        self._redraw_btn()
        self._refresh_field_visuals()
        self._refresh_search_placeholder_visual()

        if self._popup and self._popup.winfo_exists():
            self._render_popup_items()

    def _refresh_field_visuals(self):
        if getattr(self, "_visuals_refresh_pending", False):
            return
        self._visuals_refresh_pending = True
        try:
            self.after_idle(self._do_refresh_field_visuals)
        except tk.TclError:
            self._visuals_refresh_pending = False

    def _do_refresh_field_visuals(self):
        self._visuals_refresh_pending = False
        try:
            if not self._chip_area.winfo_exists():
                return
        except tk.TclError:
            return

        bg = self._disabled_bg if self._state == DISABLED else self._field_bg
        fg = self._disabled_fg if self._state == DISABLED else self._field_fg
        border = self._field_border if self._state != DISABLED else self._mix_color(self._field_border, bg, 0.50)

        self._field_frame.configure(bg=bg, highlightbackground=border, highlightcolor=border)
        self._chip_area.configure(bg=bg)
        self._btn_frame.configure(bg=bg)
        self._display_var.set(self._build_display_text())

        self._suppress_host_configure = True
        try:
            for child in self._chip_area.winfo_children():
                try:
                    child.destroy()
                except tk.TclError:
                    pass

            selected = [(i, item) for i, item in enumerate(self._items) if item["selected"]]
            if not selected:
                placeholder = tk.Label(
                    self._chip_area,
                    text=self._placeholder,
                    bg=bg,
                    fg=self._placeholder_fg if self._state != DISABLED else self._disabled_fg,
                    font=self._font,
                    bd=0,
                    anchor="w",
                    padx=2,
                    cursor="hand2" if self._state != DISABLED else "arrow",
                )
                placeholder.pack(side=LEFT, fill=X, expand=YES)
                if self._state != DISABLED:
                    self._bind_open_click(placeholder)
                return

            for index, item in selected:
                self._create_chip(item["text"], index=index, removable=(self._state != DISABLED))

            filler = tk.Frame(self._chip_area, bg=bg, bd=0, highlightthickness=0)
            filler.pack(side=LEFT, fill=BOTH, expand=YES)
            if self._state != DISABLED:
                self._bind_open_click(filler)
        finally:
            self.after_idle(self._collapse_then_release)

    def _collapse_then_release(self):
        try:
            self._collapse_chips_to_fit()
        finally:
            self._suppress_host_configure = False
            try:
                if self.winfo_exists():
                    self._last_configure_width = self.winfo_width()
            except tk.TclError:
                pass

    def _collapse_chips_to_fit(self):
        """根据 chip_area 实际可用宽度动态折叠标签为 '+N'，宽度足够时全部展示。"""
        try:
            if not self._chip_area.winfo_exists():
                return
        except tk.TclError:
            return

        selected = [(i, item) for i, item in enumerate(self._items) if item["selected"]]
        if not selected:
            return

        try:
            self._chip_area.update_idletasks()
            avail = self._chip_area.winfo_width() - 4
        except tk.TclError:
            return

        if avail <= 0:
            return

        chips = [c for c in self._chip_area.winfo_children() if isinstance(c, tk.Frame) and c.winfo_children()]
        if not chips:
            return

        widths = []
        for chip in chips:
            try:
                w = chip.winfo_reqwidth() + 4
            except tk.TclError:
                w = 0
            widths.append(w)

        total = sum(widths)
        if total <= avail:
            return

        summary_w = 38
        visible_count = 0
        used = 0
        for w in widths:
            if used + w + summary_w <= avail:
                used += w
                visible_count += 1
            else:
                break

        if visible_count >= len(selected):
            return

        bg = self._disabled_bg if self._state == DISABLED else self._field_bg
        for child in self._chip_area.winfo_children():
            try:
                child.destroy()
            except tk.TclError:
                pass

        for index, item in selected[:visible_count]:
            self._create_chip(item["text"], index=index, removable=(self._state != DISABLED))

        hidden_count = len(selected) - visible_count
        self._create_chip(f"+{hidden_count}", index=None, removable=False, summary=True)

        filler = tk.Frame(self._chip_area, bg=bg, bd=0, highlightthickness=0)
        filler.pack(side=LEFT, fill=BOTH, expand=YES)
        if self._state != DISABLED:
            self._bind_open_click(filler)

    def _create_chip(self, text, index=None, removable=True, summary=False):
        host_bg = self._disabled_bg if self._state == DISABLED else self._field_bg
        chip_bg = self._summary_bg if summary else self._chip_bg
        chip_fg = self._summary_fg if summary else self._chip_fg
        chip_border = self._summary_border if summary else self._chip_border

        chip = tk.Frame(
            self._chip_area,
            bg=chip_bg,
            bd=0,
            highlightthickness=0,
            cursor="hand2" if self._state != DISABLED else "arrow",
        )
        chip.pack(side=LEFT, padx=(0, 4), pady=1)

        lbl = tk.Label(
            chip,
            text=text,
            bg=chip_bg,
            fg=chip_fg,
            font=self._font,
            bd=0,
            padx=8,
            pady=2,
            cursor="hand2" if self._state != DISABLED else "arrow",
        )
        lbl.pack(side=LEFT)

        if self._state != DISABLED:
            self._bind_open_click(chip)
            self._bind_open_click(lbl)

        if removable and index is not None:
            close_label = tk.Label(
                chip,
                text="x",
                bg=chip_bg,
                fg=chip_fg,
                font=self._font,
                bd=0,
                padx=5,
                pady=2,
                cursor="hand2",
            )
            close_label.pack(side=LEFT)
            close_label.bind("<Button-1>", lambda e, i=index: self._remove_selected_index(i))
            close_label.bind("<Enter>", lambda e, w=close_label: w.configure(bg=self._shift_color(chip_bg, -0.08)))
            close_label.bind("<Leave>", lambda e, w=close_label, c=chip_bg: w.configure(bg=c))

        spacer = tk.Frame(self._chip_area, bg=host_bg, bd=0)
        spacer.pack_forget()

    def _remove_selected_index(self, index):
        if self._state == DISABLED:
            return "break"
        if not (0 <= index < len(self._items)):
            return "break"
        self._items[index]["selected"] = False
        if not self._multiselect:
            for i, item in enumerate(self._items):
                if i != index:
                    item["selected"] = False
        self._refresh_field_visuals()
        if self._popup and self._popup.winfo_exists():
            self._render_popup_items()
        self._emit_changed()
        return "break"

    def _build_display_text(self):
        selected_texts = self.get_selected_texts()
        if not selected_texts:
            return self._placeholder
        if self._multiselect and len(selected_texts) > self._max_display_items:
            visible = selected_texts[: self._max_display_items]
            hidden = len(selected_texts) - len(visible)
            return self._separator.join(visible) + f"{self._separator}+{hidden}"
        return self._separator.join(selected_texts)

    def _on_theme_changed(self, event=None):
        self._update_theme_colors()

    def _is_search_placeholder_visible(self):
        return self._search_placeholder_active

    def _activate_search_placeholder(self):
        if self._popup_search_entry is None:
            return
        self._search_placeholder_active = True
        self._search_var.set(self._search_placeholder)
        self._refresh_search_placeholder_visual()

    def _deactivate_search_placeholder(self):
        if self._popup_search_entry is None:
            return
        if self._search_placeholder_active:
            self._search_placeholder_active = False
            self._search_var.set("")
            self._refresh_search_placeholder_visual()

    def _refresh_search_placeholder_visual(self):
        if self._popup_search_entry is None:
            return
        try:
            self._popup_search_entry.configure(
                fg=self._search_placeholder_fg if self._search_placeholder_active else self._field_fg
            )
        except tk.TclError:
            pass

    def _on_search_focus_in(self, event=None):
        self._deactivate_search_placeholder()

    def _on_search_focus_out(self, event=None):
        if self._popup_search_entry is None:
            return
        if not self._search_var.get().strip():
            self._activate_search_placeholder()

    def _focus_search_entry(self):
        """延迟聚焦搜索框，确保 overrideredirect 窗口在 Windows 上能接收键盘输入。"""
        try:
            if self._popup_search_entry and self._popup_search_entry.winfo_exists():
                self._popup_search_entry.focus_force()
                self._popup_search_entry.selection_range(0, END)
                self._popup_search_entry.icursor(END)
        except tk.TclError:
            pass

    def _get_search_keyword(self):
        if self._search_placeholder_active:
            return ""
        return self._search_var.get().strip().lower()

    def _set_active_row(self, index):
        self._active_row_index = index
        for pos, info in enumerate(self._popup_widgets):
            row = info["row"]
            bg = self._hover_row_bg if pos == index else self._surface_bg
            try:
                row.configure(bg=bg, highlightbackground=bg, highlightcolor=bg)
            except tk.TclError:
                pass
            for widget in info["widgets"]:
                try:
                    widget.configure(bg=bg)
                except Exception:
                    pass

    def _move_active_row(self, step):
        if not self._popup_widgets:
            return "break"
        if self._active_row_index is None:
            next_index = 0 if step >= 0 else len(self._popup_widgets) - 1
        else:
            next_index = max(0, min(len(self._popup_widgets) - 1, self._active_row_index + step))
        self._set_active_row(next_index)
        try:
            self._popup_widgets[next_index]["row"].focus_set()
        except tk.TclError:
            pass
        return "break"

    def _activate_current_row(self, event=None):
        if self._active_row_index is None or not self._popup_widgets:
            return "break"
        action = self._popup_widgets[self._active_row_index]["action"]
        if action:
            action()
        return "break"

    def _bind_popup_row_events(self, row, index, action=None):
        row.bind("<Enter>", lambda e, i=index: self._set_active_row(i), add="+")
        row.bind("<Button-1>", lambda e, fn=action: self._invoke_row_action(fn), add="+")
        row.bind("<Up>", lambda e: self._move_active_row(-1), add="+")
        row.bind("<Down>", lambda e: self._move_active_row(1), add="+")
        row.bind("<Return>", self._activate_current_row, add="+")
        row.bind("<space>", self._activate_current_row, add="+")

    def _invoke_row_action(self, action):
        if action:
            action()
        return "break"

    def _on_entry_click(self, event=None):
        if self._state == DISABLED:
            return "break"
        self._toggle_dropdown()
        return "break"

    def _on_open_key(self, event=None):
        if self._state == DISABLED:
            return "break"
        if not self._popup or not self._popup.winfo_exists():
            self._open_dropdown()
        return "break"

    def _on_host_configure(self, event=None):
        if event is not None and getattr(event, "widget", None) is not self:
            return

        if self._popup and self._popup.winfo_exists():
            self.after_idle(self._reposition_popup)

        if getattr(self, "_suppress_host_configure", False):
            return

        new_width = getattr(event, "width", None) if event is not None else None
        if new_width is not None and new_width == getattr(self, "_last_configure_width", None):
            return
        if new_width is not None:
            self._last_configure_width = new_width

        self._schedule_chip_relayout()

    def _schedule_chip_relayout(self):
        if getattr(self, "_chip_relayout_pending", False):
            return
        self._chip_relayout_pending = True
        self.after(30, self._do_chip_relayout)

    def _do_chip_relayout(self):
        self._chip_relayout_pending = False
        try:
            if not self._chip_area.winfo_exists():
                return
        except tk.TclError:
            return
        self._refresh_field_visuals()

    def _on_destroy(self, event=None):
        if event is not None and event.widget is not self:
            return
        self._close_dropdown(emit_event=False)

    def _toggle_dropdown(self):
        if self._popup and self._popup.winfo_exists():
            self._close_dropdown()
        else:
            self._open_dropdown()

    def _open_dropdown(self):
        if self._state == DISABLED:
            return
        if self._popup and self._popup.winfo_exists():
            self._reposition_popup()
            return

        self.update_idletasks()

        popup = tk.Toplevel(self)
        popup.withdraw()
        popup.overrideredirect(True)
        popup.transient(self.winfo_toplevel())

        body = tk.Frame(
            popup,
            bg=self._surface_bg,
            bd=0,
            highlightthickness=1,
            highlightbackground=self._field_border,
            highlightcolor=self._field_border,
            padx=6,
            pady=6,
        )
        body.pack(fill=BOTH, expand=YES)

        if self._searchable:
            search_holder = tk.Frame(body, bg=self._surface_bg, bd=0, highlightthickness=0)
            search_holder.pack(fill=X, pady=(0, 4))
            self._popup_search_entry = tk.Entry(
                search_holder,
                textvariable=self._search_var,
                font=self._font,
                bd=0,
                relief="flat",
                highlightthickness=0,
                bg=self._surface_bg,
                fg=self._field_fg,
                insertbackground=self._field_fg,
            )
            self._popup_search_entry.pack(fill=X, padx=4, pady=2)
            self._popup_search_entry.bind("<KeyRelease>", self._on_search_changed)
            self._popup_search_entry.bind("<Escape>", self._on_popup_escape)
            self._popup_search_entry.bind("<Down>", self._focus_first_item)
            self._popup_search_entry.bind("<Up>", lambda e: self._move_active_row(-1))
            self._popup_search_entry.bind("<Return>", self._activate_current_row)
            self._popup_search_entry.bind("<FocusIn>", self._on_search_focus_in, add="+")
            self._popup_search_entry.bind("<FocusOut>", self._on_search_focus_out, add="+")
        else:
            self._popup_search_entry = None

        scroll_host = ttk.Frame(body, height=self._dropdown_height)
        scroll_host.pack(fill=BOTH, expand=YES)
        scroll_host.pack_propagate(False)

        self._popup_scroll = HY127_ScrollableFrame(scroll_host, autohide=True)
        self._popup_scroll.pack(fill=BOTH, expand=YES)

        self._popup = popup
        self._popup_body = body
        self._render_popup_items()
        self._reposition_popup()
        popup.deiconify()
        popup.lift()
        popup.focus_force()

        root = self.winfo_toplevel()
        self._outside_click_binding = root.bind("<ButtonPress-1>", self._handle_global_click, add="+")
        self._escape_binding = root.bind("<Escape>", self._on_popup_escape, add="+")

        try:
            self.event_generate(EVENT_DROPDOWNSELECT_OPENED, when="tail")
        except tk.TclError:
            pass

        if self._popup_search_entry is not None:
            self._activate_search_placeholder()
            self.after(20, self._focus_search_entry)
        else:
            popup.focus_force()

    def _close_dropdown(self, emit_event=True):
        root = None
        try:
            root = self.winfo_toplevel()
        except tk.TclError:
            root = None

        if root is not None and self._outside_click_binding is not None:
            try:
                root.unbind("<ButtonPress-1>", self._outside_click_binding)
            except tk.TclError:
                pass
            self._outside_click_binding = None

        if root is not None and self._escape_binding is not None:
            try:
                root.unbind("<Escape>", self._escape_binding)
            except tk.TclError:
                pass
            self._escape_binding = None

        if self._popup is not None:
            try:
                self._popup.destroy()
            except tk.TclError:
                pass

        self._popup = None
        self._popup_body = None
        self._popup_scroll = None
        self._popup_search_entry = None
        self._popup_rows = []
        self._popup_widgets = []
        self._active_row_index = None
        self._search_var.set("")

        if emit_event:
            try:
                self.event_generate(EVENT_DROPDOWNSELECT_CLOSED, when="tail")
            except tk.TclError:
                pass

    def _get_monitor_workarea(self, x, y):
        """返回坐标 (x, y) 所在显示器的工作区 (left, top, right, bottom)。"""
        try:
            import ctypes
            import ctypes.wintypes as wt

            class MONITORINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wt.DWORD),
                    ("rcMonitor", wt.RECT),
                    ("rcWork", wt.RECT),
                    ("dwFlags", wt.DWORD),
                ]

            user32 = ctypes.windll.user32
            user32.MonitorFromPoint.argtypes = [wt.POINT, wt.DWORD]
            user32.MonitorFromPoint.restype = ctypes.c_void_p
            user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(MONITORINFO)]
            user32.GetMonitorInfoW.restype = wt.BOOL

            pt = wt.POINT(int(x), int(y))
            hmon = user32.MonitorFromPoint(pt, 2)
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                return (mi.rcWork.left, mi.rcWork.top, mi.rcWork.right, mi.rcWork.bottom)
        except Exception:
            pass
        return (0, 0, self.winfo_screenwidth(), self.winfo_screenheight())

    def _reposition_popup(self):
        if not self._popup or not self._popup.winfo_exists():
            return

        self.update_idletasks()
        self._popup.update_idletasks()

        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height() + 1
        width = int(self._dropdown_width or max(self.winfo_width(), 180))
        popup_req_height = self._popup.winfo_reqheight()

        mon_left, mon_top, mon_right, mon_bottom = self._get_monitor_workarea(x, y)

        if x + width > mon_right - 8:
            x = max(mon_left + 8, mon_right - width - 8)

        if y + popup_req_height > mon_bottom - 8:
            y = self.winfo_rooty() - popup_req_height - 1
            if y < mon_top + 8:
                y = mon_top + 8

        self._popup.geometry(f"{width}x{popup_req_height}+{x}+{y}")

    def _handle_global_click(self, event):
        if not self._popup or not self._popup.winfo_exists():
            return
        if self._point_in_widget(event.x_root, event.y_root, self):
            return
        if self._point_in_widget(event.x_root, event.y_root, self._popup):
            return
        self._close_dropdown()

    def _point_in_widget(self, x_root, y_root, widget):
        try:
            left = widget.winfo_rootx()
            top = widget.winfo_rooty()
            right = left + widget.winfo_width()
            bottom = top + widget.winfo_height()
            return left <= x_root <= right and top <= y_root <= bottom
        except tk.TclError:
            return False

    def _on_popup_escape(self, event=None):
        self._close_dropdown()
        return "break"

    def _on_search_changed(self, event=None):
        if self._search_placeholder_active:
            return
        self._render_popup_items()

    def _focus_first_item(self, event=None):
        if self._popup_widgets:
            self._set_active_row(0)
            try:
                self._popup_widgets[0]["row"].focus_set()
            except tk.TclError:
                pass
        return "break"

    def _get_filtered_indices(self):
        keyword = self._get_search_keyword()
        if not keyword:
            return list(range(len(self._items)))

        result = []
        for index, item in enumerate(self._items):
            text = str(item["text"]).lower()
            extra = item.get("keywords", "")
            if isinstance(extra, (list, tuple, set)):
                extra = " ".join(str(x) for x in extra)
            extra = str(extra).lower()
            if keyword in text or keyword in extra:
                result.append(index)
        return result

    def _toggle_all(self):
        if self._state == DISABLED or not self._multiselect:
            return
        enabled_indices = [i for i, item in enumerate(self._items) if item.get("enabled", True)]
        if not enabled_indices:
            return
        all_selected = all(self._items[i]["selected"] for i in enabled_indices)
        for i in enabled_indices:
            self._items[i]["selected"] = not all_selected
        self._refresh_field_visuals()
        if self._popup and self._popup.winfo_exists():
            self._render_popup_items()
        self._emit_changed()

    def _render_popup_items(self):
        if not self._popup_scroll:
            return

        host = self._popup_scroll.frame
        for child in host.winfo_children():
            try:
                child.destroy()
            except tk.TclError:
                pass
        self._popup_rows = []
        self._popup_widgets = []
        self._active_row_index = None

        filtered_indices = self._get_filtered_indices()
        selected_indices = self.get_selected_indices()
        self._single_choice_var.set(str(selected_indices[0]) if selected_indices else "")

        if self._multiselect and self._items:
            top_row = tk.Frame(host, bg=self._surface_bg, bd=0, highlightthickness=0)
            top_row.pack(fill=X, padx=2, pady=(1, 4))
            self._popup_rows.append(top_row)

            enabled_indices = [i for i, item in enumerate(self._items) if item.get("enabled", True)]
            checked = bool(enabled_indices) and all(self._items[i]["selected"] for i in enabled_indices)
            total_var = tk.BooleanVar(value=checked)
            total_text = f"全选 ({len(selected_indices)}/{len(self._items)})"
            total_cb = ttk.Checkbutton(
                top_row,
                text=total_text,
                variable=total_var,
                bootstyle=self._bootstyle,
                takefocus=False,
                command=self._toggle_all,
            )
            if self._font is not None:
                try:
                    total_cb.configure(font=self._font)
                except tk.TclError:
                    pass
            if self._state == DISABLED:
                total_cb.configure(state=DISABLED)
            total_cb.pack(fill=X, anchor=W)
            widgets = [total_cb]
            self._popup_widgets.append({"row": top_row, "widgets": widgets, "action": self._toggle_all})
            self._bind_popup_row_events(top_row, len(self._popup_widgets) - 1, self._toggle_all)


        if not filtered_indices:
            lbl = ttk.Label(
                host,
                text="没有匹配项",
                anchor=W,
                bootstyle="secondary",
                font=self._font,
            )
            lbl.pack(fill=X, padx=4, pady=4)
            return

        for index in filtered_indices:
            item = self._items[index]
            row = tk.Frame(host, bg=self._surface_bg, bd=0, highlightthickness=0)
            row.pack(fill=X, padx=2, pady=0)
            self._popup_rows.append(row)

            if self._multiselect:
                var = tk.BooleanVar(value=bool(item["selected"]))
                widget = ttk.Checkbutton(
                    row,
                    text=item["text"],
                    variable=var,
                    bootstyle=self._bootstyle,
                    takefocus=False,
                    command=lambda i=index, v=var: self._on_multi_toggle(i, v),
                )
            else:
                widget = ttk.Radiobutton(
                    row,
                    text=item["text"],
                    value=str(index),
                    variable=self._single_choice_var,
                    bootstyle=self._bootstyle,
                    takefocus=False,
                    command=lambda i=index: self._on_single_select(i),
                )

            if self._font is not None:
                try:
                    widget.configure(font=self._font)
                except tk.TclError:
                    pass

            if not item.get("enabled", True) or self._state == DISABLED:
                widget.configure(state=DISABLED)

            widget.pack(fill=X, anchor=W)
            action = (
                (lambda i=index, v=var: self._on_multi_toggle(i, v)) if self._multiselect
                else (lambda i=index: self._on_single_select(i))
            )
            self._popup_widgets.append({"row": row, "widgets": [widget], "action": action})
            self._bind_popup_row_events(row, len(self._popup_widgets) - 1, action)
            widget.bind("<Enter>", lambda e, pos=len(self._popup_widgets) - 1: self._set_active_row(pos), add="+")
            widget.bind("<Up>", lambda e: self._move_active_row(-1), add="+")
            widget.bind("<Down>", lambda e: self._move_active_row(1), add="+")
            widget.bind("<Return>", self._activate_current_row, add="+")
            widget.bind("<space>", self._activate_current_row, add="+")

        if self._popup_widgets:
            self._set_active_row(0)

    def _on_multi_toggle(self, index, var):
        if self._state == DISABLED:
            return
        if not (0 <= index < len(self._items)):
            return
        self._items[index]["selected"] = bool(var.get())
        self._refresh_field_visuals()
        self._emit_changed()
        if self._auto_close_on_select:
            self._close_dropdown()

    def _on_single_select(self, index):
        if self._state == DISABLED:
            return
        self._set_selected_indices_internal([index], silent=False)
        if self._auto_close_on_select:
            self._close_dropdown()

    def _emit_changed(self):
        self._refresh_field_visuals()

        if self._command:
            self._command()
        if self._on_selection_changed:
            self._on_selection_changed()

        for event_name in (EVENT_DROPDOWNSELECT_CHANGED, "<<ComboboxSelected>>"):
            try:
                self.event_generate(event_name, when="tail")
            except tk.TclError:
                pass

    def _normalize_single_mode_selection(self):
        if self._multiselect:
            return
        found = False
        for item in self._items:
            if item["selected"]:
                if not found:
                    found = True
                else:
                    item["selected"] = False

    def _apply_state(self):
        if self._state == DISABLED:
            self.button.configure(state=DISABLED)
            self._close_dropdown(emit_event=False)
        else:
            self.button.configure(state=NORMAL)
        self._refresh_field_visuals()

    def _resolve_matches(self, values):
        matches = []
        for raw in values:
            if isinstance(raw, int):
                if 0 <= raw < len(self._items):
                    matches.append(raw)
                continue

            for index, item in enumerate(self._items):
                if raw == item["user_data"] or raw == item["text"]:
                    matches.append(index)
                    break
        return matches

    def _set_selected_indices_internal(self, indices, silent=False):
        picked = []
        for idx in indices:
            if 0 <= idx < len(self._items):
                picked.append(idx)

        if self._multiselect:
            selected_set = set(picked)
            for index, item in enumerate(self._items):
                item["selected"] = index in selected_set
        else:
            first_index = picked[0] if picked else None
            for index, item in enumerate(self._items):
                item["selected"] = (index == first_index)

        self._refresh_field_visuals()

        if self._popup and self._popup.winfo_exists():
            self._render_popup_items()

        if not silent:
            self._emit_changed()

    def set_items(self, items, silent=False):
        self._items = [_normalize_item(x) for x in items]
        self._normalize_single_mode_selection()
        self._refresh_field_visuals()
        if self._popup and self._popup.winfo_exists():
            self._render_popup_items()
        if not silent:
            self._emit_changed()

    def get_items(self):
        return [
            {
                "text": item["text"],
                "selected": bool(item["selected"]),
                "user_data": item["user_data"],
                "keywords": item.get("keywords", ""),
                "enabled": bool(item.get("enabled", True)),
            }
            for item in self._items
        ]

    def append_item(self, text, selected=False, user_data=None, keywords="", enabled=True, silent=False):
        item = {
            "text": text,
            "selected": selected,
            "user_data": text if user_data is None else user_data,
            "keywords": keywords,
            "enabled": enabled,
        }
        items = self.get_items()
        items.append(item)
        self.set_items(items, silent=silent)

    def remove_item(self, index, silent=False):
        items = self.get_items()
        if 0 <= index < len(items):
            del items[index]
            self.set_items(items, silent=silent)

    def clear(self, silent=False):
        self.set_items([], silent=silent)

    def get_selected_indices(self):
        return [index for index, item in enumerate(self._items) if item["selected"]]

    def get_selected_items(self):
        return [item for item in self.get_items() if item["selected"]]

    def get_selected_texts(self):
        return [item["text"] for item in self._items if item["selected"]]

    def get_selected_values(self):
        return [item["user_data"] for item in self._items if item["selected"]]

    def get_value(self):
        values = self.get_selected_values()
        if self._multiselect:
            return values
        return values[0] if values else None

    def get_display_text(self):
        return self._display_var.get()

    def get(self):
        texts = self.get_selected_texts()
        if self._multiselect:
            return texts
        return texts[0] if texts else ""

    def set_selected_indices(self, indices, silent=False):
        self._set_selected_indices_internal(indices, silent=silent)

    def set_selected_texts(self, texts, silent=False):
        if isinstance(texts, str):
            texts = [texts]
        self._set_selected_indices_internal(self._resolve_matches(list(texts)), silent=silent)

    def select_all(self, silent=False):
        if not self._multiselect:
            return
        self._set_selected_indices_internal(list(range(len(self._items))), silent=silent)

    def deselect_all(self, silent=False):
        self._set_selected_indices_internal([], silent=silent)

    def current(self, newindex=None):
        if newindex is None:
            selected = self.get_selected_indices()
            return selected[0] if selected else -1
        self._set_selected_indices_internal([int(newindex)], silent=False)

    def set(self, value, silent=False):
        if value in (None, ""):
            self.deselect_all(silent=silent)
            return

        if isinstance(value, (list, tuple, set)):
            self._set_selected_indices_internal(self._resolve_matches(list(value)), silent=silent)
            return

        if isinstance(value, int):
            self._set_selected_indices_internal([value], silent=silent)
            return

        if self._multiselect and isinstance(value, str) and self._separator in value:
            values = [x.strip() for x in value.split(self._separator) if x.strip()]
            self._set_selected_indices_internal(self._resolve_matches(values), silent=silent)
            return

        self._set_selected_indices_internal(self._resolve_matches([value]), silent=silent)

    def enable(self):
        self._state = READONLY
        self._apply_state()

    def disable(self):
        self._state = DISABLED
        self._apply_state()

    def open_dropdown(self):
        self._open_dropdown()

    def close_dropdown(self):
        self._close_dropdown()

    def configure(self, **kwargs):
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        if "on_selection_changed" in kwargs:
            self._on_selection_changed = kwargs.pop("on_selection_changed")
        if "bootstyle" in kwargs:
            self._bootstyle = kwargs.pop("bootstyle")
            self._update_theme_colors()
        if "font" in kwargs:
            self._font = kwargs.pop("font")
            self._refresh_field_visuals()
            if self._popup and self._popup_search_entry is not None:
                self._popup_search_entry.configure(font=self._font)
            if self._popup and self._popup.winfo_exists():
                self._render_popup_items()
        if "multiselect" in kwargs:
            self._multiselect = bool(kwargs.pop("multiselect"))
            self._auto_close_on_select = not self._multiselect
            self._normalize_single_mode_selection()
            self._refresh_field_visuals()
            if self._popup and self._popup.winfo_exists():
                self._render_popup_items()
        if "searchable" in kwargs:
            self._searchable = bool(kwargs.pop("searchable"))
            if self._popup and self._popup.winfo_exists():
                self._close_dropdown(emit_event=False)
        if "placeholder" in kwargs:
            self._placeholder = kwargs.pop("placeholder")
            self._refresh_field_visuals()
        if "separator" in kwargs:
            self._separator = kwargs.pop("separator")
            self._refresh_field_visuals()
        if "max_display_items" in kwargs:
            self._max_display_items = max(1, int(kwargs.pop("max_display_items")))
            self._refresh_field_visuals()
        if "dropdown_height" in kwargs:
            self._dropdown_height = max(120, int(kwargs.pop("dropdown_height")))
        if "dropdown_width" in kwargs:
            self._dropdown_width = kwargs.pop("dropdown_width")
        if "values" in kwargs:
            self.set_items(kwargs.pop("values"), silent=True)
        if "items" in kwargs:
            self.set_items(kwargs.pop("items"), silent=True)
        if "state" in kwargs:
            self._state = kwargs.pop("state")
            self._apply_state()
        if "width" in kwargs:
            self._width = kwargs["width"]
        if "height" in kwargs:
            self._height = kwargs["height"]
            if hasattr(self, "_field_frame") and self._height is not None:
                self._field_frame.configure(height=self._height)
                self._field_frame.grid_propagate(False)
        super().configure(**kwargs)


if __name__ == "__main__":
    app = ttk.Window(themename="cosmo")
    app.title("HY127_DropdownSelect 演示")
    app.geometry("700x460")

    ttk.Label(app, text="多选 + 搜索 + 标签").pack(anchor=W, padx=12, pady=(12, 4))
    multi = HY127_DropdownSelect(
        app,
        items=[
            {"text": "新客户", "selected": True, "user_data": 1, "keywords": "新客户 customer"},
            {"text": "加急交付", "selected": True, "user_data": 2, "keywords": "加急 urgent"},
            {"text": "需要开票", "selected": False, "user_data": 3, "keywords": "开票 finance"},
            {"text": "上门安装", "selected": True, "user_data": 4, "keywords": "安装 service"},
            {"text": "重点客户", "selected": False, "user_data": 5, "keywords": "重点 vip"},
            {"text": "技术陪跑", "selected": False, "user_data": 6, "keywords": "技术 support"},
        ],
        multiselect=True,
        searchable=True,
        bootstyle="success",
        max_display_items=2,
    )
    multi.pack(fill=X, padx=12)

    ttk.Label(app, text="退化为单选").pack(anchor=W, padx=12, pady=(12, 4))
    single = HY127_DropdownSelect(
        app,
        values=["苹果", "香蕉", "葡萄", "西瓜"],
        multiselect=False,
        searchable=True,
        bootstyle="primary",
    )
    single.pack(fill=X, padx=12)
    single.current(1)

    status = ttk.Label(app, text="", bootstyle="secondary")
    status.pack(fill=X, padx=12, pady=12)

    def refresh_status(event=None):
        status.configure(
            text=f"多选={multi.get_selected_texts()} | 单选={single.get()} | 单选值={single.get_value()}"
        )

    multi.bind(EVENT_DROPDOWNSELECT_CHANGED, refresh_status)
    single.bind(EVENT_DROPDOWNSELECT_CHANGED, refresh_status)
    refresh_status()

    app.mainloop()
