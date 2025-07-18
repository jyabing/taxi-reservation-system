import csv
from datetime import datetime, date, timedelta


from django.contrib.auth.decorators import user_passes_test, login_required
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.shortcuts import render, get_object_or_404, redirect, HttpResponse
from django.utils.timezone import now
from django.utils import timezone
from django.db.models import Sum, Case, When, F, DecimalField, Q
from django.http import HttpResponse
from django.utils.encoding import escape_uri_path

from .models import DriverDailyReport, DriverDailyReportItem
from .forms import DriverDailyReportForm, DriverDailyReportItemForm, ReportItemFormSet

from staffbook.services import get_driver_info
from staffbook.utils import is_dailyreport_admin, get_active_drivers
from staffbook.models import Driver

from vehicles.models import Reservation
from urllib.parse import quote
from carinfo.models import Car  # 🚗 请根据你项目中车辆模型名称修改
from collections import defaultdict

from .utils import (
    calculate_totals_from_formset,
    calculate_totals_from_queryset,
    PAYMENT_KEYWORDS,
)

from decimal import Decimal, ROUND_HALF_UP
from calendar import monthrange, month_name
from urllib.parse import quote



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

# ✅ 编辑日报
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
            print("🧪 cleaned_data:", formset.cleaned_data)

            report = form.save(commit=False)

            # ✅ 强化保存：确保 etc 字段写入
            report.etc_expected = form.cleaned_data.get('etc_expected') or 0
            report.etc_collected = form.cleaned_data.get('etc_collected') or 0

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
        return redirect('dailyreport:driver_basic_info', driver_id=driver.id)
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
@user_passes_test(is_dailyreport_admin)
def export_dailyreports_csv(request, year, month):
    from collections import defaultdict
    from django.db.models import Sum

    reports = DriverDailyReport.objects.filter(date__year=year, date__month=month).order_by('date', 'driver__name')
    response = HttpResponse(content_type='text/csv')

    # ✅ ✅ 修改：美化文件名为「2025年7月全员每日明细.csv」格式
    filename = f"{year}年{month}月全员每日明细.csv"
    response['Content-Disposition'] = f"attachment; filename*=UTF-8''{quote(filename)}"

    writer = csv.writer(response)

    headers = [
        '日期', '司机代码', '司机',
        '现金', 'Uber', 'Didi', 'クレジットカード',
        '扫码支付', '京交信', 'オムロン', '京都市他',
        'ETC应收', 'ETC实收', '未收ETC'
    ]
    writer.writerow(headers)

    payment_keys = ['cash', 'uber', 'didi', 'credit', 'qr', 'kyokushin', 'omron', 'kyotoshi']

    for report in reports:
        summary = defaultdict(int)
        for item in report.items.all():
            if item.payment_method in payment_keys:
                summary[item.payment_method] += item.meter_fee or 0

        etc_expected = report.etc_expected or 0
        etc_collected = report.etc_collected or 0
        etc_diff = etc_expected - etc_collected

        writer.writerow([
            report.date.strftime('%Y-%m-%d'),
            report.driver.driver_code if report.driver else '',
            report.driver.name,
            summary['cash'],
            summary['uber'],
            summary['didi'],
            summary['credit'],
            summary['qr'],
            summary['kyokushin'],
            summary['omron'],
            summary['kyotoshi'],
            etc_expected,
            etc_collected,
            etc_diff
        ])

    # ✅ 合计行统计
    total_summary = defaultdict(int)
    for report in reports:
        for item in report.items.all():
            if item.payment_method in payment_keys:
                total_summary[item.payment_method] += item.meter_fee or 0
        total_summary['etc_expected'] += report.etc_expected or 0
        total_summary['etc_collected'] += report.etc_collected or 0

    etc_diff = total_summary['etc_expected'] - total_summary['etc_collected']

    writer.writerow([
        '合计', '', '',  # 日期、司机代码、司机名
        total_summary['cash'],
        total_summary['uber'],
        total_summary['didi'],
        total_summary['credit'],
        total_summary['qr'],
        total_summary['kyokushin'],
        total_summary['omron'],
        total_summary['kyotoshi'],
        total_summary['etc_expected'],
        total_summary['etc_collected'],
        etc_diff
    ])

    return response

