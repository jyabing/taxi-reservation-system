from django import template

register = template.Library()

@register.filter
def get_total(totals_dict, key):
    """
    用于获取 totals 中原始金额（raw）的值：totals["{key}_raw"]
    """
    return totals_dict.get(f"{key}_raw", 0)

@register.filter
def get_bonus(totals_dict, key):
    """
    用于获取 totals 中分成金额（split）的值：totals["{key}_split"]
    """
    return totals_dict.get(f"{key}_split", 0)