# vehicles/tasks.py
import datetime
from datetime import timedelta
from django.utils import timezone
from django.db.models import Q
from vehicles.models import Reservation


def auto_update_reservations():
    now = timezone.now()

    # ✅ 自动取消：开始时间已过1小时还未出库的
    cancel_threshold = now - timedelta(hours=1)
    to_cancel = Reservation.objects.filter(
        status='reserved',
        actual_departure__isnull=True,
        date__lte=cancel_threshold.date(),
        start_time__lte=cancel_threshold.time()
    )

    for r in to_cancel:
        r.status = 'canceled'
        r.save()
        print(f"🔁 自动取消预约 ID {r.id} - {r.vehicle.license_plate}")

    # ✅ 自动延长：结束时间已过30分钟仍未入库的
    extend_threshold = now - timedelta(minutes=30)
    to_extend = Reservation.objects.filter(
        status='out',
        actual_return__isnull=True,
        end_date__lte=extend_threshold.date(),
        end_time__lte=extend_threshold.time()
    )

    for r in to_extend:
        r.end_time = (datetime.combine(r.end_date, r.end_time) + timedelta(minutes=30)).time()
        r.save()
        print(f"⏩ 自动延长预约 ID {r.id} - {r.vehicle.license_plate} 到 {r.end_time}")

        # ✅ 如果有下一条预约，顺延其开始时间
        next_res = Reservation.objects.filter(
            vehicle=r.vehicle,
            date__gte=r.date,
            start_time__gte=r.end_time,
            status='reserved'
        ).order_by('date', 'start_time').first()

        if next_res:
            next_start = datetime.combine(next_res.date, next_res.start_time) + timedelta(minutes=30)
            next_end = datetime.combine(next_res.end_date, next_res.end_time) + timedelta(minutes=30)
            next_res.start_time = next_start.time()
            next_res.end_time = next_end.time()
            next_res.save()
            print(f"🔄 顺延下个预约 ID {next_res.id} 到 {next_res.start_time} - {next_res.end_time}")