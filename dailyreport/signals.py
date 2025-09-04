from __future__ import annotations
from datetime import datetime, time as dtime, timedelta
from typing import Optional, Tuple, List
from django.utils import timezone

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.timezone import make_aware, get_current_timezone

from dailyreport.models import DriverDailyReport
from vehicles.models import Reservation

import threading
_SYNC_GUARD = threading.local()
def _in_guard() -> bool:
    return getattr(_SYNC_GUARD, "on", False)
class _Guard:
    def __enter__(self):
        _SYNC_GUARD.on = True
    def __exit__(self, exc_type, exc, tb):
        _SYNC_GUARD.on = False

TZ = get_current_timezone()

def _to_aware(dt: Optional[datetime]) -> Optional[datetime]:
    if not dt:
        return None
    return make_aware(dt, TZ) if dt.tzinfo is None else dt.astimezone(TZ)

def _combine_date_time(d, t, fallback_date=None) -> Optional[datetime]:
    if d is None:
        d = fallback_date
    if d is None or t is None:
        return None
    if not isinstance(t, dtime):
        try:
            t = dtime.fromisoformat(str(t))
        except Exception:
            return None
    return _to_aware(datetime.combine(d, t))

# ---- 通用：把 time/datetime 统一为“带日期的 aware datetime” ----
def _as_aware_datetime(value: datetime | dtime | None, base_date: date | None) -> Optional[datetime]:
    """
    - value 可为 datetime / time / None
    - base_date 用于把 time 组合成 datetime；缺省时用 localdate()
    - 返回：时区 aware 的 datetime；若 value 为 None 返回 None
    """
    if value is None:
        return None

    if base_date is None:
        base_date = timezone.localdate()

    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, dtime):
        dt = datetime.combine(base_date, value)
    else:
        raise TypeError(f"Unsupported type: {type(value)!r}")

    if getattr(settings, "USE_TZ", False):
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt

# ---- 从 Reservation 拿“开始时间”的 datetime 表达 ----
def _reservation_start_dt(r, base_date: date | None) -> Optional[datetime]:
    """
    兼容两种模型设计：
    - 若有 r.start_datetime（DateTimeField），优先用它
    - 否则用 r.date + r.start_time（TimeField）
    都会统一转为 aware datetime
    """
    # 1) 显式的 DateTimeField
    start_dt_field = getattr(r, "start_datetime", None)
    if start_dt_field:
        return _as_aware_datetime(start_dt_field, base_date)

    # 2) date + time
    r_date = getattr(r, "date", None) or base_date
    r_time = getattr(r, "start_time", None)
    if r_time:
        return _as_aware_datetime(r_time, r_date)

    return None

# ---- 你原来的函数：改成安全/稳态版 ----
def _pick_reservation_for_report(rep: "DriverDailyReport") -> Optional["Reservation"]:
    # 司机绑定校验
    if not rep.driver or not getattr(rep.driver, "user", None):
        return None

    qs = (Reservation.objects
          .filter(driver=rep.driver.user, date__lte=rep.date, end_date__gte=rep.date)
          .order_by("date", "start_time"))
    candidates = list(qs[:20])
    if not candidates:
        return None

    base_date = getattr(rep, "date", None) or timezone.localdate()

    # 统一：key_time 为 aware datetime（优先用 clock_in，没有则用当天 10:00）
    key_time = _as_aware_datetime(getattr(rep, "clock_in", None), base_date)
    if key_time is None:
        key_time = _as_aware_datetime(dtime(10, 0), base_date)  # 兜底参考点

    def score(r: "Reservation") -> float:
        # 统一：每个候选的开始时刻也转成 aware datetime；没有就用 key_time 自身
        start_dt = _reservation_start_dt(r, base_date) or key_time
        # 两端都是 aware datetime，可安全做差
        return abs((start_dt - key_time).total_seconds())

    return min(candidates, key=score)

def _get_actual_out_in(res: Reservation) -> Tuple[Optional[datetime], Optional[datetime]]:
    return res.actual_departure, res.actual_return

def _set_actual_out_in(res: Reservation, out_dt: Optional[datetime], in_dt: Optional[datetime]) -> List[str]:
    updated: List[str] = []
    if out_dt is not None:
        out_dt = _to_aware(out_dt)
        if res.actual_departure != out_dt:
            res.actual_departure = out_dt
            updated.append("actual_departure")
    if in_dt is not None:
        in_dt = _to_aware(in_dt)
        if res.actual_return != in_dt:
            res.actual_return = in_dt
            updated.append("actual_return")
    return updated

@receiver(post_save, sender=DriverDailyReport)
def sync_report_to_reservation(sender, instance: DriverDailyReport, **kwargs):
    if _in_guard():
        return
    res = _pick_reservation_for_report(instance)
    if not res:
        return
    with _Guard():
        update_fields = _set_actual_out_in(res, instance.clock_in, instance.clock_out)
        if update_fields:
            res.save(update_fields=update_fields)
