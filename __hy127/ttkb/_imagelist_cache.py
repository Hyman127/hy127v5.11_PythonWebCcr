# -*- coding: utf-8 -*-
"""
HY127_ImageList 内部使用的缩略图缓存与异步加载器（私有模块，外部不直接使用）。

设计目标：
1. 主线程零阻塞：所有磁盘 IO + PIL 解码都在后台线程池里完成
2. 双层缓存：
   - 内存 LRU：最近使用的 PhotoImage（控制总数避免 GC 抖动）
   - 磁盘缓存：缩略图 PNG 持久化到临时目录，下次启动秒开
3. 优先级调度：
   - 当前可视区任务优先（用 generation 标记，旧的一律作废）
   - 滚动后无效的任务在 worker 端跳过解码，进一步省 CPU
4. 容错：
   - 文件不存在 / 解码失败 → 返回占位图，记录错误
   - 提供 PIL/Pillow 缺失时的降级路径（仅 PNG/GIF 通过 tk.PhotoImage 读取）
"""
from __future__ import annotations

import hashlib
import os
import queue
import tempfile
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

import tkinter as tk

# Pillow 是推荐依赖；为容错保留运行时 import
try:
    from PIL import Image, ImageDraw, ImageTk  # type: ignore

    _PIL_AVAILABLE = True
except Exception:  # pragma: no cover - 运行环境不带 Pillow 时
    Image = None  # type: ignore
    ImageDraw = None  # type: ignore
    ImageTk = None  # type: ignore
    _PIL_AVAILABLE = False


# ============================================================================
# 工具函数
# ============================================================================

def is_pil_available() -> bool:
    """是否可用 Pillow（不可用时仅支持 PNG/GIF 原图，无缩略图能力）。"""
    return _PIL_AVAILABLE


def _hash_key(path: str, mtime: float, size: int, thumb_size: int) -> str:
    raw = f"{os.path.abspath(path)}|{int(mtime)}|{size}|{thumb_size}".encode(
        "utf-8", "ignore"
    )
    return hashlib.md5(raw).hexdigest()


def _safe_stat(path: str):
    try:
        st = os.stat(path)
        return st.st_mtime, st.st_size
    except OSError:
        return 0.0, 0


# ============================================================================
# 占位图 / 错误图（一次生成，全控件复用）
# ============================================================================

class _PlaceholderFactory:
    """生成"加载中"和"错误"占位图，按尺寸缓存。"""

    def __init__(self):
        self._cache: dict[tuple[str, int, str], "tk.PhotoImage"] = {}
        self._lock = threading.Lock()

    def get(
        self,
        kind: str,
        size: int,
        bg: str = "#e9ecef",
        fg: str = "#adb5bd",
    ) -> Optional["tk.PhotoImage"]:
        """kind: 'loading' | 'error' | 'blank'。"""
        key = (kind, size, bg)
        with self._lock:
            cached = self._cache.get(key)
        if cached is not None:
            return cached

        if not _PIL_AVAILABLE:
            return None

        img = Image.new("RGB", (size, size), bg)
        draw = ImageDraw.Draw(img)
        # 中心画一个简单图标
        cx, cy = size // 2, size // 2
        r = max(8, size // 6)
        if kind == "error":
            draw.line((cx - r, cy - r, cx + r, cy + r), fill="#dc3545", width=3)
            draw.line((cx - r, cy + r, cx + r, cy - r), fill="#dc3545", width=3)
        elif kind == "loading":
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=fg, width=3)
            draw.line((cx, cy, cx, cy - r), fill=fg, width=3)
        # 'blank' 不画任何东西

        photo = ImageTk.PhotoImage(img)
        with self._lock:
            self._cache[key] = photo
        return photo

    def clear(self):
        with self._lock:
            self._cache.clear()


# 全局共享一份占位图工厂
PLACEHOLDERS = _PlaceholderFactory()


# ============================================================================
# 内存 LRU 缓存
# ============================================================================

