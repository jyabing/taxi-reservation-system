from django import template
register = template.Library()

@register.filter
def get_total(data, key):
    """获取某支付方式的总金额"""
    return data.get(key, {}).get('total', 0)

@register.filter
def get_bonus(data, key):
    """获取某支付方式的分成金额"""
    return data.get(key, {}).get('bonus', 0)