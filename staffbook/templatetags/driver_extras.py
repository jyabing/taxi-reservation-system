from datetime import date
from django import template

register = template.Library()

@register.filter
def age(value):
    """
    计算年龄。如果 value 不是 date 类型，返回空字符串。
    """
    if not value or not hasattr(value, "year"):
        return ""
    today = date.today()
    return today.year - value.year - ((today.month, today.day) < (value.month, value.day))

@register.filter
def typeof(value):
    return str(type(value))

@register.filter
def format_duration(value):
    """
    格式化 timedelta 为 'H:MM' 格式（支持负数）。
    例：
        3:36:00 → 3:36
        -1 day, 19:36:00 → -4:24
    """
    if not value:
        return "--:--"

    total_seconds = int(value.total_seconds())
    negative = total_seconds < 0
    total_seconds = abs(total_seconds)

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60

    return f"{'-' if negative else ''}{hours}:{minutes:02d}"
