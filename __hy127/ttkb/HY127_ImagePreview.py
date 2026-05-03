# -*- coding: utf-8 -*-
"""
HY127_ImagePreview — 单/多张图片的独立预览 Toplevel 窗口。

特性：
    - 居中弹出、可调整大小
    - 工具栏：上一张 / 下一张 / 适应窗口 / 原图 / 缩小 / 放大 / 重置 / 关闭
    - 键盘：← → Esc + - 0(原图) F(适应)
    - 异步加载大图，避免点开瞬间卡顿
    - 滚动条 + 鼠标拖动平移（缩放后）
    - 主控件可单独使用：HY127_ImagePreview.show(parent, items, start_index=0)
"""
from __future__ import annotations

import os
from typing import Iterable, Optional

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from ._imagelist_cache import PreviewLoader, is_pil_available

try:
    from PIL import Image, ImageTk  # type: ignore
except Exception:  # pragma: no cover
    Image = None  # type: ignore
    ImageTk = None  # type: ignore


def _normalize_preview_items(items) -> list[dict]:
    """将 list[str|dict] 标准化为 [{path, caption, user_data}, ...]。"""
    norm = []
    for raw in items or []:
        if isinstance(raw, dict):
            path = raw.get("path") or raw.get("file") or ""
            caption = raw.get("caption") or os.path.basename(path)
            user_data = raw.get("user_data", raw.get("data"))
        else:
            path = str(raw)
            caption = os.path.basename(path)
            user_data = None
        norm.append({"path": path, "caption": caption, "user_data": user_data})
    return norm


