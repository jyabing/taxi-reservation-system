from django import template
from decimal import Decimal, InvalidOperation

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
    """生成 range(start, end)，用于模板中 {% for i in x|to:y %}"""
    return range(start, end)

@register.filter
def to_int(value):
    """将字符串或浮点数转换为整数，失败时返回 0"""
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return 0

@register.filter(name="jpy")
def jpy(value):
    """
    金额格式化：去小数 -> 千位逗号
    None/"" -> "0"
    任意可转成数字的值都能安全处理（包含 Decimal / str / int / float）。
    """
    if value is None or value == "":
        return "0"
    try:
        n = int(Decimal(str(value)).quantize(Decimal("1")))
    except (InvalidOperation, ValueError):
        try:
            n = int(float(value))
        except Exception:
            return value  # 非数字，原样返回
    return f"{n:,}"