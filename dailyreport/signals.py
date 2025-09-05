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

from .models import DriverDailyReport  # 日报模型

logger = logging.getLogger(__name__)


# ========= 通用：时间归一化 & 时长计算 =========

def _as_aware_datetime(value: datetime | dtime | None, base_date: date | None) -> Optional[datetime]:
    """
    把 time/datetime 统一成（带日期的）aware datetime；None 原样返回。
    - value: datetime 或 time 或 None
    - base_date: 用于把 time 组合成 datetime；缺省使用本地当前日期
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
        raise TypeError(f"Unsupported type for datetime normalization: {type(value)!r}")

    if getattr(settings, "USE_TZ", False) and timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _safe_duration_hours(start_v, end_v, base_date: date | None, allow_overnight: bool = True) -> Optional[float]:
    """
    计算时长（小时）。任一端缺失返回 None。
    - start_v / end_v: datetime 或 time 或 None
    - base_date: 若传入 time，使用该日期进行组合
    - allow_overnight: True 时，end < start 视为跨午夜 +1 天
    """
    start_dt = _as_aware_datetime(start_v, base_date)
    end_dt = _as_aware_datetime(end_v, base_date)
    if start_dt is None or end_dt is None:
        return None
    if allow_overnight and end_dt < start_dt:
        end_dt += timedelta(days=1)
    return (end_dt - start_dt).total_seconds() / 3600.0


# ========= Reservation 相关辅助 =========

def _reservation_start_dt(reservation, base_date: date | None) -> Optional[datetime]:
    """
    从 Reservation 拿“开始时刻”的 datetime 表达（aware）。
    兼容两种设计：
    - 若有 reservation.start_datetime（DateTimeField），优先用它
    - 否则用 reservation.date + reservation.start_time（TimeField）
    """
    start_dt_field = getattr(reservation, "start_datetime", None)
    if start_dt_field:
        return _as_aware_datetime(start_dt_field, base_date)

    r_date = getattr(reservation, "date", None) or base_date
    r_time = getattr(reservation, "start_time", None)
    if r_time:
        return _as_aware_datetime(r_time, r_date)

    return None


def _pick_reservation_for_report(rep: DriverDailyReport) -> Optional["Reservation"]:
    """
    在同司机、覆盖 rep.date 的预约中，选“开始时刻最接近 key_time”的一条。
    key_time 优先用 rep.clock_in；否则用当日 10:00。
    """
    driver = getattr(getattr(rep, "driver", None), "user", None)
    if not driver or not getattr(rep, "date", None):
        return None

    from vehicles.models import Reservation  # 延迟导入，避免循环依赖

    qs = (
        Reservation.objects
        .filter(driver=driver, date__lte=rep.date, end_date__gte=rep.date)
        .order_by("date", "start_time")
    )
    candidates = list(qs[:20])
    if not candidates:
        return None

    base_date = rep.date
    key_time = _as_aware_datetime(getattr(rep, "clock_in", None), base_date)
    if key_time is None:
        key_time = _as_aware_datetime(dtime(10, 0), base_date)  # 兜底参考点

    def _score(r) -> float:
        start_dt = _reservation_start_dt(r, base_date) or key_time
        return abs((start_dt - key_time).total_seconds())

    return min(candidates, key=_score)


# ========= 业务：打分 / 统计（示例，可按需扩展） =========

def _apply_scores(report: DriverDailyReport) -> None:
    """
    示例：计算工时等。只修改内存对象，不直接保存，避免递归。
    若模型没有对应字段，自动跳过。
    """
    base_date = getattr(report, "date", None)

    hours = _safe_duration_hours(
        getattr(report, "clock_in", None),
        getattr(report, "clock_out", None),
        base_date,
        allow_overnight=True,
    )
    if hasattr(report, "working_hours"):
        setattr(report, "working_hours", hours)


# ========= 兼容垫片：供 vehicles.signals 继续 import =========
# 作用：
# - _Guard / _in_guard：简单的重入保护，避免信号相互触发导致递归
# - _get_actual_out_in：旧代码兼容，统一给出 (actual_departure_dt, actual_return_dt)

__guard_flags = threading.local()

def __get_flags():
    if not hasattr(__guard_flags, "flags"):
        __guard_flags.flags = set()
    return __guard_flags.flags

@contextmanager
def _Guard(name: str | None = None):
    """
    兼容两种用法：
        with _Guard("sync_report_to_reservation"):
            ...
        with _Guard():  # 旧代码可能这么写
            ...
    """
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
    """
    兼容两种用法：
        _in_guard("sync_reservation_to_report")
        _in_guard()   # 无参时表示：处在任意保护区间
    """
    flags = __get_flags()
    if name is None:
        return bool(flags)
    return name in flags

def _get_actual_out_in(rep) -> tuple[Optional[datetime], Optional[datetime]]:
    """
    旧代码兼容：从日报对象上推导 (actual_departure_dt, actual_return_dt)
    - 允许 clock_in/clock_out 为 TimeField 或 DateTimeField
    - 与 rep.date 组合成 aware datetime
    - 处理跨午夜（return < depart 则 +1 天）
    """
    base_date = getattr(rep, "date", None)
    depart_dt = _as_aware_datetime(getattr(rep, "clock_in", None), base_date)
    return_dt = _as_aware_datetime(getattr(rep, "clock_out", None), base_date)
    if depart_dt and return_dt and return_dt < depart_dt:
        return_dt = return_dt + timedelta(days=1)
    return depart_dt, return_dt


# ========= 信号处理：保存日报后与预约同步 =========

@receiver(post_save, sender=DriverDailyReport)
def sync_report_to_reservation(sender, instance: DriverDailyReport, **kwargs):
    """
    日报保存后：
    - 尝试找到对应 Reservation
    - 将 clock_in/clock_out 写入 Reservation.actual_departure / actual_return（DateTimeField）
    - 同步车辆（如果日报上有、且 Reservation 为空）
    用 QuerySet.update() 落库，避免不必要的信号递归。
    """
    rep = instance
    try:
        # 重入保护（可选，若与 vehicles.signals 有互相触发的情况）
        with _Guard("sync_report_to_reservation"):
            if _in_guard("sync_reservation_to_report"):  # 若对方也有保护名，可避免循环
                return

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

            rep_vehicle_id = getattr(rep, "vehicle_id", None)
            if rep_vehicle_id and hasattr(res, "vehicle_id") and getattr(res, "vehicle_id", None) is None:
                update_map["vehicle_id"] = rep_vehicle_id

            if update_map:
                from vehicles.models import Reservation  # 延迟导入
                Reservation.objects.filter(pk=res.pk).update(**update_map)

    except Exception as e:
        logger.exception(
            "sync_report_to_reservation failed for report id=%s: %s",
            getattr(rep, "pk", None), e
        )


@receiver(post_save, sender=DriverDailyReport)
def score_report(sender, instance: DriverDailyReport, **kwargs):
    """
    日报保存后应用打分/统计。
    仅使用 update() 将结果落库，避免递归保存。
    """
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
