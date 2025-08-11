import csv, os, sys
import logging
logger = logging.getLogger(__name__)
from datetime import datetime, date, timedelta
from tempfile import NamedTemporaryFile

from django.contrib.auth.decorators import user_passes_test, login_required
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.shortcuts import render, get_object_or_404, redirect, HttpResponse
from django.utils.timezone import now
from django.utils import timezone
from django.db.models import Sum, Case, When, F, DecimalField, Q, Count
from django.http import HttpResponse, FileResponse
from django.utils.encoding import escape_uri_path
from django.urls import reverse
from django.utils.http import urlencode
from dateutil.relativedelta import relativedelta

from django.db.models.functions import Lower, Trim

from dailyreport.models import DriverDailyReport, DriverDailyReportItem
from .forms import DriverDailyReportForm, DriverDailyReportItemForm, ReportItemFormSet
from .services.calculations import calculate_deposit_difference  # ✅ 导入新函数

from staffbook.services import get_driver_info
from staffbook.utils.permissions import is_dailyreport_admin, get_active_drivers
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

# ✅ 新增日报
@user_passes_test(is_dailyreport_admin)
def dailyreport_create(request):
    print("🧪 formset is valid?", formset.is_valid())
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
        extra=1,
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
    from collections import defaultdict
    from decimal import Decimal, ROUND_HALF_UP
    from tempfile import NamedTemporaryFile
    from urllib.parse import quote

    from django.db.models import Sum
    from django.db.models.functions import Lower, Trim
    from django.http import FileResponse
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill, Border, Side

    TAX_RATE = Decimal("0.10")
    FEE_RATE = Decimal("0.05")  # 平台手数料
    CASH_METHODS = ["cash", "uber_cash", "didi_cash", "go_cash"]  # 非貸切の現金系
    CHARTER_CASH_KEYS = ["jpy_cash", "jp_cash", "cash"]           # 貸切現金（兼容三写法）
    CHARTER_UNCOLLECTED_KEYS = ["to_company", "invoice", "uncollected", "未収", "請求"]

    reports = (
        DriverDailyReport.objects.filter(date__year=year, date__month=month)
        .select_related("driver")
        .prefetch_related("items")
        .order_by("date", "driver__name")
    )

    by_date = defaultdict(list)
    for r in reports:
        by_date[r.date].append(r)

    wb = Workbook()
    wb.remove(wb.active)

    center = Alignment(horizontal="center", vertical="center")
    right = Alignment(horizontal="right", vertical="center")
    bold = Font(bold=True)
    red_bold = Font(bold=True, color="CC0000")
    gray = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")
    yellow = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
    blue = PatternFill(start_color="DAEEF3", end_color="DAEEF3", fill_type="solid")
    thin = Side(style="thin")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    def compute_row(r):
        qs = r.items.all().annotate(
            pm=Lower(Trim("payment_method")),
            cpm=Lower(Trim("charter_payment_method")),
        )

        # メータのみ（非貸切）
        meter_only = qs.filter(is_charter=False).aggregate(s=Sum("meter_fee"))["s"] or 0

        # ながし現金（非貸切 現金系のみ）
        nagashi_cash = qs.filter(is_charter=False, pm__in=CASH_METHODS)\
                         .aggregate(s=Sum("meter_fee"))["s"] or 0

        # 貸切現金 / 貸切未収
        charter_cash = qs.filter(is_charter=True, cpm__in=CHARTER_CASH_KEYS)\
                         .aggregate(s=Sum("charter_amount_jpy"))["s"] or 0
        charter_uncol = qs.filter(is_charter=True, cpm__in=CHARTER_UNCOLLECTED_KEYS)\
                          .aggregate(s=Sum("charter_amount_jpy"))["s"] or 0

        # 平台売上（非貸切 + 貸切）
        def amt_normal(keys):
            return qs.filter(is_charter=False, pm__in=keys).aggregate(s=Sum("meter_fee"))["s"] or 0
        def amt_charter(keys):
            return qs.filter(is_charter=True, cpm__in=keys).aggregate(s=Sum("charter_amount_jpy"))["s"] or 0

        kyokushin = amt_normal(["kyokushin"]) + amt_charter(["kyokushin"])
        omron     = amt_normal(["omron"])     + amt_charter(["omron"])
        kyotoshi  = amt_normal(["kyotoshi"])  + amt_charter(["kyotoshi"])
        uber      = amt_normal(["uber"])      + amt_charter(["uber"])
        credit    = amt_normal(["credit", "credit_card"]) + amt_charter(["credit", "credit_card"])
        paypay    = amt_normal(["qr", "scanpay"])
        didi      = amt_normal(["didi"])      + amt_charter(["didi"])

        def fee(x):
            return int((Decimal(x) * FEE_RATE).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) if x else 0
        uber_fee, credit_fee, paypay_fee, didi_fee = map(fee, [uber, credit, paypay, didi])

        # ETC 两列
        etc_collected_val = r.etc_collected
        etc_ride_total = int(etc_collected_val if etc_collected_val not in [None, ""]
                             else (r.etc_collected_cash or 0) + (r.etc_collected_app or 0))
        etc_empty_total = int(getattr(r, "etc_uncollected", 0) or 0)

        # 未収合計（平台合计之和）
        uncol_total = int(uber + didi + credit + kyokushin + omron + kyotoshi + paypay)

        # ✅ 水揚合計＝メータのみ＋貸切現金＋貸切未収（＝売上合計）
        water_total = int(meter_only) + int(charter_cash) + int(charter_uncol)

        # 税抜/消費税
        tax_ex = int((Decimal(water_total) / Decimal("1.1")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        tax = water_total - tax_ex

        # ✅ 過不足＝入金 − ながし現金 − 貸切現金
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

            "kyokushin": int(kyokushin),
            "omron": int(omron),
            "kyotoshi": int(kyotoshi),
            "uber": int(uber), "uber_fee": uber_fee,
            "credit": int(credit), "credit_fee": credit_fee,
            "paypay": int(paypay), "paypay_fee": paypay_fee,
            "didi": int(didi), "didi_fee": didi_fee,

            "uncol_total": int(uncol_total),
            "fee_total": int(uber_fee + credit_fee + paypay_fee + didi_fee),
            "water_total": int(water_total),
            "tax_ex": tax_ex,
            "tax": tax,
            "gas_l": float(r.gas_volume or 0),
            "km": float(r.mileage or 0),

            "deposit_diff": int(deposit_diff),
        }

    for d, day_reports in sorted(by_date.items()):
        # 同一天内按社員番号升序
        def _code_key(rep):
            code = getattr(rep.driver, "driver_code", "") if rep.driver else ""
            return (int(code) if str(code).isdigit() else 10**9, str(code))
        day_reports = sorted(day_reports, key=_code_key)

        ws = wb.create_sheet(title=d.strftime("%Y-%m-%d"))

        # —— 双表头（社員番号在最左；最后一列为 過不足）——
        row1 = [
            "社員番号", "従業員", "出勤時刻", "退勤時刻",
            "1.ながし現金", "2.貸切現金",
            "3.ETC", "", "貸切未収",
            "4.京交信売上", "5.オムロン売上", "6.京都市他売上",
            "7.Uber売上", "", "8.クレジット売上", "", "9.PayPay売上", "", "10.DiDi売上", "",
            "未収合計", "手数料合計",
            "水揚合計", "税抜収入", "消費税",
            "11.ガソリン(L)", "12.距離(KM)",
            "過不足"
        ]
        row2 = [
            "", "", "", "",
            "", "",
            "乗車合計", "空車ETC金額", "",
            "", "", "",
            "", "手数料", "", "手数料", "", "手数料", "", "手数料",
            "", "",
            "", "", "",
            "", "",  # Z, AA
            ""       # AB
        ]
        ws.append(row1); ws.append(row2)

        merges = [
            ("A1","A2"), ("B1","B2"), ("C1","C2"), ("D1","D2"),
            ("E1","E2"), ("F1","F2"),
            ("I1","I2"), ("J1","J2"), ("K1","K2"), ("L1","L2"),
            ("U1","U2"), ("V1","U2".replace("U2","V2")),  # V1~V2
            ("W1","W2"), ("X1","X2"), ("Y1","Y2"),
            ("Z1","Z2"), ("AA1","AA2"),
            ("AB1","AB2"),
        ]
        for a, b in merges:
            ws.merge_cells(f"{a}:{b}")

        for row in ws.iter_rows(min_row=1, max_row=2):
            for c in row:
                c.alignment = center; c.font = bold; c.fill = gray; c.border = border
        for pos in ["N2", "P2", "R2", "T2"]:
            ws[pos].font = red_bold; ws[pos].alignment = center

        totals = defaultdict(Decimal)
        for r in day_reports:
            data = compute_row(r)
            ws.append([
                data["driver_code"], data["driver"], data["clock_in"], data["clock_out"],
                data["nagashi_cash"], data["charter_cash"],
                data["etc_ride_total"], data["etc_empty_total"],
                data["charter_uncol"],
                data["kyokushin"], data["omron"], data["kyotoshi"],
                data["uber"], data["uber_fee"],
                data["credit"], data["credit_fee"],
                data["paypay"], data["paypay_fee"],
                data["didi"], data["didi_fee"],
                data["uncol_total"], data["fee_total"],
                data["water_total"], data["tax_ex"], data["tax"],
                data["gas_l"], data["km"],
                data["deposit_diff"],
            ])
            for k, v in data.items():
                if isinstance(v, (int, float, Decimal)):
                    totals[k] += Decimal(str(v))

        ws.append([
            "合計", "", "", "",
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
        ])
        last = ws.max_row
        for c in ws[last]:
            c.font = bold; c.fill = yellow; c.border = border
            if isinstance(c.value, (int, float)): c.alignment = right

        # 着色：ETC列(G/H)、水揚/税(W/X/Y)
        for col in ws.iter_cols(min_col=7, max_col=8, min_row=3, max_row=last-1):
            for c in col: c.fill = blue
        for col in ws.iter_cols(min_col=23, max_col=25, min_row=3, max_row=last-1):
            for c in col: c.fill = yellow

        # 数字右对齐 + 边框
        for row in ws.iter_rows(min_row=3, max_row=last):
            for i, c in enumerate(row, start=1):
                c.border = border
                if i >= 5: c.alignment = right

        widths = {
            "A":10, "B":12, "C":9, "D":9, "E":12, "F":12,
            "G":12, "H":14, "I":12, "J":12, "K":12, "L":12,
            "M":12, "N":10, "O":14, "P":10, "Q":12, "R":10, "S":12, "T":10,
            "U":12, "V":12, "W":12, "X":12, "Y":12, "Z":12, "AA":12, "AB":12,
        }
        for col, w in widths.items():
            ws.column_dimensions[col].width = w

    filename = f"{year}年{month}月_全員毎日集計.xlsx"
    tmp = NamedTemporaryFile(); wb.save(tmp.name); tmp.seek(0)
    return FileResponse(tmp, as_attachment=True, filename=quote(filename),
                        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


#导出全员每月汇总（每个司机一个 Sheet（表单））
@user_passes_test(is_dailyreport_admin)
def export_monthly_summary_excel(request, year, month):
    reports = DriverDailyReport.objects.filter(
        date__year=year, date__month=month
    ).select_related('driver').prefetch_related('items')

    driver_summary = defaultdict(lambda: defaultdict(Decimal))
    driver_info = {}

    for report in reports:
        driver = report.driver
        if not driver:
            continue

        driver_code = driver.driver_code or ''
        driver_name = driver.name or ''
        driver_info[driver_code] = driver_name

        for item in report.items.all():
            if (
                item.payment_method and
                item.meter_fee and item.meter_fee > 0 and
                (not item.note or 'キャンセル' not in item.note)
            ):
                driver_summary[driver_code][item.payment_method] += item.meter_fee

        etc_expected = Decimal(report.etc_expected or 0)
        etc_collected = Decimal(report.etc_collected or 0)
        etc_deficit = max(Decimal("0"), etc_collected - etc_expected)

        driver_summary[driver_code]['etc_expected'] += etc_expected
        driver_summary[driver_code]['etc_collected'] += etc_collected
        driver_summary[driver_code]['etc_deficit'] += etc_deficit
        driver_summary[driver_code]['deposit_diff'] += report.deposit_difference or 0
        driver_summary[driver_code]['mileage'] += Decimal(report.mileage or 0)
        driver_summary[driver_code]['gas'] += Decimal(report.gas_volume or 0)

    wb = Workbook()
    ws = wb.active

    last_day = monthrange(year, month)[1]
    ws.title = f"{year}年{month}月（{month}月1日~{month}月{last_day}日）"

    headers = [
        '社員番号', '司机',
        '現金', 'Uber', 'Didi', 'クレジットカード', '扫码支付',
        '京交信', 'オムロン', '京都市他',
        'ETC应收', 'ETC实收', 'ETC差額', 'ETC不足額',
        '過不足額', '走行距離(KM)', '給油量(L)'
    ]
    ws.append(headers)

    total_row = defaultdict(Decimal)

    for driver_code in sorted(driver_summary.keys()):
        data = driver_summary[driver_code]
        etc_expected = data.get('etc_expected', Decimal('0'))
        etc_collected = data.get('etc_collected', Decimal('0'))
        etc_diff = etc_expected - etc_collected

        row = [
            driver_code,
            driver_info.get(driver_code, ''),
            data.get('cash', Decimal('0')),
            data.get('uber', Decimal('0')),
            data.get('didi', Decimal('0')),
            data.get('credit', Decimal('0')),
            data.get('qr', Decimal('0')),
            data.get('kyokushin', Decimal('0')),
            data.get('omron', Decimal('0')),
            data.get('kyotoshi', Decimal('0')),
            etc_expected,
            etc_collected,
            etc_diff,
            data.get('etc_deficit', Decimal('0')),
            data.get('deposit_diff', Decimal('0')),
            data.get('mileage', Decimal('0')),
            data.get('gas', Decimal('0')),
        ]
        ws.append(row)

        # 加入合计
        for i, key in enumerate([
            'cash', 'uber', 'didi', 'credit', 'qr',
            'kyokushin', 'omron', 'kyotoshi',
            'etc_expected', 'etc_collected', 'etc_diff', 'etc_deficit',
            'deposit_diff', 'mileage', 'gas'
        ], start=2):
            value = row[i]
            total_row[key] += value if isinstance(value, Decimal) else Decimal(str(value))

    # 添加合计行
    ws.append([
        '合計', '',
        total_row['cash'], total_row['uber'], total_row['didi'], total_row['credit'], total_row['qr'],
        total_row['kyokushin'], total_row['omron'], total_row['kyotoshi'],
        total_row['etc_expected'], total_row['etc_collected'],
        total_row['etc_expected'] - total_row['etc_collected'],
        total_row['etc_deficit'],
        total_row['deposit_diff'], total_row['mileage'], total_row['gas']
    ])

    # 样式美化：自动列宽
    for col in ws.columns:
        max_len = max(len(str(cell.value)) if cell.value else 0 for cell in col)
        ws.column_dimensions[get_column_letter(col[0].column)].width = max_len + 2

    # 样式：文字居左，其余居中，合计加粗背景
    align_center = Alignment(horizontal="center", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")
    bold_font = Font(bold=True)
    fill = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")
    last_row = ws.max_row

    for row in ws.iter_rows(min_row=2, max_row=last_row):
        for idx, cell in enumerate(row):
            if idx == 0 or idx == 1:  # 司机代码/姓名
                cell.alignment = align_left
            else:
                cell.alignment = align_center
            if cell.row == last_row:
                cell.font = bold_font
                cell.fill = fill

    # 导出文件
    from tempfile import NamedTemporaryFile
    tmp = NamedTemporaryFile()
    wb.save(tmp.name)
    tmp.seek(0)

    filename = f"{year}年{month}月_全员月报汇总.xlsx"
    response = FileResponse(tmp, as_attachment=True, filename=quote(filename))
    response['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    return response


# ✅ 功能：查看某位司机的月度日报合计
@user_passes_test(is_dailyreport_admin)
def driver_dailyreport_month(request, driver_id):
    from datetime import datetime

    driver = get_object_or_404(Driver, id=driver_id)
    month_str = request.GET.get("month")
    if not month_str:
        month = datetime.today().date().replace(day=1)
    else:
        month = datetime.strptime(month_str, "%Y-%m").date()

    reports_qs = DriverDailyReport.objects.filter(
        driver=driver,
        date__year=month.year,
        date__month=month.month
    ).order_by('-date')

    print("✅ 已进入视图，报告数:", reports_qs.count())

    report_list = []

    for report in reports_qs:
        items = report.items.all()

        print(f"[DEBUG] items count: {items.count()}")
        for item in items:
            print(f"[ITEM] id={item.id}, payment_method=《{item.payment_method}》, note=《{item.note}》")

        totals = calculate_totals_from_instances(items)

        # 预览页口径与编辑页保持一致：
        # 合計 = 売上合計 = メータのみ + 貸切現金 + 貸切未収
        report.total_all = totals.get("sales_total", Decimal("0"))

        # メータのみ（不含貸切）
        report.meter_only_total = totals.get("meter_only_total", Decimal("0"))

        # 可保留调试，确认数值
        print(f"[TOTAL] sales_total={report.total_all}, meter_only_total={report.meter_only_total}")

        report_list.append(report)

    return render(request, 'dailyreport/driver_dailyreport_month.html', {
        'driver': driver,
        'month': month,
        'reports': report_list,  # ✅ 使用构建好的新列表
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


# ✅ 管理员新增日报给某员工
@user_passes_test(is_dailyreport_admin)
def dailyreport_create_for_driver(request, driver_id):
    driver = get_driver_info(driver_id)
    if not driver:
        return render(request, 'dailyreport/not_found.html', status=404)

    # ✅ 特殊 GET 请求：根据 ?date=YYYY-MM-DD 自动创建日报并跳转
    if request.method == 'GET' and request.GET.get('date'):
        try:
            date = datetime.strptime(request.GET.get('date'), "%Y-%m-%d").date()
        except ValueError:
            messages.error(request, "无效的日期格式")
            return redirect('dailyreport:driver_dailyreport_month', driver_id=driver.id)

        # 如果日报已存在，则直接跳转
        existing = DriverDailyReport.objects.filter(driver=driver, date=date).first()
        if existing:
            return redirect('dailyreport:driver_dailyreport_edit', driver_id=driver.id, report_id=existing.id)

        # 否则创建空日报并跳转编辑页
        new_report = DriverDailyReport.objects.create(driver=driver, date=date)
        return redirect('dailyreport:driver_dailyreport_edit', driver_id=driver.id, report_id=new_report.id)

    # ✅ 表单提交处理逻辑
    if request.method == 'POST':
        report_form = DriverDailyReportForm(request.POST)
        formset = ReportItemFormSet(request.POST)

        if report_form.is_valid() and formset.is_valid():
            dailyreport = report_form.save(commit=False)
            dailyreport.driver = driver

            # 自动计算时间字段
            dailyreport.calculate_work_times()

            # 计算现现金合计差额
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

            messages.success(request, '新增日报成功')
            return redirect('dailyreport:driver_dailyreport_month', driver_id=driver.id)
        else:
            print("日报主表错误：", report_form.errors)
            print("明细表错误：", formset.errors)
    else:
        report_form = DriverDailyReportForm()
        formset = ReportItemFormSet()

    # ✅ 合计统计（POST 用 cleaned_data，GET 用 instance）
    if request.method == 'POST' and formset.is_valid():
        data_iter = [f.cleaned_data for f in formset.forms if f.cleaned_data]
        totals = calculate_totals_from_formset(data_iter)
    else:
        data_iter = [f.instance for f in formset.forms]
        totals = calculate_totals_from_instances(data_iter)
        print("🔍 totals =", totals)

    # ✅ 用于模板合计栏
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
        "nagashi_cash_total": nagashi_cash_total,
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
        form = DriverDailyReportForm(request.POST, instance=report)
        formset = ReportItemFormSet(request.POST, instance=report)

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

    # === 以下保持你原有合计/上下文逻辑 ===
    data_iter = []
    for f in formset.forms:
        if f.is_bound and f.is_valid():
            cleaned = f.cleaned_data
            if cleaned.get("meter_fee") and not cleaned.get("DELETE", False):
                data_iter.append({
                    'meter_fee': cleaned.get('meter_fee'),
                    'payment_method': cleaned.get('payment_method'),
                    'note': cleaned.get('note', ''),
                    'DELETE': False,
                })
        elif f.instance and not getattr(f.instance, 'DELETE', False):
            data_iter.append({
                'meter_fee': getattr(f.instance, 'meter_fee', 0),
                'payment_method': getattr(f.instance, 'payment_method', ''),
                'note': getattr(f.instance, 'note', ''),
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
    }
    return render(request, 'dailyreport/driver_dailyreport_edit.html', context)

@user_passes_test(is_dailyreport_admin)
def driver_dailyreport_add_unassigned(request):
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
        return redirect('sdailyreport:bind_missing_users')

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

        data[key]['出勤日数'] += 1
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
def driver_dailyreport_add_unassigned(request):
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


# ✅ 司机查看自己日报
@login_required
def my_dailyreports(request):
    reports = DriverDailyReport.objects.filter(driver=request.user).order_by('-date')
    return render(request, 'dailyreport/my_dailyreports.html', {'reports': reports})

@user_passes_test(is_dailyreport_admin)
def dailyreport_overview(request):
    # 1. 基本参数
    today = now().date()
    keyword = request.GET.get('keyword', '').strip()
    month_str = request.GET.get('month', '')

    # 2. 解析月份
    try:
        month = datetime.strptime(month_str, "%Y-%m")
    except ValueError:
        month = today.replace(day=1)
        month_str = month.strftime('%Y-%m')

    # ✅ 供模板导航
    month_label = f"{month.year}年{month.month:02d}月"
    prev_month = (month - relativedelta(months=1)).strftime('%Y-%m')
    next_month = (month + relativedelta(months=1)).strftime('%Y-%m')

    # 3. 导出按钮
    export_year = month.year
    export_month = month.month

    # 4. 所有当月日报（含离职者），及用于展示/计算的在职司机
    reports_all = DriverDailyReport.objects.filter(
        date__year=month.year,
        date__month=month.month,
    )
    drivers = get_active_drivers(month, keyword)
    reports = reports_all.filter(driver__in=drivers)

    # 5. 取本月所有明细并归一化字段
    items_all = DriverDailyReportItem.objects.filter(report__in=reports_all)
    items_norm = items_all.annotate(
        pm=Lower(Trim('payment_method')),
        cpm=Lower(Trim('charter_payment_method')),
    )

    totals = defaultdict(Decimal)
    counts = defaultdict(int)

    # 6. メーター(水揚) —— 仅统计非貸切的 meter_fee
    meter_sum_non_charter = items_norm.filter(is_charter=False)\
        .aggregate(x=Sum('meter_fee'))['x'] or Decimal('0')
    totals['total_meter'] = meter_sum_non_charter
    totals['meter_only_total'] = meter_sum_non_charter  # 给模板的“メータのみ”

    # 7. 各支付方式口径
    #    规则：
    #    - 普通部分：meter_fee 且 is_charter=False
    #    - 貸切部分：charter_amount_jpy 且 is_charter=True（仅在需要将貸切计入该方式时）
    ALIASES = {
        'cash':      {'normal': ['cash'],                 'charter': ['jpy_cash']},  # 注意：这里不会叠加 charter 到 cash
        'credit':    {'normal': ['credit', 'credit_card'],'charter': ['credit','credit_card']},
        'uber':      {'normal': ['uber'],                 'charter': ['uber']},
        'didi':      {'normal': ['didi'],                 'charter': ['didi']},
        'kyokushin': {'normal': ['kyokushin'],            'charter': ['kyokushin']},
        'omron':     {'normal': ['omron'],                'charter': ['omron']},
        'kyotoshi':  {'normal': ['kyotoshi'],             'charter': ['kyotoshi']},
        'qr':        {'normal': ['qr', 'scanpay'],        'charter': ['qr', 'scanpay']},
    }
    # 现金卡片不叠加貸切
    EXCLUDE_CHARTER_IN_METHODS = {'cash'}

    for key, alias in ALIASES.items():
        # 普通：排除貸切
        normal_qs = items_norm.filter(is_charter=False, pm__in=alias['normal'])
        normal_amt = normal_qs.aggregate(x=Sum('meter_fee'))['x'] or Decimal('0')
        normal_cnt = normal_qs.count()

        # 貸切：需要时才叠加（除 cash 外）
        charter_amt = Decimal('0')
        charter_cnt = 0
        if key not in EXCLUDE_CHARTER_IN_METHODS:
            charter_qs = items_norm.filter(is_charter=True, cpm__in=alias['charter'])
            charter_amt = charter_qs.aggregate(x=Sum('charter_amount_jpy'))['x'] or Decimal('0')
            charter_cnt = charter_qs.count()

        totals[f'total_{key}'] = normal_amt + charter_amt
        counts[key] = normal_cnt + charter_cnt

    # 8. 貸切現金 / 貸切未収（独立卡片）
    #    ✅ 修正拼写：'jpy_cash'（之前写成了 'jp_cash' 导致 0）
    totals['charter_cash_total'] = items_norm.filter(
        is_charter=True, cpm__in=['jpy_cash']
    ).aggregate(x=Sum('charter_amount_jpy'))['x'] or Decimal('0')

    totals['charter_uncollected_total'] = items_norm.filter(
        is_charter=True, cpm__in=['to_company', 'invoice', 'uncollected', '未収', '請求']
    ).aggregate(x=Sum('charter_amount_jpy'))['x'] or Decimal('0')

    # ✅ 水揚合計(= 売上合計) を “total_meter” に反映
    totals['total_meter'] = (
        (totals.get('meter_only_total') or Decimal('0')) +
        (totals.get('charter_cash_total') or Decimal('0')) +
        (totals.get('charter_uncollected_total') or Decimal('0'))
    )

    # 9. 分成费率（ETC 不参与）
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

    totals_all = {
        k: {"total": totals.get(f"total_{k}", Decimal("0")), "bonus": split(k)}
        for k in rates
    }
    totals_all["meter_only_total"] = totals.get("meter_only_total", Decimal("0"))

    # 10. 税前合计（基于非貸切 meter）
    gross = totals.get('total_meter') or Decimal('0')
    totals['meter_pre_tax'] = (gross / Decimal('1.1')).quantize(Decimal('1'), rounding=ROUND_HALF_UP)

    # 11. ETC 不足合计（来自日报主表）
    etc_shortage_total = reports.aggregate(total=Sum('etc_shortage'))['total'] or 0

    # 12. 每位司机当月「売上合計」
    #     口径：メータのみ(非貸切) + 貸切現金 + 貸切未収
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

    # 売上合計 = メータのみ + 貸切現金 + 貸切未収
    fee_map = {
        r['report__driver']: (r['meter_only'] or 0)
                            + (r['charter_cash'] or 0)
                            + (r['charter_uncol'] or 0)
        for r in per_driver
    }

    # ✅ 读取排序参数（默认金额降序）
    sort = request.GET.get('sort', 'amount_desc')
    reverse = (sort != 'amount_asc')   # desc 为 True, asc 为 False

    # ✅ 用 ordered_drivers，而不是 drivers
    ordered_drivers = sorted(
        list(drivers),  # 先实化 QuerySet
        key=lambda d: (
            fee_map.get(d.id, Decimal('0')),                      # 金额
            (getattr(d, 'driver_code', '') or d.name or '')       # 稳定次序辅助
        ),
        reverse=reverse
    )

    driver_data = []
    for d in ordered_drivers:  # ← 这里改成 ordered_drivers
        total = fee_map.get(d.id, Decimal("0"))
        has_any = d.id in fee_map
        has_issue = reports.filter(driver=d, has_issue=True).exists()
        note = "⚠️ 異常あり" if has_issue else ("（未報告）" if not has_any else "")
        driver_data.append({
            'driver': d,
            'total_fee': total,   # 模板“合計メータ料金”列显示用
            'note': note,
            'month_str': month_str,
        })

    # 13. 分页
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
        'current_sort': sort,   # ✅ 让模板里的隐藏字段/切换按钮/分页保留排序
        'keyword': keyword,     # ✅ 搜索框回填与链接需要

        'month_str': month_str,
        'current_year': export_year,
        'current_month': export_month,
        'summary_keys': summary_keys,
        'month_label': month_label,
        'prev_month': prev_month,
        'next_month': next_month,
        'counts': counts,
    })
