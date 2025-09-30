# vehicles/utils_reservation.py
from contextlib import contextmanager
from datetime import datetime
from django.db import transaction
from django.db.models import Q
from .models import Reservation, ReservationStatus


def time_ranges_overlap(start_time_a, end_time_a, start_time_b, end_time_b) -> bool:
    """
    仅比较时间（不含日期）的区间交叠：A 与 B 是否有交集？
    交叠条件：A.start < B.end 且 A.end > B.start
    """
    return (start_time_a < end_time_b) and (end_time_a > start_time_b)


def has_conflict(vehicle, start_date, end_date, start_time, end_time, *, exclude_id=None,
                 status_scope=None) -> bool:
    """
    以【日期跨天 + 时间段】为口径，检查该 vehicle 是否与现有记录冲突。
    - 会匹配到覆盖 start_date~end_date 的所有预约；
    - 再用时间段重叠规则过滤；
    - 可通过 exclude_id 排除正在编辑的同一条；
    - status_scope 缺省为 PENDING/BOOKED/OUT（审批时可缩小到 BOOKED/OUT）。
    """
    if status_scope is None:
        status_scope = [ReservationStatus.PENDING, ReservationStatus.BOOKED, ReservationStatus.OUT]

    qs = Reservation.objects.filter(
        vehicle=vehicle,
        date__lte=end_date,
        end_date__gte=start_date,
        status__in=status_scope,
    )

    if exclude_id:
        qs = qs.exclude(id=exclude_id)

    # 仅保留“时间段相交”的记录
    qs = qs.filter(
        Q(start_time__lt=end_time) & Q(end_time__gt=start_time)
    )

    return qs.exists()


@contextmanager
def lock_vehicle_reservations(vehicle):
    """
    给某辆车的预约集合加行级锁，避免并发插入/审批造成数据竞态。
    用法：
        with lock_vehicle_reservations(vehicle):
            # 这里做冲突检查与写入
    """
    with transaction.atomic():
        # 行级锁：不同数据库后端兼容性略有差异；即便被忽略也不影响事务隔离保障
        Reservation.objects.select_for_update().filter(vehicle=vehicle)
        yield
