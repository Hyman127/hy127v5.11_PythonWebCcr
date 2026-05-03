# -*- coding: utf-8 -*-
"""
HY127_ImageList — 类似 Windows 资源管理器"大图标视图"的图片列表控件。

特性：
    - Canvas 虚拟化网格（仅渲染可视区，万张图片也能流畅）
    - 缩略图大小可缩放（API / 滑块 / Ctrl+滚轮）
    - 单选 / Ctrl 多选 / Shift 连选 / 鼠标框选（橡皮筋）
    - 鼠标悬浮 → 浮窗预览大图（异步加载、可关闭）
    - 双击 → 弹出 HY127_ImagePreview 大图窗
    - 键盘导航：← → ↑ ↓ Home End PgUp PgDn  Space/Enter 激活
    - 缩略图磁盘缓存 + 内存 LRU + 后台线程池
    - 与 HY127_CheckList 一致的事件 + bootstyle + 边框风格

虚拟事件（在控件上 bind）：
    <<HY127ImageListSelectionChanged>>   选择改变后触发（after 尾部派发）
    <<HY127ImageListItemActivated>>      双击 / Enter 激活某项
    <<HY127ImageListZoomChanged>>        缩放档位变化
"""
from __future__ import annotations

import datetime as _dt
import logging
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable, Optional

import tkinter as tk
import tkinter.font as tkfont
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from ._imagelist_cache import (
    LRUImageCache,
    PLACEHOLDERS,
    PreviewLoader,
    ThumbLoader,
    is_pil_available,
)
from .HY127_ImagePreview import HY127_ImagePreview

logger = logging.getLogger(__name__)


EVENT_IMAGELIST_SELECTION_CHANGED = "<<HY127ImageListSelectionChanged>>"
EVENT_IMAGELIST_ITEM_ACTIVATED = "<<HY127ImageListItemActivated>>"
EVENT_IMAGELIST_ZOOM_CHANGED = "<<HY127ImageListZoomChanged>>"
EVENT_IMAGELIST_VIEW_MODE_CHANGED = "<<HY127ImageListViewModeChanged>>"
# 行 / 单元格 / 列 级事件（增强 ListView 用）
EVENT_IMAGELIST_ROW_CLICKED = "<<HY127ImageListRowClicked>>"
EVENT_IMAGELIST_ROW_DOUBLE_CLICKED = "<<HY127ImageListRowDoubleClicked>>"
EVENT_IMAGELIST_ROW_RIGHT_CLICKED = "<<HY127ImageListRowRightClicked>>"
EVENT_IMAGELIST_CELL_CLICKED = "<<HY127ImageListCellClicked>>"
EVENT_IMAGELIST_CELL_DOUBLE_CLICKED = "<<HY127ImageListCellDoubleClicked>>"
EVENT_IMAGELIST_SORT_CHANGED = "<<HY127ImageListSortChanged>>"
EVENT_IMAGELIST_COLUMN_RESIZED = "<<HY127ImageListColumnResized>>"
EVENT_IMAGELIST_COLUMN_CLICKED = "<<HY127ImageListColumnClicked>>"
# 拖动重排（行/图片移动到指定位置）
EVENT_IMAGELIST_ITEMS_REORDERED = "<<HY127ImageListItemsReordered>>"
# 列内嵌控件
EVENT_IMAGELIST_CELL_VALUE_CHANGED = "<<HY127ImageListCellValueChanged>>"
EVENT_IMAGELIST_BUTTON_CLICKED = "<<HY127ImageListButtonClicked>>"
EVENT_IMAGELIST_EDIT_STARTED = "<<HY127ImageListEditStarted>>"
EVENT_IMAGELIST_EDIT_COMMITTED = "<<HY127ImageListEditCommitted>>"
EVENT_IMAGELIST_EDIT_CANCELLED = "<<HY127ImageListEditCancelled>>"


# 默认支持的图片扩展名（小写）
DEFAULT_IMAGE_EXTS = (
    ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp",
    ".ico", ".tif", ".tiff",
)


# ====================== 详情视图辅助 ======================

