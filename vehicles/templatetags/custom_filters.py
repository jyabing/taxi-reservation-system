
from django import template

register = template.Library()

@register.filter
def index(sequence, position):
    """允许在模板中使用 list|index:0 获取第1个元素"""
    try:
        return sequence[position]
    except (IndexError, TypeError):
        return ''
