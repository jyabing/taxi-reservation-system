import csv, re, datetime
import re
import json
from itertools import zip_longest
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse
from datetime import datetime as DatetimeClass, timedelta, date as _date, datetime as _datetime, datetime as _dt, date , date as _DateType, datetime as _DTType

from django.views.decorators.http import require_http_methods
from django.utils.safestring import mark_safe

from django.utils.timezone import make_aware, is_naive, now, localdate
from collections import defaultdict
from carinfo.models import Car
from vehicles.models import Reservation
from django.forms import inlineformset_factory
from dailyreport.models import DriverDailyReport, DriverDailyReportItem
from staffbook.models import Driver, DriverSchedule, Accident 

from .permissions import is_staffbook_admin
from django.contrib import messages
from .forms import (
    DriverForm, DriverPersonalInfoForm, DriverLicenseForm, 
    DriverBasicForm, RewardForm, DriverPayrollRecordForm, DriverCertificateForm,
    HistoryEntryForm
    )

from dailyreport.forms import (
    DriverDailyReportForm, DriverDailyReportItemForm, DriverReportImageForm,
)

from .models import (
    Driver, DrivingExperience, 
    DriverInsurance, FamilyMember, DriverLicense, LicenseType, Qualification, Aptitude,
    Reward, Accident, Education, Pension, DriverPayrollRecord,
    DriverSchedule,   # ←← 新增这一行注意：末尾那个逗号要保留，这样排版也一致
)

from django.db.models import Q, Sum, Case, When, F, DecimalField, Count
from django.forms import inlineformset_factory, modelformset_factory
from django.utils import timezone
from django import forms

from calendar import monthrange

from django.core.paginator import Paginator
from django.urls import reverse
from decimal import Decimal, ROUND_HALF_UP

# ===== BEGIN SAFE IMPORTS (留存代码-开始) =====
# 这些模型在你的项目中 app 名可能不同；先做容错导入，避免整个视图崩溃
try:
    from reports.models import DriverDailyReportItem  # 出勤/日报明细
except Exception:
    DriverDailyReportItem = None  # 兼容：后续指标函数会判空

try:
    from reservations.models import Reservation      # 预约/派单记录
except Exception:
    Reservation = None  # 兼容：后续毁约率函数会判空
# ===== END SAFE IMPORTS (留存代码-结束) =====

from accounts.utils import check_module_permission
from dailyreport.services.summary import (
    calculate_totals_from_queryset,
    calculate_totals_from_formset, 
)

def is_admin_user(user):
    # "仅允许 is_staff 或 superuser 的用户访问：要么是超级管理员，要么是staff
    return user.is_superuser or user.is_staff

# ===== BEGIN keep-code: Japanese date helper =====
WEEK_JA = ['月', '火', '水', '木', '金', '土', '日']
def fmt_jp_date(d):
    """2025年11月14日（金）のように整形"""
    if not d:
        return ""
    return f"{d.year}年{d.month}月{d.day}日（{WEEK_JA[d.weekday()]}）"
# ===== END keep-code: Japanese date helper =====

# ===== 売上に基づく分段控除（給与側の規則）BEGIN =====
def calc_progressive_fee_by_table(amount_jpy: int | Decimal) -> int:
    """
    基于你提供的分段表计算扣款。
    入参：不含税売上（円）
    返回：円（整数）

    表规则（单位换算）：
      - 黄色列为「万円」：22.5 → 225,000 円，…，77 → 770,000 円
      - 超过 125,000 円部分，每增加 10,000 円，加 7 万円（= 70,000 円）
    """
    # 阈值单位应为「万円」→ 换算为 円（×10,000）
    THRESHOLDS = [450_000, 550_000, 650_000, 750_000, 850_000, 950_000, 1_050_000, 1_150_000, 1_250_000]
    # 对应累计值（黄色列：万円）
    CUM_VALUES_MAN = [22.5, 28.5, 35, 42, 49, 56, 63, 70, 77]  # 万円
    # 超出 125,000 円后，每 10,000 円的增量：7 万円
    STEP_AFTER_LAST_MAN = 7.0  # 万円 / 1万
    # 单位换算
    MAN_TO_YEN = 10_000        # 万円 → 円
    STEP_SIZE = 10_000         # 每一段宽度（1万）

    amt = int(Decimal(amount_jpy))
    if amt <= 0:
        return 0

    # 阈值内：直接按段取累计值（本表以 1 万为步进，不做更细插值）
    for i, limit in enumerate(THRESHOLDS):
        if amt <= limit:
            return int(round(CUM_VALUES_MAN[i] * MAN_TO_YEN))

    # 超出部分：基数 + 追加段数 * 每段增量
    base_man = CUM_VALUES_MAN[-1]
    extra_steps = (amt - THRESHOLDS[-1]) // STEP_SIZE
    total_man = base_man + extra_steps * STEP_AFTER_LAST_MAN
    return int(round(total_man * MAN_TO_YEN))
# ===== 売上に基づく分段控除（黄色列：万円）END =====


# ======== Auto-assign: helpers & metrics (place right after imports) ========

# —— 小工具 —— 
def _safe_date(d, default_future=True):
    if isinstance(d, _date):
        return d
    return _date(2100, 1, 1) if default_future else _date(1970, 1, 1)

def _serialize_sort_key(tup):
    """把排序键里的 date 等不可 JSON 序列化对象转换为字符串"""
    out = []
    for v in key_tuple:
        if hasattr(v, "isoformat"):  # date/datetime
            out.append(v.isoformat())
        else:
            out.append(v)
    return tuple(out)


def _business_days(d1: date, d2: date) -> int:
    days, cur = 0, d1
    while cur < d2:
        if cur.weekday() < 5:
            days += 1
        cur += timedelta(days=1)
    return max(days, 1)

# --- 指标（无数据时做稳健兜底） ---
def metric_join_date(driver) -> date:
    jd = getattr(driver, "hire_date", None) or getattr(driver, "join_date", None)
    return jd

def metric_accident_rate(driver, ref: date) -> float:
    if not Accident or not DriverDailyReportItem:
        return 0.0
    a_from = ref - timedelta(days=365)
    cnt = Accident.objects.filter(driver=driver, happened_at__gte=a_from, happened_at__lt=ref).count()
    attend = (DriverDailyReportItem.objects
              .filter(report__driver=driver, report__date__gte=a_from, report__date__lt=ref)
              .values('report__date').distinct().count())
    return cnt / max(attend, 1)


def _attend_days(driver, start: date, end: date) -> int:
    if not DriverDailyReportItem:
        return 0
    return (DriverDailyReportItem.objects
            .filter(report__driver=driver, report__date__gte=start, report__date__lt=end)
            .values('report__date').distinct().count())


def metric_attendance_rate(driver, ref: date) -> float:
    if not DriverDailyReportItem:
        return 0.0
    start = ref - timedelta(days=90)
    attend = (DriverDailyReportItem.objects
              .filter(report__driver=driver, report__date__gte=start, report__date__lt=ref)
              .values('report__date').distinct().count())
    return attend / _business_days(start, ref)

def metric_sales_last_month(driver, ref: date) -> float:
    if not DriverDailyReportItem:
        return 0.0
    y, m = ref.year, ref.month
    py, pm = (y, m-1) if m > 1 else (y-1, 12)
    start, end = date(py, pm, 1), date(y, m, 1)
    qs = DriverDailyReportItem.objects.filter(report__driver=driver,
                                              report__date__gte=start,
                                              report__date__lt=end)
    gross = (qs.aggregate(total=Sum(F('meter_fee') + F('charter_amount_jpy')))['total'] or 0)
    try:
        return float(Decimal(gross) / Decimal("1.10"))
    except Exception:
        return float(gross)


def metric_breach_rate(driver, ref: date) -> float:
    if not Reservation:
        return 0.0
    start = ref - timedelta(days=90)
    time_field = None
    for f in ("reserved_at", "created_at"):
        if hasattr(Reservation, f):
            time_field = f
            break
    if not time_field:
        return 0.0
    time_filter = {f"{time_field}__gte": start, f"{time_field}__lt": ref}
    total = Reservation.objects.filter(driver=driver, **time_filter).count()
    cancel_statuses = ["canceled", "cancelled", "no_show", "rejected"]
    canceled = Reservation.objects.filter(driver=driver, **time_filter, status__in=cancel_statuses).count()
    return canceled / max(total, 1)

def build_ranking_key(driver, ref: date):
    """
    优先顺序：
      1) 事故率低 (asc)
      2) 毁约率低 (asc)
      3) 上月売上高 (desc)
      4) 出勤率高 (desc)
      5) 入社早   (asc)
      6) driver_id(asc)
    """
    jd = metric_join_date(driver) or date(2100,1,1)
    ar = metric_accident_rate(driver, ref)
    br = metric_breach_rate(driver, ref)
    sl = metric_sales_last_month(driver, ref)
    at = metric_attendance_rate(driver, ref)
    return (ar, br, -sl, -at, jd, driver.id)


def _serialize_sort_key(val):
    """
    递归把 tuple/list/日期/Decimal 等，转成 JSON 可序列化的基础类型（list/str/float/int）。
    """
    if isinstance(val, (int, float, str)) or val is None:
        return val
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, (_DateType, _DTType)):
        return val.isoformat()
    if isinstance(val, (tuple, list)):
        return [_serialize_sort_key(x) for x in val]
    # 其它类型，保底转字符串
    return str(val)
# ===== 【结束留存代码】_serialize_sort_key =====

def _sort_key_to_json(key_tuple):
    out = []
    for v in key_tuple:
        if isinstance(v, _Date):
            # 用 ISO 字符串或 ordinal 都行；为了可读性用 ISO
            out.append(v.isoformat())
        else:
            # Decimal / numpy 数字等也可能混进来，统一转成原生类型
            try:
                # 尝试 float 化，失败就原样
                if hasattr(v, 'quantize'):  # Decimal
                    out.append(float(v))
                else:
                    out.append(v)
            except Exception:
                out.append(str(v))
    return out

def _serialize_sort_key(sk):
    """
    将排序键中的 date/datetime 元素转成 ISO 字符串，以便写入 JSONField。
    """
    try:
        return [(x.isoformat() if isinstance(x, (_Date, _DateTime)) else x) for x in sk]
    except Exception:
        # sk 不是可迭代或意外情况，尽量退化成字符串
        return str(sk)
# ===== 结束留存代码 =====

# ===== 【开始留存代码】build_assign_reason：计算详细理由（全局可复用） =====
def build_assign_reason(drv, ref: date):
    """生成落库/预演通用的“推荐理由”结构，全部字段可 JSON 序列化"""
    jd = metric_join_date(drv)
    ar = metric_accident_rate(drv, ref)
    at = metric_attendance_rate(drv, ref)
    sl = metric_sales_last_month(drv, ref)
    br = metric_breach_rate(drv, ref)

    a_from = ref - timedelta(days=365)
    b_from = ref - timedelta(days=90)
    # --- 安全取数：模型可能不存在时返回 0 ---
    # 事故数（近12个月）
    try:
        if 'Accident' in globals() and Accident is not None:
            accidents_12m = Accident.objects.filter(
                driver=drv, happened_at__gte=a_from, happened_at__lt=ref
            ).count()
        else:
            accidents_12m = 0
    except Exception:
        accidents_12m = 0

    # 出勤天数（近12个月）
    try:
        if 'DriverDailyReportItem' in globals() and DriverDailyReportItem is not None:
            attend_12m = (DriverDailyReportItem.objects
                        .filter(report__driver=drv,
                                report__date__gte=a_from, report__date__lt=ref)
                        .values('report__date').distinct().count())
        else:
            attend_12m = 0
    except Exception:
        attend_12m = 0

    # 出勤天数（近90天）
    try:
        if 'DriverDailyReportItem' in globals() and DriverDailyReportItem is not None:
            attend_90 = (DriverDailyReportItem.objects
                        .filter(report__driver=drv,
                                report__date__gte=b_from, report__date__lt=ref)
                        .values('report__date').distinct().count())
        else:
            attend_90 = 0
    except Exception:
        attend_90 = 0

    wd90 = sum(1 for i in range(90) if (b_from + timedelta(days=i)).weekday() < 5)

    acc_rate_show = (round(accidents_12m / max(attend_12m,1), 4)
                     if attend_12m > 0 else "NA")

    sort_key = _serialize_sort_key(build_ranking_key(drv, ref))

    return {
        "join_date": jd.isoformat() if jd else None,
        "accidents_12m": accidents_12m,
        "attend_days_12m": attend_12m,
        "accident_rate": acc_rate_show,
        "attend_days_90": attend_90,
        "workdays_90": wd90,
        "attendance_rate_90": round(at, 4),
        "last_month_sales": int(sl),
        "breach_rate": float(br),
        "sort_key": sort_key,
        "priority_order": [
            "accident_rate_12m（低）",
            "breach_rate（低）",
            "last_month_sales（高）",
            "attendance_rate_90（高）",
            "join_date（早）",
            "driver_id（昇順）",
        ],
    }

# ===== 留存代码-开始: notices & tooltip =====
DAY_NOTICE   = "（もし昼勤と夜勤の交代があれば17時厳守。）"
NIGHT_NOTICE = "（もし夜勤と昼勤の交代があれば7時厳守。）"

