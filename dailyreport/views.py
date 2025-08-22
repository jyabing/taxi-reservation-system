from types import SimpleNamespace as NS
from django.forms import inlineformset_factory

import csv, os, sys, logging
from io import BytesIO
logger = logging.getLogger(__name__)
from datetime import datetime, date, timedelta, time
from tempfile import NamedTemporaryFile

from django.contrib.auth.decorators import user_passes_test, login_required
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.shortcuts import render, get_object_or_404, redirect, HttpResponse
from django.utils.timezone import now
from django.utils import timezone
from django.db.models import IntegerField, Value, Case, When, ExpressionWrapper, F, Sum, Q, Count
from django.db.models.functions import Substr, Cast, Coalesce, NullIf  # ←【在这行里确保包含 Coalesce, NullIf】
from django.http import HttpResponse, FileResponse
from django.utils.encoding import escape_uri_path
from django.urls import reverse
from django.utils.http import urlencode
from dateutil.relativedelta import relativedelta

from django.db.models.functions import Lower, Trim, ExtractHour, ExtractMinute
from dailyreport.constants import PAYMENT_RATES
from vehicles.utils import mark_linked_reservation_incomplete


from dailyreport.models import DriverDailyReport, DriverDailyReportItem
from .forms import DriverDailyReportForm, DriverDailyReportItemForm, ReportItemFormSet
from .services.calculations import calculate_deposit_difference  # ✅ 导入新函数

from staffbook.services import get_driver_info

from staffbook.models import Driver
from dailyreport.services.summary import (
    resolve_payment_method, 
    calculate_totals_from_instances, calculate_totals_from_formset
)
from dailyreport.constants import CHARTER_CASH_KEYS, CHARTER_UNCOLLECTED_KEYS

from vehicles.models import Reservation
from urllib.parse import quote
from carinfo.models import Car  # 🚗 请根据你项目中车辆模型名称修改
from collections import defaultdict

from decimal import Decimal, ROUND_HALF_UP
from calendar import monthrange, month_name
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from dailyreport.utils.debug import debug_print

DEBUG_PRINT_ENABLED = True
#import builtins
#builtins.print = lambda *args, **kwargs: None   #删除或注释掉

def test_view(request):
    print("✅ test_view 被调用", flush=True)
    return HttpResponse("ok")

debug_print("✅ DEBUG_PRINT 导入成功，模块已执行")
# 直接测试原生 print 看能否打印
print("🔥🔥🔥 原生 print 测试：views.py 模块加载成功")

# --- 安全整数转换：空串/None/异常 -> 0  ←【新增：就插在这里】
def _to_int0(v):
    try:
        if v in ("", None):
            return 0
        return int(v)
    except (TypeError, ValueError):
        return 0

NIGHT_END_MIN = 5 * 60  # 05:00

def _sorted_items_qs(report):
    """
    ride_time 为字符串(HH:MM)时的排序：
    05:00 之前的时间 +24h 排到当天最后
    """
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
# --- end 明细时间排序 ---

def is_dailyreport_admin(user):
    """
    允许：superuser 或 拥有 dailyreport_admin / dailyreport 模块权限；回退 is_staff。
    如你的权限键不同，请把下面的 key 改成你实际使用的。
    """
    try:
        return (
            check_module_permission(user, 'dailyreport_admin')
            or check_module_permission(user, 'dailyreport')
            or getattr(user, 'is_superuser', False)
        )
    except Exception:
        return bool(getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False))

# 你文件里大量写了 @user_passes_test(is_dailyreport_admin)，继续可用；
# 若需要装饰器名，也提供一个等价别名：
dailyreport_admin_required = user_passes_test(is_dailyreport_admin)

def get_active_drivers(month_obj=None, keyword=None):
    """
    返回完整的 Driver QuerySet（不使用 values），
    只筛当月在职，支持关键词。
    """
    qs = Driver.objects.all()
    if month_obj is None:
        month_obj = date.today()

    first_day = date(month_obj.year, month_obj.month, 1)
    last_day = date(month_obj.year, month_obj.month, monthrange(month_obj.year, month_obj.month)[1])

    qs = qs.filter(
        Q(hire_date__lte=last_day) &
        (Q(resigned_date__isnull=True) | Q(resigned_date__gte=first_day))
    )

    if keyword:
        qs = qs.filter(
            Q(name__icontains=keyword) |
            Q(kana__icontains=keyword) |
            Q(driver_code__icontains=keyword)
        )

    return qs.order_by('name')

# ✅ 新增日报
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

# ✅ 编辑日报（管理员）
@user_passes_test(is_dailyreport_admin)
def dailyreport_edit(request, pk):
    report = get_object_or_404(DriverDailyReport, pk=pk)

    ReportItemFormSet = inlineformset_factory(
        DriverDailyReport,
        DriverDailyReportItem,
        form=DriverDailyReportItemForm,
        formset=RequiredReportItemFormSet,
        extra=0,
        can_delete=True,
        max_num=40
    )

    if request.method == 'POST':
        form = DriverDailyReportForm(request.POST, instance=report)
        formset = ReportItemFormSet(request.POST, instance=report)

        if form.is_valid() and formset.is_valid():
            cd = form.cleaned_data
            report = form.save(commit=False)

            # ✅ 小工具：None/'' -> 0
            def _to_int(v):
                try:
                    return int(v or 0)
                except (TypeError, ValueError):
                    return 0

            # ⚠️ etc_expected 是 @property，只读，不能赋值
            # report.etc_expected = _to_int(cd.get('etc_expected'))  # ← 删除

            # 明细
            report.etc_collected_cash = _to_int(cd.get('etc_collected_cash') or request.POST.get('etc_collected_cash'))
            report.etc_collected_app  = _to_int(cd.get('etc_collected_app')  or request.POST.get('etc_collected_app'))

            # 汇总（若为空，用 cash+app 兜底）
            etc_collected_val = cd.get('etc_collected')
            report.etc_collected = _to_int(
                etc_collected_val if etc_collected_val not in [None, '']
                else (report.etc_collected_cash or 0) + (report.etc_collected_app or 0)
            )

            # 空车ETC金额（兼容旧字段名 etc_empty_amount）
            report.etc_uncollected = _to_int(
                cd.get('etc_uncollected') or request.POST.get('etc_uncollected') or request.POST.get('etc_empty_amount')
            )

            # 收取方式（可为空）
            report.etc_payment_method = cd.get('etc_payment_method') or None

            # 不足额：若表单提供则用表单；否则用只读 etc_expected 回算
            if 'etc_shortage' in form.fields:
                report.etc_shortage = _to_int(cd.get('etc_shortage'))
            else:
                expected_val = _to_int(getattr(report, 'etc_expected', 0))
                report.etc_shortage = max(0, expected_val - _to_int(report.etc_collected))

            report.save()
            formset.save()

            messages.success(request, "保存成功！")
            return redirect('dailyreport:dailyreport_edit', pk=report.pk)
        else:
            messages.error(request, "保存失败，请检查输入内容")
    else:
        form = DriverDailyReportForm(instance=report)
        formset = ReportItemFormSet(instance=report)

    return render(request, 'dailyreport/driver_dailyreport_edit.html', {
        'form': form,
        'formset': formset,
        'report': report
    })


