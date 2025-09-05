# vehicles/signals.py
from __future__ import annotations
from typing import Optional
from django.db.models.signals import post_save
from django.dispatch import receiver

from vehicles.models import Reservation
from dailyreport.models import DriverDailyReport
from dailyreport.signals import _Guard, _in_guard, _get_actual_out_in  # 复用


def _pick_report_for_reservation(res: Reservation) -> Optional[DriverDailyReport]:
    """根据 Reservation 找到对应的 DriverDailyReport（优先同日）"""
    if not res.driver:
        return None
    qs = (
        DriverDailyReport.objects
        .filter(driver__user=res.driver, date__gte=res.date, date__lte=res.end_date)
        .order_by("date")
    )
    if not qs.exists():
        return None
    same_day = qs.filter(date=res.date).first()
    return same_day or qs.first()


@receiver(post_save, sender=Reservation)
def sync_reservation_to_report(sender, instance: Reservation, **kwargs):
    """
    Reservation 保存后同步到日报：
      - actual_departure → clock_in
      - actual_return → clock_out
    """
    # 防环：如果是 Report→Reservation 的链路触发，这里退出
    if _in_guard("sync_report_to_reservation"):
        return

    rep = _pick_report_for_reservation(instance)
    if not rep:
        return

    out_dt, in_dt = _get_actual_out_in(instance)  # 已兼容 Reservation 类型

    changed = False
    with _Guard("sync_reservation_to_report"):
        if out_dt and getattr(rep, "clock_in", None) != out_dt:
            rep.clock_in = out_dt
            changed = True
        if in_dt and getattr(rep, "clock_out", None) != in_dt:
            rep.clock_out = in_dt
            changed = True
        if changed:
            rep.save(update_fields=["clock_in", "clock_out"])
