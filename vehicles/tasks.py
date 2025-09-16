import logging
from datetime import datetime, timedelta
from django.utils import timezone
from vehicles.models import Reservation, ReservationStatus

logger = logging.getLogger(__name__)  # ✅ 模块级 logger


def auto_update_reservations():
    now = timezone.now()
    try:
        # 1. 自动取消：开始时间已过1小时还未出库的
        cancel_threshold = now - timedelta(hours=1)
        to_cancel = Reservation.objects.filter(
            status=ReservationStatus.BOOKED,
            actual_departure__isnull=True,
            date__lte=cancel_threshold.date(),
            start_time__lte=cancel_threshold.time()
        )

        for r in to_cancel:
            r.status = ReservationStatus.CANCEL   # ✅ 状态名修正
            r.vehicle.status = 'available'
            r.vehicle.save()
            r.save()
            logger.info("🔁 自动取消预约 ID %s - %s", r.id, r.vehicle.license_plate)

        # 2. 自动延长：结束时间已过30分钟仍未入库的
        extend_threshold = now - timedelta(minutes=30)
        to_extend = Reservation.objects.filter(
            status=ReservationStatus.OUT,         # ✅ 状态名修正
            actual_return__isnull=True,
            end_date__lte=extend_threshold.date(),
            end_time__lte=extend_threshold.time()
        )

        for r in to_extend:
            # 延长当前预约
            combined_end = datetime.combine(r.end_date, r.end_time) + timedelta(minutes=30)
            r.end_time = combined_end.time()
            r.save()
            logger.info("⏩ 自动延长预约 ID %s - %s 到 %s", r.id, r.vehicle.license_plate, r.end_time)

            # 顺延下一个预约（如果有）
            next_res = Reservation.objects.filter(
                vehicle=r.vehicle,
                status=ReservationStatus.BOOKED,
                date__gte=r.date,
                start_time__gte=r.end_time
            ).order_by('date', 'start_time').first()

            if next_res:
                n_start = datetime.combine(next_res.date, next_res.start_time) + timedelta(minutes=30)
                n_end = datetime.combine(next_res.end_date, next_res.end_time) + timedelta(minutes=30)
                next_res.start_time = n_start.time()
                next_res.end_time = n_end.time()
                next_res.save()
                logger.info(
                    "🔄 顺延下个预约 ID %s 到 %s - %s",
                    next_res.id, next_res.start_time, next_res.end_time
                )

    except Exception:
        logger.exception("❌ auto_update_reservations 任务出错")