@login_required
def sales_thanks(request):
    return render(request, 'dailyreport/sales_thanks.html')

# ✅ 删除日报（管理员）
@user_passes_test(is_dailyreport_admin)
def dailyreport_delete_for_driver(request, driver_id, pk):
    driver = get_object_or_404(Driver, pk=driver_id)
    report = get_object_or_404(DriverDailyReport, pk=pk, driver=driver)
    if request.method == "POST":
        report.delete()
        messages.success(request, "已删除该日报记录。")
        return redirect('dailyreport:driver_dailyreport_month', driver_id=driver.id)
    return render(request, 'dailyreport/dailyreport_confirm_delete.html', {
        'report': report,
        'driver': driver,
    })

# ✅ 日报列表（管理员看全部，司机看自己）
@login_required
def dailyreport_list(request):
    if request.user.is_staff:
        reports = DriverDailyReport.objects.all().order_by('-date')
    else:
        reports = DriverDailyReport.objects.filter(driver=request.user).order_by('-date')
    return render(request, 'dailyreport/dailyreport_list.html', {'reports': reports})

#全员每日明细
# ✅ 新版本：全员每日明细导出为 Excel（每个日期一个 Sheet）
@user_passes_test(is_dailyreport_admin)
def export_dailyreports_csv(request, year, month):

    reports = (
        DriverDailyReport.objects
        .filter(date__year=year, date__month=month)
        .select_related('driver')
        .prefetch_related('items')
        .order_by('date', 'driver__name')
    )

    reports_by_date = defaultdict(list)

    # ✅ 所有统计用支付方式
    payment_keys = ['cash', 'uber', 'didi', 'ticket', 'credit', 'qr']

    for report in reports:
        summary = defaultdict(int)

        for item in report.items.all():
            if (
                item.payment_method in payment_keys
                and item.meter_fee and item.meter_fee > 0
                and (not item.note or 'キャンセル' not in item.note)
            ):
                summary[item.payment_method] += item.meter_fee

        deposit = report.deposit_amount or 0
        etc_app = report.etc_collected_app or 0
        etc_cash = report.etc_collected_cash or 0
        etc_total = etc_app + etc_cash
        etc_expected = report.etc_expected or 0
        etc_diff = etc_expected - etc_total
        deposit_diff = calculate_deposit_difference(report, summary['cash'])

        reports_by_date[report.date.strftime('%Y-%m-%d')].append({
            'driver_code': report.driver.driver_code if report.driver else '',
            'driver': report.driver.name if report.driver else '',
            'status': report.get_status_display(),
            'cash': summary['cash'],
            'uber': summary['uber'],
            'didi': summary['didi'],
            'ticket': summary['ticket'],
            'credit': summary['credit'],
            'qr': summary['qr'],
            'etc_expected': etc_expected,
            'etc_collected': etc_total,
            'etc_diff': etc_diff,
            'deposit': deposit,
            'deposit_diff': deposit_diff,
            'mileage': report.mileage or '',
            'gas_volume': report.gas_volume or '',
            'note': report.note or '',
        })

    # ✅ 创建 Excel 工作簿
    wb = Workbook()
    wb.remove(wb.active)

    for date_str, rows in sorted(reports_by_date.items()):
        ws = wb.create_sheet(title=date_str)

        headers = [
            '司机代码', '司机', '出勤状态',
            '现金', 'Uber', 'Didi', 'チケット', 'クレジット', '扫码',
            'ETC应收', 'ETC实收', '未收ETC',
            '入金', '差額',
            '公里数', '油量', '备注'
        ]
        ws.append(headers)

        for row in rows:
            ws.append([
                row['driver_code'],
                row['driver'],
                row['status'],
                row['cash'],
                row['uber'],
                row['didi'],
                row['ticket'],
                row['credit'],
                row['qr'],
                row['etc_expected'],
                row['etc_collected'],
                row['etc_diff'],
                row['deposit'],
                row['deposit_diff'],
                row['mileage'],
                row['gas_volume'],
                row['note'],
            ])

    filename = f"{year}年{month}月全员每日明细.xlsx"
    tmp = NamedTemporaryFile()
    wb.save(tmp.name)
    tmp.seek(0)

    response = FileResponse(tmp, as_attachment=True, filename=quote(filename))
    response['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    return response

@login_required
def sales_thanks(request):
    return render(request, 'dailyreport/sales_thanks.html')

# ✅ 删除日报（管理员）
@user_passes_test(is_dailyreport_admin)
def dailyreport_delete_for_driver(request, driver_id, pk):
    driver = get_object_or_404(Driver, pk=driver_id)
    report = get_object_or_404(DriverDailyReport, pk=pk, driver=driver)
    if request.method == "POST":
        report.delete()
        messages.success(request, "已删除该日报记录。")
        return redirect('dailyreport:driver_dailyreport_month', driver_id=driver.id)
    return render(request, 'dailyreport/dailyreport_confirm_delete.html', {
        'report': report,
        'driver': driver,
    })

# ✅ 日报列表（管理员看全部，司机看自己）
@login_required
def dailyreport_list(request):
    if request.user.is_staff:
        reports = DriverDailyReport.objects.all().order_by('-date')
    else:
        reports = DriverDailyReport.objects.filter(driver=request.user).order_by('-date')
    return render(request, 'dailyreport/dailyreport_list.html', {'reports': reports})

# 全员每日明细（每个日期一个 Sheet，仿截图样式）
@user_passes_test(is_dailyreport_admin)
def export_dailyreports_excel(request, year, month):
    """全员每日 Excel 导出（索引 + 每日 + 月度(集計)）
    - 金额列：¥#,##0
    - L/KM 两位小数
    - 月度(集計)出勤時数(h) 两位小数
    - 负数過不足标红
    """
    # 依赖（更友好提示）
    try:
        import xlsxwriter
    except ModuleNotFoundError:
        return HttpResponse("XlsxWriter 未安装。请在虚拟环境中运行：pip install XlsxWriter", status=500)

    # 常量
    FEE_RATE = Decimal("0.05")

    # ながし現金判定（普通单）
    CASH_METHODS = {"cash", "uber_cash", "didi_cash", "go_cash"}

    # 貸切現金 / 貸切未収 判定（全部按小写比较；“現金”不受 lower 影响，但保留以直观表达）
    #CHARTER_CASH_KEYS = {"jpy_cash", "jp_cash", "cash", "現金"}
    #CHARTER_UNCOLLECTED_KEYS = {"to_company", "invoice", "uncollected", "未収", "請求"}

    # 数据：整月日报
    reports = (
        DriverDailyReport.objects
        .filter(date__year=year, date__month=month)
        .select_related("driver")
        .prefetch_related("items")
        .order_by("date", "driver__name")
    )
    by_date = defaultdict(list)
    for r in reports:
        by_date[r.date].append(r)

    # 单日行计算
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
                # 先二分：现金 vs 非现金（非现金一律视为未収/后结）
                if cpm in CHARTER_CASH_KEYS:
                    charter_cash += charter_jpy
                else:
                    charter_uncol += charter_jpy

                # 再做渠道归集（用于未収合计、平台费率等）
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

    # === 工作簿 & 样式 ===
    output = BytesIO()
    wb = xlsxwriter.Workbook(output, {'in_memory': True, 'constant_memory': True})

    # 基础样式
    fmt_header = wb.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'bg_color': '#DDDDDD', 'border': 1})
    fmt_subheader_red = wb.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'font_color': '#CC0000'})
    fmt_border = wb.add_format({'border': 1})
    fmt_total_base = wb.add_format({'bold': True, 'bg_color': '#FFF2CC', 'border': 1, 'align': 'right'})
    fmt_right = wb.add_format({'align': 'right', 'valign': 'vcenter'})
    fmt_neg_red = wb.add_format({'font_color': '#CC0000'})

    # 金额/两位小数样式
    fmt_yen     = wb.add_format({'border': 1, 'align': 'right', 'valign': 'vcenter', 'num_format': '¥#,##0'})
    fmt_yen_tot = wb.add_format({'bold': True, 'bg_color': '#FFF2CC', 'border': 1, 'align': 'right', 'num_format': '¥#,##0'})
    fmt_num_2d   = wb.add_format({'border': 1, 'align': 'right', 'valign': 'vcenter', 'num_format': '#,##0.00'})
    fmt_num_2d_t = wb.add_format({'bold': True, 'bg_color': '#FFF2CC', 'border': 1, 'align': 'right', 'num_format': '#,##0.00'})

    # 列宽
    col_widths = {
        0:10, 1:12, 2:9, 3:9, 4:12, 5:12, 6:12, 7:14, 8:12, 9:12, 10:12, 11:12,
        12:12, 13:10, 14:14, 15:10, 16:12, 17:10, 18:12, 19:10, 20:12, 21:12,
        22:12, 23:12, 24:12, 25:12, 26:12, 27:12
    }

    # 两行表头（每日 & 集计共用）
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

    # 金额/两位小数列定位
    MONEY_COLS = {4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,27}
    TWO_DEC_COLS = {25, 26}  # L / KM

    def write_mixed_row(ws, r, values, is_total=False):
        """按列写入：金额¥、两位小数、其他"""
        for c, v in enumerate(values):
            if c in MONEY_COLS:
                num = float(v or 0)
                ws.write_number(r, c, num, fmt_yen_tot if is_total else fmt_yen)
            elif c in TWO_DEC_COLS:
                num = float(v or 0)
                ws.write_number(r, c, num, fmt_num_2d_t if is_total else fmt_num_2d)
            else:
                ws.write(r, c, v, fmt_total_base if is_total else fmt_border)

    # === 索引 Sheet ===
    idx_ws = wb.add_worksheet("索引")
    idx_ws.write_row(0, 0, ["日付", "件数"], fmt_header)
    rr = 1
    for d, reps in sorted(by_date.items()):
        idx_ws.write_row(rr, 0, [d.strftime("%Y-%m-%d"), len(reps)], fmt_border)
        rr += 1
    idx_ws.set_column(0, 0, 14); idx_ws.set_column(1, 1, 8)
    idx_ws.freeze_panes(1, 0)  # 冻结表头

    # === 每日 Sheet ===
    for d, day_reports in sorted(by_date.items()):
        def _code_key(rep):
            code = getattr(rep.driver, "driver_code", "") if rep.driver else ""
            return (int(code) if str(code).isdigit() else 10**9, str(code))
        day_reports = sorted(day_reports, key=_code_key)

        ws = wb.add_worksheet(d.strftime("%Y-%m-%d"))
        write_headers(ws)
        ws.freeze_panes(2, 2)  # 冻结两行表头 + 左两列

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

        # 「過不足」（列 27）负数标红
        if r > 2:
            ws.conditional_format(2, 27, r-1, 27, {
                'type': 'cell', 'criteria': '<', 'value': 0, 'format': fmt_neg_red
            })

    # === 月度(集計) Sheet ===
    summary_ws = wb.add_worksheet(f"{year}-{month:02d} 月度(集計)")
    # 表头
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

    # 聚合（每司机）
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
        row["days"] += 1  # 有日报记一天

        # 出勤时数（跨日修正，扣休憩）
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

    # 写入 + 合计
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
        # 将“出勤時数(h)”强制两位小数样式
        summary_ws.write_number(r, 3, float(hours_2d), fmt_num_2d)

        for k, v in row.items():
            if k in ("code","name"): continue
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
    # 覆盖“出勤時数(h)”为两位小数合计样式
    summary_ws.write_number(r, 3, float(hours_total_2d), fmt_num_2d_t)

    # 负数過不足标红
    if r > 2:
        summary_ws.conditional_format(2, 27, r-1, 27, {
            'type': 'cell', 'criteria': '<', 'value': 0, 'format': fmt_neg_red
        })

    # === 导出 ===
    wb.close()
    output.seek(0)
    filename = f"{year}年{month}月_全員毎日集計.xlsx"
    return FileResponse(output, as_attachment=True, filename=quote(filename),
                        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def _normalize(val: str) -> str:
    """把 charter_payment_method 归一化，防止显示文案/大小写导致漏算"""
    if not val:
        return ''
    v = str(val).strip().lower()
    mapping = {
        # 规范值
        'jpy_cash':'jpy_cash','rmb_cash':'rmb_cash',
        'self_wechat':'self_wechat','boss_wechat':'boss_wechat',
        'to_company':'to_company','bank_transfer':'bank_transfer',
        '--------':'','------':'','': '',
        # 现场常见写法 → 规范值（按你实际打印出来的补充）
        '現金':'jpy_cash','现金':'jpy_cash','日元現金':'jpy_cash','日元现金':'jpy_cash',
        '人民幣現金':'rmb_cash','人民币现金':'rmb_cash',
        '自有微信':'self_wechat','老板微信':'boss_wechat',
        '公司回收':'to_company','会社回収':'to_company','公司结算':'to_company',
        '銀行振込':'bank_transfer','bank':'bank_transfer',
        # ……把你打印出来的值逐个补齐
    }

    return mapping.get(v, v)

def _totals_of(items):
    """一次性算出  メータのみ / 貸切現金 / 貸切未収 / 未分類  和  sales_total"""
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
                # 未知的枚举也计入总额，避免漏算（但单列“未知”便于后续清洗）
                charter_unknown += amt
        else:
            # メータのみ：与编辑页一致，要求存在支付方式才计入
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

@user_passes_test(is_dailyreport_admin)
def driver_dailyreport_month(request, driver_id):
    from datetime import datetime, timedelta

    driver = get_object_or_404(Driver, id=driver_id)

    # 解析 ?month=YYYY-MM
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
        .prefetch_related('items')  # ✅ 避免 N+1
    )

    report_list = []
    for report in reports_qs:
        items = report.items.all()

        # 如需定位特定一天（例：2025-08-10），开启下面这个 if block：
        # if report.date.strftime('%Y-%m-%d') == '2025-08-10':
        #     for it in items:
        #         print(f"[DEBUG-8/10] id={it.id}, is_charter={getattr(it,'is_charter',None)}, "
        #               f"meter_fee={it.meter_fee}, payment_method={it.payment_method!r}, "
        #               f"charter_amount_jpy={getattr(it,'charter_amount_jpy',None)}, "
        #               f"charter_payment_method={getattr(it,'charter_payment_method',None)!r}")

        # ✅ 更健壮的合计（归一化 + 未知兜底）
        totals = _totals_of(items)

        report.total_all = totals['sales_total']                # 合計：メータのみ + 貸切現金 + 貸切未収 (+ 未分類)
        report.meter_only_total = totals['meter_only_total']    # メータのみ（不含貸切）
        report.charter_unknown_total = totals['charter_unknown_total']  # 可选：模板显示方便排查

        report_list.append(report)

    # 上/下月（可选：模板里做月切换链接）
    prev_month = (month - timedelta(days=1)).replace(day=1).strftime('%Y-%m')
    next_month = (month.replace(day=28) + timedelta(days=4)).replace(day=1).strftime('%Y-%m')

    return render(request, 'dailyreport/driver_dailyreport_month.html', {
        'driver': driver,
        'month': month,
        'reports': report_list,

        # ✅ 模板使用的几个上下文（你的模板里有）
        'selected_month': month_str,
        'selected_date': request.GET.get("date", ""),
        'today': timezone.localdate(),

        # （可选）提供 prev/next，若你想加“前の月 / 次の月”按钮
        'prev_month': prev_month,
        'next_month': next_month,
    })


