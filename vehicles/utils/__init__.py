"""
vehicles.utils 包初始化文件
统一导出常用工具函数，供 views / admin / commands 等模块直接使用。
"""

# === 通知相关 ===
from .notify import (
    send_notification,
    notify_driver_reservation_approved,
)

from .admin_notify import (
    notify_admin_about_new_reservation,
)

# === 冲突检测工具 ===
from .conflict_fix import (
    find_and_fix_conflicts,
    overlap_q,
)

__all__ = [
    # 通知
    "send_notification",
    "notify_driver_reservation_approved",
    "notify_admin_about_new_reservation",

    # 冲突检测
    "find_and_fix_conflicts",
    "overlap_q",
]