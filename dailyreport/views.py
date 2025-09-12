import csv, logging
from io import BytesIO
from datetime import datetime, date, timedelta, time as dtime, time
from tempfile import NamedTemporaryFile
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from calendar import monthrange
from django.conf import settings

from django.contrib.auth.decorators import user_passes_test, login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import render, get_object_or_404, redirect, HttpResponse
from django.utils.timezone import now, make_aware, get_current_timezone
TZ = get_current_timezone()
from django.utils import timezone
from django.db import transaction
from django.db.models import IntegerField, Value, Case, When, ExpressionWrapper, F, Sum, Q, DateField
from django.db.models.functions import Substr, Cast, Coalesce, NullIf, Lower, Trim
from django.http import HttpResponse, FileResponse
from django.utils.encoding import escape_uri_path
from django.urls import reverse
from django.utils.http import urlencode
from django.forms import inlineformset_factory
from dateutil.relativedelta import relativedelta

from dailyreport.constants import PAYMENT_RATES, CHARTER_CASH_KEYS, CHARTER_UNCOLLECTED_KEYS
from dailyreport.models import DriverDailyReport, DriverDailyReportItem
from .forms import DriverDailyReportForm, DriverDailyReportItemForm, ReportItemFormSet, RequiredReportItemFormSet
from .services.calculations import calculate_deposit_difference
from dailyreport.services.summary import (
    resolve_payment_method,
    calculate_totals_from_instances, calculate_totals_from_formset
)
from dailyreport.utils.debug import debug_print

from staffbook.services import get_driver_info
from staffbook.models import Driver

from vehicles.models import Reservation
from urllib.parse import quote

from openpyxl import Workbook
from openpyxl.utils import get_column_letter

logger = logging.getLogger(__name__)

def _norm_hhmm(v: object) -> str:
    """
    归一化为 'HH:MM'；不合法返回 ''。
    支持：
      - datetime/time 对象
      - '10:30'、'10：30'（全角冒号）
      - '1030' 或 '930'
    """
    if not v:
        return ""
    if isinstance(v, dtime):
        return v.strftime("%H:%M")
    if isinstance(v, datetime):
        return v.strftime("%H:%M")

    s = str(v).strip().replace("：", ":")
    if not s:
        return ""

    # 纯数字 3~4 位：930 / 1030
    if s.isdigit() and len(s) in (3, 4):
        h = int(s[:-2]); m = int(s[-2:])
        if 0 <= h < 24 and 0 <= m < 60:
            return f"{h:02d}:{m:02d}"
        return ""

    if ":" in s:
        try:
            h, m = map(int, s.split(":", 1))
            if 0 <= h < 24 and 0 <= m < 60:
                return f"{h:02d}:{m:02d}"
        except Exception:
            return ""
    return ""

def _as_aware_dt(val, base_date):
    """把 datetime / time / 'HH:MM' 统一成当天的 aware datetime。"""
    if not val:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo else make_aware(val, TZ)
    if isinstance(val, dtime):
        return make_aware(datetime.combine(base_date, val), TZ)
    s = str(val).strip()
    if ":" in s:
        try:
            h, m = map(int, s.split(":", 1))
            return make_aware(datetime.combine(base_date, dtime(h, m)), TZ)
        except Exception:
            return None
    return None
# =================================================

# ========= 软预填（不落库，仅用于渲染初值） =========
def _safe_as_time(val):
    try:
        if val is None:
            return None
        if hasattr(val, "time") and callable(getattr(val, "time")):
            return val.time()
        if hasattr(val, "hour") and hasattr(val, "minute") and not hasattr(val, "date"):
            return val
        s = str(val).strip()
        if ":" in s:
            h, m = s.split(":", 1)
            h = int(h); m = int(m)
            if 0 <= h < 24 and 0 <= m < 60:
                from datetime import time as _t
                return _t(h, m)
    except Exception:
        pass
    return None

def _prefill_report_without_fk(report):
    """
    预填规则（只用实际值，不用计划值）：
    - 车辆：取当天该司机任一预约的 vehicle
    - 出勤：若为空，取当天所有预约中最早的 actual_departure
    - 退勤：若为空，取当天所有预约中最晚的 actual_return
      ▶ 若没有 actual_return，则保持空（绝不再用 end_time 回填）
    """
    try:
        user = getattr(getattr(report, "driver", None), "user", None)
        the_date = getattr(report, "date", None)
        if not user or not the_date:
            return

        # 当天所有覆盖该日期的预约（含跨天）
        qs = (Reservation.objects
              .filter(driver=user, date__lte=the_date, end_date__gte=the_date)
              .select_related("vehicle")
              .order_by("date", "start_time"))
        if not qs.exists():
            return

        # 车辆：缺就取第一条有车的
        if not getattr(report, "vehicle_id", None):
            for r in qs:
                v = getattr(r, "vehicle", None)
                if v:
                    report.vehicle = v
                    break

        # 出勤：仅取“实际出库”中最早的一个
        if getattr(report, "clock_in", None) in (None, ""):
            actual_deps = []
            for r in qs:
                ad = getattr(r, "actual_departure", None)
                if ad:
                    t = _safe_as_time(ad)
                    if t:
                        actual_deps.append(t)
            if actual_deps:
                report.clock_in = sorted(actual_deps)[0]

        # 退勤：仅取“实际入库”中最晚的一个；没有就保持空
        if getattr(report, "clock_out", None) in (None, ""):
            actual_returns = []
            for r in qs:
                ar = getattr(r, "actual_return", None)
                if ar:
                    t = _safe_as_time(ar)
                    if t:
                        actual_returns.append(t)
            if actual_returns:
                report.clock_out = sorted(actual_returns)[-1]
            # else: 不再用 end_time 填充，保持为空
    except Exception as e:
        debug_print("SOFT_PREFILL error:", e)

# ========= 小工具 =========
BASE_BREAK_MINUTES = 20
DEBUG_PRINT_ENABLED = True
if getattr(settings, "DEBUG", False):
    print("🔥 views.py 加载 OK")

def _to_int0(v):
    try:
        if v in ("", None):
            return 0
        return int(v)
    except (TypeError, ValueError):
        return 0

# 兼容旧代码里用到的 _to_int
_to_int = _to_int0

def _minutes_from_timedelta(td):
    if not td:
        return 0
    try:
        return int(td.total_seconds() // 60)
    except Exception:
        return 0

NIGHT_END_MIN = 5 * 60  # 05:00

def _sorted_items_qs(report):
    safe_ride = Coalesce(NullIf(F('ride_time'), Value('')), Value('00:00'))
    return (
        report.items
        .annotate(
            _safe_ride=safe_ride,
            _hour=Cast(Substr(F('_safe_ride'), 1, 2), IntegerField()),
            _minute=Cast(Substr(F('_safe_ride'), 4, 2), IntegerField()),
        )
        .annotate(_total_min=F('_hour') * 60 + F('_minute'))
        .annotate(
            _minutes_for_sort=ExpressionWrapper(
                F('_total_min') + Case(
                    When(_total_min__lt=NIGHT_END_MIN, then=Value(24 * 60)),
                    default=Value(0),
                ),
                output_field=IntegerField(),
            )
        )
        .order_by('_minutes_for_sort', 'id')
    )

def to_aware_dt(base_date, value, *, base_clock_in=None, tz=None):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, dtime):
        dt = datetime.combine(base_date, value)
    elif isinstance(value, str):
        s = value.strip()
        if not s or ":" not in s:
            return None
        try:
            h, m = map(int, s.split(":", 1))
        except Exception:
            return None
        dt = datetime.combine(base_date, dtime(hour=h, minute=m))
    else:
        return None

    if base_clock_in:
        ci = base_clock_in.time() if isinstance(base_clock_in, datetime) else base_clock_in
        if isinstance(ci, dtime) and dt.time() < ci:
            dt += timedelta(days=1)

    tz = tz or timezone.get_current_timezone()
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, tz)
    return dt

# === [SYNC UTILS START] 日报 <-> 预约 同步工具（在本文件内，不新建模块） ===
def _reservation_plan_window(reservation):
    """
    将 Reservation 的 (date, start_time) / (end_date, end_time)
    组合成本地时区 datetime 的计划窗口。
    """
    s = to_aware_dt(reservation.date, reservation.start_time)
    e = to_aware_dt(reservation.end_date, reservation.end_time, base_clock_in=reservation.start_time)
    return s, e


def _find_best_reservation_for_report(report, in_dt, out_dt):
    """
    在同一司机（report.driver.user）、同一车辆（若选择了车辆）、
    以 report.date 为中心 前后各 1 天 的范围内，选一条“最匹配”的预约：
      - 同时有 in/out：选“重叠时长最大”的预约
      - 只有一个时间点：选“距离最近”的预约
    """
    driver_user = getattr(getattr(report, "driver", None), "user", None)
    if not driver_user:
        return None

    qs = Reservation.objects.filter(
        driver=driver_user,
        date__lte=report.date + timedelta(days=1),
        end_date__gte=report.date - timedelta(days=1),
    )
    if getattr(report, "vehicle_id", None):
        qs = qs.filter(vehicle_id=report.vehicle_id)

    if not qs.exists():
        return None

    def overlap_or_gap(r):
        s, e = _reservation_plan_window(r)
        if in_dt and out_dt:
            a, b = max(s, in_dt), min(e, out_dt)
            overlap = max(timedelta(0), b - a)
            # 负数表示“更差”，用于排序（重叠越大越好）
            return (0, -overlap.total_seconds())
        else:
            t = in_dt or out_dt
            if s <= t <= e:
                gap = 0
            else:
                gap = min(abs(t - s), abs(t - e)).total_seconds()
            return (1, gap)

    # 按 (模式, 指标) 排序：模式 0(有重叠) 优于 1(只看距离)；指标越小越好
    best = sorted(qs, key=overlap_or_gap)[0]
    return best