@user_passes_test(is_dailyreport_admin)
def dailyreport_add_selector(request, driver_id):
    from datetime import datetime, date
    driver = get_object_or_404(Driver, pk=driver_id)

    # ✅ 解析 ?month=2025-03 参数
    month_str = request.GET.get("month")
    try:
        if month_str:
            target_year, target_month = map(int, month_str.split("-"))
            display_date = date(target_year, target_month, 1)
        else:
            display_date = date.today()
    except ValueError:
        display_date = date.today()

    current_month = display_date.strftime("%Y-%m")

    # ✅ 构造当月所有日期与是否有预约
    num_days = monthrange(display_date.year, display_date.month)[1]
    all_dates = [date(display_date.year, display_date.month, d) for d in range(1, num_days + 1)]

    reserved_dates = set()
    if driver.user:
        reserved_dates = set(
            Reservation.objects
            .filter(driver=driver.user, date__year=display_date.year, date__month=display_date.month)
            .values_list("date", flat=True)
        )

    calendar_dates = [
        {
            "date": d,
            "enabled": d in reserved_dates,
        }
        for d in all_dates
    ]

    # ✅ 提交处理
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

    # ✅ 渲染模板
    return render(request, "dailyreport/driver_dailyreport_add.html", {
        "driver": driver,
        "current_month": display_date.strftime("%Y年%m月"),
        "year": display_date.year,
        "month": display_date.month,
        "calendar_dates": calendar_dates,
    })