class LRUImageCache:
    """主线程使用：以 (cache_key) 为键存放 PhotoImage。

    PhotoImage 必须由主线程持有引用，否则会被 GC 回收变成黑块。
    """

    def __init__(self, max_items: int = 600):
        self._max = max(64, int(max_items))
        self._od: "OrderedDict[str, tk.PhotoImage]" = OrderedDict()

    def set_capacity(self, max_items: int):
        self._max = max(64, int(max_items))
        while len(self._od) > self._max:
            self._od.popitem(last=False)

    def get(self, key: str) -> Optional["tk.PhotoImage"]:
        if key in self._od:
            self._od.move_to_end(key)
            return self._od[key]
        return None

    def put(self, key: str, photo: "tk.PhotoImage"):
        if key in self._od:
            self._od.move_to_end(key)
            self._od[key] = photo
            return
        self._od[key] = photo
        if len(self._od) > self._max:
            self._od.popitem(last=False)

    def clear(self):
        self._od.clear()

    def __len__(self):
        return len(self._od)


# ============================================================================
# 缩略图加载请求 / 异步加载器
# ============================================================================

class _ThumbRequest:
    __slots__ = ("path", "thumb_size", "generation", "cache_key", "callback")

    def __init__(
        self,
        path: str,
        thumb_size: int,
        generation: int,
        cache_key: str,
        callback: Callable[[str, Optional[bytes], Optional[Exception]], None],
    ):
        self.path = path
        self.thumb_size = thumb_size
        self.generation = generation
        self.cache_key = cache_key
        # callback 在 worker 线程中被调用，参数: (cache_key, png_bytes_or_path, error)
        self.callback = callback


