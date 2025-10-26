# analysis/views.py
from __future__ import annotations

from datetime import date, datetime, timedelta
from collections import defaultdict

from django.db.models.functions import Coalesce

from django.db import models
from django.db.models import F, Sum, DurationField, ExpressionWrapper, Q, Case, When, Value, FloatField
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.timezone import get_current_timezone
from django.contrib.auth.decorators import login_required
import csv

# 按你的 app 实际情况调整
from dailyreport.models import DriverDailyReport
from carinfo.models import Car as Vehicle  # 若你的车辆模型不是 Car，请改为 Vehicle

TZ = get_current_timezone()


def _parse_date(q: str | None, default: date) -> date:
    if not q:
        return default
    try:
        return datetime.strptime(q, "%Y-%m-%d").date()
    except Exception:
        return default


def _end_of_month(d: date) -> date:
    """返回 d 所在月份的最后一天"""
    first_next = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return first_next - timedelta(days=1)


def _daterange(d1: date, d2: date):
    cur = d1
    while cur <= d2:
        yield cur
        cur = cur + timedelta(days=1)


def _model_has_field(model_cls, field_name: str) -> bool:
    return field_name in {f.name for f in model_cls._meta.get_fields()}


def _vehicle_label(vdict: dict) -> str:
    return (
        vdict.get("license_plate")
        or vdict.get("registration_number")
        or vdict.get("name")
        or f"Vehicle#{vdict.get('id')}"
    )


def _compute_vehicle_idle(d_from: date, d_to: date):
    """核心计算：返回 rows 列表与 total_days"""
    # 车辆集合（若有 status 字段，排除报废/退役等）
    vehicle_qs = Vehicle.objects.all()
    if _model_has_field(Vehicle, "status"):
        # 你项目里的停用状态值若不同，在此调整
        vehicle_qs = vehicle_qs.exclude(status__in=["retired", "scrapped"])

    # 一次取出可能作为显示名的字段
    vehicles = list(
        vehicle_qs.values("id", "license_plate", "registration_number", "name")
    )

    # 报表区间内的日报聚合（每车每日工时）
    reports = (
        DriverDailyReport.objects
        .filter(date__gte=d_from, date__lte=d_to)
        .values("vehicle_id", "date")
        .annotate(
            # 仅当 clock_in 和 clock_out 都不为空时计算差值，否则记 0
            work_time=Sum(
                Case(
                    When(
                        clock_in__isnull=False,
                        clock_out__isnull=False,
                        then=ExpressionWrapper(
                            F("clock_out") - F("clock_in"),
                            output_field=DurationField()
                        )
                    ),
                    default=Value(timedelta(0)),
                    output_field=DurationField(),
                )
            )
        )
    )

    # 预计算：vehicle_id -> {date: hours}
    per_vehicle_day_hours = defaultdict(lambda: defaultdict(float))
    for r in reports:
        vid = r["vehicle_id"]
        d = r["date"]
        seconds = (r["work_time"] or timedelta()).total_seconds()
        hours = max(0.0, seconds / 3600.0)
        per_vehicle_day_hours[vid][d] += hours

    all_days = list(_daterange(d_from, d_to))
    total_days_in_range = len(all_days)

    result_rows = []
    for v in vehicles:
        vid = v["id"]
        label = _vehicle_label(v)

        # 若有维修日历，可在这里计算不可用天数并扣减
        unavailable_days = 0
        available_days = max(0, total_days_in_range - unavailable_days)

        active_days = 0
        total_hours = 0.0

        if available_days > 0:
            day_map = per_vehicle_day_hours.get(vid, {})
            for d in all_days:
                h = day_map.get(d, 0.0)
                if h > 0.0:
                    active_days += 1
                    total_hours += h

            utilization = (active_days / available_days) if available_days else 0.0
            idle_rate = 1.0 - utilization
            avg_hours_if_active = (total_hours / active_days) if active_days else 0.0
        else:
            utilization = 0.0
            idle_rate = 0.0
            avg_hours_if_active = 0.0

        result_rows.append({
            "vehicle_id": vid,
            "label": label,                 # 统一显示名
            "available_days": available_days,
            "active_days": active_days,
            "total_hours": round(total_hours, 2),
            "utilization": round(utilization, 4),  # 0~1
            "idle_rate": round(idle_rate, 4),      # 0~1
            "avg_active_hours": round(avg_hours_if_active, 2),
        })

    # 按闲置率降序，其次按 label
    result_rows.sort(key=lambda x: (-x["idle_rate"], x["label"]))
    return result_rows, total_days_in_range