# ✅ 編集日報（従業員）
@user_passes_test(is_dailyreport_admin)
def dailyreport_edit_for_driver(request, driver_id, report_id):
    with open("/tmp/django_debug.log", "a", encoding="utf-8") as f:
        f.write("✅ 进入视图 dailyreport_edit_for_driver\n")

    driver = get_driver_info(driver_id)
    if not driver:
        return render(request, "dailyreport/not_found.html", status=404)

    report = get_object_or_404(DriverDailyReport, pk=report_id, driver_id=driver_id)
    duration = timedelta()
    user_h = 0
    user_m = 0

    if request.method == 'POST':
        # ① 拷贝 POST
        post = request.POST.copy()

        # ② 明细行 payment_method 归一化（保持你原有映射）
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

        # ③ 先把 etc_payment_method 取出来 → 计算“安全值”
        raw_etc = (post.get('etc_payment_method') or '').strip().lower()
        # 别名 → 语义
        if raw_etc in ('会社カード', 'company card', 'credit', 'credit card', '公司卡'):
            safe_etc = 'company_card'
        elif raw_etc in ('個人カード', 'personal card', 'personal_card'):
            # 业务禁止：一律回落公司卡
            safe_etc = 'company_card'
        elif raw_etc in ('現金', '现金', 'cash', 'cash(現金)'):
            # 如果你的模型不支持 'cash'，也统一回落公司卡
            safe_etc = 'company_card'
        else:
            # 未识别时回落
            safe_etc = 'company_card'

        # ④ 关键：提交给表单时清空该字段，绕开 Choice 校验
        post['etc_payment_method'] = ''

        # ⑤ 绑定表单与 formset（用 post，而不是 request.POST）
        form = DriverDailyReportForm(post, instance=report)
        formset = ReportItemFormSet(post, instance=report)
        formset.queryset = _sorted_items_qs(report)

        # ⑥ （保持你原有的）不变更的 formset 行标记 DELETE（如果你之前有这段就留着）
        for form_item in formset.forms:
            if not form_item.has_changed():
                form_item.fields['DELETE'].initial = True

        # ⑦ 校验通过后写回“安全值”到实例再保存
        if form.is_valid() and formset.is_valid():
            inst = form.save(commit=False)

            # 将安全值直接写入实例（不再走字段选择校验）
            try:
                # 为了保险：如果模型字段确有 choices，就校验一下；否则直接赋值
                model_choices = [c[0] for c in getattr(inst._meta.get_field('etc_payment_method'), 'choices', [])]
                if model_choices and safe_etc not in model_choices:
                    # 如果模型 choices 没有 company_card，就退回第一个合法值
                    safe_etc = model_choices[0]
            except Exception:
                pass
            inst.etc_payment_method = safe_etc

        for form_item in formset.forms:
            if not form_item.has_changed():
                form_item.fields['DELETE'].initial = True

        if form.is_valid() and formset.is_valid():
            inst = form.save(commit=False)

            # ✅ 休憩入力→timedelta
            break_input = request.POST.get("break_time_input", "").strip()
            break_minutes = 0
            try:
                if ":" in break_input:
                    h, m = map(int, break_input.split(":"))
                else:
                    h, m = 0, int(break_input)
                break_minutes = h * 60 + m
            except Exception:
                break_minutes = 0
            inst.休憩時間 = timedelta(minutes=break_minutes)

            inst.calculate_work_times()
            inst.edited_by = request.user

            # ✅ 入金差額：仅入金 - 非貸切現金
            cash_total = sum(
                item.cleaned_data.get('meter_fee') or 0
                for item in formset.forms
                if item.cleaned_data.get('payment_method') == 'cash'
                and not item.cleaned_data.get('DELETE', False)
            )

            # ✅ 新增：貸切現金
            charter_cash_total = sum(
                (item.cleaned_data.get('charter_amount_jpy') or 0)
                for item in formset.forms
                if item.cleaned_data.get('is_charter')
                   and (item.cleaned_data.get('charter_payment_method') in ['jpy_cash', 'jp_cash', 'cash'])
                   and not item.cleaned_data.get('DELETE', False)
            )

            deposit = inst.deposit_amount or 0
            # ✅ 過不足＝入金 − 現金(ながし) − 貸切現金
            inst.deposit_difference = deposit - cash_total - charter_cash_total

            # ✅ ETC 字段：统一保存 + 兜底 + 兼容旧字段名
            cd = form.cleaned_data
            def _to_int(v):
                try:
                    return int(v or 0)
                except (TypeError, ValueError):
                    return 0

            #inst.etc_expected = _to_int(cd.get('etc_expected'))
            inst.etc_collected_cash = _to_int(cd.get('etc_collected_cash') or request.POST.get('etc_collected_cash'))
            inst.etc_collected_app  = _to_int(cd.get('etc_collected_app')  or request.POST.get('etc_collected_app'))

            # `etc_collected` 若为空，用 cash+app 兜底
            etc_collected_val = cd.get('etc_collected')
            inst.etc_collected = _to_int(
                etc_collected_val if etc_collected_val not in [None, '']
                else (inst.etc_collected_cash or 0) + (inst.etc_collected_app or 0)
            )

            # 空車ETC 金額 → etc_uncollected（兼容旧 etc_empty_amount）
            inst.etc_uncollected = _to_int(
                cd.get('etc_uncollected') or request.POST.get('etc_uncollected') or request.POST.get('etc_empty_amount')
            )

            # 收取方式/不足额
            inst.etc_payment_method = cd.get('etc_payment_method') or None

            # 不足额：若表单提供则用表单；否则按只读 etc_expected 回算
            if 'etc_shortage' in form.fields:
                inst.etc_shortage = _to_int(cd.get('etc_shortage'))
            else:
                expected_val = _to_int(getattr(inst, 'etc_expected', 0))
                inst.etc_shortage = max(0, expected_val - _to_int(inst.etc_collected))

            # ✅ 状态/异常标记
            if inst.status in [DriverDailyReport.STATUS_PENDING, DriverDailyReport.STATUS_CANCELLED] and inst.clock_in and inst.clock_out:
                inst.status = DriverDailyReport.STATUS_COMPLETED
            if inst.clock_in and inst.clock_out:
                inst.has_issue = False

            inst.save()
            formset.instance = inst
            formset.save()

            # ✅ 回写预约的出入库时间
            driver_user = inst.driver.user
            if driver_user and inst.clock_in:
                res = Reservation.objects.filter(driver=driver_user, date=inst.date).order_by('start_time').first()
                if res:
                    tz = timezone.get_current_timezone()
                    res.actual_departure = timezone.make_aware(datetime.combine(inst.date, inst.clock_in), tz)
                    if inst.clock_out:
                        ret_date = inst.date
                        if inst.clock_out < inst.clock_in:
                            ret_date += timedelta(days=1)
                        res.actual_return = timezone.make_aware(datetime.combine(ret_date, inst.clock_out), tz)
                    res.save()

            inst.has_issue = inst.items.filter(has_issue=True).exists()
            inst.save(update_fields=["has_issue"])

            messages.success(request, "✅ 保存成功")
            return redirect('dailyreport:driver_dailyreport_month', driver_id=driver_id)
        else:
            messages.error(request, "❌ 保存失败，请检查输入内容")
            # === 表单校验失败时也构造 totals，避免 totals 未定义 ===
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

    else:
        initial = {'status': report.status}
        clock_in = None
        clock_out = None
        driver_user = report.driver.user

        if driver_user:
            res = Reservation.objects.filter(driver=driver_user, date=report.date).order_by('start_time').first()
            if res:
                if res.actual_departure:
                    clock_in = timezone.localtime(res.actual_departure).time()
                    initial['clock_in'] = clock_in
                if res.actual_return:
                    clock_out = timezone.localtime(res.actual_return).time()
                    initial['clock_out'] = clock_out
                if res.vehicle:
                    initial['vehicle'] = res.vehicle
                if not report.vehicle:
                    report.vehicle = res.vehicle
                    report.save()
                if clock_in and clock_out:
                    dt_in = datetime.combine(report.date, clock_in)
                    dt_out = datetime.combine(report.date, clock_out)
                    if dt_out <= dt_in:
                        dt_out += timedelta(days=1)
                    duration = dt_out - dt_in

        if report.休憩時間:
            user_break_min = int(report.休憩時間.total_seconds() / 60) - 20
            user_h = user_break_min // 60
            user_m = user_break_min % 60
            initial['break_time_input'] = f"{user_h}:{str(user_m).zfill(2)}"
        else:
            initial['break_time_input'] = "0:00"

        form = DriverDailyReportForm(instance=report, initial=initial)
        formset = ReportItemFormSet(instance=report)
        formset.queryset = _sorted_items_qs(report)

    # === 以下保持你原有合计/上下文逻辑 ===
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

        print("📦 data_iter 内容如下：")
        for item in data_iter:
            print(item)

        totals_raw = calculate_totals_from_formset(data_iter)

        totals = {f"{k}_raw": v["total"] for k, v in totals_raw.items() if isinstance(v, dict)}
        totals.update({f"{k}_split": v["bonus"] for k, v in totals_raw.items() if isinstance(v, dict)})
        totals["meter_only_total"] = totals_raw.get("meter_only_total", 0)
        meter_only_total = totals.get("meter_only_total", 0)

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
    summary_panel_data = [
        {
            'key': key,
            'label': label,
            'raw': totals.get(f'{key}_raw', 0),
            'split': totals.get(f'{key}_split', 0),
            'meter_only': totals.get(f'{key}_meter_only', 0),
        }
        for key, label in summary_keys
    ]

    cash = totals.get("cash_raw", 0)
    etc = report.etc_collected or 0  # 仅用于显示
    raw_deposit_amt = form.cleaned_data.get("deposit_amount") if form.is_bound else report.deposit_amount
    deposit_amt = int(raw_deposit_amt) if raw_deposit_amt not in [None, ''] else 0
    total_sales = totals.get("meter_raw", 0)
    meter_only_total = totals.get("meter_only_total", 0)
    deposit_diff = getattr(report, "deposit_difference", deposit_amt - cash)

    # ==== 新增：把费率给到前端 ====
    payment_rates = {k: float(v) for k, v in PAYMENT_RATES.items()}

    context = {
        'form': form,
        'formset': formset,
        'totals': totals,
        'driver_id': driver_id,
        'report': report,
        'duration': duration,
        'summary_keys': summary_keys,
        'summary_panel_data': summary_panel_data,
        'break_time_h': user_h,
        'break_time_m': f"{user_m:02}",
        'cash_total': cash,
        'etc_collected': etc,
        'deposit_amt': deposit_amt,
        'total_collected': cash,
        'total_sales': total_sales,
        'meter_only_total': meter_only_total,
        'deposit_diff': deposit_diff,
        'payment_rates': payment_rates,  # ← 新增这一行
    }
    return render(request, 'dailyreport/driver_dailyreport_edit.html', context)


