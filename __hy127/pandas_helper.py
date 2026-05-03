# pandas_helper.py
"""
封装基于pandas增强的数据处理方法
创建者：郑广学 2025-10-27 vbayyds.com
完全启用需要安装包: uv add pandas openpyxl pywin32 psutil pypinyin
"""
import pandas as pd, numpy as np
from typing import List, Dict, Tuple, Callable, Union,Any, Optional
import warnings
# 完整的中文显示优化配置
pd.set_option('display.unicode.east_asian_width', True)  # 东亚字符宽度
# pd.set_option('display.max_columns', None)               # 显示所有列
# pd.set_option('display.max_rows', None)                  # 显示所有行
# pd.set_option('display.width', None)                     # 自动调整显示宽度
# pd.set_option('display.max_colwidth', None)              # 不限制列内容长度


def super_pivot_table(
        数据框: pd.DataFrame,
        行字段: List[str],
        列字段: List[str],
        聚合字典: Dict[str, Union[Tuple[str, Union[str, Callable]], Callable]],
        转列表=False,
        填充值="",
        表头合并=False,
        小数位数=2,
        字段按拼音排序=True,
    ) -> pd.DataFrame:
    """
    郑广学 2025.11.05 hy127.cn
    创建透视表并进行自定义聚合（支持 apply 形式的多列聚合）
    
    参数:
        数据框: 原始数据DataFrame
        行字段: 行字段列表，作为透视表的行索引
        列字段: 列字段列表，作为透视表的列索引
        聚合字典: 聚合字典，支持两种格式混合使用：
                 格式1（单列聚合）: {'新列名': ('原列名', 聚合函数)}
                 格式2（多列聚合）: {'新列名': lambda g: 表达式}
        转列表: 是否转换为二维列表格式
        填充值: 填充空值，默认为""
        表头合并: 行列多层表头是否合并同类项
        小数位数: 对数值列进行四舍五入的小数位数，None表示不处理
        字段按拼音排序: 默认为true 否则按原始数据出现顺序
    返回:
        透视表: 透视表DataFrame或二维列表
    """
    # 检查字段是否存在
    行字段= [] if 行字段 is None else 行字段
    列字段= [] if 列字段 is None else 列字段
    所有字段 = 行字段 + 列字段
    缺失字段 = [字段 for 字段 in 所有字段 if 字段 not in 数据框.columns]
    if 缺失字段:
        raise ValueError(f"以下字段在数据框中不存在: {缺失字段}")
    
    # ===== 核心改进1：保存原始顺序 =====
    数据框 = 数据框.copy()  # 避免修改原始数据
    
    # 为行字段和列字段创建有序分类类型，保持原始出现顺序
    for 字段 in 行字段 + 列字段:
        if 字段 in 数据框.columns:
            # 获取该字段值在原始数据中的首次出现顺序
            原始顺序 = 数据框[字段].drop_duplicates().tolist()
            # 转换为有序分类类型
            数据框[字段] = pd.Categorical(
                数据框[字段], 
                categories=原始顺序, 
                ordered=True
            )
    
    # ===== 核心改进：区分两种聚合方式 =====
    传统聚合字典 = {}  # 格式1: {'新列名': ('原列名', 函数)}
    apply聚合字典 = {}  # 格式2: {'新列名': lambda g: ...}
    聚合字典顺序 = list(聚合字典.keys())  # 保存原始顺序！

    for 新列名, 聚合配置 in 聚合字典.items():
        if isinstance(聚合配置, tuple):
            # 格式1：传统的单列聚合
            原列名, 聚合函数 = 聚合配置
            if 原列名 not in 数据框.columns:
                raise ValueError(f"聚合字典中列'{原列名}'不存在")
            传统聚合字典[新列名] = 聚合配置
        elif callable(聚合配置):
            # 格式2：apply形式的多列聚合
            apply聚合字典[新列名] = 聚合配置
        else:
            raise ValueError(f"聚合字典中'{新列名}'的配置格式不正确，应为 tuple 或 callable")
    
    # ===== 执行分组聚合 =====
    分组字段 = 行字段 + 列字段 if (行字段 and 列字段) else (行字段 or 列字段)
    
    if not 分组字段:
        # 无分组字段，特殊处理
        分组对象 = [数据框]  # 整个DataFrame作为一个组
        使用分组 = False
    else:
        分组对象 = 数据框.groupby(分组字段, sort=False, observed=True)  # observed=False保留所有分类
        使用分组 = True
    
    结果列表 = []
    
    # 执行传统聚合
    if 传统聚合字典:
        if 使用分组:
            传统结果 = 分组对象.agg(**传统聚合字典).reset_index()
        else:
            # 无分组时的处理
            传统结果_dict = {}
            for 新列名, (原列名, 聚合函数) in 传统聚合字典.items():
                if callable(聚合函数):
                    传统结果_dict[新列名] = 聚合函数(数据框[原列名])
                else:
                    传统结果_dict[新列名] = 数据框[原列名].agg(聚合函数)
            传统结果 = pd.DataFrame([传统结果_dict])
        结果列表.append(传统结果)
    
    # 执行apply聚合
    if apply聚合字典:
        if 使用分组:
            # 保持 apply 内部的顺序
            apply结果 = 分组对象.apply(
                lambda g: pd.Series({k: apply聚合字典[k](g) for k in apply聚合字典.keys()}),
                include_groups=False  # pandas 2.x 兼容性
            ).reset_index()
        else:
            # 无分组时的处理
            apply结果_dict = {k: v(数据框) for k, v in apply聚合字典.items()}
            apply结果 = pd.DataFrame([apply结果_dict])
        结果列表.append(apply结果)
    
    # ===== 合并结果 =====
    if len(结果列表) == 2:
        # 两种聚合都有，横向合并
        if 使用分组:
            结果 = pd.merge(结果列表[0], 结果列表[1], on=分组字段, how='outer')
        else:
            结果 = pd.concat(结果列表, axis=1)
    elif len(结果列表) == 1:
        结果 = 结果列表[0]
    else:
        raise ValueError("聚合字典不能为空")
    
    # ===== 重要：按照原始聚合字典的顺序重新排列列 =====
    if 使用分组:
        结果 = 结果[分组字段 + 聚合字典顺序]
    else:
        结果 = 结果[聚合字典顺序]
    
    # ===== 转换为透视表格式 =====
    if not 行字段 and not 列字段:
        # 无行列字段，直接返回聚合结果
        透视表 = 结果
    elif not 列字段:
        # 只有行字段，无需pivot
        透视表 = 结果.set_index(行字段)
    elif not 行字段:
        # 只有列字段
        透视表 = 结果.set_index(列字段).T
    else:
        # 标准透视
        透视表 = 结果.pivot(
            index=行字段,
            columns=列字段,
            values=聚合字典顺序,  # 使用原始顺序！
        )
        
        # 兼容无行字段的情况：Series 转 DataFrame
        if isinstance(透视表, pd.Series):
            透视表 = 透视表.to_frame().T
        
        # === 重点修复：确保 MultiIndex 列的顺序正确 ===
        if isinstance(透视表.columns, pd.MultiIndex) and len(聚合字典顺序) > 1:
            # 重新排序最外层（values层）
            透视表 = 透视表.reindex(columns=聚合字典顺序, level=0)
            

    # ===== 确保最终透视表的聚合字段顺序与聚合字典一致 =====
    if isinstance(透视表.columns, pd.MultiIndex):
        # 获取当前最外层(values层)的唯一值
        outer_level_values = 透视表.columns.get_level_values(0).unique()
        # 过滤聚合字典顺序中实际存在于列中的值
        desired_order = [col for col in 聚合字典顺序 if col in outer_level_values]
        # 重新排序
        透视表 = 透视表.reindex(columns=desired_order, level=0)
    if 字段按拼音排序 : #行列字段按拼音排序
        透视表=z数据框表头排序(透视表,行字段+列字段)

    # ===== 小数位数处理 =====
    if 小数位数 is not None:
        if isinstance(透视表, pd.DataFrame):
            # 遍历所有列，对数值类型列进行 round
            透视表=透视表.round(小数位数)
            
    if 填充值 is not None:
        透视表 = 透视表.fillna(填充值)

    if 转列表:
        return df_to_list(透视表, 表头合并=表头合并)
    else:
        return 透视表


