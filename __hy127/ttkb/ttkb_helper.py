#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ttkbootstrap 辅助函数库
提供常用的 UI 辅助功能
"""
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import tkinter as tk


def 设置分割窗格初始位置(分割窗格: ttk.Panedwindow, 左侧宽度: int = 200, 延迟毫秒: int = 10):
    """
    设置 PanedWindow 分割窗格的初始位置，避免加载时的闪烁效果
    
    参数:
        分割窗格: ttk.Panedwindow 控件对象
        左侧宽度: 左侧面板的固定宽度（像素），默认为 200
        延迟毫秒: 延迟执行的毫秒数，默认为 10（确保窗口已完全显示）
    
    使用示例:
        # 在 _on_ui_loaded 方法中调用
        def _on_ui_loaded(self):
            super()._on_ui_loaded()
            设置分割窗格初始位置(self.spl外层分割容器, 150)
    
    说明:
        - 此函数会设置水平分割窗格的第一个面板为固定宽度
        - 使用 after 方法延迟执行，确保窗口已完全显示
        - 适用于所有水平方向的 PanedWindow 控件
    """
    def 设置位置():
        try:
            获取宽度 = 分割窗格.winfo_width()
            if 获取宽度 > 1:  # 确保窗口已显示
                # 设置 sash 位置（第一个分割线）
                # 使用 sashpos 方法设置位置
                分割窗格.sashpos(0, 左侧宽度)
        except Exception as e:
            print(f"设置分割窗格位置失败: {e}")
    
    # 延迟执行，确保窗口已完全显示
    分割窗格.after(延迟毫秒, 设置位置)


def 设置多个分割窗格初始位置(窗体对象, 分割窗格配置列表):
    """
    批量设置多个 PanedWindow 分割窗格的初始位置
    
    参数:
        窗体对象: 窗体对象（通常是 self）
        分割窗格配置列表: 配置列表，每个元素是字典格式
            [
                {"分割窗格": self.spl外层分割容器, "左侧宽度": 150},
                {"分割窗格": self.spl内层分割容器, "左侧宽度": 100},
            ]
    
    使用示例:
        def _on_ui_loaded(self):
            super()._on_ui_loaded()
            设置多个分割窗格初始位置(self, [
                {"分割窗格": self.spl外层分割容器, "左侧宽度": 150},
                {"分割窗格": self.spl内层分割容器, "左侧宽度": 100},
            ])
    """
    for 配置 in 分割窗格配置列表:
        分割窗格 = 配置.get("分割窗格")
        左侧宽度 = 配置.get("左侧宽度", 200)
        if 分割窗格:
            设置分割窗格初始位置(分割窗格, 左侧宽度)


def 设置垂直分割窗格初始位置(分割窗格: ttk.Panedwindow, 上方高度: int = 200, 延迟毫秒: int = 10):
    """
    设置垂直方向 PanedWindow 分割窗格的初始位置
    
    参数:
        分割窗格: ttk.Panedwindow 控件对象
        上方高度: 上方面板的固定高度（像素），默认为 200
        延迟毫秒: 延迟执行的毫秒数，默认为 10
    
    使用示例:
        def _on_ui_loaded(self):
            super()._on_ui_loaded()
            设置垂直分割窗格初始位置(self.spl垂直分割, 300)
    """
    def 设置位置():
        try:
            获取高度 = 分割窗格.winfo_height()
            if 获取高度 > 1:  # 确保窗口已显示
                # 设置 sash 位置（第一个分割线）
                分割窗格.sashpos(0, 上方高度)
        except Exception as e:
            print(f"设置垂直分割窗格位置失败: {e}")
    
    # 延迟执行，确保窗口已完全显示
    分割窗格.after(延迟毫秒, 设置位置)


def 禁用分割窗格拖动(分割窗格: ttk.Panedwindow):
    """
    禁用 PanedWindow 的拖动功能，固定分割位置
    
    参数:
        分割窗格: ttk.Panedwindow 控件对象
    
    使用示例:
        def _on_ui_loaded(self):
            super()._on_ui_loaded()
            设置分割窗格初始位置(self.spl外层分割容器, 150)
            禁用分割窗格拖动(self.spl外层分割容器)
    """
    try:
        # 禁用 sash 的拖动
        分割窗格.sash_place(0, 分割窗格.sash_coord(0)[0], 0)
        # 通过绑定事件来阻止拖动
        def 阻止拖动(event):
            return "break"
        
        分割窗格.bind("<Button-1>", 阻止拖动)
        分割窗格.bind("<B1-Motion>", 阻止拖动)
    except Exception as e:
        print(f"禁用分割窗格拖动失败: {e}")
