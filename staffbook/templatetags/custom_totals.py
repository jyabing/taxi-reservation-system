from django import template
register = template.Library()

@register.filter
def get_total(data, key):
    """兼容两种结构：扁平结构 或 嵌套结构"""
    if f"{key}_raw" in data:
        return data.get(f"{key}_raw", 0)
    return data.get(key, {}).get('total', 0)

@register.filter
def get_bonus(data, key):
    """兼容两种结构：扁平结构 或 嵌套结构"""
    if f"{key}_split" in data:
        return data.get(f"{key}_split", 0)
    return data.get(key, {}).get('bonus', 0)