def df_to_list(
    df: pd.DataFrame, 
    表头合并: bool = False, 
    列层级顺序: Optional[List[int]] = None,
    保持行原顺序: bool = True,
) -> List[List[Any]]:
    """
    将 pandas DataFrame 转换为带表头的二维列表（Excel 透视表样式）
    
    支持：
    - 普通 DataFrame
    - pivot_table 结果
    - pivot 结果  
    - groupby().reset_index() 结果
    
    参数：
        df: pandas DataFrame
        表头合并: bool, 默认 False
            - False: 返回普通的二维列表（可能有重复的表头值）
            - True: 在二维列表中直接体现合并效果，被合并的单元格用空字符串填充
        列层级顺序: List[int], 可选
            - 自定义列层级的显示顺序，例如 [0, 1, 2] 或 [2, 0, 1]
            - 仅对多级列索引有效
            - 如果为 None，则使用默认顺序（dimension → value → aggfunc）
        保持行原顺序: bool, 默认 True
            - True: 按数据原始出现顺序排列行
            - False: 按字母顺序排序（pandas 默认行为）
        
    返回：
        List[List[Any]]: 二维列表
    """
    # 输入验证和预处理
    if isinstance(df, list):
        return df
    if isinstance(df, pd.Series):
        df = df.to_frame().T
    df = df.copy()
    
    # 保存原始行索引信息
    original_index_names = []
    index_col_count = 0
    
    if not isinstance(df.index, pd.RangeIndex):
        # 如果需要保持原顺序，在 reset_index 前记录原始顺序
        if 保持行原顺序 and isinstance(df.index, pd.MultiIndex):
            df = _sort_index_by_original_order(df)
        
        # 保存索引名称
        if isinstance(df.index, pd.MultiIndex):
            original_index_names = list(df.index.names)
            index_col_count = df.index.nlevels
        else:
            original_index_names = [df.index.name if df.index.name is not None else '']
            index_col_count = 1
        
        df = df.reset_index()
    
    # 处理列索引排序
    if isinstance(df.columns, pd.MultiIndex):
        if 列层级顺序 is not None:
            df = _reorder_by_custom_order(df, 列层级顺序)
        else:
            df = _reorder_to_excel_style(df)
    
    # 转换为列表
    result = []
    
    # 添加表头
    if isinstance(df.columns, pd.MultiIndex):
        for level in range(df.columns.nlevels):
            header_row = [col[level] if isinstance(col, tuple) else col for col in df.columns]
            result.append(header_row)
    else:
        result.append(df.columns.tolist())

   # df=df.astype(object) #转为python数据类型 
    df=df日期时间标准化(df)
    # 添加数据行
    result.extend(df.values.tolist())
    
    # 应用表头合并
    if 表头合并:
        result = _apply_merges_to_list(result, df.columns, index_col_count, original_index_names)
    
    return result

