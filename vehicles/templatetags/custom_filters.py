from django import template

register = template.Library()

@register.filter
def index(sequence, position):
    """允许在模板中使用 list|index:0 获取第1个元素"""
    try:
        return sequence[position]
    except (IndexError, TypeError):
        return ''

@register.filter
def to(start, end):
    return range(start, end)

@register.filter
def to_int(value):
    """
    将数字或数字字符串转成 int，失败时返回 0
    """
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return 0

@register.filter
def display_datetime(value):
    return value.strftime('%Y-%m-%d %H:%M')