def _sync_reservation_actual_for_report(report, old_clock_in, old_clock_out):
    """
    只在“从空到有”的场景下，同步 Reservation.actual_departure / actual_return。
    若预约里已有实际时间，则不覆盖。
    """
    # 判断是否“从空到有”
    filled_in_from_empty  = (not old_clock_in)  and bool(getattr(report, "clock_in",  None))
    filled_out_from_empty = (not old_clock_out) and bool(getattr(report, "clock_out", None))
    if not (filled_in_from_empty or filled_out_from_empty):
        return

    # 计算当天的 aware datetime（退勤相对出勤自动跨天）
    in_dt  = to_aware_dt(report.date, report.clock_in)  if getattr(report, "clock_in",  None) else None
    out_dt = to_aware_dt(report.date, report.clock_out, base_clock_in=in_dt) if getattr(report, "clock_out", None) else None

    reservation = _find_best_reservation_for_report(report, in_dt, out_dt)
    if not reservation:
        return

    updated_fields = []
    if filled_in_from_empty and in_dt and getattr(reservation, "actual_departure", None) in (None, ""):
        reservation.actual_departure = in_dt
        updated_fields.append("actual_departure")

    if filled_out_from_empty and out_dt and getattr(reservation, "actual_return", None) in (None, ""):
        reservation.actual_return = out_dt
        updated_fields.append("actual_return")

    if updated_fields:
        reservation.save(update_fields=updated_fields)
# === [SYNC UTILS END] ===

def check_module_permission(user, perm_key: str) -> bool:
    try:
        if not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False):
            return True

        APP_LABEL = "dailyreport"
        key = (perm_key or "").strip().lower()

        candidates = [
            f"{APP_LABEL}.{key}",
            f"{APP_LABEL}.can_{key}",
            f"{APP_LABEL}.is_{key}",
            key,
        ]
        for perm in candidates:
            try:
                if user.has_perm(perm):
                    return True
            except Exception:
                pass

        try:
            if user.has_module_perms(APP_LABEL):
                return True
        except Exception:
            pass

        try:
            group_names = {g.name.strip().lower() for g in user.groups.all()}
            if key in group_names or f"{APP_LABEL}:{key}" in group_names:
                return True
        except Exception:
            pass

        return False
    except Exception:
        return False

def is_dailyreport_admin(user):
    try:
        return (
            check_module_permission(user, 'dailyreport_admin')
            or check_module_permission(user, 'dailyreport')
            or getattr(user, 'is_superuser', False)
            or getattr(user, "is_staff", False)
        )
    except Exception:
        return bool(getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False))

dailyreport_admin_required = user_passes_test(is_dailyreport_admin)

def get_active_drivers(month_obj=None, keyword=None):
    qs = Driver.objects.all()
    if month_obj is None:
        month_obj = date.today()

    year = month_obj.year
    month = month_obj.month
    from datetime import date as _date
    from calendar import monthrange as _monthrange
    first_day = _date(year, month, 1)
    last_day = _date(year, month, _monthrange(year, month)[1])

    try:
        qs = qs.filter(
            Q(hire_date__lte=last_day)
            & (Q(resigned_date__isnull=True) | Q(resigned_date__gte=first_day))
        )
    except Exception:
        pass

    if hasattr(Driver, 'is_active'):
        try:
            qs = qs.filter(is_active=True)
        except Exception:
            pass

    if keyword:
        try:
            qs = qs.filter(Q(name__icontains=keyword) | Q(code__icontains=keyword))
        except Exception:
            pass

    return qs.order_by('name')

# ========= 基础视图 =========
@user_passes_test(is_dailyreport_admin)
def dailyreport_create(request):
    if request.method == 'POST':
        form = DriverDailyReportForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('dailyreport:dailyreport_list')
    else:
        form = DriverDailyReportForm()
    return render(request, 'dailyreport/driver_dailyreport_edit.html', {'form': form})


PREFIX = "items"   # ✅ 前后端统一的前缀

ReportItemFormSet = inlineformset_factory(
    DriverDailyReport,
    DriverDailyReportItem,
    form=DriverDailyReportItemForm,
    extra=0,
    can_delete=True,     # ✅ 允许删除
    max_num=40,
)


def dailyreport_edit(request, pk):
    report = get_object_or_404(DR, pk=pk)

    if request.method == 'POST':
        form = DriverDailyReportForm(request.POST, instance=report)
        formset = ReportItemFormSet(request.POST, instance=report, prefix=PREFIX)

        if form.is_valid() and formset.is_valid():
            inst = form.save(commit=False)
            inst.edited_by = request.user
            inst.save()

            # 关键：一句话就够了（增/改/删 都在这里完成）
            formset.instance = inst
            formset.save()   # ✅ 会自动删除勾选 DELETE 的旧行

            messages.success(request, "保存成功！")
            return redirect('dailyreport:dailyreport_edit', pk=inst.pk)
        else:
            messages.error(request, "保存失败，请检查输入内容")
    else:
        form = DriverDailyReportForm(instance=report)
        formset = ReportItemFormSet(instance=report, prefix=PREFIX)  # ✅ GET 同样用 prefix

    # 模板需要的其它上下文按你现有的来，这里只保证能渲染
    return render(request, 'dailyreport/driver_dailyreport_edit.html', {
        'form': form,
        'formset': formset,
        'report': report,
        'driver': getattr(report, 'driver', None),
        'is_edit': True,
    })
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
# 如果上面没引入 user_passes_test / 模型，也一并确认
from django.contrib.auth.decorators import user_passes_test
from .models import DriverDailyReportItem
@user_passes_test(is_dailyreport_admin)
@require_POST
def dailyreport_item_delete(request, item_id):
    item = get_object_or_404(DriverDailyReportItem, pk=item_id)
    report_id = item.report_id
    item.delete()
    messages.success(request, "已删除 1 条明细。")
    return redirect('dailyreport:dailyreport_edit', pk=report_id)

@login_required
def sales_thanks(request):
    return render(request, 'dailyreport/sales_thanks.html')

@user_passes_test(is_dailyreport_admin)
def dailyreport_delete_for_driver(request, driver_id, pk):
    driver = get_object_or_404(Driver, pk=driver_id)
    report = get_object_or_404(DR, pk=pk, driver=driver)
    if request.method == "POST":
        report.delete()
        messages.success(request, "已删除该日报记录。")
        return redirect('dailyreport:driver_dailyreport_month', driver_id=driver.id)
    return render(request, 'dailyreport/dailyreport_confirm_delete.html', {
        'report': report,
        'driver': driver,
    })

@login_required
def dailyreport_list(request):
    if request.user.is_staff:
        reports = DriverDailyReport.objects.all().order_by('-date')
    else:
        reports = DriverDailyReport.objects.filter(driver=request.user).order_by('-date')
    return render(request, 'dailyreport/dailyreport_list.html', {'reports': reports})

# ========= 导出：每日汇总（openpyxl） =========
# ========== [BEGIN 保留：export_dailyreports_csv（已停用）] ==========
# @user_passes_test(is_dailyreport_admin)
# def export_dailyreports_csv(request, year, month):
#     from datetime import time as dtime, timedelta
#     from django.db.models import Case, When, F, ExpressionWrapper, DateField
#     work_date_expr = Case(
#         When(clock_in__lt=dtime(6, 0),
#              then=ExpressionWrapper(F('date') - timedelta(days=1), output_field=DateField())),
#         default=F('date'), output_field=DateField(),
#     )
#     reports = (
#         DriverDailyReport.objects
#         .annotate(work_date=work_date_expr)
#         .filter(work_date__year=year, work_date__month=month)
#         .select_related('driver')
#         .prefetch_related('items')
#         .order_by('work_date', 'driver__name')
#     )
    # ========== [END   新：按“勤務開始日(work_date)”归属月份过滤] ==========

#    reports_by_date = defaultdict(list)
#    payment_keys = ['cash', 'uber', 'didi', 'ticket', 'credit', 'qr']

#    for report in reports:
#        summary = defaultdict(int)
#        for item in report.items.all():
#            if (
#                item.payment_method in payment_keys
#                and item.meter_fee and item.meter_fee > 0
#                and (not item.note or 'キャンセル' not in item.note)
#            ):
#                summary[item.payment_method] += item.meter_fee

#        deposit = report.deposit_amount or 0
#        etc_app = report.etc_collected_app or 0
#        etc_cash = report.etc_collected_cash or 0
#        etc_total = etc_app + etc_cash
#        etc_expected = report.etc_expected or 0
#        etc_diff = etc_expected - etc_total
#        deposit_diff = calculate_deposit_difference(report, summary['cash'])

#        reports_by_date[report.date.strftime('%Y-%m-%d')].append({
#           'driver_code': report.driver.driver_code if report.driver else '',
#            'driver': report.driver.name if report.driver else '',
#            'status': report.get_status_display(),
#            'cash': summary['cash'],
#            'uber': summary['uber'],
#            'didi': summary['didi'],
#            'ticket': summary['ticket'],
#            'credit': summary['credit'],
#            'qr': summary['qr'],
#            'etc_expected': etc_expected,
#            'etc_collected': etc_total,
#            'etc_diff': etc_diff,
#            'deposit': deposit,
#            'deposit_diff': deposit_diff,
#            'mileage': report.mileage or '',
#            'gas_volume': report.gas_volume or '',
#            'note': report.note or '',
#        })

#    wb = Workbook()
#    wb.remove(wb.active)

#    for date_str, rows in sorted(reports_by_date.items()):
#        ws = wb.create_sheet(title=date_str)
#        headers = [
#            '司机代码', '司机', '出勤状态',
#            '现金', 'Uber', 'Didi', 'チケット', 'クレジット', '扫码',
#            'ETC应收', 'ETC实收', '未收ETC',
#            '入金', '差額',
#            '公里数', '油量', '备注'
#        ]
#        ws.append(headers)
#        for row in rows:
#            ws.append([
#                row['driver_code'],
#                row['driver'],
#                row['status'],
#                row['cash'],
#                row['uber'],
#                row['didi'],
#                row['ticket'],
#                row['credit'],
#                row['qr'],
#                row['etc_expected'],
#                row['etc_collected'],
#                row['etc_diff'],
#                row['deposit'],
#                row['deposit_diff'],
#                row['mileage'],
#                row['gas_volume'],
#                row['note'],
#            ])

