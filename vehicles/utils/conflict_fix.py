# vehicles/utils/conflict_fix.py
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from vehicles.models import Reservation, ReservationStatus

CONFLICT_STATUSES = [ReservationStatus.PENDING, ReservationStatus.BOOKED, ReservationStatus.OUT]

def overlap_q(start_date, start_time, end_date, end_time):
    """
    半开区间重叠： [date+start_time, end_date+end_time)
    """
    return (
        Q(date__lte=end_date) & Q(end_date__gte=start_date) &
        Q(start_time__lt=end_time) & Q(end_time__gt=start_time)
    )

def find_and_fix_conflicts(commit=False):
    """
    扫描“同车、同时间段、不同司机”的冲突预约。
    规则：保留“先创建”的记录，取消“后创建”的记录（status='canceled'）。

    返回:
      {
        "conflicts": int,     # 发现的冲突对数（计数对数）
        "fixed": int,         # 实际取消的条数
        "samples": [ { vehicle, date, time, driver1, driver2, winner_id, canceled_id }, ... ]  # 最多 50 条预览
      }
    """
    conflict_pairs = 0
    fixed = 0
    samples = []

    # 先取“可能参与冲突”的记录（减少扫描量）
    qs_all = (
        Reservation.objects
        .filter(status__in=CONFLICT_STATUSES)
        .select_related("vehicle", "driver")
        .order_by("vehicle_id", "date", "start_time", "created_at", "id")
    )

    # 按车分组
    from itertools import groupby
    for vid, group in groupby(qs_all, key=lambda r: r.vehicle_id):
        group_list = list(group)
        # 逐条与后面的记录比较（同车）
        for i, r1 in enumerate(group_list):
            for r2 in group_list[i+1:]:
                # 快速剪枝：不同日期范围可能不重叠
                if r1.end_date < r2.date or r2.end_date < r1.date:
                    continue
                # 时间重叠 + 不同司机
                if (r1.driver_id != r2.driver_id
                    and r1.status in CONFLICT_STATUSES and r2.status in CONFLICT_STATUSES
                    and r1.start_time < r2.end_time and r1.end_time > r2.start_time):
                    conflict_pairs += 1

                    # 谁先创建
                    older, newer = (r1, r2) if (r1.created_at, r1.id) <= (r2.created_at, r2.id) else (r2, r1)

                    if commit:
                        if newer.status != "canceled":
                            newer.status = "canceled"
                            newer.save(update_fields=["status"])
                            fixed += 1

                    # 收集样本（最多 50 条）
                    if len(samples) < 50:
                        samples.append({
                            "vehicle": getattr(r1.vehicle, "license_plate", str(r1.vehicle_id)),
                            "date": f"{r1.date}~{r1.end_date}",
                            "time": f"{r1.start_time}-{r1.end_time} / {r2.start_time}-{r2.end_time}",
                            "driver1": str(r1.driver) if r1.driver_id else "-",
                            "driver2": str(r2.driver) if r2.driver_id else "-",
                            "winner_id": older.id,
                            "canceled_id": newer.id if commit else None,
                        })

    return {"conflicts": conflict_pairs, "fixed": fixed, "samples": samples}