def df日期时间标准化(df: pd.DataFrame) -> pd.DataFrame:
    """
    将 DataFrame 中的所有时间列（包括 Timestamp、datetime64[ns]、object 类型的时间）转换为无时区的 datetime 类型，
    避免写入 Excel 时报错：'NoneType' object has no attribute 'total_seconds'
    参数:
        df (pd.DataFrame): 输入的 DataFrame
    返回:
        pd.DataFrame: 处理后的时间列已转为 datetime 的 DataFrame
    """
    #df = df.copy()  # 避免修改原始数据

    for col in df.columns:
        if df[col].dtype == 'datetime64[ns, UTC]' :
            try:
                #转为datetime 类型
                #注意必须处理 dtype="object" 不然总是会转为pandas日期类型
                df[col] = pd.Series([x.to_pydatetime() if pd.notna(x) else None for x in df[col]], dtype="object")
                #print(type(df[col].iloc[0]))
            except Exception as e:
                #print(f"列 '{col}' 转换失败: {e}")
                continue
    return df

def _sort_index_by_original_order(df: pd.DataFrame) -> pd.DataFrame:
    """
    按原始出现顺序对多级行索引进行排序
    
    核心逻辑：
    1. 记录每个层级中每个值在其父层级上下文中的首次出现位置
    2. 构建分层排序键，按原始顺序排序
    """
    if not isinstance(df.index, pd.MultiIndex):
        return df
    
    index = df.index
    nlevels = index.nlevels
    
    # 构建分层排序键
    sort_keys = []
    
    for idx_tuple in index:
        key = []
        
        for level_idx in range(nlevels):
            # 构建当前层级的父上下文
            parent_context = idx_tuple[:level_idx]
            current_value = idx_tuple[level_idx]
            
            # 在相同父上下文中，查找当前值的首次出现位置
            position = 0
            seen = set()
            for other_tuple in index:
                other_parent = other_tuple[:level_idx]
                other_value = other_tuple[level_idx]
                
                # 只在相同父上下文中计数
                if other_parent == parent_context:
                    if other_value == current_value:
                        break
                    if other_value not in seen:
                        seen.add(other_value)
                        position += 1
            
            key.append(position)
        
        sort_keys.append(tuple(key))
    
    # 按排序键排序
    sorted_indices = sorted(range(len(index)), key=lambda i: sort_keys[i])
    
    return df.iloc[sorted_indices]


