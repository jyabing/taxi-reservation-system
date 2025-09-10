# dailyreport/signals.py
from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from datetime import datetime, date, time as dtime, timedelta
from typing import Optional, Tuple, Any

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import DriverDailyReport

from vehicles.models import ReservationStatus

logger = logging.getLogger(__name__)

# ========= 通用：时间归一化 & 时长计算 =========

def _as_aware_datetime(value: datetime | dtime | None, base_date: date | None) -> Optional[datetime]:
    """
    把 time/datetime 统一成（带日期的）aware datetime；None 原样返回。
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
    兼容两种设计：
    - reservation.start_datetime（DateTimeField）
    - reservation.date + reservation.start_time（TimeField）
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
    在同司机、覆盖 rep.date 的预约中选择：
      1) 尽量同日
      2) 若日报有车，尽量同车
      3) 再用“开始时刻最接近 key_time（clock_in 或 10:00）”打分
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

    # 1) 优先同一天
    same_day = qs.filter(date=rep.date)

    # 2) 若日报有车，优先同车
    veh_id = getattr(rep, "vehicle_id", None)
    if veh_id:
        same_day_same_car = same_day.filter(vehicle_id=veh_id)
        if same_day_same_car.exists():
            qs = same_day_same_car
        elif same_day.exists():
            qs = same_day
    elif same_day.exists():
        qs = same_day

    candidates = list(qs[:20])
    if not candidates:
        return None

    base_date = rep.date
    key_time = _as_aware_datetime(getattr(rep, "clock_in", None), base_date) \
               or _as_aware_datetime(dtime(10, 0), base_date)

    def _score(r) -> float:
        start_dt = _reservation_start_dt(r, base_date) or key_time
        return abs((start_dt - key_time).total_seconds())

    picked = min(candidates, key=_score)
    logger.info("[R->V] pick by score: reservation_id=%s vehicle=%r date=%s~%s",
                getattr(picked, "pk", None),
                getattr(picked, "vehicle_id", None),
                getattr(picked, "date", None),
                getattr(picked, "end_date", None))
    return picked


# ========= 评分（按需扩展，不保存自身，避免递归） =========

def _apply_scores(report: DriverDailyReport) -> None:
    base_date = getattr(report, "date", None)
    hours = _safe_duration_hours(
        getattr(report, "clock_in", None),
        getattr(report, "clock_out", None),
        base_date,
        allow_overnight=True,
    )
    if hasattr(report, "working_hours"):
        setattr(report, "working_hours", hours)


# ========= Guard 兼容垫片（保留这些名字，避免外部 import 失效） =========

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
      with _Guard():  # 旧代码
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
      _in_guard()  # 表示处在任意保护区间
    """
    flags = __get_flags()
    if name is None:
        return bool(flags)
    return name in flags


def _get_actual_out_in(obj: Any) -> Tuple[Optional[datetime], Optional[datetime]]:
    """
    兼容旧外部调用：传入 Report 或 Reservation 都能返回 (depart_dt, return_dt)
    - Report: 用 clock_in / clock_out (+ rep.date)
    - Reservation: 优先 actual_departure / actual_return；退回 start/end (+ date)
    """
    # Report
    if hasattr(obj, "clock_in") or hasattr(obj, "clock_out"):
        base_date = getattr(obj, "date", None)
        depart_dt = _as_aware_datetime(getattr(obj, "clock_in", None), base_date)
        return_dt = _as_aware_datetime(getattr(obj, "clock_out", None), base_date)
        if depart_dt and return_dt and return_dt < depart_dt:
            return_dt = return_dt + timedelta(days=1)
        return depart_dt, return_dt

    # Reservation
    base_date = getattr(obj, "date", None)
    depart_dt = getattr(obj, "actual_departure", None)
    return_dt = getattr(obj, "actual_return", None)
    if not depart_dt:
        # 回退到计划开始
        st = getattr(obj, "start_time", None)
        depart_dt = _as_aware_datetime(st, base_date)
    if not return_dt:
        et = getattr(obj, "end_time", None)
        return_dt = _as_aware_datetime(et, base_date)
    if isinstance(depart_dt, dtime):
        depart_dt = _as_aware_datetime(depart_dt, base_date)
    if isinstance(return_dt, dtime):
        return_dt = _as_aware_datetime(return_dt, base_date)
    if depart_dt and return_dt and return_dt < depart_dt:
        return_dt = return_dt + timedelta(days=1)
    return depart_dt, return_dt


# ========= Report → Reservation 同步（保持“点已完成→写入实际入库+改状态”） =========