@login_required
def vehicle_idle_view(request: HttpRequest) -> HttpResponse:
    """车辆闲置分析页"""
    today = date.today()
    d_from = _parse_date(request.GET.get("from"), today.replace(day=1))
    d_to = _parse_date(request.GET.get("to"), _end_of_month(d_from))

    rows, total_days_in_range = _compute_vehicle_idle(d_from, d_to)

    context = {
        "rows": rows,
        "date_from": d_from.strftime("%Y-%m-%d"),
        "date_to": d_to.strftime("%Y-%m-%d"),
        "total_days": total_days_in_range,
    }
    return render(request, "analysis/vehicle_idle.html", context)


@login_required
def vehicle_idle_export_csv(request: HttpRequest) -> HttpResponse:
    """导出 CSV（与页面同口径）"""
    today = date.today()
    d_from = _parse_date(request.GET.get("from"), today.replace(day=1))
    d_to = _parse_date(request.GET.get("to"), _end_of_month(d_from))

    rows, _ = _compute_vehicle_idle(d_from, d_to)

    filename = f"vehicle_idle_{d_from:%Y-%m-%d}_to_{d_to:%Y-%m-%d}.csv"
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(["Label", "AvailableDays", "ActiveDays", "TotalHours", "Utilization(%)", "IdleRate(%)", "AvgActiveHours"])
    for r in rows:
        writer.writerow([
            r["label"],
            r["available_days"],
            r["active_days"],
            r["total_hours"],
            f"{r['utilization']*100:.2f}",
            f"{r['idle_rate']*100:.2f}",
            f"{r['avg_active_hours']:.2f}",
        ])
    return response


# =============================
# 司机売上分析 (/analysis/driver/)
# =============================

def _driver_label(d: dict) -> str:
    # 依据你实际的 Driver 字段调整：name / full_name / code 等
    return (
        d.get("driver__name")
        or d.get("driver__full_name")
        or d.get("driver__code")
        or f"Driver#{d.get('driver_id')}"
    )

def _compute_driver_sales(d_from: date, d_to: date):
    """
    rows: [{
        driver_id, label, work_days, work_hours,
        meter_sales, charter_sales, total_sales,
        avg_sales_per_day, sales_per_hour
    }]
    说明：
      - 工时 = sum(clock_out - clock_in)，自动忽略为空的记录
      - 計程売上 = items.is_charter=False 的 meter_fee 之和
      - 包车売上 = 优先 items.charter_amount_jpy；没有则回退 items.meter_fee
      - 如果 related_name 不是 items，请把 'items__...' 改成实际 related_name
    """
    qs = (
        DriverDailyReport.objects
        .filter(date__gte=d_from, date__lte=d_to)
        .values("driver_id", "driver__name")
        .annotate(
            work_hours=Sum(
                Case(
                    When(clock_in__isnull=False, clock_out__isnull=False,
                         then=ExpressionWrapper(F("clock_out") - F("clock_in"), output_field=DurationField())),
                    default=Value(timedelta(0)), output_field=DurationField()
                )
            ),
            work_days=Sum(
                Case(
                    When(clock_in__isnull=False, clock_out__isnull=False, then=Value(1)),
                    default=Value(0), output_field=FloatField()
                )
            ),
            meter_sales=Coalesce(Sum(
                Case(
                    When(items__is_charter=False, then=F("items__meter_fee")),
                    default=Value(0.0), output_field=FloatField()
                )
            ), Value(0.0)),
            charter_sales=Coalesce(Sum(
                Case(
                    When(items__is_charter=True,
                         then=Coalesce(F("items__charter_amount_jpy"), F("items__meter_fee"), Value(0.0))),
                    default=Value(0.0), output_field=FloatField()
                )
            ), Value(0.0)),
        )
    )

    rows = []
    for d in qs:
        hours = (d["work_hours"] or timedelta()).total_seconds() / 3600.0
        work_days = int(d.get("work_days") or 0)
        meter_sales = float(d["meter_sales"] or 0)
        charter_sales = float(d["charter_sales"] or 0)
        total_sales = meter_sales + charter_sales
        avg_per_day = (total_sales / work_days) if work_days else 0.0
        per_hour = (total_sales / hours) if hours > 0 else 0.0
        rows.append({
            "driver_id": d["driver_id"],
            "label": _driver_label(d),
            "work_days": work_days,
            "work_hours": round(hours, 2),
            "meter_sales": round(meter_sales, 0),
            "charter_sales": round(charter_sales, 0),
            "total_sales": round(total_sales, 0),
            "avg_sales_per_day": round(avg_per_day, 0),
            "sales_per_hour": round(per_hour, 0),
        })

    rows.sort(key=lambda x: (-x["total_sales"], x["label"]))
    return rows

