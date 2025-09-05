from __future__ import annotations
from typing import Optional
from django.db.models.signals import post_save
from django.dispatch import receiver

from vehicles.models import Reservation
from dailyreport.models import DriverDailyReport
from dailyreport.signals import _Guard, _in_guard, _get_actual_out_in  # 复用

def _pick_report_for_reservation(res: Reservation) -> Optional[DriverDailyReport]:
    """根据 Reservation 找到对应的 DriverDailyReport"""
    if not res.driver:
        return None
    qs = (
        DriverDailyReport.objects
        .filter(driver__user=res.driver, date__gte=res.date, date__lte=res.end_date)
        .order_by("date")
    )
    if not qs.exists():
        return None
    # 优先同一天的日报
    same_day = qs.filter(date=res.date).first()
    return same_day or qs.first()


@receiver(post_save, sender=Reservation)
def sync_reservation_to_report(sender, instance: Reservation, **kwargs):
    """
    当 Reservation 保存时，自动同步到 DriverDailyReport：
    - actual_departure → clock_in
    - actual_return → clock_out
    """
    # ✅ 使用带名字的 guard，避免和 dailyreport.signals 循环触发
    if _in_guard("sync_reservation_to_report"):
        return

    rep = _pick_report_for_reservation(instance)
    if not rep:
        return

    # _get_actual_out_in 会返回 (actual_departure_dt, actual_return_dt)，已处理跨午夜
    out_dt, in_dt = _get_actual_out_in(instance)

    changed = False
    with _Guard("sync_reservation_to_report"):
        if out_dt and rep.clock_in != out_dt:
            rep.clock_in = out_dt
            changed = True
        if in_dt and rep.clock_out != in_dt:
            rep.clock_out = in_dt
            changed = True
        if changed:
            rep.save(update_fields=["clock_in", "clock_out"])