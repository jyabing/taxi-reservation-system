import datetime

from django.contrib.auth.decorators import user_passes_test, login_required
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.shortcuts import render, get_object_or_404, redirect, HttpResponse
from django.utils.timezone import now
from django.utils import timezone
from django.db.models import Sum, Case, When, F, DecimalField, Q

from .models import DriverDailyReport, DriverDailyReportItem
from .forms import DriverDailyReportForm, DriverDailyReportItemForm, ReportItemFormSet

from staffbook.services import get_driver_info
from staffbook.utils import is_dailyreport_admin
from staffbook.models import Driver

from vehicles.models import Reservation

from .utils import (
    calculate_totals_from_formset,
    calculate_totals_from_queryset,
    PAYMENT_KEYWORDS,
)

from decimal import Decimal, ROUND_HALF_UP
from calendar import monthrange, month_name



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
        extra=0,
        can_delete=True
    )

    if request.method == 'POST':
        form = DriverDailyReportForm(request.POST, instance=report)
        formset = ReportItemFormSet(request.POST, instance=report)

        if form.is_valid() and formset.is_valid():
            print("🧪 cleaned_data:", formset.cleaned_data)
            form.save()
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

@user_passes_test(is_dailyreport_admin)
def export_dailyreports_csv(request):
    month_str = request.GET.get('month')  # 例: '2025-06'

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="dailyreports.csv"'

    writer = csv.writer(response)
    writer.writerow([
        '司机', '日期', '出勤时间', '退勤时间',
        '勤務時間', '休憩時間', '実働時間', '残業時間'
    ])

    reports = DriverDailyReport.objects.all().order_by('-date')
    
    if month_str:
        try:
            year, month = map(int, month_str.split('-'))
            start_date = datetime.date(year, month, 1)
            if month == 12:
                end_date = datetime.date(year + 1, 1, 1)
            else:
                end_date = datetime.date(year, month + 1, 1)
            reports = reports.filter(date__gte=start_date, date__lt=end_date)
        except Exception:
            pass

    def fmt(td):
        if td is None:
            return ''
        total_minutes = int(td.total_seconds() // 60)
        return f"{total_minutes // 60:02}:{total_minutes % 60:02}"

    for report in reports:
        writer.writerow([
            report.driver.name,
            report.date.strftime("%Y-%m-%d"),
            report.clock_in.strftime("%H:%M") if report.clock_in else '',
            report.clock_out.strftime("%H:%M") if report.clock_out else '',
            fmt(report.勤務時間),
            fmt(report.休憩時間),
            fmt(report.実働時間),
            fmt(report.残業時間),
        ])

    return response

def export_monthly_summary_csv(request):
    target_month = request.GET.get('month')  # 例：2025-07
    reports = DriverDailyReport.objects.filter(date__startswith=target_month).select_related('driver')

    # 按员工聚合
    summary = defaultdict(lambda: defaultdict(int))

    for report in reports:
        driver = report.driver
        code = driver.driver_code or ''
        key = f"{driver.name}（{code}）"

        summary[key]['uber'] += getattr(report, 'uber_fee', 0) or 0
        summary[key]['credit'] += getattr(report, 'credit_fee', 0) or 0
        summary[key]['didi'] += getattr(report, 'didi_fee', 0) or 0
        summary[key]['qr'] += getattr(report, 'qr_fee', 0) or 0
        summary[key]['omron'] += getattr(report, 'omron_fee', 0) or 0
        summary[key]['kyotoshi'] += getattr(report, 'kyotoshi_fee', 0) or 0
        summary[key]['gasoline'] += getattr(report, 'gasoline_fee', 0) or 0
        summary[key]['distance_km'] += getattr(report, 'distance_km', 0) or 0
        summary[key]['smoke'] += getattr(report, 'smoke_fee', 0) or 0
        summary[key]['refund_lack'] += getattr(report, 'refund_lack', 0) or 0

    response = HttpResponse(content_type='text/csv')
    filename = f"月报汇总_{target_month}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)

    # 表头
    writer.writerow([
        '従業員（コード）', '空車', 'ETC', 
        'Uber売上', 'クレジット売上', 'DIDI売上', 'PayPay売上',
        'オムロン売上', '京交信市他売上', '水揚合計',
        'ガソリン', '里程KM',  '返金不足'
    ])

    for key, data in summary.items():
        total = sum([
            data['uber'], data['credit'], data['didi'], data['qr'],
            data['omron'], data['kyotoshi']
        ])
        writer.writerow([
            key,
            0, 0, 0, 0,  # 空車 ETC 楽券 子機料 默认填0
            data['uber'],
            data['credit'],
            data['didi'],
            data['qr'],
            data['omron'],
            data['kyotoshi'],
            total,
            data['gasoline'],
            data['distance_km'],
            data['smoke'],
            data['refund_lack'],
        ])

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
            selected_date_obj = datetime.datetime.strptime(selected_date, '%Y-%m-%d').date()
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
    duration = datetime.timedelta()

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

            inst.休憩時間 = datetime.timedelta(minutes=break_minutes)
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
                    res.actual_departure = timezone.make_aware(datetime.datetime.combine(inst.date, inst.clock_in), tz)
                    if inst.clock_out:
                        ret_date = inst.date
                        if inst.clock_out < inst.clock_in:
                            ret_date += datetime.timedelta(days=1)
                        res.actual_return = timezone.make_aware(datetime.datetime.combine(ret_date, inst.clock_out), tz)
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
                    dt_in = datetime.datetime.combine(report.date, clock_in)
                    dt_out = datetime.datetime.combine(report.date, clock_out)
                    if dt_out <= dt_in:
                        dt_out += datetime.timedelta(days=1)
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
    month_str = request.GET.get('month', today.strftime('%Y-%m'))

    # 2. 解析 month_str
    try:
        month = datetime.datetime.strptime(month_str, "%Y-%m")
    except ValueError:
        month = today.replace(day=1)

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
    first_day_of_month = month.replace(day=1)

    # ✅ 筛选未离职或离职日期在本月之后的司机
    driver_qs = Driver.objects.filter(
        Q(resigned_date__isnull=True) | Q(resigned_date__gte=first_day_of_month)
    )

    # ✅ 上方已经定义了 driver_qs，直接在这里加关键字过滤
    if keyword:
        driver_qs = driver_qs.filter(name__icontains=keyword)

    driver_data = []
    for d in driver_qs:
        dr_reps = reports.filter(driver=d)
        total = sum(r.total_meter_fee for r in dr_reps)
        if dr_reps.exists():
            note = "⚠️ 異常あり" if dr_reps.filter(has_issue=True).exists() else ""
        else:
            note = "（未報告）"

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

    # 10. 渲染模板
    return render(request, 'dailyreport/dailyreport_overview.html', {
        'page_obj':  page_obj,
        'month':     month,
        'month_str': month_str,
        'keyword':   keyword,
        'totals_all':    totals_all,
        'summary_keys':  summary_keys,
    })
    
