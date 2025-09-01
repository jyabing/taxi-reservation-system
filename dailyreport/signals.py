# dailyreport/signals.py
from __future__ import annotations
from datetime import datetime, time as dtime
from typing import Optional, Tuple, List
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.timezone import make_aware, get_current_timezone

from dailyreport.models import DriverDailyReport
from vehicles.models import Reservation

# ---------- 防循环保护 ----------
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

# ---------- 工具：读/写 Reservation 的“实际出/入库” ----------
def _dt(date_field, time_field) -> Optional[datetime]:
    if not date_field or time_field is None:
        return None
    dt = datetime.combine(date_field, time_field if isinstance(time_field, dtime) else dtime.fromisoformat(str(time_field)))
    try:
        return make_aware(dt, TZ) if dt.tzinfo is None else dt
    except Exception:
        return dt

def _get_actual_out_in(res: Reservation) -> Tuple[Optional[datetime], Optional[datetime]]:
    """
    兼容两种模型：
    1) 单字段：actual_departure_at / actual_return_at (DateTimeField)
    2) 拆分：actual_out_date + actual_out_time / actual_in_date + actual_in_time
    """
    if hasattr(res, "actual_departure_at") or hasattr(res, "actual_return_at"):
        out_dt = getattr(res, "actual_departure_at", None)
        in_dt  = getattr(res, "actual_return_at", None)
        return out_dt, in_dt

    # 拆分字段（从你截图推测）
    out_dt = _dt(getattr(res, "actual_out_date", None), getattr(res, "actual_out_time", None))
    in_dt  = _dt(getattr(res, "actual_in_date",  None), getattr(res, "actual_in_time",  None))
    return out_dt, in_dt

def _set_actual_out_in(res: Reservation, out_dt: Optional[datetime], in_dt: Optional[datetime]) -> List[str]:
    """
    反向写入 Reservation，返回需要 update 的字段列表
    """
    updated: List[str] = []
    if hasattr(res, "actual_departure_at") or hasattr(res, "actual_return_at"):
        if out_dt is not None and getattr(res, "actual_departure_at", None) != out_dt:
            setattr(res, "actual_departure_at", out_dt); updated.append("actual_departure_at")
        if in_dt is not None and getattr(res, "actual_return_at", None) != in_dt:
            setattr(res, "actual_return_at", in_dt); updated.append("actual_return_at")
        return updated

    # 拆分字段
    def _split(dt: Optional[datetime]):
        if not dt:
            return None, None
        local = dt.astimezone(TZ) if dt.tzinfo else dt
        return local.date(), local.timetz() if hasattr(local, "timetz") else local.time()

    if out_dt is not None:
        d, t = _split(out_dt)
        if d is not None and getattr(res, "actual_out_date", None) != d:
            setattr(res, "actual_out_date", d); updated.append("actual_out_date")
        if t is not None and getattr(res, "actual_out_time", None) != t:
            setattr(res, "actual_out_time", t); updated.append("actual_out_time")

    if in_dt is not None:
        d, t = _split(in_dt)
        if d is not None and getattr(res, "actual_in_date", None) != d:
            setattr(res, "actual_in_date", d); updated.append("actual_in_date")
        if t is not None and getattr(res, "actual_in_time", None) != t:
            setattr(res, "actual_in_time", t); updated.append("actual_in_time")

    return updated

# ---------- 选择与日报匹配的预约 ----------
def _pick_reservation_for_report(rep: DriverDailyReport) -> Optional[Reservation]:
    """
    需求：同司机 & 覆盖 rep.date 当天的预约；
    若有多条，取最接近 rep.clock_in 的一条；若 clock_in 为空，则取开始时间最接近 10:00 的一条。
    """
    if not rep.driver or not getattr(rep.driver, "user", None):
        return None
    qs = (Reservation.objects
          .filter(driver=rep.driver.user, date__lte=rep.date, end_date__gte=rep.date)
          .order_by("date", "start_time"))
    candidates = list(qs[:5])
    if not candidates:
        return None
    key_time = rep.clock_in or make_aware(datetime.combine(rep.date, dtime(10, 0)), TZ)
    def score(r: Reservation):
        start_dt = make_aware(datetime.combine(r.date, r.start_time), TZ) if getattr(r, "start_time", None) else key_time
        return abs((start_dt - key_time).total_seconds())
    return sorted(candidates, key=score)[0]

# ---------- 从日报同步到预约 ----------
@receiver(post_save, sender=DriverDailyReport)
def sync_report_to_reservation(sender, instance: DriverDailyReport, **kwargs):
    if _in_guard():
        return
    res = _pick_reservation_for_report(instance)
    if not res:
        return

    with _Guard():
        # 把日报 clock_in / clock_out 写到 Reservation 的实际出/入库
        out_dt = instance.clock_in
        in_dt  = instance.clock_out
        update_fields = _set_actual_out_in(res, out_dt, in_dt)
        if update_fields:
            res.save(update_fields=update_fields)
