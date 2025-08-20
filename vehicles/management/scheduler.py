import datetime
from django.utils import timezone
from vehicles.models import Reservation

def run_scheduled_tasks():
    now = timezone.now()

    # 1️⃣ 自动取消未出库预约：预约已开始 1 小时内未出库，则取消
    one_hour_ago = now - datetime.timedelta(hours=1)
    stale = Reservation.objects.filter(
        status=ReservationStatus.BOOKED,
        actual_departure__isnull=True,
        date__lte=one_hour_ago.date(),
        start_time__lte=one_hour_ago.time()
    )
    for r in stale:
        r.status = 'canceled'
        r.save()
        print(f"✅ 已取消未出库预约：{r}")

    # 2️⃣ 自动延长未还车预约：预约结束已过 30 分钟，但仍未还车，延后 30 分钟
    thirty_mins_ago = now - datetime.timedelta(minutes=30)
    active = Reservation.objects.filter(
        status__in=[ReservationStatus.BOOKED, ReservationStatus.DEPARTED],
        actual_departure__isnull=False,
        actual_return__isnull=True,
        end_date__lt=now.date()
    ) | Reservation.objects.filter(
        status__in=[ReservationStatus.BOOKED, ReservationStatus.DEPARTED],
        actual_departure__isnull=False,
        actual_return__isnull=True,
        end_date=now.date(),
        end_time__lte=thirty_mins_ago.time()
    )

    for r in active:
        new_end = datetime.datetime.combine(r.end_date, r.end_time) + datetime.timedelta(minutes=30)
        r.end_date = new_end.date()
        r.end_time = new_end.time()
        r.save()
        print(f"⏩ 已自动延后预约：{r}")