def _reorder_to_excel_style(df: pd.DataFrame) -> pd.DataFrame:
    """
    将多级列索引重排为 Excel 透视表样式，并保持原始数据顺序
    顺序：列字段 → 值字段 → 聚合函数
    """
    if not isinstance(df.columns, pd.MultiIndex):
        return df
    
    columns = df.columns
    nlevels = columns.nlevels
    
    if nlevels == 1:
        return df
    
    # 分析层级类型
    level_types = _classify_column_levels(columns)
    
    # 构建新的层级顺序
    new_order = (
        [i for i, t in enumerate(level_types) if t == 'dimension'] +
        [i for i, t in enumerate(level_types) if t == 'value'] +
        [i for i, t in enumerate(level_types) if t == 'aggfunc']
    )
    
    # 重新排列层级
    if new_order != list(range(nlevels)):
        df.columns = df.columns.reorder_levels(new_order)
    
    # 按原始顺序排序列
    return _sort_columns_by_original_order(df)


def _sort_columns_by_original_order(df: pd.DataFrame) -> pd.DataFrame:
    """
    按原始出现顺序对多级列索引进行排序
    
    核心逻辑：每个层级的值在其父层级上下文中保持首次出现的顺序
    例如：
    - Level 0: 手机, 鼠标（全局顺序）
    - Level 1 under '鼠标': Gaming-2, Gaming-3, Mouse-1, ... (在'鼠标'下的顺序)
    """
    if not isinstance(df.columns, pd.MultiIndex):
        return df
    
    columns = df.columns
    nlevels = columns.nlevels
    
    # 构建分层排序键
    sort_keys = []
    
    for col_tuple in columns:
        key = []
        
        for level_idx in range(nlevels):
            # 构建当前层级的父上下文
            parent_context = col_tuple[:level_idx]
            current_value = col_tuple[level_idx]
            
            # 在相同父上下文中，查找当前值的首次出现位置
            position = 0
            seen = set()
            for other_tuple in columns:
                other_parent = other_tuple[:level_idx]
                other_value = other_tuple[level_idx]
                
                # 只在相同父上下文中计数
                if other_parent == parent_context:
                    if other_value == current_value:
                        break
                    if other_value not in seen:
                        seen.add(other_value)
                        position += 1
            
            key.append(position)
        
        sort_keys.append(tuple(key))
    
    # 按排序键排序
    sorted_indices = sorted(range(len(columns)), key=lambda i: sort_keys[i])
    sorted_columns = [columns[i] for i in sorted_indices]
    
    return df[sorted_columns]


