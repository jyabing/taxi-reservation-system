# app/templatetags/attrs.py
from django import template
register = template.Library()

@register.filter
def attr(obj, key):
    """支持对象点取和字典取值：it|attr:'field'"""
    if obj is None or not key:
        return ''
    if isinstance(obj, dict):
        return obj.get(key, '')
    return getattr(obj, key, '')
