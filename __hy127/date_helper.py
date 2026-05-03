# file: date_utils.py
from dateutil.relativedelta import relativedelta
from datetime import datetime, timedelta
import calendar
try:
    from . import vba
except ImportError:
    import vba
import re,arrow
def z转表格日期(日期: datetime) -> float:
    """
    将日期转换为Excel表格数值型日期
    
    Args:
        日期: datetime对象
        
    Returns:
        str: YYYY-MM-DD格式的日期字符串
    """
    return vba.z转日期数值(日期)

def z日期格式化(日期: datetime, 格式: str) -> str:
    """
    按指定格式格式化日期，支持Excel TEXT函数格式参数
    
    Args:
        日期 (datetime): datetime对象，需要格式化的日期时间
        格式 (str): 日期格式字符串，支持Excel TEXT函数格式，如 "yyyy-mm-dd"
            支持的格式包括:
            - yyyy: 四位年份
            - yy: 两位年份
            - MM: 两位数字月份
            - M: 数字月份（无前导零）
            - dddd: 完整星期名称
            - ddd: 缩写星期名称
            - dd: 两位数字日期
            - d: 数字日期（无前导零）
            - hh: 两位数字小时（24小时制）
            - h: 数字小时（24小时制，无前导零）
            - mm: 两位数字分钟
            - m: 数字分钟（无前导零）
            - ss: 两位数字秒
            - s: 数字秒（无前导零）
            - am/pm: 上午/下午
            - a/p: A/P
            
    Returns:
        str: 格式化后的日期字符串
        
    Examples:
        >>> from datetime import datetime
        >>> 日期 = datetime(2023, 5, 16, 14, 30, 45)
        >>> z日期格式化(日期, "yyyy-MM-dd")
        '2023-05-16'
        >>> z日期格式化(日期, "yyyy年M月d日")
        '2023年5月16日'
        >>> z日期格式化(日期, "hh:mm:ss")
        '14:30:45'
    """
    # Excel格式到Python strftime格式的映射
    格式映射 = {
        "yyyy": "%Y",  # 四位年份
        "yy": "%y",    # 两位年份
        "MM": "%m",    # 两位数字月份
        "M": "%#m",    # 数字月份（无前导零）
        "dddd": "%A",  # 完整星期名称
        "ddd": "%a",   # 缩写星期名称
        "dd": "%d",    # 两位数字日期
        "d": "%#d",    # 数字日期（无前导零）
        "hh": "%H",    # 两位数字小时（24小时制）
        "h": "%#H",    # 数字小时（24小时制，无前导零）
        "mm": "%M",    # 两位数字分钟
        "m": "%#M",    # 数字分钟（无前导零）
        "ss": "%S",    # 两位数字秒
        "s": "%#S",    # 数字秒（无前导零）
        "am/pm": "%p", # 上午/下午
        "a/p": "%p",   # A/P
    }
    
    # 创建格式副本以避免修改原始参数
    转换格式 = 格式
    转换格式 = re.sub(r"[YD]", lambda m: m.group(0).lower(), 转换格式)
    # 按长度降序排列，避免部分匹配问题
    排序映射 = sorted(格式映射.items(), key=lambda x: len(x[0]), reverse=True)
    
    # 先按位置替换成{0},{1},{2}...的形式
    for 下标, (excel_format, python_format) in enumerate(排序映射):
        转换格式 = 转换格式.replace(excel_format, "{" + str(下标) + "}")
    #print(转换格式)
    # 再把{0},{1},{2}...替换为对应的Python格式
   
    def 替换函数(匹配):
        下标 = int(匹配.group(1))
        return 排序映射[下标][1]
    
    转换格式 = re.sub(r"\{(\d+)\}", 替换函数, 转换格式)
    
    return 日期.strftime(转换格式)

def z加天(日期: datetime, 天数: int) -> datetime:
    """
    在指定日期上增加天数
    
    Args:
        日期: datetime对象
        天数: 要增加的天数
        
    Returns:
        datetime: 增加天数后的日期
    """
    return 日期 + timedelta(days=天数)

