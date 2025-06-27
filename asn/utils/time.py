import re
import random
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

TIME_FORMAT = '%Y-%m-%d %H:%M:%S'
TIME_STR_MIN = '1000-01-01 00:00:00'
TIME_STR_MAX = '9999-12-31 23:59:59'

def datetime_to_str(dt: datetime) -> str:
    return datetime.strftime(dt, TIME_FORMAT)

def str_to_datetime(dt_str: str) -> datetime:
    return datetime.strptime(dt_str, TIME_FORMAT)

def parse_interval(intv_str: str) -> relativedelta:
    pattern = r'(\d+)([ymdHMS])'
    matches = re.findall(pattern, intv_str)
    kwargs = {
        'years': 0,
        'months': 0,
        'days': 0,
        'hours': 0,
        'minutes': 0,
        'seconds': 0
    }
    for value, unit in matches:
        value = int(value)
        if unit == 'y':
            kwargs['years'] = value
        elif unit == 'm':
            kwargs['months'] = value
        elif unit == 'd':
            kwargs['days'] = value
        elif unit == 'H':
            kwargs['hours'] = value
        elif unit == 'M':
            kwargs['minutes'] = value
        elif unit == 'S':
            kwargs['seconds'] = value
    return relativedelta(**kwargs)

def add_interval(time_str: str, intv_str: str) -> datetime:
    # return str_to_datetime(time_str) + parse_interval(intv_str)
    return datetime_to_str(str_to_datetime(time_str) + parse_interval(intv_str))

def sub_interval(time_str: str, intv_str: str) -> datetime:
    # return str_to_datetime(time_str) - parse_interval(intv_str)
    return datetime_to_str(str_to_datetime(time_str) - parse_interval(intv_str))


def generate_random_between(start_str: str, end_str: str) -> datetime:
    # 解析时间字符串为 datetime 对象
    fmt = "%Y-%m-%d %H:%M:%S"
    start = datetime.strptime(start_str, fmt)
    end = datetime.strptime(end_str, fmt)
    
    # 确保时间顺序正确
    if start > end:
        start, end = end, start
    
    # 计算时间差（秒数）
    delta = (end - start).total_seconds()
    
    # 生成随机秒数偏移量（包含起始时间，不包含结束时间）
    random_seconds = random.uniform(0, delta)
    
    # 生成随机时间
    return start + timedelta(seconds=random_seconds)