def _human_readable_size(num_bytes) -> str:
    """字节数 → 1.2 MB / 345 KB 这种。"""
    if num_bytes is None:
        return "—"
    try:
        n = float(num_bytes)
    except (TypeError, ValueError):
        return "—"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(n)} B"
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _format_mtime(mtime) -> str:
    if not mtime:
        return "—"
    try:
        return _dt.datetime.fromtimestamp(float(mtime)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "—"


def _default_details_columns() -> list[dict]:
    """默认的详情视图列定义。

    每个 dict 字段：
        key:   列标识
        title: 表头文字
        width: 像素宽度；最后一个 width<=0 的列会吃掉剩余宽度
        type:  "image" / "text" / "meta"
        anchor: 文本对齐 "w"/"center"/"e"
        getter: 取值函数。type=text → fn(item)；type=meta → fn(item, meta_dict)
    """
    return [
        {"key": "thumb", "title": "", "width": 46, "type": "image",
         "anchor": "center"},
        {"key": "name", "title": "名称", "width": 280, "type": "text",
         "anchor": "w",
         "getter": lambda it: it.get("caption") or os.path.basename(it.get("path", ""))},
        {"key": "ext", "title": "类型", "width": 70, "type": "text",
         "anchor": "w",
         "getter": lambda it: (os.path.splitext(it.get("path", ""))[1].lstrip(".").upper() or "—")},
        {"key": "dimensions", "title": "尺寸", "width": 110, "type": "meta",
         "anchor": "e",
         "getter": lambda it, m: (f"{m['w']}×{m['h']}" if m.get("w") else "—")},
        {"key": "size", "title": "大小", "width": 100, "type": "meta",
         "anchor": "e",
         "getter": lambda it, m: _human_readable_size(m.get("size_bytes"))},
        {"key": "mtime", "title": "修改时间", "width": 160, "type": "meta",
         "anchor": "w",
         "getter": lambda it, m: _format_mtime(m.get("mtime"))},
        {"key": "path", "title": "路径", "width": 0, "type": "text",
         "anchor": "w",
         "getter": lambda it: it.get("path", "")},
    ]


def _normalize_item(raw, default_user_data=None) -> dict:
    """str / dict → 标准化 item dict。

    设计要点：
        - 当 raw 是 dict 时，直接复用同一对象（仅补齐 path / caption / user_data / _key
          等元字段），用户的额外字段（enabled / rating / 业务字段等）全部保留。
          这样列内嵌控件的 value_setter 写值时，外部传入的 dict 能直接看到变化。
        - 当 raw 是 str 时，构造一个新 dict。
        - _key 用作内部稳定 ID（默认 = 绝对路径）。
    """
    if isinstance(raw, dict):
        path = raw.get("path") or raw.get("file") or ""
        if "path" not in raw:
            raw["path"] = path
        if "caption" not in raw or raw.get("caption") is None:
            raw["caption"] = os.path.basename(path) if path else ""
        else:
            raw["caption"] = str(raw["caption"])
        if "user_data" not in raw:
            raw["user_data"] = raw.get("data", default_user_data)
        if "_key" not in raw:
            raw["_key"] = os.path.abspath(path) if path else f"__id_{id(raw)}"
        return raw
    path = str(raw)
    return {
        "path": path,
        "caption": os.path.basename(path),
        "user_data": default_user_data,
        "_key": os.path.abspath(path) if path else f"__id_{id(raw)}",
    }


class HY127_ImageList(ttk.Frame):
    """图片缩略图列表控件。

    参数说明见模块文档。常用参数：
        items: 初始项，元素可为 str（路径）或 dict({path, caption, user_data})
        thumb_size: 初始缩略图边长（像素），默认 128
        thumb_sizes: 可选档位（用于 Ctrl+滚轮 / API set_thumb_size_step）
        show_caption: 是否在缩略图下显示文件名
        caption_lines: 文件名最多显示多少行（1 或 2）
        selection_mode: "single" / "multi" / "extended"（默认）
        enable_marquee: 是否启用框选
        enable_hover_preview: 是否启用悬浮浮窗预览
        hover_delay_ms: 悬浮多少毫秒后显示预览
        hover_preview_size: 浮窗预览图最大边长
        enable_zoom_with_ctrl_wheel: 是否允许 Ctrl+滚轮缩放
        cache_dir: 缩略图磁盘缓存目录（默认 %TEMP%/hy127_imagelist_cache）
        max_workers: 后台线程数
        bootstyle: 选择高亮配色（取 ttkbootstrap 的语义色）
        show_border / border_color / inner_padding: 与 HY127_CheckList 一致的边框
        on_select_changed: 选择变化回调，参数 = list[dict] 已选项
        on_double_click: 双击/激活回调，参数 = dict（被双击的项）
        on_context_menu: 右键回调 (item, event)，返回 True 表示已处理（不再弹默认菜单）
"""

    # 可用的缩放档位
    DEFAULT_THUMB_SIZES = (64, 96, 128, 160, 192, 224, 256, 320)

    # bootstyle → (fill, outline, hover_outline) 颜色映射；未命中走 PRIMARY
    _SELECT_COLORS = {
        "primary":   ("#cfe2ff", "#0d6efd", "#6ea8fe"),
        "secondary": ("#e2e3e5", "#6c757d", "#adb5bd"),
        "success":   ("#d1e7dd", "#198754", "#75b798"),
        "info":      ("#cff4fc", "#0dcaf0", "#6edff6"),
        "warning":   ("#fff3cd", "#ffc107", "#ffe083"),
        "danger":    ("#f8d7da", "#dc3545", "#ea868f"),
        "light":     ("#f8f9fa", "#adb5bd", "#dee2e6"),
        "dark":      ("#d3d3d4", "#212529", "#495057"),
    }

    _DEFAULT_BG = "#ffffff"
    _DEFAULT_BORDER_COLOR = "#ced4da"
    _DEFAULT_DETAILS_HEADER_BG = "#f1f3f5"
    _DEFAULT_DETAILS_HEADER_FG = "#495057"
    _DEFAULT_DETAILS_ALT_ROW_BG = "#f8f9fb"
    _DEFAULT_DETAILS_GRID_COLOR = "#e9ecef"

    def __init__(
        self,
        master=None,
        items=None,
        thumb_size: int = 128,
        thumb_sizes: Iterable[int] = DEFAULT_THUMB_SIZES,
        cell_padx: int = 8,
        cell_pady: int = 8,
        show_caption: bool = True,
        caption_lines: int = 2,
        selection_mode: str = "extended",
        enable_marquee: bool = True,
        enable_hover_preview: bool = True,
        hover_delay_ms: int = 500,
        hover_preview_size: int = 480,
        enable_zoom_with_ctrl_wheel: bool = True,
        enable_double_click_preview: bool = True,
        cache_dir: Optional[str] = None,
        max_workers: int = 4,
        bg: str = "#ffffff",
        bootstyle: str = PRIMARY,
        show_border: bool = True,
        border_color: str = "#ced4da",
        inner_padding: int = 4,
        # —— 详情视图相关 ——
        view_mode: str = "thumbnail",
        details_columns: Optional[list[dict]] = None,
        details_show_thumb_column: bool = True,
        details_thumb_size: int = 32,
        details_row_height: int = 36,
        details_header_height: int = 28,
        details_header_bg: str = "#f1f3f5",
        details_header_fg: str = "#495057",
        details_alt_row_bg: str = "#f8f9fb",
        details_grid_color: str = "#e9ecef",
        details_show_v_grid: bool = True,   # 列与列之间的竖线（表头 + 数据行）
        details_show_h_grid: bool = True,   # 行与行之间的横线
        # —— 拖动重排 ——
        enable_drag_reorder: bool = False,
        drag_reorder_threshold: int = 5,
        drag_clear_sort: bool = True,       # 拖动时若有排序，自动取消排序
        # 行 / 单元格 / 列事件回调（除虚拟事件外可选直传）
        on_row_click: Optional[Callable] = None,
        on_cell_click: Optional[Callable] = None,
        on_sort_changed: Optional[Callable] = None,
        on_column_resized: Optional[Callable] = None,
        on_cell_value_changed: Optional[Callable] = None,
        on_button_clicked: Optional[Callable] = None,
        on_select_changed: Optional[Callable] = None,
        on_double_click: Optional[Callable] = None,
        on_context_menu: Optional[Callable] = None,
        font=None,
        **kwargs,
    ):
        super().__init__(master, **kwargs)

        # ---------- 配置 ----------
        self._items: list[dict] = []
        self._thumb_size = int(thumb_size)
        self._thumb_sizes = tuple(sorted(set(int(x) for x in thumb_sizes)))
        if self._thumb_size not in self._thumb_sizes:
            # 把当前值加入档位
            self._thumb_sizes = tuple(sorted(set(self._thumb_sizes + (self._thumb_size,))))
        self._cell_padx = int(cell_padx)
        self._cell_pady = int(cell_pady)
        self._show_caption = bool(show_caption)
        self._caption_lines = max(1, min(2, int(caption_lines)))
        self._selection_mode = selection_mode if selection_mode in ("single", "multi", "extended") else "extended"
        self._enable_marquee = bool(enable_marquee)
        self._enable_hover_preview = bool(enable_hover_preview) and is_pil_available()
        self._hover_delay_ms = int(hover_delay_ms)
        self._hover_preview_size = int(hover_preview_size)
        self._enable_zoom_with_ctrl_wheel = bool(enable_zoom_with_ctrl_wheel)
        self._enable_double_click_preview = bool(enable_double_click_preview)
        self._bg = bg
        self._bootstyle = (bootstyle or "primary").lower()
        self._show_border = bool(show_border)
        self._border_color = border_color
        self._inner_padding = max(0, int(inner_padding))
        self._on_select_changed = on_select_changed
        self._on_double_click = on_double_click
        self._on_context_menu = on_context_menu
        self._font = font or tkfont.nametofont("TkDefaultFont")

        # —— 详情视图配置 ——
        self._view_mode = view_mode if view_mode in ("thumbnail", "details") else "thumbnail"
        cols = (
            details_columns if details_columns is not None else _default_details_columns()
        )
        if not details_show_thumb_column:
            cols = [c for c in cols if c.get("type") != "image"]
        self._details_columns = list(cols)
        self._details_show_thumb_column = bool(details_show_thumb_column)
        # 行/单元格事件回调
        self._on_row_click = on_row_click
        self._on_cell_click = on_cell_click
        self._on_sort_changed = on_sort_changed
        self._on_column_resized = on_column_resized
        self._on_cell_value_changed = on_cell_value_changed
        self._on_button_clicked = on_button_clicked
        self._details_thumb_size = max(16, int(details_thumb_size))
        self._details_row_height = max(20, int(details_row_height))
        self._details_header_height = max(20, int(details_header_height))
        self._details_header_bg = details_header_bg
        self._details_header_fg = details_header_fg
        self._details_alt_row_bg = details_alt_row_bg
        self._details_grid_color = details_grid_color
        self._details_show_v_grid = bool(details_show_v_grid)
        self._details_show_h_grid = bool(details_show_h_grid)
        # 拖动重排
        self._enable_drag_reorder = bool(enable_drag_reorder)
        self._drag_reorder_threshold = max(2, int(drag_reorder_threshold))
        self._drag_clear_sort = bool(drag_clear_sort)
        self._drag_state: Optional[dict] = None
        # 单元格内嵌控件状态
        self._editing: Optional[dict] = None  # {pos, data_idx, col_key, widget, win_id, original}
        self._control_press: Optional[dict] = None  # {pos, col_key, control_type}
        # 列头 Canvas（在 _build_ui 中创建）
        self._header_canvas: Optional[tk.Canvas] = None
        # 当前列宽缓存（含 flex 列实际像素）
        self._effective_col_widths: list[int] = []
        # 拖列宽状态
        self._col_drag: Optional[dict] = None
        # 排序状态：{"key": str, "order": "asc" | "desc"} 或 None
        self._sort_state: Optional[dict] = None
        # 显示顺序映射：display_index -> data_index；None 表示未排序
        self._display_indices: Optional[list[int]] = None
        self._theme_after: Optional[str] = None

        # 若用户未显式传色，则允许主题切换时自动跟随。
        self._bg_follows_theme = (bg == self._DEFAULT_BG)
        self._border_follows_theme = (border_color == self._DEFAULT_BORDER_COLOR)
        self._header_bg_follows_theme = (
            details_header_bg == self._DEFAULT_DETAILS_HEADER_BG
        )
        self._header_fg_follows_theme = (
            details_header_fg == self._DEFAULT_DETAILS_HEADER_FG
        )
        self._alt_row_bg_follows_theme = (
            details_alt_row_bg == self._DEFAULT_DETAILS_ALT_ROW_BG
        )
        self._grid_color_follows_theme = (
            details_grid_color == self._DEFAULT_DETAILS_GRID_COLOR
        )

        # —— 元数据缓存（详情视图列：尺寸/大小/时间） ——
        self._meta_cache: dict[str, dict] = {}
        self._meta_loader = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="HY127ImgMeta",
        )
        self._meta_pending: set[str] = set()

        # ---------- 状态 ----------
        self._selected: set[int] = set()
        self._anchor_index: Optional[int] = None  # Shift 连选锚点
        self._cursor_index: Optional[int] = None  # 键盘导航当前焦点
        self._hover_index: Optional[int] = None
        self._hover_col_key: Optional[str] = None
        self._cols = 1
        self._rows = 0
        self._cell_w = self._thumb_size + 2 * self._cell_padx
        self._cell_h = self._thumb_size + 2 * self._cell_pady + (
            self._caption_height() if self._show_caption else 0
        )

        # 缩略图缓存与加载器
        self._lru = LRUImageCache(max_items=600)
        self._loader = ThumbLoader(
            cache_dir=cache_dir,
            max_workers=max_workers,
            on_done=self._on_thumb_loaded,
            tk_root=self,
        )
        self._preview_loader = PreviewLoader(max_workers=2, tk_root=self)

        # canvas item 字典：index -> { 'image':id, 'rect':id, 'caption':id }
        self._cell_items: dict[int, dict] = {}
        # 选择变更尾部派发
        self._sel_changed_after: Optional[str] = None
        # 滚动节流
        self._scroll_after: Optional[str] = None
        # hover 计时
        self._hover_after: Optional[str] = None
        self._hover_window: Optional[tk.Toplevel] = None
        self._hover_label: Optional[ttk.Label] = None
        self._hover_path: Optional[str] = None
        self._hover_photo: Optional[tk.PhotoImage] = None
        # 框选
        self._marquee_start: Optional[tuple[float, float]] = None
        self._marquee_id: Optional[int] = None
        # 滚动期间不触发 hover
        self._suspend_hover_until: float = 0.0

        # ---------- UI ----------
        self._update_theme_colors()
        self._build_ui()
        self._bind_events()

        # 如果初始就是 details，立刻构建表头
        if self._view_mode == "details":
            # 等 canvas 拿到宽度后再构建表头，避免 winfo_width()=1
            self.after_idle(self._build_details_header)

        if items:
            self.set_items(items)
        else:
            self._relayout(force=True)

    # ====================================================================
    # UI 构建
    # ====================================================================

    def _build_ui(self):
        # 外层边框（show_border=True 时显示）
        if self._show_border:
            self.configure(borderwidth=1, relief="solid")
            try:
                # ttkbootstrap 的 Frame 也支持 highlightbackground 透传
                self.configure(highlightthickness=0)
            except tk.TclError:
                pass
        # 根容器 grid 布局：
        #   row 0 = 表头 Canvas（仅 details 显示，与主 Canvas 共享 xview）
        #   row 1 = 主 Canvas
        #   row 2 = 水平滚动条（按需自动隐藏）
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)
        self.grid_columnconfigure(0, weight=1)

        pad = self._inner_padding if self._show_border else 0
        self._ui_pad = pad

        # 详情视图固定表头：用 Canvas 渲染，便于跟主 Canvas 同步 xview / 画排序箭头 / 拖列宽
        self._header_canvas = tk.Canvas(
            self,
            bg=self._details_header_bg,
            height=self._details_header_height,
            bd=0,
            highlightthickness=0,
        )
        self._header_canvas.grid(
            row=0, column=0, sticky=EW,
            padx=(pad, 0), pady=(pad, 0),
        )
        if self._view_mode != "details":
            self._header_canvas.grid_remove()

        # 主 Canvas
        self._canvas = tk.Canvas(
            self,
            bg=self._bg,
            highlightthickness=0,
            bd=0,
        )
        canvas_pady = (0, 0) if self._view_mode == "details" else (pad, 0)
        self._canvas.grid(row=1, column=0, sticky=NSEW, padx=(pad, 0), pady=canvas_pady)

        # 垂直滚动条
        self._vsb = ttk.Scrollbar(
            self, orient=VERTICAL, command=self._on_yscroll_command,
        )
        self._vsb.grid(row=1, column=1, sticky=NS, pady=canvas_pady)

        # 水平滚动条（按需显示）
        self._hsb = ttk.Scrollbar(
            self, orient=HORIZONTAL, command=self._on_hscroll_command,
        )
        self._hsb.grid(row=2, column=0, sticky=EW, padx=(pad, 0))
        self._hsb.grid_remove()  # 默认隐藏；scrollregion 超宽时自动出现

        self._canvas.configure(
            yscrollcommand=self._on_yscroll_set,
            xscrollcommand=self._on_xscroll_set,
        )
        self._header_canvas.configure(xscrollcommand=lambda *a: None)

        # 表头交互：点击排序 / 拖列宽
        self._header_canvas.bind("<Motion>", self._on_header_motion)
        self._header_canvas.bind("<ButtonPress-1>", self._on_header_press)
        self._header_canvas.bind("<B1-Motion>", self._on_header_drag)
        self._header_canvas.bind("<ButtonRelease-1>", self._on_header_release)
        self._header_canvas.bind("<Leave>", self._on_header_leave)

        # 边框颜色（轻量伪边框：在 frame 外 配置 takefocus 0）
        if self._show_border and self._border_color:
            try:
                self.configure(highlightbackground=self._border_color)
            except tk.TclError:
                pass

    def _bind_events(self):
        c = self._canvas
        c.bind("<Configure>", self._on_canvas_configure)
        c.bind("<ButtonPress-1>", self._on_left_press)
        c.bind("<B1-Motion>", self._on_left_motion)
        c.bind("<ButtonRelease-1>", self._on_left_release)
        c.bind("<Double-Button-1>", self._on_double_click_event)
        c.bind("<Button-3>", self._on_right_click)
        c.bind("<Motion>", self._on_motion)
        c.bind("<Leave>", self._on_canvas_leave)
        c.bind("<Enter>", self._on_canvas_enter)
        # 滚轮
        c.bind("<MouseWheel>", self._on_mousewheel)
        if self._enable_zoom_with_ctrl_wheel:
            c.bind("<Control-MouseWheel>", self._on_ctrl_mousewheel)
        # 键盘
        c.configure(takefocus=1)
        c.bind("<FocusIn>", lambda e: None)
        for seq, fn in (
            ("<Left>",   lambda e: self._move_cursor(dx=-1)),
            ("<Right>",  lambda e: self._move_cursor(dx=1)),
            ("<Up>",     lambda e: self._move_cursor(dy=-1)),
            ("<Down>",   lambda e: self._move_cursor(dy=1)),
            ("<Home>",   lambda e: self._move_cursor(absolute=0)),
            ("<End>",    lambda e: self._move_cursor(absolute=len(self._items) - 1)),
            ("<Prior>",  lambda e: self._move_cursor(page=-1)),  # PageUp
            ("<Next>",   lambda e: self._move_cursor(page=1)),   # PageDown
            ("<Return>", lambda e: self._activate_current()),
            ("<KP_Enter>", lambda e: self._activate_current()),
            ("<space>",  lambda e: self._toggle_current()),
            ("<Control-a>", lambda e: (self.select_all(), "break")),
            ("<F2>",     lambda e: self._start_edit_at_cursor()),
            ("<Escape>", lambda e: self._cancel_edit() if self._editing else None),
        ):
            c.bind(seq, fn)
        self.bind("<<ThemeChanged>>", self._on_theme_changed, add="+")
        c.bind("<<ThemeChanged>>", self._on_theme_changed, add="+")
        if self._header_canvas is not None:
            self._header_canvas.bind("<<ThemeChanged>>", self._on_theme_changed, add="+")

    # ====================================================================
    # 颜色与计算
    # ====================================================================

    def _get_style_instance(self):
        try:
            return ttk.Style.get_instance()
        except Exception:
            return ttk.Style()

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
        return self._rgb_to_hex((
            r1 * (1.0 - weight) + r2 * weight,
            g1 * (1.0 - weight) + g2 * weight,
            b1 * (1.0 - weight) + b2 * weight,
        ))

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
                bg = self._DEFAULT_BG
        return self._luminance(bg) < 0.5

    def _resolve_bootstyle_color(self):
        style = self._get_style_instance()
        try:
            colors = style.colors
            color_name = str(self._bootstyle or "primary").split("-")[0]
            return getattr(colors, color_name, colors.primary)
        except Exception:
            mapping = self._SELECT_COLORS.get(self._bootstyle, self._SELECT_COLORS["primary"])
            return mapping[1]

    def _update_theme_colors(self):
        style = self._get_style_instance()
        try:
            colors = style.colors
            theme_bg = getattr(colors, "bg", self._DEFAULT_BG)
            theme_fg = getattr(colors, "fg", "#212529")
            border = getattr(colors, "border", self._DEFAULT_BORDER_COLOR)
            select_fg = getattr(colors, "selectfg", "#ffffff")
            warning = getattr(colors, "warning", "#ffc107")
        except Exception:
            theme_bg = self._DEFAULT_BG
            theme_fg = "#212529"
            border = self._DEFAULT_BORDER_COLOR
            select_fg = "#ffffff"
            warning = "#ffc107"

        field_bg = (
            self._lookup_style("TEntry", "fieldbackground", None)
            or self._lookup_style("TCombobox", "fieldbackground", theme_bg)
            or theme_bg
        )
        field_fg = (
            self._lookup_style("TEntry", "foreground", None)
            or self._lookup_style("TCombobox", "foreground", theme_fg)
            or theme_fg
        )
        dark_theme = self._is_dark_theme()
        accent = self._resolve_bootstyle_color()

        self._theme_bg = theme_bg
        self._theme_fg = theme_fg
        self._theme_muted_fg = self._mix_color(theme_fg, theme_bg, 0.45 if dark_theme else 0.35)
        self._theme_surface = field_bg
        self._theme_surface_alt = self._mix_color(
            theme_fg, theme_bg, 0.92 if dark_theme else 0.98
        )
        self._theme_border = border
        self._theme_grid = self._mix_color(
            theme_fg, theme_bg, 0.78 if dark_theme else 0.90
        )
        self._theme_accent = accent
        self._theme_accent_hover = self._shift_color(accent, 0.30 if dark_theme else 0.18)
        self._theme_select_fill = self._mix_color(field_bg, accent, 0.22 if dark_theme else 0.18)
        self._theme_select_outline = accent
        self._theme_cursor_outline = self._mix_color(border, accent, 0.70)
        self._theme_select_fg = select_fg
        self._theme_check_fill = accent
        self._theme_check_outline = self._mix_color(border, theme_bg, 0.15)
        self._theme_combo_btn_bg = self._mix_color(field_bg, theme_bg, 0.25 if dark_theme else 0.12)
        self._theme_progress_track = self._mix_color(border, theme_bg, 0.45 if dark_theme else 0.65)
        self._theme_rating_fill = warning
        self._theme_rating_outline = self._shift_color(warning, -0.15 if dark_theme else -0.12)
        self._theme_rating_empty = self._mix_color(border, theme_bg, 0.35)
        self._theme_tooltip_bg = accent
        self._theme_tooltip_fg = select_fg

        if self._bg_follows_theme:
            self._bg = theme_bg
        if self._border_follows_theme:
            self._border_color = border
        if self._header_bg_follows_theme:
            self._details_header_bg = self._mix_color(
                theme_fg, theme_bg, 0.86 if dark_theme else 0.95
            )
        if self._header_fg_follows_theme:
            self._details_header_fg = theme_fg
        if self._alt_row_bg_follows_theme:
            self._details_alt_row_bg = self._theme_surface_alt
        if self._grid_color_follows_theme:
            self._details_grid_color = self._theme_grid
        self._theme_text = field_fg or theme_fg

    def _apply_theme_to_widgets(self):
        try:
            self._canvas.configure(bg=self._bg)
        except tk.TclError:
            pass
        try:
            self._header_canvas.configure(bg=self._details_header_bg)
        except tk.TclError:
            pass
        if self._show_border and self._border_color:
            try:
                self.configure(highlightbackground=self._border_color)
            except tk.TclError:
                pass

    def _apply_theme_change(self):
        self._theme_after = None
        self._cancel_hover()
        if self._editing is not None:
            self._commit_edit()
        self._update_theme_colors()
        self._apply_theme_to_widgets()
        if self._view_mode == "details":
            self._build_details_header()
        self._canvas.delete("all")
        self._cell_items.clear()
        self._relayout(force=True)

    def _on_theme_changed(self, _event=None):
        if self._theme_after:
            return
        self._theme_after = self.after_idle(self._apply_theme_change)

    def _select_colors(self):
        return (
            self._theme_select_fill,
            self._theme_select_outline,
            self._theme_accent_hover,
        )

    def _caption_height(self) -> int:
        try:
            line_h = self._font.metrics("linespace") if hasattr(self._font, "metrics") else 16
        except Exception:
            line_h = 16
        # 上下各 2px 间隔
        return self._caption_lines * line_h + 4

    def _recalc_cell_size(self):
        if self._view_mode == "details":
            cw = max(1, self._canvas.winfo_width() or 1)
            self._cell_w = cw
            self._cell_h = self._details_row_height
        else:
            self._cell_w = self._thumb_size + 2 * self._cell_padx
            self._cell_h = self._thumb_size + 2 * self._cell_pady + (
                self._caption_height() if self._show_caption else 0
            )

    # ====================================================================
    # 详情视图：列宽与表头
    # ====================================================================

    def _compute_column_widths(self) -> list[int]:
        """根据 canvas 宽度把 width<=0 的列分摊剩余空间；
        若用户已通过拖拽设置过 user_width，则以 user_width 为准。
        如果总宽超过画布宽度 → 不再压缩，让水平滚动条出现。
        """
        cw = max(1, self._canvas.winfo_width() or 1)
        cols = self._details_columns
        widths: list[int] = []
        flex_indices: list[int] = []
        fixed = 0
        for i, c in enumerate(cols):
            if "user_width" in c and c["user_width"] is not None:
                w = int(c["user_width"])
                widths.append(w)
                fixed += w
                continue
            base = int(c.get("width", 0))
            if base <= 0:
                widths.append(0)
                flex_indices.append(i)
            else:
                widths.append(base)
                fixed += base

        if flex_indices:
            remaining = cw - fixed
            min_each = 80
            if remaining < min_each * len(flex_indices):
                # 没有足够空间 → flex 列也用最小宽度，让总宽度超过画布（出现横滚）
                for i in flex_indices:
                    widths[i] = min_each
            else:
                per = remaining // len(flex_indices)
                for i in flex_indices:
                    widths[i] = max(min_each, per)

        # 应用每列的 min_width / max_width
        for i, c in enumerate(cols):
            mn = int(c.get("min_width", 24))
            mx = c.get("max_width")
            widths[i] = max(mn, widths[i])
            if mx:
                widths[i] = min(int(mx), widths[i])
        return widths

    def _column_offsets(self) -> list[int]:
        """返回每列的起始 x 偏移（含一个末尾哨兵）。"""
        widths = self._effective_col_widths or self._compute_column_widths()
        offsets = [0]
        for w in widths:
            offsets.append(offsets[-1] + w)
        return offsets

    def _build_details_header(self):
        """在 _header_canvas 上重画表头：列名、排序箭头、列分隔线、拖动手柄区。"""
        if self._header_canvas is None:
            return
        self._header_canvas.delete("all")

        widths = self._compute_column_widths()
        self._effective_col_widths = widths
        offsets = [0]
        for w in widths:
            offsets.append(offsets[-1] + w)
        total_w = offsets[-1]
        h = self._details_header_height

        # scrollregion 与主体保持一致（后续 _relayout 会再统一设一次）
        cw = max(total_w, max(1, self._canvas.winfo_width() or 1))
        self._header_canvas.configure(scrollregion=(0, 0, cw, h))

        # 表头底部一条分隔线
        self._header_canvas.create_line(
            0, h - 1, cw, h - 1,
            fill=self._details_grid_color,
            tags=("hdr_bottom_line",),
        )

        for i, col in enumerate(self._details_columns):
            x0 = offsets[i]
            x1 = offsets[i + 1]
            w = widths[i]
            key = col["key"]
            title = col.get("title", "")

            # 列背景（用于排序高亮）
            sort_state = self._sort_state if hasattr(self, "_sort_state") else None
            is_sorted = bool(sort_state and sort_state.get("key") == key)
            bg = col.get("header_bg") or (
                "#e7f1ff" if is_sorted else self._details_header_bg
            )
            self._header_canvas.create_rectangle(
                x0, 0, x1 - 1, h - 1,
                fill=bg, outline="",
                tags=("hdr_bg", f"hdr_bg_{key}"),
            )

            # 标题
            anchor_str = col.get("header_anchor", col.get("anchor", "w"))
            if anchor_str == "e":
                tx = x1 - 24  # 右侧留 24px 给排序箭头
                tk_anchor = E
            elif anchor_str == "center":
                tx = (x0 + x1) // 2
                tk_anchor = CENTER
            else:
                tx = x0 + 8
                tk_anchor = W
            font = col.get("header_font") or self._font
            fg = col.get("header_fg") or self._details_header_fg
            self._header_canvas.create_text(
                tx, h // 2,
                text=title, anchor=tk_anchor,
                font=font, fill=fg,
                tags=("hdr_text", f"hdr_text_{key}"),
            )

            # 排序箭头
            if is_sorted:
                order = sort_state.get("order")
                arrow = "▲" if order == "asc" else "▼"
                self._header_canvas.create_text(
                    x1 - 10, h // 2,
                    text=arrow, anchor=E,
                    font=font, fill=self._theme_accent,
                    tags=("hdr_arrow", f"hdr_arrow_{key}"),
                )

            # 列分隔线（除最后一列）
            if self._details_show_v_grid and i < len(self._details_columns) - 1:
                self._header_canvas.create_line(
                    x1 - 1, 4, x1 - 1, h - 4,
                    fill=self._details_grid_color,
                    tags=("hdr_sep", f"hdr_sep_{key}"),
                )

    def _apply_view_mode_ui(self):
        """切换 view_mode 时同步表头显隐与 padding。"""
        pad = self._ui_pad
        if self._view_mode == "details":
            self._header_canvas.grid()
            self._build_details_header()
            self._canvas.grid_configure(pady=(0, 0))
            self._vsb.grid_configure(pady=(0, 0))
        else:
            self._header_canvas.grid_remove()
            self._hsb.grid_remove()  # 缩略图视图永远不出现横滚
            self._canvas.grid_configure(pady=(pad, 0))
            self._vsb.grid_configure(pady=(pad, 0))

    # ====================================================================
    # 表头交互：列宽拖拽 + 排序
    # ====================================================================

    _RESIZE_HOT_PX = 5  # 边缘热区像素

    def _hit_test_header(self, event_x_widget: int):
        """命中测试。返回 (action, col_index)
        action ∈ {"resize", "click", None}
        """
        widths = self._effective_col_widths or self._compute_column_widths()
        x = self._header_canvas.canvasx(event_x_widget)
        offsets = [0]
        for w in widths:
            offsets.append(offsets[-1] + w)
        # 优先 resize 命中（最后一列右边缘也可拖）
        for i, c in enumerate(self._details_columns):
            if c.get("resizable", True):
                edge = offsets[i + 1]
                if abs(x - edge) <= self._RESIZE_HOT_PX:
                    return ("resize", i)
        # 列点击
        for i in range(len(self._details_columns)):
            if offsets[i] <= x < offsets[i + 1]:
                return ("click", i)
        return (None, -1)

    def _on_header_motion(self, event):
        if self._col_drag is not None:
            return  # 拖动中由 _on_header_drag 处理
        action, _ = self._hit_test_header(event.x)
        cur = "sb_h_double_arrow" if action == "resize" else ""
        try:
            self._header_canvas.configure(cursor=cur)
        except tk.TclError:
            pass

    def _on_header_leave(self, _event=None):
        if self._col_drag is None:
            try:
                self._header_canvas.configure(cursor="")
            except tk.TclError:
                pass

    def _on_header_press(self, event):
        action, idx = self._hit_test_header(event.x)
        if action == "resize" and idx >= 0:
            widths = self._effective_col_widths
            self._col_drag = {
                "col_index": idx,
                "start_x": self._header_canvas.canvasx(event.x),
                "start_w": widths[idx],
                "indicator": None,
            }
            self._draw_resize_indicator(self._header_canvas.canvasx(event.x))
        elif action == "click" and idx >= 0:
            # 记录起点，松手且未拖动 → 触发排序
            self._col_drag = {
                "col_index": idx,
                "is_click": True,
                "start_x": self._header_canvas.canvasx(event.x),
            }

    def _on_header_drag(self, event):
        if self._col_drag is None:
            return
        x = self._header_canvas.canvasx(event.x)
        if self._col_drag.get("is_click"):
            # 点击模式下，移动超过阈值就放弃排序
            if abs(x - self._col_drag["start_x"]) > 4:
                self._col_drag = None
            return
        idx = self._col_drag["col_index"]
        new_w = int(self._col_drag["start_w"] + (x - self._col_drag["start_x"]))
        col = self._details_columns[idx]
        mn = int(col.get("min_width", 24))
        mx = col.get("max_width")
        new_w = max(mn, new_w)
        if mx:
            new_w = min(int(mx), new_w)
        # 实时更新列宽。拖动过程中避免走 _relayout(force=True) 的整屏 delete("all"),
        # 否则会先清空画布，再 after_idle 重画，肉眼就会看到白屏闪烁。
        col["user_width"] = new_w
        self._effective_col_widths = []  # 强制重算
        self._relayout_for_column_resize_drag()
        # 移动指示线
        widths = self._effective_col_widths
        offsets_sum = sum(widths[: idx + 1])
        self._draw_resize_indicator(offsets_sum)

    def _on_header_release(self, event):
        if self._col_drag is None:
            return
        info = self._col_drag
        self._col_drag = None
        self._header_canvas.delete("resize_indicator")
        if info.get("is_click"):
            # 真点击 → 触发排序
            x = self._header_canvas.canvasx(event.x)
            if abs(x - info["start_x"]) <= 4:
                self._toggle_sort(info["col_index"])
            return
        # 拖动结束：派发列宽变化事件
        idx = info["col_index"]
        col = self._details_columns[idx]
        new_w = int(col.get("user_width", info["start_w"]))
        self._fire_event(
            EVENT_IMAGELIST_COLUMN_RESIZED,
            data={"key": col["key"], "width": new_w, "index": idx},
        )
        try:
            self._header_canvas.configure(cursor="")
        except tk.TclError:
            pass

    def _draw_resize_indicator(self, x: float):
        """画一条竖向虚线表示拖动位置（在表头与主 Canvas 上）。"""
        try:
            self._header_canvas.delete("resize_indicator")
            self._header_canvas.create_line(
                x, 0, x, self._details_header_height,
                fill=self._theme_accent, dash=(3, 2),
                tags=("resize_indicator",),
            )
        except tk.TclError:
            pass

    def _relayout_for_column_resize_drag(self):
        """列宽拖动时的轻量重排。

        目标：
            - 不整屏 delete("all")
            - 不依赖 after_idle 才重画
            - 仅同步更新表头、scrollregion 与当前可视区 cell
        """
        if self._view_mode != "details":
            self._relayout(force=True)
            return
        cw = max(1, self._canvas.winfo_width() or 1)
        new_widths = self._compute_column_widths()
        self._effective_col_widths = new_widths
        total_col_w = sum(new_widths)
        self._cols = 1
        self._rows = max(0, len(self._items))
        self._cell_w = max(cw, total_col_w)
        self._cell_h = self._details_row_height
        self._build_details_header()
        total_h = self._rows * self._cell_h
        self._canvas.configure(
            scrollregion=(0, 0, self._cell_w, max(total_h, 1))
        )
        self._rebuild_visible_cells()
        try:
            self.update_idletasks()
        except tk.TclError:
            pass

    # ----- 排序 -----

    def _toggle_sort(self, col_index: int):
        """循环切换：none → asc → desc → none。"""
        col = self._details_columns[col_index]
        if not col.get("sortable", True):
            return
        key = col["key"]
        cur = self._sort_state
        if cur is None or cur.get("key") != key:
            new_state = {"key": key, "order": "asc"}
        elif cur.get("order") == "asc":
            new_state = {"key": key, "order": "desc"}
        else:
            new_state = None
        self._sort_state = new_state
        self._apply_sort()
        self._build_details_header()
        self._relayout(force=True)
        self._fire_event(
            EVENT_IMAGELIST_SORT_CHANGED,
            data={
                "key": new_state["key"] if new_state else None,
                "order": new_state["order"] if new_state else None,
            },
        )

    def _apply_sort(self):
        """根据 _sort_state 计算 _display_indices。"""
        if self._sort_state is None:
            self._display_indices = None
            return
        key = self._sort_state["key"]
        order = self._sort_state["order"]
        col = next(
            (c for c in self._details_columns if c["key"] == key), None
        )
        if col is None:
            self._display_indices = None
            return

        sort_key = col.get("sort_key")
        sort_type = col.get("sort_type", "auto")  # auto / numeric / text / date

        def value_of(item):
            if sort_key is not None:
                try:
                    return sort_key(item)
                except Exception:
                    return None
            # 默认按列定义的 type 取值
            return self._extract_column_value(col, item)

        def coerce(v):
            if v is None:
                return (1, "")  # None 排到最后
            if sort_type == "numeric":
                try:
                    return (0, float(v))
                except (TypeError, ValueError):
                    return (1, str(v))
            if sort_type == "text":
                return (0, str(v).lower())
            if sort_type == "date":
                # 字符串/数字时间戳；返回原始（已是可比较）
                return (0, v)
            # auto
            try:
                return (0, float(v))
            except (TypeError, ValueError):
                return (0, str(v).lower())

        idx = list(range(len(self._items)))
        idx.sort(
            key=lambda i: coerce(value_of(self._items[i])),
            reverse=(order == "desc"),
        )
        self._display_indices = idx

    def _data_index(self, display_index: int) -> int:
        """display_index → 实际数据索引（无排序时直接返回）。"""
        if self._display_indices is None:
            return display_index
        if 0 <= display_index < len(self._display_indices):
            return self._display_indices[display_index]
        return display_index

    def _extract_column_value(self, col: dict, item):
        """从 item 中按列定义抽取原始值。供排序与默认渲染共用。"""
        ctype = col.get("type", "text")
        key = col.get("key")
        path = _normalize_item(item)["path"]
        if ctype == "name":
            try:
                import os
                return os.path.basename(path) if path else ""
            except Exception:
                return ""
        if ctype == "size":
            meta = self._meta_cache.get(path) or {}
            return meta.get("size_bytes") or 0
        if ctype == "mtime":
            meta = self._meta_cache.get(path) or {}
            return meta.get("mtime") or 0
        if ctype == "dimension":
            meta = self._meta_cache.get(path) or {}
            w = meta.get("w") or 0
            h = meta.get("h") or 0
            return (w or 0) * (h or 0)
        if ctype == "meta":
            # type=meta 时按 key 取 meta 字段
            meta = self._meta_cache.get(path) or {}
            return meta.get(key)
        if ctype == "ext":
            try:
                import os
                _, ext = os.path.splitext(path)
                return ext.lower().lstrip(".")
            except Exception:
                return ""
        if ctype == "image":
            return ""
        # 自定义列：dict item 直接取 key
        if isinstance(item, dict) and key in item:
            return item[key]
        return ""

    def _default_format_value(self, col: dict, raw, meta: dict) -> str:
        """没有 formatter 时的默认渲染：按列 type 决定。"""
        if raw is None:
            ctype = col.get("type", "text")
            if ctype in ("size", "mtime", "dimension"):
                return "—"
            return ""
        ctype = col.get("type", "text")
        if ctype == "size":
            return _human_readable_size(raw)
        if ctype == "mtime":
            return _format_mtime(raw)
        if ctype == "dimension":
            w = (meta or {}).get("w")
            h = (meta or {}).get("h")
            if w and h:
                return f"{w}×{h}"
            return "—"
        if ctype == "ext":
            s = str(raw).upper()
            return s if s else "—"
        return str(raw)

    # ====================================================================
    # 视图模式 API
    # ====================================================================

    def set_view_mode(self, mode: str):
        """切换 'thumbnail' / 'details'。"""
        if mode not in ("thumbnail", "details"):
            return
        if mode == self._view_mode:
            return
        self._view_mode = mode
        self._cancel_hover()
        # 清掉所有 cell（两种模式 item 结构不同）
        self._canvas.delete("all")
        self._cell_items.clear()
        self._apply_view_mode_ui()
        # generation+1 让旧的缩略图任务失效（避免详情小图和大缩略图混淆）
        self._loader.set_generation(self._loader.get_generation() + 1)
        self._recalc_cell_size()
        self._relayout(force=True)
        try:
            self.event_generate(EVENT_IMAGELIST_VIEW_MODE_CHANGED, when="tail")
        except tk.TclError:
            pass

    def get_view_mode(self) -> str:
        return self._view_mode

    def toggle_view_mode(self) -> str:
        self.set_view_mode("details" if self._view_mode == "thumbnail" else "thumbnail")
        return self._view_mode

    def set_details_columns(self, columns: list[dict]):
        """运行时修改列定义。"""
        if not columns:
            return
        self._details_columns = list(columns)
        # 失效列宽缓存 & 排序（旧 key 可能不再存在）
        self._effective_col_widths = []
        if self._sort_state and not any(
                c["key"] == self._sort_state["key"] for c in self._details_columns):
            self._sort_state = None
            self._display_indices = None
        if self._view_mode == "details":
            self._build_details_header()
            self._canvas.delete("all")
            self._cell_items.clear()
            self._relayout(force=True)

    def set_grid_visible(self,
                         v: Optional[bool] = None,
                         h: Optional[bool] = None):
        """运行时切换网格线显示。
        v: 列与列之间的竖线（含表头列分隔线）；None 表示不变
        h: 行与行之间的横线；None 表示不变
        """
        changed = False
        if v is not None and bool(v) != self._details_show_v_grid:
            self._details_show_v_grid = bool(v)
            changed = True
        if h is not None and bool(h) != self._details_show_h_grid:
            self._details_show_h_grid = bool(h)
            changed = True
        if not changed:
            return
        if self._view_mode == "details":
            self._build_details_header()
            self._canvas.delete("all")
            self._cell_items.clear()
            self._relayout(force=True)

    def get_grid_visible(self) -> tuple[bool, bool]:
        """返回 (vertical, horizontal)。"""
        return (self._details_show_v_grid, self._details_show_h_grid)

    # ====================================================================
    # 列宽 / 排序 公共 API
    # ====================================================================

    def set_column_width(self, key: str, width: int):
        """设置某列像素宽度，立即生效。"""
        for c in self._details_columns:
            if c["key"] == key:
                c["user_width"] = max(int(c.get("min_width", 24)), int(width))
                break
        else:
            return
        self._effective_col_widths = []
        if self._view_mode == "details":
            self._build_details_header()
            self._relayout(force=True)

    def get_column_width(self, key: str) -> int:
        """获取某列当前实际像素宽度。"""
        widths = self._effective_col_widths or self._compute_column_widths()
        for i, c in enumerate(self._details_columns):
            if c["key"] == key:
                return widths[i] if i < len(widths) else 0
        return 0

    def sort_by(self, key: Optional[str], order: str = "asc"):
        """按列编程式排序。key=None 取消排序。"""
        if key is None:
            self._sort_state = None
        else:
            if order not in ("asc", "desc"):
                order = "asc"
            if not any(c["key"] == key for c in self._details_columns):
                return
            self._sort_state = {"key": key, "order": order}
        self._apply_sort()
        if self._view_mode == "details":
            self._build_details_header()
        self._relayout(force=True)

    def get_sort_state(self) -> Optional[dict]:
        """返回 {"key", "order"} 或 None。"""
        return dict(self._sort_state) if self._sort_state else None

    # ====================================================================
    # 数据 API
    # ====================================================================

    def set_items(self, items: Iterable):
        """整体替换。"""
        self._cancel_hover()
        self._selected.clear()
        self._anchor_index = None
        self._cursor_index = None
        self._cell_items.clear()
        self._lru.clear()
        self._meta_cache.clear()
        self._meta_pending.clear()
        self._items = [_normalize_item(x) for x in (items or [])]
        # 旧 generation 全部失效
        self._loader.set_generation(self._loader.get_generation() + 1)
        # 重新计算排序（保留排序状态）
        self._apply_sort()
        self._canvas.yview_moveto(0)
        self._canvas.xview_moveto(0)
        try:
            self._header_canvas.xview_moveto(0)
        except tk.TclError:
            pass
        self._relayout(force=True)
        self._dispatch_selection_changed()

    def add_items(self, items: Iterable):
        new_items = [_normalize_item(x) for x in (items or [])]
        if not new_items:
            return
        self._items.extend(new_items)
        self._apply_sort()
        self._relayout(force=True)

    def clear(self):
        self.set_items([])

    def get_items(self) -> list[dict]:
        return [dict(it) for it in self._items]

    def get_item(self, index: int) -> Optional[dict]:
        if 0 <= index < len(self._items):
            return dict(self._items[index])
        return None

    def get_selected(self) -> list[dict]:
        return [dict(self._items[i]) for i in sorted(self._selected) if 0 <= i < len(self._items)]

    def get_selected_indices(self) -> list[int]:
        return sorted(self._selected)

    def select_index(self, index: int, additive: bool = False):
        if not (0 <= index < len(self._items)):
            return
        if not additive:
            self._selected.clear()
        self._selected.add(index)
        self._anchor_index = index
        self._cursor_index = index
        self._redraw_visible()
        self._dispatch_selection_changed()

    def select_all(self):
        if self._selection_mode == "single":
            return
        self._selected = set(range(len(self._items)))
        self._redraw_visible()
        self._dispatch_selection_changed()

    def clear_selection(self):
        if not self._selected:
            return
        self._selected.clear()
        self._redraw_visible()
        self._dispatch_selection_changed()

    # ====================================================================
    # 缩放 API
    # ====================================================================

    def set_thumb_size(self, px: int):
        px = max(32, min(1024, int(px)))
        if px == self._thumb_size:
            return
        self._thumb_size = px
        # 详情视图下 thumb_size 只是状态值，不影响小图标渲染；下次切回缩略图视图才生效
        if self._view_mode == "thumbnail":
            # 仅清除大缩略图相关的 LRU 是更精细的做法；这里直接清空更简单可靠
            self._lru.clear()
            self._cell_items.clear()
            self._loader.set_generation(self._loader.get_generation() + 1)
            self._recalc_cell_size()
            self._relayout(force=True)
        try:
            self.event_generate(EVENT_IMAGELIST_ZOOM_CHANGED, when="tail")
        except tk.TclError:
            pass

    def get_thumb_size(self) -> int:
        return self._thumb_size

    def zoom_in(self):
        for s in self._thumb_sizes:
            if s > self._thumb_size:
                self.set_thumb_size(s)
                return
        self.set_thumb_size(int(self._thumb_size * 1.25))

    def zoom_out(self):
        for s in reversed(self._thumb_sizes):
            if s < self._thumb_size:
                self.set_thumb_size(s)
                return
        self.set_thumb_size(int(self._thumb_size * 0.8))

    # ====================================================================
    # 滚动 API
    # ====================================================================

    def scroll_to(self, index: int):
        self.ensure_visible(index)

    def ensure_visible(self, index: int):
        """index 为数据索引；自动按当前显示顺序计算位置。"""
        if not (0 <= index < len(self._items)):
            return
        pos = self._display_pos_of(index)
        row = pos // max(1, self._cols)
        y = row * self._cell_h
        y2 = y + self._cell_h
        cv_h = self._canvas.winfo_height()
        view_top = self._canvas.canvasy(0)
        view_bottom = view_top + cv_h
        if y < view_top:
            total_h = max(1, self._rows * self._cell_h)
            self._canvas.yview_moveto(y / total_h)
        elif y2 > view_bottom:
            total_h = max(1, self._rows * self._cell_h)
            self._canvas.yview_moveto((y2 - cv_h) / total_h)
        self._schedule_redraw_visible()

    # ====================================================================
    # 布局与渲染（虚拟化核心）
    # ====================================================================

    def _on_canvas_configure(self, _event=None):
        self._relayout()

    def _relayout(self, force: bool = False):
        cw = max(1, self._canvas.winfo_width())

        if self._view_mode == "details":
            # 详情视图：每行一项，行宽 = max(canvas宽度, 列总宽)
            new_widths = self._compute_column_widths()
            total_col_w = sum(new_widths)
            new_cols = 1
            new_cell_w = max(cw, total_col_w)
            new_cell_h = self._details_row_height
            new_rows = len(self._items)
            width_changed = new_widths != self._effective_col_widths
            if width_changed:
                self._effective_col_widths = new_widths
                self._build_details_header()
            else:
                # 即使列宽未变，也要让表头 scrollregion 跟上画布宽度
                h = self._details_header_height
                try:
                    self._header_canvas.configure(
                        scrollregion=(0, 0, max(total_col_w, cw), h)
                    )
                except tk.TclError:
                    pass
            cell_changed = (new_cell_w != self._cell_w or new_cell_h != self._cell_h)
            if cell_changed:
                self._cell_w = new_cell_w
                self._cell_h = new_cell_h
            if (not force) and not cell_changed and not width_changed and \
                    new_cols == self._cols and new_rows == self._rows:
                self._schedule_redraw_visible()
                return
            self._cols = new_cols
            self._rows = max(0, new_rows)
            scroll_w = new_cell_w
        else:
            # 缩略图视图：根据 cell 宽度反推列数
            new_cols = max(1, cw // max(1, self._cell_w))
            new_rows = (len(self._items) + new_cols - 1) // max(1, new_cols)
            if (not force) and new_cols == self._cols and new_rows == self._rows:
                self._schedule_redraw_visible()
                return
            self._cols = new_cols
            self._rows = max(0, new_rows)
            scroll_w = cw

        total_h = self._rows * self._cell_h
        self._canvas.delete("all")
        self._cell_items.clear()
        self._canvas.configure(scrollregion=(0, 0, scroll_w, max(total_h, 1)))
        self._schedule_redraw_visible()

    def _schedule_redraw_visible(self):
        if self._scroll_after:
            try:
                self.after_cancel(self._scroll_after)
            except Exception:
                pass
        self._scroll_after = self.after_idle(self._redraw_visible)

    def _fire_event(self, sequence: str, *, data: Optional[dict] = None):
        """触发虚拟事件 + 直接调用对应 Python 回调（如果设置了）。"""
        self._last_event_data = data
        # 先派发 Python 回调（同步执行 → 不依赖事件队列时序）
        cb_map = {
            EVENT_IMAGELIST_ROW_CLICKED: self._on_row_click,
            EVENT_IMAGELIST_CELL_CLICKED: self._on_cell_click,
            EVENT_IMAGELIST_SORT_CHANGED: self._on_sort_changed,
            EVENT_IMAGELIST_COLUMN_RESIZED: self._on_column_resized,
            EVENT_IMAGELIST_CELL_VALUE_CHANGED: getattr(self, "_on_cell_value_changed", None),
            EVENT_IMAGELIST_BUTTON_CLICKED: getattr(self, "_on_button_clicked", None),
        }
        cb = cb_map.get(sequence)
        if cb is not None:
            try:
                cb(data or {})
            except Exception:
                logger.exception("HY127_ImageList callback failed for %s", sequence)
        try:
            self.event_generate(sequence, when="tail")
        except tk.TclError:
            pass

    def last_event_data(self) -> Optional[dict]:
        """获取最近一次 _fire_event 携带的数据（行/单元格/列事件用）。"""
        return getattr(self, "_last_event_data", None)

    def _on_yscroll_set(self, *args):
        self._vsb.set(*args)
        # 滚动期间挂起 hover
        import time
        self._suspend_hover_until = time.monotonic() + 0.25
        self._cancel_hover()
        # 滚动时如果有编辑态：commit
        if self._editing is not None:
            self._commit_edit()
        self._schedule_redraw_visible()

    def _on_yscroll_command(self, *args):
        self._canvas.yview(*args)

    def _on_xscroll_set(self, *args):
        """主 Canvas 横向位置变化 → 更新 hsb，同步表头横向滚动。"""
        self._hsb.set(*args)
        # 表头跟随主体一起滚
        try:
            if args:
                first = float(args[0])
                self._header_canvas.xview_moveto(first)
        except (ValueError, tk.TclError):
            pass
        # 自动隐藏：完全在视图内时藏起来
        try:
            first, last = float(args[0]), float(args[1])
            if first <= 0.0 and last >= 1.0:
                self._hsb.grid_remove()
            else:
                self._hsb.grid()
        except (ValueError, IndexError, tk.TclError):
            pass

    def _on_hscroll_command(self, *args):
        """用户拖动水平滚动条 → 同时移动主体和表头。"""
        self._canvas.xview(*args)
        try:
            self._header_canvas.xview(*args)
        except tk.TclError:
            pass

    def _visible_index_range(self) -> tuple[int, int]:
        if not self._items:
            return (0, -1)
        cv_h = max(1, self._canvas.winfo_height())
        view_top = self._canvas.canvasy(0)
        view_bottom = view_top + cv_h
        # 上下各预渲染一行做缓冲
        first_row = max(0, int(view_top // self._cell_h) - 1)
        last_row = min(self._rows - 1, int(view_bottom // self._cell_h) + 1)
        first = first_row * self._cols
        last = min(len(self._items) - 1, (last_row + 1) * self._cols - 1)
        return (first, last)

    def _cell_box(self, index: int) -> tuple[int, int, int, int]:
        """返回 cell 的 (x0, y0, x1, y1)（绝对画布坐标）。"""
        row = index // max(1, self._cols)
        col = index % max(1, self._cols)
        x0 = col * self._cell_w
        y0 = row * self._cell_h
        return (x0, y0, x0 + self._cell_w, y0 + self._cell_h)

    def _thumb_box(self, index: int) -> tuple[int, int, int, int]:
        x0, y0, x1, y1 = self._cell_box(index)
        tx0 = x0 + self._cell_padx
        ty0 = y0 + self._cell_pady
        tx1 = tx0 + self._thumb_size
        ty1 = ty0 + self._thumb_size
        return (tx0, ty0, tx1, ty1)

    def _redraw_visible(self):
        self._scroll_after = None
        if not self._items:
            self._canvas.delete("all")
            self._cell_items.clear()
            return
        first, last = self._visible_index_range()
        visible_set = set(range(first, last + 1))

        # 1) 删除已离开可视区的 cell
        for idx in list(self._cell_items.keys()):
            if idx not in visible_set:
                self._destroy_cell(idx)

        # 2) 新可视区里没绘制的，创建
        for idx in range(first, last + 1):
            if idx not in self._cell_items:
                self._create_cell(idx)
            else:
                self._refresh_cell_state(idx)

    def _create_cell(self, pos: int):
        data_idx = self._data_index(pos)
        if self._view_mode == "details":
            self._create_details_cell(pos, data_idx)
        else:
            self._create_thumbnail_cell(pos, data_idx)

    def _create_thumbnail_cell(self, pos: int, data_idx: int):
        x0, y0, x1, y1 = self._cell_box(pos)
        tx0, ty0, tx1, ty1 = self._thumb_box(pos)
        item = self._items[data_idx]
        sel_fill, sel_outline, _ = self._select_colors()
        is_sel = data_idx in self._selected
        is_cursor = data_idx == self._cursor_index

        # 选择背景矩形
        rect_id = self._canvas.create_rectangle(
            x0 + 2, y0 + 2, x1 - 2, y1 - 2,
            fill=sel_fill if is_sel else "",
            outline=sel_outline if is_sel else (self._theme_cursor_outline if is_cursor else ""),
            width=2 if (is_sel or is_cursor) else 0,
            tags=("cell", f"cell_{pos}"),
        )

        # 缩略图（先放占位图，加载完再替换）
        photo = self._lookup_or_request_thumb(item, self._thumb_size)
        image_id = self._canvas.create_image(
            (tx0 + tx1) // 2, (ty0 + ty1) // 2,
            image=photo,
            tags=("cell", f"cell_{pos}", "thumb"),
        )

        caption_id = None
        if self._show_caption:
            caption_y = ty1 + 2
            caption_id = self._canvas.create_text(
                (x0 + x1) // 2,
                caption_y,
                text=self._wrap_caption(item["caption"], self._cell_w - 4),
                anchor=N,
                font=self._font,
                fill=self._theme_text,
                width=self._cell_w - 8,
                tags=("cell", f"cell_{pos}", "caption"),
            )

        all_ids = [rect_id, image_id]
        if caption_id is not None:
            all_ids.append(caption_id)
        self._cell_items[pos] = {
            "data_idx": data_idx,
            "rect": rect_id,
            "image": image_id,
            "caption": caption_id,
            "thumb_size": self._thumb_size,
            "all_ids": all_ids,
        }

    def _create_details_cell(self, pos: int, data_idx: int):
        x0, y0, x1, y1 = self._cell_box(pos)
        item = self._items[data_idx]
        meta = self._ensure_meta(item["path"])
        sel_fill, sel_outline, _ = self._select_colors()
        is_sel = data_idx in self._selected
        is_cursor = data_idx == self._cursor_index
        is_alt = (pos % 2 == 1)

        # 行背景：选中 > 光标 > 斑马纹 > 透明
        if is_sel:
            bg_fill = sel_fill
            bg_outline = sel_outline
            bg_width = 1
        elif is_cursor:
            bg_fill = ""
            bg_outline = self._theme_cursor_outline
            bg_width = 1
        elif is_alt:
            bg_fill = self._details_alt_row_bg
            bg_outline = ""
            bg_width = 0
        else:
            bg_fill = ""
            bg_outline = ""
            bg_width = 0

        rect_id = self._canvas.create_rectangle(
            x0, y0, x1, y1,
            fill=bg_fill, outline="", width=0,
            tags=("cell", f"cell_{pos}"),
        )

        all_ids = [rect_id]

        # 行底横线（行与行之间的分隔线）
        if self._details_show_h_grid:
            line_id = self._canvas.create_line(
                x0, y1 - 1, x1, y1 - 1,
                fill=self._details_grid_color,
                tags=("cell", f"cell_{pos}"),
            )
            all_ids.append(line_id)

        col_widths = self._effective_col_widths or self._compute_column_widths()
        offsets = [x0]
        for w in col_widths:
            offsets.append(offsets[-1] + w)

        # 列竖线（列与列之间的分隔线）
        if self._details_show_v_grid:
            for i in range(len(col_widths) - 1):
                vx = offsets[i + 1] - 1
                vline_id = self._canvas.create_line(
                    vx, y0, vx, y1 - 1,
                    fill=self._details_grid_color,
                    tags=("cell", f"cell_{pos}", "vgrid"),
                )
                all_ids.append(vline_id)

        image_id = None
        text_ids: dict[str, int] = {}

        for i, col in enumerate(self._details_columns):
            cx0 = offsets[i]
            cw = col_widths[i] if i < len(col_widths) else 0
            ctype = col.get("type", "text")
            anchor_str = col.get("anchor", "w")
            ctrl_type = col.get("control")

            if ctrl_type:
                # 列内嵌控件
                ids = self._draw_cell_control(
                    ctrl_type, col, item, data_idx, pos, cx0, y0, cw, y1 - y0,
                )
                all_ids.extend(ids)
            elif ctype == "image":
                # 小缩略图居中
                photo = self._lookup_or_request_thumb(item, self._details_thumb_size)
                image_id = self._canvas.create_image(
                    cx0 + cw // 2, (y0 + y1) // 2,
                    image=photo,
                    tags=("cell", f"cell_{pos}", "thumb"),
                )
                all_ids.append(image_id)
            else:
                getter = col.get("getter")
                formatter = col.get("formatter")
                try:
                    if getter is not None:
                        if ctype == "meta":
                            raw = getter(item, meta)
                        else:
                            raw = getter(item)
                    else:
                        raw = self._extract_column_value(col, item)
                    if formatter is not None:
                        text = formatter(raw, item)
                    else:
                        text = self._default_format_value(col, raw, meta)
                except Exception:
                    text = ""
                # 锚点 → Canvas anchor
                if anchor_str == "e":
                    tx = cx0 + cw - 8
                    tk_anchor = E
                elif anchor_str == "center":
                    tx = cx0 + cw // 2
                    tk_anchor = CENTER
                else:
                    tx = cx0 + 8
                    tk_anchor = W
                font = col.get("font") or self._font
                fg = col.get("fg") or self._theme_text
                wrap_opt = col.get("wrap")
                if wrap_opt:
                    line_h = 16
                    try:
                        if hasattr(font, "metrics"):
                            line_h = max(1, int(font.metrics("linespace")))
                    except Exception:
                        pass
                    # wrap 可以是 bool 或 int(显式指定行数)
                    if isinstance(wrap_opt, bool):
                        # bool=True 时，按行高自动推断；至少 2 行
                        avail = max(1, y1 - y0 - 4)
                        max_lines = max(2, avail // line_h)
                    else:
                        try:
                            max_lines = max(1, int(wrap_opt))
                        except Exception:
                            max_lines = 2
                    shown = self._wrap_text_to_width(
                        str(text), max(20, cw - 12), max_lines, font=font,
                    )
                    # 单行结果按垂直居中绘制；多行才走顶端对齐
                    if "\n" not in shown:
                        ty = (y0 + y1) // 2
                        if anchor_str == "e":
                            tx = cx0 + cw - 8
                            tk_anchor = E
                            justify = RIGHT
                        elif anchor_str == "center":
                            tx = cx0 + cw // 2
                            tk_anchor = CENTER
                            justify = CENTER
                        else:
                            tx = cx0 + 8
                            tk_anchor = W
                            justify = LEFT
                    else:
                        ty = y0 + 3
                        if anchor_str == "e":
                            tx = cx0 + cw - 8
                            tk_anchor = NE
                            justify = RIGHT
                        elif anchor_str == "center":
                            tx = cx0 + cw // 2
                            tk_anchor = N
                            justify = CENTER
                        else:
                            tx = cx0 + 8
                            tk_anchor = NW
                            justify = LEFT
                    tid = self._canvas.create_text(
                        tx, ty, text=shown, anchor=tk_anchor,
                        width=max(20, cw - 12), justify=justify,
                        font=font, fill=fg,
                        tags=("cell", f"cell_{pos}", f"col_{col['key']}"),
                    )
                else:
                    ty = (y0 + y1) // 2
                    shown = self._truncate_to_width(
                        str(text), max(20, cw - 12), font=font,
                    )
                    tid = self._canvas.create_text(
                        tx, ty, text=shown, anchor=tk_anchor,
                        font=font, fill=fg,
                        tags=("cell", f"cell_{pos}", f"col_{col['key']}"),
                    )
                text_ids[col["key"]] = tid
                all_ids.append(tid)

        outline_id = self._canvas.create_rectangle(
            x0, y0, x1 - 1, y1 - 1,
            fill="", outline=bg_outline, width=bg_width,
            tags=("cell", f"cell_{pos}", "row_outline"),
        )
        all_ids.append(outline_id)

        self._cell_items[pos] = {
            "data_idx": data_idx,
            "rect": rect_id,
            "outline": outline_id,
            "image": image_id,
            "caption": None,
            "thumb_size": self._details_thumb_size,
            "text_ids": text_ids,
            "all_ids": all_ids,
        }

    def _destroy_cell(self, index: int):
        ids = self._cell_items.pop(index, None)
        if not ids:
            return
        for cid in ids.get("all_ids", []):
            try:
                self._canvas.delete(cid)
            except tk.TclError:
                pass

    def _rebuild_visible_cells(self):
        """重建当前可视区的 cell，确保控件图形与最新值一致。"""
        if not self._items:
            self._canvas.delete("all")
            self._cell_items.clear()
            return
        first, last = self._visible_index_range()
        for pos in range(first, last + 1):
            if pos in self._cell_items:
                self._destroy_cell(pos)
        for pos in range(first, last + 1):
            if 0 <= pos < len(self._items):
                self._create_cell(pos)

    def _refresh_cell_state(self, pos: int):
        ids = self._cell_items.get(pos)
        if not ids:
            return
        data_idx = ids.get("data_idx", pos)
        sel_fill, sel_outline, _ = self._select_colors()
        is_sel = data_idx in self._selected
        is_cursor = data_idx == self._cursor_index
        try:
            if self._view_mode == "details":
                is_alt = (pos % 2 == 1)
                if is_sel:
                    self._canvas.itemconfigure(
                        ids["rect"],
                        fill=sel_fill, outline="", width=0,
                    )
                    self._canvas.itemconfigure(
                        ids["outline"], outline=sel_outline, width=1,
                    )
                elif is_cursor:
                    self._canvas.itemconfigure(
                        ids["rect"],
                        fill="", outline="", width=0,
                    )
                    self._canvas.itemconfigure(
                        ids["outline"], outline=self._theme_cursor_outline, width=1,
                    )
                elif is_alt:
                    self._canvas.itemconfigure(
                        ids["rect"],
                        fill=self._details_alt_row_bg, outline="", width=0,
                    )
                    self._canvas.itemconfigure(
                        ids["outline"], outline="", width=0,
                    )
                else:
                    self._canvas.itemconfigure(
                        ids["rect"], fill="", outline="", width=0,
                    )
                    self._canvas.itemconfigure(
                        ids["outline"], outline="", width=0,
                    )
            else:
                self._canvas.itemconfigure(
                    ids["rect"],
                    fill=sel_fill if is_sel else "",
                    outline=sel_outline if is_sel else (self._theme_cursor_outline if is_cursor else ""),
                    width=2 if (is_sel or is_cursor) else 0,
                )
        except tk.TclError:
            pass

    # ====================================================================
    # 列内嵌控件：轻量类（纯 Canvas 绘制）
    # ====================================================================

    def _control_value(self, col: dict, item: dict):
        """统一的取值入口：value_getter / item[key] / 默认。"""
        getter = col.get("value_getter") or col.get("getter")
        if getter is not None:
            try:
                return getter(item)
            except Exception:
                return None
        key = col.get("key")
        if isinstance(item, dict) and key in item:
            return item[key]
        if isinstance(item, dict):
            ud = item.get("user_data")
            if isinstance(ud, dict) and key in ud:
                return ud[key]
        return None

    def _control_set_value(self, col: dict, item: dict, value):
        """统一的写值入口：value_setter / 写到 user_data[key]。"""
        setter = col.get("value_setter")
        if setter is not None:
            try:
                setter(item, value)
                return True
            except Exception:
                return False
        key = col.get("key")
        if not key:
            return False
        # 默认写到 item 自身（如果是 dict） + user_data
        try:
            item[key] = value
        except Exception:
            pass
        try:
            ud = item.get("user_data")
            if not isinstance(ud, dict):
                ud = {}
                item["user_data"] = ud
            ud[key] = value
        except Exception:
            pass
        return True

    def _draw_cell_control(self, ctrl_type: str, col: dict, item: dict,
                           data_idx: int, pos: int,
                           cx0: int, y0: int, cw: int, ch: int) -> list:
        ctrl_type = ctrl_type.lower()
        if ctrl_type == "checkbox":
            return self._draw_checkbox(col, item, pos, cx0, y0, cw, ch)
        if ctrl_type == "radio":
            return self._draw_radio(col, item, pos, cx0, y0, cw, ch)
        if ctrl_type == "button":
            return self._draw_button(col, item, pos, cx0, y0, cw, ch)
        if ctrl_type == "progress":
            return self._draw_progress(col, item, pos, cx0, y0, cw, ch)
        if ctrl_type == "rating":
            return self._draw_rating(col, item, pos, cx0, y0, cw, ch)
        if ctrl_type in ("entry", "combobox"):
            # 非编辑态：显示文本（与 text 列相同）+ combobox 末尾画 ▾
            return self._draw_text_like_control(ctrl_type, col, item, pos, cx0, y0, cw, ch)
        return []

    def _draw_checkbox(self, col, item, pos, cx0, y0, cw, ch) -> list:
        sz = max(12, min(18, ch - 12))
        cx = cx0 + cw // 2 - sz // 2
        cy = y0 + (ch - sz) // 2
        checked = bool(self._control_value(col, item))
        fill = self._theme_check_fill if checked else self._theme_surface
        outline = self._theme_accent if checked else self._theme_check_outline
        rect = self._canvas.create_rectangle(
            cx, cy, cx + sz, cy + sz,
            fill=fill, outline=outline, width=1,
            tags=("cell", f"cell_{pos}", "ctrl", f"ctrl_{col['key']}"),
        )
        ids = [rect]
        if checked:
            check = self._canvas.create_line(
                cx + sz * 0.22, cy + sz * 0.55,
                cx + sz * 0.45, cy + sz * 0.78,
                cx + sz * 0.80, cy + sz * 0.28,
                fill=self._theme_select_fg, width=2, capstyle="round", joinstyle="round",
                tags=("cell", f"cell_{pos}", "ctrl", f"ctrl_{col['key']}"),
            )
            ids.append(check)
        return ids

    def _draw_radio(self, col, item, pos, cx0, y0, cw, ch) -> list:
        value = self._control_value(col, item)
        options = self._radio_options(col)
        if options:
            return self._draw_radio_group(col, item, pos, cx0, y0, cw, ch, options, value)

        sz = max(12, min(18, ch - 12))
        cx = cx0 + cw // 2 - sz // 2
        cy = y0 + (ch - sz) // 2
        radio_value = col.get("radio_value")
        checked = (value == radio_value) if radio_value is not None else bool(value)
        outline = self._theme_accent if checked else self._theme_check_outline
        oval = self._canvas.create_oval(
            cx, cy, cx + sz, cy + sz,
            outline=outline, width=1, fill=self._theme_surface,
            tags=("cell", f"cell_{pos}", "ctrl", f"ctrl_{col['key']}"),
        )
        ids = [oval]
        if checked:
            inner = sz * 0.45
            ix0 = cx + (sz - inner) / 2
            iy0 = cy + (sz - inner) / 2
            dot = self._canvas.create_oval(
                ix0, iy0, ix0 + inner, iy0 + inner,
                fill=self._theme_accent, outline="",
                tags=("cell", f"cell_{pos}", "ctrl", f"ctrl_{col['key']}"),
            )
            ids.append(dot)
        return ids

    def _radio_options(self, col: dict) -> list[dict]:
        raw = col.get("radio_options")
        if raw is None:
            raw = col.get("options")
        out = []
        for opt in raw or []:
            if isinstance(opt, dict):
                value = opt.get("value", opt.get("id", opt.get("label")))
                label = opt.get("label", value)
            else:
                value = opt
                label = opt
            out.append({"value": value, "label": "" if label is None else str(label)})
        return out

    def _radio_group_layout(self, col, cx0, y0, cw, ch, options: list[dict]) -> list[dict]:
        if not options:
            return []
        sz = max(12, min(18, ch - 12))
        pad_x = 6
        gap = 8
        inner_w = max(1, cw - 2 * pad_x)
        slot_w = inner_w / max(1, len(options))
        cy = y0 + (ch - sz) / 2
        ty = y0 + ch / 2
        layout = []
        for i, opt in enumerate(options):
            sx0 = cx0 + pad_x + i * slot_w
            sx1 = sx0 + slot_w
            text = opt.get("label", "")
            try:
                tw = self._font.measure(text)
            except Exception:
                tw = len(text) * 7
            total_w = sz + (gap if text else 0) + tw
            start_x = sx0 + max(0, (slot_w - total_w) / 2)
            layout.append({
                "value": opt.get("value"),
                "label": text,
                "slot_x0": sx0,
                "slot_x1": sx1,
                "radio_x": start_x,
                "radio_y": cy,
                "text_x": start_x + sz + gap,
                "text_y": ty,
                "size": sz,
            })
        return layout

    def _draw_radio_group(self, col, item, pos, cx0, y0, cw, ch, options: list[dict], value) -> list:
        ids = []
        layout = self._radio_group_layout(col, cx0, y0, cw, ch, options)
        font = col.get("font") or self._font
        fg = col.get("fg") or self._theme_text
        for opt in layout:
            checked = (value == opt["value"])
            outline = self._theme_accent if checked else self._theme_check_outline
            oval = self._canvas.create_oval(
                opt["radio_x"], opt["radio_y"],
                opt["radio_x"] + opt["size"], opt["radio_y"] + opt["size"],
                outline=outline, width=1, fill=self._theme_surface,
                tags=("cell", f"cell_{pos}", "ctrl", f"ctrl_{col['key']}"),
            )
            ids.append(oval)
            if checked:
                inner = opt["size"] * 0.45
                ix0 = opt["radio_x"] + (opt["size"] - inner) / 2
                iy0 = opt["radio_y"] + (opt["size"] - inner) / 2
                dot = self._canvas.create_oval(
                    ix0, iy0, ix0 + inner, iy0 + inner,
                    fill=self._theme_accent, outline="",
                    tags=("cell", f"cell_{pos}", "ctrl", f"ctrl_{col['key']}"),
                )
                ids.append(dot)
            if opt["label"]:
                tid = self._canvas.create_text(
                    opt["text_x"], opt["text_y"],
                    text=opt["label"], anchor=W, font=font, fill=fg,
                    tags=("cell", f"cell_{pos}", "ctrl", f"ctrl_{col['key']}"),
                )
                ids.append(tid)
        return ids

    def _button_style_colors(self, style_name: str) -> dict:
        style = self._get_style_instance()
        try:
            colors = style.colors
            base = getattr(colors, style_name, None)
        except Exception:
            base = None
        if not base:
            if style_name == "light":
                base = self._theme_surface
            elif style_name in ("link", "outline"):
                base = self._theme_accent
            else:
                base = self._theme_accent
        fg = self._theme_select_fg if self._luminance(base) < 0.62 else self._theme_fg
        if style_name == "light":
            fg = self._theme_fg
        return {"fill": base, "fg": fg, "outline": base}

    def _draw_button(self, col, item, pos, cx0, y0, cw, ch) -> list:
        text = col.get("text", "")
        if callable(text):
            try:
                text = text(item) or ""
            except Exception:
                text = ""
        style_name = (col.get("bootstyle") or "primary").lower().split("-")[0]
        if "outline" in (col.get("bootstyle") or ""):
            style = dict(self._button_style_colors(style_name))
            style.update({"fill": "", "fg": style["outline"]})
        else:
            style = self._button_style_colors(style_name)
        # 按钮区域：左右各留 6px padding
        bx0 = cx0 + 6
        by0 = y0 + 4
        bx1 = cx0 + cw - 6
        by1 = y0 + ch - 4
        rect = self._canvas.create_rectangle(
            bx0, by0, bx1, by1,
            fill=style["fill"], outline=style["outline"], width=1,
            tags=("cell", f"cell_{pos}", "ctrl", f"ctrl_{col['key']}", "btn"),
        )
        tid = self._canvas.create_text(
            (bx0 + bx1) // 2, (by0 + by1) // 2,
            text=str(text), fill=style["fg"], font=col.get("font") or self._font,
            tags=("cell", f"cell_{pos}", "ctrl", f"ctrl_{col['key']}", "btn"),
        )
        return [rect, tid]

    def _draw_progress(self, col, item, pos, cx0, y0, cw, ch) -> list:
        try:
            v = float(self._control_value(col, item) or 0)
        except (TypeError, ValueError):
            v = 0
        v_max = float(col.get("max", 100))
        v = max(0.0, min(v_max, v))
        ratio = v / v_max if v_max else 0
        bar_h = max(8, min(14, ch - 14))
        bx0 = cx0 + 8
        by0 = y0 + (ch - bar_h) // 2
        bx1 = cx0 + cw - 8
        by1 = by0 + bar_h
        track = self._canvas.create_rectangle(
            bx0, by0, bx1, by1,
            fill=self._theme_progress_track, outline=self._theme_border,
            tags=("cell", f"cell_{pos}", "ctrl", f"ctrl_{col['key']}"),
        )
        fill_color = col.get("color") or self._theme_accent
        ids = [track]
        fw = int((bx1 - bx0) * ratio)
        if fw > 0:
            fill_id = self._canvas.create_rectangle(
                bx0, by0, bx0 + fw, by1,
                fill=fill_color, outline="",
                tags=("cell", f"cell_{pos}", "ctrl", f"ctrl_{col['key']}"),
            )
            ids.append(fill_id)
        if col.get("show_percent", True):
            pct_text = f"{int(ratio * 100)}%"
            tid = self._canvas.create_text(
                (bx0 + bx1) // 2, (by0 + by1) // 2,
                text=pct_text, fill=self._theme_text,
                font=col.get("font") or self._font,
                tags=("cell", f"cell_{pos}", "ctrl", f"ctrl_{col['key']}"),
            )
            ids.append(tid)
        return ids

    def _draw_rating(self, col, item, pos, cx0, y0, cw, ch) -> list:
        try:
            v = int(self._control_value(col, item) or 0)
        except (TypeError, ValueError):
            v = 0
        n = int(col.get("max", 5))
        v = max(0, min(n, v))
        sz = max(12, min(18, ch - 14))
        spacing = 2
        total_w = n * sz + (n - 1) * spacing
        anchor = (col.get("anchor") or "w").lower()
        if anchor == "center":
            sx = cx0 + (cw - total_w) // 2
        elif anchor == "e":
            sx = cx0 + cw - total_w - 6
        else:
            sx = cx0 + 6
        sy = y0 + (ch - sz) // 2
        ids = []
        for i in range(n):
            cx = sx + i * (sz + spacing)
            filled = (i < v)
            color = self._theme_rating_fill if filled else self._theme_rating_empty
            star_id = self._canvas.create_polygon(
                self._star_points(cx, sy, sz),
                fill=color,
                outline=self._theme_rating_outline if filled else self._theme_check_outline,
                tags=("cell", f"cell_{pos}", "ctrl", f"ctrl_{col['key']}",
                      f"star_{i + 1}"),
            )
            ids.append(star_id)
        return ids

    @staticmethod
    def _star_points(x: int, y: int, size: int) -> list:
        """计算 5 角星顶点坐标。"""
        import math
        cx = x + size / 2
        cy = y + size / 2
        outer = size / 2
        inner = outer * 0.5
        pts = []
        for i in range(10):
            angle = math.pi / 2 + i * math.pi / 5
            r = outer if i % 2 == 0 else inner
            pts.extend([cx - r * math.cos(angle), cy - r * math.sin(angle)])
        return pts

    def _draw_text_like_control(self, ctrl_type, col, item, pos, cx0, y0, cw, ch) -> list:
        """Entry / Combobox 在非编辑态时按文本渲染 + Combobox 末尾画 ▾。"""
        v = self._control_value(col, item)
        formatter = col.get("formatter")
        try:
            text = formatter(v, item) if formatter else ("" if v is None else str(v))
        except Exception:
            text = ""
        anchor_str = (col.get("anchor") or "w").lower()
        # 给 combobox 留出更明显的下拉按钮区
        combo_btn_w = max(24, min(34, ch))
        right_pad = combo_btn_w + 8 if ctrl_type == "combobox" else 8
        if anchor_str == "e":
            tx = cx0 + cw - right_pad
            tk_anchor = E
        elif anchor_str == "center":
            tx = cx0 + (cw - right_pad) // 2
            tk_anchor = CENTER
        else:
            tx = cx0 + 8
            tk_anchor = W
        ty = y0 + ch // 2
        shown = self._truncate_to_width(text, max(20, cw - 12 - (right_pad - 8)))
        font = col.get("font") or self._font
        fg = col.get("fg") or self._theme_text
        ids = []
        tid = self._canvas.create_text(
            tx, ty, text=shown, anchor=tk_anchor,
            font=font, fill=fg,
            tags=("cell", f"cell_{pos}", "ctrl", f"ctrl_{col['key']}"),
        )
        ids.append(tid)
        if ctrl_type == "combobox":
            btn_x0 = cx0 + cw - combo_btn_w - 4
            btn_y0 = y0 + 3
            btn_x1 = cx0 + cw - 4
            btn_y1 = y0 + ch - 3
            btn_id = self._canvas.create_rectangle(
                btn_x0, btn_y0, btn_x1, btn_y1,
                fill=self._theme_combo_btn_bg, outline=self._theme_border, width=1,
                tags=("cell", f"cell_{pos}", "ctrl", f"ctrl_{col['key']}",
                      "combo_arrow"),
            )
            ids.append(btn_id)
            arrow_id = self._canvas.create_text(
                (btn_x0 + btn_x1) / 2, ty, text="▼", anchor=CENTER,
                font=col.get("arrow_font") or font, fill=self._theme_muted_fg,
                tags=("cell", f"cell_{pos}", "ctrl", f"ctrl_{col['key']}",
                      "combo_arrow"),
            )
            ids.append(arrow_id)
        return ids

    # ====================================================================
    # 列内嵌控件：交互 + 编辑态
    # ====================================================================

    def _find_control_column(self, col_key: str) -> Optional[dict]:
        if not col_key:
            return None
        for col in self._details_columns:
            if col.get("key") == col_key and col.get("control"):
                return col
        return None

    def _maybe_handle_control_press(self, event, data_idx: int, col_key: str) -> bool:
        """处理 control 列上的鼠标按下。返回 True 表示已处理，跳过常规选择/拖动。"""
        col = self._find_control_column(col_key)
        if col is None:
            return False
        ctrl_type = col.get("control", "").lower()
        if not ctrl_type:
            return False
        if not (0 <= data_idx < len(self._items)):
            return False
        item = self._items[data_idx]
        # 禁用？
        if col.get("disabled"):
            return True  # 拦截但不动作

        if ctrl_type == "checkbox":
            old = bool(self._control_value(col, item))
            new = not old
            self._control_set_value(col, item, new)
            self._refresh_pos_cell(self._display_pos_of(data_idx))
            self._fire_event(
                EVENT_IMAGELIST_CELL_VALUE_CHANGED,
                data={"index": data_idx, "item": item, "column": col_key,
                      "old": old, "new": new},
            )
            on_change = col.get("on_change")
            if callable(on_change):
                try:
                    on_change(item, new)
                except Exception as e:
                    print(f"[HY127_ImageList] on_change error: {e}")
            return True

        if ctrl_type == "radio":
            options = self._radio_options(col)
            radio_value = col.get("radio_value")
            old = self._control_value(col, item)

            if options:
                cw = self._effective_col_width_for(col_key)
                cx0 = self._col_x0(col_key)
                if cw is None or cx0 is None:
                    return True
                xc = self._canvas.canvasx(event.x)
                layout = self._radio_group_layout(
                    col, cx0, 0, cw, self._details_row_height, options,
                )
                hit = None
                for opt in layout:
                    if opt["slot_x0"] <= xc < opt["slot_x1"]:
                        hit = opt["value"]
                        break
                if hit is None:
                    return True
                new = hit
                if old == new:
                    if col.get("allow_uncheck"):
                        new = None
                    else:
                        return True
                self._control_set_value(col, item, new)
                self._refresh_pos_cell(self._display_pos_of(data_idx))
            elif radio_value is not None:
                # —— 高级用法：行内多列互斥（多个 radio 列共享同一字段，每列代表一个值）
                # 点击 cat_a 列 → 把 category 字段改为 "A"
                new = radio_value
                if old == new:
                    if col.get("allow_uncheck"):
                        new = None
                    else:
                        return True
                self._control_set_value(col, item, new)
            else:
                # —— 默认用法：整列单选（同列里所有行只有一个被选中）
                # 点哪一行 → 当前行 True，其他所有行 False
                if bool(old):
                    if col.get("allow_uncheck"):
                        new = False
                    else:
                        return True
                else:
                    new = True
                    # 清掉同列其它行的选中
                    for j, it in enumerate(self._items):
                        if j == data_idx:
                            continue
                        if bool(self._control_value(col, it)):
                            self._control_set_value(col, it, False)
                self._control_set_value(col, item, new)

            self._fire_event(
                EVENT_IMAGELIST_CELL_VALUE_CHANGED,
                data={"index": data_idx, "item": item, "column": col_key,
                      "old": old, "new": new},
            )
            on_change = col.get("on_change")
            if callable(on_change):
                try:
                    on_change(item, new)
                except Exception as e:
                    print(f"[HY127_ImageList] on_change error: {e}")
            self._rebuild_visible_cells()
            return True

        if ctrl_type == "button":
            # 按下高亮（按下→抬起算 click）
            self._control_press = {"pos": self._display_pos_of(data_idx),
                                   "col_key": col_key, "type": "button",
                                   "data_idx": data_idx}
            return True

        if ctrl_type == "rating":
            # 计算点击的星位置
            n = int(col.get("max", 5))
            cw = self._effective_col_width_for(col_key)
            cx0 = self._col_x0(col_key)
            if cw is None or cx0 is None:
                return True
            sz = max(12, min(18, self._details_row_height - 14))
            spacing = 2
            total_w = n * sz + (n - 1) * spacing
            anchor = (col.get("anchor") or "w").lower()
            if anchor == "center":
                sx = cx0 + (cw - total_w) // 2
            elif anchor == "e":
                sx = cx0 + cw - total_w - 6
            else:
                sx = cx0 + 6
            xc = self._canvas.canvasx(event.x)
            star_idx = int((xc - sx) // (sz + spacing))
            star_idx = max(0, min(n - 1, star_idx))
            old = int(self._control_value(col, item) or 0)
            new = star_idx + 1
            if col.get("allow_zero", True) and new == old:
                new = 0
            if new == old:
                return True
            self._control_set_value(col, item, new)
            self._refresh_pos_cell(self._display_pos_of(data_idx))
            self._fire_event(
                EVENT_IMAGELIST_CELL_VALUE_CHANGED,
                data={"index": data_idx, "item": item, "column": col_key,
                      "old": old, "new": new},
            )
            on_change = col.get("on_change")
            if callable(on_change):
                try:
                    on_change(item, new)
                except Exception as e:
                    print(f"[HY127_ImageList] on_change error: {e}")
            return True

        if ctrl_type == "progress":
            # 进度条默认不交互；如果配置了 editable=True 则按比例设置
            if not col.get("editable"):
                return True
            cw = self._effective_col_width_for(col_key)
            cx0 = self._col_x0(col_key)
            if cw is None or cx0 is None:
                return True
            xc = self._canvas.canvasx(event.x)
            ratio = max(0.0, min(1.0, (xc - cx0 - 8) / max(1, cw - 16)))
            v_max = float(col.get("max", 100))
            new = ratio * v_max
            old = self._control_value(col, item) or 0
            self._control_set_value(col, item, new)
            self._refresh_pos_cell(self._display_pos_of(data_idx))
            self._fire_event(
                EVENT_IMAGELIST_CELL_VALUE_CHANGED,
                data={"index": data_idx, "item": item, "column": col_key,
                      "old": old, "new": new},
            )
            return True

        if ctrl_type in ("entry", "combobox"):
            # 文本类控件默认单击进入编辑；可通过 edit_trigger 覆盖。
            trig = (col.get("edit_trigger") or "single").lower()
            if trig == "single" and col.get("editable", True):
                self._start_edit(data_idx, col)
                return True
            # combobox 即便 trigger='double'，也可以让单击触发（更符合下拉框直觉）
            if ctrl_type == "combobox" and col.get("editable", True) \
                    and trig in ("single", "click", "double"):
                # combobox 单击就弹出
                self._start_edit(data_idx, col)
                return True
            # 否则继续走选择逻辑（不拦截）
            return False

        return False

    # ---- 按钮抬起：判断 click ----

    def _on_left_release_extra(self, event):
        """由 _on_left_release 末尾调用：处理 button 抬起时的 click 触发。"""
        if self._control_press is None:
            return
        cp = self._control_press
        self._control_press = None
        if cp.get("type") != "button":
            return
        # 抬起时还在原 cell 上才算 click
        idx, col_key = self._xy_to_pos_and_col(event.x, event.y)
        if idx == cp["data_idx"] and col_key == cp["col_key"]:
            col = self._find_control_column(col_key)
            if col is None:
                return
            item = self._items[idx]
            self._fire_event(
                EVENT_IMAGELIST_BUTTON_CLICKED,
                data={"index": idx, "item": item, "column": col_key},
            )
            on_click = col.get("on_click")
            if callable(on_click):
                try:
                    on_click(item, idx)
                except Exception as e:
                    print(f"[HY127_ImageList] on_click error: {e}")

    # ---- 工具：按 col_key 求该列的 x0 / 宽 ----

    def _details_col_index(self, col_key: str) -> Optional[int]:
        for i, c in enumerate(self._details_columns):
            if c.get("key") == col_key:
                return i
        return None

    def _col_x0(self, col_key: str) -> Optional[int]:
        i = self._details_col_index(col_key)
        if i is None:
            return None
        widths = self._effective_col_widths or self._compute_column_widths()
        return sum(widths[:i])

    def _effective_col_width_for(self, col_key: str) -> Optional[int]:
        i = self._details_col_index(col_key)
        if i is None:
            return None
        widths = self._effective_col_widths or self._compute_column_widths()
        return widths[i] if i < len(widths) else None

    def _refresh_pos_cell(self, pos: int):
        """重绘单个显示位置的 cell（control 值变化时局部刷新）。"""
        if pos is None or pos < 0:
            return
        cell = self._cell_items.get(pos)
        if cell is None:
            return
        # 仅刷新背景不够，checkbox/radio/rating 等控件需要重建图形。
        self._destroy_cell(pos)
        self._create_cell(pos)

    # ====================================================================
    # 编辑态：Entry / Combobox
    # ====================================================================

    def _start_edit(self, data_idx: int, col: dict):
        if not (0 <= data_idx < len(self._items)):
            return
        self._cancel_hover()
        self._hover_index = None
        self._hover_col_key = None
        import time
        self._suspend_hover_until = time.monotonic() + 0.8
        if self._editing is not None:
            self._commit_edit()
        item = self._items[data_idx]
        col_key = col.get("key")
        cw = self._effective_col_width_for(col_key)
        cx0 = self._col_x0(col_key)
        if cw is None or cx0 is None:
            return
        pos = self._display_pos_of(data_idx)
        # cell 行 y0
        y0 = self._row_y0_for_pos(pos)
        if y0 is None:
            return
        ch = self._details_row_height
        ctrl_type = (col.get("control") or "").lower()
        cur_val = self._control_value(col, item)
        cur_str = "" if cur_val is None else str(cur_val)

        if ctrl_type == "combobox":
            options = col.get("options") or []
            if callable(options):
                try:
                    options = options(item) or []
                except Exception:
                    options = []
            allow_text_input = bool(col.get("allow_text_input"))
            readonly = bool(col.get("readonly", not allow_text_input))
            widget = ttk.Combobox(
                self._canvas, values=list(options),
                state=("normal" if allow_text_input and not readonly else "readonly"),
                font=col.get("font") or self._font,
            )
            widget.set(cur_str)

            def _on_combo_selected(_e, w=widget):
                # 选中瞬间立即捕获新值，再延迟 commit，避免 widget 被销毁/失焦后读不到
                try:
                    new_value = w.get()
                except tk.TclError:
                    return
                self.after_idle(lambda v=new_value: self._commit_edit(forced_value=v))

            widget.bind("<<ComboboxSelected>>", _on_combo_selected)
            widget.bind("<Return>", lambda e: self._commit_edit())
            widget.bind("<Escape>", lambda e: self._cancel_edit())
        else:
            widget = ttk.Entry(
                self._canvas, font=col.get("font") or self._font,
            )
            widget.insert(0, cur_str)
            widget.select_range(0, "end")
            widget.bind("<Return>", lambda e: self._commit_edit())
            widget.bind("<Escape>", lambda e: self._cancel_edit())
            widget.bind("<FocusOut>", lambda e: self._commit_edit())

        # 用 create_window 嵌入到 canvas
        win_id = self._canvas.create_window(
            cx0 + 1, y0 + 1,
            window=widget, anchor=NW,
            width=max(20, cw - 2), height=max(16, ch - 2),
            tags=("edit_widget",),
        )
        widget.focus_set()
        self._editing = {
            "data_idx": data_idx, "pos": pos, "col_key": col_key,
            "widget": widget, "win_id": win_id,
            "original": cur_val, "ctrl_type": ctrl_type,
        }
        self._fire_event(
            EVENT_IMAGELIST_EDIT_STARTED,
            data={"index": data_idx, "item": item, "column": col_key,
                  "value": cur_val},
        )
        # combobox 自动展开
        if ctrl_type == "combobox":
            self.after_idle(lambda w=widget: self._post_combobox_dropdown(w))

    def _post_combobox_dropdown(self, widget):
        """尽量以原生方式展开 ttk.Combobox 下拉列表。"""
        try:
            widget.focus_set()
        except tk.TclError:
            return
        try:
            widget.tk.call("ttk::combobox::Post", str(widget))
            return
        except tk.TclError:
            pass
        for seq in ("<Alt-Down>", "<Down>", "<Button-1>"):
            try:
                widget.event_generate(seq)
                return
            except tk.TclError:
                continue

    def _commit_edit(self, forced_value=None):
        """提交编辑。forced_value 不为 None 时，跳过从 widget 读值（用于
        Combobox 选中瞬间已经把值捕获、避免延迟 commit 时 widget 已被销毁/失焦）。"""
        if self._editing is None:
            return
        ed = self._editing
        pos = ed.get("pos")
        self._editing = None  # 防重入
        if forced_value is not None:
            new_str = forced_value
        else:
            try:
                new_str = ed["widget"].get()
            except tk.TclError:
                new_str = ""
        # 类型转换
        col = self._find_control_column(ed["col_key"])
        new_val = new_str
        if col is not None:
            cast = col.get("cast")
            if callable(cast):
                try:
                    new_val = cast(new_str)
                except Exception:
                    new_val = ed["original"]
        try:
            self._canvas.delete(ed["win_id"])
        except tk.TclError:
            pass
        try:
            ed["widget"].destroy()
        except tk.TclError:
            pass

        old = ed["original"]
        if str(new_val) != str(old):
            data_idx = ed["data_idx"]
            if 0 <= data_idx < len(self._items):
                item = self._items[data_idx]
                if col is not None:
                    self._control_set_value(col, item, new_val)
                self._fire_event(
                    EVENT_IMAGELIST_CELL_VALUE_CHANGED,
                    data={"index": data_idx, "item": item,
                          "column": ed["col_key"], "old": old, "new": new_val},
                )
                if col is not None:
                    on_change = col.get("on_change")
                    if callable(on_change):
                        try:
                            on_change(item, new_val)
                        except Exception as e:
                            print(f"[HY127_ImageList] on_change error: {e}")
        self._fire_event(
            EVENT_IMAGELIST_EDIT_COMMITTED,
            data={"index": ed["data_idx"], "column": ed["col_key"],
                  "old": old, "new": new_val},
        )
        # 注意：_redraw_visible() 对已存在的可视 cell 只刷新选中态，不会重建
        # entry/combobox 的静态文本图形，因此提交后必须局部重建该 cell。
        if pos in self._cell_items:
            self._refresh_pos_cell(pos)
        else:
            self._redraw_visible()

    def _cancel_edit(self):
        if self._editing is None:
            return
        ed = self._editing
        self._editing = None
        try:
            self._canvas.delete(ed["win_id"])
        except tk.TclError:
            pass
        try:
            ed["widget"].destroy()
        except tk.TclError:
            pass
        self._fire_event(
            EVENT_IMAGELIST_EDIT_CANCELLED,
            data={"index": ed["data_idx"], "column": ed["col_key"],
                  "value": ed["original"]},
        )
        self._redraw_visible()

    def _start_edit_at_cursor(self):
        """F2 键：在当前光标行的第一个可编辑 entry/combobox 列上启动编辑。"""
        if self._editing is not None:
            return
        if self._cursor_index is None:
            return
        for col in self._details_columns:
            ctype = (col.get("control") or "").lower()
            if ctype in ("entry", "combobox") and col.get("editable", True):
                self._start_edit(self._cursor_index, col)
                return

    def _row_y0_for_pos(self, pos: int) -> Optional[int]:
        """获取显示位置 pos 对应行的 canvas y 坐标。"""
        if self._view_mode != "details":
            return None
        if pos is None or pos < 0:
            return None
        return pos * self._details_row_height

    def _truncate_to_width(self, text: str, max_w_px: int, font=None) -> str:
        """二分截断文字，保证不超过指定像素宽度。"""
        if not text:
            return ""
        font = font or self._font
        try:
            measured = font.measure(text) if hasattr(font, "measure") else len(text) * 7
            if measured <= max_w_px:
                return text
            ellipsis = "…"
            lo, hi = 0, len(text)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                w = font.measure(text[:mid] + ellipsis) if hasattr(font, "measure") else (mid + 1) * 7
                if w <= max_w_px:
                    lo = mid
                else:
                    hi = mid - 1
            return text[:lo] + ellipsis
        except Exception:
            return text[:24] + ("…" if len(text) > 24 else "")

    def _wrap_text_to_width(self, text: str, max_w_px: int, max_lines: int, font=None) -> str:
        """按像素宽度折行，并限制最大显示行数。"""
        if not text:
            return ""
        font = font or self._font
        max_lines = max(1, int(max_lines))
        if max_lines <= 1:
            return self._truncate_to_width(text, max_w_px, font=font)

        def _measure(s: str) -> int:
            try:
                return font.measure(s) if hasattr(font, "measure") else len(s) * 7
            except Exception:
                return len(s) * 7

        lines = []
        paragraphs = text.splitlines() or [text]
        for para in paragraphs:
            src = para or " "
            cur = ""
            for ch in src:
                cand = cur + ch
                if cur and _measure(cand) > max_w_px:
                    lines.append(cur)
                    cur = ch
                    if len(lines) >= max_lines:
                        break
                else:
                    cur = cand
            if len(lines) >= max_lines:
                break
            lines.append(cur or src[:1])
            if len(lines) >= max_lines:
                break

        if len(lines) > max_lines:
            lines = lines[:max_lines]
        joined = "\n".join(lines[:max_lines])
        if joined == text:
            return joined

        consumed = sum(len(line.replace(" ", "")) for line in lines[:max_lines])
        if consumed < len(text.replace("\n", "").replace(" ", "")):
            last = self._truncate_to_width(lines[max_lines - 1], max_w_px, font=font)
            if not last.endswith("…"):
                last = self._truncate_to_width(last + "…", max_w_px, font=font)
            lines[max_lines - 1] = last
        return "\n".join(lines[:max_lines])

    def _wrap_caption(self, text: str, _max_w_px: int) -> str:
        # tk Canvas text 用 width 自动按像素折行，行数控制简化为：超长就截断 + …
        if not text:
            return ""
        if self._caption_lines >= 2:
            return text
        # 只显示一行 → 截断
        try:
            avail = max(40, self._cell_w - 8)
            measured = self._font.measure(text) if hasattr(self._font, "measure") else len(text) * 7
            if measured <= avail:
                return text
            ellipsis = "…"
            # 二分截断
            lo, hi = 0, len(text)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                w = self._font.measure(text[:mid] + ellipsis) if hasattr(self._font, "measure") else (mid + 1) * 7
                if w <= avail:
                    lo = mid
                else:
                    hi = mid - 1
            return text[:lo] + ellipsis
        except Exception:
            return text[:24] + ("…" if len(text) > 24 else "")

    # ====================================================================
    # 缩略图获取（同步 LRU + 同步磁盘 + 异步队列）
    # ====================================================================

    def _placeholder_image(self, size: Optional[int] = None) -> Optional[tk.PhotoImage]:
        return PLACEHOLDERS.get("loading", size or self._current_thumb_size())

    def _error_image(self, size: Optional[int] = None) -> Optional[tk.PhotoImage]:
        return PLACEHOLDERS.get("error", size or self._current_thumb_size())

    def _current_thumb_size(self) -> int:
        return self._details_thumb_size if self._view_mode == "details" else self._thumb_size

    def _lookup_or_request_thumb(self, item: dict, thumb_size: Optional[int] = None) -> Optional[tk.PhotoImage]:
        path = item["path"]
        size = thumb_size if thumb_size else self._current_thumb_size()
        if not path:
            return self._error_image(size)
        if not is_pil_available():
            # 没有 Pillow，仅尝试 tk.PhotoImage（PNG/GIF）
            try:
                key = f"native::{path}::{size}"
                cached = self._lru.get(key)
                if cached is not None:
                    return cached
                photo = tk.PhotoImage(file=path)
                self._lru.put(key, photo)
                return photo
            except Exception:
                return self._error_image(size)

        cache_key = self._loader.make_cache_key(path, size)
        # 1) 内存命中
        cached = self._lru.get(cache_key)
        if cached is not None:
            return cached
        # 2) 磁盘命中（同步快路径）—— 仅当文件存在且磁盘缓存就绪时尝试
        photo = self._loader.get_disk_cached_photo(path, size)
        if photo is not None:
            self._lru.put(cache_key, photo)
            return photo
        # 3) 异步加载
        self._loader.submit(path, size)
        return self._placeholder_image(size)

    def _on_thumb_loaded(self, cache_key, photo, err, path, thumb_size, _gen):
        # 详情视图用 details_thumb_size；缩略图视图用 thumb_size
        accept_sizes = {self._thumb_size, self._details_thumb_size}
        if thumb_size not in accept_sizes:
            return
        if photo is None:
            err_img = self._error_image(thumb_size)
            for idx, it in enumerate(self._items):
                if it["path"] == path and idx in self._cell_items:
                    cell = self._cell_items[idx]
                    if cell.get("thumb_size") != thumb_size:
                        continue
                    eid = cell.get("image")
                    if eid:
                        try:
                            self._canvas.itemconfigure(eid, image=err_img)
                        except tk.TclError:
                            pass
            return
        # 主线程缓存
        self._lru.put(cache_key, photo)
        # 把所有引用该 path 且 cell 的 thumb_size 匹配的项更新
        for idx, it in enumerate(self._items):
            if it["path"] == path and idx in self._cell_items:
                cell = self._cell_items[idx]
                if cell.get("thumb_size") != thumb_size:
                    continue
                eid = cell.get("image")
                if eid:
                    try:
                        self._canvas.itemconfigure(eid, image=photo)
                    except tk.TclError:
                        pass

    # ====================================================================
    # 元数据（详情视图列：尺寸/大小/修改时间）
    # ====================================================================

    def _ensure_meta(self, path: str) -> dict:
        """同步取 stat（快），异步取图片尺寸（PIL header）。返回当前可用 meta。"""
        if not path:
            return {}
        meta = self._meta_cache.get(path)
        if meta is not None and meta.get("w") is not None:
            return meta
        if meta is None:
            meta = {"size_bytes": None, "mtime": None, "w": None, "h": None}
            try:
                st = os.stat(path)
                meta["size_bytes"] = st.st_size
                meta["mtime"] = st.st_mtime
            except OSError:
                pass
            self._meta_cache[path] = meta
        # 提交异步获取图片尺寸
        if is_pil_available() and path not in self._meta_pending and meta.get("w") is None:
            self._meta_pending.add(path)
            try:
                self._meta_loader.submit(self._meta_worker, path)
            except RuntimeError:
                # executor 已关闭
                self._meta_pending.discard(path)
        return meta

    def _meta_worker(self, path: str):
        """后台读取图片尺寸（仅 header，不解码像素）。"""
        try:
            from PIL import Image  # type: ignore
            with Image.open(path) as im:
                w, h = im.size
            try:
                self.after(0, self._on_meta_loaded, path, w, h, None)
            except RuntimeError:
                pass
        except Exception as e:
            try:
                self.after(0, self._on_meta_loaded, path, None, None, e)
            except RuntimeError:
                pass

    def _on_meta_loaded(self, path: str, w, h, _err):
        self._meta_pending.discard(path)
        meta = self._meta_cache.setdefault(path, {})
        meta["w"] = w
        meta["h"] = h
        # 如果当前正按 meta 相关列排序，触发一次延迟重排（聚合多次 meta 回调）
        if self._sort_state is not None:
            sk = self._sort_state.get("key")
            col = next((c for c in self._details_columns if c["key"] == sk), None)
            if col and col.get("type") in ("meta", "size", "mtime", "dimension"):
                if not getattr(self, "_pending_meta_resort", False):
                    self._pending_meta_resort = True
                    self.after(200, self._do_pending_meta_resort)
        # 详情视图下刷新对应可见行的列文本
        if self._view_mode != "details":
            return
        for pos, cell in list(self._cell_items.items()):
            data_idx = cell.get("data_idx", pos)
            if data_idx >= len(self._items):
                continue
            it = self._items[data_idx]
            if it["path"] != path:
                continue
            text_ids = cell.get("text_ids") or {}
            for col in self._details_columns:
                if col.get("type") not in ("meta", "size", "mtime", "dimension"):
                    continue
                tid = text_ids.get(col["key"])
                if not tid:
                    continue
                try:
                    if col.get("getter"):
                        if col.get("type") == "meta":
                            val = col["getter"](it, meta)
                        else:
                            val = col["getter"](it)
                    else:
                        raw = self._extract_column_value(col, it)
                        formatter = col.get("formatter")
                        val = formatter(raw, it) if formatter else \
                            self._default_format_value(col, raw, meta)
                except Exception:
                    val = ""
                # 取该列的可用宽度
                key = col["key"]
                col_idx = next((i for i, c in enumerate(self._details_columns) if c["key"] == key), None)
                if col_idx is None:
                    continue
                widths = self._effective_col_widths or self._compute_column_widths()
                cw = widths[col_idx] if col_idx < len(widths) else 100
                shown = self._truncate_to_width(str(val), max(20, cw - 12))
                try:
                    self._canvas.itemconfigure(tid, text=shown)
                except tk.TclError:
                    pass

    def _do_pending_meta_resort(self):
        self._pending_meta_resort = False
        if self._sort_state is None:
            return
        self._apply_sort()
        self._relayout(force=True)

    # ====================================================================
    # 命中测试 & 选择
    # ====================================================================

    def _xy_to_index(self, x_widget: int, y_widget: int) -> Optional[int]:
        """命中测试。返回数据索引（data_idx），未命中返回 None。"""
        x = self._canvas.canvasx(x_widget)
        y = self._canvas.canvasy(y_widget)
        if x < 0 or y < 0:
            return None
        col = int(x // max(1, self._cell_w))
        row = int(y // max(1, self._cell_h))
        if col >= self._cols:
            return None
        pos = row * self._cols + col
        if pos >= len(self._items):
            return None
        x0, y0, x1, y1 = self._cell_box(pos)
        if x < x0 + 1 or x > x1 - 1 or y < y0 + 1 or y > y1 - 1:
            return None
        return self._data_index(pos)

    def _xy_to_pos_and_col(self, x_widget: int, y_widget: int):
        """返回 (data_idx, column_key)；详情视图下用于派发单元格事件。"""
        x = self._canvas.canvasx(x_widget)
        y = self._canvas.canvasy(y_widget)
        if x < 0 or y < 0:
            return (None, None)
        col_pos = int(x // max(1, self._cell_w))
        row = int(y // max(1, self._cell_h))
        if col_pos >= self._cols:
            return (None, None)
        pos = row * self._cols + col_pos
        if pos >= len(self._items):
            return (None, None)
        data_idx = self._data_index(pos)
        if self._view_mode != "details":
            return (data_idx, None)
        # 详情视图：在 cell 内根据 x 偏移找列
        x0, _, _, _ = self._cell_box(pos)
        rel_x = x - x0
        widths = self._effective_col_widths or self._compute_column_widths()
        acc = 0
        for i, w in enumerate(widths):
            if acc <= rel_x < acc + w:
                return (data_idx, self._details_columns[i]["key"])
            acc += w
        return (data_idx, None)

    def _display_pos_of(self, data_idx: int) -> int:
        """data_idx → 显示位置（无排序时直接返回）。"""
        if self._display_indices is None:
            return data_idx
        try:
            return self._display_indices.index(data_idx)
        except ValueError:
            return data_idx

    def _on_left_press(self, event):
        self._canvas.focus_set()
        self._cancel_hover()
        # 编辑态：先 commit 当前编辑（除非点在编辑控件上）
        if self._editing is not None:
            self._commit_edit()
        idx, col_key = self._xy_to_pos_and_col(event.x, event.y)
        # —— 调试：环境变量 HY127_IMAGELIST_DEBUG_CLICK=1 时打印每次点击 ——
        if os.environ.get("HY127_IMAGELIST_DEBUG_CLICK"):
            cx = self._canvas.canvasx(event.x)
            cy = self._canvas.canvasy(event.y)
            print(
                f"[ImageList] click widget=({event.x},{event.y}) "
                f"canvas=({cx:.0f},{cy:.0f}) → idx={idx}, col={col_key!r}"
            )

        # —— 列内嵌控件拦截 ——（必须在选择/拖动逻辑之前）
        if idx is not None and col_key is not None and \
                self._view_mode == "details":
            handled = self._maybe_handle_control_press(event, idx, col_key)
            if os.environ.get("HY127_IMAGELIST_DEBUG_CLICK"):
                col = self._find_control_column(col_key)
                ctype = (col.get("control") if col else None)
                print(
                    f"[ImageList]   control type={ctype!r}, handled={handled}"
                )
            if handled:
                # 同步 cursor 高亮，让用户感知到"点中了哪一行"
                if self._cursor_index != idx:
                    self._cursor_index = idx
                    self._redraw_visible()
                import time
                self._suspend_hover_until = time.monotonic() + 0.8
                return
        if idx is None:
            # 点空白 → 开始框选 / 清空选择
            if self._selection_mode != "single" and self._enable_marquee \
                    and self._view_mode != "details":
                self._marquee_start = (
                    self._canvas.canvasx(event.x),
                    self._canvas.canvasy(event.y),
                )
                if not (event.state & 0x4):
                    if self._selected:
                        self._selected.clear()
                        self._redraw_visible()
                        self._dispatch_selection_changed()
            else:
                if self._selected:
                    self._selected.clear()
                    self._redraw_visible()
                    self._dispatch_selection_changed()
            return

        ctrl = bool(event.state & 0x4)
        shift = bool(event.state & 0x1)
        prev = set(self._selected)

        if self._selection_mode == "single":
            self._selected = {idx}
            self._anchor_index = idx
        elif self._selection_mode == "multi":
            if idx in self._selected:
                self._selected.remove(idx)
            else:
                self._selected.add(idx)
            self._anchor_index = idx
        else:  # extended
            if shift and self._anchor_index is not None:
                # 按显示位置 [pos_lo..pos_hi] 选择
                pos_a = self._display_pos_of(self._anchor_index)
                pos_b = self._display_pos_of(idx)
                lo, hi = min(pos_a, pos_b), max(pos_a, pos_b)
                rng = {self._data_index(p) for p in range(lo, hi + 1)}
                if ctrl:
                    self._selected |= rng
                else:
                    self._selected = rng
            elif ctrl:
                if idx in self._selected:
                    self._selected.remove(idx)
                else:
                    self._selected.add(idx)
                self._anchor_index = idx
            else:
                self._selected = {idx}
                self._anchor_index = idx

        self._cursor_index = idx
        if self._selected != prev:
            self._redraw_visible()
            self._dispatch_selection_changed()

        # 派发行/单元格点击事件
        item = self._items[idx] if 0 <= idx < len(self._items) else None
        self._fire_event(
            EVENT_IMAGELIST_ROW_CLICKED,
            data={"index": idx, "item": item},
        )
        if col_key is not None:
            value = self._cell_value_for_event(idx, col_key)
            self._fire_event(
                EVENT_IMAGELIST_CELL_CLICKED,
                data={
                    "index": idx, "item": item,
                    "column": col_key, "value": value,
                },
            )

        # 拖动重排候选（不立即触发，等 motion 超过阈值）
        if self._enable_drag_reorder and not (ctrl or shift):
            self._drag_state = {
                "start_x": event.x,
                "start_y": event.y,
                "started": False,
                "source_idx": idx,
                "source_indices": None,
                "indicator_id": None,
                "tooltip_bg": None,
                "tooltip_text": None,
                "target_pos": None,
            }

    def _on_left_motion(self, event):
        # 拖动重排优先于框选
        if self._drag_state is not None:
            ds = self._drag_state
            if not ds["started"]:
                if abs(event.x - ds["start_x"]) > self._drag_reorder_threshold or \
                        abs(event.y - ds["start_y"]) > self._drag_reorder_threshold:
                    self._begin_drag_reorder(ds)
            if ds["started"]:
                self._update_drag_indicator(event.x, event.y)
                self._auto_scroll_for_drag(event.y)
                return
        if self._marquee_start is None:
            return
        x0, y0 = self._marquee_start
        x1 = self._canvas.canvasx(event.x)
        y1 = self._canvas.canvasy(event.y)
        # 自动滚动：拖到边界附近
        cv_h = self._canvas.winfo_height()
        view_top = self._canvas.canvasy(0)
        view_bottom = view_top + cv_h
        if event.y < 20:
            self._canvas.yview_scroll(-1, "units")
        elif event.y > cv_h - 20:
            self._canvas.yview_scroll(1, "units")

        if self._marquee_id is None:
            self._marquee_id = self._canvas.create_rectangle(
                x0, y0, x1, y1,
                outline=self._theme_accent,
                fill=self._theme_accent,
                stipple="gray12",
                tags=("marquee",),
            )
        else:
            self._canvas.coords(self._marquee_id, x0, y0, x1, y1)
        # 实时更新选中
        ctrl = bool(event.state & 0x4)
        base = set(self._selected) if ctrl else set()
        rect_lo_x, rect_hi_x = sorted([x0, x1])
        rect_lo_y, rect_hi_y = sorted([y0, y1])
        new_sel = set(base)
        # 通过行列范围裁剪
        c_lo = max(0, int(rect_lo_x // max(1, self._cell_w)))
        c_hi = min(self._cols - 1, int(rect_hi_x // max(1, self._cell_w)))
        r_lo = max(0, int(rect_lo_y // max(1, self._cell_h)))
        r_hi = min(self._rows - 1, int(rect_hi_y // max(1, self._cell_h)))
        for r in range(r_lo, r_hi + 1):
            for c in range(c_lo, c_hi + 1):
                pos = r * self._cols + c
                if pos >= len(self._items):
                    break
                cx0, cy0, cx1, cy1 = self._cell_box(pos)
                if cx1 < rect_lo_x or cx0 > rect_hi_x or cy1 < rect_lo_y or cy0 > rect_hi_y:
                    continue
                new_sel.add(self._data_index(pos))
        if new_sel != self._selected:
            self._selected = new_sel
            self._redraw_visible()
            self._dispatch_selection_changed()

    def _on_left_release(self, event):
        # 列内嵌按钮：抬起时判定 click
        if self._control_press is not None:
            self._on_left_release_extra(event)
        if self._drag_state is not None:
            ds = self._drag_state
            self._drag_state = None
            if ds.get("started"):
                self._finalize_drag_reorder(ds)
            else:
                self._cleanup_drag_visuals(ds)
        if self._marquee_id is not None:
            try:
                self._canvas.delete(self._marquee_id)
            except tk.TclError:
                pass
            self._marquee_id = None
        self._marquee_start = None

    # ====================================================================
    # 拖动重排
    # ====================================================================

    def _begin_drag_reorder(self, ds: dict):
        """从候选状态进入真正的拖动态：确定 source 集合、清排序、改光标。"""
        ds["started"] = True
        source_idx = ds["source_idx"]
        if source_idx in self._selected and len(self._selected) > 1:
            ds["source_indices"] = sorted(self._selected)
        else:
            ds["source_indices"] = [source_idx]
        # 若当前有排序：物理重排没有意义 → 自动取消排序
        if self._drag_clear_sort and self._sort_state is not None:
            self.sort_by(None)
        # 取消框选
        self._marquee_start = None
        try:
            self._canvas.configure(cursor="fleur")
        except tk.TclError:
            pass

    def _auto_scroll_for_drag(self, widget_y: int):
        cv_h = self._canvas.winfo_height()
        if widget_y < 20:
            self._canvas.yview_scroll(-1, "units")
        elif widget_y > cv_h - 20:
            self._canvas.yview_scroll(1, "units")

    def _hit_insertion_pos(self, x_widget: int, y_widget: int) -> int:
        """把鼠标坐标转成"插入位置"（0..n，表示在第 n 个 display pos 之前）。"""
        n = len(self._items)
        if n == 0:
            return 0
        x = self._canvas.canvasx(x_widget)
        y = self._canvas.canvasy(y_widget)
        if self._view_mode == "details":
            row = int(y // max(1, self._cell_h))
            row = max(0, min(n, row))
            if row >= n:
                return n
            # 与行中线比较：落上半 → 插到该行之前；下半 → 插到之后
            cy = row * self._cell_h + self._cell_h / 2
            return row if y < cy else row + 1
        # 缩略图视图
        col = int(x // max(1, self._cell_w))
        row = int(y // max(1, self._cell_h))
        col = max(0, min(self._cols - 1, col))
        row = max(0, min(self._rows - 1, row))
        pos = row * self._cols + col
        if pos >= n:
            return n
        cx0, _, cx1, _ = self._cell_box(pos)
        cx_mid = (cx0 + cx1) / 2
        return pos if x < cx_mid else pos + 1

    def _update_drag_indicator(self, x_widget: int, y_widget: int):
        ds = self._drag_state
        if ds is None or not ds["started"]:
            return
        target = self._hit_insertion_pos(x_widget, y_widget)
        ds["target_pos"] = target
        # 删旧指示线
        old = ds.get("indicator_id")
        if old is not None:
            try:
                self._canvas.delete(old)
            except tk.TclError:
                pass
            ds["indicator_id"] = None

        # 画新指示线：详情视图用横线；缩略图视图用竖线
        n = len(self._items)
        if n == 0:
            self._draw_drag_tooltip(x_widget, y_widget, ds)
            return

        if self._view_mode == "details":
            cw_canvas = max(1, self._canvas.winfo_width())
            total_w = max(cw_canvas, self._cell_w)
            if target >= n:
                y = n * self._cell_h - 1
            else:
                y = target * self._cell_h
            line_id = self._canvas.create_line(
                0, y, total_w, y,
                fill=self._theme_accent, width=3,
                tags=("drag_indicator",),
            )
            ds["indicator_id"] = line_id
        else:
            # 缩略图：在网格某条竖线上画
            if target == 0:
                ref_pos = 0
                x_line_side = "left"
            else:
                ref_pos = target - 1
                x_line_side = "right"
            if ref_pos >= n:
                ref_pos = n - 1
                x_line_side = "right"
            cx0, cy0, cx1, cy1 = self._cell_box(ref_pos)
            # 如果 target 超过这一行末尾 → 指示线放在该行右侧，画满这一行高
            if target == 0 or (target % self._cols == 0 and target < n):
                lx = cx0 if x_line_side == "left" else cx0
                y_top = (target // self._cols) * self._cell_h
                y_bot = y_top + self._cell_h
                line_id = self._canvas.create_line(
                    lx, y_top, lx, y_bot,
                    fill=self._theme_accent, width=3,
                    tags=("drag_indicator",),
                )
            else:
                lx = cx1 if x_line_side == "right" else cx0
                line_id = self._canvas.create_line(
                    lx, cy0, lx, cy1,
                    fill=self._theme_accent, width=3,
                    tags=("drag_indicator",),
                )
            ds["indicator_id"] = line_id

        self._draw_drag_tooltip(x_widget, y_widget, ds)

    def _draw_drag_tooltip(self, x_widget: int, y_widget: int, ds: dict):
        """在鼠标附近显示"拖动 N 项"的轻量 tooltip。"""
        for key in ("tooltip_bg", "tooltip_text"):
            cid = ds.get(key)
            if cid is not None:
                try:
                    self._canvas.delete(cid)
                except tk.TclError:
                    pass
                ds[key] = None
        count = len(ds.get("source_indices") or [])
        if count <= 0:
            return
        text = f"移动 {count} 项" if count > 1 else "移动 1 项"
        cx = self._canvas.canvasx(x_widget) + 12
        cy = self._canvas.canvasy(y_widget) + 12
        # 先画文本测量
        tid = self._canvas.create_text(
            cx + 8, cy + 4, text=text, anchor=NW,
            font=self._font, fill=self._theme_tooltip_fg,
            tags=("drag_tooltip",),
        )
        bbox = self._canvas.bbox(tid) or (cx, cy, cx + 60, cy + 18)
        bg_id = self._canvas.create_rectangle(
            bbox[0] - 6, bbox[1] - 3, bbox[2] + 6, bbox[3] + 3,
            fill=self._theme_tooltip_bg, outline="",
            tags=("drag_tooltip",),
        )
        self._canvas.tag_raise(tid)
        ds["tooltip_bg"] = bg_id
        ds["tooltip_text"] = tid

    def _cleanup_drag_visuals(self, ds: dict):
        for key in ("indicator_id", "tooltip_bg", "tooltip_text"):
            cid = ds.get(key)
            if cid is not None:
                try:
                    self._canvas.delete(cid)
                except tk.TclError:
                    pass
        try:
            self._canvas.configure(cursor="")
        except tk.TclError:
            pass

    def _finalize_drag_reorder(self, ds: dict):
        self._cleanup_drag_visuals(ds)
        indices = ds.get("source_indices") or []
        target = ds.get("target_pos")
        if not indices or target is None:
            return
        self.move_items(indices, target)

    # ---------- 公共 API ----------

    def move_items(self, indices: list[int], target_pos: int) -> list[int]:
        """把一组数据索引移动到 target_pos 位置（插入到第 target_pos 个之前）。

        返回移动后这些项的新数据索引（按移动后的顺序）。触发 reorder 事件。
        """
        if not indices:
            return []
        n = len(self._items)
        indices = sorted(set(i for i in indices if 0 <= i < n))
        if not indices:
            return []
        target_pos = max(0, min(n, int(target_pos)))
        # 如果 target 落在选中块内部 → 视为不动
        if indices[0] <= target_pos <= indices[-1] + 1 and \
                all(indices[k] + 1 == indices[k + 1] for k in range(len(indices) - 1)):
            if indices[0] <= target_pos <= indices[-1] + 1:
                return list(indices)

        items = list(self._items)
        moved = [items[i] for i in indices]
        idx_set = set(indices)
        remaining = [it for i, it in enumerate(items) if i not in idx_set]
        shift = sum(1 for i in indices if i < target_pos)
        new_target = target_pos - shift
        new_target = max(0, min(len(remaining), new_target))
        remaining[new_target:new_target] = moved
        self._items = remaining
        new_indices = list(range(new_target, new_target + len(moved)))

        # 选择/光标跟随
        self._selected = set(new_indices)
        self._cursor_index = new_indices[0] if new_indices else None
        self._anchor_index = self._cursor_index

        # 如果当前有排序，拖动后排序在 _begin_drag_reorder 里已被清；
        # 但编程式 move_items 也可能在排序状态下调用 → 保持排序一致性
        if self._sort_state is not None:
            self._apply_sort()

        self._relayout(force=True)
        self._dispatch_selection_changed()
        self._fire_event(
            EVENT_IMAGELIST_ITEMS_REORDERED,
            data={
                "moved_from": list(indices),
                "target_pos": target_pos,
                "new_indices": new_indices,
            },
        )
        return new_indices

    def set_drag_reorder_enabled(self, enabled: bool):
        self._enable_drag_reorder = bool(enabled)
        if not self._enable_drag_reorder and self._drag_state is not None:
            self._cleanup_drag_visuals(self._drag_state)
            self._drag_state = None

    def is_drag_reorder_enabled(self) -> bool:
        return self._enable_drag_reorder

    def _cell_value_for_event(self, data_idx: int, col_key: str):
        """为事件 payload 计算某行某列的格式化值。"""
        if data_idx < 0 or data_idx >= len(self._items):
            return None
        item = self._items[data_idx]
        col = next((c for c in self._details_columns if c["key"] == col_key), None)
        if col is None:
            return None
        meta = self._meta_cache.get(item["path"]) or {}
        getter = col.get("getter")
        try:
            if getter is not None:
                if col.get("type") == "meta":
                    raw = getter(item, meta)
                else:
                    raw = getter(item)
            else:
                raw = self._extract_column_value(col, item)
            formatter = col.get("formatter")
            return formatter(raw, item) if formatter else raw
        except Exception:
            return None

    def _on_double_click_event(self, event):
        idx, col_key = self._xy_to_pos_and_col(event.x, event.y)
        if idx is None:
            return
        # 列内嵌可编辑控件：双击进入编辑（默认 trigger='double'）
        if col_key is not None and self._view_mode == "details":
            col = self._find_control_column(col_key)
            if col is not None:
                ctrl_type = (col.get("control") or "").lower()
                trig = (col.get("edit_trigger") or "single").lower()
                if ctrl_type in ("entry", "combobox") and \
                        col.get("editable", True) and \
                        trig in ("double", "single", "f2"):
                    self._start_edit(idx, col)
                    return
                # 其它 control 列（checkbox/radio/button/rating/progress）：
                # 双击不应该弹预览或派发 row_double_clicked
                if ctrl_type:
                    return

        item = self._items[idx]
        if self._on_double_click is not None:
            try:
                self._on_double_click(dict(item))
            except Exception:
                pass
        self._fire_event(
            EVENT_IMAGELIST_ROW_DOUBLE_CLICKED,
            data={"index": idx, "item": item},
        )
        if col_key is not None:
            self._fire_event(
                EVENT_IMAGELIST_CELL_DOUBLE_CLICKED,
                data={
                    "index": idx, "item": item,
                    "column": col_key,
                    "value": self._cell_value_for_event(idx, col_key),
                },
            )
        self.event_generate(EVENT_IMAGELIST_ITEM_ACTIVATED, when="tail")
        if self._enable_double_click_preview:
            # 详情视图下：必须双击在 type=image 的列上才弹预览；
            # 缩略图视图下：双击任意位置都弹。
            if self._view_mode == "details":
                if col_key is None:
                    return
                col = next(
                    (c for c in self._details_columns if c.get("key") == col_key),
                    None,
                )
                if col is None or col.get("type") != "image":
                    return
            self._open_preview_window(idx)

    def _on_right_click(self, event):
        idx, col_key = self._xy_to_pos_and_col(event.x, event.y)
        if idx is None:
            return
        if idx not in self._selected:
            self._selected = {idx}
            self._anchor_index = idx
            self._cursor_index = idx
            self._redraw_visible()
            self._dispatch_selection_changed()
        item = self._items[idx]
        self._fire_event(
            EVENT_IMAGELIST_ROW_RIGHT_CLICKED,
            data={
                "index": idx, "item": item,
                "column": col_key,
                "x_root": event.x_root, "y_root": event.y_root,
            },
        )
        if self._on_context_menu is not None:
            try:
                handled = self._on_context_menu(dict(item), event)
                if handled:
                    return
            except Exception:
                pass
        self._show_default_context_menu(idx, event)

    def _show_default_context_menu(self, index: int, event):
        item = self._items[index]
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="预览大图", command=lambda: self._open_preview_window(index))
        menu.add_separator()
        menu.add_command(label="复制路径", command=lambda: self._copy_to_clipboard(item["path"]))
        menu.add_command(label="在文件夹中显示", command=lambda: self._reveal_in_folder(item["path"]))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                menu.grab_release()
            except tk.TclError:
                pass

    def _copy_to_clipboard(self, text: str):
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
        except Exception:
            pass

    def _reveal_in_folder(self, path: str):
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer.exe", f"/select,{os.path.normpath(path)}"])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", path])
            else:
                subprocess.Popen(["xdg-open", os.path.dirname(path) or "."])
        except Exception:
            logger.exception("打开文件所在位置失败: %s", path)

    def _activate_current(self):
        if self._cursor_index is not None and 0 <= self._cursor_index < len(self._items):
            item = self._items[self._cursor_index]
            if self._on_double_click is not None:
                try:
                    self._on_double_click(dict(item))
                except Exception:
                    pass
            self.event_generate(EVENT_IMAGELIST_ITEM_ACTIVATED, when="tail")
            if self._enable_double_click_preview:
                self._open_preview_window(self._cursor_index)

    def _toggle_current(self):
        if self._cursor_index is None:
            return
        if self._selection_mode == "single":
            self._selected = {self._cursor_index}
        else:
            if self._cursor_index in self._selected:
                self._selected.remove(self._cursor_index)
            else:
                self._selected.add(self._cursor_index)
        self._redraw_visible()
        self._dispatch_selection_changed()

    def _move_cursor(self, dx: int = 0, dy: int = 0,
                     absolute: Optional[int] = None, page: int = 0):
        if not self._items:
            return
        # 所有运算先转到 display pos 上，再映射回 data_idx
        cur_data = self._cursor_index if self._cursor_index is not None else 0
        cur_pos = self._display_pos_of(cur_data)
        n = len(self._items)
        if absolute is not None:
            new_pos = max(0, min(n - 1, absolute))
        elif page != 0:
            cv_h = max(1, self._canvas.winfo_height())
            rows_per_page = max(1, cv_h // max(1, self._cell_h))
            new_pos = max(0, min(n - 1,
                                 cur_pos + page * rows_per_page * self._cols))
        else:
            row = cur_pos // max(1, self._cols)
            col = cur_pos % max(1, self._cols)
            row = max(0, min(self._rows - 1, row + dy))
            col = max(0, min(self._cols - 1, col + dx))
            new_pos = min(n - 1, row * self._cols + col)
        new_idx = self._data_index(new_pos)
        self._cursor_index = new_idx
        # 简化：键盘移动同时更新选择（单选语义）
        if self._selection_mode == "single":
            self._selected = {new_idx}
        else:
            self._selected = {new_idx}
            self._anchor_index = new_idx
        self._redraw_visible()
        self.ensure_visible(new_idx)
        self._dispatch_selection_changed()
        return "break"

    # ====================================================================
    # 滚轮 & 缩放
    # ====================================================================

    def _on_mousewheel(self, event):
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        import time
        self._suspend_hover_until = time.monotonic() + 0.25
        self._cancel_hover()

    def _on_ctrl_mousewheel(self, event):
        # 详情视图下 Ctrl+滚轮不缩放（缩略图大小对详情视图无意义）
        if self._view_mode == "details":
            return
        if event.delta > 0:
            self.zoom_in()
        else:
            self.zoom_out()
        return "break"

    # ====================================================================
    # Hover 浮窗预览
    # ====================================================================

    def _on_motion(self, event):
        # control 列上的鼠标光标：可点击元素 → hand2
        if self._view_mode == "details":
            self._update_cursor_for_motion(event)
        if not self._enable_hover_preview:
            return
        import time
        if time.monotonic() < self._suspend_hover_until:
            return
        idx = self._xy_to_index(event.x, event.y)
        hover_col_key = None
        if self._view_mode == "details":
            idx2, hover_col_key = self._xy_to_pos_and_col(event.x, event.y)
            if idx2 != idx:
                idx = idx2
            if hover_col_key is not None:
                col = next(
                    (c for c in self._details_columns if c.get("key") == hover_col_key),
                    None,
                )
                if col is None or col.get("type") != "image":
                    self._cancel_hover()
                    self._hover_index = None
                    self._hover_col_key = hover_col_key
                    return
        if idx == self._hover_index and hover_col_key == self._hover_col_key:
            # 移动到同一格的不同位置 → 不重新启动倒计时
            return
        self._cancel_hover()
        self._hover_index = idx
        self._hover_col_key = hover_col_key
        if idx is None:
            return
        # 启动倒计时
        self._hover_after = self.after(self._hover_delay_ms, self._show_hover_preview)

    def _update_cursor_for_motion(self, event):
        try:
            _, col_key = self._xy_to_pos_and_col(event.x, event.y)
        except Exception:
            col_key = None
        cur_cursor = ""
        if col_key:
            col = self._find_control_column(col_key)
            if col is not None and not col.get("disabled"):
                ctype = (col.get("control") or "").lower()
                if ctype in ("checkbox", "radio", "button", "rating", "combobox"):
                    cur_cursor = "hand2"
                elif ctype == "entry" and col.get("editable", True):
                    cur_cursor = "xterm"
                elif ctype == "progress" and col.get("editable"):
                    cur_cursor = "hand2"
        if getattr(self, "_last_cursor", None) != cur_cursor:
            try:
                self._canvas.configure(cursor=cur_cursor)
            except tk.TclError:
                pass
            self._last_cursor = cur_cursor

    def _on_canvas_leave(self, _event):
        self._cancel_hover()
        self._hover_index = None
        self._hover_col_key = None

    def _on_canvas_enter(self, _event):
        pass

    def _cancel_hover(self):
        if self._hover_after:
            try:
                self.after_cancel(self._hover_after)
            except Exception:
                pass
            self._hover_after = None
        self._hide_hover_window()

    def _show_hover_preview(self):
        self._hover_after = None
        if self._hover_index is None or not (0 <= self._hover_index < len(self._items)):
            return
        if self._editing is not None:
            return
        if self._view_mode == "details":
            if not self._hover_col_key:
                return
            col = next(
                (c for c in self._details_columns if c.get("key") == self._hover_col_key),
                None,
            )
            if col is None or col.get("type") != "image":
                return
        item = self._items[self._hover_index]
        path = item["path"]
        if not path or not is_pil_available():
            return
        # 异步加载预览图，加载好后再弹窗（避免 UI 卡）
        self._hover_path = path
        self._preview_loader.request(
            path,
            self._hover_preview_size,
            target="hover",
            callback=self._on_hover_preview_loaded,
        )

    def _on_hover_preview_loaded(self, photo, err, _rid):
        # 如果鼠标早就离开了 → 不显示
        if self._hover_index is None:
            return
        if err is not None or photo is None:
            return
        cur_path = self._items[self._hover_index]["path"] if 0 <= self._hover_index < len(self._items) else None
        if cur_path != self._hover_path:
            return
        self._hover_photo = photo
        self._popup_hover_window(photo)

    def _popup_hover_window(self, photo: tk.PhotoImage):
        if self._hover_window is not None:
            try:
                self._hover_window.destroy()
            except tk.TclError:
                pass
        win = tk.Toplevel(self)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        try:
            win.attributes("-alpha", 0.97)
        except tk.TclError:
            pass
        frm = tk.Frame(win, bg="#212529", bd=1, highlightthickness=1,
                       highlightbackground="#0d6efd")
        frm.pack(fill=BOTH, expand=YES)
        lbl = tk.Label(frm, image=photo, bd=0, bg="#212529")
        lbl.pack(padx=2, pady=(2, 0))
        # 标题条
        if self._hover_index is not None and 0 <= self._hover_index < len(self._items):
            cap = self._items[self._hover_index]["caption"]
            tk.Label(
                frm, text=cap, bg="#212529", fg="#f8f9fa",
                font=self._font, padx=6, pady=2, anchor=W,
            ).pack(fill=X)
        # 定位：鼠标右下 16px 偏移；超出屏幕则翻转
        win.update_idletasks()
        ww = win.winfo_reqwidth()
        wh = win.winfo_reqheight()
        px = self.winfo_pointerx() + 18
        py = self.winfo_pointery() + 18
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        if px + ww > sw:
            px = self.winfo_pointerx() - ww - 18
        if py + wh > sh:
            py = self.winfo_pointery() - wh - 18
        win.geometry(f"+{max(0, px)}+{max(0, py)}")
        self._hover_window = win

    def _hide_hover_window(self):
        if self._hover_window is not None:
            try:
                self._hover_window.destroy()
            except tk.TclError:
                pass
            self._hover_window = None
        self._hover_photo = None

    # ====================================================================
    # 预览窗
    # ====================================================================

    def _open_preview_window(self, start_index: int):
        # 如果有多选，预览窗只在已选范围内翻页；否则全部
        if len(self._selected) > 1:
            sel_sorted = sorted(self._selected)
            try:
                pos = sel_sorted.index(start_index)
            except ValueError:
                pos = 0
            items = [self._items[i] for i in sel_sorted]
            HY127_ImagePreview.show(self.winfo_toplevel(), items, start_index=pos)
        else:
            HY127_ImagePreview.show(
                self.winfo_toplevel(), self._items, start_index=start_index,
            )

    # ====================================================================
    # 选择变更派发
    # ====================================================================

    def _dispatch_selection_changed(self):
        if self._sel_changed_after:
            return
        self._sel_changed_after = self.after_idle(self._fire_selection_changed)

    def _fire_selection_changed(self):
        self._sel_changed_after = None
        try:
            self.event_generate(EVENT_IMAGELIST_SELECTION_CHANGED, when="tail")
        except tk.TclError:
            pass
        if self._on_select_changed is not None:
            try:
                self._on_select_changed(self.get_selected())
            except Exception:
                pass

    # ====================================================================
    # 销毁
    # ====================================================================

    def destroy(self):
        try:
            self._cancel_hover()
        except Exception:
            pass
        try:
            self._loader.shutdown(wait=False)
        except Exception:
            pass
        try:
            self._preview_loader.shutdown(wait=False)
        except Exception:
            pass
        try:
            self._meta_loader.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            try:
                self._meta_loader.shutdown(wait=False)
            except Exception:
                pass
        except Exception:
            pass
        super().destroy()


# ============================================================================
# HY127_ListView：增强 ListView（详情视图为主）
# ============================================================================

def _default_listview_columns() -> list[dict]:
    """ListView 默认列：不含图片，按通用 ListView 形态。"""
    return [
        {"key": "name", "title": "名称", "width": 280, "type": "name",
         "anchor": "w", "sortable": True, "sort_type": "text"},
        {"key": "ext", "title": "类型", "width": 80, "type": "ext",
         "anchor": "center", "sortable": True, "sort_type": "text"},
        {"key": "dimensions", "title": "尺寸", "width": 110, "type": "dimension",
         "anchor": "e", "sortable": True, "sort_type": "numeric"},
        {"key": "size", "title": "大小", "width": 100, "type": "size",
         "anchor": "e", "sortable": True, "sort_type": "numeric"},
        {"key": "mtime", "title": "修改时间", "width": 160, "type": "mtime",
         "anchor": "w", "sortable": True, "sort_type": "numeric"},
        {"key": "path", "title": "路径", "width": 0, "type": "text",
         "anchor": "w", "sortable": True, "sort_type": "text",
         "getter": lambda it: it.get("path", "")},
    ]


class HY127_ListView(HY127_ImageList):
    """增强版 ListView（详情视图）。

    与 HY127_ImageList 的区别：
        * view_mode 默认 "details"
        * 默认不包含缩略图列（details_show_thumb_column=False）
        * 默认禁用 hover 预览、双击预览（更像传统 ListView）
        * 默认禁用 Ctrl+滚轮缩放
        * 默认列含 sortable=True
        * 默认 selection_mode='extended'（支持 Ctrl/Shift 多选）

    所有"行/单元格/列"事件 (RowClicked / CellClicked / SortChanged / ColumnResized
    等) 与 HY127_ImageList 完全一致，可视为同一控件的另一个默认配置。
    """

    def __init__(
        self,
        master=None,
        items=None,
        columns: Optional[list[dict]] = None,
        view_mode: str = "details",
        details_show_thumb_column: bool = False,
        enable_hover_preview: bool = False,
        enable_double_click_preview: bool = False,
        enable_zoom_with_ctrl_wheel: bool = False,
        selection_mode: str = "extended",
        **kwargs,
    ):
        if columns is None and "details_columns" not in kwargs:
            kwargs["details_columns"] = _default_listview_columns()
        elif columns is not None:
            kwargs["details_columns"] = columns
        super().__init__(
            master=master,
            items=items,
            view_mode=view_mode,
            details_show_thumb_column=details_show_thumb_column,
            enable_hover_preview=enable_hover_preview,
            enable_double_click_preview=enable_double_click_preview,
            enable_zoom_with_ctrl_wheel=enable_zoom_with_ctrl_wheel,
            selection_mode=selection_mode,
            **kwargs,
        )
