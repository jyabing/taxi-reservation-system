# dailyreport/utils/debug.py

import datetime, os
from django.conf import settings

# 是否启用调试打印，默认根据环境变量 DEBUG_PRINT_ENABLED 决定
DEBUG_PRINT_ENABLED = os.getenv("DEBUG_PRINT_ENABLED", "1") == "1"    #默认值是 "1"（即开启）

def debug_print(*args, **kwargs):
    """
    封装的调试打印函数。根据开关决定是否输出。
    用法如：debug_print("报告数：", count)
    """
    if DEBUG_PRINT_ENABLED:
        print("[DEBUG]", *args, **kwargs)

def apply_form_control_style(fields):
    """
    批量为 Django Form 字段添加 Bootstrap 的 'form-control' 样式。
    通常用于字段是 Input、TextArea 等类型。
    """
    for name, field in fields.items():
        widget = field.widget
        css_class = widget.attrs.get('class', '')
        if 'form-control' not in css_class:
            widget.attrs['class'] = (css_class + ' form-control').strip()