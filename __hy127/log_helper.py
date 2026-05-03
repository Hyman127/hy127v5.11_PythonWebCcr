
"""
Python表格打印函数 
作者: 郑广学 hy127.cn 2025.10.15
"""

import sys
import unicodedata
import os
import time
import logging
try:
    from . import pandas_helper as pdx
except ImportError :
    try:
        import pandas_helper as pdx
    except ImportError:
        pdx = None

def logtable(data,表头行数=1,
             显示列数=15,
             style='simple',
             index_label="行",
             显示行数=20,
             properties=None,):
    """
    打印格式化的表格，类似Node.js的console.table()
    
    参数:
        data: 要打印的数据
        properties: 要显示的列名列表，None表示显示所有列
        index_label: 索引列的标题，默认为"(index)"
        style: 边框样式 'auto', 'unicode', 'ascii', 'simple', 'debug'
        colors: 是否使用颜色
        header_row: 针对二维列表，指定表头行数（前N行作为表头区域），0表示无表头
        显示列数: 最大显示列数，0表示显示全部
    """
    
    # 自动检测样式
    实际显示列数 = 10000 if 显示列数 == 0 else 显示列数
    if style == 'auto':
        style = 'simple'
     
    colors=False
    # 处理不同数据类型
    table_data = []
    headers = []
    indices = []
    header_rows = []  # 存储多行表头数据
    
    try:
        import pandas as pd
        if isinstance(data, pd.DataFrame)  :
            if pdx is None:
                raise ImportError("logtable 处理 DataFrame 需要 pandas_helper")
            # 处理pandas DataFrame 转为二维数组 带列标题
            #data= [data.columns.tolist()] + data.values.tolist()
            try:
                表头行数=data.columns.nlevels #表头行数
            except Exception:
                pass
            data=pdx.df_to_list(data)
    except ImportError:
        pass
    
    # 1. 处理字典列表 [{}, {}, ...]
    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
        indices = list(range(len(data)))
        
        all_keys = set()
        for item in data:
            all_keys.update(item.keys())
        
        if properties:
            headers = [h for h in properties if h in all_keys]
        else:
            headers = sorted(all_keys)
        
        for item in data:
            row = [_format_value(item.get(h, '')) for h in headers]
            table_data.append(row)
    
    # 2. 处理嵌套字典
    elif isinstance(data, dict) and len(data) > 0 and isinstance(next(iter(data.values())), dict):
        indices = list(data.keys())
        
        all_keys = set()
        for item in data.values():
            all_keys.update(item.keys())
        
        if properties:
            headers = [h for h in properties if h in all_keys]
        else:
            headers = sorted(all_keys)
        
        for key in indices:
            item = data[key]
            row = [_format_value(item.get(h, '')) for h in headers]
            table_data.append(row)
    
    # 3. 处理简单字典
    elif isinstance(data, dict):
        indices = list(data.keys())
        headers = ['Values']
        table_data = [[_format_value(v)] for v in data.values()]
    
    # 4. 处理二维列表
    elif isinstance(data, list) and len(data) > 0 and isinstance(data[0], (list, tuple)):
        max_cols = max(len(row) for row in data)
        是否截断 = max_cols > 实际显示列数
        实际列数 = min(max_cols, 实际显示列数)
        
        # 根据header_row参数决定如何处理表头
        if 表头行数 > 0 and len(data) >= 表头行数:
            # 前N行作为表头区域
            header_rows = []
            for i in range(表头行数):
                header_row_data = [str(item) for item in data[i][:实际列数]]
                # 补齐空列
                header_row_data.extend([''] * (实际列数 - len(header_row_data)))
                # 如果截断，添加 ...
                if 是否截断:
                    header_row_data.append('...')
                header_rows.append(header_row_data)
            
            # 使用最后一行表头作为列标题（用于宽度计算）
            headers = header_rows[-1]
            
            # 数据从表头后开始
            table_rows = data[表头行数:]
            indices = list(range(len(table_rows)))
        else:
            # header_row=0 或数据行数不足，使用索引作为表头
            headers = [str(i) for i in range(实际列数)]
            if 是否截断:
                headers.append('...')
            table_rows = data
            indices = list(range(len(table_rows)))
        
        table_data = []
        for row in table_rows:
            # 截取前N列
            formatted_row = [_format_value(v) for v in row[:实际列数]]
            # 补齐空列
            formatted_row.extend([''] * (实际列数 - len(formatted_row)))
            # 如果截断，添加 ... 
            if 是否截断:
                formatted_row.append('...')
            table_data.append(formatted_row)
    
    # 5. 处理简单列表
    elif isinstance(data, list):
        indices = list(range(len(data)))
        headers = ['Values']
        table_data = [[_format_value(v)] for v in data]
    
    else:
        print("Unsupported data type")
        return
    
    if not table_data and not header_rows:
        print("Empty table")
        return
    table_data=table_data[0:显示行数]
    # 根据样式选择打印方法
    _print_table_normal_mode(indices, headers, table_data, index_label, style, colors, header_rows)