def _format_reason_tooltip(why: dict) -> str:
    if not why:
        return ""
    def pct(x):
        try:
            return f"{float(x)*100:.1f}%"
        except Exception:
            return "NA"
    parts = []
    parts.append(f"入社日: {why.get('join_date') or '-'}")
    parts.append(
        f"事故率(12ヶ月): {why.get('accident_rate')} "
        f"（事故{why.get('accidents_12m',0)} / 出勤{why.get('attend_days_12m',0)}）"
    )
    parts.append(
        f"出勤率(90日): {why.get('attendance_rate_90')} "
        f"（出勤{why.get('attend_days_90',0)} / 営業日{why.get('workdays_90',0)}）"
    )
    parts.append(f"上月売上(税抜): {why.get('last_month_sales',0)}円")
    parts.append(f"毁約率(90日): {why.get('breach_rate',0)}")
    return " / ".join([p for p in parts if p])
# ===== 留存代码-结束 =====


def build_priority_tuple_and_reason(d):
    """
    d: dict，至少包含
      join_date, accidents_12m, attend_days_90, workdays_90,
      last_month_sales, breach_rate
    返回：(key_tuple, reason_dict)
    规则优先级（由高到低）：
      1. 入社更早（早者优先）    -> 用 -入社天数 做键
      2. 事故率更低              -> accidents_12m / attend_days_90(或出勤天数)；无出勤按大数惩罚
      3. 出勤率更高（近90天）    -> attend_days_90 / workdays_90
      4. 上月売上更高（不含税）
      5. 毁约率更低（缺数据=0）
    """
    today = _date.today()
    # 1) 入社天数（越大越早）→ 排序要“越早越靠前”，所以取负号放在 key 里
    if d.get("join_date"):
        senior_days = (today - d["join_date"]).days
    else:
        senior_days = 0

    # 2) 事故率（12 个月事故数 / 出勤天数），分母为 0 视为极差（用一个较大的值）
    accidents = int(d.get("accidents_12m") or 0)
    attend_12m = int(d.get("attend_days_12m") or 0)  # 更稳：用 12 个月出勤
    accident_rate = (accidents / attend_12m) if attend_12m > 0 else 9999.0

    # 3) 出勤率（近 90 天）
    ad90 = int(d.get("attend_days_90") or 0)
    wd90 = int(d.get("workdays_90") or 0)
    attend_rate_90 = (ad90 / wd90) if wd90 > 0 else 0.0

    # 4) 上月売上（不含税）
    sales = int(d.get("last_month_sales") or 0)

    # 5) 毁约率（缺失按 0）
    breach_rate = float(d.get("breach_rate") or 0.0)

    # —— 排序键（按优先级逐项比较）——
    key = (
        -senior_days,               # 入社越早数值越小 → 更优
        accident_rate,              # 越小越优
        -attend_rate_90,            # 越大越优 → 取负
        -sales,                     # 越大越优 → 取负
        breach_rate,                # 越小越优
    )

    sk = build_ranking_key(obj.driver, obj.work_date)

    reason = {
        "seniority_days": senior_days,
        "accidents_12m": accidents,
        "attend_days_12m": attend_12m,
        "accident_rate": round(accident_rate, 4) if accident_rate != 9999.0 else "NA",
        "attend_days_90": ad90,
        "workdays_90": wd90,
        "attendance_rate_90": round(attend_rate_90, 4),
        "last_month_sales": sales,
        "breach_rate": breach_rate,
        "join_date": getattr(obj.driver, "join_date", None) and getattr(obj.driver, "join_date").isoformat(),
        "sort_key":   _serialize_sort_key(sk),   # ← 这里！
    }
    return key, reason

DAY_NOTICE   = "（もし昼勤と夜勤の交代があれば17時厳守。）"
NIGHT_NOTICE = "（もし夜勤と昼勤の交代があれば7時厳守。）"

# —— 主函数：自动配车 —— 
def auto_assign_plan_for_date(target_date: _date):
    """
    只计算不落库；返回：
      {
        "preview_rows": [...],   # 供灰色卡片列表
        "assign_ops":   [(sched_id, car_id, shift, why_dict), ...],
        "counts":       {"first":x,"second":y,"any":z}
      }
    """
    scheds = list(
        DriverSchedule.objects
        .select_related('driver','first_choice_car','second_choice_car','assigned_car')
        .filter(work_date=target_date, is_rest=False)
    )

    # 已占用（按班别）
    used_day   = {s.assigned_car_id for s in scheds if s.assigned_car_id and (s.shift or "") == "day"}
    used_night = {s.assigned_car_id for s in scheds if s.assigned_car_id and (s.shift or "") == "night"}

    raw_cars = Car.objects.exclude(status__in=["scrapped","retired","disabled"]).order_by('id')
    available_ids = []
    for c in raw_cars:
        if getattr(c, "is_scrapped", False):  continue
        if not getattr(c, "is_active", True): continue
        st = (getattr(c,'status','') or '').strip().lower()
        if st in ("maintenance","repair","fixing") or getattr(c, 'is_maintaining', False):
            continue
        available_ids.append(c.id)

    ref = target_date
    score_cache, why_cache = {}, {}
    def _score(drv):
        if drv.id not in score_cache:
            score_cache[drv.id] = build_ranking_key(drv, ref)
        return score_cache[drv.id]
    def _why(drv):
        if drv.id not in why_cache:
            why_cache[drv.id] = build_assign_reason(drv, ref)
        return why_cache[drv.id]

    def _car_free_for_shift(car_id, shift):
        s = (shift or "").strip()
        if s == "night": return car_id not in used_night
        return car_id not in used_day  # 默认当作白班

    preview_rows, assign_ops = [], []
    assigned_drv_ids = set()
    first_cnt = second_cnt = any_cnt = 0

    # 第1希望
    car_to_scheds = {}
    for s in scheds:
        if s.first_choice_car_id and s.driver_id not in assigned_drv_ids and not s.assigned_car_id:
            car_to_scheds.setdefault(s.first_choice_car_id, []).append(s)

    for car_id, rows in car_to_scheds.items():
        rows_sorted = sorted(rows, key=lambda r: _score(r.driver))
        win = next((r for r in rows_sorted if _car_free_for_shift(car_id, r.shift)), None)
        if not win:
            continue
        if (win.shift or "") == "night": used_night.add(car_id)
        else: used_day.add(car_id)
        assigned_drv_ids.add(win.driver_id)
        first_cnt += 1
        preview_rows.append({
            "car": win.first_choice_car, "driver": win.driver, "winner": True,
            "why": _why(win.driver),
            "others": [{"driver": r.driver, "why": _why(r.driver), "key": _score(r.driver)} for r in rows_sorted if r!=win],
        })
        assign_ops.append((win.id, car_id, (win.shift or ""), build_assign_reason(win.driver, ref)))

    # 第2希望
    remaining = [s for s in scheds if s.driver_id not in assigned_drv_ids and not s.assigned_car_id]
    car2_to_scheds = {}
    for s in remaining:
        if s.second_choice_car_id:
            car2_to_scheds.setdefault(s.second_choice_car_id, []).append(s)

    for car_id, rows in car2_to_scheds.items():
        rows_sorted = sorted(rows, key=lambda r: _score(r.driver))
        win = next((r for r in rows_sorted if _car_free_for_shift(car_id, r.shift)), None)
        if not win:
            continue
        if (win.shift or "") == "night": used_night.add(car_id)
        else: used_day.add(car_id)
        assigned_drv_ids.add(win.driver_id)
        second_cnt += 1
        preview_rows.append({
            "car": win.second_choice_car, "driver": win.driver, "winner": True,
            "why": _why(win.driver),
            "others": [{"driver": r.driver, "why": _why(r.driver), "key": _score(r.driver)} for r in rows_sorted if r!=win],
        })
        assign_ops.append((win.id, car_id, (win.shift or ""), build_assign_reason(win.driver, ref)))

    # 任意车
    free_ids = [cid for cid in available_ids]
    remain_any = [
        s for s in scheds
        if s.driver_id not in assigned_drv_ids and not s.assigned_car_id
        and (getattr(s, "any_car", False) is True
             or (not s.first_choice_car_id and not s.second_choice_car_id))
    ]
    remain_any_sorted = sorted(remain_any, key=lambda r: _score(r.driver))
    for s in remain_any_sorted:
        # 找第一辆在该班别可用的车
        cid = next((cid for cid in free_ids if _car_free_for_shift(cid, s.shift)), None)
        if not cid:
            break
        if (s.shift or "") == "night": used_night.add(cid)
        else: used_day.add(cid)
        assigned_drv_ids.add(s.driver_id)
        any_cnt += 1
        preview_rows.append({
            "car": next((c for c in raw_cars if c.id == cid), None),
            "driver": s.driver, "winner": True,
            "why": _why(s.driver),
            "others": [],
        })
        assign_ops.append((s.id, cid, (s.shift or ""), build_assign_reason(s.driver, ref)))

    return {"preview_rows": preview_rows, "assign_ops": assign_ops,
            "counts": {"first": first_cnt, "second": second_cnt, "any": any_cnt}}


# =================== Auto-assign block END ===================

# ==== BEGIN INSERT P1: plan-only (dry-run) helper ====
def auto_assign_plan_for_date(target_date: date):
    scheds = list(
        DriverSchedule.objects
        .select_related('driver','first_choice_car','second_choice_car','assigned_car')
        .filter(work_date=target_date, is_rest=False)
    )

    used_car_ids = set(s.assigned_car_id for s in scheds if s.assigned_car_id)

    raw_cars = Car.objects.exclude(status__in=["scrapped","retired","disabled"]).order_by('id')
    available = []
    for c in raw_cars:
        if getattr(c, "is_scrapped", False):  continue
        if not getattr(c, "is_active", True): continue
        st = (getattr(c,'status','') or '').strip().lower()
        if st in ("maintenance","repair","fixing") or getattr(c, 'is_maintaining', False):
            continue
        if c.id in used_car_ids:
            continue
        available.append(c.id)

    ref = target_date
    score_cache, why_cache = {}, {}

    def _score(drv):
        if drv.id not in score_cache:
            score_cache[drv.id] = build_ranking_key(drv, ref)
        return score_cache[drv.id]

    def _why(drv):
        if drv.id not in why_cache:
            why_cache[drv.id] = build_assign_reason(drv, ref)
        return why_cache[drv.id]

    preview_rows, assign_ops = [], []
    assigned_drv_ids = set()
    first_cnt = second_cnt = any_cnt = 0

    # 第一希望
    car_to_scheds = {}
    for s in scheds:
        if s.first_choice_car_id and s.driver_id not in assigned_drv_ids and not s.assigned_car_id:
            car_to_scheds.setdefault(s.first_choice_car_id, []).append(s)

    for car_id, rows in car_to_scheds.items():
        if car_id in used_car_ids:
            continue
        rows_sorted = sorted(rows, key=lambda r: _score(r.driver))
        win = rows_sorted[0]
        assigned_drv_ids.add(win.driver_id)
        used_car_ids.add(car_id)
        first_cnt += 1
        preview_rows.append({
            "car": win.first_choice_car, "driver": win.driver, "winner": True,
            "why": _why(win.driver),
            "others": [{"driver": r.driver, "why": _why(r.driver), "key": _score(r.driver)} for r in rows_sorted[1:]],
        })
        assign_ops.append((win.id, car_id, _why(win.driver)))

    # 第二希望
    remaining = [s for s in scheds if s.driver_id not in assigned_drv_ids and not s.assigned_car_id]
    car2_to_scheds = {}
    for s in remaining:
        if s.second_choice_car_id:
            car2_to_scheds.setdefault(s.second_choice_car_id, []).append(s)

    for car_id, rows in car2_to_scheds.items():
        if car_id in used_car_ids:
            continue
        rows_sorted = sorted(rows, key=lambda r: _score(r.driver))
        win = rows_sorted[0]
        assigned_drv_ids.add(win.driver_id)
        used_car_ids.add(car_id)
        second_cnt += 1
        preview_rows.append({
            "car": win.second_choice_car, "driver": win.driver, "winner": True,
            "why": _why(win.driver),
            "others": [{"driver": r.driver, "why": _why(r.driver), "key": _score(r.driver)} for r in rows_sorted[1:]],
        })
        assign_ops.append((win.id, car_id, _why(win.driver)))

    # 任意车
    free = [cid for cid in available if cid not in used_car_ids]
    remain_any = [
        s for s in scheds
        if s.driver_id not in assigned_drv_ids
        and not s.assigned_car_id
        and (
            getattr(s, "any_car", False) is True
            or (not s.first_choice_car_id and not s.second_choice_car_id)
        )
    ]
    remain_any_sorted = sorted(remain_any, key=lambda r: _score(r.driver))
    idx = 0
    for s in remain_any_sorted:
        while idx < len(free) and free[idx] in used_car_ids:
            idx += 1
        if idx >= len(free):
            break
        cid = free[idx]
        assigned_drv_ids.add(s.driver_id)
        used_car_ids.add(cid)
        any_cnt += 1
        preview_rows.append({
            "car": next((c for c in raw_cars if c.id == cid), None),
            "driver": s.driver, "winner": True,
            "why": _why(s.driver),
            "others": [],
        })
        assign_ops.append((s.id, cid, _why(s.driver)))
        idx += 1

    return {
        "preview_rows": preview_rows,
        "assign_ops": assign_ops,
        "counts": {"first": first_cnt, "second": second_cnt, "any": any_cnt},
    }
