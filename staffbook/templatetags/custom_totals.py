# your_app/templatetags/custom_totals.py

from django import template

register = template.Library()

@register.filter
def get_total(totals_dict, key):
    """从 totals 中取出 total_xxx 值"""
    return totals_dict.get(f"total_{key}", 0)

@register.filter
def get_bonus(totals_dict, key):
    """从 totals 中取出 bonus_xxx 值"""
    return totals_dict.get(f"bonus_{key}", 0)