@receiver(post_save, sender=DriverDailyReport)
def sync_report_to_reservation(sender, instance: DriverDailyReport, **kwargs):
    """
    日报保存后：
      - clock_in → Reservation.actual_departure
      - clock_out → Reservation.actual_return
      - 若日报勾“已完成”，补全 actual_return（必要时用 now）并把 Reservation.status 改为“已完成”
    """
    rep = instance
    try:
        logger.info(
            "[R->V] report_id=%s date=%s driver=%s completed_flags=%s",
            getattr(rep, "pk", None),
            getattr(rep, "date", None),
            getattr(getattr(rep, "driver", None), "user", None),
            {k: getattr(rep, k, None) for k in ("is_completed", "completed", "is_done", "finished")}
        )

        # 如果是 Reservation→Report 的链路触发，这里退出避免回环
        if _in_guard("sync_reservation_to_report"):
            logger.info("[R->V] skipped due to guard(sync_reservation_to_report)")
            return

        res = _pick_reservation_for_report(rep)
        if not res:
            logger.warning("[R->V] no reservation found for report_id=%s", getattr(rep, "pk", None))
            return

        logger.info("[R->V] picked reservation id=%s status=%r vehicle_id=%r dates=%s~%s",
                    getattr(res, "pk", None), getattr(res, "status", None),
                    getattr(res, "vehicle_id", None),
                    getattr(res, "date", None), getattr(res, "end_date", None))

        # 统一出退勤时间
        base_date = getattr(rep, "date", None)
        depart_dt = _as_aware_datetime(getattr(rep, "clock_in", None), base_date)
        return_dt = _as_aware_datetime(getattr(rep, "clock_out", None), base_date)
        if depart_dt and return_dt and return_dt < depart_dt:
            return_dt += timedelta(days=1)

        # 是否“已完成”
        completed = any(
            getattr(rep, name, False)
            for name in ("is_completed", "completed", "is_done", "finished")
        )

        # 日报勾已完成但没有退勤 → 用现在兜底
        if completed and return_dt is None:
            return_dt = timezone.now()

        logger.info("[R->V] depart_dt=%s return_dt=%s completed=%s", depart_dt, return_dt, completed)

        # ==== 字段名自适应（避免和你模型的实际字段名不一致） ====
        def _first_attr(obj, names):
            for n in names:
                if hasattr(obj, n):
                    return n
            return None

        field_depart = _first_attr(res, ("actual_departure", "actual_out", "actual_departure_datetime"))
        field_return = _first_attr(res, ("actual_return", "actual_in", "actual_return_datetime"))

        fields_to_update = []
        if depart_dt is not None and field_depart:
            setattr(res, field_depart, depart_dt)
            fields_to_update.append(field_depart)
        if return_dt is not None and field_return:
            setattr(res, field_return, return_dt)
            fields_to_update.append(field_return)

        # 同步车辆（预约无车时）
        if getattr(rep, "vehicle_id", None) and getattr(res, "vehicle_id", None) is None:
            res.vehicle_id = rep.vehicle_id
            fields_to_update.append("vehicle_id")

        # ==== 状态值：优先使用常量或从 choices 里反查（不是中文标签） ====
#        if completed and hasattr(res, "status"):
#            target_done = None
            # 常量优先
#            if hasattr(res, "STATUS_COMPLETED"):
#                target_done = getattr(res, "STATUS_COMPLETED")
            # 从 choices 里按标签反查值
#            elif hasattr(type(res), "status") and hasattr(type(res).status, "choices"):
#                for val, label in type(res).status.flatchoices:
#                    if str(label) in ("已完成", "完成", "完了", "Completed", "complete"):
#                        target_done = val
#                        break
#            if target_done is not None and getattr(res, "status", None) != target_done:
#                res.status = target_done
#                fields_to_update.append("status")

        
        # completed 表示“本次流程应判定为完成”
        if completed and hasattr(res, "status"):
            # 预约完成态：项目统一使用 DONE
            if res.status != ReservationStatus.DONE:
                res.status = ReservationStatus.DONE
                fields_to_update.append("status")

        # 同步把日报也设为已完成（条件可按你口径调整）
        if completed and hasattr(report, "status"):
            if report.clock_in and report.clock_out:
                if report.status != DriverDailyReport.STATUS_COMPLETED:
                    report.status = DriverDailyReport.STATUS_COMPLETED
                    # 注意：report 不在 res 的 fields_to_update 里，单独保存或由外层统一保存

        logger.info("[R->V] fields_to_update=%s values=%s",
                    fields_to_update, {f: getattr(res, f, None) for f in fields_to_update})

        if fields_to_update:
            # 用 save(update_fields=...) 保留你在 Reservation.save()/signals 的后续行为
            with _Guard("sync_report_to_reservation"):
                res.save(update_fields=fields_to_update)
            logger.info("[R->V] saved reservation id=%s with fields=%s",
                        getattr(res, "pk", None), fields_to_update)
        else:
            logger.info("[R->V] nothing to update for reservation id=%s", getattr(res, "pk", None))

    except Exception as e:
        logger.exception(
            "sync_report_to_reservation failed for report id=%s: %s",
            getattr(rep, "pk", None), e
        )


# ========= 评分更新（只用 update 落库，避免递归保存） =========

@receiver(post_save, sender=DriverDailyReport)
def score_report(sender, instance: DriverDailyReport, **kwargs):
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