# ✅ 司机查看自己日报
@login_required
def my_dailyreports(request):
    try:
        # ✅ 获取当前登录用户对应的 Driver 实例
        driver = Driver.objects.get(user=request.user)
    except Driver.DoesNotExist:
        return render(request, 'dailyreport/not_found.html', {
            'message': '该用户未绑定司机档案。'
        }, status=404)

    # ✅ 现在使用 Driver 实例来查询日报
    reports = DriverDailyReport.objects.filter(driver=driver).order_by('-date')

    return render(request, 'dailyreport/my_dailyreports.html', {
        'reports': reports,
        'driver': driver,
    })

# ✅ 批量生成账号绑定员工
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
        return redirect('dailyreport:bind_missing_users')

    return render(request, 'dailyreport/bind_missing_users.html', {
        'drivers': drivers_without_user,
    })


#导出每日明细
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
            report.driver.name,
            expected,
            collected,
            diff
        ])

    return response

@user_passes_test(is_dailyreport_admin)
def export_vehicle_csv(request, year, month):
    reports = DriverDailyReport.objects.filter(
        date__year=year,
        date__month=month,
        vehicle__isnull=False
    ).select_related('vehicle')

    # 以车辆为单位进行统计
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

        # --- 出勤计数（替换开始：原先是无条件 +1） ---
        if r.items.filter(start_time__isnull=False, end_time__isnull=False).exists():
            # 如果有实际出勤时间，则计数 +1
            data[key]['出勤日数'] += 1 
        # --- 出勤计数（替换结束） ---

        # 累加各项数据
        data[key]['走行距離'] += mileage
        data[key]['実車距離'] += mileage * 0.75
        data[key]['乗車回数'] += boarding_count
        data[key]['人数'] += boarding_count * 2
        data[key]['水揚金額'] += total_fee
        data[key]['車名'] = car.name
        data[key]['車牌'] = car.license_plate
        data[key]['部門'] = car.department
        data[key]['使用者名'] = car.user_company_name
        data[key]['所有者名'] = car.owner_company_name

    # CSV 响应设置
    response = HttpResponse(content_type='text/csv')
    filename = f"{year}年{month}月_車両運輸実績表.csv"
    response['Content-Disposition'] = f"attachment; filename*=UTF-8''{quote(filename)}"

    # 添加 UTF-8 BOM 防止 Excel 乱码
    response.write(u'\ufeff'.encode('utf8'))
    writer = csv.writer(response)

    # 表头
    headers = [
        '車名', '車牌', '部門', '使用者名', '所有者名',
        '出勤日数', '走行距離', '実車距離', '乗車回数', '人数', '水揚金額'
    ]
    writer.writerow(headers)

    # 数据行
    total_row = [0] * 6  # 出勤〜水揚合计
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

        # 合计累加
        for i in range(5, 11):
            total_row[i - 5] += row[i]

    # ✅ 合计行
    writer.writerow([
        '合計', '', '', '', '',
        total_row[0],  # 出勤日数
        total_row[1],  # 走行距離
        round(total_row[2], 2),  # 実車距離
        total_row[3],  # 乗車回数
        total_row[4],  # 人数
        round(total_row[5], 2),  # 水揚金額
    ])

    return response

