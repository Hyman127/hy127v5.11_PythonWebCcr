# -*- coding: utf-8 -*-
"""
多行复选列表组件 — 可在 ttkbootstrap 窗体上与其它 HY127 组件组合使用。

提供数据读写、全选/反选、回调与虚拟事件，内部滚动区域使用 HY127_ScrollableFrame。
"""
import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

try:
    from .HY127_ScrollableFrame import HY127_ScrollableFrame
except ImportError:
    from HY127_ScrollableFrame import HY127_ScrollableFrame

# 主窗体可 bind 的虚拟事件：任意勾选变化后触发（after 尾部派发）
EVENT_CHECKLIST_CHANGED = "<<HY127CheckListChanged>>"
# 单行勾选状态改变时触发（与 command 同时）
EVENT_ITEM_TOGGLED = "<<HY127CheckListItemToggled>>"
# 行间拖放排序完成后触发（after 尾部派发），可通过 last_reorder 读取 (old_index, new_index)
EVENT_REORDERED = "<<HY127CheckListReordered>>"


def _normalize_item(raw, default_checked=False):
    """将 str / dict 转为统一结构 dict: text, checked, user_data。"""
    if isinstance(raw, dict):
        text = raw.get("text", "")
        checked = bool(raw.get("checked", default_checked))
        user_data = raw.get("user_data", raw.get("data"))
        return {"text": str(text), "checked": checked, "user_data": user_data}
    return {"text": str(raw), "checked": default_checked, "user_data": None}