def _reorder_by_custom_order(df: pd.DataFrame, custom_order: List[int]) -> pd.DataFrame:
    """按用户指定的顺序重新排列多级列索引"""
    if not isinstance(df.columns, pd.MultiIndex):
        return df
    
    nlevels = df.columns.nlevels
    
    # 验证有效性
    if len(custom_order) != nlevels or set(custom_order) != set(range(nlevels)):
        raise ValueError(f"列层级顺序必须包含 0 到 {nlevels-1} 的所有索引")
    
    # 重新排列层级
    if custom_order != list(range(nlevels)):
        df.columns = df.columns.reorder_levels(custom_order)
    
    return _sort_columns_by_original_order(df)


def _classify_column_levels(columns: pd.MultiIndex) -> List[str]:
    """
    分类多级列索引的每一层
    返回：'dimension'（列字段）, 'value'（值字段）, 'aggfunc'（聚合函数）
    """
    AGGFUNC_KEYWORDS = {'sum', 'mean', 'count', 'min', 'max', 'std', 'var', 
                        'median', 'first', 'last', 'size'}
    
    names = columns.names
    nlevels = columns.nlevels
    level_types = []
    
    for level_idx in range(nlevels):
        name = names[level_idx]
        unique_values = set(columns.get_level_values(level_idx).unique())
        
        if name is not None:
            level_types.append('dimension')
        elif unique_values & AGGFUNC_KEYWORDS:
            level_types.append('aggfunc')
        else:
            level_types.append('value')
    
    # 特殊处理：所有层级名称都是 None
    if all(name is None for name in names):
        level_types = ['dimension'] * nlevels
        last_values = set(columns.get_level_values(-1).unique())
        
        if last_values & AGGFUNC_KEYWORDS:
            level_types[-1] = 'aggfunc'
            if nlevels >= 2:
                level_types[-2] = 'value'
        else:
            level_types[-1] = 'value'
    
    return level_types


def _apply_merges_to_list(
    data: List[List[Any]], 
    columns: pd.Index, 
    index_col_count: int,
    index_names: List[str],
    placeholder: Any = ""
) -> List[List[Any]]:
    """
    直接在二维列表中应用合并效果
    
    规则：
    1. 横向合并：表头中相邻的相同值，只保留第一个，其余用占位符替换
    2. 纵向合并：行索引列在多级表头中，列名显示在最后一行，其他行用占位符替换
    """
    is_multi_index = isinstance(columns, pd.MultiIndex)
    header_rows = columns.nlevels if is_multi_index else 1
    
    # 1. 处理行索引列的纵向合并
    if is_multi_index and index_col_count > 0 and header_rows > 1:
        last_header_row = header_rows - 1
        
        for col_idx in range(index_col_count):
            # 最后一行显示索引名称
            if col_idx < len(index_names):
                data[last_header_row][col_idx] = index_names[col_idx] or ''
            
            # 前面的行用占位符替换
            for row_idx in range(last_header_row):
                data[row_idx][col_idx] = placeholder
    
    # 2. 处理多级表头的横向合并
    if is_multi_index:
        for level in range(header_rows):
            col_idx = index_col_count
            
            while col_idx < len(data[level]):
                current_value = data[level][col_idx]
                merge_end = col_idx + 1
                
                # 查找相邻相同值
                while merge_end < len(data[level]) and data[level][merge_end] == current_value:
                    merge_end += 1
                
                # 清空后续相同值（实现合并效果）
                for clear_idx in range(col_idx + 1, merge_end):
                    data[level][clear_idx] = placeholder
                
                col_idx = merge_end
    
    return data