class ThumbLoader:
    """缩略图异步加载器。

    用法：
        loader = ThumbLoader(cache_dir=..., on_done=主线程回调, tk_root=...)
        loader.set_generation(n)        # 滚动/缩放时调用，让旧任务作废
        loader.submit(path, thumb_size) # 提交一个任务
        loader.shutdown()               # 销毁

    on_done 在主线程被调用：on_done(cache_key, photo_or_None, error_or_None, path, thumb_size)
    """

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        max_workers: int = 4,
        on_done: Optional[Callable] = None,
        tk_root: Optional[tk.Misc] = None,
    ):
        if cache_dir is None:
            cache_dir = os.path.join(tempfile.gettempdir(), "hy127_imagelist_cache")
        try:
            os.makedirs(cache_dir, exist_ok=True)
        except OSError:
            cache_dir = tempfile.gettempdir()

        self.cache_dir = cache_dir
        self._on_done = on_done
        self._tk_root = tk_root

        self._executor = ThreadPoolExecutor(
            max_workers=max(1, int(max_workers)),
            thread_name_prefix="HY127ImgThumb",
        )
        self._generation = 0
        self._gen_lock = threading.Lock()
        # path+size -> 已经在队列中的标记，避免重复提交
        self._pending: set[str] = set()
        self._pending_lock = threading.Lock()

        # 主线程回调队列（worker 完成后塞结果，主线程通过 after 取出）
        self._result_queue: "queue.Queue[tuple]" = queue.Queue()
        self._poller_running = False
        self._shutdown = False

    # ---------------- 公共 API ----------------

    def set_generation(self, gen: int):
        """更新当前 generation。worker 取任务时若发现 task.generation < 当前 → 直接丢弃。"""
        with self._gen_lock:
            self._generation = int(gen)

    def get_generation(self) -> int:
        with self._gen_lock:
            return self._generation

    def make_cache_key(self, path: str, thumb_size: int) -> str:
        mtime, size = _safe_stat(path)
        return _hash_key(path, mtime, size, thumb_size)

    def get_disk_cached_photo(
        self, path: str, thumb_size: int
    ) -> Optional["tk.PhotoImage"]:
        """同步检查磁盘缓存，命中则直接返回 PhotoImage（必须在主线程调用）。"""
        if not _PIL_AVAILABLE:
            return None
        key = self.make_cache_key(path, thumb_size)
        cache_path = os.path.join(self.cache_dir, key + ".png")
        if not os.path.exists(cache_path):
            return None
        try:
            img = Image.open(cache_path)
            img.load()
            return ImageTk.PhotoImage(img)
        except Exception:
            return None

    def submit(
        self,
        path: str,
        thumb_size: int,
        generation: Optional[int] = None,
    ) -> str:
        """异步提交一个缩略图任务，返回 cache_key。"""
        if generation is None:
            generation = self.get_generation()
        cache_key = self.make_cache_key(path, thumb_size)
        dedup_key = f"{cache_key}@{generation}"
        with self._pending_lock:
            if dedup_key in self._pending:
                return cache_key
            self._pending.add(dedup_key)

        self._executor.submit(
            self._worker, path, thumb_size, generation, cache_key, dedup_key
        )
        self._ensure_poller()
        return cache_key

    def shutdown(self, wait: bool = False):
        self._shutdown = True
        try:
            self._executor.shutdown(wait=wait, cancel_futures=True)
        except TypeError:
            # Python < 3.9 兼容（项目要求 3.12，这里只是兜底）
            self._executor.shutdown(wait=wait)

    # ---------------- 内部 ----------------

    def _ensure_poller(self):
        """启动主线程定时轮询（只启动一次）。"""
        if self._poller_running or self._tk_root is None:
            return
        self._poller_running = True
        self._tk_root.after(20, self._poll_results)

    def _poll_results(self):
        if self._shutdown:
            self._poller_running = False
            return
        # 一次最多处理 64 条，避免突发任务占住主线程
        processed = 0
        try:
            while processed < 64:
                cache_key, png_bytes, err, path, thumb_size, gen = (
                    self._result_queue.get_nowait()
                )
                processed += 1
                # 过滤过期 generation
                if gen >= 0 and gen < self.get_generation() - 1:
                    # 允许差 1 代避免边界抖动
                    pass  # 仍然交付，主线程自己再判断是否使用
                photo = None
                if png_bytes is not None and _PIL_AVAILABLE:
                    try:
                        # png_bytes 可能是 bytes，也可能是磁盘路径（命中磁盘缓存时）
                        if isinstance(png_bytes, str):
                            img = Image.open(png_bytes)
                            img.load()
                        else:
                            from io import BytesIO

                            img = Image.open(BytesIO(png_bytes))
                            img.load()
                        photo = ImageTk.PhotoImage(img)
                    except Exception as e:
                        err = err or e
                        photo = None
                if self._on_done is not None:
                    try:
                        self._on_done(cache_key, photo, err, path, thumb_size, gen)
                    except Exception:
                        # 避免回调抛异常打断轮询
                        pass
        except queue.Empty:
            pass

        if not self._shutdown:
            # 有持续任务时继续 20ms 轮询，空闲后退化为 60ms
            delay = 20 if not self._result_queue.empty() else 60
            self._tk_root.after(delay, self._poll_results)
        else:
            self._poller_running = False

    def _worker(
        self,
        path: str,
        thumb_size: int,
        generation: int,
        cache_key: str,
        dedup_key: str,
    ):
        """worker 线程：解码 + 缩放 + 写磁盘缓存。"""
        try:
            # 任务"过期"且差距较大 → 跳过，节约 CPU
            current_gen = self.get_generation()
            if generation < current_gen - 2:
                self._result_queue.put(
                    (cache_key, None, None, path, thumb_size, generation)
                )
                return

            cache_path = os.path.join(self.cache_dir, cache_key + ".png")

            # 1) 命中磁盘缓存：直接交付路径
            if os.path.exists(cache_path):
                try:
                    # 校验文件可读
                    if os.path.getsize(cache_path) > 0:
                        self._result_queue.put(
                            (cache_key, cache_path, None, path, thumb_size, generation)
                        )
                        return
                except OSError:
                    pass

            if not os.path.exists(path):
                self._result_queue.put(
                    (cache_key, None, FileNotFoundError(path), path, thumb_size, generation)
                )
                return

            if not _PIL_AVAILABLE:
                # 没有 Pillow，无法缩放；让主线程自己 fallback 到 tk.PhotoImage
                self._result_queue.put(
                    (cache_key, None, RuntimeError("Pillow not available"),
                     path, thumb_size, generation)
                )
                return

            # 2) PIL 解码 + 缩放
            with Image.open(path) as src:
                src.load()
                # 转 RGBA 避免 P/CMYK 模式问题
                if src.mode not in ("RGB", "RGBA"):
                    src = src.convert("RGBA")
                # 等比缩放到 thumb_size x thumb_size 以内
                src.thumbnail(
                    (thumb_size, thumb_size),
                    Image.Resampling.LANCZOS,
                )

                # 居中放在正方形画布上，方便网格对齐
                canvas_bg = (255, 255, 255, 0) if src.mode == "RGBA" else (255, 255, 255)
                canvas = Image.new(src.mode, (thumb_size, thumb_size), canvas_bg)
                ox = (thumb_size - src.width) // 2
                oy = (thumb_size - src.height) // 2
                canvas.paste(src, (ox, oy))

                # 3) 写盘 + 交付 bytes（避免主线程二次开盘）
                from io import BytesIO

                buf = BytesIO()
                canvas.save(buf, format="PNG", optimize=False)
                png_bytes = buf.getvalue()

                # 异步落盘（失败也不影响 UI）
                try:
                    with open(cache_path, "wb") as f:
                        f.write(png_bytes)
                except OSError:
                    pass

                self._result_queue.put(
                    (cache_key, png_bytes, None, path, thumb_size, generation)
                )
        except Exception as e:
            self._result_queue.put(
                (cache_key, None, e, path, thumb_size, generation)
            )
        finally:
            with self._pending_lock:
                self._pending.discard(dedup_key)