class HY127_CheckList(ttk.Frame):
    """
    带复选框的多行列表（可滚动）。

    参数:
        master: 父容器
        items: 初始项，元素可为 str 或 dict:
            dict 支持键: text, checked, user_data (或 data)
        bootstyle: Checkbutton 的 bootstyle
        font: 字体，传给 Checkbutton / Label
        command: 勾选变化回调 (index, text, checked, user_data) -> None
        on_selection_changed: 任意勾选变化后的回调，无参数（可与虚拟事件二选一）
        row_padding: 行间垂直 padding
        text_wraplength: 长文本用 Label 折行时的最大宽度（像素）；为 None 且 wrap_to_viewport=False 时
            使用 Checkbutton 单行显示。与 wrap_to_viewport 配合见下。
        wrap_to_viewport: 为 True（默认）时，实际折行宽度为 min(text_wraplength, 视口可用宽度)，
            窗体变窄时仍按可视区域折行，由 HY127_ScrollableFrame 自动出现垂直滚动条；
            为 False 时折行宽度固定为 text_wraplength（窄视口可能出现横向裁切）。
        horizontal_scroll: 为 True 时，内部滚动区不强制把内容区拉到与画布同宽，内容可宽于视区，
            从而在需要时出现横向滚动条（与 HY127_ScrollableFrame.shrink_inner_to_canvas=False 协作）。
        autohide: 是否自动隐藏滚动条（传给 HY127_ScrollableFrame）
        height: 可选，固定整体高度（像素）时设置并配合布局
        takefocus: 是否接收焦点（便于键盘 Space 切换当前行，见 enable_keyboard_toggle）
        show_border: 是否在外层显示 1 像素细边框，默认 True；设为 False 则完全无边框
        border_color: 边框颜色，默认 "#ced4da"（与其它 HY127 组件一致的浅灰描边）
        inner_padding: 边框内侧留白（像素），默认 4。仅在 show_border=True 时生效，
            目的是让复选框/文字与边框之间不至于贴得太紧；设为 0 即可恢复贴边
        display_mode: 显示模式，可选：
            - "checkbox"（默认）: 传统多行复选框样式
            - "tag" / "chip": 每项显示为一个标签 chip，选中态高亮填充并可带 × 关闭，
              未选中态为浅色描边；自动换行排布，点击 chip 切换状态，点击 × 取消勾选。
        tag_show_close: tag 模式下，已选中标签是否显示 × 关闭图标（默认 True）
        tag_hpad: tag 模式下相邻 chip 的水平间距（默认 6）
        tag_vpad: tag 模式下相邻 chip 行的垂直间距（默认 6）
        tag_padx: chip 内文字的左右内边距（默认 8）
        tag_pady: chip 内文字的上下内边距（默认 3）
        allow_reorder: 是否允许通过鼠标拖放重新排序行（默认 False）。
            开启后可在任意显示模式下按住一行/一个 chip 拖动到目标位置释放即可完成排序，
            勾选状态会随项目一起搬迁；排序完成会触发 `<<HY127CheckListReordered>>`
            虚拟事件以及 `on_reorder(old_index, new_index)` 回调。
        on_reorder: 拖放排序完成后的回调，签名 (old_index, new_index) -> None。
            仅在 allow_reorder=True 时生效。
    """

    # 复选框列 + 与文字间距，用于计算折行可用宽度
    _RESERVE_CHECKBOX_COL = 48
    # 鼠标按下后位移超过该像素阈值才进入拖动模式，避免误触
    _DRAG_THRESHOLD = 4

    def __init__(
        self,
        master=None,
        items=None,
        bootstyle=PRIMARY,
        font=None,
        command=None,
        on_selection_changed=None,
        row_padding=2,
        text_wraplength=None,
        wrap_to_viewport=True,
        horizontal_scroll=False,
        autohide=True,
        height=None,
        takefocus=False,
        show_border=True,
        border_color="#ced4da",
        inner_padding=4,
        display_mode="checkbox",
        tag_show_close=True,
        tag_hpad=6,
        tag_vpad=6,
        tag_padx=8,
        tag_pady=3,
        multiselect=True,
        allow_reorder=False,
        on_reorder=None,
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        # multiselect=False 时，复选框消失，每行只是可点击的高亮列表项；
        # 同时只允许有一项处于"选中"状态，便于像普通 ListBox 那样使用。
        self._multiselect = bool(multiselect)
        self._single_index = None  # 单选模式下当前选中行索引

        self._bootstyle = bootstyle
        self._font = font
        self._command = command
        self._on_selection_changed = on_selection_changed
        self._row_padding = row_padding
        self._text_wraplength_max = text_wraplength
        self._wrap_to_viewport = wrap_to_viewport
        self._horizontal_scroll = horizontal_scroll
        self._takefocus = takefocus
        self._show_border = bool(show_border)
        self._border_color = border_color
        self._inner_padding = max(0, int(inner_padding)) if self._show_border else 0

        # tag 模式相关参数
        mode = str(display_mode or "checkbox").lower()
        if mode in ("chip", "tag", "tags", "label"):
            self._display_mode = "tag"
        else:
            self._display_mode = "checkbox"
        self._tag_show_close = bool(tag_show_close)
        self._tag_hpad = max(0, int(tag_hpad))
        self._tag_vpad = max(0, int(tag_vpad))
        self._tag_padx = max(0, int(tag_padx))
        self._tag_pady = max(0, int(tag_pady))

        # tag 模式渲染缓存
        self._tag_chips = []        # list of dict: {frame, label, close, index}
        self._tag_relayout_pending = False
        self._tag_colors_ready = False

        self._rows = []
        self._vars = []
        self._user_data = []
        self._row_frames = []
        self._wrap_labels = []
        self._keyboard_index = None
        self.last_double_click_index = None

        self._allow_reorder = bool(allow_reorder)
        self._on_reorder = on_reorder
        self._drag_state = None
        self._drop_indicator = None
        self.last_reorder = None  # (old_index, new_index)

        if self._show_border:
            # 用经典 tk.Frame 的 highlightthickness 画 1px 边框，
            # 与 HY127_DropdownSelect 的描边方案保持一致（不依赖 ttk 主题对 relief 的实现）
            self._border_frame = tk.Frame(
                self,
                bd=0,
                highlightthickness=1,
                highlightbackground=self._border_color,
                highlightcolor=self._border_color,
            )
            self._border_frame.pack(fill=BOTH, expand=YES)
            scroll_parent = self._border_frame
        else:
            self._border_frame = None
            scroll_parent = self

        self._scroll = HY127_ScrollableFrame(
            scroll_parent,
            autohide=autohide,
            shrink_inner_to_canvas=not horizontal_scroll,
        )
        self._scroll.pack(
            fill=BOTH,
            expand=YES,
            padx=self._inner_padding,
            pady=self._inner_padding,
        )

        self._body = self._scroll.frame
        self._scroll.bind("<Configure>", self._on_scroll_configure)

        if height is not None:
            self.configure(height=height)
            self.pack_propagate(False)

        self._state = NORMAL
        self.set_items(items or [], silent=True)
        if self._takefocus:
            self.enable_keyboard_toggle(True)

    def _on_scroll_configure(self, event=None):
        if self._wrap_to_viewport and (self._text_wraplength_max is not None or self._wrap_labels):
            self.after_idle(self._apply_viewport_wrap)
        if self._display_mode == "tag" and self._tag_chips:
            self._schedule_tag_relayout()

    def _effective_wraplength(self, canvas_width):
        avail = max(20, int(canvas_width) - self._RESERVE_CHECKBOX_COL)
        if self._text_wraplength_max is None:
            return avail
        return min(int(self._text_wraplength_max), avail)

    def _apply_viewport_wrap(self):
        if not self._wrap_labels:
            return
        try:
            cw = self._scroll._canvas.winfo_width()
        except tk.TclError:
            return
        if cw <= 1:
            return
        wl = self._effective_wraplength(cw)
        for lbl in self._wrap_labels:
            try:
                lbl.configure(wraplength=wl)
            except tk.TclError:
                pass
        self._body.update_idletasks()
        self._scroll.refresh_scrollregion()

    # --- 内部：重建行 ---
    def _clear_rows(self):
        for f in self._row_frames:
            try:
                f.destroy()
            except tk.TclError:
                pass
        for chip in self._tag_chips:
            try:
                chip["frame"].destroy()
            except tk.TclError:
                pass
        self._rows = []
        self._vars = []
        self._user_data = []
        self._row_frames = []
        self._wrap_labels = []
        self._tag_chips = []
        if self._drop_indicator is not None:
            try:
                self._drop_indicator.destroy()
            except tk.TclError:
                pass
            self._drop_indicator = None

    def _on_row_toggle(self, index):
        if self._state == DISABLED:
            return
        if index < 0 or index >= len(self._vars):
            return
        checked = self._vars[index].get()
        text = self._rows[index]
        ud = self._user_data[index]
        self._keyboard_index = index
        if self._command:
            self._command(index, text, checked, ud)
        try:
            self.event_generate(EVENT_ITEM_TOGGLED, when="tail")
        except tk.TclError:
            pass
        self._emit_changed()

    def _emit_changed(self):
        if self._on_selection_changed:
            self._on_selection_changed()
        try:
            self.event_generate(EVENT_CHECKLIST_CHANGED, when="tail")
        except tk.TclError:
            pass

    def _build_row(self, index, text, checked, user_data):
        var = tk.BooleanVar(value=checked)
        self._vars.append(var)
        self._rows.append(text)
        self._user_data.append(user_data)

        if self._display_mode == "tag":
            self._build_tag_chip(index, text, var)
            return

        if not self._multiselect:
            self._build_single_row(index, text, var)
            if checked:
                self._single_index = index
            return

        row = ttk.Frame(self._body)
        row.pack(fill=X, pady=(self._row_padding, 0))
        self._row_frames.append(row)

        cb_style = self._bootstyle
        # 开启拖放排序时强制走 (Checkbutton + Label) 形态，
        # 这样始终有 Label 可以作为拖动抓手，UX 更明显
        use_wrap_label = (
            (self._text_wraplength_max is not None)
            or self._wrap_to_viewport
            or self._allow_reorder
        )
        if use_wrap_label:
            try:
                cw0 = max(self._scroll._canvas.winfo_width(), 2)
            except tk.TclError:
                cw0 = 200
            if self._wrap_to_viewport:
                wl0 = self._effective_wraplength(cw0)
            else:
                wl0 = int(self._text_wraplength_max)
            cb = ttk.Checkbutton(
                row,
                variable=var,
                bootstyle=cb_style,
                takefocus=self._takefocus,
                command=lambda i=index: self._on_row_toggle(i),
            )
            cb.pack(side=LEFT, anchor=N)
            lbl = ttk.Label(
                row,
                text=text,
                wraplength=wl0,
                font=self._font,
                anchor=W,
                justify=LEFT,
            )
            lbl.pack(side=LEFT, fill=X, expand=YES, padx=(4, 0))
            lbl.bind("<Double-1>", lambda e, i=index: self._emit_double_click(i))
            if self._wrap_to_viewport:
                self._wrap_labels.append(lbl)
        else:
            cb = ttk.Checkbutton(
                row,
                text=text,
                variable=var,
                bootstyle=cb_style,
                font=self._font,
                takefocus=self._takefocus,
                command=lambda i=index: self._on_row_toggle(i),
            )
            cb.pack(side=LEFT, anchor=W)
            cb.bind("<Double-1>", lambda e, i=index: self._emit_double_click(i))

        if self._state == DISABLED:
            cb.configure(state=DISABLED)
            for child in row.winfo_children():
                if isinstance(child, ttk.Label):
                    child.configure(state=DISABLED)

        # 拖放排序：把整行 Frame、文本 Label、Checkbutton 都当作可抓手
        # （Checkbutton 自身的 toggle 走类绑定 Release，未发生拖动时会正常生效；
        #  发生拖动时 _on_drag_release 返回 "break" 抑制类绑定，避免误 toggle）
        if self._allow_reorder:
            self._install_drag(row, index)
            self._install_drag(cb, index)
            for child in row.winfo_children():
                if isinstance(child, ttk.Label):
                    self._install_drag(child, index)

    def _emit_double_click(self, index):
        if self._state == DISABLED:
            return
        self.last_double_click_index = index
        try:
            self.event_generate("<<HY127CheckListItemDoubleClick>>", when="tail")
        except tk.TclError:
            pass

    # ------------- 单选模式：无复选框、单击高亮、互斥选中 -------------
    def _resolve_single_select_colors(self):
        try:
            colors = self._get_style_instance().colors
            theme_bg = getattr(colors, "bg", "#ffffff")
            theme_fg = getattr(colors, "fg", "#212529")
            accent = self._resolve_bootstyle_color()
        except Exception:
            theme_bg = "#ffffff"
            theme_fg = "#212529"
            accent = "#0d6efd"
        # 选中行：用 accent 与背景混合，保证深浅主题下都清晰
        sel_bg = self._mix_color(theme_bg, accent, 0.30)
        sel_fg = "#ffffff" if self._luminance(sel_bg) < 0.55 else theme_fg
        return theme_bg, theme_fg, sel_bg, sel_fg

    def _build_single_row(self, index, text, var):
        bg, fg, sel_bg, sel_fg = self._resolve_single_select_colors()
        row = tk.Frame(self._body, bd=0, highlightthickness=0, bg=bg)
        row.pack(fill=X, pady=(self._row_padding, 0))
        self._row_frames.append(row)

        try:
            f = self._font
        except Exception:
            f = None

        lbl = tk.Label(
            row,
            text=text,
            anchor=W,
            justify=LEFT,
            bg=bg,
            fg=fg,
            font=f,
            padx=6,
            pady=2,
        )
        lbl.pack(fill=X, expand=YES)

        def _set_visual(selected):
            target_bg = sel_bg if selected else bg
            target_fg = sel_fg if selected else fg
            try:
                row.configure(bg=target_bg)
                lbl.configure(bg=target_bg, fg=target_fg)
            except tk.TclError:
                pass

        def _on_click(event=None, i=index):
            if self._state == DISABLED:
                return
            self._select_single(i)

        if self._allow_reorder:
            self._install_drag(row, index, click_action=lambda i: self._select_single(i))
            self._install_drag(lbl, index, click_action=lambda i: self._select_single(i))
        else:
            lbl.bind("<Button-1>", _on_click)
            row.bind("<Button-1>", _on_click)
        lbl.bind("<Double-1>", lambda e, i=index: self._emit_double_click(i))

        # 缓存 setter，单选切换时由 _select_single 调用
        row._hy127_set_visual = _set_visual

        if self._state == DISABLED:
            try:
                lbl.configure(state=DISABLED)
            except tk.TclError:
                pass

    def _select_single(self, index, silent=False):
        if not self._multiselect:
            if index < 0 or index >= len(self._vars):
                return
            old = self._single_index
            if old == index:
                return
            self._single_index = index
            for i, v in enumerate(self._vars):
                v.set(i == index)
            for i, frame in enumerate(self._row_frames):
                setter = getattr(frame, "_hy127_set_visual", None)
                if setter:
                    setter(i == index)
            text = self._rows[index]
            ud = self._user_data[index] if index < len(self._user_data) else None
            self._keyboard_index = index
            if self._command and not silent:
                try:
                    self._command(index, text, True, ud)
                except Exception:
                    pass
            try:
                self.event_generate(EVENT_ITEM_TOGGLED, when="tail")
            except tk.TclError:
                pass
            if not silent:
                self._emit_changed()

    def _rebuild(self, silent=False):
        self._clear_rows()
        self._single_index = None
        if self._display_mode == "tag":
            self._ensure_tag_colors()
        for i, item in enumerate(getattr(self, "_pending_items", [])):
            self._build_row(i, item["text"], item["checked"], item["user_data"])
        # 单选模式：根据初始 checked 状态高亮（取最后一个 checked 项）
        if not self._multiselect:
            target = None
            for i, v in enumerate(self._vars):
                if v.get():
                    target = i
            self._single_index = None  # 强制 _select_single 应用一次
            if target is not None:
                self._select_single(target, silent=True)
        self._body.update_idletasks()
        self._scroll.refresh_scrollregion()
        if self._display_mode == "tag":
            self._schedule_tag_relayout()
        if self._wrap_to_viewport and self._wrap_labels:
            self.after_idle(self._apply_viewport_wrap)
        if not silent:
            self._emit_changed()

    # ============================================================
    # tag / chip 模式实现
    # ============================================================
    def _get_style_instance(self):
        try:
            return ttk.Style.get_instance()
        except Exception:
            return ttk.Style()

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

    def _resolve_bootstyle_color(self):
        style = self._get_style_instance()
        try:
            colors = style.colors
            color_name = str(self._bootstyle).split("-")[0] if self._bootstyle else "primary"
            return getattr(colors, color_name, colors.primary)
        except Exception:
            return "#0d6efd"

    def _ensure_tag_colors(self):
        """根据当前主题/bootstyle 计算 chip 配色。"""
        style = self._get_style_instance()
        try:
            colors = style.colors
            theme_bg = getattr(colors, "bg", "#ffffff")
            theme_fg = getattr(colors, "fg", "#212529")
        except Exception:
            theme_bg = "#ffffff"
            theme_fg = "#212529"
        accent = self._resolve_bootstyle_color()
        dark = self._luminance(theme_bg) < 0.5

        if dark:
            self._tag_checked_bg = self._mix_color(theme_bg, accent, 0.40)
            self._tag_checked_fg = "#ffffff"
            self._tag_checked_border = self._mix_color(theme_bg, accent, 0.60)
            self._tag_unchecked_bg = self._mix_color(theme_bg, theme_fg, 0.10)
            self._tag_unchecked_fg = self._mix_color(theme_fg, theme_bg, 0.20)
            self._tag_unchecked_border = self._mix_color(theme_bg, theme_fg, 0.25)
        else:
            self._tag_checked_bg = self._mix_color(theme_bg, accent, 0.16)
            self._tag_checked_fg = self._shift_color(accent, -0.30)
            self._tag_checked_border = self._mix_color(theme_bg, accent, 0.45)
            self._tag_unchecked_bg = self._mix_color(theme_bg, theme_fg, 0.04)
            self._tag_unchecked_fg = self._mix_color(theme_fg, theme_bg, 0.30)
            self._tag_unchecked_border = self._mix_color(theme_bg, theme_fg, 0.18)

        self._tag_body_bg = theme_bg
        try:
            self._body.configure(style="TFrame")
        except tk.TclError:
            pass
        self._tag_colors_ready = True

    def _build_tag_chip(self, index, text, var):
        if not self._tag_colors_ready:
            self._ensure_tag_colors()
        checked = bool(var.get())
        bg = self._tag_checked_bg if checked else self._tag_unchecked_bg
        fg = self._tag_checked_fg if checked else self._tag_unchecked_fg
        border = self._tag_checked_border if checked else self._tag_unchecked_border

        # 用 highlightthickness=1 画一像素描边
        chip = tk.Frame(
            self._body,
            bg=bg,
            bd=0,
            highlightthickness=1,
            highlightbackground=border,
            highlightcolor=border,
            cursor="hand2" if self._state != DISABLED else "arrow",
        )

        lbl_kwargs = {"bg": bg, "fg": fg, "bd": 0, "padx": self._tag_padx, "pady": self._tag_pady}
        if self._font is not None:
            lbl_kwargs["font"] = self._font
        lbl = tk.Label(
            chip,
            text=text,
            cursor="hand2" if self._state != DISABLED else "arrow",
            **lbl_kwargs,
        )
        lbl.pack(side=LEFT, fill=Y)

        close = None
        if self._tag_show_close:
            close_kwargs = {
                "bg": bg, "fg": fg, "bd": 0,
                "padx": 4, "pady": self._tag_pady,
                "cursor": "hand2",
                "text": "\u2715",  # ✕
            }
            if self._font is not None:
                close_kwargs["font"] = self._font
            close = tk.Label(chip, **close_kwargs)
            close.pack(side=LEFT, fill=Y, padx=(0, 2))
            if checked:
                close.pack(side=LEFT, fill=Y, padx=(0, 2))
            else:
                close.pack_forget()

        chip_info = {"frame": chip, "label": lbl, "close": close, "index": index}
        self._tag_chips.append(chip_info)

        def _on_click(_e=None, i=index):
            if self._state == DISABLED:
                return
            self._toggle_tag(i)

        if self._allow_reorder:
            self._install_drag(chip, index, click_action=lambda i: self._toggle_tag(i))
            self._install_drag(lbl, index, click_action=lambda i: self._toggle_tag(i))
        else:
            chip.bind("<Button-1>", _on_click)
            lbl.bind("<Button-1>", _on_click)
        lbl.bind("<Double-1>", lambda e, i=index: self._emit_double_click(i))
        chip.bind("<Double-1>", lambda e, i=index: self._emit_double_click(i))

        if close is not None:
            def _on_close(e=None, i=index):
                if self._state == DISABLED:
                    return "break"
                if self._vars[i].get():
                    self._vars[i].set(False)
                    self._apply_tag_visual(i)
                    self._on_row_toggle(i)
                return "break"
            close.bind("<Button-1>", _on_close)
            close.bind(
                "<Enter>",
                lambda e, w=close: w.configure(bg=self._shift_color(w.cget("bg"), -0.10)),
            )
            close.bind(
                "<Leave>",
                lambda e, w=close, i=index: w.configure(
                    bg=self._tag_checked_bg if self._vars[i].get() else self._tag_unchecked_bg
                ),
            )

        # 悬停效果
        def _on_enter(_e=None, c=chip, l=lbl, i=index):
            if self._state == DISABLED:
                return
            base = self._tag_checked_bg if self._vars[i].get() else self._tag_unchecked_bg
            hover = self._shift_color(base, -0.06)
            try:
                c.configure(bg=hover)
                l.configure(bg=hover)
                cl = self._tag_chips[i].get("close") if i < len(self._tag_chips) else None
                if cl is not None and cl.winfo_ismapped():
                    cl.configure(bg=hover)
            except tk.TclError:
                pass

        def _on_leave(_e=None, i=index):
            self._apply_tag_visual(i)

        chip.bind("<Enter>", _on_enter)
        chip.bind("<Leave>", _on_leave)
        lbl.bind("<Enter>", _on_enter)

        if self._state == DISABLED:
            try:
                lbl.configure(state=DISABLED)
                if close is not None:
                    close.configure(state=DISABLED)
            except tk.TclError:
                pass

    def _toggle_tag(self, index):
        if not (0 <= index < len(self._vars)):
            return
        v = self._vars[index]
        v.set(not v.get())
        self._apply_tag_visual(index)
        self._on_row_toggle(index)

    def _apply_tag_visual(self, index):
        if not (0 <= index < len(self._tag_chips)):
            return
        info = self._tag_chips[index]
        chip, lbl, close = info["frame"], info["label"], info["close"]
        checked = bool(self._vars[index].get())
        bg = self._tag_checked_bg if checked else self._tag_unchecked_bg
        fg = self._tag_checked_fg if checked else self._tag_unchecked_fg
        border = self._tag_checked_border if checked else self._tag_unchecked_border
        try:
            chip.configure(
                bg=bg,
                highlightbackground=border,
                highlightcolor=border,
            )
            lbl.configure(bg=bg, fg=fg)
            if close is not None:
                close.configure(bg=bg, fg=fg)
                if checked:
                    if not close.winfo_ismapped():
                        close.pack(side=LEFT, fill=Y, padx=(0, 2))
                else:
                    if close.winfo_ismapped():
                        close.pack_forget()
        except tk.TclError:
            pass

    def _schedule_tag_relayout(self):
        if self._tag_relayout_pending:
            return
        self._tag_relayout_pending = True
        try:
            self.after_idle(self._do_tag_relayout)
        except tk.TclError:
            self._tag_relayout_pending = False

    def _do_tag_relayout(self):
        self._tag_relayout_pending = False
        if self._display_mode != "tag" or not self._tag_chips:
            try:
                self._body.configure(height=1)
            except tk.TclError:
                pass
            return
        try:
            cw = self._scroll._canvas.winfo_width()
        except tk.TclError:
            return
        if cw <= 1:
            self.after(50, self._schedule_tag_relayout)
            return

        # 计算可用宽度
        avail = max(20, cw - 2)
        x = 0
        y = 0
        line_h = 0
        max_x = 0

        # 让所有 chip 先 update，以便测得实际请求宽高
        for info in self._tag_chips:
            try:
                info["frame"].update_idletasks()
            except tk.TclError:
                pass

        for info in self._tag_chips:
            chip = info["frame"]
            try:
                w = max(chip.winfo_reqwidth(), 1)
                h = max(chip.winfo_reqheight(), 1)
            except tk.TclError:
                continue
            # 单个 chip 宽度超出可用宽度时强制换行并占满
            if w > avail and x == 0:
                pass  # 直接占据这一行
            elif x + w > avail and x > 0:
                # 换行
                x = 0
                y += line_h + self._tag_vpad
                line_h = 0
            try:
                chip.place(x=x, y=y, width=w, height=h)
            except tk.TclError:
                pass
            x += w + self._tag_hpad
            line_h = max(line_h, h)
            max_x = max(max_x, x)

        total_h = y + line_h
        try:
            self._body.configure(height=max(total_h, 1))
        except tk.TclError:
            pass
        self._body.update_idletasks()
        try:
            self._scroll.refresh_scrollregion()
        except tk.TclError:
            pass

    # ============================================================
    # 行间拖放排序
    # ============================================================
    def _install_drag(self, widget, index, click_action=None):
        """为 widget 安装拖动监听。

        - widget: 要绑定的目标控件（行 Frame / 标签 / Checkbutton / chip 等）
        - index: 安装时该 widget 所在的源行下标（rebuild 后整套绑定会重建，所以
          直接用闭包默认参数捕获即可）
        - click_action: 可选，未发生拖动时在 ButtonRelease 时调用 (index)。
          tag/single 模式用它把"点击=立即触发"改为"点击=Release 触发"，避免
          与拖动手势冲突；checkbox 多选模式传 None 即可（toggle 由 Checkbutton
          自身的类绑定处理，发生拖动时由本类的 release 返回 "break" 抑制）。
        """
        if not self._allow_reorder:
            return
        try:
            widget.bind(
                "<ButtonPress-1>",
                lambda e, i=index: self._on_drag_press(e, i),
            )
            widget.bind("<B1-Motion>", self._on_drag_motion)
            widget.bind(
                "<ButtonRelease-1>",
                lambda e, i=index, ca=click_action: self._on_drag_release(e, i, ca),
            )
        except tk.TclError:
            pass

    def _on_drag_press(self, event, index):
        if self._state == DISABLED:
            return None
        if not (0 <= index < len(self._rows)):
            return None
        self._drag_state = {
            "src": index,
            "x_root": event.x_root,
            "y_root": event.y_root,
            "dragging": False,
        }
        return None

    def _on_drag_motion(self, event):
        s = self._drag_state
        if not s:
            return None
        if not s["dragging"]:
            dx = event.x_root - s["x_root"]
            dy = event.y_root - s["y_root"]
            if abs(dx) + abs(dy) < self._DRAG_THRESHOLD:
                return None
            s["dragging"] = True
            try:
                self.configure(cursor="fleur")
            except tk.TclError:
                pass
        self._update_drop_indicator(event)
        return None

    def _on_drag_release(self, event, index, click_action):
        s = self._drag_state
        self._drag_state = None
        self._hide_drop_indicator()
        try:
            self.configure(cursor="")
        except tk.TclError:
            pass
        if not s:
            return None
        if s["dragging"]:
            target_slot = self._compute_drop_slot(event)
            src = s["src"]
            # target_slot 是"源被移除前的目标插槽"，转成移除后的最终下标
            if target_slot > src:
                dst = target_slot - 1
            else:
                dst = target_slot
            n = len(self._rows)
            if 0 <= dst < n and dst != src:
                self._move_row(src, dst)
            # 抑制底层类绑定（避免 Checkbutton 在长拖动后被误 toggle）
            return "break"
        # 未发生拖动：触发 click_action（tag/single 模式专用）
        if click_action is not None and 0 <= index < len(self._rows):
            try:
                click_action(index)
            except Exception:
                pass
        return None

    def _ensure_drop_indicator(self):
        ind = self._drop_indicator
        if ind is None or not ind.winfo_exists():
            try:
                accent = self._resolve_bootstyle_color()
            except Exception:
                accent = "#0d6efd"
            self._drop_indicator = tk.Frame(
                self._body,
                bd=0,
                highlightthickness=0,
                bg=accent,
            )
        return self._drop_indicator

    def _hide_drop_indicator(self):
        ind = self._drop_indicator
        if ind is None:
            return
        try:
            ind.place_forget()
        except tk.TclError:
            pass

    def _body_xy_from_event(self, event):
        try:
            bx = self._body.winfo_rootx()
            by = self._body.winfo_rooty()
        except tk.TclError:
            return 0, 0
        return event.x_root - bx, event.y_root - by

    def _update_drop_indicator(self, event):
        bx, by = self._body_xy_from_event(event)
        if self._display_mode == "tag":
            self._update_tag_drop_indicator(bx, by)
        else:
            self._update_vertical_drop_indicator(by)

    # ---- 垂直布局（checkbox / 单选）目标插槽 ----
    def _compute_vertical_target_slot(self, body_y):
        rows = self._row_frames
        n = len(rows)
        if n == 0:
            return 0
        for i, row in enumerate(rows):
            try:
                ry = row.winfo_y()
                rh = row.winfo_height()
            except tk.TclError:
                continue
            mid = ry + rh / 2
            if body_y < mid:
                return i
        return n

    def _update_vertical_drop_indicator(self, body_y):
        slot = self._compute_vertical_target_slot(body_y)
        rows = self._row_frames
        n = len(rows)
        if n == 0:
            return
        try:
            body_w = max(self._body.winfo_width(), 4)
        except tk.TclError:
            return
        if slot <= 0:
            ry = max(0, rows[0].winfo_y() - 1)
        elif slot >= n:
            last = rows[-1]
            ry = last.winfo_y() + last.winfo_height()
        else:
            cur = rows[slot]
            ry = max(0, cur.winfo_y() - 1)
        ind = self._ensure_drop_indicator()
        try:
            ind.place(x=0, y=ry, width=body_w, height=2)
            ind.lift()
        except tk.TclError:
            pass

    # ---- tag 流式布局目标插槽 ----
    def _compute_tag_target_with_anchor(self, body_x, body_y):
        n = len(self._tag_chips)
        if n == 0:
            return 0, None, "left"
        best = None
        best_d = None
        for i, info in enumerate(self._tag_chips):
            chip = info["frame"]
            try:
                cx = chip.winfo_x()
                cy = chip.winfo_y()
                cw = chip.winfo_width()
                ch = chip.winfo_height()
            except tk.TclError:
                continue
            midx = cx + cw / 2
            midy = cy + ch / 2
            # 同一行（y 接近）显著加权，避免跳到上一行末尾
            d = abs(midy - body_y) * 10 + abs(midx - body_x)
            if best_d is None or d < best_d:
                best_d = d
                best = i
        if best is None:
            return n, None, "left"
        chip = self._tag_chips[best]["frame"]
        try:
            cx = chip.winfo_x()
            cw = chip.winfo_width()
        except tk.TclError:
            return best, best, "left"
        if body_x < cx + cw / 2:
            return best, best, "left"
        return best + 1, best, "right"

    def _update_tag_drop_indicator(self, body_x, body_y):
        target, anchor_idx, side = self._compute_tag_target_with_anchor(body_x, body_y)
        if anchor_idx is None or anchor_idx >= len(self._tag_chips):
            return
        chip = self._tag_chips[anchor_idx]["frame"]
        try:
            cx = chip.winfo_x()
            cy = chip.winfo_y()
            cw = chip.winfo_width()
            ch = chip.winfo_height()
        except tk.TclError:
            return
        bar_w = 2
        if side == "left":
            bx = max(0, cx - 2)
        else:
            bx = cx + cw
        ind = self._ensure_drop_indicator()
        try:
            ind.place(x=bx, y=cy, width=bar_w, height=ch)
            ind.lift()
        except tk.TclError:
            pass

    def _compute_drop_slot(self, event):
        bx, by = self._body_xy_from_event(event)
        if self._display_mode == "tag":
            target, _, _ = self._compute_tag_target_with_anchor(bx, by)
            return target
        return self._compute_vertical_target_slot(by)

    def _move_row(self, src, dst):
        """把第 src 行移动到 dst 位置（其它行相应顺延）。同步触发回调与虚拟事件。"""
        if src == dst:
            return
        items = self.get_items()
        n = len(items)
        if not (0 <= src < n) or not (0 <= dst < n):
            return
        was_single_selected_src = (
            (not self._multiselect) and self._single_index == src
        )
        item = items.pop(src)
        items.insert(dst, item)
        # 直接重排已规范化的 _pending_items，避免再次 _normalize_item
        self._pending_items = [_normalize_item(x) for x in items]
        self._rebuild(silent=True)
        if was_single_selected_src:
            try:
                self._select_single(dst, silent=True)
            except Exception:
                pass
        self._keyboard_index = dst
        self.last_reorder = (src, dst)
        if self._on_reorder is not None:
            try:
                self._on_reorder(src, dst)
            except Exception:
                pass
        try:
            self.event_generate(EVENT_REORDERED, when="tail")
        except tk.TclError:
            pass

    def reorder_item(self, old_index, new_index):
        """公开 API：把 old_index 项移动到 new_index 位置（含勾选状态搬迁）。"""
        try:
            old_index = int(old_index)
            new_index = int(new_index)
        except (TypeError, ValueError):
            return
        self._move_row(old_index, new_index)

    def set_allow_reorder(self, allow):
        """运行时切换"允许拖放排序"开关。会触发一次重建以重新挂载手势监听。"""
        new_val = bool(allow)
        if new_val == self._allow_reorder:
            return
        self._allow_reorder = new_val
        self.set_items(self.get_items(), silent=True)

    def get_allow_reorder(self):
        return self._allow_reorder

    def set_on_reorder(self, callback):
        self._on_reorder = callback

    # --- 公开 API：数据 ---
    def set_items(self, items, silent=False):
        """替换全部列表项。silent=True 时不触发 on_selection_changed / 虚拟事件。"""
        parsed = [_normalize_item(x) for x in items]
        self._pending_items = parsed
        self._rebuild(silent=silent)

    def get_items(self):
        """返回当前每项: [{"text","checked","user_data"}, ...]"""
        result = []
        for i in range(len(self._vars)):
            result.append(
                {
                    "text": self._rows[i],
                    "checked": self._vars[i].get(),
                    "user_data": self._user_data[i],
                }
            )
        return result

    def get_checked_indices(self):
        return [i for i, v in enumerate(self._vars) if v.get()]

    def get_unchecked_indices(self):
        return [i for i, v in enumerate(self._vars) if not v.get()]

    def get_checked_texts(self):
        return [self._rows[i] for i in self.get_checked_indices()]

    def get_checked_user_data(self):
        return [self._user_data[i] for i in self.get_checked_indices()]

    def set_checked_indices(self, indices, value=True, silent=False):
        """按索引设置勾选状态。"""
        s = set(indices)
        if not self._multiselect:
            # 单选模式：只取最后一个 index 作为高亮
            target = None
            for i in s:
                if 0 <= i < len(self._vars) and value:
                    target = i
            if target is not None:
                self._select_single(target, silent=silent)
            return
        for i, v in enumerate(self._vars):
            if i in s:
                v.set(value)
        self._refresh_all_tag_visuals()
        if not silent:
            self._emit_changed()

    def set_all(self, checked=True, silent=False):
        if not self._multiselect:
            # 单选模式不支持全选；checked=False 等价于清空选择
            if not checked:
                self._single_index = None
                for i, v in enumerate(self._vars):
                    v.set(False)
                for frame in self._row_frames:
                    setter = getattr(frame, "_hy127_set_visual", None)
                    if setter:
                        setter(False)
                if not silent:
                    self._emit_changed()
            return
        for v in self._vars:
            v.set(checked)
        self._refresh_all_tag_visuals()
        if not silent:
            self._emit_changed()

    def select_all(self, silent=False):
        self.set_all(True, silent=silent)

    def deselect_all(self, silent=False):
        self.set_all(False, silent=silent)

    def invert_selection(self, silent=False):
        for v in self._vars:
            v.set(not v.get())
        self._refresh_all_tag_visuals()
        if not silent:
            self._emit_changed()

    def _refresh_all_tag_visuals(self):
        if self._display_mode != "tag":
            return
        for i in range(len(self._tag_chips)):
            self._apply_tag_visual(i)

    def append_item(self, text, checked=False, user_data=None, silent=False):
        items = self.get_items()
        items.append(_normalize_item({"text": text, "checked": checked, "user_data": user_data}))
        self.set_items(items, silent=silent)

    def remove_item(self, index, silent=False):
        items = self.get_items()
        if 0 <= index < len(items):
            del items[index]
            self.set_items(items, silent=silent)

    def clear(self, silent=False):
        self.set_items([], silent=silent)

    @property
    def item_count(self):
        return len(self._vars)

    def configure_item(self, index, text=None, user_data=None):
        """更新某一行的显示文本或 user_data（会重建该行所在列表以简化实现）。"""
        items = self.get_items()
        if not (0 <= index < len(items)):
            return
        if text is not None:
            items[index]["text"] = text
        if user_data is not None:
            items[index]["user_data"] = user_data
        self.set_items(items, silent=True)

    # --- 状态与样式 ---
    def configure(self, **kwargs):
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        if "on_selection_changed" in kwargs:
            self._on_selection_changed = kwargs.pop("on_selection_changed")
        if "bootstyle" in kwargs:
            self._bootstyle = kwargs.pop("bootstyle")
            if self._display_mode == "tag":
                self._tag_colors_ready = False
            self.set_items(self.get_items(), silent=True)
        if "display_mode" in kwargs:
            mode = str(kwargs.pop("display_mode") or "checkbox").lower()
            self._display_mode = "tag" if mode in ("chip", "tag", "tags", "label") else "checkbox"
            self._tag_colors_ready = False
            self.set_items(self.get_items(), silent=True)
        if "tag_show_close" in kwargs:
            self._tag_show_close = bool(kwargs.pop("tag_show_close"))
            if self._display_mode == "tag":
                self.set_items(self.get_items(), silent=True)
        if "font" in kwargs:
            self._font = kwargs.pop("font")
            self.set_items(self.get_items(), silent=True)
        if "text_wraplength" in kwargs:
            self._text_wraplength_max = kwargs.pop("text_wraplength")
            self.set_items(self.get_items(), silent=True)
        if "wrap_to_viewport" in kwargs:
            self._wrap_to_viewport = kwargs.pop("wrap_to_viewport")
            self.set_items(self.get_items(), silent=True)
        if "allow_reorder" in kwargs:
            self.set_allow_reorder(kwargs.pop("allow_reorder"))
        if "on_reorder" in kwargs:
            self._on_reorder = kwargs.pop("on_reorder")
        if "state" in kwargs:
            self._apply_state(kwargs.pop("state"))
        super().configure(**kwargs)

    def _apply_state(self, state):
        self._state = state
        for row in self._row_frames:
            for child in row.winfo_children():
                try:
                    child.configure(state=state)
                except tk.TclError:
                    pass

    def set_bootstyle(self, bootstyle):
        self._bootstyle = bootstyle
        self.set_items(self.get_items(), silent=True)

    def get_bootstyle(self):
        return self._bootstyle

    def set_command(self, command):
        self._command = command

    def set_on_selection_changed(self, callback):
        self._on_selection_changed = callback

    # --- 键盘：聚焦组件后方向键移动，Space 切换 ---
    def enable_keyboard_toggle(self, enable=True):
        self._takefocus = enable
        try:
            self.configure(takefocus=1 if enable else 0)
        except tk.TclError:
            pass
        if enable:
            self.bind("<FocusIn>", self._on_focus_in)
            self.bind("<Key-Down>", self._key_down)
            self.bind("<Key-Up>", self._key_up)
            self.bind("<space>", self._key_space)
            self.bind("<Return>", self._key_space)
        else:
            for seq in ("<FocusIn>", "<Key-Down>", "<Key-Up>", "<space>", "<Return>"):
                self.unbind(seq)

    def _on_focus_in(self, event=None):
        if self._keyboard_index is None and self._vars:
            self._keyboard_index = 0

    def _key_down(self, event=None):
        if not self._vars:
            return "break"
        if self._keyboard_index is None:
            self._keyboard_index = 0
        else:
            self._keyboard_index = min(len(self._vars) - 1, self._keyboard_index + 1)
        return "break"

    def _key_up(self, event=None):
        if not self._vars:
            return "break"
        if self._keyboard_index is None:
            self._keyboard_index = 0
        else:
            self._keyboard_index = max(0, self._keyboard_index - 1)
        return "break"

    def _key_space(self, event=None):
        if self._keyboard_index is None or not self._vars:
            return "break"
        i = self._keyboard_index
        v = self._vars[i]
        v.set(not v.get())
        self._on_row_toggle(i)
        return "break"


if __name__ == "__main__":
    app = ttk.Window(themename="cosmo")
    app.title("HY127_CheckList 演示")
    app.geometry("780x520")

    container = ttk.Frame(app)
    container.pack(fill=BOTH, expand=YES, padx=10, pady=10)

    # 左侧：传统复选框模式
    left = ttk.Labelframe(container, text="复选框模式", padding=8)
    left.pack(side=LEFT, fill=BOTH, expand=YES, padx=(0, 5))

    lst = HY127_CheckList(
        left,
        items=[
            "苹果",
            {"text": "香蕉", "checked": True},
            {"text": "备注很长的项用于测试折行显示效果", "checked": False, "user_data": {"id": 3}},
        ],
        bootstyle="primary",
        text_wraplength=280,
        height=220,
    )
    lst.pack(fill=BOTH, expand=YES)

    # 右侧：标签 chip 模式
    right = ttk.Labelframe(container, text="标签 (tag) 模式", padding=8)
    right.pack(side=LEFT, fill=BOTH, expand=YES, padx=(5, 0))

    tag_items = [
        {"text": "新客户", "checked": True},
        {"text": "加急交付", "checked": True},
        "VIP",
        "退款单",
        "海外订单",
        "需复核",
        "线上支付",
        "线下支付",
        "缺货",
        "促销活动",
    ]

    def on_tag_changed():
        texts = tag_lst.get_checked_texts()
        cur.configure(text="当前标签：" + ("，".join(texts) if texts else "（空）"))

    tag_lst = HY127_CheckList(
        right,
        items=tag_items,
        bootstyle="info",
        display_mode="tag",
        on_selection_changed=on_tag_changed,
        height=180,
    )
    tag_lst.pack(fill=BOTH, expand=YES)

    cur = ttk.Label(right, text="当前标签：新客户，加急交付", bootstyle="secondary")
    cur.pack(fill=X, pady=(6, 0))

    bar = ttk.Frame(app)
    bar.pack(fill=X, padx=10, pady=(0, 10))

    ttk.Button(bar, text="全选(右)", command=tag_lst.select_all, bootstyle="info-outline").pack(side=LEFT, padx=2)
    ttk.Button(bar, text="全不选(右)", command=tag_lst.deselect_all, bootstyle="secondary-outline").pack(side=LEFT, padx=2)
    ttk.Button(bar, text="反选(右)", command=tag_lst.invert_selection, bootstyle="secondary-outline").pack(side=LEFT, padx=2)
    ttk.Button(
        bar,
        text="打印已选(右)",
        command=lambda: print("checked:", tag_lst.get_checked_indices(), tag_lst.get_checked_texts()),
        bootstyle="secondary-outline",
    ).pack(side=LEFT, padx=2)

    on_tag_changed()
    app.mainloop()