def z加时间(日期: datetime, 秒数: int) -> datetime:
    """
    在指定日期上增加秒数
    
    Args:
        日期: datetime对象
        秒数: 要增加的秒数
        
    Returns:
        datetime: 增加秒数后的日期
    """
    return 日期 + timedelta(seconds=秒数)

def z加月(日期: datetime, 月数: int) -> datetime:
    """
    在指定日期上增加月数
    
    Args:
        日期: datetime对象
        月数: 要增加的月数
        
    Returns:
        datetime: 增加月数后的日期
    """
    年 = 日期.year
    月 = 日期.month + 月数
    日 = 日期.day
    
    # 处理月份溢出情况
    while 月 > 12:
        年 += 1
        月 -= 12
        
    while 月 < 1:
        年 -= 1
        月 += 12
        
    # 处理日期溢出情况（例如1月31日加1个月应该是2月28日或29日）
    最大日期 = calendar.monthrange(年, 月)[1]
    if 日 > 最大日期:
        日 = 最大日期
        
    return 日期.replace(year=年, month=月, day=日)

def z加年(日期: datetime, 年数: int) -> datetime:
    """
    在指定日期上增加年数
    
    Args:
        日期: datetime对象
        年数: 要增加的年数
        
    Returns:
        datetime: 增加年数后的日期
    """
    try:
        return 日期.replace(year=日期.year + 年数)
    except ValueError:
        # 处理闰年2月29日的情况
        return 日期.replace(year=日期.year + 年数, day=28)
    
def z年(日期: datetime) -> int:
    """
    获取日期中的年份
    
    Args:
        日期: datetime对象
        
    Returns:
        int: 年份
    """
    return 日期.year

def z月(日期: datetime) -> int:
    """
    获取日期中的月份
    
    Args:
        日期: datetime对象
        
    Returns:
        int: 月份
    """
    return 日期.month

def z日(日期: datetime) -> int:
    """
    获取日期中的日
    
    Args:
        日期: datetime对象
        
    Returns:
        int: 日
    """
    return 日期.day

def z星期(日期: datetime) -> int:
    """
    获取日期中的星期几 (1=周一 ... 7=周日)
    
    Args:
        日期: datetime对象

            
    Returns:
        int: 星期几 (0-6)
    """
    # Python的weekday()返回0=周一...6=周日
    return 日期.weekday()+1

def z星期中文(日期: datetime) -> str:
    """
    获取日期中的中文星期几
    
    Args:
        日期: datetime对象
        
    Returns:
        str: 中文星期几
    """
    星期映射 = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    return 星期映射[日期.weekday()]

def z季度(日期: datetime) -> int:
    """
    获取日期所属季度
    
    Args:
        日期: datetime对象
        
    Returns:
        int: 季度 (1-4)
    """
    return (日期.month - 1) // 3 + 1

def z当月天数(日期: datetime) -> int:
    """
    获取指定日期所在月份的总天数
    
    Args:
        日期: datetime对象
        
    Returns:
        int: 当月天数
    """
    return calendar.monthrange(日期.year, 日期.month)[1]

def z月初(日期: datetime) -> datetime:
    """
    获取指定日期所在月份的第一天
    
    Args:
        日期: datetime对象
        
    Returns:
        datetime: 月初日期
    """
    return 日期.replace(day=1)

def z月底(日期: datetime) -> datetime:
    """
    获取指定日期所在月份的最后一天
    
    Args:
        日期: datetime对象
        
    Returns:
        datetime: 月末日期
    """
    下月第一天 = (日期.replace(day=28) + timedelta(days=4)).replace(day=1)
    本月最后一天 = 下月第一天 - timedelta(days=1)
    return 本月最后一天

def z转VBA日期数值(日期: datetime) -> float:
    """
    将日期转换为VBA日期数值格式

    Args:
        日期: datetime对象
        
    Returns:
        float: Excel日期数值
    """
    return vba.z转日期数值(日期)

def z表格日期转py(日期字符串: str) -> datetime:
    """
    将表格日期字符串转换为datetime对象
    
    Args:
        日期字符串: YYYY-MM-DD格式的日期字符串
        
    Returns:
        datetime: datetime对象
    """
    return vba.z转日期(日期字符串)

def z今天日期() -> datetime:
    """
    获取今天的日期
    
    Returns:
        datetime: 今天的日期
    """
    return datetime.today()