@login_required
def driver_sales_view(request: HttpRequest) -> HttpResponse:
    today = date.today()
    d_from = _parse_date(request.GET.get("from"), today.replace(day=1))
    d_to = _parse_date(request.GET.get("to"), _end_of_month(d_from))

    rows = _compute_driver_sales(d_from, d_to)
    ctx = {
        "rows": rows,
        "date_from": f"{d_from:%Y-%m-%d}",
        "date_to": f"{d_to:%Y-%m-%d}",
        # ✅ 回传来源页；优先 ?back_url，没有就用当前完整路径
        "back_url": request.GET.get("back_url") or request.get_full_path(),
    }
    return render(request, "analysis/driver_sales.html", ctx)

@login_required
def driver_sales_export_csv(request: HttpRequest) -> HttpResponse:
    today = date.today()
    d_from = _parse_date(request.GET.get("from"), today.replace(day=1))
    d_to = _parse_date(request.GET.get("to"), _end_of_month(d_from))

    rows = _compute_driver_sales(d_from, d_to)

    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="driver_sales_{d_from:%Y-%m-%d}_to_{d_to:%Y-%m-%d}.csv"'
    w = csv.writer(resp)
    w.writerow(["Driver", "WorkDays", "WorkHours", "MeterSales", "CharterSales", "TotalSales", "AvgPerDay", "SalesPerHour"])
    for r in rows:
        w.writerow([r["label"], r["work_days"], r["work_hours"], r["meter_sales"], r["charter_sales"],
                    r["total_sales"], r["avg_sales_per_day"], r["sales_per_hour"]])
    return resp


# =================================
# 高效利用率分析 (/analysis/efficiency/)
# =================================

