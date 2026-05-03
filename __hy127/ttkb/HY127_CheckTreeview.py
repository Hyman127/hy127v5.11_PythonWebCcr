# -*- coding: utf-8 -*-
"""
增强 Treeview 组件（性能优化版）。

特性：
- 使用文本复选框字符实现三态勾选，不依赖图片资源
- 内部以 _TreeNode 集中维护父/子/原文本/状态/tag，避免反复 get_children
- 批量更新机制，状态改变时只算不画，最后统一刷新文本，性能可支撑数万节点
- 单击节点支持原生折叠/展开三角；点击复选框区域才触发勾选切换
- 运行时可显示/隐藏复选框（show_checkboxes / set_checkboxes_visible）
- 监听 <<ThemeChanged>> 自动适配主题切换
- 内置横纵滚动条，按需自动显示
- 完全向后兼容 ttkbootstrap.Treeview 与原 HY127_CheckTreeview 的 API
"""
from __future__ import annotations

from contextlib import contextmanager
import tkinter as tk
import tkinter.font as tkfont

import ttkbootstrap as ttk
from ttkbootstrap.constants import *


EVENT_CHECKTREE_CHANGED = "<<HY127CheckTreeviewChanged>>"
EVENT_CHECKTREE_ITEM_TOGGLED = "<<HY127CheckTreeviewItemToggled>>"


class _TreeNode:
    """节点元数据。集中存放父/子/原文本/状态/是否文件夹/tag。"""

    __slots__ = ("parent", "children", "is_folder", "original_text", "state", "tag")

    def __init__(self, parent="", is_folder=None, original_text="", state=0, tag=None):
        self.parent = parent
        self.children = []
        self.is_folder = is_folder
        self.original_text = original_text
        self.state = state
        self.tag = tag