def z日期时间() -> datetime:
    """
    获取当前日期和时间
    
    Returns:
        datetime: 当前日期和时间
    """
    return datetime.now()

def z时间() -> str:
    """
    获取当前时间字符串(HH:MM:SS)
    
    Returns:
        str: 当前时间字符串
    """
    return datetime.now().strftime("%H:%M:%S")

def z日期间隔(开始日期: datetime, 结束日期: datetime) -> dict:
    """
    计算两个日期之间的间隔
    
    Args:
        开始日期: 开始datetime对象
        结束日期: 结束datetime对象
        
    Returns:
        dict: 包含天数、小时数、分钟数等的字典
    """
    差值 = 结束日期 - 开始日期
    总秒数 = int(差值.total_seconds())
    天数 = 差值.days
    小时数 = (总秒数 % (24 * 3600)) // 3600
    分钟数 = (总秒数 % 3600) // 60
    秒数 = 总秒数 % 60
    
    return {
        "天数": 天数,
        "小时数": 小时数,
        "分钟数": 分钟数,
        "秒数": 秒数,
        "总秒数": 总秒数
    }

def z只留日期(日期: datetime) -> datetime:
    """
    只保留日期部分，去除时间部分
    
    Args:
        日期: datetime对象
        
    Returns:
        datetime: 只包含日期的对象
    """
    return 日期.date()

def z只留时间(日期: datetime) -> datetime:
    """
    只保留时间部分，去除日期部分
    
    Args:
        日期: datetime对象
        
    Returns:
        datetime: 只包含时间的对象
    """
    return 日期.time()


def z间隔年月日(开始, 结束,返回元组=False):
    """
        类似excel的Dateif函数 返回间隔年月日
    """
    借款 = arrow.get(开始)
    还款 = arrow.get(结束)
    期限 = relativedelta(还款.datetime, 借款.datetime)
    if 返回元组:
        return (期限.years,期限.months,期限.days)
    return f"{期限.years}年 {期限.months}月 {期限.days}天"

def z计算年龄(生日,截止日期=None)->int:
    生日 = arrow.get(生日)
    if  截止日期: 
        截止日期 = arrow.get(截止日期)
    else:
        截止日期 = arrow.now()
    年龄 = 截止日期.year - 生日.year
    # 如果今年生日还没到，年龄减1
    if 截止日期.month < 生日.month or (截止日期.month == 生日.month and 截止日期.day < 生日.day):
        年龄 -= 1
    return 年龄

def z某月日期列表(日期):
    日期 = arrow.get(日期)
    月末 = 日期.ceil('month')    
    # 使用列表推导式生成本月日期列表
    日期列表 = [日期.replace(day=日).format('YYYY-MM-DD')  for 日 in range(1, 月末.day + 1)]
    return 日期列表



def main():
    """主函数，演示各函数用法"""
    # 示例用法
    当前时间 = datetime.now()
    print(f"当前时间: {当前时间}")
    print(f"转表格日期: {z转表格日期(当前时间)}")
    print(f"年: {z年(当前时间)}, 月: {z月(当前时间)}, 日: {z日(当前时间)}")
    print(f"星期: {z星期(当前时间)}, 中文星期: {z星期中文(当前时间)}")
    print(f"季度: {z季度(当前时间)}")
    print(f"当月天数: {z当月天数(当前时间)}")
    print(f"月初: {z月初(当前时间)}")
    print(f"月底: {z月底(当前时间)}")
    print(f"加7天: {z加天(当前时间, 7)}")
    print(f"加1个月: {z加月(当前时间, 1)}")
    print(f"加1年: {z加年(当前时间, 1)}")
    print(f"VBA日期数值: {z转VBA日期数值(当前时间)}")
    print(f"今天日期: {z今天日期()}")
    print(f"当前时间: {z时间()}")

if __name__ == "__main__":
    from datetime import date
    d1 = date(2025, 10, 2)
    oa日期值=z转VBA日期数值(d1)
    print(oa日期值)
    d2=z表格日期转py(oa日期值)
    print(d2)
   

    main()
    datetime.now().strftime("%Y-%m-%d")
    import date_helper  
    print(date_helper.z日期格式化(d1,"yyyy-M-d")) 