#enddf
def df表头排序(df, 字段列表=None, 排序方式="拼音")->pd.DataFrame:
    """
    对DataFrame的行索引和列索引进行排序。

    参数:
        df (pd.DataFrame): 需要排序的DataFrame。
        字段列表支持后缀'+'表示升序，'-'表示降序。
        排序方式 (str or callable, optional): 排序依据。可选值：
            - "拼音": 使用拼音顺序排序（默认）；
            - callable: 自定义排序函数。lambda x: len(x)

    返回值:
        pd.DataFrame: 排序后的DataFrame。

    示例:
        >>> df = pd.DataFrame(...)
        >>> df_sorted = df表头排序(df, ["A-", "B+"])
    """
    if isinstance(字段列表, str):
        字段列表 = [字段列表]
    
    # 解析字段配置
    def 解析字段(字段):
        if 字段.endswith('-'):
            return 字段[:-1], True
        elif 字段.endswith('+'):
            return 字段[:-1], False
        else:
            return 字段, False
    
    # 获取索引信息
    行字段集 = set(df.index.names) if isinstance(df.index, pd.MultiIndex) else {df.index.name}
    列字段集 = set(df.columns.names) if isinstance(df.columns, pd.MultiIndex) else {df.columns.name}
    
    # 分类字段
    if 字段列表 is None:
        行配置 = [(f, False) for f in df.index.names if f is not None]
        列配置 = [(f, False) for f in df.columns.names if f is not None]
    else:
        解析结果 = [解析字段(f) for f in 字段列表]
        行配置 = [(f, desc) for f, desc in 解析结果 if f in 行字段集]
        列配置 = [(f, desc) for f, desc in 解析结果 if f in 列字段集]
    
    # 排序函数
    if 排序方式 == "拼音":
        try:
            from . import vba
        except ImportError:
            import vba
        key_func = lambda x: vba.z拼音全拼(x)
    elif callable(排序方式):
        key_func = 排序方式
    else:
        key_func = lambda x: x
    
    # 执行排序
    if 行配置:
        df = _df多级排序(df, 行配置, axis=0, key_func=key_func)
    if 列配置:
        df = _df多级排序(df, 列配置, axis=1, key_func=key_func)
    
    return df
#end def

def _df多级排序(df, 字段配置, axis, key_func):
    """多级索引排序"""
    idx = df.columns if axis == 1 else df.index
    
    if not isinstance(idx, pd.MultiIndex):
        # 单级索引
        _, 降序 = 字段配置[0]
        sorted_idx = sorted(idx, key=key_func, reverse=降序)
    else:
        # 多级索引 - 构建排序键的DataFrame
        名称映射 = {name: i for i, name in enumerate(idx.names)}
        
        # 创建一个包含所有level值的DataFrame
        idx_df = pd.DataFrame(idx.tolist(), columns=idx.names)
        
        # 为每个排序字段添加排序键列
        sort_keys = []
        sort_ascending = []
        
        for 字段名, 降序 in 字段配置:
            if 字段名 in 名称映射:
                # 应用key_func到该列
                key_col_name = f'_sort_key_{字段名}'
                idx_df[key_col_name] = idx_df[字段名].apply(key_func)
                sort_keys.append(key_col_name)
                sort_ascending.append(not 降序)
        
        # 按构建的键排序
        idx_df_sorted = idx_df.sort_values(by=sort_keys, ascending=sort_ascending)
        
        # 重建MultiIndex
        sorted_idx = pd.MultiIndex.from_arrays(
            [idx_df_sorted[name].values for name in idx.names],
            names=idx.names
        )
    
    return df[sorted_idx] if axis == 1 else df.loc[sorted_idx]

#end def