# ==== END INSERT P1 ====

def _make_reason_meta(driver, ref_date, match_kind, base_reason: dict):
    """
    统一 assignment_meta 的结构：保留预演产生的 reason，并补齐 by/at/match。
    """
    # 你的 build_ranking_key / metric_* 已经在上方定义
    meta = {
        "rule_version": "v1.0",
        "by": "auto",
        "at": now().isoformat(timespec="seconds"),
        "match": match_kind,   # "first" / "second" / "any"
        "reason": dict(base_reason or {}),
    }
    # 兜底：reason.sort_key 不存在则补齐
    if "sort_key" not in meta["reason"]:
        meta["reason"]["sort_key"] = build_ranking_key(driver, ref_date)
    return meta


def auto_assign_apply_ops(assign_ops, target_date: date) -> int:
    saved = 0
    has_meta = "assignment_meta" in {f.name for f in DriverSchedule._meta.fields}
    for op in assign_ops:
        # 兼容旧三元组
        sched_id, car_id = op[0], op[1]
        why = op[3] if len(op) > 3 else (op[2] if len(op) > 2 else {})
        upd = {
            "assigned_car_id": car_id,
            "status": "approved",
        }
        if hasattr(DriverSchedule, "assigned_by"):
            upd["assigned_by"] = "auto"
        if hasattr(DriverSchedule, "assigned_at"):
            upd["assigned_at"] = now()
        if has_meta:
            upd["assignment_meta"] = {
                "rule_version": "v1.0",
                "by": "auto",
                "at": now().isoformat(timespec="seconds"),
                "reason": why,
            }
        DriverSchedule.objects.filter(pk=sched_id).update(**upd)
        saved += 1
    return saved

def _parse_work_dates(raw: str) -> list[_date]:
    """支持中文/英文逗号、分号、空格分隔；返回去重后的日期列表"""
    if not raw:
        return []
    s = raw.replace("，", ",").replace("；", ";")
    tokens = re.split(r"[,\s;]+", s.strip())
    out = []
    for t in tokens:
        if not t:
            continue
        try:
            out.append(_date.fromisoformat(t))
        except Exception:
            # 忽略解析失败的片段
            pass
    # 去重 + 排序
    return sorted(set(out))


@user_passes_test(is_staffbook_admin)
def staffbook_dashboard(request):
    return render(request, 'staffbook/dashboard.html')

# ==============================================================
# BEGIN: 司机本人填写“约日期”表单页（桌面=表格，手机=卡片）
# ==============================================================


@login_required
@require_http_methods(["GET", "POST"])
def schedule_form_view(request):
    """司机本人：提交自己的希望スケジュール（含区分冲突防护）"""
    today = _date.today()

    # ① 当前登录司机
    try:
        me = Driver.objects.get(user=request.user)
    except Driver.DoesNotExist:
        me = None

    # ② 页面右上角“查看基准日”（非提交用）
    work_date_str = request.GET.get("work_date") or today.strftime("%Y-%m-%d")
    try:
        y, m, d = [int(x) for x in work_date_str.split("-")]
        work_date = _date(y, m, d)
    except Exception:
        work_date = today

    # ③ 该日是否已提交过
    existing = None
    if me:
        existing = DriverSchedule.objects.filter(driver=me, work_date=work_date).first()

    # ④ 车辆下拉（正常在上，整備中在下；报废/退役/停用不出）
    raw_cars = (
        Car.objects
        .exclude(status__in=["scrapped", "retired", "disabled"])
        .order_by("license_plate", "name", "id")
    )
    normal_cars, maint_cars = [], []
    for c in raw_cars:
        plate = getattr(c, "license_plate", None) or getattr(c, "registration_number", None) or ""
        car_name = getattr(c, "name", None) or getattr(c, "model", None) or ""
        base_label = " / ".join([s for s in (plate, car_name) if s]) or f"ID:{c.id}"

        status      = (getattr(c, "status", "") or "").strip()
        is_active   = getattr(c, "is_active", True)
        is_maint    = bool(getattr(c, "is_maintaining", False))
        is_scrapped = bool(getattr(c, "is_scrapped", False))
        if is_scrapped:
            continue

        is_maint_status = status in ("maintenance", "repair", "fixing") or is_maint
        if is_maint_status:
            c.label = f"{base_label}（整備中）"
            c.is_bad = True
            maint_cars.append(c)
            continue

        if not is_active:
            continue

        c.label = base_label
        c.is_bad = False
        normal_cars.append(c)

    cars = normal_cars + maint_cars
    allowed_car_ids = {c.id for c in normal_cars}

    # ⑤ 提交保存（支持多日期）
    if request.method == "POST" and me:
        dates_str = (request.POST.get("work_dates") or "").strip()
        if not dates_str:
            messages.error(request, "日付を選択してください。")
            return redirect(request.path)

        # 解析多日
        dates = []
        for part in re.split(r"[,\s]+", dates_str.replace("，", ",").strip()):
            if not part:
                continue
            try:
                y, m, d = [int(x) for x in part.split("-")]
                dt = _date(y, m, d)
                if dt >= today:
                    dates.append(dt)
            except Exception:
                continue
        dates = sorted(set(dates))
        if not dates:
            messages.error(request, "有効な日付がありません。")
            return redirect(request.path)

        # 其它字段（兼容手机端）
        mode     = request.POST.get("mode")      or request.POST.get("m-mode")
        shift    = request.POST.get("shift")     or request.POST.get("m-shift") or ""
        note     = request.POST.get("note")      or request.POST.get("m_note")  or ""
        any_car  = (request.POST.get("any_car")  or request.POST.get("m_any_car")) == "1"
        first_id = request.POST.get("first_car") or request.POST.get("m_first_car") or None
        second_id= request.POST.get("second_car")or request.POST.get("m_second_car") or None
        overwrite = (request.POST.get("overwrite") == "1")  # ← 可选：允许覆盖开关

        # —— 服务器端校验 —— #
        if mode not in ("rest", "wish"):
            messages.error(request, "区分を選択してください。")
            return redirect(request.path)

        if mode == "wish":
            if not shift:
                messages.error(request, "シフトを選択してください。")
                return redirect(request.path)
            if not any_car:
                if not first_id or not second_id:
                    messages.error(request, "第1希望と第2希望を選択してください。")
                    return redirect(request.path)
                if first_id == second_id:
                    messages.error(request, "第1希望と第2希望は同じ車両にできません。")
                    return redirect(request.path)
                try:
                    f_id_int = int(first_id); s_id_int = int(second_id)
                except Exception:
                    messages.error(request, "車両の選択が不正です。")
                    return redirect(request.path)
                if f_id_int not in allowed_car_ids or s_id_int not in allowed_car_ids:
                    messages.error(request, "選択した車両は現在使用できません。別の車両を選んでください。")
                    return redirect(request.path)

        # —— 区分冲突检查（后端强拦）——
        # 已有记录中与当前提交“区分”不同的日期，即为冲突
        existing_rows = {
            r.work_date: r
            for r in DriverSchedule.objects.filter(driver=me, work_date__in=dates)
        }
        want_rest = (mode == "rest")
        conflicts = []
        for d in dates:
            row = existing_rows.get(d)
            if not row:
                continue
            if bool(row.is_rest) != want_rest:
                conflicts.append(d)

        if conflicts and not overwrite:
            jstr = "、".join(dt.strftime("%Y-%m-%d") for dt in conflicts)
            tip = "既に『希望提出』で登録済み" if want_rest else "既に『休み』で登録済み"
            messages.error(
                request,
                f"以下の日付は区分が衝突しています：{jstr}。{tip}のため上書きできません。"
                "先に該当日の登録を削除するか、同じ区分で再提出してください。"
            )
            return redirect(request.path)

        # 逐日保存（若 overwrite=True，则允许覆盖）
        saved, skipped = 0, 0
        for wd in dates:
            try:
                obj, _ = DriverSchedule.objects.get_or_create(driver=me, work_date=wd)
                obj.note = note

                if mode == "rest":
                    obj.is_rest = True
                    obj.shift = ""
                    obj.any_car = False
                    obj.first_choice_car = None
                    obj.second_choice_car = None
                    obj.assigned_car = None
                    obj.status = "pending"
                else:
                    obj.is_rest = False
                    obj.shift = shift
                    obj.any_car = any_car

                    fc = Car.objects.filter(pk=first_id).first() if first_id else None
                    sc = Car.objects.filter(pk=second_id).first() if second_id else None
                    if fc and sc and fc.id == sc.id:
                        sc = None
                    if fc and fc.id not in allowed_car_ids:
                        fc = None
                    if sc and sc.id not in allowed_car_ids:
                        sc = None

                    obj.first_choice_car = fc
                    obj.second_choice_car = sc
                    # 如需改“希望”时也清空已配车，取消下一行注释
                    # obj.assigned_car = None

                obj.save()
                saved += 1
            except Exception:
                skipped += 1

        if saved:
            messages.success(request, f"{saved} 日分のスケジュールを保存しました。")
        if skipped:
            messages.warning(request, f"{skipped} 日は保存できませんでした。入力内容をご確認ください。")
        return redirect("staffbook:my_reservations")

    # ⑥ GET 渲染 —— 附带“我已有的提交”给前端做即时提醒（可选）
    my_existing_json = "[]"
    if me:
        rng_from = today - timedelta(days=30)
        rng_to   = today + timedelta(days=90)
        rows = DriverSchedule.objects.filter(
            driver=me, work_date__gte=rng_from, work_date__lte=rng_to
        ).values("work_date", "is_rest")
        my_existing_json = json.dumps([
            {"date": r["work_date"].strftime("%Y-%m-%d"), "is_rest": bool(r["is_rest"])}
            for r in rows
        ])

    ctx = {
        "driver": me,
        "today": today,
        "work_date": work_date,
        "existing": existing,
        "cars": cars,
        "my_existing_json": mark_safe(my_existing_json),  # ← 前端可读
    }
    return render(request, "staffbook/schedule_form.html", ctx)

# ==============================================================
# END: 司机本人填写“约日期”表单页（支持保存）
# ==============================================================

# ==============================================================
# 司机本人：看自己最近30天内提交的希望/休み
# ==============================================================
@login_required
def schedule_my_list_view(request):
    """司机本人：看自己最近30天内提交的希望/休み"""
    # 1. 找到这个登录用户对应的司机
    try:
        driver = Driver.objects.get(user=request.user)
    except Driver.DoesNotExist:
        driver = None

    # ✅ 用我们在文件头里导入的名字 _date
    today = _date.today()
    to_date = today + timedelta(days=30)

    rows = []
    if driver:
        rows = (
            DriverSchedule.objects
            .filter(driver=driver, work_date__gte=today, work_date__lte=to_date)
            .order_by("work_date")
        )

    ctx = {
        "driver": driver,
        "rows": rows,
        "today": today,
        "to_date": to_date,
    }
    return redirect("staffbook:my_reservations")


# ==============================================================
# BEGIN: 司机本人查看「我的预约」页面
# ==============================================================

@login_required
def my_reservations_view(request):
    """
    当前登录司机查看自己提交的スケジュール
    """
    try:
        driver = Driver.objects.get(user=request.user)
    except Driver.DoesNotExist:
        driver = None

    today = _date.today()
    # 你模板里要显示 “今天 ~ to_date”
    to_date = today + timedelta(days=14)   # 自己的sschedule, 想 7 天就写 7, 14 天就写 14 天

    if driver:
        schedules = (
            DriverSchedule.objects
            .filter(driver=driver, work_date__gte=today, work_date__lte=to_date)
            .order_by("work_date", "-created_at")
        )
    else:
        schedules = []

    ctx = {
        "driver": driver,
        "today": today,
        "to_date": to_date,   # 👈 模板要的
        "schedules": schedules,
    }
    return render(request, "staffbook/my_reservations.html", ctx)

# ==============================================================
# END: 司机本人查看「我的预约」页面
# ==============================================================

# === 目标示例：车辆分组与清单生成（A/B/C/D/その他） ===
_SCHEDULE_GROUP_RULES = [
    (["alphard", "アルファード", "alpha"], "A アルファ"),
    (["voxy", "ヴォクシー", "noah", "ノア"], "B ウォクシー等"),
    (["camry", "カムリ"],                   "C カムリ"),
    (["sienta", "シエンタ"],               "D シエンタ"),
]

def _veh_number(v):
    return (
        getattr(v, "license_plate", "") or
        getattr(v, "nameplate", "") or
        getattr(v, "registration_number", "") or
        str(getattr(v, "id", ""))
    )

def _veh_group_title(v):
    val = (getattr(v, "model", "") or getattr(v, "model_code", "") or "").lower()
    for keys, title in _SCHEDULE_GROUP_RULES:
        if any(k.lower() in val for k in keys):
            return title
    return "その他"

def _driver_name(d):
    if not d:
        return ""
    for attr in ("display_name", "name", "full_name", "realname", "username"):
        if hasattr(d, attr) and getattr(d, attr):
            return str(getattr(d, attr))
    return str(d)