class HY127_CheckTreeview(ttk.Frame):
    """带三态复选框的增强 Treeview。"""

    STATE_UNCHECKED = 0
    STATE_PARTIAL = 1
    STATE_CHECKED = 2

    DEFAULT_CHECKBOX_CHARS = {
        STATE_UNCHECKED: "⬜",
        STATE_PARTIAL: "🔳",
        STATE_CHECKED: "✅",
    }
    _CHECKBOX_TEXT_GAP = " "

    _EXTRA_OPTIONS = {
        "auto_scrollbars",
        "cascade_check",
        "checkbox_chars",
        "clickable_region",
        "checkbox_column",
        "show_checkboxes",
    }

    def __init__(
        self,
        master=None,
        *,
        columns=None,
        displaycolumns=None,
        height=None,
        selectmode=None,
        show=TREE,
        style=None,
        bootstyle=PRIMARY,
        takefocus=True,
        cursor=None,
        auto_scrollbars=True,
        cascade_check=True,
        checkbox_chars=None,
        clickable_region="tree",
        checkbox_column="#0",
        show_checkboxes=True,
        **kwargs,
    ):
        super().__init__(master, **kwargs)

        self._auto_scrollbars = bool(auto_scrollbars)
        self._cascade_check = bool(cascade_check)
        self._clickable_region = clickable_region
        self._checkbox_column = checkbox_column
        self._show_checkboxes = bool(show_checkboxes)
        self._bootstyle = bootstyle
        self._checkbox_chars = dict(self.DEFAULT_CHECKBOX_CHARS)
        if checkbox_chars:
            self._checkbox_chars.update(checkbox_chars)

        normalized_show = self._normalize_show(show)
        self._tree = ttk.Treeview(
            self,
            columns=columns,
            displaycolumns=displaycolumns,
            height=height,
            selectmode=selectmode,
            show=normalized_show,
            style=style,
            bootstyle=bootstyle,
            takefocus=takefocus,
            cursor=cursor,
        )
        self.tree = self._tree
        self.view = self._tree

        self._vbar = ttk.Scrollbar(self, orient=VERTICAL, command=self._tree.yview)
        self._hbar = ttk.Scrollbar(self, orient=HORIZONTAL, command=self._tree.xview)
        self._tree.configure(yscrollcommand=self._on_yscroll, xscrollcommand=self._on_xscroll)

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._tree.grid(row=0, column=0, sticky=NSEW)
        self._vbar.grid(row=0, column=1, sticky=NS)
        self._hbar.grid(row=1, column=0, sticky=EW)

        # 节点元数据集中存储；"" 表示根，预先建一个虚拟节点便于统一处理 children
        self._nodes = {"": _TreeNode(parent=None, is_folder=True, original_text="", state=self.STATE_UNCHECKED)}

        self._bulk_level = 0
        self._batch_updates = set()
        self._pending_changed = False
        self._scrollbar_update_after_id = None
        self._emit_after_id = None
        self.last_toggled_item = None

        self._bind_events()
        self._update_scrollbar_visibility()

    # ------------------------------------------------------------------
    # 透传未知方法给原生 Treeview，最大程度兼容系统组件用法
    # ------------------------------------------------------------------
    def __getattr__(self, name):
        tree = self.__dict__.get("_tree")
        if tree is not None and hasattr(tree, name):
            return getattr(tree, name)
        raise AttributeError(f"{type(self).__name__!s} object has no attribute {name!r}")

    @staticmethod
    def _normalize_show(show):
        tokens = []
        if show:
            tokens = [str(part) for part in str(show).split() if str(part).strip()]
        if "tree" not in tokens:
            tokens.insert(0, "tree")
        deduped = []
        for token in tokens:
            if token not in deduped:
                deduped.append(token)
        return " ".join(deduped) if deduped else "tree"

    def _bind_events(self):
        self._tree.bind("<Button-1>", self._on_tree_click, add="+")
        self._tree.bind("<space>", self._on_space, add="+")
        self._tree.bind("<<TreeviewOpen>>", self._queue_scrollbar_update, add="+")
        self._tree.bind("<<TreeviewClose>>", self._queue_scrollbar_update, add="+")
        self._tree.bind("<Configure>", self._queue_scrollbar_update, add="+")
        self.bind("<<ThemeChanged>>", self._on_theme_changed, add="+")
        self._tree.bind("<<ThemeChanged>>", self._on_theme_changed, add="+")

    # ------------------------------------------------------------------
    # configure / cget / keys：兼容原 API + 新增 show_checkboxes
    # ------------------------------------------------------------------
    def configure(self, cnf=None, **kwargs):
        if self.__dict__.get("_tree") is None:
            if cnf and isinstance(cnf, dict):
                kwargs.update(cnf)
                cnf = None
            if cnf is not None and not kwargs:
                return super().configure(cnf)
            return super().configure(**kwargs)

        if cnf is not None and not kwargs and isinstance(cnf, str):
            return self.cget(cnf)

        if cnf and isinstance(cnf, dict):
            kwargs.update(cnf)

        tree_kwargs = {}
        frame_kwargs = {}
        need_full_refresh = False

        for key, value in list(kwargs.items()):
            if key == "auto_scrollbars":
                self._auto_scrollbars = bool(value)
            elif key == "cascade_check":
                self._cascade_check = bool(value)
            elif key == "checkbox_chars":
                self._checkbox_chars = dict(self.DEFAULT_CHECKBOX_CHARS)
                if value:
                    self._checkbox_chars.update(value)
                need_full_refresh = True
            elif key == "clickable_region":
                self._clickable_region = str(value)
            elif key == "checkbox_column":
                self._checkbox_column = str(value)
            elif key == "show_checkboxes":
                if bool(value) != self._show_checkboxes:
                    self._show_checkboxes = bool(value)
                    need_full_refresh = True
            elif key == "show":
                tree_kwargs[key] = self._normalize_show(value)
            elif key in self._tree.keys():
                tree_kwargs[key] = value
            else:
                frame_kwargs[key] = value

        if frame_kwargs:
            super().configure(**frame_kwargs)
        if tree_kwargs:
            self._tree.configure(**tree_kwargs)
            self._queue_scrollbar_update()
        if need_full_refresh:
            self._refresh_all_texts()
        if not self._auto_scrollbars:
            self._vbar.grid()
            self._hbar.grid()
        else:
            self._update_scrollbar_visibility()

    config = configure

    def cget(self, key):
        if self.__dict__.get("_tree") is None:
            return super().cget(key)
        if key == "auto_scrollbars":
            return self._auto_scrollbars
        if key == "cascade_check":
            return self._cascade_check
        if key == "checkbox_chars":
            return dict(self._checkbox_chars)
        if key == "clickable_region":
            return self._clickable_region
        if key == "checkbox_column":
            return self._checkbox_column
        if key == "show_checkboxes":
            return self._show_checkboxes
        if key in self._tree.keys():
            return self._tree.cget(key)
        return super().cget(key)

    def keys(self):
        if self.__dict__.get("_tree") is None:
            return list(super().keys())
        merged = list(super().keys())
        for key in self._tree.keys():
            if key not in merged:
                merged.append(key)
        for key in sorted(self._EXTRA_OPTIONS):
            if key not in merged:
                merged.append(key)
        return merged

    # ------------------------------------------------------------------
    # 滚动条
    # ------------------------------------------------------------------
    def _on_yscroll(self, first, last):
        self._vbar.set(first, last)
        if self._auto_scrollbars:
            self._update_scrollbar_visibility()

    def _on_xscroll(self, first, last):
        self._hbar.set(first, last)
        if self._auto_scrollbars:
            self._update_scrollbar_visibility()

    def _queue_scrollbar_update(self, event=None):
        if self._scrollbar_update_after_id is not None:
            try:
                self.after_cancel(self._scrollbar_update_after_id)
            except tk.TclError:
                pass
        self._scrollbar_update_after_id = self.after_idle(self._update_scrollbar_visibility)

    def _update_scrollbar_visibility(self):
        self._scrollbar_update_after_id = None
        if not self.winfo_exists():
            return
        if not self._auto_scrollbars:
            self._vbar.grid()
            self._hbar.grid()
            return

        v_first, v_last = self._vbar.get()
        h_first, h_last = self._hbar.get()

        if v_first <= 0 and v_last >= 1:
            self._vbar.grid_remove()
        else:
            self._vbar.grid()

        if h_first <= 0 and h_last >= 1:
            self._hbar.grid_remove()
        else:
            self._hbar.grid()

    # ------------------------------------------------------------------
    # 主题切换：刷新行高/字体相关并重画文本
    # ------------------------------------------------------------------
    def _on_theme_changed(self, event=None):
        # 不强制改 foreground/background，避免破坏 emoji 彩色字形；
        # 只重画一次文本，确保新字体下度量正确，并刷新滚动条可见性
        try:
            self._refresh_all_texts()
        except tk.TclError:
            pass
        self._queue_scrollbar_update()

    # ------------------------------------------------------------------
    # 状态规范化与文本组装
    # ------------------------------------------------------------------
    def _normalize_state(self, value):
        if value in (True, self.STATE_CHECKED, "checked", "on", 2):
            return self.STATE_CHECKED
        if value in (self.STATE_PARTIAL, "partial", "mixed", 1):
            return self.STATE_PARTIAL
        return self.STATE_UNCHECKED

    def _checkbox_char(self, state):
        return self._checkbox_chars.get(state, self.DEFAULT_CHECKBOX_CHARS[state])

    def _checkbox_prefix(self, state):
        return f"{self._checkbox_char(state)}{self._CHECKBOX_TEXT_GAP}"

    def _compose_text(self, item):
        node = self._nodes.get(item)
        if node is None:
            return ""
        if not self._show_checkboxes:
            return node.original_text
        return f"{self._checkbox_prefix(node.state)}{node.original_text}".rstrip()

    def _apply_item_text(self, item):
        if not self._tree.exists(item):
            return
        try:
            self._tree.item(item, text=self._compose_text(item))
        except tk.TclError:
            pass

    def _refresh_all_texts(self):
        for item in self._nodes:
            if item == "":
                continue
            self._apply_item_text(item)
        self._queue_scrollbar_update()

    # ------------------------------------------------------------------
    # 节点遍历（为兼容旧测试，保留 _walk_items）
    # ------------------------------------------------------------------
    def _walk_items(self, start=""):
        node = self._nodes.get(start)
        if node is None:
            return
        stack = list(reversed(node.children))
        while stack:
            current = stack.pop()
            yield current
            current_node = self._nodes.get(current)
            if current_node and current_node.children:
                stack.extend(reversed(current_node.children))

    # ------------------------------------------------------------------
    # 是否文件夹：未显式指定时按"是否有子节点"动态判断
    # ------------------------------------------------------------------
    def _is_folder(self, item):
        node = self._nodes.get(item)
        if node is None:
            return False
        if node.is_folder is True:
            return True
        if node.is_folder is False:
            return False
        return bool(node.children)

    # ------------------------------------------------------------------
    # 状态计算
    # ------------------------------------------------------------------
    def _calc_parent_state(self, parent_id):
        node = self._nodes.get(parent_id)
        if node is None or not node.children:
            return self.STATE_UNCHECKED

        all_checked = True
        all_unchecked = True
        for child_id in node.children:
            child_state = self._nodes[child_id].state
            if child_state == self.STATE_PARTIAL:
                return self.STATE_PARTIAL
            if child_state == self.STATE_CHECKED:
                all_unchecked = False
            else:  # UNCHECKED
                all_checked = False
            if not all_checked and not all_unchecked:
                return self.STATE_PARTIAL
        if all_checked:
            return self.STATE_CHECKED
        return self.STATE_UNCHECKED

    def _propagate_down(self, item, target_state):
        """向下传播；只把状态确实改变的节点加入 batch。"""
        stack = [item]
        while stack:
            current = stack.pop()
            node = self._nodes.get(current)
            if node is None:
                continue
            for child_id in node.children:
                child_node = self._nodes[child_id]
                if child_node.state != target_state:
                    child_node.state = target_state
                    self._batch_updates.add(child_id)
                if child_node.children:
                    stack.append(child_id)

    def _propagate_up(self, item):
        """向上传播；状态没变即提前终止。"""
        node = self._nodes.get(item)
        if node is None:
            return
        current_id = node.parent
        while current_id:
            current_node = self._nodes.get(current_id)
            if current_node is None:
                return
            new_state = self._calc_parent_state(current_id)
            if current_node.state == new_state:
                return
            current_node.state = new_state
            self._batch_updates.add(current_id)
            current_id = current_node.parent

    def _execute_batch_updates(self, force=False):
        if force:
            for item in self._nodes:
                if item == "":
                    continue
                self._apply_item_text(item)
            self._batch_updates.clear()
            return
        if not self._batch_updates:
            return
        for item in self._batch_updates:
            self._apply_item_text(item)
        self._batch_updates.clear()

    def _mark_changed(self, item=None, *, emit_toggle=False):
        self._pending_changed = True
        if item is not None:
            self.last_toggled_item = item
        if self._bulk_level > 0:
            return
        if emit_toggle and item is not None:
            try:
                self.event_generate(EVENT_CHECKTREE_ITEM_TOGGLED, when="tail")
            except tk.TclError:
                pass
        self._emit_changed_event()

    def _emit_changed_event(self):
        if self._emit_after_id is not None:
            try:
                self.after_cancel(self._emit_after_id)
            except tk.TclError:
                pass
        self._emit_after_id = self.after_idle(self._emit_changed_event_now)

    def _emit_changed_event_now(self):
        self._emit_after_id = None
        if not self._pending_changed:
            return
        self._pending_changed = False
        try:
            self.event_generate(EVENT_CHECKTREE_CHANGED, when="tail")
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # 公共 API：勾选状态
    # ------------------------------------------------------------------
    def set_check_state(self, item, state, *, cascade=None, silent=False):
        node = self._nodes.get(item)
        if node is None or not self._tree.exists(item):
            return False

        desired_state = self._normalize_state(state)
        cascade = self._cascade_check if cascade is None else bool(cascade)
        has_children = bool(node.children)

        changed = False
        if desired_state == self.STATE_PARTIAL:
            if node.state != self.STATE_PARTIAL:
                node.state = self.STATE_PARTIAL
                self._batch_updates.add(item)
                changed = True
        else:
            if node.state != desired_state:
                node.state = desired_state
                self._batch_updates.add(item)
                changed = True
            if cascade and has_children:
                self._propagate_down(item, desired_state)
                if self._batch_updates:
                    changed = True

        self._propagate_up(item)
        if self._batch_updates:
            changed = True

        if self._bulk_level == 0:
            self._execute_batch_updates()
            if changed and not silent:
                self._mark_changed(item, emit_toggle=True)
        else:
            if changed and not silent:
                self._pending_changed = True
                self.last_toggled_item = item
        return changed

    def check(self, *items, silent=False):
        targets = self._normalize_items_argument(items)
        return self._set_many_states(targets, self.STATE_CHECKED, silent=silent)

    def uncheck(self, *items, silent=False):
        targets = self._normalize_items_argument(items)
        return self._set_many_states(targets, self.STATE_UNCHECKED, silent=silent)

    def toggle_check(self, item, silent=False):
        node = self._nodes.get(item)
        if node is None or not self._tree.exists(item):
            return False
        if node.state == self.STATE_CHECKED:
            return self.set_check_state(item, self.STATE_UNCHECKED, silent=silent)
        return self.set_check_state(item, self.STATE_CHECKED, silent=silent)

    def _set_many_states(self, items, state, silent=False):
        changed = False
        with self.bulk_update(emit=not silent):
            for item in items:
                if self.set_check_state(item, state, silent=True):
                    changed = True
        if changed:
            self._pending_changed = not silent
        return changed

    def get_check_state(self, item):
        node = self._nodes.get(item)
        if node is None:
            return self.STATE_UNCHECKED
        return node.state

    def is_checked(self, item):
        return self.get_check_state(item) == self.STATE_CHECKED

    def get_checked_items(self, include_partially_checked=False, leaf_only=False):
        result = []
        for item, node in self._nodes.items():
            if item == "":
                continue
            if leaf_only and node.children:
                continue
            if node.state == self.STATE_CHECKED:
                result.append(item)
            elif include_partially_checked and node.state == self.STATE_PARTIAL:
                result.append(item)
        return result

    def get_checked_texts(self, include_partially_checked=False, leaf_only=False):
        return [
            self._nodes[item].original_text
            for item in self.get_checked_items(
                include_partially_checked=include_partially_checked,
                leaf_only=leaf_only,
            )
            if item in self._nodes
        ]

    def set_propagate_check(self, enabled=True):
        self._cascade_check = bool(enabled)

    def get_propagate_check(self):
        return self._cascade_check

    def check_all(self, silent=False):
        """全选：直接平铺循环，O(N) 写入，绕过单点传播。"""
        return self._fill_all_states(self.STATE_CHECKED, silent=silent)

    def uncheck_all(self, silent=False):
        """全不选：直接平铺循环，O(N) 写入。"""
        return self._fill_all_states(self.STATE_UNCHECKED, silent=silent)

    def _fill_all_states(self, target_state, silent=False):
        changed = False
        for item, node in self._nodes.items():
            if item == "":
                continue
            if node.state != target_state:
                node.state = target_state
                self._batch_updates.add(item)
                changed = True
        if changed:
            self._execute_batch_updates()
            self._queue_scrollbar_update()
            if not silent:
                self._pending_changed = True
                self._emit_changed_event()
        return changed

    # ------------------------------------------------------------------
    # 批量更新
    # ------------------------------------------------------------------
    def begin_bulk_update(self):
        self._bulk_level += 1

    def end_bulk_update(self, emit=True):
        if self._bulk_level <= 0:
            return
        self._bulk_level -= 1
        if self._bulk_level > 0:
            return
        # 批量插入完成后：刷新所有未刷新文本 + 重算所有父节点状态 + 滚动条
        self._reconcile_states_after_bulk()
        self._execute_batch_updates()
        self._queue_scrollbar_update()
        # 强制立即刷新滚动条以应对大数据加载
        try:
            self.update_idletasks()
        except tk.TclError:
            pass
        self._update_scrollbar_visibility()
        if emit and self._pending_changed:
            self._emit_changed_event()
        elif not emit:
            self._pending_changed = False

    def _reconcile_states_after_bulk(self):
        """批量插入后，按子节点状态重算所有父节点状态（不发事件）。
        遍历顺序：从最深的节点向上算（用栈做后序）。
        """
        # 后序遍历：先收集所有节点的访问顺序
        order = []
        stack = list(reversed(self._nodes[""].children))
        while stack:
            current = stack.pop()
            order.append(current)
            node = self._nodes.get(current)
            if node and node.children:
                stack.extend(reversed(node.children))
        # 反向遍历就是后序
        for current in reversed(order):
            node = self._nodes.get(current)
            if node is None or not node.children:
                # 叶子节点的状态在 insert 时已写好文本，无需重画
                continue
            new_state = self._calc_parent_state(current)
            if node.state != new_state:
                node.state = new_state
                self._batch_updates.add(current)

    @contextmanager
    def bulk_update(self, emit=True):
        self.begin_bulk_update()
        try:
            yield self
        finally:
            self.end_bulk_update(emit=emit)

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
    def _normalize_items_argument(self, items):
        if len(items) == 1 and isinstance(items[0], (list, tuple, set)):
            return [item for item in items[0] if self._tree.exists(item)]
        return [item for item in items if self._tree.exists(item)]

    # ------------------------------------------------------------------
    # 增删改查
    # ------------------------------------------------------------------
    def insert(self, parent, index, iid=None, *, is_folder=None, tag=None, **kwargs):
        """插入节点。

        扩展参数:
            checked / check_state: 初始勾选状态
            is_folder: True/False 强制指定；None 时按"是否有子节点"动态判断
            tag: 自定义标签数据
        """
        checked = kwargs.pop("checked", None)
        check_state = kwargs.pop("check_state", checked)
        raw_text = str(kwargs.get("text", ""))
        normalized_state = self._normalize_state(check_state)

        # 直接组装显示文本，避免插入后再 item(..., text=...) 二次开销
        if self._show_checkboxes:
            kwargs["text"] = f"{self._checkbox_char(normalized_state)}{self._CHECKBOX_TEXT_GAP}{raw_text}".rstrip()
        else:
            kwargs["text"] = raw_text

        normalized_parent = parent or ""
        # 确保父节点元数据存在（兼容外部直接调用底层 self._tree.insert 的情况）
        if normalized_parent not in self._nodes:
            self._sync_node(normalized_parent)

        item = self._tree.insert(parent, index, iid=iid, **kwargs)
        node = _TreeNode(
            parent=normalized_parent,
            is_folder=is_folder,
            original_text=raw_text,
            state=normalized_state,
            tag=tag,
        )
        self._nodes[item] = node

        parent_node = self._nodes.get(normalized_parent)
        if parent_node is not None:
            # index 可能是 "end" 或整数；统一按 tree 的真实顺序插
            if index == "end" or index == END or index == -1:
                parent_node.children.append(item)
            else:
                try:
                    parent_node.children.insert(int(index), item)
                except (ValueError, TypeError):
                    parent_node.children.append(item)

        if self._bulk_level == 0:
            # 非批量模式才刷祖先（叶子的父链）
            if normalized_state != self.STATE_UNCHECKED:
                self._propagate_up(item)
                self._execute_batch_updates()
            self._queue_scrollbar_update()
        else:
            self._pending_changed = True
        return item

    def _sync_node(self, item):
        """从底层 Treeview 同步一个未在 _nodes 中的节点（兜底）。"""
        if item == "" and "" not in self._nodes:
            self._nodes[""] = _TreeNode(parent=None, is_folder=True, original_text="", state=self.STATE_UNCHECKED)
            return
        if not self._tree.exists(item):
            return
        parent = self._tree.parent(item) or ""
        if parent and parent not in self._nodes:
            self._sync_node(parent)
        raw_text = self._tree.item(item, "text") or ""
        # 剥离已存在的复选框前缀
        for state in (self.STATE_UNCHECKED, self.STATE_PARTIAL, self.STATE_CHECKED):
            prefix = self._checkbox_prefix(state)
            if raw_text.startswith(prefix):
                raw_text = raw_text[len(prefix):]
                break
        self._nodes[item] = _TreeNode(parent=parent, original_text=raw_text)
        parent_node = self._nodes.get(parent)
        if parent_node is not None and item not in parent_node.children:
            parent_node.children.append(item)

    def item(self, item, option=None, **kwargs):
        """兼容 item 查询；text 视为未带复选框前缀的原文本。"""
        node = self._nodes.get(item)

        if not kwargs:
            if option == "text":
                if node is not None:
                    return node.original_text
                return self._tree.item(item, "text")
            if option is not None:
                return self._tree.item(item, option)
            result = self._tree.item(item)
            if node is not None:
                result["text"] = node.original_text
                result["check_state"] = node.state
            return result

        if "text" in kwargs:
            new_text = str(kwargs.pop("text"))
            if node is not None:
                node.original_text = new_text
            else:
                # 兜底：直接设置底层
                self._tree.item(item, text=new_text)
        if "checked" in kwargs:
            kwargs["check_state"] = kwargs.pop("checked")
        if "check_state" in kwargs:
            state = kwargs.pop("check_state")
            self.set_check_state(item, state, silent=True)
        if "tag" in kwargs and node is not None:
            node.tag = kwargs.pop("tag")
        if "is_folder" in kwargs and node is not None:
            node.is_folder = kwargs.pop("is_folder")
        if kwargs:
            self._tree.item(item, **kwargs)
        if node is not None:
            self._apply_item_text(item)
        return self._tree.item(item)

    def delete(self, *items):
        existing = self._normalize_items_argument(items)
        if not existing:
            return

        affected_parents = set()
        for item in existing:
            node = self._nodes.get(item)
            parent = node.parent if node is not None else (self._tree.parent(item) or "")
            affected_parents.add(parent or "")
            self._discard_subtree(item)

        self._tree.delete(*existing)
        for parent in affected_parents:
            self._propagate_up_at(parent)
        self._execute_batch_updates()
        self._queue_scrollbar_update()
        self._mark_changed(None, emit_toggle=False)

    def _discard_subtree(self, item):
        """从 _nodes 中删除 item 及其全部后代，并从父节点 children 列表中移除。"""
        node = self._nodes.pop(item, None)
        if node is None:
            return
        parent_node = self._nodes.get(node.parent)
        if parent_node is not None:
            try:
                parent_node.children.remove(item)
            except ValueError:
                pass
        # 后代
        stack = list(node.children)
        while stack:
            current = stack.pop()
            current_node = self._nodes.pop(current, None)
            if current_node is not None:
                stack.extend(current_node.children)

    def _propagate_up_at(self, parent_item):
        """从给定父节点开始向上重算状态（用于 delete/move 等结构变更）。"""
        current_id = parent_item
        while current_id:
            current_node = self._nodes.get(current_id)
            if current_node is None:
                return
            new_state = self._calc_parent_state(current_id)
            if current_node.state == new_state:
                return
            current_node.state = new_state
            self._batch_updates.add(current_id)
            current_id = current_node.parent

    def clear(self):
        roots = list(self._nodes[""].children)
        if roots:
            self.delete(*roots)

    def move(self, item, parent, index):
        node = self._nodes.get(item)
        old_parent = node.parent if node is not None else (self._tree.parent(item) or "")
        new_parent = parent or ""

        self._tree.move(item, parent, index)

        if node is not None:
            old_parent_node = self._nodes.get(old_parent)
            if old_parent_node is not None:
                try:
                    old_parent_node.children.remove(item)
                except ValueError:
                    pass
            node.parent = new_parent
            new_parent_node = self._nodes.get(new_parent)
            if new_parent_node is not None:
                if index == "end" or index == END or index == -1:
                    new_parent_node.children.append(item)
                else:
                    try:
                        new_parent_node.children.insert(int(index), item)
                    except (ValueError, TypeError):
                        new_parent_node.children.append(item)

        self._propagate_up_at(old_parent)
        self._propagate_up_at(new_parent)
        self._execute_batch_updates()
        self._queue_scrollbar_update()

    def detach(self, *items):
        existing = self._normalize_items_argument(items)
        if not existing:
            return
        parents = set()
        for item in existing:
            node = self._nodes.get(item)
            parent = node.parent if node is not None else (self._tree.parent(item) or "")
            parents.add(parent or "")
            if node is not None:
                parent_node = self._nodes.get(parent)
                if parent_node is not None:
                    try:
                        parent_node.children.remove(item)
                    except ValueError:
                        pass
                node.parent = ""  # 标记游离
        self._tree.detach(*existing)
        for parent in parents:
            self._propagate_up_at(parent)
        self._execute_batch_updates()
        self._queue_scrollbar_update()

    # ------------------------------------------------------------------
    # 透传 / 兼容方法
    # ------------------------------------------------------------------
    def get_children(self, item=None):
        if item is None:
            item = ""
        node = self._nodes.get(item or "")
        if node is not None:
            return tuple(node.children)
        return self._tree.get_children(item)

    def parent(self, item):
        node = self._nodes.get(item)
        if node is not None:
            return node.parent or ""
        return self._tree.parent(item)

    def exists(self, item):
        return self._tree.exists(item)

    def selection(self):
        return self._tree.selection()

    def selection_set(self, items):
        return self._tree.selection_set(items)

    def selection_add(self, items):
        return self._tree.selection_add(items)

    def selection_remove(self, items):
        return self._tree.selection_remove(items)

    def focus(self, item=None):
        if item is None:
            return self._tree.focus()
        self._tree.focus(item)

    def heading(self, column, option=None, **kwargs):
        if option is not None and not kwargs:
            return self._tree.heading(column, option)
        return self._tree.heading(column, **kwargs)

    def column(self, column, option=None, **kwargs):
        if option is not None and not kwargs:
            return self._tree.column(column, option)
        return self._tree.column(column, **kwargs)

    def see(self, item):
        self._tree.see(item)

    def expand_all(self, item=""):
        node = self._nodes.get(item or "")
        if node is None:
            for child in self._tree.get_children(item or ""):
                self._tree.item(child, open=True)
                self.expand_all(child)
            return
        for child in node.children:
            try:
                self._tree.item(child, open=True)
            except tk.TclError:
                pass
            self.expand_all(child)
        self._queue_scrollbar_update()

    def collapse_all(self, item=""):
        node = self._nodes.get(item or "")
        if node is None:
            for child in self._tree.get_children(item or ""):
                self.collapse_all(child)
                self._tree.item(child, open=False)
            return
        for child in node.children:
            self.collapse_all(child)
            try:
                self._tree.item(child, open=False)
            except tk.TclError:
                pass
        self._queue_scrollbar_update()

    # ------------------------------------------------------------------
    # 兼容旧 API：refresh_hierarchy / refresh_check_states
    # ------------------------------------------------------------------
    def refresh_hierarchy(self):
        """从底层 Treeview 重建 _nodes（兜底，正常使用不需要调用）。"""
        # 保留根
        self._nodes = {"": _TreeNode(parent=None, is_folder=True, original_text="", state=self.STATE_UNCHECKED)}

        def _walk(parent_iid):
            for child in self._tree.get_children(parent_iid):
                raw_text = self._tree.item(child, "text") or ""
                for state in (self.STATE_UNCHECKED, self.STATE_PARTIAL, self.STATE_CHECKED):
                    prefix = self._checkbox_prefix(state)
                    if raw_text.startswith(prefix):
                        raw_text = raw_text[len(prefix):]
                        break
                self._nodes[child] = _TreeNode(parent=parent_iid or "", original_text=raw_text)
                self._nodes[parent_iid or ""].children.append(child)
                _walk(child)

        _walk("")
        self.refresh_check_states()

    def refresh_check_states(self):
        """重新按子节点状态计算所有父节点状态。"""
        self._reconcile_states_after_bulk()
        self._execute_batch_updates()

    # ------------------------------------------------------------------
    # 显示/隐藏复选框
    # ------------------------------------------------------------------
    def set_checkboxes_visible(self, visible: bool):
        """运行时切换复选框的显示与隐藏。"""
        visible = bool(visible)
        if visible == self._show_checkboxes:
            return
        self._show_checkboxes = visible
        self._refresh_all_texts()

    def get_checkboxes_visible(self) -> bool:
        return self._show_checkboxes

    # ------------------------------------------------------------------
    # tag 辅助
    # ------------------------------------------------------------------
    def get_item_tag(self, item):
        node = self._nodes.get(item)
        return node.tag if node is not None else None

    def set_item_tag(self, item, tag):
        node = self._nodes.get(item)
        if node is not None:
            node.tag = tag

    # ------------------------------------------------------------------
    # 键盘 / 点击交互
    # ------------------------------------------------------------------
    def _on_space(self, event=None):
        item = self._tree.focus() or self._tree.identify_row(0)
        if item:
            self.toggle_check(item)
            return "break"
        return None

    def _checkbox_hit_test(self, item, x):
        bbox = self._tree.bbox(item, self._checkbox_column)
        if not bbox:
            return False
        font_name = "TkDefaultFont"
        try:
            configured_font = self._tree.cget("font")
            if configured_font:
                font_name = configured_font
            font = tkfont.nametofont(font_name)
        except Exception:
            font = tkfont.Font(font=font_name)
        click_width = max(
            font.measure(self._checkbox_prefix(state))
            for state in (self.STATE_UNCHECKED, self.STATE_PARTIAL, self.STATE_CHECKED)
        )
        return bbox[0] <= x <= bbox[0] + click_width + 8

    def _is_indicator_click(self, x, y):
        """判断是否点击在展开/折叠三角上。"""
        try:
            elem = self._tree.identify_element(x, y)
        except tk.TclError:
            elem = ""
        if elem and "indicator" in elem.lower():
            return True
        # ttk 在某些主题下 element 名称不同，再用 region 兜底
        try:
            region = self._tree.identify_region(x, y)
        except tk.TclError:
            region = ""
        if region == "tree" and elem == "":
            # 进一步用列首/缩进区域判断
            return False
        return False

    def _should_toggle_for_click(self, item, column, region, x, y):
        if not item:
            return False
        # 永远不拦截三角的点击 → 让原生展开/折叠生效
        if self._is_indicator_click(x, y):
            return False
        # 复选框被隐藏时，不切换
        if not self._show_checkboxes:
            return False
        if self._clickable_region == "row":
            return region in ("tree", "cell")
        if column != self._checkbox_column:
            return False
        if self._clickable_region == "checkbox":
            return self._checkbox_hit_test(item, x)
        return region in ("tree", "cell")

    def _on_tree_click(self, event):
        item = self._tree.identify_row(event.y)
        column = self._tree.identify_column(event.x)
        region = self._tree.identify("region", event.x, event.y)

        if not self._should_toggle_for_click(item, column, region, event.x, event.y):
            # 不切换勾选时让原生处理（包括展开/折叠三角、选区）
            return None

        self._tree.focus(item)
        try:
            self._tree.selection_set(item)
        except tk.TclError:
            pass
        self.toggle_check(item)
        return "break"


