# vehicles/signals.py
from __future__ import annotations
from django.db.models.signals import post_save
from django.dispatch import receiver

from vehicles.models import Reservation
from dailyreport.models import DriverDailyReport
from dailyreport.signals import _Guard, _in_guard, _get_actual_out_in  # 复用工具

def _pick_report_for_reservation(res: Reservation) -> DriverDailyReport | None:
    """
    同司机 & 覆盖预约 date..end_date 期间的日报（通常同一天）。
    若多条，以 res.date 当天为第一选择。
    """
    if not res.driver:
        return None
    qs = (DriverDailyReport.objects
          .filter(driver__user=res.driver, date__gte=res.date, date__lte=res.end_date)
          .order_by("date"))
    if not qs.exists():
        return None
    # 优先同一天
    same_day = qs.filter(date=res.date).first()
    return same_day or qs.first()

@receiver(post_save, sender=Reservation)
def sync_reservation_to_report(sender, instance: Reservation, **kwargs):
    if _in_guard():
        return
    rep = _pick_report_for_reservation(instance)
    if not rep:
        return

    out_dt, in_dt = _get_actual_out_in(instance)

    changed = False
    with _Guard():
        if out_dt and rep.clock_in != out_dt:
            rep.clock_in = out_dt; changed = True
        if in_dt and rep.clock_out != in_dt:
            rep.clock_out = in_dt; changed = True
        if changed:
            rep.save(update_fields=["clock_in", "clock_out"])
