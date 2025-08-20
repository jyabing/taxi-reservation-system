from datetime import datetime, timedelta
from django.utils import timezone
from vehicles.models import Reservation, ReservationStatus


def auto_update_reservations():
    """
    定时任务：自动更新预约状态
    - 未出库且已到开始时间 → 仍保持 BOOKED（不改）
    - 已到开始时间且出库登记 → DEPARTED
    - 已到结束时间且已入库 → COMPLETED
    - 已到结束时间但未出库 → CANCELED
    """
    now = timezone.now()
    today = now.date()

    # 处理已到期未出库 → CANCELED
    for r in Reservation.objects.filter(
        status=ReservationStatus.BOOKED,
        actual_departure__isnull=True,
        end_datetime__lt=now
    ):
        r.status = ReservationStatus.CANCELED
        r.save()

    # 处理已出库但未归还 → DEPARTED
    for r in Reservation.objects.filter(
        status=ReservationStatus.BOOKED,
        actual_departure__isnull=False,
        actual_return__isnull=True
    ):
        r.status = ReservationStatus.DEPARTED
        r.save()

    # 处理已完成 → COMPLETED
    for r in Reservation.objects.filter(
        status__in=[ReservationStatus.BOOKED, ReservationStatus.DEPARTED],
        actual_departure__isnull=False,
        actual_return__isnull=False
    ):
        r.status = ReservationStatus.COMPLETED
        r.save()