def _compute_efficiency(d_from: date, d_to: date):
    """
    输出三张榜单：
      vehicles: [{label, hours, sales, yen_per_hour}]
      drivers:  [{label, hours, sales, yen_per_hour}]
      pairs:    [{driver_label, vehicle_label, hours, sales, yen_per_hour}]
    """
    base = (
        DriverDailyReport.objects
        .filter(date__gte=d_from, date__lte=d_to)
        .annotate(
            work_time=Case(
                When(clock_in__isnull=False, clock_out__isnull=False,
                     then=ExpressionWrapper(F("clock_out") - F("clock_in"), output_field=DurationField())),
                default=Value(timedelta(0)), output_field=DurationField()
            ),
            meter_sales=Coalesce(Sum(
                Case(
                    When(items__is_charter=False, then=F("items__meter_fee")),
                    default=Value(0.0), output_field=FloatField()
                )
            ), Value(0.0)),
            charter_sales=Coalesce(Sum(
                Case(
                    When(items__is_charter=True,
                         then=Coalesce(F("items__charter_amount_jpy"), F("items__meter_fee"), Value(0.0))),
                    default=Value(0.0), output_field=FloatField()
                )
            ), Value(0.0)),
        )
        .values("id", "driver_id", "driver__name", "vehicle_id",
                "vehicle__license_plate", "vehicle__registration_number", "vehicle__name",
                "work_time", "meter_sales", "charter_sales")
    )

    def hours_of(v): return (v or timedelta()).total_seconds() / 3600.0
    def v_label(vdict):
        return (vdict.get("vehicle__license_plate")
                or vdict.get("vehicle__registration_number")
                or vdict.get("vehicle__name")
                or f"Vehicle#{vdict.get('vehicle_id')}")

    agg_vehicle = defaultdict(lambda: {"hours": 0.0, "sales": 0.0, "label": ""})
    agg_driver  = defaultdict(lambda: {"hours": 0.0, "sales": 0.0, "label": ""})
    agg_pair    = defaultdict(lambda: {"hours": 0.0, "sales": 0.0, "driver_label": "", "vehicle_label": ""})

    for r in base:
        h = hours_of(r["work_time"])
        sales = float(r["meter_sales"] or 0) + float(r["charter_sales"] or 0)

        # 车辆
        vid = r["vehicle_id"]
        vlab = v_label(r)
        av = agg_vehicle[vid]
        av["hours"] += h; av["sales"] += sales; av["label"] = vlab

        # 司机
        did = r["driver_id"]
        dlab = _driver_label({"driver__name": r.get("driver__name"), "driver_id": did})
        ad = agg_driver[did]
        ad["hours"] += h; ad["sales"] += sales; ad["label"] = dlab

        # 组合
        key = (did, vid)
        ap = agg_pair[key]
        ap["hours"] += h; ap["sales"] += sales
        ap["driver_label"] = dlab; ap["vehicle_label"] = vlab

    def finalize(dict_in, formatter):
        rows = []
        for _k, v in dict_in.items():
            ph = (v["sales"] / v["hours"]) if v["hours"] > 0 else 0.0
            rows.append(formatter(v, ph))
        rows.sort(key=lambda x: (-x["yen_per_hour"], x.get("label", "")))
        return rows

    vehicles = finalize(agg_vehicle, lambda v, ph: {
        "label": v["label"], "hours": round(v["hours"], 2), "sales": round(v["sales"], 0), "yen_per_hour": round(ph, 0)
    })
    drivers = finalize(agg_driver, lambda v, ph: {
        "label": v["label"], "hours": round(v["hours"], 2), "sales": round(v["sales"], 0), "yen_per_hour": round(ph, 0)
    })
    pairs = []
    for (_did, _vid), v in agg_pair.items():
        ph = (v["sales"] / v["hours"]) if v["hours"] > 0 else 0.0
        pairs.append({
            "driver_label": v["driver_label"],
            "vehicle_label": v["vehicle_label"],
            "hours": round(v["hours"], 2),
            "sales": round(v["sales"], 0),
            "yen_per_hour": round(ph, 0),
        })
    pairs.sort(key=lambda x: (-x["yen_per_hour"], x["driver_label"], x["vehicle_label"]))
    return vehicles, drivers, pairs

@login_required
def efficiency_view(request: HttpRequest) -> HttpResponse:
    today = date.today()
    d_from = _parse_date(request.GET.get("from"), today.replace(day=1))
    d_to = _parse_date(request.GET.get("to"), _end_of_month(d_from))

    vehicles, drivers, pairs = _compute_efficiency(d_from, d_to)
    ctx = {
        "vehicles": vehicles,
        "drivers": drivers,
        "pairs": pairs,
        "date_from": f"{d_from:%Y-%m-%d}",
        "date_to": f"{d_to:%Y-%m-%d}",
    }
    return render(request, "analysis/efficiency.html", ctx)

@login_required
def efficiency_export_csv(request: HttpRequest) -> HttpResponse:
    today = date.today()
    d_from = _parse_date(request.GET.get("from"), today.replace(day=1))
    d_to = _parse_date(request.GET.get("to"), _end_of_month(d_from))

    vehicles, drivers, pairs = _compute_efficiency(d_from, d_to)

    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="efficiency_{d_from:%Y-%m-%d}_to_{d_to:%Y-%m-%d}.csv"'
    w = csv.writer(resp)
    w.writerow([f"Vehicles {d_from:%Y-%m-%d}~{d_to:%Y-%m-%d}"])
    w.writerow(["Vehicle", "Hours", "Sales", "Yen/Hour"])
    for r in vehicles:
        w.writerow([r["label"], r["hours"], r["sales"], r["yen_per_hour"]])

    w.writerow([])
    w.writerow(["Drivers", "Hours", "Sales", "Yen/Hour"])
    for r in drivers:
        w.writerow([r["label"], r["hours"], r["sales"], r["yen_per_hour"]])

    w.writerow([])
    w.writerow(["Driver", "Vehicle", "Hours", "Sales", "Yen/Hour"])
    for r in pairs:
        w.writerow([r["driver_label"], r["vehicle_label"], r["hours"], r["sales"], r["yen_per_hour"]])

    return resp