def build_daily_vehicle_schedule(work_date):
    """
    返回 [(group_title, [(num, driver, is_repair), ...]), ...] 已排序。
    规则：
      - 同日若有预约，优先显示 STATUS=out 的司机；否则显示当天该车第一条预约的司机
      - 维修中车辆显示“🛠️ 维修中”，司机留空
      - 车号按数字排序
    """
    vehicles = Car.objects.exclude(status__in=["retired", "scrapped", "disabled"])

    # 当天涉及的预约（含跨日）
    day_res = (
        Reservation.objects
        .select_related("vehicle", "driver")
        .filter(date__lte=work_date, end_date__gte=work_date)
        .order_by("vehicle_id", "status", "start_time")
    )

    # 挑每辆车“最合适的一条”
    chosen = {}
    for r in day_res:
        vid = getattr(r.vehicle, "id", None)
        prev = chosen.get(vid)
        # 优先 out，其次第一条
        if prev is None or (getattr(prev, "status", "") != "out" and getattr(r, "status", "") == "out"):
            chosen[vid] = r

    grouped = {}
    for v in vehicles:
        is_repair = (getattr(v, "status", "") in ["repair", "maintenance", "fixing"])
        num = _veh_number(v)
        r = chosen.get(getattr(v, "id", None))
        dname = _driver_name(getattr(r, "driver", None)) if (r and not is_repair) else ""
        gtitle = _veh_group_title(v)
        grouped.setdefault(gtitle, []).append((num, dname, is_repair))

    # 数字顺序（029、162……）
    def _numkey(t):
        digits = "".join(ch for ch in str(t[0]) if ch.isdigit())
        return int(digits) if digits else 10**9

    for rows in grouped.values():
        rows.sort(key=_numkey)

    order = ["A アルファ", "B ウォクシー等", "C カムリ", "D シエンタ", "その他"]
    return [(g, grouped[g]) for g in order if g in grouped and grouped[g]]


# ==============================================================
# 管理员 / 事务员：查看所有司机提交的“日期+希望车両”
# URL: /staffbook/schedule-list/
# 模板: staffbook/schedule_list.html
# ==============================================================

# ===== BEGIN VIEW schedule_list_view (留存代码-开始) =====
@login_required
@user_passes_test(is_admin_user)
def schedule_list_view(request):
    today = _date.today()
    date_from, date_to = today, today + timedelta(days=14)

    group         = request.GET.get("group","date")
    driver_id     = request.GET.get("driver")
    work_date_str = request.GET.get("work_date")

    qs = (DriverSchedule.objects
          .select_related("driver","first_choice_car","second_choice_car","assigned_car")
          .filter(work_date__gte=date_from, work_date__lte=date_to))

    selected_work_date = None
    if work_date_str:
        try:
            selected_work_date = _date.fromisoformat(work_date_str)
            qs = qs.filter(work_date=selected_work_date)
        except ValueError:
            selected_work_date = None

    if driver_id:
        qs = qs.filter(driver_id=driver_id)

    # 车辆下拉
    raw_cars = Car.objects.exclude(status__in=["scrapped","retired","disabled"]).order_by("license_plate","name","id")
    normal_cars, maint_cars = [], []
    for c in raw_cars:
        plate = getattr(c,"license_plate",None) or getattr(c,"registration_number",None) or ""
        car_name = getattr(c,"name",None) or getattr(c,"model",None) or ""
        base_label = " / ".join([p for p in (plate,car_name) if p]) or f"ID:{c.id}"
        status    = (getattr(c,"status","") or "").strip()
        is_active = getattr(c,"is_active",True)
        is_maint  = bool(getattr(c,"is_maintaining",False))
        is_scrap  = bool(getattr(c,"is_scrapped",False))
        if is_scrap: continue
        if status in ("maintenance","repair","fixing") or is_maint:
            c.label = f"{base_label}（整備中）"; c.is_bad = True; maint_cars.append(c); continue
        if not is_active: continue
        c.label = base_label; c.is_bad = False; normal_cars.append(c)
    cars = normal_cars + maint_cars

    all_drivers  = Driver.objects.order_by("driver_code","name")
    date_choices = [date_from + timedelta(days=i) for i in range((date_to - date_from).days + 1)]

    # 自动配车按钮
    if request.POST.get("action") == "auto_assign":
        auto_date_str = request.POST.get("auto_work_date") or work_date_str
        try:
            auto_date = _date.fromisoformat(auto_date_str)
        except Exception:
            auto_date = today

        plan = auto_assign_plan_for_date(auto_date)
        setattr(request, "_auto_assign_plan", plan)

        if (request.GET.get("dryrun") or "").strip() == "1":
            messages.info(request, "これは予演結果（保存されません）です。")
            setattr(request, "_auto_assign_preview", plan["preview_rows"])
        else:
            saved = auto_assign_apply_ops(plan["assign_ops"], auto_date)
            c = plan["counts"]
            messages.success(
                request,
                f"{auto_date:%Y-%m-%d} の自動配車を反映しました（新規 {saved} 件：第1 {c['first']} / 第2 {c['second']} / 任意 {c['any']}）。"
            )
            redirect_url = f"{reverse('staffbook:schedule_list')}?group={group}"
            if driver_id:     redirect_url += f"&driver={driver_id}"
            if auto_date_str: redirect_url += f"&work_date={auto_date_str}"
            return redirect(redirect_url)

    # 行内保存（昼/夜交替规则）
    if request.method == "POST" and request.POST.get("action") != "auto_assign":
        sched_id        = request.POST.get("sched_id")
        status_v        = request.POST.get("status") or "pending"
        assigned_car_id = request.POST.get("assigned_car") or None
        admin_note      = (request.POST.get("admin_note") or "").strip()

        post_group     = request.POST.get("group", group)
        post_driver    = request.POST.get("driver") or driver_id
        post_work_date = request.POST.get("work_date") or work_date_str

        obj = DriverSchedule.objects.filter(pk=sched_id).first()
        if obj:
            obj.status = status_v
            obj.admin_note = admin_note

            if assigned_car_id:
                assigned_car_id = int(assigned_car_id)
                obj.assigned_car_id = assigned_car_id

                # 同班冲突拒绝
                same_exists = DriverSchedule.objects.filter(
                    work_date=obj.work_date, assigned_car_id=assigned_car_id, shift=(obj.shift or "").strip()
                ).exclude(pk=obj.pk).exists()
                if same_exists:
                    messages.error(request, "同一日・同一車両・同一勤種（昼/夜）が既に割当済みです。")
                    obj.assigned_car = None
                    return redirect(request.get_full_path())

                # 允许对向班并追加提醒
                opp = "night" if (obj.shift or "") == "day" else ("day" if (obj.shift or "") == "night" else None)
                cross_exists = False
                if opp:
                    cross_exists = DriverSchedule.objects.filter(
                        work_date=obj.work_date, assigned_car_id=assigned_car_id, shift=opp
                    ).exists()
                    if cross_exists:
                        if (obj.shift or "") == "day":
                            obj.admin_note = ((obj.admin_note or "") + " " + DAY_NOTICE).strip()
                        elif (obj.shift or "") == "night":
                            obj.admin_note = ((obj.admin_note or "") + " " + NIGHT_NOTICE).strip()

                # 元素 & 元数据
                match_kind = "manual"
                if obj.first_choice_car_id and obj.assigned_car_id == obj.first_choice_car_id:   match_kind = "first"
                elif obj.second_choice_car_id and obj.assigned_car_id == obj.second_choice_car_id: match_kind = "second"
                elif bool(getattr(obj, "any_car", False)):                                         match_kind = "any"

                obj.status = "approved"
                if hasattr(obj,"assigned_by"): obj.assigned_by = "manual"
                if hasattr(obj,"assigned_at"): obj.assigned_at = now()

                if "assignment_meta" in {f.name for f in DriverSchedule._meta.fields}:
                    reason = build_assign_reason(obj.driver, obj.work_date)
                    meta = {
                        "rule_version": "v1.0", "by":"manual",
                        "at": now().isoformat(timespec="seconds"),
                        "match": match_kind, "reason": reason,
                    }
                    if cross_exists:
                        meta["notice"] = DAY_NOTICE if (obj.shift or "")=="day" else NIGHT_NOTICE if (obj.shift or "")=="night" else ""
                    base_meta = getattr(obj,"assignment_meta",{}) or {}
                    base_meta.update(meta)
                    obj.assignment_meta = base_meta
            else:
                obj.assigned_car = None
                if "assignment_meta" in {f.name for f in DriverSchedule._meta.fields}:
                    base_meta = getattr(obj,"assignment_meta",{}) or {}
                    base_meta.update({"cleared": True, "at": now().isoformat(timespec="seconds")})
                    obj.assignment_meta = base_meta

            obj.save()
            messages.success(request, "スケジュールを更新しました。")

        redirect_url = f"{reverse('staffbook:schedule_list')}?group={post_group}"
        if post_driver:    redirect_url += f"&driver={post_driver}"
        if post_work_date: redirect_url += f"&work_date={post_work_date}"
        return redirect(redirect_url)

    # 分组供页面展示
    grouped = {}
    if group == "driver":
        qs = qs.order_by("driver__driver_code","work_date")
        for row in qs:
            key = f"{row.driver.driver_code} {row.driver.name}"
            grouped.setdefault(key, []).append(row)
    else:
        group = "date"
        qs = qs.order_by("work_date","driver__driver_code")
        for row in qs:
            grouped.setdefault(row.work_date, []).append(row)

    # “本日の配車/整備中/空き車両”
    dispatch_sections = []
    if selected_work_date:
        day_qs = qs.filter(work_date=selected_work_date)
        assigned_rows, used_car_ids = [], set()
        for s in day_qs:
            car = s.assigned_car or None
            if car: used_car_ids.add(car.id)
            assigned_rows.append({"car": car,"driver": s.driver,"is_rest": s.is_rest,"shift": s.shift,
                                  "admin_note": s.admin_note,"driver_note": s.note})
        if assigned_rows: dispatch_sections.append({"title":"本日の配車","rows": assigned_rows})

        maint_rows, free_rows = [], []
        for car in cars:
            status = getattr(car,"status","") or ""
            is_scrap = getattr(car,"is_scrapped",False)
            is_active = getattr(car,"is_active",True)
            if is_scrap or status in ("retired","disabled","scrapped") or not is_active: continue
            if car.id in used_car_ids: continue
            is_maint = status in ("maintenance","repair","fixing") or getattr(car,"is_maintaining",False)
            row = {"car":car,"driver":None,"is_rest":False,"shift":None,"admin_note":"","driver_note":""}
            (maint_rows if is_maint else free_rows).append(row)
        if maint_rows: dispatch_sections.append({"title":"整備中 / 修理中","rows": maint_rows})
        if free_rows:  dispatch_sections.append({"title":"空き車両","rows": free_rows})

    # 绿色面板数据（dryrun 优先）
    auto_schedule_groups = None
    if selected_work_date:
        is_dryrun = (request.GET.get("dryrun") or "").strip() == "1"
        plan_obj = getattr(request,"_auto_assign_plan",None) if is_dryrun else None
        if plan_obj:
            auto_schedule_groups = _build_green_from_plan(plan_obj, cars)
        else:
            day_qs_full = (DriverSchedule.objects
                           .select_related("driver","assigned_car")
                           .filter(work_date=selected_work_date))
            auto_schedule_groups = _build_green_from_assigned(day_qs_full, cars)

    ctx = {
        "date_from": date_from, "date_to": date_to,
        "group": group, "grouped": grouped,
        "cars": cars, "all_drivers": all_drivers, "date_choices": date_choices,
        "selected_driver": int(driver_id) if driver_id else None,
        "selected_work_date": selected_work_date,
        "dispatch_sections": dispatch_sections,
        "auto_assign_preview": getattr(request, "_auto_assign_preview", None),
        "auto_schedule_groups": auto_schedule_groups,
        "jp_selected_date": fmt_jp_date(selected_work_date) if selected_work_date else "",
    }
    return render(request, "staffbook/schedule_list.html", ctx)
# ===== END VIEW schedule_list_view (留存代码-结束) =====


# ===== 绿色板工具（带 state/shift） =====
from collections import defaultdict

def _car_model_text(car) -> str:
    """尽量从车型相关字段里拿“车型名”"""
    for f in ("model", "name", "car_model", "car_type", "category", "group"):
        v = getattr(car, f, None)
        if v:
            return str(v)
    return ""

def _car_group_title(car) -> str:
    """
    通过 group/category/model/name 等文本来推断 A/B/C/D；识别日文/英文常见写法
    """
    txt = " ".join([
        str(getattr(car, f, "") or "")
        for f in ("group", "category", "model", "name", "car_type")
    ]).lower()

    # A アルファード
    if ("アルファ" in txt) or ("アルファード" in txt) or ("alphard" in txt) or ("alpha" in txt):
        return "A アルファ"

    # B ヴォクシー等
    if ("ヴォクシー" in txt) or ("ボクシー" in txt) or ("voxy" in txt) \
        or ("ノア" in txt) or ("noah" in txt) \
        or ("セレナ" in txt) or ("serena" in txt) \
        or ("ステップ" in txt) or ("stepwgn" in txt) \
        or ("ウォクシー" in txt):
        return "B ウォクシー等"

    # C カムリ
    if ("カムリ" in txt) or ("camry" in txt):
        return "C カムリ"

    # D シエンタ
    if ("シエンタ" in txt) or ("sienta" in txt):
        return "D シエンタ"

    return "その他"