def _print_table_normal_mode(indices, headers, table_data, index_label, style, colors, header_rows=None):
    """正常模式：使用边框字符"""
    index_width = max(_display_width(str(idx)) for idx in indices) if indices else 0
    index_width = max(index_width, _display_width(index_label))
    
    # 计算列宽
    col_widths = []
    for i in range(len(headers)):
        max_width = _display_width(str(headers[i]))
        # 检查所有表头行
        if header_rows:
            for header_row in header_rows:
                if i < len(header_row):
                    max_width = max(max_width, _display_width(str(header_row[i])))
        # 检查数据行
        for row in table_data:
            if i < len(row):
                max_width = max(max_width, _display_width(str(row[i])))
        col_widths.append(max_width)
    
    borders = _get_border_chars(style)
    use_colors = colors and _supports_color()
    
    # 打印顶部边框
    _print_border(index_width, col_widths, borders, 'top')
    
    # 打印多行表头
    if header_rows:
        for row_idx, header_row in enumerate(header_rows):
            # 第一行显示索引标签，其他行为空
            if row_idx == 0:
                row_values = [index_label] + header_row
            else:
                row_values = [''] + header_row
            _print_row(row_values, [index_width] + col_widths, 
                      borders, is_header=True, use_colors=use_colors)
    else:
        # 单行表头
        _print_row([index_label] + headers, [index_width] + col_widths, 
                  borders, is_header=True, use_colors=use_colors)
    
    # 打印表头和数据之间的分隔线
    _print_border(index_width, col_widths, borders, 'middle')
    
    # 打印数据行
    for idx, row in zip(indices, table_data):
        _print_row([str(idx)] + row, [index_width] + col_widths, 
                   borders, use_colors=use_colors)
    
    # 打印底部边框
    _print_border(index_width, col_widths, borders, 'bottom')


def _display_width(text):
    """计算字符串的显示宽度"""
    width = 0
    for char in str(text):
        if unicodedata.east_asian_width(char) in ('F', 'W'):
            width += 2
        else:
            width += 1
    return width


def _pad_string(text, width, align='left'):
    """填充字符串到指定显示宽度"""
    text = str(text)
    current_width = _display_width(text)
    padding_needed = width - current_width
    
    if padding_needed <= 0:
        return text
    
    if align == 'right':
        return ' ' * padding_needed + text
    else:
        return text + ' ' * padding_needed


def _get_border_chars(style):
    """获取不同样式的边框字符"""
    styles = {
        'unicode': {
            'top': ('┌', '┬', '┐', '─'),
            'middle': ('├', '┼', '┤', '─'),
            'bottom': ('└', '┴', '┘', '─'),
            'vertical': '│'
        },
        'ascii': {
            'top': ('+', '+', '+', '-'),
            'middle': ('+', '+', '+', '-'),
            'bottom': ('+', '+', '+', '-'),
            'vertical': '|'
        },
        'simple': {
            'top': ('+', '+', '+', '-'),
            'middle': ('+', '+', '+', '-'),
            'bottom': ('+', '+', '+', '-'),
            'vertical': '|'
        }
    }
    return styles.get(style, styles['simple'])


