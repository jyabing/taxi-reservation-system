from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    try:
        return dictionary.get(key)
    except AttributeError:
        return None

@register.filter
def get_meter_only(dictionary, key):
    try:
        return dictionary.get(key, 0)
    except Exception:
        return 0

@register.filter
def get_total(dictionary, key):
    try:
        return dictionary.get(key, {}).get("total", 0)
    except Exception:
        return 0

@register.filter
def get_bonus(dictionary, key):
    try:
        return dictionary.get(key, {}).get("bonus", 0)
    except Exception:
        return 0

@register.filter
def get_count(counts_dict, key):
    """
    从 counts 字典里取指定 key 的件数
    用法：{{ counts|get_count:key }}
    """
    try:
        return counts_dict.get(key, 0)
    except Exception:
        return 0