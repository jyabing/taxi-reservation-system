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