# ============================================================================
# 大图（hover / 双击预览）异步加载
# ============================================================================

class PreviewLoader:
    """中/大尺寸预览图的异步加载器（独立线程池，与缩略图互不抢资源）。"""

    def __init__(self, max_workers: int = 2, tk_root: Optional[tk.Misc] = None):
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, int(max_workers)),
            thread_name_prefix="HY127ImgPreview",
        )
        self._tk_root = tk_root
        self._req_id = 0
        self._latest_id_lock = threading.Lock()
        self._latest_id_for_target: dict[str, int] = {}

    def request(
        self,
        path: str,
        max_size: int,
        target: str,
        callback: Callable[[Optional["tk.PhotoImage"], Optional[Exception], int], None],
    ) -> int:
        """提交大图加载请求。

        target: 区分目的地的字符串（例如 "hover" / "preview"），同一 target 后续请求会
                让旧请求的回调被忽略。
        callback 在主线程被调用：(photo, err, req_id)
        """
        with self._latest_id_lock:
            self._req_id += 1
            rid = self._req_id
            self._latest_id_for_target[target] = rid

        future = self._executor.submit(self._load, path, max_size)

        def _done(fut):
            err = None
            png_bytes = None
            try:
                png_bytes = fut.result()
            except Exception as e:
                err = e

            def _on_main():
                # 已被更新请求覆盖 → 丢弃
                with self._latest_id_lock:
                    if self._latest_id_for_target.get(target) != rid:
                        return
                photo = None
                if png_bytes is not None and _PIL_AVAILABLE:
                    try:
                        from io import BytesIO

                        img = Image.open(BytesIO(png_bytes))
                        img.load()
                        photo = ImageTk.PhotoImage(img)
                    except Exception as e:
                        err_local = e
                        callback(None, err_local, rid)
                        return
                callback(photo, err, rid)

            if self._tk_root is not None:
                try:
                    self._tk_root.after(0, _on_main)
                except RuntimeError:
                    # 主循环已退出
                    pass

        future.add_done_callback(_done)
        return rid

    def _load(self, path: str, max_size: int) -> Optional[bytes]:
        if not _PIL_AVAILABLE:
            raise RuntimeError("Pillow not available")
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        with Image.open(path) as src:
            src.load()
            if src.mode not in ("RGB", "RGBA"):
                src = src.convert("RGBA")
            if max(src.width, src.height) > max_size:
                src.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            from io import BytesIO

            buf = BytesIO()
            src.save(buf, format="PNG", optimize=False)
            return buf.getvalue()

    def shutdown(self, wait: bool = False):
        try:
            self._executor.shutdown(wait=wait, cancel_futures=True)
        except TypeError:
            self._executor.shutdown(wait=wait)