#导出全员每月汇总（每人一行）
@user_passes_test(is_dailyreport_admin)
def export_monthly_summary_csv(request, year, month):
    from collections import defaultdict
    from django.db.models import Sum
    from dailyreport.models import DriverDailyReport

    reports = DriverDailyReport.objects.filter(date__year=year, date__month=month).select_related('driver')
    response = HttpResponse(content_type='text/csv')
    filename = f"{year}年{month}月全员每月汇总.csv"
    response['Content-Disposition'] = f"attachment; filename*=UTF-8''{quote(filename)}"
    

    writer = csv.writer(response)

    # ✅ 1. 表头
    headers = [
        '司机代码','司机',
        '现金', 'Uber', 'Didi', 'クレジットカード', '扫码支付',
        '京交信', 'オムロン', '京都市他',
        'ETC应收', 'ETC实收', '未收ETC',
        '出勤天数'
    ]
    writer.writerow(headers)

    # ✅ 2. 准备统计结构
    driver_data = defaultdict(lambda: defaultdict(int))

    for report in reports:
        driver = report.driver.name
        driver_data[driver]['days'] += 1

        for item in report.items.all():
            method = item.payment_method
            amount = item.meter_fee or 0
            if method:
                driver_data[driver][method] += amount

        etc_expected = report.etc_expected or 0
        etc_collected = report.etc_collected or 0

        driver_data[driver]['etc_expected'] += etc_expected
        driver_data[driver]['etc_collected'] += etc_collected

    # ✅ 3. 写入每人一行
    payment_keys = ['cash', 'uber', 'didi', 'credit', 'qr', 'kyokushin', 'omron', 'kyotoshi']

    for driver_name, data in sorted(driver_data.items()):
        # 获取 driver 对象（通过名字找回）
        driver = Driver.objects.filter(name=driver_name).first()
        code = driver.driver_code if driver else ''
        row = [code, driver_name]
        for key in payment_keys:
            row.append(data.get(key, 0))

        etc_expected = data['etc_expected']
        etc_collected = data['etc_collected']
        etc_diff = etc_expected - etc_collected

        row += [etc_expected, etc_collected, etc_diff, data['days']]
        writer.writerow(row)

    # ✅ 合计行追加
    total_row = ['合计']
    for key in payment_keys:
        total = sum(d.get(key, 0) for d in driver_data.values())
        total_row.append(total)

    total_etc_expected = sum(d.get('etc_expected', 0) for d in driver_data.values())
    total_etc_collected = sum(d.get('etc_collected', 0) for d in driver_data.values())
    total_etc_diff = total_etc_expected - total_etc_collected
    total_days = sum(d.get('days', 0) for d in driver_data.values())

    total_row += [total_etc_expected, total_etc_collected, total_etc_diff, total_days]
    writer.writerow(total_row)

    return response

