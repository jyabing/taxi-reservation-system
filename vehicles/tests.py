# vehicles/tasks.py
from __future__ import annotations

from django.utils import timezone
from django.db import transaction
from vehicles.models import Reservation, ReservationStatus  # ✅ 关键修复：导入枚举

def _now():
    return timezone.now()

@transaction.atomic
def auto_update_reservations():
    """
    周期任务（APS cheduler 调用）：
    - 已到开始时间但仍 BOOKED 且无实际出库 -> 取消（CANCELED）
    - 已到开始时间且 BOOKED -> 标记已出库（DEPARTED/OUT）
    - 已到结束时间，且状态在进行中 -> 标记完成（COMPLETED）
    说明：
      你的项目里存在 DEPARTED/OUT/COMPLETED/CANCELED 等状态，以下逻辑参考你仓内的
      management/scheduler.py & management/commands/*.py 的写法，尽量对齐。
    """
    now = _now()

    # 1) 超时未出库的预约 -> 取消
    overdue_qs = Reservation.objects.select_for_update().filter(
        status=ReservationStatus.BOOKED,
        actual_departure__isnull=True,
        start_datetime__lt=now,
    )
    for r in overdue_qs:
        r.status = ReservationStatus.CANCELED
        r.save(update_fields=["status"])

    # 2) 到点了仍 BOOKED 的 -> 视为已出库（部分项目用 DEPARTED，有的用 OUT，择其一）
    to_depart_qs = Reservation.objects.select_for_update().filter(
        status=ReservationStatus.BOOKED,
        start_datetime__lte=now,
        actual_departure__isnull=False,  # 如果你的逻辑是“有 actual_departure 就算出库”，保留
    )
    for r in to_depart_qs:
        # 你的项目里既有 DEPARTED 也有 OUT 的使用痕迹；优先使用你 tasks.py 里正在使用的状态。
        r.status = ReservationStatus.DEPARTED if hasattr(ReservationStatus, "DEPARTED") else ReservationStatus.OUT
        r.save(update_fields=["status"])

    # 3) 到了结束时间，仍在进行中的 -> 完成
    in_progress_status = []
    # 兼容两种命名：DEPARTED / OUT
    if hasattr(ReservationStatus, "DEPARTED"):
        in_progress_status.append(ReservationStatus.DEPARTED)
    if hasattr(ReservationStatus, "OUT"):
        in_progress_status.append(ReservationStatus.OUT)
    # 也把 BOOKED 兜进去（防止遗漏）
    in_progress_status.append(ReservationStatus.BOOKED)

    to_complete_qs = Reservation.objects.select_for_update().filter(
        status__in=in_progress_status,
        end_datetime__lte=now,
    )
    for r in to_complete_qs:
        r.status = ReservationStatus.COMPLETED
        r.save(update_fields=["status"])