def _supports_color():
    """检测是否支持ANSI颜色"""
    if 'debugpy' in sys.modules:
        return False
    if hasattr(sys.stdout, 'isatty') and sys.stdout.isatty():
        return True
    return False


def _format_value(value):
    """格式化单元格的值"""
    if value is None:
        return ''
    elif isinstance(value, bool):
        return str(value).lower()
    elif isinstance(value, (int, float)):
        return str(value)
    else:
        return str(value)


def _print_border(index_width, col_widths, borders, border_type):
    """打印边框线"""
    border_set = borders[border_type]
    left, middle, right, horizontal = border_set
    
    parts = [horizontal * (index_width + 2)]
    for width in col_widths:
        parts.append(horizontal * (width + 2))
    
    print(left + middle.join(parts) + right)


def _print_row(values, widths, borders, is_header=False, use_colors=False):
    """打印一行数据"""
    vertical = borders['vertical']
    
    BLUE = '\033[94m' if use_colors else ''
    CYAN = '\033[96m' if use_colors else ''
    RESET = '\033[0m' if use_colors else ''
    
    parts = []
    for i, (value, width) in enumerate(zip(values, widths)):
        value_str = str(value)
        
        # ... 列左对齐
        if value_str == '...':
            formatted = _pad_string(value_str, width, align='left')
        else:
            is_number = (not is_header and value_str and 
                        value_str.replace('.', '').replace('-', '').replace(' ', '').isdigit())
            
            if is_number:
                formatted = _pad_string(value_str, width, align='right')
            else:
                formatted = _pad_string(value_str, width, align='left')
        
        if use_colors:
            if i == 0:
                formatted = f'{CYAN}{formatted}{RESET}'
            elif is_header:
                formatted = f'{BLUE}{formatted}{RESET}'
        
        parts.append(f' {formatted} ')
    
    print(vertical + vertical.join(parts) + vertical)


def logjson(数据, 换行=True, 美化=True, 直接输出=False):
    """
    按JSON格式输出数据
    
    参数:
        数据: 要输出的JSON数据
        换行: 是否按行换行显示（针对二维数组）
        美化: 是否美化JSON格式
        直接输出: 是否直接输出JSON字符串而不使用print
    """
    import json
    try:
        import pandas as pd
        if isinstance(数据, pd.DataFrame)  :
            # 处理pandas DataFrame 转为二维数组 带列标题
            #data= [data.columns.tolist()] + data.values.tolist()
            数据=pdx.df_to_list(数据)
    except ImportError:
        pass
    # 如果是二维数组且需要换行处理
    if 换行 and isinstance(数据, (list, tuple)) and len(数据) > 0 and isinstance(数据[0], (list, dict)):
        结果 = []
        for 行 in 数据:
            # 换行模式下不进行JSON格式化，直接转为字符串
            结果.append(str(行))
        
        输出内容 = '\n'.join(结果)
        if 直接输出:
            return 输出内容
        else:
            print(输出内容)
            return None
    else:
        # 非换行模式：统一使用json.dumps处理
        if 美化:
            输出内容 = json.dumps(数据, ensure_ascii=False, indent=2)
        else:
            输出内容 = json.dumps(数据, ensure_ascii=False)
        
        if 直接输出:
            return 输出内容
        else:
            print(输出内容)
            return None