@user_passes_test(is_dailyreport_admin)
def dailyreport_add_by_month(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)

    month_str = request.GET.get("month")  # 格式："2025-03"
    if not month_str:
        return redirect("dailyreport:driver_dailyreport_add_selector", driver_id=driver_id)

    try:
        year, month = map(int, month_str.split("-"))
        assert 1 <= month <= 12
    except (ValueError, AssertionError):
        return redirect("dailyreport:driver_dailyreport_add_selector", driver_id=driver_id)

    current_month = f"{year}年{month}月"

    # ✅ 处理表单提交
    if request.method == "POST":
        selected_date_str = request.POST.get("selected_date")
        try:
            selected_date = datetime.strptime(selected_date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            # 日期不合法 → 返回本页
            return render(request, "dailyreport/driver_dailyreport_add.html", {
                "driver": driver,
                "year": year,
                "month": month,
                "current_month": current_month,
                "error": "日付が正しくありません"
            })

        # ✅ 重定向到“该司机该日新增日报”页面
        # ✅ 构造重定向 URL，带上 date 参数
        base_url = reverse("dailyreport:driver_dailyreport_direct_add", args=[driver.id])
        query_string = urlencode({"date": selected_date})
        url = f"{base_url}?{query_string}"
        return redirect(url)

    # 默认 GET 显示页面
    return render(request, "dailyreport/driver_dailyreport_add.html", {
        "driver": driver,
        "year": year,
        "month": month,
        "current_month": current_month,
    })


# ✅ 管理员新增日报给某员工
@user_passes_test(is_dailyreport_admin)
def dailyreport_create_for_driver(request, driver_id):
    driver = get_driver_info(driver_id)
    if not driver:
        return render(request, 'dailyreport/not_found.html', status=404)

    # ✅ 如果带有 GET 参数 ?date=2025-03-29 就自动创建日报并跳转
    if request.method == 'GET' and request.GET.get('date'):
        try:
            date = datetime.strptime(request.GET.get('date'), "%Y-%m-%d").date()
        except ValueError:
            messages.error(request, "无效的日期格式")
            return redirect('dailyreport:driver_dailyreport_month', driver_id=driver.id)

        existing = DriverDailyReport.objects.filter(driver=driver, date=date).first()
        if existing:
            return redirect('dailyreport:driver_dailyreport_edit', driver_id=driver.id, report_id=existing.id)

        # ✅ 创建空日报并跳转到编辑页
        new_report = DriverDailyReport.objects.create(driver=driver, date=date)
        return redirect('dailyreport:driver_dailyreport_edit', driver_id=driver.id, report_id=new_report.id)

    # ✅ POST：提交表单
    if request.method == 'POST':
        report_form = DriverDailyReportForm(request.POST)
        formset = ReportItemFormSet(request.POST)

        if report_form.is_valid() and formset.is_valid():
            dailyreport = report_form.save(commit=False)
            dailyreport.driver = driver
            dailyreport.calculate_work_times()

            cash_total = sum(
                item.cleaned_data.get('meter_fee') or 0
                for item in formset.forms
                if item.cleaned_data.get('payment_method') == 'cash' and not item.cleaned_data.get('DELETE', False)
            )
            deposit = dailyreport.deposit_amount or 0
            dailyreport.deposit_difference = deposit - cash_total

            dailyreport.save()
            formset.instance = dailyreport
            formset.save()

            # === mark_linked_reservation_incomplete call: START ===
            # 仅当管理员勾选了“未完成出入庫”时，将同车且覆盖该日报日期的预约标记为 INCOMPLETE。
            # 非管理员即使传值也不会生效（工具函数内部会检查 is_staff）。
            mark_flag = request.POST.get('mark_incomplete') in ('1', 'on', 'true', 'True')
            mark_linked_reservation_incomplete(dailyreport, request.user, mark_flag)
            # === mark_linked_reservation_incomplete call: END ===

            messages.success(request, '新增日报成功')
            return redirect('dailyreport:driver_dailyreport_month', driver_id=driver.id)
        else:
            print("日报主表错误：", report_form.errors)
            print("明细表错误：", formset.errors)
    else:
        report_form = DriverDailyReportForm()
        formset = ReportItemFormSet()
        # ✅ 这一步关键：用于模板显示司机名等
        report = DriverDailyReport(driver=driver)

    # ✅ 合计逻辑
    if request.method == 'POST' and formset.is_valid():
        data_iter = [f.cleaned_data for f in formset.forms if f.cleaned_data]
        totals = calculate_totals_from_formset(data_iter)
    else:
        data_iter = [f.instance for f in formset.forms]
        totals = calculate_totals_from_instances(data_iter)

    summary_keys = [
        ('meter', 'メーター(水揚)'),
        ('nagashi_cash', '現金(ながし)'),   # ✅ 这是我们要加的合并字段
        ('cash', '現金'),                   # ✅ 若仍想分开显示可保留，否则可删
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
        'report': report,  # ✅ 模板能取到 driver.name 等
        'is_edit': False,
        'summary_keys': summary_keys,
        'totals': totals,
        'nagashi_cash_total': nagashi_cash_total,
    })