class HY127_ImagePreview(ttk.Toplevel):
    """大图预览窗口。"""

    # 缩放档位
    _ZOOM_STEPS = (0.1, 0.15, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0)

    def __init__(
        self,
        parent: Optional[tk.Misc] = None,
        items: Optional[Iterable] = None,
        start_index: int = 0,
        title: str = "图片预览",
        max_load_size: int = 2400,
        bg: str = "#1f1f1f",
        toolbar_bootstyle: str = "secondary",
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        # 立即隐藏 → 等几何/布局就绪后再显示，避免黑框闪烁
        try:
            self.withdraw()
        except tk.TclError:
            pass

        self.title(title)
        self._bg = bg
        self._max_load_size = int(max_load_size)
        self._items = _normalize_preview_items(items)
        if not self._items:
            self._items = [{"path": "", "caption": "(空)", "user_data": None}]
        self._index = max(0, min(int(start_index), len(self._items) - 1))

        # 缩放与平移
        self._zoom = 1.0  # 1.0 = 原图；"fit" 模式由 _fit_mode 控制
        self._fit_mode = True
        self._drag_start: Optional[tuple[int, int]] = None
        self._scroll_start: Optional[tuple[float, float]] = None

        # 当前加载的原始 PIL.Image（按 max_load_size 限制）
        self._src_image = None
        self._photo: Optional[tk.PhotoImage] = None
        self._image_id: Optional[int] = None
        self._loader = PreviewLoader(max_workers=2, tk_root=self)

        # 提前算好窗口大小 + 居中坐标，一次性 set，再 deiconify
        self._initial_geometry(parent, w=1024, h=720)

        self._build_ui(toolbar_bootstyle)
        self._bind_keys()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # 在显示之前就把 transient 关系建立好，避免 deiconify 后再切样式闪一下
        if parent is not None:
            try:
                self.transient(parent.winfo_toplevel())
            except tk.TclError:
                pass

        # 让所有控件完成首次布局，然后才显示窗口
        self.update_idletasks()
        try:
            self.deiconify()
        except tk.TclError:
            pass

        self.after(10, self._load_current)

    # ---------------- UI ----------------

    def _build_ui(self, toolbar_bootstyle: str):
        # geometry 已在 __init__ 里 _initial_geometry() 一次性设置好
        self.minsize(480, 360)

        # 顶部工具栏
        self._toolbar = ttk.Frame(self)
        self._toolbar.pack(side=TOP, fill=X)

        self._btn_prev = ttk.Button(
            self._toolbar, text="◀ 上一张", bootstyle=f"{toolbar_bootstyle}-outline",
            command=self.show_prev,
        )
        self._btn_prev.pack(side=LEFT, padx=(8, 4), pady=6)

        self._btn_next = ttk.Button(
            self._toolbar, text="下一张 ▶", bootstyle=f"{toolbar_bootstyle}-outline",
            command=self.show_next,
        )
        self._btn_next.pack(side=LEFT, padx=4, pady=6)

        ttk.Separator(self._toolbar, orient=VERTICAL).pack(
            side=LEFT, fill=Y, padx=8, pady=8
        )

        ttk.Button(
            self._toolbar, text="适应 (F)", bootstyle=f"{toolbar_bootstyle}-outline",
            command=self.fit_to_window,
        ).pack(side=LEFT, padx=4, pady=6)

        ttk.Button(
            self._toolbar, text="原图 (0)", bootstyle=f"{toolbar_bootstyle}-outline",
            command=lambda: self.set_zoom(1.0),
        ).pack(side=LEFT, padx=4, pady=6)

        ttk.Button(
            self._toolbar, text="-", width=3, bootstyle=f"{toolbar_bootstyle}-outline",
            command=self.zoom_out,
        ).pack(side=LEFT, padx=4, pady=6)

        self._lbl_zoom = ttk.Label(
            self._toolbar, text="100%", width=6, anchor=CENTER,
        )
        self._lbl_zoom.pack(side=LEFT, padx=4, pady=6)

        ttk.Button(
            self._toolbar, text="+", width=3, bootstyle=f"{toolbar_bootstyle}-outline",
            command=self.zoom_in,
        ).pack(side=LEFT, padx=4, pady=6)

        ttk.Separator(self._toolbar, orient=VERTICAL).pack(
            side=LEFT, fill=Y, padx=8, pady=8
        )

        self._lbl_index = ttk.Label(self._toolbar, text="")
        self._lbl_index.pack(side=LEFT, padx=8, pady=6)

        ttk.Button(
            self._toolbar, text="关闭 (Esc)", bootstyle="danger-outline",
            command=self._on_close,
        ).pack(side=RIGHT, padx=8, pady=6)

        # 中央 Canvas + 滚动条
        center = ttk.Frame(self)
        center.pack(side=TOP, fill=BOTH, expand=YES)
        center.grid_rowconfigure(0, weight=1)
        center.grid_columnconfigure(0, weight=1)

        self._canvas = tk.Canvas(
            center, bg=self._bg, highlightthickness=0,
        )
        self._canvas.grid(row=0, column=0, sticky=NSEW)

        self._vsb = ttk.Scrollbar(
            center, orient=VERTICAL, command=self._canvas.yview,
        )
        self._vsb.grid(row=0, column=1, sticky=NS)
        self._hsb = ttk.Scrollbar(
            center, orient=HORIZONTAL, command=self._canvas.xview,
        )
        self._hsb.grid(row=1, column=0, sticky=EW)
        self._canvas.configure(
            yscrollcommand=self._vsb.set, xscrollcommand=self._hsb.set
        )

        # 底部状态栏
        self._statusbar = ttk.Label(
            self, text="", anchor=W, padding=(8, 4),
        )
        self._statusbar.pack(side=BOTTOM, fill=X)

        # Canvas 事件
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self._canvas.bind("<B1-Motion>", self._on_drag_move)
        self._canvas.bind("<ButtonRelease-1>", self._on_drag_end)
        self._canvas.bind("<MouseWheel>", self._on_mousewheel)
        self._canvas.bind("<Control-MouseWheel>", self._on_ctrl_mousewheel)

    def _bind_keys(self):
        self.bind("<Left>", lambda e: self.show_prev())
        self.bind("<Right>", lambda e: self.show_next())
        self.bind("<Escape>", lambda e: self._on_close())
        self.bind("<plus>", lambda e: self.zoom_in())
        self.bind("<KP_Add>", lambda e: self.zoom_in())
        self.bind("<minus>", lambda e: self.zoom_out())
        self.bind("<KP_Subtract>", lambda e: self.zoom_out())
        self.bind("<Key-0>", lambda e: self.set_zoom(1.0))
        self.bind("<KP_0>", lambda e: self.set_zoom(1.0))
        self.bind("<Key-f>", lambda e: self.fit_to_window())
        self.bind("<Key-F>", lambda e: self.fit_to_window())
        self.focus_set()

    def _initial_geometry(self, parent, w: int, h: int):
        """一次性算好 widthxheight+x+y，避免分两次设置导致窗口闪一下。"""
        try:
            if parent is not None and parent.winfo_exists():
                # 用屏幕坐标定位（rootx/rooty），父窗口可能是 Frame，没有自己 geometry
                top = parent.winfo_toplevel()
                px = top.winfo_rootx()
                py = top.winfo_rooty()
                pw = top.winfo_width()
                ph = top.winfo_height()
                if pw <= 1 or ph <= 1:
                    pw = self.winfo_screenwidth()
                    ph = self.winfo_screenheight()
                    px = py = 0
                x = px + (pw - w) // 2
                y = py + (ph - h) // 2
            else:
                sw = self.winfo_screenwidth()
                sh = self.winfo_screenheight()
                x = (sw - w) // 2
                y = (sh - h) // 2
            x = max(0, x)
            y = max(0, y)
            self.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            self.geometry(f"{w}x{h}")

    # ---------------- 加载与显示 ----------------

    def _load_current(self):
        item = self._items[self._index]
        path = item["path"]
        self._update_index_label()
        self._update_status(f"加载中… {os.path.basename(path)}")
        if not is_pil_available():
            self._update_status("未安装 Pillow，仅支持 PNG/GIF 原图直接显示。")
            try:
                self._photo = tk.PhotoImage(file=path)
                self._src_image = None
                self._render()
            except Exception as e:
                self._update_status(f"无法加载: {e}")
            return

        # 异步加载原图（限制最大边长，避免巨图爆内存）
        self._loader.request(
            path,
            self._max_load_size,
            target="preview-main",
            callback=self._on_main_loaded,
        )

    def _on_main_loaded(self, photo: Optional[tk.PhotoImage], err, _rid):
        if err is not None or photo is None:
            self._photo = None
            self._src_image = None
            self._update_status(f"加载失败: {err}")
            self._canvas.delete("all")
            return
        # 重新生成原始 PIL 用于多次缩放（loader 给的是 PhotoImage，原始 PIL 在 worker 内）
        # 这里再开一次 PIL，主线程持有，便于本地多次缩放
        try:
            path = self._items[self._index]["path"]
            with Image.open(path) as src:
                src.load()
                if src.mode not in ("RGB", "RGBA"):
                    src = src.convert("RGBA")
                if max(src.width, src.height) > self._max_load_size:
                    src.thumbnail(
                        (self._max_load_size, self._max_load_size),
                        Image.Resampling.LANCZOS,
                    )
                self._src_image = src.copy()
        except Exception as e:
            self._src_image = None
            self._photo = photo
            self._update_status(f"加载完成（无法二次缩放）: {e}")
            self._render()
            return

        self._photo = photo
        if self._fit_mode:
            self.fit_to_window(redraw_only=True)
        else:
            self._render()
        self._update_status(
            f"{self._items[self._index]['caption']}  "
            f"  原图 {self._src_image.width}×{self._src_image.height}"
        )

    def _render(self):
        self._canvas.delete("all")
        self._image_id = None
        if self._photo is None:
            self._canvas.configure(scrollregion=(0, 0, 0, 0))
            return

        # 按 zoom 缩放
        if self._src_image is not None and is_pil_available():
            w = max(1, int(self._src_image.width * self._zoom))
            h = max(1, int(self._src_image.height * self._zoom))
            try:
                if (w, h) == (self._src_image.width, self._src_image.height):
                    pil_show = self._src_image
                else:
                    pil_show = self._src_image.resize(
                        (w, h),
                        Image.Resampling.LANCZOS if self._zoom < 2.0 else Image.Resampling.NEAREST,
                    )
                self._photo = ImageTk.PhotoImage(pil_show)
            except Exception as e:
                self._update_status(f"缩放失败: {e}")
                return

        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        iw = self._photo.width()
        ih = self._photo.height()
        # 居中放置
        x = max(0, (cw - iw) // 2)
        y = max(0, (ch - ih) // 2)
        self._image_id = self._canvas.create_image(x, y, anchor=NW, image=self._photo)
        self._canvas.configure(scrollregion=(0, 0, max(cw, iw), max(ch, ih)))
        self._lbl_zoom.configure(text=f"{int(self._zoom * 100)}%")

    # ---------------- 导航 ----------------

    def show_prev(self):
        if len(self._items) <= 1:
            return
        self._index = (self._index - 1) % len(self._items)
        self._fit_mode = True
        self._zoom = 1.0
        self._load_current()

    def show_next(self):
        if len(self._items) <= 1:
            return
        self._index = (self._index + 1) % len(self._items)
        self._fit_mode = True
        self._zoom = 1.0
        self._load_current()

    def _update_index_label(self):
        self._lbl_index.configure(
            text=f"[{self._index + 1} / {len(self._items)}]  "
                 f"{self._items[self._index]['caption']}"
        )

    def _update_status(self, text: str):
        self._statusbar.configure(text=text)

    # ---------------- 缩放 ----------------

    def set_zoom(self, zoom: float):
        self._fit_mode = False
        self._zoom = max(0.05, min(16.0, float(zoom)))
        self._render()

    def zoom_in(self):
        self._fit_mode = False
        # 找到下一个档位
        for z in self._ZOOM_STEPS:
            if z > self._zoom + 1e-6:
                self._zoom = z
                break
        else:
            self._zoom = min(16.0, self._zoom * 1.25)
        self._render()

    def zoom_out(self):
        self._fit_mode = False
        for z in reversed(self._ZOOM_STEPS):
            if z < self._zoom - 1e-6:
                self._zoom = z
                break
        else:
            self._zoom = max(0.05, self._zoom * 0.8)
        self._render()

    def fit_to_window(self, redraw_only: bool = False):
        if self._src_image is None:
            self._render()
            return
        cw = max(1, self._canvas.winfo_width())
        ch = max(1, self._canvas.winfo_height())
        iw = self._src_image.width
        ih = self._src_image.height
        zoom = min(cw / iw, ch / ih, 1.0)
        self._fit_mode = True
        self._zoom = max(0.05, zoom)
        self._render()

    # ---------------- 事件 ----------------

    def _on_canvas_configure(self, _event):
        if self._fit_mode and self._src_image is not None:
            # 防抖：连续 Configure 时只在最后一次重算
            if hasattr(self, "_fit_after_id") and self._fit_after_id:
                try:
                    self.after_cancel(self._fit_after_id)
                except Exception:
                    pass
            self._fit_after_id = self.after(60, self.fit_to_window)
        else:
            self._render()

    def _on_drag_start(self, event):
        self._drag_start = (event.x, event.y)
        self._scroll_start = (self._canvas.canvasx(0), self._canvas.canvasy(0))
        self._canvas.configure(cursor="fleur")

    def _on_drag_move(self, event):
        if self._drag_start is None:
            return
        dx = event.x - self._drag_start[0]
        dy = event.y - self._drag_start[1]
        # scroll 单位：以滚动总宽度为分母换算
        sr = self._canvas.cget("scrollregion")
        try:
            x0, y0, x1, y1 = [float(v) for v in str(sr).split()]
            sw = max(1.0, x1 - x0)
            sh = max(1.0, y1 - y0)
            self._canvas.xview_moveto((self._scroll_start[0] - dx) / sw)
            self._canvas.yview_moveto((self._scroll_start[1] - dy) / sh)
        except Exception:
            pass

    def _on_drag_end(self, _event):
        self._drag_start = None
        self._canvas.configure(cursor="")

    def _on_mousewheel(self, event):
        # 普通滚轮 = 上下滚动
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_ctrl_mousewheel(self, event):
        # Ctrl+滚轮 = 缩放
        if event.delta > 0:
            self.zoom_in()
        else:
            self.zoom_out()

    def _on_close(self):
        try:
            self._loader.shutdown(wait=False)
        except Exception:
            pass
        self.destroy()

    # ---------------- 类方法：便捷调用 ----------------

    @classmethod
    def show(
        cls,
        parent: Optional[tk.Misc],
        items: Iterable,
        start_index: int = 0,
        **kwargs,
    ) -> "HY127_ImagePreview":
        win = cls(parent, items=items, start_index=start_index, **kwargs)
        # transient 已在 __init__ 内 deiconify 之前设置；这里只补 lift/focus
        win.lift()
        win.focus_force()
        return win


# =============================================================================
# 演示
# =============================================================================

if __name__ == "__main__":  # pragma: no cover
    import sys

    app = ttk.Window(themename="cosmo")
    app.title("HY127_ImagePreview Demo")
    app.geometry("400x200")

    paths = [p for p in sys.argv[1:] if os.path.exists(p)]
    if not paths:
        ttk.Label(
            app,
            text="用法：python HY127_ImagePreview.py <图片1> <图片2> ...",
            padding=20,
        ).pack(expand=YES)
    else:
        ttk.Button(
            app,
            text=f"打开预览（{len(paths)} 张）",
            bootstyle="primary",
            command=lambda: HY127_ImagePreview.show(app, paths),
        ).pack(expand=YES)
    app.mainloop()
