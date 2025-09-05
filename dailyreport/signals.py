# dailyreport/signals.py
from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from datetime import datetime, date, time as dtime, timedelta
from typing import Optional

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import DriverDailyReport

logger = logging.getLogger(__name__)

# ========= 通用工具函数（省略，与之前一样） =========
# _as_aware_datetime, _safe_duration_hours, _reservation_start_dt, _pick_reservation_for_report, _apply_scores


# ========= Guard 兼容垫片 =========
__guard_flags = threading.local()

def __get_flags():
    if not hasattr(__guard_flags, "flags"):
        __guard_flags.flags = set()
    return __guard_flags.flags

@contextmanager
def _Guard(name: str | None = None):
    flags = __get_flags()
    key = name or "__default__"
    entered = key in flags
    flags.add(key)
    try:
        yield
    finally:
        if not entered:
            flags.discard(key)

def _in_guard(name: str | None = None) -> bool:
    flags = __get_flags()
    if name is None:
        return bool(flags)
    return name in flags

def _get_actual_out_in(rep) -> tuple[Optional[datetime], Optional[datetime]]:
    base_date = getattr(rep, "date", None)
    depart_dt = _as_aware_datetime(getattr(rep, "clock_in", None), base_date)
    return_dt = _as_aware_datetime(getattr(rep, "clock_out", None), base_date)
    if depart_dt and return_dt and return_dt < depart_dt:
        return_dt = return_dt + timedelta(days=1)
    return depart_dt, return_dt


# ========= 信号处理 =========

@receiver(post_save, sender=DriverDailyReport)
def sync_report_to_reservation(sender, instance: DriverDailyReport, **kwargs):
    """
    日报保存后 → 更新 Reservation
    - clock_in → actual_departure
    - clock_out → actual_return
    """
    rep = instance
    try:
        # ✅ 使用命名 guard，避免和 vehicles/signals 的 guard 冲突
        if _in_guard("sync_reservation_to_report"):
            return

        from vehicles.models import Reservation
        res = _pick_reservation_for_report(rep)
        if not res:
            return

        base_date = getattr(rep, "date", None)
        depart_dt = _as_aware_datetime(getattr(rep, "clock_in", None), base_date)
        return_dt = _as_aware_datetime(getattr(rep, "clock_out", None), base_date)

        if depart_dt and return_dt and return_dt < depart_dt:
            return_dt += timedelta(days=1)

        update_map = {}
        if depart_dt is not None and hasattr(res, "actual_departure"):
            update_map["actual_departure"] = depart_dt
        if return_dt is not None and hasattr(res, "actual_return"):
            update_map["actual_return"] = return_dt
        if getattr(rep, "vehicle_id", None) and getattr(res, "vehicle_id", None) is None:
            update_map["vehicle_id"] = rep.vehicle_id

        if update_map:
            with _Guard("sync_report_to_reservation"):
                Reservation.objects.filter(pk=res.pk).update(**update_map)

    except Exception as e:
        logger.exception(
            "sync_report_to_reservation failed for report id=%s: %s",
            getattr(rep, "pk", None), e
        )


@receiver(post_save, sender=DriverDailyReport)
def score_report(sender, instance: DriverDailyReport, **kwargs):
    """日报保存后，应用打分/统计"""
    rep = instance
    try:
        _apply_scores(rep)
        update_map = {}
        if hasattr(rep, "working_hours"):
            update_map["working_hours"] = getattr(rep, "working_hours")

        if update_map:
            DriverDailyReport.objects.filter(pk=rep.pk).update(**update_map)

    except Exception as e:
        logger.exception(
            "score_report failed for report id=%s: %s",
            getattr(rep, "pk", None), e
        )