@user_passes_test(is_dailyreport_admin)
def driver_dailyreport_add_unassigned(request, driver_id):
    driver = get_driver_info(driver_id)
    if not driver or driver.user:
        messages.warning(request, "未找到未分配账号的员工")
        return redirect("dailyreport:dailyreport_overview")

    driver = get_object_or_404(Driver, id=driver_id, user__isnull=True)

    today = date.today()
    report, created = DriverDailyReport.objects.get_or_create(
        driver=driver,
        date=today,
        defaults={"status": "草稿"}
    )

    # ✅ 加在这里：命令行中会输出 driver 和 report 的主键
    print("🚗 创建日报：", driver.id, report.id, "是否新建：", created)

    if created:
        messages.success(request, f"已为 {driver.name} 创建 {today} 的日报。")
    else:
        messages.info(request, f"{driver.name} 今天的日报已存在，跳转到编辑页面。")

    return redirect("dailyreport:driver_dailyreport_edit", driver_id=driver.id, report_id=report.id)

@user_passes_test(is_dailyreport_admin)
def dailyreport_overview(request):
    today = now().date()
    month_str = request.GET.get('month') or today.strftime('%Y-%m')
    try:
        month = datetime.strptime(month_str, '%Y-%m')
    except ValueError:
        month = today.replace(day=1)
        month_str = month.strftime('%Y-%m')

    month_label = f"{month.year}年{month.month:02d}月"
    prev_month = (month - relativedelta(months=1)).strftime('%Y-%m')
    next_month = (month + relativedelta(months=1)).strftime('%Y-%m')
    keyword = (request.GET.get('keyword') or '').strip()

    # 仅取需要的字段，预先把公司/营业所名字拍扁为字符串；不再碰已删除的 driver.company 列
    raw = (
        get_active_drivers(month, keyword)
        .select_related('workplace__company')
        .values('id', 'driver_code', 'name', 'kana',
                'workplace__name', 'workplace__company__name')
        .order_by('driver_code', 'id')     # ← 加这一行，强制不用默认ordering
    )

    print("drivers SQL =>", str(raw.query))

    drivers = [
        NS(id=r['id'],
           driver_code=r['driver_code'],
           name=r['name'],
           kana=r['kana'],
           company=NS(name=r['workplace__company__name']),
           workplace=NS(name=r['workplace__name']))
        for r in raw
    ]
    driver_ids = [r['id'] for r in raw]

    # 仅当月且仅这些司机
    reports = DriverDailyReport.objects.filter(
        date__year=month.year, date__month=month.month,
        driver_id__in=driver_ids
    )

    # 明细（同样只算这些司机的）
    items_norm = (
        DriverDailyReportItem.objects.filter(report__in=reports)
        .annotate(pm=Lower(Trim('payment_method')),
                  cpm=Lower(Trim('charter_payment_method')))
    )

    from collections import defaultdict
    totals = defaultdict(Decimal)
    counts = defaultdict(int)

    # メータのみ（非貸切）
    totals['meter_only_total'] = items_norm.filter(is_charter=False)\
        .aggregate(x=Sum('meter_fee'))['x'] or Decimal('0')

    # 各方式（现金不叠加貸切）
    MAP = {
        'cash':   (['cash'],                 []),
        'credit': (['credit','credit_card'], ['credit','credit_card']),
        'uber':   (['uber'],                 ['uber']),
        'didi':   (['didi'],                 ['didi']),
        'kyokushin': (['kyokushin'],        ['kyokushin']),
        'omron':     (['omron'],            ['omron']),
        'kyotoshi':  (['kyotoshi'],         ['kyotoshi']),
        'qr':        (['qr','scanpay'],     ['qr','scanpay']),
    }
    for key, (nlist, clist) in MAP.items():
        n = items_norm.filter(is_charter=False, pm__in=nlist)\
              .aggregate(x=Sum('meter_fee'))['x'] or Decimal('0')
        c = (items_norm.filter(is_charter=True, cpm__in=clist)
                    .aggregate(x=Sum('charter_amount_jpy'))['x'] or Decimal('0')) if clist else Decimal('0')
        totals[f'total_{key}'] = n + c
        counts[key] = (items_norm.filter(is_charter=False, pm__in=nlist).count() +
                       (items_norm.filter(is_charter=True, cpm__in=clist).count() if clist else 0))

    totals['charter_cash_total'] = items_norm.filter(is_charter=True, cpm__in=['jpy_cash'])\
        .aggregate(x=Sum('charter_amount_jpy'))['x'] or Decimal('0')
    totals['charter_uncollected_total'] = items_norm.filter(
        is_charter=True, cpm__in=['to_company','invoice','uncollected','未収','請求']
    ).aggregate(x=Sum('charter_amount_jpy'))['x'] or Decimal('0')

    totals['total_meter'] = (totals['meter_only_total'] +
                             totals['charter_cash_total'] +
                             totals['charter_uncollected_total'])

    rates = {'meter':Decimal('0.9091'),'cash':Decimal('0'),
             'uber':Decimal('0.05'),'didi':Decimal('0.05'),
             'credit':Decimal('0.05'),'kyokushin':Decimal('0.05'),
             'omron':Decimal('0.05'),'kyotoshi':Decimal('0.05'),'qr':Decimal('0.05')}
    split = lambda k: ((totals.get(f'total_{k}') or 0) * rates[k]).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    totals_all = {k:{'total': totals.get(f'total_{k}', Decimal('0')), 'bonus': split(k)} for k in rates}
    totals_all['meter_only_total'] = totals['meter_only_total']

    totals['meter_pre_tax'] = (totals['total_meter'] / Decimal('1.1')).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    etc_shortage_total = reports.aggregate(total=Sum('etc_shortage'))['total'] or 0

    # 每司机“売上合計”
    per_driver = DriverDailyReportItem.objects.filter(report__in=reports)\
        .values('report__driver').annotate(
            meter_only=Sum('meter_fee', filter=Q(is_charter=False)),
            charter_cash=Sum('charter_amount_jpy', filter=Q(is_charter=True, charter_payment_method__in=['jpy_cash'])),
            charter_uncol=Sum('charter_amount_jpy', filter=Q(is_charter=True, charter_payment_method__in=['to_company','invoice','uncollected','未収','請求'])),
        )
    fee_map = {r['report__driver']: (r['meter_only'] or 0)+(r['charter_cash'] or 0)+(r['charter_uncol'] or 0)
               for r in per_driver}

    sort = request.GET.get('sort', 'amount_desc')
    def code_key(d):
        code = (getattr(d, 'driver_code', '') or '').strip()
        return (0, int(code)) if code.isdigit() else (1, code)

    if sort == 'code_asc':
        ordered = sorted(drivers, key=code_key)
    elif sort == 'code_desc':
        ordered = sorted(drivers, key=code_key, reverse=True)
    elif sort == 'amount_asc':
        ordered = sorted(drivers, key=lambda d: (fee_map.get(d.id, Decimal('0')), code_key(d)))
    else:
        ordered = sorted(drivers, key=lambda d: (fee_map.get(d.id, Decimal('0')), code_key(d)), reverse=True)

    rows = []
    for d in ordered:
        total = fee_map.get(d.id, Decimal('0'))
        has_issue = reports.filter(driver_id=d.id, has_issue=True).exists()  # ← 用 driver_id
        rows.append({'driver': d, 'total_fee': total,
                     'note': "⚠️ 異常あり" if has_issue else ("（未報告）" if d.id not in fee_map else ""),
                     'month_str': month_str})

    page_obj = Paginator(rows, 10).get_page(request.GET.get('page'))

    summary_keys = [
        ('meter','メーター(水揚)'),('cash','現金'),('uber','Uber'),
        ('didi','Didi'),('credit','クレジットカード'),
        ('kyokushin','京交信'),('omron','オムロン'),
        ('kyotoshi','京都市他'),('qr','扫码'),
    ]

    return render(request, 'dailyreport/dailyreport_overview.html', {
        'totals': totals, 'totals_all': totals_all, 'etc_shortage_total': etc_shortage_total,
        'drivers': drivers, 'page_obj': page_obj, 'counts': counts,
        'current_sort': sort, 'keyword': keyword,
        'month_str': month_str, 'current_year': month.year, 'current_month': month.month,
        'summary_keys': summary_keys, 'month_label': month_label,
        'prev_month': prev_month, 'next_month': next_month, 'sort': sort,
    })