if __name__ == "__main__":
    app = ttk.Window(themename="cosmo")
    app.title("HY127_CheckTreeview 演示")
    app.geometry("760x520")

    tree = HY127_CheckTreeview(app, columns=("value",), bootstyle="primary", height=18)
    tree.pack(fill=BOTH, expand=YES, padx=10, pady=10)
    tree.heading("#0", text="名称")
    tree.heading("value", text="值")
    tree.column("#0", width=360, stretch=True)
    tree.column("value", width=180, anchor=W)

    root_a = tree.insert("", END, text="项目 A", values=("root",), open=True)
    tree.insert(root_a, END, text="子项 A-1", values=("leaf",), checked=True)
    tree.insert(root_a, END, text="子项 A-2", values=("leaf",))
    root_b = tree.insert("", END, text="项目 B", values=("root",), open=True)
    sub = tree.insert(root_b, END, text="分组 B-1", values=("group",), open=True)
    tree.insert(sub, END, text="子项 B-1-1", values=("leaf",))
    tree.insert(sub, END, text="子项 B-1-2", values=("leaf",), checked=True)
    tree.refresh_check_states()

    info = ttk.Label(app, text="点击复选框切换勾选；点击三角可折叠/展开；Space 切换焦点行。", bootstyle="secondary")
    info.pack(fill=X, padx=10, pady=(0, 10))

    app.mainloop()
