# --- [追加] 日文曜日フィルタ ---
from django import template as _tmpl  # 若文件已定义 register，此行不会冲突

try:
    register
except NameError:
    register = _tmpl.Library()

@register.filter
def ja_weekday(value):
    """
    将日期/时间转换为日文星期简称：月火水木金土日
    优先用 .weekday()（Monday=0）以符合日本常用显示。
    """
    try:
        wd = value.weekday()  # Monday=0 .. Sunday=6
    except Exception:
        return ""
    mapping = ["月", "火", "水", "木", "金", "土", "日"]
    if 0 <= wd <= 6:
        return mapping[wd]
    return ""


@register.filter
def get_item(d, key):
    try:
        return d.get(key)
    except Exception:
        try:
            return d[key]
        except Exception:
            return ""