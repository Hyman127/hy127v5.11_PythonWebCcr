
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.font as tkfont
import ttkbootstrap as ttkb
from ttkbootstrap.constants import *
from PIL import Image, ImageDraw, ImageTk
import hashlib
import os
import logging

logger = logging.getLogger(__name__)

class HY127_Button(ttkb.Frame):
    """
    高级圆角按钮组件 V13 (完全兼容 ttkbootstrap 样式系统)
    
    新增特性：
    - 完全支持 ttk.Style().configure() 和 ttk.Style().map() 样式配置
    - hover/pressed 颜色可通过 style.map() 配置，与 ttkbootstrap 按钮一致
    - 支持 Shape 参数，可选择 "round" (圆角) 或 "circle" (圆形)
    - 完全兼容 ttkbootstrap 主题系统
    
    样式配置示例：
        style = ttk.Style()
        style.configure("MyButton.primary.TButton", 
                       background="#9B59B6",      # 默认背景色
                       foreground="white",        # 文字颜色
                       font=("微软雅黑", 11),
                       borderwidth=2,
                       bordercolor="#7D3C98")     # 边框颜色
        
        style.map("MyButton.primary.TButton",
                 background=[("active", "#8E44AD"),     # 鼠标滑过颜色
                           ("pressed", "#7D3C98"),      # 按下颜色
                           ("disabled", "#CCCCCC")],    # 禁用颜色
                 foreground=[("disabled", "#666666")])  # 禁用文字颜色
        
        btn = HY127_Button(parent, text="My Button", style="MyButton.primary.TButton")
    """
    
    # 缓存系统
    _background_cache = {}
    _cache_max_size = 100
    
    # 图片缩放模式
    IMAGE_SCALE_TILE = "tile"
    IMAGE_SCALE_FIT = "fit"
    IMAGE_SCALE_STRETCH = "stretch"
    IMAGE_SCALE_ORIGINAL = "original"
    
    # 形状模式
    SHAPE_ROUND = "round"
    SHAPE_CIRCLE = "circle"

    # 文字位置（相对于按钮，控制图区与文字区的分割方式）
    # CENTER：图占满按钮、文字居中叠加（向后兼容默认行为）
    # TOP / BOTTOM / LEFT / RIGHT：图与文字分占两块互不重叠的区域
    TEXT_POS_CENTER = "center"
    TEXT_POS_TOP    = "top"
    TEXT_POS_BOTTOM = "bottom"
    TEXT_POS_LEFT   = "left"
    TEXT_POS_RIGHT  = "right"
    
    # 默认样式配置
    _DEFAULT_STYLE_CONFIG = {
        "background": None,
        "foreground": None,
        "bordercolor": None,
        "font": ('Microsoft YaHei', 10),
        "borderwidth": 2,
        "relief": "flat",
    }
    
    # 状态映射默认值
    _DEFAULT_STATE_MAP = {
        "hover_background": None,      # 鼠标滑过背景色
        "pressed_background": None,    # 按下背景色
        "disabled_background": None,   # 禁用背景色
        "disabled_foreground": None,   # 禁用文字颜色
    }
    
    def __init__(self, master=None, text="", command=None, bootstyle=PRIMARY,
                 style=None, corner_radius=20, width=None, height=None, font=None,
                 image=None, compound=None, state=NORMAL, 
                 bg_image=None, bg_image_scale=None, bg_image_anchor=CENTER,
                 bg_image_alpha=1.0, border_width=None, use_cache=True,
                 shape=SHAPE_ROUND,
                 text_position="center", text_padding=8,
                 auto_wrap=False,
                 transparent_background=False,
                 **kwargs):
        
        # 初始化标志
        self._initialized = False
        self._canvas = None
        
        # Style 引擎
        try:
            self._style_engine = ttkb.Style.get_instance()
        except Exception:
            self._style_engine = ttk.Style()
        
        # 基本参数
        self._text = text
        self._command = command
        self._bootstyle = bootstyle
        self._style_name = style
        self._corner_radius = corner_radius
        self._shape = shape
        self._req_width = width
        self._req_height = height
        self._image = image
        self._compound = compound
        self._state = state
        self._use_cache = use_cache
        
        # 样式配置（包含静态配置和状态映射）
        self._style_config = self._DEFAULT_STYLE_CONFIG.copy()
        self._state_map = self._DEFAULT_STATE_MAP.copy()
        self._load_style_config()
        
        self._font = font if font is not None else self._style_config.get("font", ('Microsoft YaHei', 10))
        # 透明背景：强制无填充、无边框，专给 HY127_ImageButton 这种"图叠文字、按钮本体不可见"的场景用
        self._transparent_background = bool(transparent_background)
        if self._transparent_background:
            self._border_width = 0
        else:
            self._border_width = max(0, border_width if border_width is not None else self._style_config.get("borderwidth", 2))
        
        # 背景图片参数
        self._bg_image_path = bg_image
        self._bg_image_scale = bg_image_scale if bg_image_scale else self.IMAGE_SCALE_FIT
        self._bg_image_anchor = bg_image_anchor
        self._bg_image_alpha = max(0.0, min(1.0, bg_image_alpha))
        self._bg_image_original = None

        # 文字位置：决定 bg_image 的"图区"与"文字区"如何分割
        # 取值见 TEXT_POS_*。默认 'center' = 旧行为（图占满 + 文字居中叠加），向后兼容。
        _valid_pos = (self.TEXT_POS_CENTER, self.TEXT_POS_TOP, self.TEXT_POS_BOTTOM,
                      self.TEXT_POS_LEFT, self.TEXT_POS_RIGHT)
        self._text_position = text_position if text_position in _valid_pos else self.TEXT_POS_CENTER
        self._text_padding = max(0, int(text_padding))
        self._auto_wrap = bool(auto_wrap)
        
        # 内部状态
        self._hover = False
        self._pressed = False
        self._photo_image = None
        self._pending_redraw = None
        
        # 加载背景图片
        if self._bg_image_path:
            self._load_background_image()
        
        # 调用父类构造函数
        super().__init__(master, **kwargs)
        
        # 初始化画布
        self._canvas = tk.Canvas(
            self,
            highlightthickness=0,
            bd=0,
            bg=self._get_parent_bg()
        )
        self._canvas.pack(fill=BOTH, expand=YES)
        
        self._bind_events()
        self._bind_resize()
        self._bind_theme_change()
        self._update_preferred_size()
        
        # 标记初始化完成
        self._initialized = True
        self._draw_button()
    
    def _load_style_config(self):
        """从 ttk.Style 加载样式配置（包括 configure 和 map）"""
        if not self._style_name:
            return
        
        # 1. 加载静态配置 (style.configure)
        for key in self._style_config.keys():
            try:
                value = self._style_engine.lookup(self._style_name, key)
                if value:
                    self._style_config[key] = value
            except Exception:
                pass
        
        # 特殊处理：当只使用样式名称而没有显式配置时，忽略默认的白色背景
        # 让 _get_color_from_style_name 方法根据样式名称提取正确的颜色
        if ((self._style_config.get("background") == "#ffffff" or 
             self._style_config.get("background") == "white") and 
            not self._has_explicit_style_config()):
            # 重置背景色，让 _get_color_from_style_name 来处理
            self._style_config["background"] = None
        
        # 2. 加载状态映射 (style.map)
        # 读取 background 的状态映射
        try:
            bg_map = self._style_engine.map(self._style_name, "background")
            if bg_map:
                for state_spec, color in self._parse_style_map(bg_map):
                    if "active" in state_spec or "hover" in state_spec:
                        self._state_map["hover_background"] = color
                    elif "pressed" in state_spec:
                        self._state_map["pressed_background"] = color
                    elif "disabled" in state_spec:
                        self._state_map["disabled_background"] = color
        except Exception as e:
            pass
        
        # 读取 foreground 的状态映射
        try:
            fg_map = self._style_engine.map(self._style_name, "foreground")
            if fg_map:
                for state_spec, color in self._parse_style_map(fg_map):
                    if "disabled" in state_spec:
                        self._state_map["disabled_foreground"] = color
        except Exception as e:
            pass
    
    def _parse_style_map(self, style_map):
        """
        解析 style.map() 返回的映射数据
        
        style.map() 返回格式可能是:
        - [('active', '#color'), ('pressed', '#color')] 或
        - [(('active',), '#color'), (('pressed',), '#color')]
        """
        results = []
        if not style_map:
            return results
        
        for item in style_map:
            if len(item) >= 2:
                states = item[0]
                color = item[1]
                
                # 统一转换为字符串列表
                if isinstance(states, str):
                    state_list = [states]
                elif isinstance(states, (tuple, list)):
                    state_list = list(states)
                else:
                    state_list = [str(states)]
                
                results.append((state_list, color))
        
        return results
    
    def _has_custom_style(self):
        """检查是否使用了自定义样式（有显式配置的背景色或样式名称）"""
        return self._style_config.get("background") is not None or self._style_name is not None
    
    def _has_explicit_style_config(self):
        """检查是否有显式的样式配置（通过 style.configure 配置）"""
        if not self._style_name:
            return False
        
        # 检查是否有显式配置的样式
        try:
            # 如果样式有显式配置，lookup 会返回非默认值
            bg_value = self._style_engine.lookup(self._style_name, "background")
            # 如果背景色是白色，说明可能是默认值而不是显式配置
            return bg_value not in ["#ffffff", "white", None]
        except Exception:
            return False
    
    def _get_dynamic_colors(self):
        """获取颜色 - 优先使用自定义样式，否则使用 bootstyle。
        如果 transparent_background=True，把 bg_color/border_color 强制改写为 'transparent'，
        并用主题前景色 colors.fg 兜底文字色（避免 raw 分支默认给白文字 #FFFFFF 在浅色主题里看不见）。
        """
        bg_color, fg_color, border_color = self._get_dynamic_colors_raw()
        if self._transparent_background:
            bg_color = "transparent"
            border_color = "transparent"
            # 文字色优先级：用户显式设的 _style_config["foreground"] > 主题 colors.fg > raw 算的
            explicit_fg = self._style_config.get("foreground")
            if explicit_fg:
                fg_color = explicit_fg
            else:
                try:
                    theme_fg = self._style_engine.colors.fg
                    if theme_fg:
                        fg_color = theme_fg
                except Exception:
                    pass
        return bg_color, fg_color, border_color

    def _get_dynamic_colors_raw(self):
        # 如果有自定义样式配置或样式名称
        if self._has_custom_style():
            # 优先使用显式配置的背景色
            if self._style_config.get("background"):
                bg_color = self._style_config["background"]
                fg_color = self._style_config.get("foreground", "#FFFFFF")
                border_color = self._style_config.get("bordercolor", bg_color)
            else:
                # 如果没有显式配置，尝试从样式名称中提取颜色信息
                bg_color = self._get_color_from_style_name()
                # 对于样式名称，使用默认的前景色和边框色
                fg_color = "#FFFFFF"  # 默认白色文字
                border_color = bg_color  # 边框色与背景色相同
            
            if self._state == DISABLED:
                # 禁用状态
                bg_color = self._state_map.get("disabled_background") or self._darken_color(bg_color, 0.3)
                fg_color = self._state_map.get("disabled_foreground") or "#666666"
                border_color = bg_color
            elif self._pressed:
                # 按下状态 - 优先使用 map 配置的颜色
                bg_color = self._state_map.get("pressed_background") or self._darken_color(bg_color, 0.15)
            elif self._hover:
                # 鼠标滑过状态 - 优先使用 map 配置的颜色（active）
                bg_color = self._state_map.get("hover_background") or self._lighten_color(bg_color, 0.1)
            
            return bg_color, fg_color, border_color
        
        # 使用 bootstyle（ttkbootstrap 主题颜色）
        colors = self._style_engine.colors
        style_parts = self._bootstyle.split('-')
        color_name = style_parts[0] if style_parts else "primary"
        is_outline = "outline" in self._bootstyle
        
        if hasattr(colors, color_name):
            theme_color = getattr(colors, color_name)
        else:
            theme_color = colors.primary
        
        bg_color = theme_color
        fg_color = colors.selectfg
        border_color = theme_color
        
        if self._state == DISABLED:
            bg_color = colors.secondary
            fg_color = colors.border
            border_color = colors.border
        elif is_outline:
            if self._pressed or self._hover:
                bg_color = theme_color
                fg_color = colors.selectfg
            else:
                bg_color = "transparent"
                fg_color = theme_color
                border_color = theme_color
        else:
            if self._pressed:
                bg_color = self._darken_color(theme_color, 0.15)
            elif self._hover:
                bg_color = self._lighten_color(theme_color, 0.1)
        
        return bg_color, fg_color, border_color
    
    def _get_color_from_style_name(self):
        """从样式名称中提取颜色信息"""
        if not self._style_name:
            return None
        
        # 尝试从样式名称中提取颜色部分
        # 例如："Button14.primary.TButton" -> "primary"
        parts = self._style_name.split('.')
        for part in parts:
            if part in ['primary', 'secondary', 'success', 'info', 'warning', 'danger', 'light', 'dark']:
                colors = self._style_engine.colors
                if hasattr(colors, part):
                    return getattr(colors, part)
        
        # 如果没有找到颜色名称，使用默认的 primary 颜色
        return self._style_engine.colors.primary
    
    @classmethod
    def clear_cache(cls):
        cls._background_cache.clear()
    
    @classmethod
    def get_cache_info(cls):
        return {
            "cache_size": len(cls._background_cache),
            "max_size": cls._cache_max_size,
            "keys": list(cls._background_cache.keys())
        }
    
    def _generate_cache_key(self, w, h, bg_color, border_color, state_suffix="", bg_image_rect=None):
        bg_img_hash = ""
        if self._bg_image_path:
            if isinstance(self._bg_image_path, str):
                bg_img_hash = hashlib.md5(self._bg_image_path.encode()).hexdigest()[:8]
            else:
                bg_img_hash = str(id(self._bg_image_path))[:8]
        
        return (w, h, self._corner_radius, self._shape, bg_color, border_color, self._border_width,
                bg_img_hash, self._bg_image_scale if bg_img_hash else "",
                self._bg_image_anchor if bg_img_hash else "",
                self._bg_image_alpha if bg_img_hash else 0, state_suffix,
                bg_image_rect if bg_img_hash else None)
    
    def _get_from_cache_or_create(self, cache_key, creator_func):
        if not self._use_cache:
            return creator_func()
        
        if cache_key in self._background_cache:
            return self._background_cache[cache_key].copy()
        
        new_image = creator_func()
        if len(self._background_cache) >= self._cache_max_size:
            oldest_key = next(iter(self._background_cache))
            del self._background_cache[oldest_key]
        
        self._background_cache[cache_key] = new_image.copy()
        return new_image
    
    def _load_background_image(self):
        try:
            if isinstance(self._bg_image_path, str):
                self._bg_image_original = Image.open(self._bg_image_path).convert("RGBA")
            elif isinstance(self._bg_image_path, Image.Image):
                self._bg_image_original = self._bg_image_path.convert("RGBA")
            else:
                self._bg_image_original = None
        except Exception as e:
            logger.warning("背景图片加载失败: %s", e)
            self._bg_image_original = None
    
    def _process_background_image(self, button_width, button_height):
        if not self._bg_image_original:
            return None
        
        img = self._bg_image_original.copy()
        
        if self._bg_image_scale == self.IMAGE_SCALE_ORIGINAL:
            result = Image.new('RGBA', (button_width, button_height), (0, 0, 0, 0))
            x, y = self._calculate_anchor_position(img.width, img.height, button_width, button_height)
            result.paste(img, (x, y), img)
            img = result
        elif self._bg_image_scale == self.IMAGE_SCALE_STRETCH:
            img = img.resize((button_width, button_height), Image.Resampling.LANCZOS)
        elif self._bg_image_scale == self.IMAGE_SCALE_FIT:
            # 等比例 contain：既能缩小也能放大，让图随按钮尺寸走（与 C# 设计器 HY127_ImageButton 完全一致）。
            # 不能用 PIL.Image.thumbnail，那个只缩不放，会出现"按钮放大了图片不跟着放大"的问题。
            sw, sh = img.width, img.height
            if sw > 0 and sh > 0 and button_width > 0 and button_height > 0:
                ratio = min(button_width / sw, button_height / sh)
                new_w = max(1, int(round(sw * ratio)))
                new_h = max(1, int(round(sh * ratio)))
                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            result = Image.new('RGBA', (button_width, button_height), (0, 0, 0, 0))
            x, y = self._calculate_anchor_position(img.width, img.height, button_width, button_height)
            result.paste(img, (x, y), img)
            img = result
        elif self._bg_image_scale == self.IMAGE_SCALE_TILE:
            result = Image.new('RGBA', (button_width, button_height), (0, 0, 0, 0))
            img_w, img_h = img.size
            for x in range(0, button_width, img_w):
                for y in range(0, button_height, img_h):
                    result.paste(img, (x, y), img)
            img = result
        
        if self._bg_image_alpha < 1.0:
            alpha = img.split()[3]
            alpha = alpha.point(lambda p: int(p * self._bg_image_alpha))
            img.putalpha(alpha)
        
        return img
    
    def _effective_bg_anchor(self):
        """
        算实际生效的锚点：
        - 'center' 布局或没有文字：用 self._bg_image_anchor 不变
        - 用户已显式选了非 CENTER 的锚点：尊重用户
        - 左右布局（text_position=left/right）+ 锚点是 CENTER：自动选"贴近文字带"那一侧（E / W）
        - 上下布局（text_position=top/bottom）+ 锚点是 CENTER：图在图区内居中（左右、上下都居中）
        """
        if self._text_position == self.TEXT_POS_CENTER or not self._text:
            return self._bg_image_anchor
        if self._bg_image_anchor != CENTER:
            return self._bg_image_anchor
        if self._text_position == self.TEXT_POS_LEFT:   return E
        if self._text_position == self.TEXT_POS_RIGHT:  return W
        # TEXT_POS_TOP / TEXT_POS_BOTTOM：图区内居中
        return CENTER

    def _calculate_anchor_position(self, img_w, img_h, container_w, container_h):
        anchor_map = {
            CENTER: (container_w // 2 - img_w // 2, container_h // 2 - img_h // 2),
            N: (container_w // 2 - img_w // 2, 0),
            S: (container_w // 2 - img_w // 2, container_h - img_h),
            E: (container_w - img_w, container_h // 2 - img_h // 2),
            W: (0, container_h // 2 - img_h // 2),
            NE: (container_w - img_w, 0),
            NW: (0, 0),
            SE: (container_w - img_w, container_h - img_h),
            SW: (0, container_h - img_h)
        }
        return anchor_map.get(self._effective_bg_anchor(), anchor_map[CENTER])

    def _calc_text_image_rects(self, button_w, button_h):
        """
        根据 self._text_position 把按钮区域分割成"文字区"和"图区"两个矩形。
        返回 (text_rect, image_rect)，每个 rect 都是 (x, y, w, h)，单位 = 按钮像素。

        - 'center' 或没有文字：两个区域都 = 整个按钮（文字居中叠加在图上，旧行为）
        - 'top'    ：文字区占顶部一条带，图区占其下方
        - 'bottom' ：文字区占底部一条带，图区占其上方
        - 'left'   ：文字区占左边一条带，图区占其右方
        - 'right'  ：文字区占右边一条带，图区占其左方
        """
        full = (0, 0, button_w, button_h)
        pos = self._text_position
        if not self._text or pos == self.TEXT_POS_CENTER:
            return full, full

        pad = self._text_padding
        try:
            f = tkfont.Font(font=self._font)
            text_w_px = f.measure(self._text) if self._text else 0
            text_h_px = f.metrics("linespace") if self._text else 0
        except Exception:
            text_w_px, text_h_px = 0, 14

        if pos == self.TEXT_POS_TOP:
            band_h = min(button_h, text_h_px + 2 * pad)
            text_rect  = (0, 0, button_w, band_h)
            image_rect = (0, band_h, button_w, max(1, button_h - band_h))
        elif pos == self.TEXT_POS_BOTTOM:
            band_h = min(button_h, text_h_px + 2 * pad)
            text_rect  = (0, button_h - band_h, button_w, band_h)
            image_rect = (0, 0, button_w, max(1, button_h - band_h))
        elif pos == self.TEXT_POS_LEFT:
            band_w = min(button_w, text_w_px + 2 * pad)
            text_rect  = (0, 0, band_w, button_h)
            image_rect = (band_w, 0, max(1, button_w - band_w), button_h)
        elif pos == self.TEXT_POS_RIGHT:
            band_w = min(button_w, text_w_px + 2 * pad)
            text_rect  = (button_w - band_w, 0, band_w, button_h)
            image_rect = (0, 0, max(1, button_w - band_w), button_h)
        else:
            return full, full

        return text_rect, image_rect

    def _get_parent_bg(self):
        widget = self.master
        while widget is not None:
            try:
                bg = widget.cget('background')
                if bg and not bg.startswith('System') and bg != '':
                    return bg
            except Exception:
                pass
            try:
                bg = widget.cget('bg')
                if bg and not bg.startswith('System') and bg != '':
                    return bg
            except Exception:
                pass
            widget = getattr(widget, 'master', None)
        try:
            return self._style_engine.lookup("TFrame", "background")
        except Exception:
            pass
        try:
            return self.winfo_toplevel().cget('background')
        except Exception:
            pass
        return "#F0F0F0"
    
    def _darken_color(self, hex_color, factor=0.15):
        try:
            hex_color = hex_color.lstrip('#')
            r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
            r = int(r * (1 - factor))
            g = int(g * (1 - factor))
            b = int(b * (1 - factor))
            return f'#{r:02x}{g:02x}{b:02x}'
        except Exception:
            return hex_color
    
    def _lighten_color(self, hex_color, factor=0.1):
        try:
            hex_color = hex_color.lstrip('#')
            r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
            r = min(255, int(r + (255 - r) * factor))
            g = min(255, int(g + (255 - g) * factor))
            b = min(255, int(b + (255 - b) * factor))
            return f'#{r:02x}{g:02x}{b:02x}'
        except Exception:
            return hex_color
    
    def _update_preferred_size(self):
        if self._req_width is not None and self._req_height is not None:
            self.configure(width=self._req_width, height=self._req_height)
            self.pack_propagate(False)
            self.grid_propagate(False)
        else:
            dummy_font = tkfont.Font(font=self._font)
            text_w = dummy_font.measure(self._text) + 40
            text_h = dummy_font.metrics("linespace") + 20
            
            if self._image:
                text_w += self._image.width() + 10
                text_h = max(text_h, self._image.height() + 20)
            
            w = self._req_width if self._req_width else max(text_w, 80)
            h = self._req_height if self._req_height else max(text_h, 34)
            
            self.configure(width=w, height=h)
            self.pack_propagate(False)
            self.grid_propagate(False)
    
    def _create_background_image(self, img_w, img_h, radius, bg_color, border_color, bg_image_rect=None):
        """
        bg_image_rect: 可选 (x, y, w, h)，限制 bg_image 的绘制区域（与 img_w/img_h 同坐标系，
        即已乘过超采样系数）。None = 占满整个按钮（向后兼容）。
        """
        base_image = Image.new('RGBA', (img_w, img_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(base_image)
        
        if self._shape == self.SHAPE_CIRCLE:
            center_x = img_w // 2
            center_y = img_h // 2
            diameter = min(img_w, img_h)
            half_diameter = diameter // 2
            
            if self._border_width > 0 or bg_color != "transparent":
                if bg_color != "transparent":
                    draw.ellipse(
                        [(center_x - half_diameter, center_y - half_diameter),
                         (center_x + half_diameter, center_y + half_diameter)],
                        fill=bg_color, outline=None
                    )
            
            if self._bg_image_original:
                if bg_image_rect:
                    rx, ry, rw, rh = bg_image_rect
                else:
                    rx, ry, rw, rh = 0, 0, img_w, img_h
                bg_img = self._process_background_image(rw, rh)
                if bg_img:
                    mask = Image.new('L', (img_w, img_h), 0)
                    mask_draw = ImageDraw.Draw(mask)
                    mask_draw.ellipse(
                        [(0, 0), (img_w - 1, img_h - 1)],
                        fill=255
                    )
                    
                    img_layer = Image.new('RGBA', (img_w, img_h), (0, 0, 0, 0))
                    img_layer.paste(bg_img, (rx, ry))
                    
                    if img_layer.mode == 'RGBA':
                        r, g, b, a = img_layer.split()
                        from PIL import ImageChops
                        a = ImageChops.multiply(a, mask)
                        img_layer = Image.merge('RGBA', (r, g, b, a))
                    
                    base_image = Image.alpha_composite(base_image, img_layer)
            
            if self._border_width > 0 and border_color:
                scaled_border_width = int(self._border_width * 4)
                draw.ellipse(
                    [(center_x - half_diameter, center_y - half_diameter),
                     (center_x + half_diameter, center_y + half_diameter)],
                    outline=border_color, width=scaled_border_width
                )
        else:
            if self._border_width > 0 or bg_color != "transparent":
                if bg_color != "transparent":
                    try:
                        draw.rounded_rectangle([(0, 0), (img_w - 1, img_h - 1)], radius=radius, fill=bg_color)
                    except ValueError:
                        draw.rectangle([(0, 0), (img_w - 1, img_h - 1)], fill=bg_color)
            
            if self._bg_image_original:
                if bg_image_rect:
                    rx, ry, rw, rh = bg_image_rect
                else:
                    rx, ry, rw, rh = 0, 0, img_w, img_h
                bg_img = self._process_background_image(rw, rh)
                if bg_img:
                    mask = Image.new('L', (img_w, img_h), 0)
                    mask_draw = ImageDraw.Draw(mask)
                    try:
                        mask_draw.rounded_rectangle([(0, 0), (img_w - 1, img_h - 1)], radius=radius, fill=255)
                    except ValueError:
                        mask_draw.rectangle([(0, 0), (img_w - 1, img_h - 1)], fill=255)
                    
                    img_layer = Image.new('RGBA', (img_w, img_h), (0, 0, 0, 0))
                    img_layer.paste(bg_img, (rx, ry))
                    
                    if img_layer.mode == 'RGBA':
                        r, g, b, a = img_layer.split()
                        from PIL import ImageChops
                        a = ImageChops.multiply(a, mask)
                        img_layer = Image.merge('RGBA', (r, g, b, a))
                    
                    base_image = Image.alpha_composite(base_image, img_layer)
            
            if self._border_width > 0 and border_color:
                draw = ImageDraw.Draw(base_image)
                scaled_border_width = int(self._border_width * 4)
                try:
                    draw.rounded_rectangle([(0, 0), (img_w - 1, img_h - 1)], radius=radius, outline=border_color, width=scaled_border_width)
                except ValueError:
                    draw.rectangle([(0, 0), (img_w - 1, img_h - 1)], outline=border_color, width=scaled_border_width)
        
        return base_image
    
    def _draw_button(self, event=None):
        if not self._initialized or self._canvas is None:
            return
        
        w = self.winfo_width()
        h = self.winfo_height()
        
        if w <= 1 or h <= 1:
            w = self.cget('width')
            h = self.cget('height')
        
        parent_bg = self._get_parent_bg()
        self._canvas.configure(bg=parent_bg)
        
        bg_color, fg_color, border_color = self._get_dynamic_colors()
        
        scale = 4
        img_w, img_h = w * scale, h * scale
        radius = self._corner_radius * scale
        
        state_suffix = ""
        if self._hover:
            state_suffix = "hover"
        if self._pressed:
            state_suffix = "pressed"

        # 算文字区 / 图区（按按钮坐标），再换算到 4x 像素坐标传给 _create_background_image
        text_rect_btn, image_rect_btn = self._calc_text_image_rects(w, h)
        bg_image_rect_4x = None
        if self._bg_image_path and self._text_position != self.TEXT_POS_CENTER and self._text:
            bg_image_rect_4x = (
                image_rect_btn[0] * scale,
                image_rect_btn[1] * scale,
                image_rect_btn[2] * scale,
                image_rect_btn[3] * scale,
            )

        cache_key = self._generate_cache_key(img_w, img_h, bg_color, border_color, state_suffix,
                                             bg_image_rect_4x)
        
        base_image = self._get_from_cache_or_create(
            cache_key,
            lambda: self._create_background_image(img_w, img_h, radius, bg_color, border_color,
                                                  bg_image_rect=bg_image_rect_4x)
        )
        
        base_image = base_image.resize((w, h), Image.Resampling.LANCZOS)
        self._photo_image = ImageTk.PhotoImage(base_image)
        
        self._canvas.delete("all")
        self._canvas.create_image(0, 0, image=self._photo_image, anchor="nw")
        
        center_x, center_y = w / 2, h / 2
        
        if self._image and self._compound == 'left':
            img_x = center_x - 15 - len(self._text) * 4
            txt_x = center_x + 10
            self._canvas.create_image(img_x, center_y, image=self._image)
            self._canvas.create_text(txt_x, center_y, text=self._text, fill=fg_color, font=self._font)
        elif self._image and not self._text:
            self._canvas.create_image(center_x, center_y, image=self._image)
        else:
            # 文字按 text_rect 居中放置（text_position='center' 时 text_rect = 整个按钮）
            tx = text_rect_btn[0] + text_rect_btn[2] / 2
            ty = text_rect_btn[1] + text_rect_btn[3] / 2
            text_kwargs = {}
            if self._auto_wrap and self._text:
                wrap_width = max(20, text_rect_btn[2] - self._text_padding * 2)
                text_kwargs["width"] = wrap_width
                text_kwargs["justify"] = "center"
            self._canvas.create_text(
                tx, ty, text=self._text, fill=fg_color, font=self._font, **text_kwargs
            )
    
    def _bind_events(self):
        if self._state == NORMAL:
            self._canvas.bind('<Enter>', self._on_enter)
            self._canvas.bind('<Leave>', self._on_leave)
            self._canvas.bind('<Button-1>', self._on_press)
            self._canvas.bind('<ButtonRelease-1>', self._on_release)
    
    def _unbind_events(self):
        self._canvas.unbind('<Enter>')
        self._canvas.unbind('<Leave>')
        self._canvas.unbind('<Button-1>')
        self._canvas.unbind('<ButtonRelease-1>')
    
    def _bind_resize(self):
        self.bind('<Configure>', self._draw_button)
    
    def _bind_theme_change(self):
        self.bind("<<ThemeChanged>>", self._on_theme_changed)
    
    def _on_theme_changed(self, event=None):
        """主题改变事件处理 - 自定义样式不受影响"""
        if self._has_custom_style():
            if self._pending_redraw is not None:
                self.after_cancel(self._pending_redraw)
            self._pending_redraw = self.after(10, self._update_canvas_bg_only)
            return
        
        if self._pending_redraw is not None:
            self.after_cancel(self._pending_redraw)
        self.clear_cache()
        self._pending_redraw = self.after(10, self._refresh_after_theme_change)
    
    def _update_canvas_bg_only(self):
        """仅更新画布背景（用于自定义样式按钮）"""
        self._pending_redraw = None
        parent_bg = self._get_parent_bg()
        if self._canvas:
            self._canvas.configure(bg=parent_bg)
    
    def _refresh_after_theme_change(self):
        """主题切换后刷新（用于 bootstyle 按钮）"""
        self._pending_redraw = None
        try:
            self._style_engine = ttkb.Style.get_instance()
        except Exception:
            self._style_engine = ttk.Style()
        self._draw_button()
    
    def _on_enter(self, e):
        self._hover = True
        self._draw_button()
    
    def _on_leave(self, e):
        self._hover = False
        self._pressed = False
        self._draw_button()
    
    def _on_press(self, e):
        self._pressed = True
        self._draw_button()
    
    def _on_release(self, e):
        if self._pressed:
            self._pressed = False
            self._draw_button()
            if self._command:
                self._command()
    
    def configure(self, **kwargs):
        """配置按钮 - 支持所有自定义参数"""
        if not getattr(self, '_initialized', False):
            frame_kwargs = {k: v for k, v in kwargs.items() 
                           if k in ('width', 'height', 'padding', 'relief', 'borderwidth')}
            if frame_kwargs:
                super().configure(**frame_kwargs)
            return
        
        if 'command' in kwargs:
            self._command = kwargs.pop('command')
        
        if 'state' in kwargs:
            new_state = kwargs.pop('state')
            if new_state != self._state:
                self._state = new_state
                if self._state == DISABLED:
                    self._unbind_events()
                else:
                    self._bind_events()
            self._draw_button()

        if 'auto_wrap' in kwargs:
            self._auto_wrap = bool(kwargs.pop('auto_wrap'))
            self._draw_button()
        
        frame_kwargs = {k: v for k, v in kwargs.items() 
                       if k in ('width', 'height', 'padding', 'relief', 'borderwidth')}
        if frame_kwargs:
            super().configure(**frame_kwargs)
        

# ================= 测试演示代码 =================
# 请将此代码与上面的 HY127_Button 类放在同一个文件中
# 或者在导入 HY127_Button 类后运行

import tkinter as tk
import ttkbootstrap as ttkb
from ttkbootstrap.constants import *

if __name__ == "__main__":
    app = ttkb.Window(themename="cosmo")
    app.geometry("1100x850")
    app.title("HY127_Button 背景图片演示")
    
    current_theme = tk.StringVar(value="cosmo")
    
    def toggle_theme():
        """切换主题"""
        themes = ["cosmo", "superhero", "solar", "flatly", "darkly", "cyborg", "vapor"]
        try:
            idx = themes.index(current_theme.get())
            next_theme = themes[(idx + 1) % len(themes)]
        except Exception:
            next_theme = themes[0]
        
        app.style.theme_use(next_theme)
        current_theme.set(next_theme)

    # 顶部控制区
    header = ttkb.Frame(app)
    header.pack(pady=15, fill=X)
    
    ttkb.Label(header, textvariable=current_theme, font=("", 16, "bold")).pack(side=LEFT, padx=20)
    ttkb.Button(header, text="🎨 切换主题", command=toggle_theme, bootstyle="info").pack(side=LEFT, padx=10)
    
    # 创建Notebook（标签页）
    notebook = ttkb.Notebook(app)
    notebook.pack(fill=BOTH, expand=YES, padx=20, pady=10)
    
    # ========== 标签页1: 基础样式对比 ==========
    tab1 = ttkb.Frame(notebook)
    notebook.add(tab1, text="基础样式对比")
    
    # 创建左右分栏布局
    main_paned = ttk.Panedwindow(tab1, orient=HORIZONTAL)
    main_paned.pack(fill=BOTH, expand=YES, padx=10, pady=10)
    
    # 左侧框架
    left_frame = ttkb.Frame(main_paned)
    main_paned.add(left_frame, weight=3)
    
    # 右侧框架
    right_frame = ttkb.Frame(main_paned)
    main_paned.add(right_frame, weight=1)
    
    # ========== 左侧：按钮对比区域 ==========
    
    # 测试区域 1: Primary 对比
    f1 = ttkb.Labelframe(left_frame, text="Primary 实心按钮对比", padding=15)
    f1.pack(pady=5, padx=5, fill=X)
    
    ttkb.Label(f1, text="原生按钮:", font=("", 10)).grid(row=0, column=0, sticky=W, pady=5)
    ttkb.Button(f1, text="ttkbootstrap 原生", bootstyle="primary").grid(row=0, column=1, padx=10, pady=5)
    
    ttkb.Label(f1, text="自定义按钮:", font=("", 10)).grid(row=1, column=0, sticky=W, pady=5)
    HY127_Button(f1, text="自定义圆角按钮", bootstyle="primary", corner_radius=25).grid(row=1, column=1, padx=10, pady=5, sticky=EW)
    
    ttkb.Label(f1, text="圆形按钮:", font=("", 10)).grid(row=2, column=0, sticky=W, pady=5)
    HY127_Button(f1, text="圆形", bootstyle="danger", shape=HY127_Button.SHAPE_CIRCLE, width=60, height=60).grid(row=2, column=1, padx=10, pady=5, sticky=EW)
    
    ttkb.Label(f1, text="纯图标圆形:", font=("", 10)).grid(row=3, column=0, sticky=W, pady=5)
    圆形图标按钮 = HY127_Button(f1, bootstyle="warning", shape=HY127_Button.SHAPE_CIRCLE, width=50, height=50)
    圆形图标按钮.grid(row=3, column=1, padx=10, pady=5)
    

    # 测试区域 2: Outline 对比
    f2 = ttkb.Labelframe(left_frame, text="Success Outline 按钮对比", padding=15)
    f2.pack(pady=5, padx=5, fill=X)
    
    ttkb.Label(f2, text="原生按钮:", font=("", 10)).grid(row=0, column=0, sticky=W, pady=5)
    ttkb.Button(f2, text="原生 Outline", bootstyle="success-outline").grid(row=0, column=1, padx=10, pady=5)
    
    ttkb.Label(f2, text="自定义按钮:", font=("", 10)).grid(row=1, column=0, sticky=W, pady=5)
    HY127_Button(f2, text="自定义 Outline", bootstyle="success-outline", corner_radius=25).grid(row=1, column=1, padx=10, pady=5, sticky=EW)
    
    # 测试区域 3: 多种 bootstyle
    f3 = ttkb.Labelframe(left_frame, text="所有样式对比（切换主题观察）", padding=15)
    f3.pack(pady=5, padx=5, fill=BOTH, expand=YES)
    
    styles = ["primary", "secondary", "success", "info", "warning", "danger"]
    
    for i, style in enumerate(styles):
        row = i
        
        # 原生按钮
        ttkb.Button(f3, text=f"原生 {style.title()}", bootstyle=style, width=15).grid(
            row=row, column=0, padx=5, pady=5
        )
        
        # 自定义实心按钮
        HY127_Button(f3, text=f"自定义 {style.title()}", bootstyle=style,  corner_radius=20, width=150).grid(
            row=row, column=1, padx=5, pady=5, sticky=EW
        )
        
        # 自定义 Outline 按钮
        HY127_Button(f3, text=f"Outline {style.title()}", bootstyle=f"{style}-outline",  corner_radius=20, width=150).grid(
            row=row, column=2, padx=5, pady=5, sticky=EW
        )
    
    f3.columnconfigure(1, weight=1)
    f3.columnconfigure(2, weight=1)
    
    # ========== 右侧：自定义样式区域 ==========
    
    # 定义自定义样式
    app.style.configure("Purple.HY127.TButton", 
                       background="#9B59B6",
                       foreground="white",
                       font=("Arial", 11))
    app.style.map("Purple.HY127.TButton",
                  background=[("active", "#8E44AD"),
                            ("pressed", "#7D3C98")])
    
    app.style.configure("CustomGreen.HY127.TButton", 
                       background="#2ECC71",
                       foreground="white",
                       font=("Arial", 11, "bold"))
    app.style.map("CustomGreen.HY127.TButton",
                  background=[("active", "#27AE60"),
                            ("pressed", "#229954")])
    
    app.style.configure("CustomOrange.HY127.TButton", 
                       background="#E67E22",
                       foreground="white",
                       font=("Arial", 11))
    app.style.map("CustomOrange.HY127.TButton",
                  background=[("active", "#D35400"),
                            ("pressed", "#BA4A00")])
    
    app.style.configure("CustomPink.HY127.TButton", 
                       background="#E91E63",
                       foreground="white",
                       font=("Arial", 11))
    app.style.map("CustomPink.HY127.TButton",
                  background=[("active", "#C2185B"),
                            ("pressed", "#AD1457")])
    
    app.style.configure("CustomBlue.HY127.TButton", 
                       background="#3498DB",
                       foreground="white",
                       font=("Arial", 11))
    app.style.map("CustomBlue.HY127.TButton",
                  background=[("active", "#2980B9"),
                            ("pressed", "#1F618D")])
    
    app.style.configure("CustomRed.HY127.TButton", 
                       background="#E74C3C",
                       foreground="white",
                       font=("Arial", 11))
    app.style.map("CustomRed.HY127.TButton",
                  background=[("active", "#C0392B"),
                            ("pressed", "#922B21")])
    
    # 创建使用自定义样式的按钮
    f4 = ttkb.Labelframe(right_frame, text="使用 style.configure()\n定义自定义样式", padding=15)
    f4.pack(pady=5, padx=5, fill=BOTH, expand=YES)
    
    custom_styles = [
        ("Purple.HY127.TButton", "紫色按钮", 25),
        ("CustomGreen.HY127.TButton", "绿色按钮", 20),
        ("CustomOrange.HY127.TButton", "橙色按钮", 15),
        ("CustomPink.HY127.TButton", "粉色按钮", 30),
        ("CustomBlue.HY127.TButton", "蓝色按钮", 18),
        ("CustomRed.HY127.TButton", "红色按钮", 22)
    ]
    
    for i, (style_name, text, radius) in enumerate(custom_styles):
        ttkb.Label(f4, text=f"{style_name}:", font=("", 8)).grid(row=i*2, column=0, sticky=W, pady=2, padx=5)
        HY127_Button(f4, text=text, style=style_name, corner_radius=radius, width=140).grid(
            row=i*2+1, column=0, padx=5, pady=2, sticky=EW
        )
    
    f4.columnconfigure(0, weight=1)
    
    # ========== 标签页2: 背景图片测试 ==========
    tab2 = ttkb.Frame(notebook)
    notebook.add(tab2, text="🖼️ 背景图片效果")
    
    # 图片路径：演示资源不存在时使用纯色按钮，避免依赖开发机绝对路径。
    demo_image_path = os.path.join(os.path.dirname(__file__), "demo_assets", "头像.png")
    IMAGE_PATH = demo_image_path if os.path.isfile(demo_image_path) else None
    
    # 创建滚动框架
    scroll_frame = ttkb.Frame(tab2)
    scroll_frame.pack(fill=BOTH, expand=YES)
    
    canvas = tk.Canvas(scroll_frame)
    scrollbar = ttkb.Scrollbar(scroll_frame, orient=VERTICAL, command=canvas.yview)
    scrollable_frame = ttkb.Frame(canvas)
    
    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    
    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    
    canvas.pack(side=LEFT, fill=BOTH, expand=YES)
    scrollbar.pack(side=RIGHT, fill=Y)
    
    # === 1. 缩放模式演示 ===
    f_scale = ttkb.Labelframe(scrollable_frame, text="📐 图片缩放模式演示（不透明）", padding=15)
    f_scale.pack(pady=10, padx=20, fill=X)
    
    scale_modes = [
        ("原始尺寸 (original)", HY127_Button.IMAGE_SCALE_ORIGINAL),
        ("等比缩放 (fit)", HY127_Button.IMAGE_SCALE_FIT),
        ("拉伸填充 (stretch)", HY127_Button.IMAGE_SCALE_STRETCH),
        ("平铺模式 (tile)", HY127_Button.IMAGE_SCALE_TILE)
    ]
    
    for i, (mode_name, mode_value) in enumerate(scale_modes):
        ttkb.Label(f_scale, text=mode_name, font=("", 9)).grid(row=i, column=0, sticky=W, pady=5, padx=5)
        HY127_Button(
            f_scale, 
            text=f"背景图片 - {mode_name}",
            bootstyle="primary",
             corner_radius=20,
            width=350,
            height=80,
            bg_image=IMAGE_PATH,
            bg_image_scale=mode_value,
            bg_image_alpha=1.0,  # 不透明
            command=lambda m=mode_name: print(f"✅ 点击了: {m}")
        ).grid(row=i, column=1, padx=10, pady=5, sticky=EW)
    
    f_scale.columnconfigure(1, weight=1)
    
    # === 2. 锚点位置演示 ===
    f_anchor = ttkb.Labelframe(scrollable_frame, text="📍 图片锚点位置演示（原始尺寸模式 - 不透明）", padding=15)
    f_anchor.pack(pady=10, padx=20, fill=X)
    
    anchors = [
        ("左上 (NW)", NW),
        ("正上 (N)", N),
        ("右上 (NE)", NE),
        ("正左 (W)", W),
        ("居中 (CENTER)", CENTER),
        ("正右 (E)", E),
        ("左下 (SW)", SW),
        ("正下 (S)", S),
        ("右下 (SE)", SE)
    ]
    
    for i, (anchor_name, anchor_value) in enumerate(anchors):
        row = i // 3
        col = i % 3
        
        HY127_Button(
            f_anchor,
            text=anchor_name,
            bootstyle="info-outline",
            corner_radius=12,
            width=200,
            height=100,
            bg_image=IMAGE_PATH,
            bg_image_scale=HY127_Button.IMAGE_SCALE_ORIGINAL,
            bg_image_anchor=anchor_value,
            bg_image_alpha=1.0,  # 不透明
            command=lambda a=anchor_name: print(f"✅ 点击了锚点: {a}")
        ).grid(row=row, column=col, padx=5, pady=5, sticky=NSEW)
    
    for i in range(3):
        f_anchor.columnconfigure(i, weight=1)
    
    # === 3. 透明度演示（使用FIT模式）===
    f_alpha = ttkb.Labelframe(scrollable_frame, text="🎨 图片透明度演示（FIT 等比缩放模式）", padding=15)
    f_alpha.pack(pady=10, padx=20, fill=X)
    
    alphas = [0.2, 0.4, 0.6, 0.8, 1.0]
    
    for i, alpha_value in enumerate(alphas):
        ttkb.Label(f_alpha, text=f"透明度 {int(alpha_value*100)}%", font=("", 9)).grid(
            row=i, column=0, sticky=W, pady=5, padx=5
        )
        HY127_Button(
            f_alpha,
            text=f"透明度 {int(alpha_value*100)}% - FIT 等比缩放",
            bootstyle="success",
             corner_radius=20,
            width=350,
            height=60,
            bg_image=IMAGE_PATH,
            bg_image_scale=HY127_Button.IMAGE_SCALE_FIT,  # 改为 FIT 模式
            bg_image_alpha=alpha_value,
            command=lambda a=alpha_value: print(f"✅ 透明度: {a}")
        ).grid(row=i, column=1, padx=10, pady=5, sticky=EW)
    
    f_alpha.columnconfigure(1, weight=1)
    
    # === 4. 不同样式的背景图片按钮（不透明）===
    f_styles = ttkb.Labelframe(scrollable_frame, text="🎭 不同 Bootstyle 的图片按钮（不透明）", padding=15)
    f_styles.pack(pady=10, padx=20, fill=X)
    
    button_styles = [
        ("primary", "主要按钮"),
        ("secondary", "次要按钮"),
        ("success", "成功按钮"),
        ("info", "信息按钮"),
        ("warning", "警告按钮"),
        ("danger", "危险按钮"),
        ("primary-outline", "主要轮廓"),
        ("success-outline", "成功轮廓"),
        ("danger-outline", "危险轮廓")
    ]
    
    for i, (style, label) in enumerate(button_styles):
        row = i // 3
        col = i % 3
        
        HY127_Button(
            f_styles,
            text=label,
            bootstyle=style,
            corner_radius=40,
            width=200,
            height=40,
            border_width=0,
             bg_image_anchor=W,
            bg_image=IMAGE_PATH,
            bg_image_scale=HY127_Button.IMAGE_SCALE_FIT,
            bg_image_alpha=1.0,  # 不透明
            command=lambda s=style: print(f"✅ 点击了样式: {s}")
        ).grid(row=row, column=col, padx=5, pady=5, sticky=NSEW)
    
    for i in range(3):
        f_styles.columnconfigure(i, weight=1)
    
    # === 5. 纯透明按钮（无背景无边框，只显示图片和文字）===
    f_transparent = ttkb.Labelframe(scrollable_frame, text="👻 纯透明按钮（无背景无边框）", padding=15)
    f_transparent.pack(pady=10, padx=20, fill=X)
    
    ttkb.Label(
        f_transparent, 
        text="这类按钮完全透明，只显示背景图片和文字，适合图标按钮或特殊UI需求",
        font=("", 9),
        foreground="gray"
    ).pack(pady=5)
    
    trans_frame = ttkb.Frame(f_transparent)
    trans_frame.pack(pady=10)
    
    # 纯图片按钮 - 不同缩放模式
    HY127_Button(
        trans_frame,
        text="",  # 无文字，只显示图片
        bootstyle="primary-outline",  # 使用outline样式作为基础
        corner_radius=50,  # 圆形按钮
        width=100,
        height=100,
        bg_image=IMAGE_PATH,
        bg_image_scale=HY127_Button.IMAGE_SCALE_STRETCH,
        border_width=0,
        bg_image_alpha=1.0,
        bg_image_anchor=CENTER,
        command=lambda: print("✅ 点击了圆形图片按钮")
    ).pack(side=LEFT, padx=0)
    
    # 图片+文字按钮（拉伸）
    HY127_Button(
        trans_frame,
        text="拉伸背景\n无边框",
        bootstyle="success-outline",
         corner_radius=20,
        width=150,
        height=100,
        font=("Microsoft YaHei", 12, "bold"),
        bg_image=IMAGE_PATH,
        bg_image_scale=HY127_Button.IMAGE_SCALE_STRETCH,
        bg_image_alpha=1.0,
        command=lambda: print("✅ 点击了拉伸背景按钮")
    ).pack(side=LEFT, padx=10)
    
    # 图片+文字按钮（平铺）
    HY127_Button(
        trans_frame,
        text="平铺背景\n透明按钮",
        bootstyle="info-outline",
        corner_radius=20,
        width=150,
        height=100,
        font=("Microsoft YaHei", 11, "bold"),
        bg_image=IMAGE_PATH,
        bg_image_scale=HY127_Button.IMAGE_SCALE_TILE,
        bg_image_alpha=0.7,
        command=lambda: print("✅ 点击了平铺背景按钮")
    ).pack(side=LEFT, padx=10)
    
    # 大尺寸透明按钮
    HY127_Button(
        f_transparent,
        text="🌈 大尺寸透明图片按钮 - FIT模式",
        bootstyle="warning-outline",
        corner_radius=25,
        width=600,
        height=120,
        font=("Microsoft YaHei", 16, "bold"),
        bg_image=IMAGE_PATH,
        bg_image_scale=HY127_Button.IMAGE_SCALE_FIT,
        bg_image_alpha=0.8,
        command=lambda: print("✅ 点击了大尺寸透明按钮")
    ).pack(pady=15, padx=10)
    
    # === 6. 综合效果展示 ===
    f_demo = ttkb.Labelframe(scrollable_frame, text="✨ 综合效果展示", padding=15)
    f_demo.pack(pady=10, padx=20, fill=X)
    
    # 大按钮 - 平铺背景
    HY127_Button(
        f_demo,
        text="🌟 大尺寸平铺背景按钮",
        bootstyle="primary",
        corner_radius=20,
        width=600,
        height=100,
        font=("Microsoft YaHei", 16, "bold"),
        bg_image=IMAGE_PATH,
        bg_image_scale=HY127_Button.IMAGE_SCALE_TILE,
        bg_image_alpha=0.2,
        command=lambda: print("✅ 点击了大按钮")
    ).pack(pady=10, padx=10)
    
    # 小按钮组 - 不同效果（不透明）
    btn_frame = ttkb.Frame(f_demo)
    btn_frame.pack(pady=10)
    
    HY127_Button(
        btn_frame,
        text="拉伸",
        bootstyle="info",
        corner_radius=12,
        width=120,
        height=50,
        bg_image=IMAGE_PATH,
        bg_image_scale=HY127_Button.IMAGE_SCALE_STRETCH,
        bg_image_alpha=1.0
    ).pack(side=LEFT, padx=5)
    
    HY127_Button(
        btn_frame,
        text="等比",
        bootstyle="success",
        corner_radius=12,
        width=120,
        height=50,
        bg_image=IMAGE_PATH,
        bg_image_scale=HY127_Button.IMAGE_SCALE_FIT,
        bg_image_alpha=1.0
    ).pack(side=LEFT, padx=5)
    
    HY127_Button(
        btn_frame,
        text="原图",
        bootstyle="warning",
        corner_radius=12,
        width=120,
        height=50,
        bg_image=IMAGE_PATH,
        bg_image_scale=HY127_Button.IMAGE_SCALE_ORIGINAL,
        bg_image_alpha=1.0
    ).pack(side=LEFT, padx=5)
    
    HY127_Button(
        btn_frame,
        text="平铺",
        bootstyle="danger",
        corner_radius=12,
        width=120,
        height=50,
        bg_image=IMAGE_PATH,
        bg_image_scale=HY127_Button.IMAGE_SCALE_TILE,
        bg_image_alpha=1.0
    ).pack(side=LEFT, padx=5)
    
    # 底部说明
    info_label = ttkb.Label(
        scrollable_frame,
        text="💡 提示：点击上方按钮切换主题，观察背景图片按钮的适配效果！outline样式可实现透明按钮效果。",
        font=("", 10),
        bootstyle="info"
    )
    info_label.pack(pady=20)
    
    # 启动应用
    app.mainloop()