z超级透视表=super_pivot_table
z数据框转列表=df_to_list
z数据框表头排序=df表头排序
# ==================== 测试函数 ====================
def _test_super_pivot_table_order():
    """测试聚合字典顺序保持"""
    import pandas as pd
   
    try:
        from .log_helper import logtable
    except ImportError:
        from log_helper import logtable
    
    print("\n" + "="*80)
    print("测试：聚合字典顺序保持测试")
    print("="*80)
    
    data = {
        '地区': ['北京', '北京', '上海', '上海', '广州', '广州'],
        '产品': ['电脑', '电脑', '手机', '电脑', '手机', '电脑'],
        '销量': [100, 50, 120, 60, 90, 45],
        '单价': [5000, 8000, 5200, 8200, 4800, 7800],
        '成本': [3000, 5000, 3100, 5100, 2900, 4900]
    }
    df = pd.DataFrame(data)
    df.join
    print("\n原始数据：")
    logtable(df)
    
    # 注意这里的顺序！
    聚合字典 = {
        '总销量': ('销量', 'sum'),           # 第1个
        '平均单价': ('单价', 'mean'),         # 第2个
        '总利润': lambda g: ((g['单价'] - g['成本']) * g['销量']).sum(),  # 第3个
        '总成本': lambda g: (g['销量'] * g['成本']).sum(),  # 第4个
        '总收入': lambda g: (g['销量'] * g['单价']).sum(),  # 第5个
        '利润率%': lambda g: (((g['单价']-g['成本'])*g['销量']).sum() / 
                              (g['销量']*g['单价']).sum() * 100) if (g['销量']*g['单价']).sum() > 0 else 0  # 第6个
    }
    
    print("\n聚合字典的顺序：")
    for i, key in enumerate(聚合字典.keys(), 1):
        print(f"  {i}. {key}")
    
    透视结果 = z超级透视表(
        数据框=df,
        行字段=['地区'],
        列字段=['产品'],
        聚合字典=聚合字典,
        转列表=False,
        表头合并=True,
        小数位数=2
    )
    
    print("\n透视结果（应该保持上述顺序）：")
    d=df_to_list(透视结果)
    logtable(透视结果)
    
    print("\n" + "="*80)
    print("测试2：你图片中的例子")
    print("="*80)
    
    data2 = {
        '地区': ['北京', '北京', '上海', '上海'] * 2,
        '产品': ['手机', '电脑', '手机', '电脑'] * 2,
        '客户类型': ['个人'] * 4 + ['公司'] * 4,
        '销量': [100, 50, 120, 60, 80, 40, 90, 55],
        '单价': [5000, 8000, 5200, 8200, 5100, 8100, 5300, 8300],
        '成本': [3000, 5000, 3100, 5100, 3050, 5050, 3150, 5150]
    }
    df2 = pd.DataFrame(data2)
    
    print("\n原始数据：")
    logtable(df2)
    
    # 完全按照你图片中的顺序
    聚合字典2 = {
        '总销量': ('销量', 'sum'),
        '平均单价': ('单价', 'mean'),
        '总收入': lambda g: (g['销量'] * g['单价']).sum(),
        '总成本': lambda g: (g['销量'] * g['成本']).sum(),
        '总利润': lambda g: ((g['单价'] - g['成本']) * g['销量']).sum(),
        '利润率%': lambda g: (((g['单价']-g['成本'])*g['销量']).sum() / (g['销量']*g['单价']).sum() * 100) if (g['销量']*g['单价']).sum() > 0 else 0
    }
    
    透视结果2 = z超级透视表(
        数据框=df2,
        行字段=['地区'],
        列字段=['产品'],
        聚合字典=聚合字典2,
        转列表=True,
        表头合并=True
    )
    
    print("\n透视结果（顺序应该是：总销量、平均单价、总收入、总成本、总利润、利润率%）：")
    logtable(透视结果2, 表头行数=2)
    

if __name__ == "__main__":
    
    _test_super_pivot_table_order()