def _car_num_label(car) -> str:
    """在车号后面拼上车型（若识别到），例：'3523 / アルファード'"""
    plate = (getattr(car, "license_plate", None)
                or getattr(car, "registration_number", None)
                or getattr(car, "name", None)
                or f"ID:{car.id}")
    model = _car_model_text(car)
    return f"{plate} / {model}" if model else str(plate)

def _build_green_from_plan(plan, cars_all):
    cars_by_id = {c.id: c for c in cars_all}
    groups = defaultdict(list)

    # 暂存：同一辆车的条目，后面看是否昼夜皆有
    items_by_car = defaultdict(list)

    for sched_id, car_id, shift, why in plan.get("assign_ops", []):
        car = cars_by_id.get(car_id)
        if not car:
            continue
        entry = {
            "car_id": car_id,
            "num": _car_num_label(car),
            "driver": "",          # 预演：司机名通常在上方卡片显示，这里保持空
            "shift": (shift or ""),
            "state": "assigned",
            "title": _format_reason_tooltip(why),  # 先放推荐理由，稍后如有昼夜交替再叠加提醒
        }
        items_by_car[car_id].append(entry)

    # 还要把未使用/维修的车放进去（不参与昼夜判断）
    used_ids = set(items_by_car.keys())
    for c in cars_all:
        if getattr(c, "is_scrapped", False):  continue
        if c.id in used_ids:                 continue
        status = (getattr(c, "status", "") or "").lower()
        is_maint = status in ("maintenance","repair","fixing") or getattr(c, "is_maintaining", False)
        entry = {
            "car_id": c.id,
            "num": _car_num_label(c),
            "driver": "🛠️ 维修中" if is_maint else "未使用",
            "shift": "",
            "state": "maint" if is_maint else "free",
            "title": "整備中" if is_maint else "",
        }
        items_by_car[c.id].append(entry)

    # 昼夜交替 → 给两边都追加各自提醒
    for car_id, items in items_by_car.items():
        shifts = { (it.get("shift") or "").strip() for it in items if it["state"] == "assigned" }
        if "day" in shifts and "night" in shifts:
            for it in items:
                if it["state"] != "assigned":
                    continue
                if (it.get("shift") or "") == "day":
                    it["title"] = ((it.get("title") or "") + " " + DAY_NOTICE).strip()
                elif (it.get("shift") or "") == "night":
                    it["title"] = ((it.get("title") or "") + " " + NIGHT_NOTICE).strip()

    # 按分组输出
    for items in items_by_car.values():
        for it in items:
            # 找回车对象以决定分组标题
            cid = it["car_id"]
            car = cars_by_id.get(cid)
            gtitle = _car_group_title(car) if car else "その他"
            groups[gtitle].append({k:v for k,v in it.items() if k!="car_id"})

    order = ["A アルファ", "B ウォクシー等", "C カムリ", "D シエンタ", "その他"]
    return [(g, groups[g]) for g in order if groups.get(g)]

def _build_green_from_assigned(day_qs_full, cars_all):
    groups = defaultdict(list)
    items_by_car = defaultdict(list)
    cars_by_id = {c.id: c for c in cars_all}

    for s in day_qs_full.select_related("assigned_car", "driver"):
        car = s.assigned_car
        if not car:
            continue
        meta = getattr(s, "assignment_meta", {}) or {}
        title = meta.get("notice") or _format_reason_tooltip(meta.get("reason"))
        entry = {
            "car_id": car.id,
            "num": _car_num_label(car),
            "driver": s.driver.name if s.driver else "",
            "shift": s.shift or "",
            "state": "assigned",
            "title": title or "",
        }
        items_by_car[car.id].append(entry)

    # 补齐未使用/维修
    used_ids = set(items_by_car.keys())
    for c in cars_all:
        if getattr(c, "is_scrapped", False):  continue
        if c.id in used_ids:                 continue
        status = (getattr(c, "status", "") or "").lower()
        is_maint = status in ("maintenance","repair","fixing") or getattr(c, "is_maintaining", False)
        entry = {
            "car_id": c.id,
            "num": _car_num_label(c),
            "driver": "🛠️ 维修中" if is_maint else "未使用",
            "shift": "",
            "state": "maint" if is_maint else "free",
            "title": "整備中" if is_maint else "",
        }
        items_by_car[c.id].append(entry)

    # 昼夜交替 → 两侧都追加
    for car_id, items in items_by_car.items():
        shifts = { (it.get("shift") or "").strip() for it in items if it["state"] == "assigned" }
        if "day" in shifts and "night" in shifts:
            for it in items:
                if it["state"] != "assigned":
                    continue
                if (it.get("shift") or "") == "day":
                    it["title"] = ((it.get("title") or "") + " " + DAY_NOTICE).strip()
                elif (it.get("shift") or "") == "night":
                    it["title"] = ((it.get("title") or "") + " " + NIGHT_NOTICE).strip()

    # 分组输出
    for items in items_by_car.values():
        for it in items:
            cid = it["car_id"]
            car = cars_by_id.get(cid)
            gtitle = _car_group_title(car) if car else "その他"
            groups[gtitle].append({k:v for k,v in it.items() if k!="car_id"})

    order = ["A アルファ", "B ウォクシー等", "C カムリ", "D シエンタ", "その他"]
    return [(g, groups[g]) for g in order if groups.get(g)]
# ==============================================================
# END: 管理员 / 事务员：查看所有司机提交的“日期+希望车両”
# ==============================================================


@login_required
def schedule_delete_view(request, sched_id):
    """
    司机本人删除自己的提交（POST）
    """
    try:
        me = Driver.objects.get(user=request.user)
    except Driver.DoesNotExist:
        me = None

    sched = get_object_or_404(DriverSchedule, pk=sched_id)

    # 只能删自己的
    if not me or sched.driver_id != me.id:
        messages.error(request, "このスケジュールを削除する権限がありません。")
        return redirect("staffbook:my_reservations")  # 或你想回的页面

    if request.method == "POST":
        wd = sched.work_date
        sched.delete()
        messages.success(request, f"{wd:%Y-%m-%d} のスケジュールを削除しました。")
        # ✅ 删除后回到确认页
        return redirect("staffbook:my_reservations")

    return redirect("staffbook:my_reservations")  # 你的确认页 url 名称


# ✅ 员工列表（管理员）
@user_passes_test(is_staffbook_admin)
def driver_list(request):
    keyword = request.GET.get('keyword', '').strip()
    show_all = request.GET.get('show_all') == '1'  # ✅ 新增：控制是否显示退職者

    # 初步筛选
    drivers_qs = Driver.objects.all()
    if not show_all:
        drivers_qs = drivers_qs.exclude(employ_type='3')  # ✅ 默认排除退職者

    if keyword:
        drivers_qs = drivers_qs.filter(
            Q(name__icontains=keyword) | Q(driver_code__icontains=keyword)
        )

    driver_list = []
    for driver in drivers_qs:
        missing = []
        if driver.is_foreign:
            if not driver.residence_card_image:
                missing.append("在留カード")
            if not driver.work_permission_confirmed:
                missing.append("就労資格")
        if not driver.has_health_check:
            missing.append("健康診断")
        if not driver.has_residence_certificate:
            missing.append("住民票")
        if not driver.has_license_copy:
            missing.append("免許コピー")

        driver_list.append({
            'driver': driver,
            'missing_flags': missing,
        })

    return render(request, 'staffbook/driver_list.html', {
        'driver_list': driver_list,
        'keyword': keyword,
        'show_all': show_all,  # ✅ 传入模板判断切换按钮
    })

# ✅ 新增：司机资料提交状况一览
@login_required
def driver_documents_status(request):
    if not request.user.is_authenticated or not hasattr(request.user, 'staff_profile'):
        return redirect('home')

    drivers = Driver.objects.filter(
        has_health_check=False
    ) | Driver.objects.filter(
        has_residence_certificate=False
    ) | Driver.objects.filter(
        has_tax_form=False
    ) | Driver.objects.filter(
        has_license_copy=False
    )

    drivers = drivers.distinct().order_by('driver_code')

    return render(request, 'staffbook/driver_documents.html', {
        'drivers': drivers,
    })

# ✅ 新增员工
@user_passes_test(is_staffbook_admin)
def driver_create(request):
    if request.method == 'POST':
        form = DriverForm(request.POST)
        if form.is_valid():
            driver = form.save()
            return redirect('staffbook:driver_basic_info', driver_id=driver.id)
    else:
        form = DriverForm()
    return render(request, 'staffbook/driver_create.html', {'form': form, 'is_create': True})

