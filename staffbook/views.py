from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import DriverDailySalesForm, DriverDailyReportForm, DriverForm, ReportItemFormSet
from .models import DriverDailySales, DriverDailyReport, Driver
from django.db.models import Q, Sum
from django.utils import timezone
from django import forms

from accounts.utils import check_module_permission

@login_required
def staffbook_dashboard(request):
    return render(request, 'staffbook/dashboard.html')

# ✅ 新增日报
@check_module_permission('employee')
def dailyreport_create(request):
    if request.method == 'POST':
        form = DriverDailyReportForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('staffbook:dailyreport_list')
    else:
        form = DriverDailyReportForm()
    return render(request, 'staffbook/dailyreport_formset.html', {'form': form})

# ✅ 编辑日报
@check_module_permission('employee')
def dailyreport_edit(request, pk):
    report = get_object_or_404(DriverDailyReport, pk=pk)
    if request.method == 'POST':
        form = DriverDailyReportForm(request.POST, instance=report)
        if form.is_valid():
            form.save()
            return redirect('staffbook:dailyreport_list')
    else:
        form = DriverDailyReportForm(instance=report)
    return render(request, 'staffbook/dailyreport_formset.html', {'form': form})

# ✅ 提交销售额（司机自己）
@login_required
def submit_sales(request):
    if request.method == 'POST':
        form = DriverDailySalesForm(request.POST)
        if form.is_valid():
            sales = form.save(commit=False)
            sales.driver = request.user
            sales.save()
            return redirect('staffbook:sales_thanks')
    else:
        form = DriverDailySalesForm()
    return render(request, 'staffbook/submit_sales.html', {'form': form})

@login_required
def sales_thanks(request):
    return render(request, 'staffbook/sales_thanks.html')

# ✅ 删除日报（管理员）
@check_module_permission('employee')
def dailyreport_delete_for_driver(request, driver_id, pk):
    driver = get_object_or_404(Driver, pk=driver_id)
    report = get_object_or_404(DriverDailyReport, pk=pk, driver=driver)
    if request.method == "POST":
        report.delete()
        messages.success(request, "已删除该日报记录。")
        return redirect('staffbook:driver_detail', driver_id=driver.id)
    return render(request, 'staffbook/dailyreport_confirm_delete.html', {
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
    return render(request, 'staffbook/dailyreport_list.html', {'reports': reports})

# ✅ 员工列表（管理员）
@check_module_permission('employee')
def driver_list(request):
    keyword = request.GET.get('keyword', '').strip()
    if keyword:
        drivers = Driver.objects.filter(
            Q(name__icontains=keyword) | Q(staff_code__icontains=keyword)
        )
    else:
        drivers = Driver.objects.all()
    return render(request, 'staffbook/driver_list.html', {'drivers': drivers})

# ✅ 新增员工
@check_module_permission('employee')
def driver_create(request):
    if request.method == 'POST':
        form = DriverForm(request.POST)
        if form.is_valid():
            driver = form.save()
            return redirect('staffbook:driver_detail', driver_id=driver.id)
    else:
        form = DriverForm()
    return render(request, 'staffbook/driver_form.html', {'form': form, 'is_create': True})

# ✅ 编辑员工
@check_module_permission('employee')
def driver_edit(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    if request.method == 'POST':
        form = DriverForm(request.POST, instance=driver)
        if form.is_valid():
            form.save()
            return redirect('staffbook:driver_detail', driver_id=driver.id)
    else:
        form = DriverForm(instance=driver)
    return render(request, 'staffbook/driver_form.html', {'form': form, 'is_create': False})

# ✅ 员工详情页（司机可看自己，管理员可看全部）
@login_required
def driver_detail(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    if not (request.user.is_staff or driver.user == request.user):
        return redirect('staffbook:driver_list')

    selected_date = request.GET.get('date')
    selected_month = request.GET.get('month')

    reports = DriverDailyReport.objects.filter(driver=driver)
    if selected_date:
        reports = reports.filter(date=selected_date)
    elif selected_month:
        year, month = map(int, selected_month.split('-'))
        reports = reports.filter(date__year=year, date__month=month)
    reports = reports.order_by('-date')

    for report in reports:
        report.total_meter_fee = report.items.aggregate(total=Sum('meter_fee'))['total'] or 0

    can_edit = request.user.is_staff
    return render(request, 'staffbook/driver_detail.html', {
        'driver': driver,
        'reports': reports,
        'selected_date': selected_date,
        'selected_month': selected_month,
        'can_edit': can_edit,
    })

# ✅ 管理员新增日报给某员工
@check_module_permission('employee')
def dailyreport_create_for_driver(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    if request.method == 'POST':
        report_form = DriverDailyReportForm(request.POST)
        formset = ReportItemFormSet(request.POST)
        if report_form.is_valid() and formset.is_valid():
            dailyreport = report_form.save(commit=False)
            dailyreport.driver = driver
            dailyreport.save()
            formset.instance = dailyreport
            formset.save()
            messages.success(request, '新增日报成功')
            return redirect('staffbook:driver_detail', driver_id=driver.id)
        else:
            print("日报主表错误：", report_form.errors)
            print("明细表错误：", formset.errors)
    else:
        report_form = DriverDailyReportForm()
        formset = ReportItemFormSet()
    return render(request, 'staffbook/dailyreport_formset.html', {
        'form': report_form,
        'formset': formset,
        'driver': driver,
        'is_edit': False,
    })

# ✅ 编辑日报（管理员）
@check_module_permission('employee')
def dailyreport_edit_for_driver(request, driver_id, pk):
    driver = get_object_or_404(Driver, pk=driver_id)
    dailyreport = get_object_or_404(DriverDailyReport, pk=pk, driver=driver)

    if request.method == 'POST':
        report_form = DriverDailyReportForm(request.POST, instance=dailyreport)
        formset = ReportItemFormSet(request.POST, instance=dailyreport)

        if report_form.is_valid() and formset.is_valid():
            report = report_form.save(commit=False)
            report.edited_by = request.user  # ✅ 记录编辑人
            report.edited_at = timezone.now()  # ✅ 记录编辑时间
            report.save()
            formset.save()
            messages.success(request, '日报修改成功')
            return redirect('staffbook:driver_detail', driver_id=driver.id)

    else:
        report_form = DriverDailyReportForm(instance=dailyreport)
        formset = ReportItemFormSet(instance=dailyreport)
        report_form.fields['date'].initial = dailyreport.date.strftime('%Y-%m-%d')
        report_form.fields['date'].widget = forms.HiddenInput()

    return render(request, 'staffbook/dailyreport_formset.html', {
        'form': report_form,
        'formset': formset,
        'driver': driver,
        'is_edit': True,
        'report': dailyreport,  # ✅ 传给模板用于显示“由谁于何时编辑”
    })

# ✅ 司机查看自己日报
@login_required
def my_dailyreports(request):
    reports = DriverDailyReport.objects.filter(driver=request.user).order_by('-date')
    return render(request, 'staffbook/my_dailyreports.html', {'reports': reports})

# ✅ 批量生成账号绑定员工
@check_module_permission('employee')
def bind_missing_users(request):
    drivers_without_user = Driver.objects.filter(user__isnull=True)

    if request.method == 'POST':
        for driver in drivers_without_user:
            username = f"driver{driver.staff_code}"
            if not User.objects.filter(username=username).exists():
                user = User.objects.create_user(username=username, password='12345678')
                driver.user = user
                driver.save()
        return redirect('staffbook:bind_missing_users')

    return render(request, 'staffbook/bind_missing_users.html', {
        'drivers': drivers_without_user,
    })