#    filename = f"{year}年{month}月全员每日明细.xlsx"
#    tmp = NamedTemporaryFile()
#    wb.save(tmp.name)
#    tmp.seek(0)
#    response = FileResponse(tmp, as_attachment=True, filename=quote(filename))
#    response['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
#    return response

# ========= 导出：每日/集计（xlsxwriter） =========
@user_passes_test(is_dailyreport_admin)
def export_dailyreports_excel(request, year, month):
    try:
        import xlsxwriter
    except ModuleNotFoundError:
        return HttpResponse("XlsxWriter 未安装。请在虚拟环境中运行：pip install XlsxWriter", status=500)

    FEE_RATE = Decimal("0.05")
    CASH_METHODS = {"cash", "uber_cash", "didi_cash", "go_cash"}

    # ==== BEGIN: 支持区间导出（from/to） ====
    q_from = (request.GET.get("from") or "").strip()
    q_to   = (request.GET.get("to") or "").strip()

    date_from = None
    date_to   = None
    date_range = None
    if q_from and q_to:
        try:
            date_from = datetime.strptime(q_from, "%Y-%m-%d").date()
            date_to   = datetime.strptime(q_to,   "%Y-%m-%d").date()
            if date_from > date_to:
                return HttpResponse("開始日必须早于/等于終了日", status=400)
            date_range = (date_from, date_to)
        except ValueError:
            return HttpResponse("日期格式应为 YYYY-MM-DD", status=400)
    # ==== END: 支持区间导出（from/to） ====

    # ========== [BEGIN 保留：原来的“按业务日期”过滤] ==========
    # if date_range:
    #     reports = (
    #         DriverDailyReport.objects
    #         .filter(date__range=date_range)
    #         .select_related("driver")
    #         .prefetch_related("items")
    #         .order_by("date", "driver__name")
    #     )
    # else:
    #     reports = (
    #         DriverDailyReport.objects
    #         .filter(date__year=year, date__month=month)
    #         .select_related("driver")
    #         .prefetch_related("items")
    #         .order_by("date", "driver__name")
    #     )
    # ========== [END   保留：原来的“按业务日期”过滤] ==========

    # ========== [BEGIN 新：按“勤務開始日(work_date)”过滤] ==========
    from datetime import time as dtime, timedelta
    from django.db.models import Case, When, F, ExpressionWrapper, DateField

    # 规则：clock_in < 06:00 → 归属前一日，否则归属当天
    work_date_expr = Case(
        When(
            clock_in__lt=dtime(6, 0),
            then=ExpressionWrapper(F('date') - timedelta(days=1), output_field=DateField()),
        ),
        default=F('date'),
        output_field=DateField(),
    )

    base_qs = (DriverDailyReport.objects
               .annotate(work_date=work_date_expr)
               .select_related("driver")
               .prefetch_related("items"))

    if date_range:
        # 区间模式也用 work_date 做区间（含头含尾）
        reports = base_qs.filter(work_date__range=date_range).order_by("work_date", "driver__name")
    else:
        reports = base_qs.filter(
            work_date__year=year, work_date__month=month
        ).order_by("work_date", "driver__name")
    # ========== [END   新：按“勤務開始日(work_date)”过滤] ==========

    by_date = defaultdict(list)
    for r in reports:
        # 用 work_date 分组；若注解不存在则退回 r.date（向后兼容）
        key_date = getattr(r, "work_date", None) or r.date
        by_date[key_date].append(r)


    def compute_row(r):
        def norm(s): return str(s).strip().lower() if s else ""
        meter_only = 0
        nagashi_cash = 0
        charter_cash = 0
        charter_uncol = 0
        amt = {"kyokushin": 0, "omron": 0, "kyotoshi": 0, "uber": 0, "credit": 0, "paypay": 0, "didi": 0}

        for it in r.items.all():
            is_charter = bool(getattr(it, "is_charter", False))
            pm = norm(getattr(it, "payment_method", None))
            cpm = norm(getattr(it, "charter_payment_method", None))
            meter_fee = int(getattr(it, "meter_fee", 0) or 0)
            charter_jpy = int(getattr(it, "charter_amount_jpy", 0) or 0)

            if not is_charter:
                meter_only += meter_fee
                if pm in CASH_METHODS:
                    nagashi_cash += meter_fee
                if pm == "kyokushin": amt["kyokushin"] += meter_fee
                elif pm == "omron":   amt["omron"] += meter_fee
                elif pm == "kyotoshi":amt["kyotoshi"] += meter_fee
                elif pm == "uber":    amt["uber"] += meter_fee
                elif pm in {"credit", "credit_card"}: amt["credit"] += meter_fee
                elif pm in {"qr", "scanpay"}:         amt["paypay"] += meter_fee
                elif pm == "didi":    amt["didi"] += meter_fee
            else:
                if cpm in CHARTER_CASH_KEYS:
                    charter_cash += charter_jpy
                else:
                    charter_uncol += charter_jpy

                if cpm == "kyokushin": amt["kyokushin"] += charter_jpy
                elif cpm == "omron":   amt["omron"] += charter_jpy
                elif cpm == "kyotoshi":amt["kyotoshi"] += charter_jpy
                elif cpm == "uber":    amt["uber"] += charter_jpy
                elif cpm in {"credit", "credit_card"}: amt["credit"] += charter_jpy
                elif cpm in {"qr", "scanpay"}:         amt["paypay"] += charter_jpy
                elif cpm == "didi":    amt["didi"] += charter_jpy

        fee_calc = lambda x: int((Decimal(x) * FEE_RATE).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) if x else 0
        uber_fee, credit_fee, paypay_fee, didi_fee = map(fee_calc, [amt["uber"], amt["credit"], amt["paypay"], amt["didi"]])

        etc_collected_val = r.etc_collected
        etc_ride_total = int(etc_collected_val if etc_collected_val not in [None, ""] else (r.etc_collected_cash or 0) + (r.etc_collected_app or 0))
        etc_empty_total = int(getattr(r, "etc_uncollected", 0) or 0)

        uncol_total = int(amt["uber"] + amt["didi"] + amt["credit"] + amt["kyokushin"] + amt["omron"] + amt["kyotoshi"] + amt["paypay"])
        water_total = int(meter_only) + int(charter_cash) + int(charter_uncol)

        tax_ex = int((Decimal(water_total) / Decimal("1.1")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        tax = water_total - tax_ex

        deposit_amt = int(r.deposit_amount or 0)
        deposit_diff = deposit_amt - int(nagashi_cash) - int(charter_cash)

        return {
            "driver_code": getattr(r.driver, "driver_code", "") or "",
            "driver": r.driver.name if r.driver else "",
            "clock_in": r.clock_in.strftime("%H:%M") if r.clock_in else "",
            "clock_out": r.clock_out.strftime("%H:%M") if r.clock_out else "",
            "nagashi_cash": int(nagashi_cash),
            "charter_cash": int(charter_cash),
            "etc_ride_total": etc_ride_total,
            "etc_empty_total": etc_empty_total,
            "charter_uncol": int(charter_uncol),
            "kyokushin": int(amt["kyokushin"]), "omron": int(amt["omron"]), "kyotoshi": int(amt["kyotoshi"]),
            "uber": int(amt["uber"]), "uber_fee": uber_fee,
            "credit": int(amt["credit"]), "credit_fee": credit_fee,
            "paypay": int(amt["paypay"]), "paypay_fee": paypay_fee,
            "didi": int(amt["didi"]), "didi_fee": didi_fee,
            "uncol_total": int(uncol_total), "fee_total": int(uber_fee + credit_fee + paypay_fee + didi_fee),
            "water_total": int(water_total), "tax_ex": tax_ex, "tax": tax,
            "gas_l": float(r.gas_volume or 0), "km": float(r.mileage or 0),
            "deposit_diff": int(deposit_diff),
        }

    output = BytesIO()
    wb = xlsxwriter.Workbook(output, {'in_memory': True, 'constant_memory': True})

    fmt_header = wb.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'bg_color': '#DDDDDD', 'border': 1})
    fmt_subheader_red = wb.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'font_color': '#CC0000'})
    fmt_border = wb.add_format({'border': 1})
    fmt_total_base = wb.add_format({'bold': True, 'bg_color': '#FFF2CC', 'border': 1, 'align': 'right'})
    fmt_neg_red = wb.add_format({'font_color': '#CC0000'})

    fmt_yen     = wb.add_format({'border': 1, 'align': 'right', 'valign': 'vcenter', 'num_format': '¥#,##0'})
    fmt_yen_tot = wb.add_format({'bold': True, 'bg_color': '#FFF2CC', 'border': 1, 'align': 'right', 'num_format': '¥#,##0'})
    fmt_num_2d   = wb.add_format({'border': 1, 'align': 'right', 'valign': 'vcenter', 'num_format': '#,##0.00'})
    fmt_num_2d_t = wb.add_format({'bold': True, 'bg_color': '#FFF2CC', 'border': 1, 'align': 'right', 'num_format': '#,##0.00'})

    col_widths = {0:10, 1:12, 2:9, 3:9, 4:12, 5:12, 6:12, 7:14, 8:12, 9:12, 10:12, 11:12,
                  12:12, 13:10, 14:14, 15:10, 16:12, 17:10, 18:12, 19:10, 20:12, 21:12,
                  22:12, 23:12, 24:12, 25:12, 26:12, 27:12}

    row1 = [
        "社員番号","従業員","出勤時刻","退勤時刻",
        "1.ながし現金","2.貸切現金",
        "3.ETC","", "貸切未収",
        "4.京交信売上","5.オムロン売上","6.京都市他売上",
        "7.Uber売上","", "8.クレジット売上","", "9.PayPay売上","", "10.DiDi売上","",
        "未収合計","手数料合計",
        "水揚合計","税抜収入","消費税",
        "11.ガソリン(L)","12.距離(KM)","過不足"
    ]
    row2 = ["","","","",
            "","",
            "乗車合計","空車ETC金額","",
            "","","",
            "","手数料","","手数料","","手数料","","手数料",
            "","",
            "","","",
            "","",
            ""]

    def write_headers(ws):
        ws.write_row(0, 0, row1, fmt_header)
        ws.write_row(1, 0, row2, fmt_header)
        merges = [
            (0,0,1,0),(0,1,1,1),(0,2,1,2),(0,3,1,3),
            (0,4,1,4),(0,5,1,5),
            (0,8,1,8),(0,9,1,9),(0,10,1,10),(0,11,1,11),
            (0,20,1,20),(0,21,1,21),
            (0,22,1,22),(0,23,1,23),(0,24,1,24),
            (0,25,1,25),(0,26,1,26),
            (0,27,1,27),
        ]
        for r1_, c1_, r2_, c2_ in merges:
            ws.merge_range(r1_, c1_, r2_, c2_, row1[c1_], fmt_header)
        for c in (13,15,17,19):
            ws.write(1, c, row2[c], fmt_subheader_red)
        for c, w in col_widths.items():
            ws.set_column(c, c, w)

    MONEY_COLS = {4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,27}
    TWO_DEC_COLS = {25, 26}

    def write_mixed_row(ws, r, values, is_total=False):
        for c, v in enumerate(values):
            if c in MONEY_COLS:
                num = float(v or 0)
                ws.write_number(r, c, num, fmt_yen_tot if is_total else fmt_yen)
            elif c in TWO_DEC_COLS:
                num = float(v or 0)
                ws.write_number(r, c, num, fmt_num_2d_t if is_total else fmt_num_2d)
            else:
                ws.write(r, c, v, fmt_total_base if is_total else fmt_border)

    idx_ws = wb.add_worksheet("索引")
    idx_ws.write_row(0, 0, ["日付", "件数"], fmt_header)
    rr = 1
    for d, reps in sorted(by_date.items()):
        idx_ws.write_row(rr, 0, [d.strftime("%Y-%m-%d"), len(reps)], fmt_border)
        rr += 1
    idx_ws.set_column(0, 0, 14); idx_ws.set_column(1, 1, 8)
    idx_ws.freeze_panes(1, 0)

    for d, day_reports in sorted(by_date.items()):
        def _code_key(rep):
            code = getattr(rep.driver, "driver_code", "") if rep.driver else ""
            return (int(code) if str(code).isdigit() else 10**9, str(code))
        day_reports = sorted(day_reports, key=_code_key)

        ws = wb.add_worksheet(d.strftime("%Y-%m-%d"))
        write_headers(ws)
        ws.freeze_panes(2, 2)

        r = 2
        totals = defaultdict(Decimal)

        for rep in day_reports:
            data = compute_row(rep)
            row_vals = [
                data["driver_code"], data["driver"], data["clock_in"], data["clock_out"],
                data["nagashi_cash"], data["charter_cash"],
                data["etc_ride_total"], data["etc_empty_total"], data["charter_uncol"],
                data["kyokushin"], data["omron"], data["kyotoshi"],
                data["uber"], data["uber_fee"],
                data["credit"], data["credit_fee"],
                data["paypay"], data["paypay_fee"],
                data["didi"], data["didi_fee"],
                data["uncol_total"], data["fee_total"],
                data["water_total"], data["tax_ex"], data["tax"],
                data["gas_l"], data["km"],
                data["deposit_diff"],
            ]
            write_mixed_row(ws, r, row_vals, is_total=False)
            for k, v in data.items():
                if isinstance(v, (int, float, Decimal)):
                    totals[k] += Decimal(str(v))
            r += 1

        total_vals = [
            "合計","","","",
            int(totals["nagashi_cash"]), int(totals["charter_cash"]),
            int(totals["etc_ride_total"]), int(totals["etc_empty_total"]), int(totals["charter_uncol"]),
            int(totals["kyokushin"]), int(totals["omron"]), int(totals["kyotoshi"]),
            int(totals["uber"]), int(totals["uber_fee"]),
            int(totals["credit"]), int(totals["credit_fee"]),
            int(totals["paypay"]), int(totals["paypay_fee"]),
            int(totals["didi"]), int(totals["didi_fee"]),
            int(totals["uncol_total"]), int(totals["fee_total"]),
            int(totals["water_total"]), int(totals["tax_ex"]), int(totals["tax"]),
            float(totals["gas_l"]), float(totals["km"]),
            int(totals["deposit_diff"]),
        ]
        write_mixed_row(ws, r, total_vals, is_total=True)

        if r > 2:
            ws.conditional_format(2, 27, r-1, 27, {
                'type': 'cell', 'criteria': '<', 'value': 0, 'format': wb.add_format({'font_color': '#CC0000'})
            })

    # === 改动点：汇总sheet标题在区间模式下更友好 ===
    summary_title = (
        f"{date_from:%Y-%m-%d}~{date_to:%Y-%m-%d}(集計)"
        if date_range else
        f"{year}-{int(month):02d} 月度(集計)"
    )
    summary_ws = wb.add_worksheet(summary_title)
    summary_ws.write_row(0, 0, row1, fmt_header)
    summary_ws.write_row(1, 0, row2, fmt_header)
    merges = [
        (0,0,1,0),(0,1,1,1),(0,2,1,2),(0,3,1,3),
        (0,4,1,4),(0,5,1,5),
        (0,8,1,8),(0,9,1,9),(0,10,1,10),(0,11,1,11),
        (0,20,1,20),(0,21,1,21),
        (0,22,1,22),(0,23,1,23),(0,24,1,24),
        (0,25,1,25),(0,26,1,26),
        (0,27,1,27),
    ]
    for r1_, c1_, r2_, c2_ in merges:
        summary_ws.merge_range(r1_, c1_, r2_, c2_, row1[c1_], fmt_header)
    for c, w in col_widths.items():
        summary_ws.set_column(c, c, w)
    summary_ws.freeze_panes(2, 2)

    per_driver = {}
    def add_to_driver(rep, data):
        if not rep.driver:
            return
        did = rep.driver.id
        if did not in per_driver:
            per_driver[did] = {
                "code": getattr(rep.driver, "driver_code", "") or "",
                "name": rep.driver.name,
                "days": 0,
                "hours": Decimal("0"),
                "nagashi_cash":0,"charter_cash":0,
                "etc_ride_total":0,"etc_empty_total":0,"charter_uncol":0,
                "kyokushin":0,"omron":0,"kyotoshi":0,
                "uber":0,"uber_fee":0,"credit":0,"credit_fee":0,
                "paypay":0,"paypay_fee":0,"didi":0,"didi_fee":0,
                "uncol_total":0,"fee_total":0,
                "water_total":0,"tax_ex":0,"tax":0,
                "gas_l":Decimal("0"),"km":Decimal("0"),
                "deposit_diff":0,
            }
        row = per_driver[did]
        row["days"] += 1
        try:
            if rep.clock_in and rep.clock_out and rep.date:
                dt_in = datetime.combine(rep.date, rep.clock_in)
                dt_out = datetime.combine(rep.date, rep.clock_out)
                if dt_out <= dt_in:
                    dt_out += timedelta(days=1)
                dur = dt_out - dt_in
                brk = getattr(rep, "休憩時間", None) or timedelta()
                sec = max(0, (dur - brk).total_seconds())
                row["hours"] += Decimal(str(sec/3600.0))
        except Exception:
            pass

        for k in [
            "nagashi_cash","charter_cash","etc_ride_total","etc_empty_total","charter_uncol",
            "kyokushin","omron","kyotoshi","uber","uber_fee","credit","credit_fee",
            "paypay","paypay_fee","didi","didi_fee",
            "uncol_total","fee_total","water_total","tax_ex","tax","deposit_diff"
        ]:
            row[k] += int(data[k])
        row["gas_l"] += Decimal(str(data["gas_l"]))
        row["km"]    += Decimal(str(data["km"]))

    for reps in by_date.values():
        for rep in reps:
            add_to_driver(rep, compute_row(rep))

    def _sort_key(code, name):
        return (int(code) if str(code).isdigit() else 10**9, str(code) or name)

    r = 2
    totals_sum = defaultdict(Decimal)
    for _, row in sorted(per_driver.items(), key=lambda kv: _sort_key(kv[1]["code"], kv[1]["name"])):
        hours_2d = row["hours"].quantize(Decimal("0.01"))
        sum_vals = [
            row["code"], row["name"], row["days"], float(hours_2d),
            row["nagashi_cash"], row["charter_cash"],
            row["etc_ride_total"], row["etc_empty_total"], row["charter_uncol"],
            row["kyokushin"], row["omron"], row["kyotoshi"],
            row["uber"], row["uber_fee"],
            row["credit"], row["credit_fee"],
            row["paypay"], row["paypay_fee"],
            row["didi"], row["didi_fee"],
            row["uncol_total"], row["fee_total"],
            row["water_total"], row["tax_ex"], row["tax"],
            float(row["gas_l"]), float(row["km"]),
            row["deposit_diff"],
        ]
        write_mixed_row(summary_ws, r, sum_vals, is_total=False)
        summary_ws.write_number(r, 3, float(hours_2d), fmt_num_2d)

        for k, v in row.items():
            if k in ("code","name"):
                continue
            if isinstance(v, (int, float, Decimal)):
                totals_sum[k] += Decimal(str(v))
        r += 1

    hours_total_2d = totals_sum["hours"].quantize(Decimal("0.01"))
    sum_total_vals = [
        "合計","", int(totals_sum["days"]), float(hours_total_2d),
        int(totals_sum["nagashi_cash"]), int(totals_sum["charter_cash"]),
        int(totals_sum["etc_ride_total"]), int(totals_sum["etc_empty_total"]), int(totals_sum["charter_uncol"]),
        int(totals_sum["kyokushin"]), int(totals_sum["omron"]), int(totals_sum["kyotoshi"]),
        int(totals_sum["uber"]), int(totals_sum["uber_fee"]),
        int(totals_sum["credit"]), int(totals_sum["credit_fee"]),
        int(totals_sum["paypay"]), int(totals_sum["paypay_fee"]),
        int(totals_sum["didi"]), int(totals_sum["didi_fee"]),
        int(totals_sum["uncol_total"]), int(totals_sum["fee_total"]),
        int(totals_sum["water_total"]), int(totals_sum["tax_ex"]), int(totals_sum["tax"]),
        float(totals_sum["gas_l"]), float(totals_sum["km"]),
        int(totals_sum["deposit_diff"]),
    ]
    write_mixed_row(summary_ws, r, sum_total_vals, is_total=True)
    summary_ws.write_number(r, 3, float(hours_total_2d), fmt_num_2d_t)

    if r > 2:
        summary_ws.conditional_format(2, 27, r-1, 27, {
            'type': 'cell', 'criteria': '<', 'value': 0, 'format': wb.add_format({'font_color': '#CC0000'})
        })

    wb.close()
    output.seek(0)

    # === 改动点：文件名按是否区间生成 ===
    if date_range:
        filename = f"{date_from.strftime('%Y%m%d')}-{date_to.strftime('%Y%m%d')}_全員毎日集計.xlsx"
    else:
        filename = f"{year}年{month}月_全員毎日集計.xlsx"

    return FileResponse(
        output,
        as_attachment=True,
        filename=quote(filename),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# ========= 合计辅助 =========
def _normalize(val: str) -> str:
    if not val:
        return ''
    v = str(val).strip().lower()
    mapping = {
        'jpy_cash':'jpy_cash','rmb_cash':'rmb_cash',
        'self_wechat':'self_wechat','boss_wechat':'boss_wechat',
        'to_company':'to_company','bank_transfer':'bank_transfer',
        '--------':'','------':'','': '',
        '現金':'jpy_cash','现金':'jpy_cash','日元現金':'jpy_cash','日元现金':'jpy_cash',
        '人民幣現金':'rmb_cash','人民币现金':'rmb_cash',
        '自有微信':'self_wechat','老板微信':'boss_wechat',
        '公司回收':'to_company','会社回収':'to_company','公司结算':'to_company',
        '銀行振込':'bank_transfer','bank':'bank_transfer',
    }
    return mapping.get(v, v)

def _totals_of(items):
    meter_only = Decimal('0')
    charter_cash = Decimal('0')
    charter_uncol = Decimal('0')
    charter_unknown = Decimal('0')

    for it in items:
        if getattr(it, 'is_charter', False):
            amt = Decimal(getattr(it, 'charter_amount_jpy', 0) or 0)
            if amt <= 0:
                continue
            method = _normalize(getattr(it, 'charter_payment_method', ''))
            if method in {'jpy_cash', 'rmb_cash', 'self_wechat', 'boss_wechat'}:
                charter_cash += amt
            elif method in {'to_company', 'bank_transfer', ''}:
                charter_uncol += amt
            else:
                charter_unknown += amt
        else:
            if getattr(it, 'payment_method', None):
                meter_only += Decimal(it.meter_fee or 0)

    sales_total = meter_only + charter_cash + charter_uncol + charter_unknown
    return {
        'meter_only_total': meter_only,
        'charter_cash_total': charter_cash,
        'charter_uncollected_total': charter_uncol,
        'charter_unknown_total': charter_unknown,
        'sales_total': sales_total,
    }

# ========= 月视图 =========
@user_passes_test(is_dailyreport_admin)
def driver_dailyreport_month(request, driver_id):
    driver = get_object_or_404(Driver, id=driver_id)

    month_str = request.GET.get("month", "")
    try:
        month = datetime.strptime(month_str, "%Y-%m").date().replace(day=1)
        month_str = month.strftime("%Y-%m")
    except Exception:
        month = timezone.localdate().replace(day=1)
        month_str = month.strftime("%Y-%m")

    reports_qs = (
        DriverDailyReport.objects
        .filter(driver=driver, date__year=month.year, date__month=month.month)
        .order_by('-date')
        .prefetch_related('items')
    )

    report_list = []
    # 仅在本函数内声明，避免全局重复与缩进问题
    SPECIAL_UBER = {'uber_reservation', 'uber_tip', 'uber_promotion'}

    for report in reports_qs:
        items = report.items.all()
        totals = _totals_of(items)

        # 统计 3 类 Uber（仅非貸切、未“待入”）
        special_uber_sum = 0
        for it in items:
            if getattr(it, 'is_pending', False):
                continue
            if getattr(it, 'is_charter', False):
                continue
            if getattr(it, 'payment_method', '') in SPECIAL_UBER:
                special_uber_sum += int(getattr(it, 'meter_fee', 0) or 0)

        # 合计仍用原 totals；“メータのみ”= 原来的 meter_only - 3 类 Uber
        report.total_all = totals['sales_total']
        base_meter_only = totals.get('meter_only_total', totals.get('meter_total', 0)) or 0
        report.meter_only_total = max(0, int(base_meter_only) - special_uber_sum)

        report.charter_unknown_total = totals['charter_unknown_total']
        report_list.append(report)

    prev_month = (month - timedelta(days=1)).replace(day=1).strftime('%Y-%m')
    next_month = (month.replace(day=28) + timedelta(days=4)).replace(day=1).strftime('%Y-%m')

    return render(request, 'dailyreport/driver_dailyreport_month.html', {
        'driver': driver,
        'month': month,
        'reports': report_list,
        'selected_month': month_str,
        'selected_date': request.GET.get("date", ""),
        'today': timezone.localdate(),
        'prev_month': prev_month,
        'next_month': next_month,
    })

# ========= 选择器 & 直接创建 =========
@user_passes_test(is_dailyreport_admin)
def dailyreport_add_selector(request, driver_id):
    from datetime import date as _date
    driver = get_object_or_404(Driver, pk=driver_id)

    month_str = request.GET.get("month")
    try:
        if month_str:
            target_year, target_month = map(int, month_str.split("-"))
            display_date = _date(target_year, target_month, 1)
        else:
            display_date = _date.today()
    except ValueError:
        display_date = _date.today()

    current_month = display_date.strftime("%Y-%m")
    num_days = monthrange(display_date.year, display_date.month)[1]
    all_dates = [_date(display_date.year, display_date.month, d) for d in range(1, num_days + 1)]

    reserved_dates = set()
    if driver.user:
        reserved_dates = set(
            Reservation.objects
            .filter(driver=driver.user, date__year=display_date.year, date__month=display_date.month)
            .values_list("date", flat=True)
        )

    calendar_dates = [{"date": d, "enabled": d in reserved_dates} for d in all_dates]

    if request.method == "POST":
        selected_date_str = request.POST.get("selected_date")
        try:
            selected_date = datetime.strptime(selected_date_str, "%Y-%m-%d").date()
        except ValueError:
            messages.error(request, "无效的日期")
            return redirect(request.path)

        if not driver.user or not Reservation.objects.filter(driver=driver.user, date=selected_date).exists():
            messages.warning(request, f"{selected_date.strftime('%Y年%m月%d日')} は出勤予約がありません。日報を作成できません。")
            return redirect(request.path + f"?month={current_month}")

        report, created = DriverDailyReport.objects.get_or_create(
            driver=driver,
            date=selected_date,
            defaults={"status": "pending"}
        )

        if created:
            res = (
                Reservation.objects
                .filter(driver=driver.user, date=selected_date)
                .order_by('start_time')
                .first()
            )
            if res:
                if res.vehicle:
                    report.vehicle = res.vehicle
                if res.actual_departure:
                    report.clock_in = timezone.localtime(res.actual_departure).time()
                if res.actual_return:
                    report.clock_out = timezone.localtime(res.actual_return).time()
                report.save()

        return redirect("dailyreport:driver_dailyreport_edit", driver_id=driver.id, report_id=report.id)

    return render(request, "dailyreport/driver_dailyreport_add.html", {
        "driver": driver,
        "current_month": display_date.strftime("%Y年%m月"),
        "year": display_date.year,
        "month": display_date.month,
        "calendar_dates": calendar_dates,
    })

@user_passes_test(is_dailyreport_admin)
def dailyreport_create_for_driver(request, driver_id):
    driver = get_driver_info(driver_id)
    if not driver:
        return render(request, 'dailyreport/not_found.html', status=404)

    if request.method == 'GET' and request.GET.get('date'):
        try:
            the_date = datetime.strptime(request.GET.get('date'), "%Y-%m-%d").date()
        except ValueError:
            messages.error(request, "无效的日期格式")
            return redirect('dailyreport:driver_dailyreport_month', driver_id=driver.id)

        existing = DriverDailyReport.objects.filter(driver=driver, date=the_date).first()
        if existing:
            return redirect('dailyreport:driver_dailyreport_edit', driver_id=driver.id, report_id=existing.id)

        new_report = DriverDailyReport.objects.create(driver=driver, date=the_date)
        return redirect('dailyreport:driver_dailyreport_edit', driver_id=driver.id, report_id=new_report.id)

    ReportItemFS = inlineformset_factory(
        DriverDailyReport, DriverDailyReportItem,
        form=DriverDailyReportItemForm,
        formset=RequiredReportItemFormSet,
        extra=0, can_delete=True, max_num=40,
    )

    if request.method == 'POST':
        report_form = DriverDailyReportForm(request.POST)
        formset = ReportItemFS(request.POST)

        if report_form.is_valid() and formset.is_valid():
            dailyreport = report_form.save(commit=False)
            dailyreport.driver = driver
            try:
                dailyreport.calculate_work_times()
            except Exception:
                pass

            cash_total = sum(
                item.cleaned_data.get('meter_fee') or 0
                for item in formset.forms
                if item.cleaned_data.get('payment_method') == 'cash'
                and not item.cleaned_data.get('DELETE', False)
            )
            deposit = dailyreport.deposit_amount or 0
            dailyreport.deposit_difference = deposit - cash_total

            dailyreport.save()
            formset.instance = dailyreport
            formset.save()

            messages.success(request, '新增日报成功')
            return redirect('dailyreport:driver_dailyreport_month', driver_id=driver.id)
        else:
            print("日报主表错误：", report_form.errors)
            print("明细表错误：", formset.errors)
    else:
        report_form = DriverDailyReportForm()
        formset = ReportItemFS()

    if request.method == 'POST' and formset.is_valid():
        data_iter = [f.cleaned_data for f in formset.forms if f.cleaned_data]
        totals = calculate_totals_from_formset(data_iter)
    else:
        data_iter = [f.instance for f in formset.forms]
        totals = calculate_totals_from_instances(data_iter)

    summary_keys = [
        ('meter', 'メーター(水揚)'),
        ('cash', '現金(ながし)'),
        ('uber', 'Uber'),
        ('didi', 'Didi'),
        ('credit', 'クレジ'),
        ('kyokushin', '京交信'),
        ('omron', 'オムロン(愛のタクシーチケット)'),
        ('kyotoshi', '京都市他'),
        ('qr', '扫码'),
    ]

    return render(request, 'dailyreport/driver_dailyreport_edit.html', {
        'form': report_form,
        'formset': formset,
        'driver': driver,
        'report': None,
        'is_edit': False,
        'summary_keys': summary_keys,
        'totals': totals,
    })

# ========= 编辑（员工） =========
@user_passes_test(is_dailyreport_admin)
def dailyreport_edit_for_driver(request, driver_id, report_id):
    driver = get_driver_info(driver_id)
    if not driver:
        return render(request, "dailyreport/not_found.html", status=404)

    # 防变量遮蔽：避免有人在函数内部把 DriverDailyReport 当作变量名赋值
    # 用 apps.get_model 以“字符串”方式获取模型，绕开名字遮蔽。
    from django.apps import apps
    DR = apps.get_model('dailyreport', 'DriverDailyReport')
    report = get_object_or_404(DR, pk=report_id, driver_id=driver_id)

    ReportItemFormSet = inlineformset_factory(
        DR,
        DriverDailyReportItem,
        form=DriverDailyReportItemForm,
        formset=RequiredReportItemFormSet,
        extra=0,
        can_delete=True,
        max_num=40,
    )

    if request.method == 'POST':
        post = request.POST.copy()

        if not post.get("vehicle") and report.vehicle_id:
            post["vehicle"] = str(report.vehicle_id)

        PM_ALIASES = {
            'company card': 'credit', 'Company Card': 'credit', '会社カード': 'credit',
            'company_card': 'credit', 'credit card': 'credit',
            'バーコード': 'qr', 'barcode': 'qr', 'bar_code': 'qr', 'qr_code': 'qr', 'qr': 'qr',
            '現金': 'cash', '现金': 'cash', 'cash(現金)': 'cash',
            'uber現金': 'uber_cash', 'didi現金': 'didi_cash', 'go現金': 'go_cash',
        }
        for k, v in list(post.items()):
            if k.endswith('-payment_method'):
                post[k] = PM_ALIASES.get(v, v)

        # ✅ 只交给表单“HH:MM”，表单验证通过后我们再拼成当天的 datetime 存库
        post['clock_in']  = _norm_hhmm(post.get('clock_in'))
        post['clock_out'] = _norm_hhmm(post.get('clock_out'))

        form = DriverDailyReportForm(post, instance=report)
        formset = ReportItemFormSet(post, instance=report)

        if form.is_valid() and formset.is_valid():
            # === 记录保存前的旧值 ===
            _old_in  = getattr(report, "clock_in",  None)
            _old_out = getattr(report, "clock_out", None)

            inst = form.save(commit=False)

            if not inst.vehicle_id and report.vehicle_id:
                inst.vehicle_id = report.vehicle_id

            break_input = (post.get("break_time_input") or "").strip()
            user_minutes = 0
            try:
                if ":" in break_input:
                    h, m = map(int, break_input.split(":", 1))
                    user_minutes = max(0, h * 60 + m)
                elif break_input:
                    user_minutes = max(0, int(break_input))
            except Exception:
                user_minutes = 0
            total_minutes = user_minutes + BASE_BREAK_MINUTES
            inst.休憩時間 = timedelta(minutes=total_minutes)

            # ✅ 把表单的 time/'HH:MM' 合成当天 datetime（带时区）存模型
            ci = form.cleaned_data.get("clock_in")
            co = form.cleaned_data.get("clock_out")
            unreturned = bool(form.cleaned_data.get("unreturned_flag"))

            ci_dt = _as_aware_dt(ci, report.date)
            co_dt = _as_aware_dt(co, report.date)

            if ci_dt is not None:
                inst.clock_in = ci_dt

            # 若已填写退勤时间，则视为已完成，覆盖勾选框
            if co_dt is not None:
                unreturned = False

            # 规则：
            # - 勾选“未完成入库手续” -> 退勤必须为空
            # - 未勾选：只有用户真的填了退勤才保存，否则保持为空
            if unreturned or co_dt is None:
                inst.clock_out = None
            else:
                inst.clock_out = co_dt

            try:
                inst.calculate_work_times()
            except Exception:
                pass

            inst.edited_by = request.user

            # ===== 保存主表/明细后，联动预约状态 =====
            #   - 退勤为空 + 勾选 -> status=未完成入库手续，actual_return 保持 None
            #   - 退勤有值 -> status=已完成（actual_return 会由 signals 用 inst.clock_out 同步回预约）
            try:
                from dailyreport.signals import _pick_reservation_for_report
                res = _pick_reservation_for_report(inst)
                if res:
                    if inst.clock_out is None:
                        # 退勤为空：实际入库也保持空
                        res.actual_return = None
                        if unreturned:
                            # 勾选“未完成入库手续”
                            try:
                                from vehicles.models import ReservationStatus
                                res.status = ReservationStatus.INCOMPLETE  # ← 使用新的枚举
                            except Exception:
                                res.status = "未完成出入库手续"
                            res.save(update_fields=["actual_return", "status"])
                        else:
                            res.save(update_fields=["actual_return"])
                    else:
                        # 退勤有值 => 已完成（actual_return 会由 signals 用 inst.clock_out 同步）
                        try:
                            res.status = ReservationStatus.DONE
                        except Exception:
                            # 兜底也用英文值，避免混入中文
                            res.status = "done"
                        res.save(update_fields=["status"])

                        # >>> BEGIN patch: finalize report times and status (views)
                        from django.utils import timezone
                        from dailyreport.models import DriverDailyReport

                        changed_fields_for_report = []

                        # 用本地时区把预约的实际出入库写回日报的 time 字段（避免 Time vs UTC DateTime 比较错误）
                        if getattr(res, "actual_departure", None):
                            _t_in = timezone.localtime(res.actual_departure).time()
                            if report.clock_in != _t_in:
                                report.clock_in = _t_in
                                changed_fields_for_report.append("clock_in")

                        if getattr(res, "actual_return", None):
                            _t_out = timezone.localtime(res.actual_return).time()
                            if report.clock_out != _t_out:
                                report.clock_out = _t_out
                                changed_fields_for_report.append("clock_out")

                        # 若日报已有出勤/退勤，则显式把状态置为已完成（completed）
                        if report.clock_in and report.clock_out and report.status != DriverDailyReport.STATUS_COMPLETED:
                            report.status = DriverDailyReport.STATUS_COMPLETED
                            changed_fields_for_report.append("status")

                        if changed_fields_for_report:
                            report.save(update_fields=changed_fields_for_report)
                        # >>> END patch

            except Exception as _e:
                logger.warning("update reservation status (incomplete/done) failed: %s", _e)
                
            # ===== [END] 预约状态联动 =====

            cash_total = sum(
                (it.cleaned_data.get('meter_fee') or 0)
                for it in formset.forms
                if it.cleaned_data.get('payment_method') == 'cash'
                and not it.cleaned_data.get('DELETE', False)
            )
            charter_cash_total = sum(
                (it.cleaned_data.get('charter_amount_jpy') or 0)
                for it in formset.forms
                if it.cleaned_data.get('is_charter')
                and (it.cleaned_data.get('charter_payment_method') in [
                    'jpy_cash', 'jp_cash', 'cash', 'rmb_cash',
                    'self_wechat', 'boss_wechat'
                ])
                and not it.cleaned_data.get('DELETE', False)
            )
            deposit = inst.deposit_amount or 0
            inst.deposit_difference = deposit - cash_total - charter_cash_total

            inst.save()
            formset.instance = inst
            items = formset.save(commit=False)
            for item in items:
                if getattr(item, "is_pending", None) is None:
                    item.is_pending = False
                item.save()

            # >>> [SYNC-RESERVATION CALL]
            try:
                _sync_reservation_actual_for_report(inst, _old_in, _old_out)
            except Exception as _e:
                logger.warning("sync reservation (dailyreport_edit_for_driver) failed: %s", _e)
            # <<< [SYNC-RESERVATION CALL]

            try:
                inst.has_issue = inst.items.filter(has_issue=True).exists()
                inst.save(update_fields=["has_issue"])
            except Exception:
                pass

            messages.success(request, "保存しました。")
            return redirect("dailyreport:driver_dailyreport_edit",
                            driver_id=driver.id, report_id=inst.id)
        else:
            messages.error(request, "❌ 保存失败，请检查输入内容")
    else:
        _prefill_report_without_fk(report)
        form = DriverDailyReportForm(instance=report)
        formset = ReportItemFormSet(instance=report)

    # ---------- 预填：尝试从 Reservation 带出车辆与实际出/入库（仅 GET，不写库） ----------
        try:
            from django.db.models import Q
            from vehicles.models import Reservation

            # 同一天的预约
            res_qs = Reservation.objects.filter(date=report.date)
            print("[prefill] report.id=", report.id, "report.date=", report.date)

            # 司机匹配：兼容“日报用档案ID、预约用账号ID”的场景
            d = report.driver
            user_obj = getattr(d, "user", None) or getattr(d, "account", None) \
                       or getattr(d, "auth_user", None) or getattr(d, "profile_user", None)
            cand = Q()
            if user_obj and getattr(user_obj, "id", None):
                cand |= Q(driver_id=user_obj.id)
                cand |= Q(driver__username=getattr(user_obj, "username", None))
            # 兜底：万一两边引用的是同一张表
            cand |= Q(driver_id=getattr(d, "id", None))
            res_qs = res_qs.filter(cand)

            # 若日报已选车，则进一步按车辆过滤
            if getattr(report, "vehicle_id", None):
                res_qs = res_qs.filter(vehicle_id=report.vehicle_id)

            # 优先选择“reserved/done”的预约；没有再取最早一条
            preferred = res_qs.filter(status__in=["reserved", "done"]).order_by("start_time").first()
            res = preferred or res_qs.order_by("start_time").first()
            print("[prefill] matched reservation ->",
                    None if not res else dict(
                        id=res.id,
                        vehicle_id=res.vehicle_id,
                        actual_departure=res.actual_departure,
                        actual_return=res.actual_return,
                        status=res.status,
                    ))


            if res:
                # 1) 预填车辆（日报未选车，预约有车）
                if not getattr(report, "vehicle_id", None) and getattr(res, "vehicle_id", None):
                    form.initial["vehicle"] = res.vehicle_id
                    if "vehicle" in form.fields:
                        form.fields["vehicle"].initial = res.vehicle_id  # 双保险：字段级 initial

                # 2) 预填出勤/退勤（日报为空，预约有“实际出/入库”），仅填 HH:MM
                if not getattr(report, "clock_in", None) and getattr(res, "actual_departure", None):
#                    form.initial["clock_in"] = res.actual_departure.astimezone().strftime("%H:%M") \
#                        if hasattr(res.actual_departure, "astimezone") else res.actual_departure.strftime("%H:%M")
                    _in = res.actual_departure
                    hhmm_in = (_in.astimezone().strftime("%H:%M") if hasattr(_in, "astimezone") else _in.strftime("%H:%M"))
                    form.initial["clock_in"] = hhmm_in
                    if "clock_in" in form.fields:
                        form.fields["clock_in"].initial = hhmm_in
                
                
                if not getattr(report, "clock_out", None) and getattr(res, "actual_return", None):
#                    form.initial["clock_out"] = res.actual_return.astimezone().strftime("%H:%M") \
#                        if hasattr(res.actual_return, "astimezone") else res.actual_return.strftime("%H:%M")
                    _out = res.actual_return
                    hhmm_out = (_out.astimezone().strftime("%H:%M") if hasattr(_out, "astimezone") else _out.strftime("%H:%M"))
                    form.initial["clock_out"] = hhmm_out
                    if "clock_out" in form.fields:
                        form.fields["clock_out"].initial = hhmm_out
        except Exception:
            # 静默容错：预填失败不影响页面打开
            pass

    data_iter = []
    for f in formset.forms:
        if f.is_bound and f.is_valid():
            cleaned = f.cleaned_data
            if not cleaned.get("DELETE", False):
                data_iter.append({
                    'meter_fee': _to_int0(cleaned.get('meter_fee')),
                    'payment_method': cleaned.get('payment_method') or '',
                    'note': cleaned.get('note') or '',
                    'DELETE': False,
                })
        elif f.instance and not getattr(f.instance, 'DELETE', False):
            data_iter.append({
                'meter_fee': _to_int0(getattr(f.instance, 'meter_fee', 0)),
                'payment_method': getattr(f.instance, 'payment_method', '') or '',
                'note': getattr(f.instance, 'note', '') or '',
                'DELETE': False,
            })
    totals_raw = calculate_totals_from_formset(data_iter)
    totals = {f"{k}_raw": v["total"] for k, v in totals_raw.items() if isinstance(v, dict)}
    totals.update({f"{k}_split": v["bonus"] for k, v in totals_raw.items() if isinstance(v, dict)})
    totals["meter_only_total"] = totals_raw.get("meter_only_total", 0)

    summary_keys = [
        ('meter', 'メーター(水揚)'),
        ('cash', '現金(ながし)'),
        ('uber', 'Uber'),
        ('didi', 'Didi'),
        ('credit', 'クレジ'),
        ('kyokushin', '京交信'),
        ('omron', 'オムロン'),
        ('kyotoshi', '京都市他'),
        ('qr', '扫码'),
    ]

    actual_break_min = _minutes_from_timedelta(getattr(report, "休憩時間", None))
    input_break_min  = max(0, actual_break_min - BASE_BREAK_MINUTES)
    break_time_h, break_time_m = divmod(input_break_min, 60)
    break_time_m = f"{break_time_m:02d}"
    actual_break_value = f"{actual_break_min // 60}:{actual_break_min % 60:02d}"

    return render(request, 'dailyreport/driver_dailyreport_edit.html', {
        'form': form,
        'formset': formset,
        'driver': driver,
        'report': report,
        'is_edit': True,
        'summary_keys': summary_keys,
        'totals': totals,
        'break_time_h': break_time_h,
        'break_time_m': break_time_m,
        'actual_break_value': actual_break_value,
    })

# ========= 未分配账号司机：当天创建 =========
@user_passes_test(is_dailyreport_admin)
def driver_dailyreport_add_unassigned(request, driver_id):
    driver = get_object_or_404(Driver, id=driver_id, user__isnull=True)
    if not driver or driver.user:
        messages.warning(request, "未找到未分配账号的员工")
        return redirect("dailyreport:dailyreport_overview")

    today = date.today()
    report, created = DriverDailyReport.objects.get_or_create(
        driver=driver,
        date=today,
        defaults={"status": "草稿"}
    )
    print("🚗 创建日报：", driver.id, report.id, "是否新建：", created)

    if created:
        messages.success(request, f"已为 {driver.name} 创建 {today} 的日报。")
    else:
        messages.info(request, f"{driver.name} 今天的日报已存在，跳转到编辑页面。")

    return redirect("dailyreport:driver_dailyreport_edit", driver_id=driver.id, report_id=report.id)

# ========= 我的日报 =========
@login_required
def my_dailyreports(request):
    try:
        driver = Driver.objects.get(user=request.user)
    except Driver.DoesNotExist:
        return render(request, 'dailyreport/not_found.html', {
            'message': '该用户未绑定司机档案。'
        }, status=404)

    reports = DriverDailyReport.objects.filter(driver=driver).order_by('-date')
    return render(request, 'dailyreport/my_dailyreports.html', {
        'reports': reports,
        'driver': driver,
    })

# ========= 批量补账号 =========
@user_passes_test(is_dailyreport_admin)
def bind_missing_users(request):
    drivers_without_user = Driver.objects.filter(user__isnull=True)

    if request.method == 'POST':
        for driver in drivers_without_user:
            username = f"driver{driver.driver_code}"
            if not User.objects.filter(username=username).exists():
                user = User.objects.create_user(username=username, password='12345678')
                driver.user = user
                driver.save()
        return redirect('sdailyreport:bind_missing_users')

    return render(request, 'dailyreport/bind_missing_users.html', {
        'drivers': drivers_without_user,
    })

# ========= 导出：ETC 明细 =========
@user_passes_test(is_dailyreport_admin)
def export_etc_daily_csv(request, year, month):
    reports = DriverDailyReport.objects.filter(date__year=year, date__month=month)

    response = HttpResponse(content_type='text/csv')
    filename = f"ETC_日報明細_{year}-{month:02d}.csv"
    response['Content-Disposition'] = f'attachment; filename="{escape_uri_path(filename)}"'

    writer = csv.writer(response)
    writer.writerow(['日期', '司机', 'ETC应收（円）', 'ETC实收（円）', '未收差额（円）'])

    for report in reports.order_by('date', 'driver__name'):
        expected = report.etc_expected or 0
        collected = report.etc_collected or 0
        diff = expected - collected

        writer.writerow([
            report.date.strftime('%Y-%m-%d'),
            report.driver.name if report.driver else "",
            expected,
            collected,
            diff
        ])

    return response

# ========= 导出：车辆运输实绩 =========
@user_passes_test(is_dailyreport_admin)
def export_vehicle_csv(request, year, month):
    reports = DriverDailyReport.objects.filter(
        date__year=year,
        date__month=month,
        vehicle__isnull=False
    ).select_related('vehicle')

    data = defaultdict(lambda: {
        '出勤日数': 0,
        '走行距離': 0,
        '実車距離': 0,
        '乗車回数': 0,
        '人数': 0,
        '水揚金額': 0,
        '車名': '',
        '車牌': '',
        '部門': '',
        '使用者名': '',
        '所有者名': '',
    })

    for r in reports:
        car = r.vehicle
        if not car:
            continue

        key = car.id
        mileage = float(r.mileage or 0)
        total_fee = float(r.total_meter_fee or 0)
        boarding_count = r.items.count()

        if r.items.filter(start_time__isnull=False, end_time__isnull=False).exists():
            data[key]['出勤日数'] += 1

        data[key]['走行距離'] += mileage
        data[key]['実車距離'] += mileage * 0.75
        data[key]['乗車回数'] += boarding_count
        data[key]['人数'] += boarding_count * 2
        data[key]['水揚金額'] += total_fee
        data[key]['車名'] = car.name
        data[key]['車牌'] = car.license_plate
        data[key]['部門'] = getattr(car, 'department', '')
        data[key]['使用者名'] = getattr(car, 'user_company_name', '')
        data[key]['所有者名'] = getattr(car, 'owner_company_name', '')

    response = HttpResponse(content_type='text/csv')
    filename = f"{year}年{month}月_車両運輸実績表.csv"
    response['Content-Disposition'] = f"attachment; filename*=UTF-8''{quote(filename)}"

    response.write(u'\ufeff'.encode('utf8'))
    writer = csv.writer(response)

    headers = ['車名', '車牌', '部門', '使用者名', '所有者名',
               '出勤日数', '走行距離', '実車距離', '乗車回数', '人数', '水揚金額']
    writer.writerow(headers)

    total_row = [0] * 6
    for info in data.values():
        row = [
            info['車名'], info['車牌'], info['部門'],
            info['使用者名'], info['所有者名'],
            info['出勤日数'], info['走行距離'],
            round(info['実車距離'], 2),
            info['乗車回数'], info['人数'],
            round(info['水揚金額'], 2),
        ]
        writer.writerow(row)
        for i in range(5, 11):
            total_row[i - 5] += row[i]

    writer.writerow([
        '合計', '', '', '', '',
        total_row[0], total_row[1], round(total_row[2], 2),
        total_row[3], total_row[4], round(total_row[5], 2),
    ])

    return response

# ========= 月份入口（表单选择） =========
@user_passes_test(is_dailyreport_admin)
def dailyreport_add_by_month(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)

    month_str = request.GET.get("month")
    if not month_str:
        return redirect("dailyreport:driver_dailyreport_add_selector", driver_id=driver_id)

    try:
        year, month = map(int, month_str.split("-"))
        assert 1 <= month <= 12
    except (ValueError, AssertionError):
        return redirect("dailyreport:driver_dailyreport_add_selector", driver_id=driver_id)

    current_month = f"{year}年{month}月"

    if request.method == "POST":
        selected_date_str = request.POST.get("selected_date")
        try:
            selected_date = datetime.strptime(selected_date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return render(request, "dailyreport/driver_dailyreport_add.html", {
                "driver": driver, "year": year, "month": month,
                "current_month": current_month, "error": "日付が正しくありません"
            })

        base_url = reverse("dailyreport:driver_dailyreport_direct_add", args=[driver.id])
        query_string = urlencode({"date": selected_date})
        url = f"{base_url}?{query_string}"
        return redirect(url)

    return render(request, "dailyreport/driver_dailyreport_add.html", {
        "driver": driver,
        "year": year,
        "month": month,
        "current_month": current_month,
    })

# ========= 月度总览 =========
@user_passes_test(is_dailyreport_admin)
def dailyreport_overview(request):
    today = now().date()
    keyword = request.GET.get('keyword', '').strip()
    month_str = request.GET.get('month', '')

    try:
        month = datetime.strptime(month_str, "%Y-%m")
    except ValueError:
        month = today.replace(day=1)
        month_str = month.strftime('%Y-%m')

    month_label = f"{month.year}年{month.month:02d}月"
    prev_month = (month - relativedelta(months=1)).strftime('%Y-%m')
    next_month = (month + relativedelta(months=1)).strftime('%Y-%m')

    export_year = month.year
    export_month = month.month

    # ========== [BEGIN 保留：原来的按业务日期月份过滤] ==========
    # reports_all = DriverDailyReport.objects.filter(
    #     date__year=month.year,
    #     date__month=month.month,
    # )
    # ========== [END   保留：原来的按业务日期月份过滤] ==========

    # ========== [BEGIN 新：按“勤務開始日(开始日)”归属月份] ==========

    # 约定：clock_in < 06:00 视为夜勤跨零点 → 归前一天
    work_date_expr = Case(
        When(clock_in__lt=time(6, 0),
            then=ExpressionWrapper(F('date') - timedelta(days=1), output_field=DateField())),
        default=F('date'),
        output_field=DateField()
    )

    reports_all = (
        DriverDailyReport.objects
        .annotate(work_date=work_date_expr)
        .filter(work_date__year=month.year, work_date__month=month.month)
    )
    # ========== [END   新：按“勤務開始日(开始日)”归属月份] ==========

    drivers = get_active_drivers(month, keyword)

    if keyword:
        drivers = drivers.filter(
            Q(name__icontains=keyword) |
            Q(kana__icontains=keyword) |
            Q(driver_code__icontains=keyword)
        )

    reports = reports_all.filter(driver__in=drivers)

    # ========== [BEGIN 保留：旧写法，统计了所有司机（含已离职）] ==========
    # items_all = DriverDailyReportItem.objects.filter(report__in=reports_all)
    # ========== [END   保留] ==========

    # ========== [BEGIN 新写法：仅统计页面显示的司机（活跃/筛选后）] ==========
    items_all = DriverDailyReportItem.objects.filter(report__in=reports)
    # ========== [END   新写法] ==========
    items_norm = items_all.annotate(
        pm=Lower(Trim('payment_method')),
        cpm=Lower(Trim('charter_payment_method')),
    )

    totals = defaultdict(Decimal)
    counts = defaultdict(int)

    meter_sum_non_charter = items_norm.filter(is_charter=False)\
        .aggregate(x=Sum('meter_fee'))['x'] or Decimal('0')
    totals['total_meter'] = meter_sum_non_charter
    totals['meter_only_total'] = meter_sum_non_charter

    ALIASES = {
        'cash':      {'normal': ['cash'],                 'charter': ['jpy_cash']},
        'credit':    {'normal': ['credit', 'credit_card'],'charter': ['credit','credit_card']},
        'uber':      {'normal': ['uber'],                 'charter': ['uber']},
        'didi':      {'normal': ['didi'],                 'charter': ['didi']},
        'kyokushin': {'normal': ['kyokushin'],            'charter': ['kyokushin']},
        'omron':     {'normal': ['omron'],                'charter': ['omron']},
        'kyotoshi':  {'normal': ['kyotoshi'],             'charter': ['kyotoshi']},
        'qr':        {'normal': ['qr', 'scanpay'],        'charter': ['qr', 'scanpay']},
    }
    EXCLUDE_CHARTER_IN_METHODS = {'cash'}

    for key, alias in ALIASES.items():
        normal_qs = items_norm.filter(is_charter=False, pm__in=alias['normal'])
        normal_amt = normal_qs.aggregate(x=Sum('meter_fee'))['x'] or Decimal('0')
        normal_cnt = normal_qs.count()

        charter_amt = Decimal('0')
        charter_cnt = 0
        if key not in EXCLUDE_CHARTER_IN_METHODS:
            charter_qs = items_norm.filter(is_charter=True, cpm__in=alias['charter'])
            charter_amt = charter_qs.aggregate(x=Sum('charter_amount_jpy'))['x'] or Decimal('0')
            charter_cnt = charter_qs.count()

        totals[f'total_{key}'] = normal_amt + charter_amt
        counts[key] = normal_cnt + charter_cnt

    totals['charter_cash_total'] = items_norm.filter(
        is_charter=True, cpm__in=['jpy_cash']
    ).aggregate(x=Sum('charter_amount_jpy'))['x'] or Decimal('0')

    totals['charter_uncollected_total'] = items_norm.filter(
        is_charter=True, cpm__in=['to_company', 'invoice', 'uncollected', '未収', '請求']
    ).aggregate(x=Sum('charter_amount_jpy'))['x'] or Decimal('0')

    totals['total_meter'] = (
        (totals.get('meter_only_total') or Decimal('0')) +
        (totals.get('charter_cash_total') or Decimal('0')) +
        (totals.get('charter_uncollected_total') or Decimal('0'))
    )

    rates = {
        'meter':     Decimal('0.9091'),
        'cash':      Decimal('0'),
        'uber':      Decimal('0.05'),
        'didi':      Decimal('0.05'),
        'credit':    Decimal('0.05'),
        'kyokushin': Decimal('0.05'),
        'omron':     Decimal('0.05'),
        'kyotoshi':  Decimal('0.05'),
        'qr':        Decimal('0.05'),
    }

    def split(key):
        amt = totals.get(f"total_{key}") or Decimal('0')
        return (amt * rates[key]).quantize(Decimal('1'), rounding=ROUND_HALF_UP)

    totals_all = {k: {"total": totals.get(f"total_{k}", Decimal("0")), "bonus": split(k)} for k in rates}
    totals_all["meter_only_total"] = totals.get("meter_only_total", Decimal("0"))

    gross = totals.get('total_meter') or Decimal('0')
    totals['meter_pre_tax'] = (gross / Decimal('1.1')).quantize(Decimal('1'), rounding=ROUND_HALF_UP)

    etc_shortage_total = reports.aggregate(total=Sum('etc_shortage'))['total'] or 0

    items = DriverDailyReportItem.objects.filter(report__in=reports)
    per_driver = items.values('report__driver').annotate(
        meter_only=Sum('meter_fee', filter=Q(is_charter=False)),
        charter_cash=Sum(
            'charter_amount_jpy',
            filter=Q(is_charter=True, charter_payment_method__in=['jpy_cash', 'jp_cash', 'cash'])
        ),
        charter_uncol=Sum(
            'charter_amount_jpy',
            filter=Q(is_charter=True, charter_payment_method__in=['to_company', 'invoice', 'uncollected', '未収', '請求'])
        ),
    )

    fee_map = {
        r['report__driver']: (r['meter_only'] or 0) + (r['charter_cash'] or 0) + (r['charter_uncol'] or 0)
        for r in per_driver
    }

    sort = request.GET.get("sort", "amount_desc")

    def code_key(d):
        code = (getattr(d, "driver_code", "") or "").strip()
        if code.isdigit():
            return (0, int(code))
        return (1, code)

    if sort == "code_asc":
        ordered_drivers = sorted(drivers, key=code_key)
    elif sort == "code_desc":
        ordered_drivers = sorted(drivers, key=code_key, reverse=True)
    elif sort == "amount_asc":
        ordered_drivers = sorted(
            drivers,
            key=lambda d: (fee_map.get(d.id, Decimal("0")), code_key(d))
        )
    else:
        ordered_drivers = sorted(
            drivers,
            key=lambda d: (fee_map.get(d.id, Decimal("0")), code_key(d)),
            reverse=True
        )

    driver_data = []
    for d in ordered_drivers:
        total = fee_map.get(d.id, Decimal("0"))
        has_any = d.id in fee_map
        has_issue = reports.filter(driver=d, has_issue=True).exists()
        note = "⚠️ 異常あり" if has_issue else ("（未報告）" if not has_any else "")
        driver_data.append({
            'driver': d,
            'total_fee': total,
            'note': note,
            'month_str': month_str,
        })

    page_obj = Paginator(driver_data, 10).get_page(request.GET.get('page'))

    summary_keys = [
        ('meter', 'メーター(水揚)'),
        ('cash', '現金'),
        ('uber', 'Uber'),
        ('didi', 'Didi'),
        ('credit', 'クレジットカード'),
        ('kyokushin', '京交信'),
        ('omron', 'オムロン'),
        ('kyotoshi', '京都市他'),
        ('qr', '扫码'),
    ]

    return render(request, 'dailyreport/dailyreport_overview.html', {
        'totals': totals,
        'totals_all': totals_all,
        'etc_shortage_total': etc_shortage_total,
        'drivers': drivers,
        'page_obj': page_obj,
        'counts': counts,
        'current_sort': sort,
        'keyword': keyword,
        'month_str': month_str,
        'current_year': export_year,
        'current_month': export_month,
        'summary_keys': summary_keys,
        'month_label': month_label,
        'prev_month': prev_month,
        'next_month': next_month,
        'sort': sort,
    })