class Logger880:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        # 默认配置
        self._启用 = True
        self._同步到终端 = True
        self._日志文件 = None
        self._文件大小 = 100 * 1024  # 默认 100KB

        # logging 组件
        self._logger = logging.getLogger("Logger880")
        self._logger.setLevel(logging.DEBUG)
        if self._logger.hasHandlers():
            self._logger.handlers.clear()

        self._console_handler = None
        self._file_handler = None
        self._active_timer = None  # 当前活动计时器
        self._timer_start_time = None  # 计时器开始时间
        self._last_log_time = None  # 上次记录时间

        # 应用初始配置
        self._应用控制台输出()
        # 文件 handler 将在首次设置日志文件时添加

    def 配置日志(self, 启用=None, 输出到终端=None, 日志文件路径=None, 日志保留大小=100*1024,自动创建文件=True):
        """
        统一配置日志行为（中文接口）
        
        参数:
            启用 (bool): 是否启用日志记录，默认保持当前值
            输出到终端 (bool): 是否将日志输出到控制台，默认保持当前值
            日志文件路径 (str): 日志文件路径，若改变则重新设置 handler
            日志保留大小 (int): 单个日志文件最大字节数，默认 100KB，超限则清空重写
        """
        if 启用 is not None:
            self._启用 = bool(启用)
        if 输出到终端 is not None:
            self._同步到终端 = bool(输出到终端)
            self._应用控制台输出()
        if 日志保留大小 is not None:
            self._文件大小 = int(日志保留大小)

        if 自动创建文件 and 日志文件路径 is not None and not os.path.exists(日志文件路径):
            try:
                日志目录 = os.path.dirname(日志文件路径)
                if 日志目录:
                    os.makedirs(日志目录, exist_ok=True)
                with open(日志文件路径, 'w', encoding='utf-8') as f:
                    f.write("创建日志文件")
            except Exception:
                pass    
        if not 日志文件路径 is  None and not 自动创建文件:   
            日志文件路径 = None   
        # 处理日志文件变更
        if 日志文件路径 is not None and 日志文件路径 != self._日志文件:
            # 移除旧 handler
            if self._file_handler:
                self._logger.removeHandler(self._file_handler)
                self._file_handler.close()
                self._file_handler = None

            self._日志文件 = 日志文件路径
            
            # 检查是否需要清空
            if os.path.exists(日志文件路径) and os.path.getsize(日志文件路径) >= self._文件大小:
                open(日志文件路径, 'w', encoding='utf-8').close()

            # 添加新 handler
            self._file_handler = logging.FileHandler(日志文件路径, mode='a', encoding='utf-8')
            formatter = logging.Formatter(
                fmt='%(asctime)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            self._file_handler.setFormatter(formatter)
            self._logger.addHandler(self._file_handler)

       

    def _应用控制台输出(self):
        """根据 _同步到终端 状态动态管理控制台输出"""
        if self._同步到终端:
            if self._console_handler is None:
                self._console_handler = logging.StreamHandler(sys.stdout)
                formatter = logging.Formatter(
                    fmt='%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S'
                )
                self._console_handler.setFormatter(formatter)
                self._logger.addHandler(self._console_handler)
        else:
            if self._console_handler is not None:
                self._logger.removeHandler(self._console_handler)
                self._console_handler.close()
                self._console_handler = None

    def _log(self, level, msg):
        if not self._启用:
            return
            
        # 如果有活动计时器，则在消息前添加计时信息
        if  level=="TIME":
            if self._active_timer is not None and self._timer_start_time is not None :
                current_time = time.time()
                total_elapsed = current_time - self._timer_start_time
                
                # 计算与上次记录的间隔时间
                if self._last_log_time is not None:
                    interval = current_time - self._last_log_time
                    msg = f"[计时]间隔:{interval:.3f}s\t总计:{total_elapsed:.3f}s {msg}"
                else:
                    msg = f"[计时]间隔:{total_elapsed:.3f}s\t总计:{total_elapsed:.3f}s  {msg}"
                
                # 更新上次记录时间为当前时间
                self._last_log_time = current_time
                self._logger.info(msg)
                return
            
        if level == "INFO":
            self._logger.info(msg)
        elif level == "WARNING":
            self._logger.warning(msg)
        elif level == "ERROR":
            self._logger.error(msg)
        elif level == "DEBUG":
            self._logger.debug(msg)

    def time(self, msg):
        self._log("TIME", msg)

    def info(self, msg):
        self._log("INFO", msg)

    def warning(self, msg):
        self._log("WARNING", msg)

    def error(self, msg):
        self._log("ERROR", msg)

    def debug(self, msg):
        self._log("DEBUG", msg)

    def print(self, msg):
        """兼容print用法（不推荐）"""
        print(msg)

    # ========== 计时器功能（修改后，按顺序计时）==========
    def time_start(self, info=""):
        """
        开始计时器，此后所有loginfo都自带计时信息
        """
        self._timer_start_time = time.time()
        self._last_log_time = self._timer_start_time  # 初始化上次记录时间为开始时间
        
        self.info(f"[计时开始]:{info}")
        self._active_timer = True
        return True  # 表示计时器已启动

    def time_stop(self, info=""):
        """
        停止计时器，恢复正常日志输出
        """
        if self._active_timer is not None and self._timer_start_time is not None:
            self.info(f"{info}")
            self.time("计时结束")
            elapsed = time.time() - self._timer_start_time
            self._active_timer = None
            self._timer_start_time = None
            self._last_log_time = None  # 清理上次记录时间
            
            self.info(f"[计时结束]:总计:{elapsed:.3f}秒 {info}")
        else:
            self.info(f"[计时结束] {info}")

# 全局单例
log = Logger880()


def 测试表格输出():
    data ='''
+----------+------------+----------------+---------+----------+------+
|产品名称   | 产品名称_count | 单价           | 销售数量 | 序号     |
+----------+------------+----------------+---------+----------+------+
|平板电脑   |          6 |        2664.17 |      96 |      117 |
|手机|          7 |        2683.29 |     301 |        1 |
|打印机|          2 |         1934.5 |      18 |      113 |
'''
    print(data)


# ==================== 使用示例 ====================
if __name__ == "__main__":
    print("\n=== 测试多行表头功能 ===")
    
    # 测试数据：前3行是表头
    data_multi_header = [
        ['分类', '分类', '产品信息', '产品信息', '产品信息', '销售数据', '销售数据'],
        ['大类', '小类', '名称', '型号', '价格', '数量', '总额'],
        ['电子', '手机', 'iPhone', '14 Pro', 7999, 50, 399950],
        ['电子', '电脑', 'MacBook', 'Air M2', 8999, 30, 269970],
        ['家电', '冰箱', '海尔', 'BCD-470', 3999, 20, 79980],
    ]
    
    print("\nheader_row=1 (只有第1行是表头):")
    logtable(data_multi_header, 表头行数=1, style='debug')
    
    print("\nheader_row=2 (前2行是表头):")
    logtable(data_multi_header, 表头行数=2, style='debug')
    
    print("\nheader_row=3 (前3行是表头) - 推荐:")
    logtable(data_multi_header, 表头行数=3, style='debug')
    
    print("\nheader_row=0 (无表头，全部是数据):")
    logtable(data_multi_header, 表头行数=0, style='debug')
    
    print("\n=== Unicode样式 + 多行表头 ===")
    logtable(data_multi_header, 表头行数=3, style='unicode')
    
    print("\n=== 多行表头 + 列截断测试 ===")
    data_multi_header_long = [
        ['列1', '列2', '列3', '列4', '列5', '列6', '列7', '列8', '列9', '列10'],
        ['A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7', 'A8', 'A9', 'A10'],
        ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B9', 'B10'],
        ['数据1', '数据2', '数据3', '数据4', '数据5', '数据6', '数据7', '数据8', '数据9', '数据10'],
    ]
    
    print("\n显示前5列（2行表头）:")
    logtable(data_multi_header_long, 表头行数=2, 显示列数=5, style='debug')
    
    print("\n=== 原有功能测试 ===")
    data1 = [
        {'id': 1, 'name': '产品A', 'price': 99.99, 'available': True},
        {'id': 2, 'name': 'Product B', 'price': 149.50, 'available': False},
        {'id': 3, 'name': '产品C', 'price': 79.00, 'available': True}
    ]
    logtable(data1, style='debug')

    log.配置日志(
        启用=True,
        输出到终端=True,
        日志文件路径="myapp.log",
        日志保留大小=100 * 1024  # 200KB
    )
    import time

    
    log.info("这条日志会输出到控制台并写入文件")
    timer_id = log.time_start("处理数据")
    log.info('错误')
    import sys
    time.sleep(1.24)
    # ... 业务逻辑 ...
    log.info("计时..")
    log.time("处理数据..")
    time.sleep(1.12)
    log.time('错误')
    log.info("操作..")
    time.sleep(1.12)
    log.time_stop("处理数据完毕")
