from __future__ import annotations
from datetime import datetime, time as dtime
from typing import Optional, Tuple, List
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

def _reservation_start_dt(res: Reservation, fallback_date) -> Optional[datetime]:
    if getattr(res, "start_datetime", None):
        return _to_aware(res.start_datetime)
    return _combine_date_time(getattr(res, "date", None), getattr(res, "start_time", None), fallback_date)

def _pick_reservation_for_report(rep: DriverDailyReport) -> Optional[Reservation]:
    if not rep.driver or not getattr(rep.driver, "user", None):
        return None
    qs = (Reservation.objects
          .filter(driver=rep.driver.user, date__lte=rep.date, end_date__gte=rep.date)
          .order_by("date", "start_time"))
    candidates = list(qs[:20])
    if not candidates:
        return None
    key_time = _to_aware(rep.clock_in) or _to_aware(datetime.combine(rep.date, dtime(10, 0)))
    def score(r: Reservation):
        start_dt = _reservation_start_dt(r, rep.date) or key_time
        start_dt = _to_aware(start_dt)
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