# ✅ 编辑员工
@user_passes_test(is_staffbook_admin)
def driver_edit(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    DrivingExpFormSet = inlineformset_factory(Driver, DrivingExperience, fields="__all__", extra=1, can_delete=True)
    DriverInsuranceFormSet = inlineformset_factory(Driver, DriverInsurance, fields="__all__", extra=1, can_delete=True)
    FamilyFormSet = inlineformset_factory(Driver, FamilyMember, fields="__all__", extra=1, can_delete=True)

    if request.method == 'POST':
        form = DriverForm(request.POST, request.FILES, instance=driver)
        exp_formset = DrivingExpFormSet(request.POST, instance=driver)
        ins_formset = DriverInsuranceFormSet(request.POST, instance=driver)
        fam_formset = FamilyFormSet(request.POST, instance=driver)
        if form.is_valid() and exp_formset.is_valid() and ins_formset.is_valid() and fam_formset.is_valid():
            form.save()
            exp_formset.save()
            ins_formset.save()
            fam_formset.save()
            return redirect('staffbook:driver_basic_info', driver_id=driver.id)
    else:
        form = DriverForm(instance=driver)
        exp_formset = DrivingExpFormSet(instance=driver)
        ins_formset = DriverInsuranceFormSet(instance=driver)
        fam_formset = FamilyFormSet(instance=driver)

    return render(request, 'staffbook/driver_edit.html', {
        'form': form,
        'exp_formset': exp_formset,
        'ins_formset': ins_formset,
        'fam_formset': fam_formset,
        'driver': driver,
    })

# ----- basic -----
# 个人主页+台账
@user_passes_test(is_staffbook_admin)
def driver_basic_info(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)

    d = driver
    is_foreign = getattr(d, "is_foreign", False)  # 外国籍の人は在留カード/就労資格を判定

    missing_items = []
    edit_url = reverse('staffbook:driver_basic_edit', args=[driver.id])

    if driver.is_foreign:
        if not driver.residence_card_image:
            missing_items.append(("在留カード未上传", f"{edit_url}#residence-card"))
        if not driver.work_permission_confirmed:
            missing_items.append(("就労資格未確認", f"{edit_url}#work-permission"))

    if not driver.has_health_check:
        missing_items.append(("健康診断書未提出", f"{edit_url}#health-check"))
    if not driver.has_residence_certificate:
        missing_items.append(("住民票未提出", f"{edit_url}#juminhyo"))
    if not driver.has_license_copy:
        missing_items.append(("免許証コピー未提出", f"{edit_url}#license-copy"))

    # ====== 入社資料デフォルト清单（公司側）======
    # ⛳ 请确认右侧 getattr(...) 中的布尔字段与你的 Driver 模型一致
    company_docs = [
        {"name": "雇用契約書の作成・署名",      "submitted": getattr(d, "signed_employment_contract", False),         "anchor": "company-1"},
        {"name": "労働条件通知書の交付",        "submitted": getattr(d, "gave_labor_conditions", False),               "anchor": "company-2"},
        {"name": "就業規則・安全衛生の説明",    "submitted": getattr(d, "explained_rules_safety", False),              "anchor": "company-3"},
        {"name": "社会保険・厚生年金加入手続",  "submitted": getattr(d, "completed_social_insurance", False),          "anchor": "company-4"},
        {"name": "雇用保険加入手続",            "submitted": getattr(d, "completed_employment_insurance", False),      "anchor": "company-5"},
        {"name": "労災保険手続",                "submitted": getattr(d, "completed_worker_accident_insurance", False), "anchor": "company-6"},
        {"name": "厚生年金基金手続",            "submitted": getattr(d, "completed_pension_fund", False),              "anchor": "company-7"},
        {"name": "社内システムID発行",          "submitted": getattr(d, "created_system_account", False),              "anchor": "company-8"},
        {"name": "研修・マニュアルの周知",       "submitted": getattr(d, "notified_training_manual", False),            "anchor": "company-9"},
        {"name": "経費・交通費申請フロー説明",  "submitted": getattr(d, "explained_expense_flow", False),              "anchor": "company-10"},
    ]

    # ====== 入社資料デフォルト清单（社員側）======
    employee_docs = [
        {"name": "履歴書・職務経歴書",                          "submitted": getattr(d, "has_resume", False),               "anchor": "employee-1"},
        {"name": "運転免許証コピー",                            "submitted": getattr(d, "has_license_copy", False),         "anchor": "employee-2"},
        {"name": "住民票（本籍地記載・マイナンバーなし）",      "submitted": getattr(d, "has_residence_certificate", False), "anchor": "employee-3"},
        {"name": "健康診断書",                                  "submitted": getattr(d, "has_health_check", False),         "anchor": "employee-4"},
        {"name": "給与振込先口座情報",                          "submitted": getattr(d, "has_bank_info", False),            "anchor": "employee-5"},
        {"name": "マイナンバー（番号は保存しない・提出のみ）",  "submitted": getattr(d, "has_my_number_submitted", False),  "anchor": "employee-6"},
        {"name": "雇用保険被保険者証",                          "submitted": getattr(d, "has_koyo_hihokenshasho", False),   "anchor": "employee-7"},
        {"name": "年金手帳／基礎年金番号届出（番号保存なし）",  "submitted": getattr(d, "has_pension_proof", False),        "anchor": "employee-8"},
        # 外国籍のみ：対象外であれば “提出済み扱い” にして未提出に出さない
        {"name": "就労資格確認（外国籍のみ）",                   "submitted": (not is_foreign) or getattr(d, "work_permission_confirmed", False), "anchor": "employee-9"},
        {"name": "在留カード（外国籍のみ）",                     "submitted": (not is_foreign) or getattr(d, "has_zairyu_card", False),            "anchor": "employee-10"},
        {"name": "在留カード画像のアップロード（外国籍のみ）",   "submitted": (not is_foreign) or bool(getattr(d, "residence_card_image", None)),  "anchor": "employee-11"},
    ]

    # —— 生成编辑页链接（用于 ❌ 跳转）——
    edit_url = reverse('staffbook:driver_basic_edit', args=[driver.id])

    # —— 左右两列对齐行（模板遍历 paired_rows 渲染）——
    paired_rows = list(
        zip_longest(
            company_docs,
            employee_docs,
            fillvalue={"name": "", "submitted": None, "anchor": ""}
        )
    )

    # —— 未提出清单（用于详情页上方的黄色提示框）——
    missing_items = []
    for item in company_docs:
        if item["submitted"] is False:
            missing_items.append((item["name"], f"{edit_url}#{item['anchor']}"))
    for item in employee_docs:
        if item["submitted"] is False:
            missing_items.append((item["name"], f"{edit_url}#{item['anchor']}"))

    return render(request, 'staffbook/driver_basic_info.html', {
        'driver': driver,
        'paired_rows': paired_rows,
        'edit_url': edit_url,
        'main_tab': 'basic',
        'tab': 'basic',
        'missing_items': missing_items,
    })

@user_passes_test(is_staffbook_admin)
def driver_basic_edit(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)

    if request.method == 'POST':
        print('DEBUG POST employ_type =', request.POST.get('employ_type'))
        print('DEBUG POST resigned_date =', request.POST.get('resigned_date'))
        form = DriverBasicForm(request.POST, request.FILES, instance=driver)
        if form.is_valid():
            obj = form.save()
            print('DEBUG SAVED resigned_date =', obj.resigned_date)
            messages.success(request, "基本データを保存しました。")
            return redirect('staffbook:driver_basic_info', driver_id=driver.id)
        else:
            print("[DEBUG] DriverBasicForm errors:", form.errors)
            messages.error(request, "入力内容をご確認ください。")
    else:
        form = DriverBasicForm(instance=driver)

    # === 入社資料 清单（布尔字段快速版）========================
    # 用 getattr 避免字段尚未创建时报 AttributeError
    d = driver
    employee_docs = [
        {"name": "履歴書・職務経歴書", "submitted": getattr(d, "has_resume", False)},
        {"name": "運転免許証コピー", "submitted": getattr(d, "has_license_copy", False)},
        {"name": "住民票（本籍地記載・マイナンバーなし）", "submitted": getattr(d, "has_juminhyo", False)},
        {"name": "健康診断書", "submitted": getattr(d, "has_health_check", False)},
        {"name": "給与振込先口座情報", "submitted": getattr(d, "has_bank_info", False)},
        {"name": "マイナンバー（番号は保存しない・提出のみ）", "submitted": getattr(d, "has_my_number_submitted", False)},
        {"name": "雇用保険被保険者証", "submitted": getattr(d, "has_koyo_hihokenshasho", False)},
        {"name": "年金手帳/基礎年金番号の届出（番号保存なし）", "submitted": getattr(d, "has_pension_proof", False)},
        {"name": "在留カード（外国籍）", "submitted": getattr(d, "has_zairyu_card", False)},
    ]
    company_docs = [
        {"name": "入社資料一式交付", "submitted": getattr(d, "gave_joining_pack", False)},
        {"name": "社会保険・年金加入手続", "submitted": getattr(d, "completed_social_insurance", False)},
        {"name": "雇用契約書 締結", "submitted": getattr(d, "signed_employment_contract", False)},
        {"name": "就業規則・安全衛生 説明", "submitted": getattr(d, "explained_rules_safety", False)},
        {"name": "社内システムID 発行", "submitted": getattr(d, "created_system_account", False)},
        {"name": "研修/マニュアル 周知", "submitted": getattr(d, "notified_training_manual", False)},
        {"name": "経費/交通費 申請説明", "submitted": getattr(d, "explained_expense_flow", False)},
    ]
    # （可选）业務用
    ops_docs = [
        {"name": "Uber アカウント", "submitted": getattr(d, "has_uber_account", False)},
        {"name": "DiDi アカウント", "submitted": getattr(d, "has_didi_account", False)},
        {"name": "社名章/名札 交付", "submitted": getattr(d, "has_company_name_tag", False)},
        {"name": "配車システム アカウント", "submitted": getattr(d, "has_dispatch_account", False)},
    ]
    # ==========================================================

    return render(request, 'staffbook/driver_basic_edit.html', {
        'form': form,
        'driver': driver,
        'main_tab': 'basic',
        'tab': 'basic',
        'employee_docs': employee_docs,
        'company_docs': company_docs,
        'ops_docs': ops_docs,      # 模板用了再显示；没用就无视
    })


#個人情報
@user_passes_test(is_staffbook_admin)
def driver_personal_info(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    insurance_fields = [
        ('健康保险', driver.health_insurance_no),
        ('厚生年金保险', driver.pension_no),
        ('雇用保险', driver.employment_insurance_no),
        ('労災保险', driver.workers_insurance_no),
        ('厚生年金基金', driver.pension_fund_no),
    ]
    return render(request, 'staffbook/driver_personal_info.html', {
        'driver': driver,
        'main_tab': 'basic',   # 例如‘basic’或‘driving’
        'tab': 'personal',     # 当前二级tab
        # 这里可以继续添加其它需要传到模板的变量，如：
        # 'form': form,
        # 'active_tab': 'personal',
        # 'title': '司机个人信息',
})

@user_passes_test(is_staffbook_admin)
def driver_personal_edit(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    if request.method == 'POST':
        form = DriverPersonalInfoForm(request.POST, request.FILES, instance=driver)
        if form.is_valid():
            form.save()
            messages.success(request, "个人信息已保存！")
            return redirect('staffbook:driver_personal_info', driver_id=driver.id)
    else:
        form = DriverPersonalInfoForm(instance=driver)
    return render(request, 'staffbook/driver_personal_edit.html', {
        'driver': driver,
        'form': form,
        'main_tab': 'basic',
        'tab': 'personal',
    })

#签证在留
@user_passes_test(is_staffbook_admin)
def driver_certificate_info(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    return render(request, 'staffbook/driver_certificate_info.html', {
        'driver': driver,
        'main_tab': 'basic',
        'tab': 'certificate',
        'today': datetime.date.today(),  # ⬅ 用于模板中比较日期
    })

@user_passes_test(is_staffbook_admin)
def driver_certificate_edit(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)

    if request.method == 'POST':
        form = DriverCertificateForm(request.POST, request.FILES, instance=driver)
        if form.is_valid():
            form.save()
            return redirect('staffbook:driver_certificate_info', driver_id=driver.id)
    else:
        form = DriverCertificateForm(instance=driver)

    # 签证即将到期提醒
    alert_expiry = False
    if driver.residence_expiry:
        delta = (driver.residence_expiry - datetime.date.today()).days
        if delta <= 30:
            alert_expiry = True

    return render(request, 'staffbook/driver_certificate_edit.html', {
        'driver': driver,
        'form': form,
        'alert_expiry': alert_expiry,
        'main_tab': 'basic',
        'tab': 'certificate',
    })


@user_passes_test(is_staffbook_admin)
def driver_history_info(request, driver_id):
    """
    履歴查看页：从 Driver.history_data(JSONField) 读取并只读展示
    """
    driver = get_object_or_404(Driver, pk=driver_id)
    data = driver.history_data or {}
    education = data.get("education", [])
    jobs = data.get("jobs", [])
    return render(request, "staffbook/driver_history_info.html", {
        "driver": driver,
        "education": education,
        "jobs": jobs,
        "tab": "history",   # 二级tab高亮
    })

#履歴変更記録
@user_passes_test(is_staffbook_admin)
def driver_history_edit(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)

    def _load_lists():
        data = driver.history_data or {}
        return data.get("education", []), data.get("jobs", [])

    education, jobs = _load_lists()

    if request.method == "POST":
        errors = []

        def collect(prefix):
            """
            收集前端提交的某一类行（edu 或 job）
            - 兼容中间索引被删除的“空洞”（不再用 while 连续自增）
            - 后端强制补充 category，避免前端缺失导致表单校验失败
            """
            # 找到本类行里所有 index（根据 -place 键）
            indices = sorted({
                int(k.split("-")[1])
                for k in request.POST.keys()
                if k.startswith(f"{prefix}-") and k.endswith("-place")
            })

            rows = []
            for idx in indices:
                data = {
                    "category": "edu" if prefix == "edu" else "job",  # ✅ 关键：后端补上
                    "start_year":  request.POST.get(f"{prefix}-{idx}-start_year"),
                    "start_month": request.POST.get(f"{prefix}-{idx}-start_month"),
                    "end_year":    request.POST.get(f"{prefix}-{idx}-end_year"),
                    "end_month":   request.POST.get(f"{prefix}-{idx}-end_month"),
                    "place":       request.POST.get(f"{prefix}-{idx}-place") or "",
                    "note":        request.POST.get(f"{prefix}-{idx}-note") or "",
                }

                form = HistoryEntryForm(data)
                if form.is_valid():
                    c = form.cleaned_data

                    def ym(y, m):
                        if not y or not m:
                            return ""
                        return f"{int(y):04d}-{int(m):02d}"

                    rows.append({
                        "start": ym(c["start_year"], c["start_month"]),
                        "end":   ym(c.get("end_year"), c.get("end_month")),
                        "place": c["place"],
                        "note":  c.get("note", ""),
                    })
                else:
                    # 记录错误，最后统一提示
                    errors.append((prefix, idx, form.errors))
            return rows

        education = collect("edu")
        jobs      = collect("job")

        if errors:
            messages.error(request, "请检查输入项。")
            # 带回成功解析的行（有错的行因为无效，不再带回）
            return render(request, "staffbook/driver_history_edit.html", {
                "driver": driver,
                "education": education,
                "jobs": jobs,
                "post_errors": errors,
            })

        # ✅ 全部合法：写回 JSONField
        driver.history_data = {"education": education, "jobs": jobs}
        driver.save()
        messages.success(request, "履歴書已保存。")
        return redirect("staffbook:driver_history_info", driver_id=driver.id)

    # GET：渲染
    return render(request, "staffbook/driver_history_edit.html", {
        "driver": driver,
        "education": education,
        "jobs": jobs,
    })
# === 替换结束 ===


# 緊急連絡先
@user_passes_test(is_staffbook_admin)
def driver_emergency_info(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    # 你可以先不传实际数据，先做一个空模板
    return render(request, 'staffbook/driver_emergency_info.html', {
        'driver': driver,
        'main_tab': 'basic',
        'tab': 'emergency'
    })

@user_passes_test(is_staffbook_admin)
def driver_emergency_edit(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    if request.method == 'POST':
        form = DriverEmergencyInfoForm(request.POST, request.FILES, instance=driver)
        if form.is_valid():
            form.save()
            messages.success(request, "緊急連絡先已保存！")
            return redirect('staffbook:driver_emergency_info', driver_id=driver.id)
    else:
        form = DriverEmergencyInfoForm(instance=driver)
    return render(request, 'staffbook/driver_emergency_edit.html', {
        'driver': driver,
        'form': form,
        'main_tab': 'basic',
        'tab': 'emergency',
    })


# 员工驾驶证信息
@user_passes_test(is_staffbook_admin)
def driver_license_info(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    # get_or_create: 没有就创建一个
    license, created = DriverLicense.objects.get_or_create(driver=driver)
    all_license_types = LicenseType.objects.all()
    return render(request, 'staffbook/driver_license_info.html', {
        'driver': driver,
        'license': license,
        'main_tab': 'driving',  # 当前大类
        'tab': 'license',  # 当前二级tab
    })

@user_passes_test(is_staffbook_admin)
def driver_license_edit(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    # get_or_create: 没有就创建一个
    license, created = DriverLicense.objects.get_or_create(driver=driver)
    if request.method == 'POST':
        form = DriverLicenseForm(request.POST, request.FILES, instance=license)
        if form.is_valid():
            form.save()
            return redirect('staffbook:driver_license_info', driver_id=driver.id)
    else:
        form = DriverLicenseForm(instance=license)
    return render(request, 'staffbook/driver_license_edit.html', {
        'form': form,
        'driver': driver,
        'license': license,
    })

#運転経験
@user_passes_test(is_staffbook_admin)
def driver_experience_info(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    experiences = DrivingExperience.objects.filter(driver=driver)
    return render(request, 'staffbook/driver_experience_info.html', {
        'driver': driver,
        'experiences': experiences,
        'main_tab': 'driving',  # 一级tab激活"運転情報"
        'tab': 'experience',    # 二级tab激活"運転経験"
    })

def driver_experience_edit(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    ExperienceFormSet = inlineformset_factory(Driver, DrivingExperience, fields="__all__", extra=1, can_delete=True)
    if request.method == 'POST':
        formset = ExperienceFormSet(request.POST, instance=driver)
        if formset.is_valid():
            formset.save()
            return redirect('staffbook:driver_experience_info', driver_id=driver.id)
    else:
        formset = ExperienceFormSet(instance=driver)
    return render(request, 'staffbook/driver_experience_edit.html', {
        'formset': formset,
        'driver': driver,
        'main_tab': 'driving',
        'tab': 'experience',
    })

#資格
@user_passes_test(is_staffbook_admin)
def driver_qualification_info(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    qualification, _ = Qualification.objects.get_or_create(driver=driver)
    return render(request, 'staffbook/driver_qualification_info.html', {
        'driver': driver,
        'qualification': qualification,
        'main_tab': 'driving',
        'tab': 'qualification',
    })

@user_passes_test(is_staffbook_admin)
def driver_qualification_edit(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    qualification, _ = Qualification.objects.get_or_create(driver=driver)
    if request.method == 'POST':
        form = QualificationForm(request.POST, instance=qualification)
        if form.is_valid():
            form.save()
            return redirect('staffbook:driver_qualification_info', driver_id=driver.id)
    else:
        form = QualificationForm(instance=qualification)
    return render(request, 'staffbook/driver_qualification_edit.html', {
        'form': form,
        'driver': driver,
        'main_tab': 'driving',
        'tab': 'qualification',
    })

#適性診断
@user_passes_test(is_staffbook_admin)
def driver_aptitude_info(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    aptitude, created = Aptitude.objects.get_or_create(driver=driver)
    return render(request, 'staffbook/driver_aptitude_info.html', {
        'driver': driver,
        'aptitude': aptitude,
        'main_tab': 'driving',
        'tab': 'aptitude',
    })

@user_passes_test(is_staffbook_admin)
def driver_aptitude_edit(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    aptitude, created = Aptitude.objects.get_or_create(driver=driver)
    if request.method == 'POST':
        form = aptitudeForm(request.POST, instance=aptitude)
        if form.is_valid():
            form.save()
            return redirect('staffbook:driver_aptitude_info', driver_id=driver.id)
    else:
        form = AptitudeForm(instance=aptitude)
    return render(request, 'staffbook/driver_aptitude_edit.html', {
        'form': form,
        'driver': driver,
        'main_tab': 'driving',
        'tab': 'aptitude',
    })


#賞罰
@user_passes_test(is_staffbook_admin)
def driver_rewards_info(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    rewards, created = Reward.objects.get_or_create(driver=driver)
    return render(request, 'staffbook/driver_rewards_info.html', {
        'driver': driver,
        'rewards': rewards,
        'main_tab': 'driving',
        'tab': 'rewards',
    })

@user_passes_test(is_staffbook_admin)
def driver_rewards_edit(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    rewards, created = Reward.objects.get_or_create(driver=driver)
    if request.method == 'POST':
        form = RewardForm(request.POST, instance=rewards)
        if form.is_valid():
            form.save()
            return redirect('staffbook:driver_rewards_info', driver_id=driver.id)
    else:
        form = RewardForm(instance=rewards)
    return render(request, 'staffbook/driver_rewards_edit.html', {
        'form': form,
        'driver': driver,
        'main_tab': 'driving',
        'tab': 'rewards',
    })


#事故・違反
@user_passes_test(is_staffbook_admin)
def driver_accident_info(request, driver_id):
    # 1. 拿到司机实例
    driver = get_object_or_404(Driver, pk=driver_id)
    # 事故记录通常会有多条，这里假设你只编辑最新一条，或者由 URL 传入具体的 accident_id
    # 2. 列出该司机的所有事故记录（QuerySet），按发生日期倒序
    accidents = Accident.objects.filter(driver=driver).order_by('-happened_at')
    # 3. 渲染模板
    return render(request, 'staffbook/driver_accident_info.html', {
        'driver': driver,
        'accidents': accidents,
        'main_tab': 'driving',
        'tab': 'accident',
    })

@user_passes_test(is_staffbook_admin)
def driver_accident_edit(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    AccidentFormSet = inlineformset_factory(Driver, Accident, form=AccidentForm, extra=1, can_delete=True)
    if request.method == 'POST':
        formset = AccidentFormSet(request.POST, instance=driver)
        if formset.is_valid():
            formset.save()
            return redirect('staffbook:driver_accident_info', driver_id=driver.id)
    else:
        formset = AccidentFormSet(instance=driver)
    return render(request, 'staffbook/driver_accident_edit.html', {
        'formset': formset,
        'driver': driver,
        'main_tab': 'driving',
        'tab': 'accident',
    })


#指導教育
@user_passes_test(is_staffbook_admin)
def driver_education_info(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    education, created = Education.objects.get_or_create(driver=driver)
    return render(request, 'staffbook/driver_education_info.html', {
        'driver': driver,
        'education': education,
        'main_tab': 'driving',
        'tab': 'education',
    })

@user_passes_test(is_staffbook_admin)
def driver_education_edit(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    education, created = Education.objects.get_or_create(driver=driver)
    if request.method == 'POST':
        form = EducationForm(request.POST, instance=education)
        if form.is_valid():
            form.save()
            return redirect('staffbook:driver_education_info', driver_id=driver.id)
    else:
        form = HealthForm(instance=health)
    return render(request, 'staffbook/driver_education_edit.html', {
        'form': form,
        'driver': driver,
        'main_tab': 'driving',
        'tab': 'education',
    })


#健康診断
@user_passes_test(is_staffbook_admin)
def driver_health_info(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    # 筛选出该司机的“健康”保险记录
    health_insurances = Insurance.objects.filter(driver=driver, kind='health')
    return render(request, 'staffbook/driver_health_info.html', {
        'driver': driver,
        'insurances': health_insurances,
        'main_tab': 'driving',
        'tab': 'health',
    })

@user_passes_test(is_staffbook_admin)
def driver_health_edit(request, driver_id, ins_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    insurance = get_object_or_404(Insurance, pk=ins_id, driver=driver)
    if request.method == 'POST':
        form = InsuranceForm(request.POST, instance=insurance)
        if form.is_valid():
            form.save()
            return redirect('staffbook:driver_health_info', driver_id=driver.id)
    else:
        form = InsuranceForm(instance=insurance)
    return render(request, 'staffbook/driver_health_edit.html', {
        'form': form,
        'driver': driver,
        'main_tab': 'driving',
        'tab': 'health',
    })

# 保险信息
@user_passes_test(is_staffbook_admin)
def driver_pension_info(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    pensions = Pension.objects.filter(driver=driver)
    return render(request, 'staffbook/driver_pension_info.html', {
        'driver': driver,
        'pensions': pensions,
        'main_tab': 'insurance',
        'tab': 'insurance',
        'sub_tab': 'pension',
    })

@user_passes_test(is_staffbook_admin)
def driver_pension_edit(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)

    # 用 ModelFormSet 一次性编辑多条记录
    PensionFormSet = modelformset_factory(Insurance, form=PensionForm, extra=0)
    qs = Pension.objects.filter(driver=driver)

    if request.method == 'POST':
        formset = PensionFormSet(request.POST, queryset=qs)
        if formset.is_valid():
            pension = formset.save(commit=False)
            for ins in pension:
                ins.driver = driver
                ins.save()
            return redirect('staffbook:driver_pension_info', driver_id=driver.id)
    else:
        formset = PensionFormSet(queryset=qs)

    return render(request, 'staffbook/driver_pension_edit.html', {
        'driver': driver,
        'form': form,
        'main_tab': 'insurance',
        'tab': 'pension',
    })



@user_passes_test(is_staffbook_admin)
def driver_health_insurance_info(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    # 拿到健康保险相关记录
    healths = Insurance.objects.filter(driver=driver, kind='health')
    return render(request, 'staffbook/driver_health_insurance_info.html', {
        'driver': driver,
        'insurances': healths,
        'main_tab': 'insurance',   # 让一级“保険・税務”被高亮
        'tab': 'insurance',        # （如果二级也用 tab 判断，可以同设）
        'sub_tab': 'health',       # 新增：告诉模板，二级要高亮“health”
    })


@user_passes_test(is_staffbook_admin)
def driver_employment_insurance_info(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    employment_ins = Insurance.objects.filter(driver=driver, kind='employment')
    return render(request, 'staffbook/driver_employment_insurance_info.html', {
        'driver': driver,
        'insurances': employment_ins,
        'main_tab': 'insurance',
        'tab': 'insurance',
        'sub_tab': 'employment',
    })

@user_passes_test(is_staffbook_admin)
def driver_tax_info(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    taxes = Insurance.objects.filter(driver=driver, kind='tax')
    return render(request, 'staffbook/driver_tax_info.html', {
        'driver': driver,
        'insurances': taxes,
        'main_tab': 'insurance',
        'tab': 'insurance',
        'sub_tab': 'tax',          # ← 模板里判断用的就是 'tax'
    })


@user_passes_test(is_staffbook_admin)
def driver_salary(request, driver_id):
    #import datetime as _dt  # ← 加这一行，确保本函数总能拿到“模块”
    """
    給与情報：勤怠 / 支給 / 控除
    - 上部情報：売上対象月(前月)・当月売上(不含税)・分段控除
    - 控除タブ：progressive_fee を只読表示。保存時は当月レコードへ強制反映（Model.save() 側の合計再計算を起動）
    - edit モード：sub パラメータに応じて該当フィールドのみレンダリング
    """
    driver = get_object_or_404(Driver, pk=driver_id)

    # -------- URL パラメータ --------
    sub_tab   = request.GET.get('sub', 'attendance')   # attendance / payment / deduction
    mode      = request.GET.get('mode', 'view')        # view / edit
    month_str = request.GET.get('month')               # YYYY-MM

    # 勤怠タブは常に只読（URLで mode=edit を指定されても無効化）
    if sub_tab == 'attendance':
        mode = 'view'

    # -------- 給与月の期間 --------
    if not month_str:
        today = datetime.date.today()
        month_str = today.strftime('%Y-%m')
    year, mon = map(int, month_str.split('-'))

    start = datetime.date(year, mon, 1)
    end   = datetime.date(year + (1 if mon == 12 else 0), 1 if mon == 12 else mon + 1, 1)

    # -------- 売上対象月（前月） --------
    if mon == 1:
        sales_year, sales_mon = year - 1, 12
    else:
        sales_year, sales_mon = year, mon - 1
    sales_start = datetime.date(sales_year, sales_mon, 1)
    sales_end   = datetime.date(sales_year + (1 if sales_mon == 12 else 0),
                                1 if sales_mon == 12 else sales_mon + 1, 1)
    sales_month_str = f"{sales_year:04d}-{sales_mon:02d}"

    # -------- 集計：不含税売上 & 分段控除 --------
    monthly_sales_excl_tax = Decimal('0')
    progressive_fee_value  = 0
    try:
        items_qs = DriverDailyReportItem.objects.filter(
            report__driver=driver,
            report__date__gte=sales_start,
            report__date__lt=sales_end,
        )
        meter_sum   = items_qs.aggregate(s=Sum('meter_fee'))['s'] or 0
        charter_sum = items_qs.filter(is_charter=True).aggregate(s=Sum('charter_amount_jpy'))['s'] or 0
        gross_incl_tax = Decimal(meter_sum) + Decimal(charter_sum)

        TAX_DIVISOR = Decimal("1.10")  # 如果原始就是不含税，可改为 1.0
        monthly_sales_excl_tax = (gross_incl_tax / TAX_DIVISOR).quantize(Decimal('1'), rounding=ROUND_HALF_UP)

        # 你的分段控除函数
        progressive_fee_value  = calc_progressive_fee_by_table(monthly_sales_excl_tax)
    except Exception as e:
        print(f"[WARN] 売上集計に失敗: {e}")

    # -------- 当月の給与レコード --------
    qs = DriverPayrollRecord.objects.filter(
        driver=driver,
        month__gte=start,
        month__lt=end
    ).order_by('-month')

    # edit で当月レコードがない場合は 1 行作って編集可能にする
    if mode == 'edit' and not qs.exists():
        DriverPayrollRecord.objects.get_or_create(driver=driver, month=start)
        qs = DriverPayrollRecord.objects.filter(driver=driver, month__gte=start, month__lt=end)

    # -------- タブごとのフィールド --------
    fields_by_tab = {
        'attendance': [
            'attendance_days', 'absence_days',
            'holiday_work_days', 'paid_leave_days',
            'overtime_hours', 'night_hours', 'holiday_hours',
            'total_working_hours'
        ],
        'payment': [
            'basic_pay', 'overtime_allowance', 'night_allowance',
            'holiday_allowance', 'commute_allowance', 'bonus',
            'other_allowances', 'special_allowance',
            'transportation_allowance', 'total_pay'
        ],
        'deduction': [
            'health_insurance_deduction', 'health_care_insurance_deduction',
            'pension_deduction', 'employment_insurance_deduction',
            'workers_insurance_deduction', 'income_tax_deduction',
            'resident_tax_deduction', 'tax_total',
            'progressive_fee', 'other_deductions',
            'total_deductions', 'net_pay'
        ],
    }
    fields = fields_by_tab.get(sub_tab, [])

    # ======== 編集モード ========
    if mode == 'edit':
        FormSet = modelformset_factory(
            DriverPayrollRecord,
            form=DriverPayrollRecordForm,
            fields=fields,
            extra=0
        )
        formset = FormSet(request.POST or None, queryset=qs)

        # 控除タブ：progressive_fee 页面上禁改（保存时由后端覆盖）
        if sub_tab == 'deduction':
            for f in formset.forms:
                if 'progressive_fee' in f.fields:
                    f.fields['progressive_fee'].disabled = True

        if request.method == 'POST':
            if formset.is_valid():
                formset.save()

                # 保存后把分段控除 + 出勤日数 强制写回当月记录（触发模型合计）
                try:
                    # —— 出勤日数：当月“有至少一条日报明细”的日期数 —— 
                    attendance_days_count = (
                        DriverDailyReportItem.objects
                        .filter(
                            report__driver=driver,
                            report__date__gte=start,   # 当月起
                            report__date__lt=end       # 次月起（半开区间）
                        )
                        .values('report__date').distinct().count()
                    )

                    # —— 固定天数（默认=当月工作日 Mon–Fri；若你有公司“固定天数”字段，替换这里即可）——

                    base_days = sum(
                        1 for i in range((end - start).days)
                        if (start + timedelta(days=i)).weekday() < 5
                    )

                    for rec in DriverPayrollRecord.objects.filter(driver=driver, month__gte=start, month__lt=end):
                        rec.progressive_fee  = Decimal(str(progressive_fee_value))
                        rec.attendance_days  = attendance_days_count

                        # 缺勤日 = 固定天数 − 出勤 − 有給（不足取 0）
                        paid = rec.paid_leave_days or 0
                        rec.absence_days = max(base_days - attendance_days_count - paid, 0)

                        rec.save()
                except Exception as e:
                    print(f"[WARN] progressive_fee auto-save failed: {e}")

                messages.success(request, "保存しました。")
                return redirect(
                    f"{reverse('staffbook:driver_salary', args=[driver.id])}"
                    f"?sub={sub_tab}&month={month_str}&mode=view"
                )

        context = {'formset': formset}

    # ======== 只読モード（ここに“勤怠集計”が入っています） ========
    else:
        def _yen(x) -> int:
            return int(Decimal(x).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

        # ---- 時間外割増 1~4 の合計（残業手当の元）----
        c = Decimal(monthly_sales_excl_tax)  # 当月売上（不含税）
        o1 = _yen(min(Decimal("225000"), c / Decimal("2")))
        o2 = _yen(Decimal("60000") if c > Decimal("550000")
                  else max(Decimal("0"), (c - Decimal("450000")) * Decimal("0.6")))
        o3 = _yen(Decimal("65000") if c > Decimal("650000")
                  else max(Decimal("0"), (c - Decimal("550000")) * Decimal("0.65")))
        o4 = _yen((c - Decimal("650000")) * Decimal("0.7")) if c > Decimal("650000") else 0
        overtime_calc_sum = o1 + o2 + o3 + o4

        # ========= 这里是你要的“前后都保留”的勤怠统计块（开始） =========

        records = list(qs)

        # 头表（日报 Header）与明细（Item）
        header_qs = DriverDailyReport.objects.filter(
            driver=driver, date__gte=start, date__lt=end
        )
        items_qs = DriverDailyReportItem.objects.filter(
            report__driver=driver, report__date__gte=start, report__date__lt=end
        )

        # 出勤日数（来自日报明细）
        attendance_days = items_qs.values('report__date').distinct().count()
        attendance_days_from_reports = attendance_days

        # —— 固定天数（默认=当月工作日 Mon–Fri；如有公司固定天数字段，可替换这里）——
        
        base_days = sum(
            1 for i in range((end - start).days)
            if (start + timedelta(days=i)).weekday() < 5
        )

        # —— 工具函数：把各种“时间/时长表示”转成十进制小时（不依赖 datetime 类型判断，避免再次报错）——
        def hours_value(v: object) -> Decimal:
            """任意输入 → 十进制小时。支持 timedelta-like、数字、'HH:MM(:SS)' 字符串。"""
            if v is None:
                return Decimal('0')
            # timedelta-like（有 total_seconds 方法）
            if hasattr(v, 'total_seconds') and callable(getattr(v, 'total_seconds', None)):
                return (Decimal(v.total_seconds()) / Decimal('3600')).quantize(Decimal('0.00'))
            # 纯数字
            if isinstance(v, (int, float, Decimal)):
                return Decimal(str(v))
            # "HH:MM(:SS)" 字符串
            s = str(v).strip()
            if ':' in s:
                try:
                    hh, mm, *ss = s.split(':')
                    sec = ss[0] if ss else '0'
                    return (Decimal(hh or '0')
                            + Decimal(mm or '0')/Decimal('60')
                            + Decimal(sec or '0')/Decimal('3600')).quantize(Decimal('0.00'))
                except Exception:
                    return Decimal('0')
            # 兜底：按数字字符串解析
            try:
                return Decimal(s)
            except Exception:
                return Decimal('0')

        def to_sec(t: object) -> int:
            """把 time/datetime/'HH:MM(:SS)'/十进制小时 转成 秒；不使用 isinstance(datetime.*)。"""
            # datetime-like：有 .time() 方法
            try:
                if hasattr(t, 'time') and callable(getattr(t, 'time', None)):
                    tt = t.time()
                else:
                    tt = t
                # time-like：有 hour/minute 属性
                if hasattr(tt, 'hour') and hasattr(tt, 'minute'):
                    sec = getattr(tt, 'second', 0) or 0
                    return int(tt.hour) * 3600 + int(tt.minute) * 60 + int(sec)
            except Exception:
                pass
            # "HH:MM(:SS)"
            s = str(t).strip()
            if ':' in s:
                parts = s.split(':')
                try:
                    h = int(parts[0] or 0)
                    m = int(parts[1] or 0)
                    sec = int(parts[2] or 0) if len(parts) > 2 else 0
                    return h*3600 + m*60 + sec
                except Exception:
                    return 0
            # 兜底：若是“十进制小时”数字，转成秒
            try:
                hours = Decimal(str(t))
                return int(hours * Decimal('3600'))
            except Exception:
                return 0

        def first_attr(obj, names):
            for nm in names:
                if hasattr(obj, nm):
                    v = getattr(obj, nm)
                    if v not in (None, ''):
                        return v
            return None

        def hours_from_times(h) -> Decimal:
            """若头表有上/下班时刻 + 休憩，推导実働小时。"""
            st = first_attr(h, ('start_time','duty_start','clock_in','on_duty_time','work_start'))
            et = first_attr(h, ('end_time','duty_end','clock_out','off_duty_time','work_end'))
            if not st or not et:
                return Decimal('0')

            ssec, esec = to_sec(st), to_sec(et)
            if esec < ssec:  # 跨零点
                esec += 24*3600
            hours = Decimal(esec - ssec) / Decimal('3600')

            # 扣休憩（分钟或小时）
            br_min = first_attr(h, ('break_minutes','rest_minutes','break_time_minutes'))
            br_hr  = first_attr(h, ('break_hours','rest_hours','break_time_hours'))
            if br_min is not None:
                hours -= Decimal(str(br_min))/Decimal('60')
            elif br_hr is not None:
                hours -= Decimal(str(br_hr))
            return hours if hours > 0 else Decimal('0')

        # —— 先从“头表字段”取実働/残業；缺失再退回“明细行字段”；还不行就用时刻推导 —— #
        sum_actual = Decimal('0')  # 実働时间（小时）
        sum_ot     = Decimal('0')  # 残業时间（小时）

        if header_qs.exists():
            for h in header_qs:
                # 実働
                v_act = first_attr(h, (
                    'actual_working_hours','total_working_hours','working_hours',
                    'actual_hours','actual_work_time','work_hours','real_working_hours',
                ))
                sum_actual += hours_value(v_act) if v_act is not None else hours_from_times(h)
                # 残業
                v_ot = first_attr(h, ('overtime_hours','total_overtime_hours','ot_hours','overtime'))
                if v_ot is not None:
                    sum_ot += hours_value(v_ot)
                else:
                    v_ot_min = first_attr(h, ('overtime_minutes','ot_minutes','overtime_time_minutes'))
                    if v_ot_min is not None:
                        sum_ot += Decimal(str(v_ot_min))/Decimal('60')
        else:
            # 退回明细行累加
            def sum_rows(qs, hour_fields, minute_fields=()):
                total = Decimal('0')
                for it in qs:
                    picked = False
                    for f in hour_fields:
                        if hasattr(it, f):
                            total += hours_value(getattr(it, f))
                            picked = True
                            break
                    if not picked:
                        for f in minute_fields:
                            if hasattr(it, f):
                                total += Decimal(str(getattr(it, f)))/Decimal('60')
                                break
                return total

            sum_actual = sum_rows(
                items_qs,
                ('actual_working_hours','working_hours','work_hours','actual_hours','actual_work_time'),
                ('actual_minutes','working_minutes','work_minutes','actual_work_minutes')
            )
            sum_ot = sum_rows(
                items_qs,
                ('overtime_hours','overtime_time','overtime','ot_hours','total_overtime_hours'),
                ('overtime_minutes','ot_minutes','overtime_time_minutes')
            )

        # 保留两位小数（模板显示 0.00）
        sum_actual = sum_actual.quantize(Decimal('0.00'))
        sum_ot     = sum_ot.quantize(Decimal('0.00'))
        # === 勤怠集計（替换块结束） ===

        # 把结果写入每条记录（同时覆盖 view_* 与同名原字段）
        for r in records:
            r.view_attendance_days     = attendance_days
            r.view_total_working_hours = sum_actual
            r.view_overtime_hours      = sum_ot
            r.attendance_days          = attendance_days
            r.total_working_hours      = sum_actual
            r.overtime_hours           = sum_ot

            # —— 缺勤日（显示/存储口径一致）——
            paid = getattr(r, 'paid_leave_days', 0) or 0
            r.view_absence_days = max(base_days - attendance_days - paid, 0)
            r.absence_days      = r.view_absence_days

            # 残業手当（显示用）
            r.view_overtime_allowance = overtime_calc_sum

            # 総支給額（显示用）
            pieces = [
                r.basic_pay or 0,
                overtime_calc_sum,
                r.night_allowance or 0,
                r.holiday_allowance or 0,
                r.commute_allowance or 0,
                r.bonus or 0,
                r.other_allowances or 0,
                r.special_allowance or 0,
                r.transportation_allowance or 0,
            ]
            r.view_total_pay = _yen(sum(Decimal(p) for p in pieces))

            # 控除页“合計”条
            def _to_dec(x): return Decimal(x or 0)
            social_ins_total = (
                _to_dec(r.health_insurance_deduction)
                + _to_dec(r.health_care_insurance_deduction)
                + _to_dec(r.pension_deduction)
                + _to_dec(r.employment_insurance_deduction)
                + _to_dec(r.workers_insurance_deduction)
            )
            total_pay_for_tax = _to_dec(getattr(r, 'view_total_pay', None) or r.total_pay)
            non_taxable = _to_dec(r.commute_allowance) + _to_dec(r.transportation_allowance)
            taxable_amount = total_pay_for_tax - non_taxable - social_ins_total
            if taxable_amount < 0:
                taxable_amount = Decimal('0')
            cash_payment = Decimal('0')  # 现现金额暂定 0
            net_pay = _to_dec(r.net_pay)
            bank_transfer = net_pay - cash_payment
            r.view_summary = {
                "social_ins_total": int(social_ins_total),
                "taxable_amount":   int(taxable_amount),
                "bank_transfer":    int(bank_transfer),
                "cash_payment":     int(cash_payment),
                "net_pay":          int(net_pay),
            }
        # ========= 这里是你要的“前后都保留”的勤怠统计块（结束） =========

        context = {'records': records}

    # -------- レンダリング --------
    return render(request, 'staffbook/driver_salary.html', {
        'driver': driver,
        'main_tab': 'salary',
        'tab': 'salary',
        'sub_tab': sub_tab,
        'mode': mode,
        'month': month_str,

        # 上部情報バー
        'sales_month_str': sales_month_str,
        'monthly_sales_excl_tax': int(monthly_sales_excl_tax),
        'progressive_fee': int(progressive_fee_value),

        **context,
    })