# ✅ 司机日报
@user_passes_test(is_dailyreport_admin)
def driver_dailyreport_month(request, driver_id):
    driver = get_driver_info(driver_id)
    if not driver:
        return render(request, 'dailyreport/not_found.html', status=404)
    today = now().date()

    selected_month = request.GET.get('month') or today.strftime('%Y-%m')  # ✅ 容错处理
    selected_date = request.GET.get('date', '').strip()

    if selected_date:
        try:
            selected_date_obj = datetime.strptime(selected_date, '%Y-%m-%d').date()
            reports = DriverDailyReport.objects.filter(driver=driver, date=selected_date_obj)
        except ValueError:
            reports = DriverDailyReport.objects.none()
    else:
        try:
            year, month = map(int, selected_month.split('-'))
            reports = DriverDailyReport.objects.filter(
                driver=driver, date__year=year, date__month=month
            )
        except ValueError:
            reports = DriverDailyReport.objects.none()

    reports = reports.order_by('-date')

    return render(request, 'dailyreport/driver_dailyreport_month.html', {
        'driver': driver,
        'reports': reports,
        'selected_month': selected_month,
        'selected_date': selected_date,
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

@user_passes_test(is_dailyreport_admin)
def dailyreport_add_by_month(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)

    month_str = request.GET.get("month")  # 格式："2025-03"
    if not month_str:
        return redirect("dailyreport:driver_dailyreport_add_selector", driver_id=driver_id)

    try:
        year, month = map(int, month_str.split("-"))
        # 校验是否是合法月份
        assert 1 <= month <= 12
    except (ValueError, AssertionError):
        return redirect("dailyreport:driver_dailyreport_add_selector", driver_id=driver_id)

    current_month = f"{year}年{month}月"

    return render(request, "dailyreport/dailyreport_add_month.html", {
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

    if request.method == 'POST':
        report_form = DriverDailyReportForm(request.POST)
        formset = ReportItemFormSet(request.POST)

        if report_form.is_valid() and formset.is_valid():
            dailyreport = report_form.save(commit=False)
            dailyreport.driver = driver

            # ✅ 自动计算时间字段
            dailyreport.calculate_work_times()

            # ✅ 新增：计算現金合计
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
            return redirect('dailyreport:driver_basic_info', driver_id=driver.id)
        else:
            print("日报主表错误：", report_form.errors)
            print("明细表错误：", formset.errors)
    else:
        report_form = DriverDailyReportForm()
        formset = ReportItemFormSet()

    # ✅ 合计面板用的 key-label 对
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

    # ✅ 修复：统计合计时使用 cleaned_data 而不是 instance
    if request.method == 'POST' and formset.is_valid():
        data_iter = [f.cleaned_data for f in formset.forms if f.cleaned_data]
    else:
        data_iter = [f.instance for f in formset.forms]
    totals = calculate_totals_from_formset(data_iter)
    print("🔥 DEBUG: totals = ", totals)  # 👈 添加这行

    return render(request, 'dailyreport/driver_dailyreport_edit.html', {
        'form': report_form,
        'formset': formset,
        'driver': driver,
        'is_edit': False,
        'summary_keys': summary_keys,
        'totals': totals,
    })

# ✅ 编辑日报（管理员）
@user_passes_test(is_dailyreport_admin)
def dailyreport_edit_for_driver(request, driver_id, report_id):
    driver = get_driver_info(driver_id)
    if not driver:
        return render(request, "dailyreport/not_found.html", status=404)

    
    report = get_object_or_404(DriverDailyReport, pk=report_id, driver_id=driver_id)
    duration = timedelta()

    # ✅ 添加这两行防止变量未赋值
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

            # ✅ 这里处理休憩時間
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

            # ✅ 插入这里：自动计算過不足額
            cash_total = sum(
                item.cleaned_data.get('meter_fee') or 0
                for item in formset.forms
                if item.cleaned_data.get('payment_method') == 'cash' and not item.cleaned_data.get('DELETE', False)
            )
            deposit = inst.deposit_amount or 0
            inst.deposit_difference = deposit - cash_total

            if inst.status in [DriverDailyReport.STATUS_PENDING, DriverDailyReport.STATUS_CANCELLED] and inst.clock_in and inst.clock_out:
                inst.status = DriverDailyReport.STATUS_COMPLETED
            if inst.clock_in and inst.clock_out:
                inst.has_issue = False

            inst.save()
            formset.instance = inst
            formset.save()

            # 更新 Reservation 出入库
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

            # ✅ 打印错误详情（推荐）
            print("📛 主表（form）错误：", form.errors)
            print("📛 明细表（formset）错误：")
            for i, f in enumerate(formset.forms):
                if f.errors:
                    print(f"  - 第{i+1}行: {f.errors}")
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

    # ✅ 汇总逻辑
    rates = {
        'meter':  Decimal('0.9091'),
        'cash':   Decimal('0'),
        'uber':   Decimal('0.05'),
        'didi':   Decimal('0.05'),
        'credit': Decimal('0.05'),
        'kyokushin': Decimal('0.05'),
        'omron':     Decimal('0.05'),
        'kyotoshi':  Decimal('0.05'),
        'qr':     Decimal('0.05'),
    }
    raw = {k: Decimal('0') for k in rates}
    split = {k: Decimal('0') for k in rates}

    if request.method == 'POST' and formset.is_valid():
        data_iter = [f.cleaned_data for f in formset.forms if f.cleaned_data]
    else:
        data_iter = [
            {
                'meter_fee': f.initial.get('meter_fee'),
                'payment_method': f.initial.get('payment_method'),
                'DELETE': f.initial.get('DELETE', False)
            }
            for f in formset.forms if f.initial.get('meter_fee') and not f.initial.get('DELETE', False)
        ]
    totals = calculate_totals_from_formset(data_iter)
    print("🧪 data_iter =", data_iter)
    print("🧪 totals =", totals)

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
        }
        for key, label in summary_keys
    ]

    return render(request, 'dailyreport/driver_dailyreport_edit.html', {
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

@user_passes_test(is_dailyreport_admin)
def dailyreport_overview(request):
    # 1. 基本参数：关键字 + 月份
    today     = now().date()
    keyword   = request.GET.get('keyword', '').strip()
    #year = int(request.GET.get('year', today.year))
    month_str = request.GET.get('month', today.strftime('%Y-%m'))

    # 2. 解析 month_str
    try:
        month = datetime.strptime(month_str, "%Y-%m")
    except ValueError:
        month = today.replace(day=1)
        month_str = month.strftime('%Y-%m')

    #year = month.year

    # ✅ 使用封装好的在职筛选函数
    drivers = get_active_drivers(month, keyword)

    # 3. 构建 reports，只按 month 过滤
    reports = DriverDailyReport.objects.filter(
        date__year=month.year,
        date__month=month.month
    )

    # 4. 全员明细聚合
    items = DriverDailyReportItem.objects.filter(report__in=reports)
    totals = items.aggregate(
        total_meter  = Sum('meter_fee'),
        total_cash   = Sum(Case(When(payment_method='cash',    then=F('meter_fee')), default=0, output_field=DecimalField())),
        total_uber   = Sum(Case(When(payment_method='uber',    then=F('meter_fee')), default=0, output_field=DecimalField())),
        total_didi   = Sum(Case(When(payment_method='didi',    then=F('meter_fee')), default=0, output_field=DecimalField())),
        total_credit = Sum(Case(When(payment_method='credit',  then=F('meter_fee')), default=0, output_field=DecimalField())),
        total_kyokushin = Sum(Case(When(payment_method='kyokushin', then=F('meter_fee')), default=0, output_field=DecimalField())),
        total_omron     = Sum(Case(When(payment_method='omron',     then=F('meter_fee')), default=0, output_field=DecimalField())),
        total_kyotoshi  = Sum(Case(When(payment_method='kyotoshi',  then=F('meter_fee')), default=0, output_field=DecimalField())),
        total_qr     = Sum(Case(When(payment_method='qr', then=F('meter_fee')), default=0, output_field=DecimalField())),
    )

    # 5. 税前计算
    gross = totals.get('total_meter') or Decimal('0')
    totals['meter_pre_tax'] = (gross / Decimal('1.1')).quantize(Decimal('1'), rounding=ROUND_HALF_UP)

    # 6. 分成额计算
    rates = {
        'meter':  Decimal('0.9091'),
        'cash':   Decimal('0'),
        'uber':   Decimal('0.05'),
        'didi':   Decimal('0.05'),
        'credit': Decimal('0.05'),
        'kyokushin': Decimal('0.05'),
        'omron':     Decimal('0.05'),
        'kyotoshi':  Decimal('0.05'),
        'qr':     Decimal('0.05'),
    }
    def split(key):
        amt = totals.get(f"total_{key}") or Decimal('0')
        return (amt * rates[key]).quantize(Decimal('1'), rounding=ROUND_HALF_UP)

    totals.update({
        'meter_split':  split('meter'),
        'cash_split':   split('cash'),
        'uber_split':   split('uber'),
        'didi_split':   split('didi'),
        'credit_split': split('credit'),
        'kyokushin': Decimal('0.05'),
        'omron':     Decimal('0.05'),
        'kyotoshi':  Decimal('0.05'),
        'qr_split':     split('qr'),
    })

    # ✅ 6.5 重新构建 totals_all 给模板使用（使用 xxx_raw + xxx_split 命名）
    totals_all = {
        "meter": {
            "total": totals.get("total_meter") or Decimal('0'),
            "bonus": totals.get("meter_split") or Decimal('0'),
        },
        "cash": {
            "total": totals.get("total_cash") or Decimal('0'),
            "bonus": totals.get("cash_split") or Decimal('0'),
        },
        "uber": {
            "total": totals.get("total_uber") or Decimal('0'),
            "bonus": totals.get("uber_split") or Decimal('0'),
        },
        "didi": {
            "total": totals.get("total_didi") or Decimal('0'),
            "bonus": totals.get("didi_split") or Decimal('0'),
        },
        "credit": {
            "total": totals.get("total_credit") or Decimal('0'),
            "bonus": totals.get("credit_split") or Decimal('0'),
        },
        "kyokushin": {
            "total": totals.get("total_kyokushin") or Decimal('0'),
            "bonus": split("kyokushin"),
        },
        "omron": {
            "total": totals.get("total_omron") or Decimal('0'),
            "bonus": split("omron"),
        },
        "kyotoshi": {
            "total": totals.get("total_kyotoshi") or Decimal('0'),
            "bonus": split("kyotoshi"),
        },
        "qr": {
            "total": totals.get("total_qr") or Decimal('0'),
            "bonus": totals.get("qr_split") or Decimal('0'),
        },
    }

    # 7. 遍历全体司机，构造每人合计（无日报也显示）

    # ✅ 使用统一封装的在职司机筛选函数
    driver_qs = drivers

    # ✅ 遍历符合条件的司机，计算其当月的合计水揚金额 + 备注状态
    driver_data = []
    for d in driver_qs:
        # 获取该司机本月的所有日报记录
        dr_reps = reports.filter(driver=d)

        # 计算该司机本月合计メータ金額（即水揚）
        total = sum(r.total_meter_fee for r in dr_reps)

        # 标注备注：未报 或 有异常
        if dr_reps.exists():
            note = "⚠️ 異常あり" if dr_reps.filter(has_issue=True).exists() else ""
        else:
            note = "（未報告）"

        # 整理成字典追加到列表中
        driver_data.append({
            'driver':    d,
            'total_fee': total,
            'note':      note,
            'month_str': month_str,
        })

    # 8. 分页
    page_obj = Paginator(driver_data, 10).get_page(request.GET.get('page'))

    # ✅ 9. 添加合计栏用的 key-label 对（显示：メーター / 現金 / QR 等）
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


    # ✅ 10. 生成分页月份链接（用于“上一月”“下一月”按钮）
    from dateutil.relativedelta import relativedelta
    prev_month_str = (month - relativedelta(months=1)).strftime('%Y-%m')
    next_month_str = (month + relativedelta(months=1)).strftime('%Y-%m')

    # 11. 渲染模板
    current_year = month.year
    current_month = month.month

    return render(request, 'dailyreport/dailyreport_overview.html', {
        'page_obj': page_obj,
        'month': month,
        'month_str': month.strftime('%Y-%m'),
        'month_label': month.strftime('%Y年%m月'),
        'prev_month': prev_month_str,
        'next_month': next_month_str,
        'keyword': keyword,
        'totals_all': totals_all,
        'summary_keys': summary_keys,
        'current_year': current_year,
        'current_month': current_month,  # ✅ 这两行是新增
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