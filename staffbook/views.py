from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from .forms import DriverDailySalesForm, DriverDailyReportForm, DriverForm, ReportItemFormSet
from .models import DriverDailySales, DriverDailyReport, Driver
from django.db.models import Q
from django.utils import timezone
from django import forms

def is_admin(user):
    return user.is_staff or user.is_superuser

@login_required
@user_passes_test(is_admin)
def dailyreport_create(request):
    if request.method == 'POST':
        form = DriverDailyReportForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('staffbook:dailyreport_list')
    else:
        form = DriverDailyReportForm()
    return render(request, 'staffbook/dailyreport_formset.html', {'form': form})

@login_required
@user_passes_test(is_admin)
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

@login_required
def submit_sales(request):
    if request.method == 'POST':
        form = DriverDailySalesForm(request.POST)
        if form.is_valid():
            sales = form.save(commit=False)
            sales.driver = request.user
            sales.save()
            return redirect('staffbook:sales_thanks')  # 录入成功页面
    else:
        form = DriverDailySalesForm()
    
    return render(request, 'staffbook/submit_sales.html', {'form': form})

@login_required
def sales_thanks(request):
    return render(request, 'staffbook/sales_thanks.html')

@user_passes_test(lambda u: u.is_staff)
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

@login_required
def dailyreport_list(request):
    # 可根据需求筛选，比如只显示自己的
    if request.user.is_staff:
        reports = DriverDailyReport.objects.all().order_by('-date')
    else:
        reports = DriverDailyReport.objects.filter(driver=request.user).order_by('-date')
    return render(request, 'staffbook/dailyreport_list.html', {'reports': reports})


# 员工列表（管理员可见）
#@user_passes_test(lambda u: u.is_staff)
def driver_list(request):
    keyword = request.GET.get('keyword', '').strip()
    if keyword:
        drivers = Driver.objects.filter(
            Q(name__icontains=keyword) | Q(staff_code__icontains=keyword)
        )
    else:
        drivers = Driver.objects.all()
    #print("【调试】当前员工数量：", drivers.count(), "| 关键字：", repr(keyword))
    return render(request, 'staffbook/driver_list.html', {'drivers': drivers})

def driver_create(request):
    if request.method == 'POST':
        form = DriverForm(request.POST)
        if form.is_valid():
            driver = form.save()
            return redirect('staffbook:driver_detail', driver_id=driver.id)
    else:
        form = DriverForm()
    return render(request, 'staffbook/driver_form.html', {'form': form, 'is_create': True})

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

# 员工卡片视图（包含日报列表）
@login_required
def driver_detail(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    if not (request.user.is_staff or driver.user == request.user):
        return redirect('staffbook:driver_list')

    # 获取查询参数
    selected_date = request.GET.get('date')
    selected_month = request.GET.get('month')

    # 构建查询条件
    reports = DriverDailyReport.objects.filter(driver=driver)
    if selected_date:
        reports = reports.filter(date=selected_date)
    elif selected_month:
        # selected_month 形如 '2025-06'
        year, month = map(int, selected_month.split('-'))
        reports = reports.filter(date__year=year, date__month=month)
    reports = reports.order_by('-date')

    can_edit = request.user.is_staff
    return render(request, 'staffbook/driver_detail.html', {
        'driver': driver,
        'reports': reports,
        'selected_date': selected_date,
        'selected_month': selected_month,
        'can_edit': can_edit,
    })

# 新增日报（管理员为任意员工）
@user_passes_test(lambda u: u.is_staff)
def dailyreport_create_for_driver(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    if request.method == 'POST':
        report_form = DriverDailyReportForm(request.POST)
        formset = ReportItemFormSet(request.POST)
        if report_form.is_valid() and formset.is_valid():
            dailyreport = report_form.save(commit=False)
            dailyreport.driver = driver
            dailyreport.save()
            # 关键点：让 formset 关联到这个 dailyreport
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

# 编辑日报（管理员）
@user_passes_test(lambda u: u.is_staff)
def dailyreport_edit_for_driver(request, driver_id, pk):
    driver = get_object_or_404(Driver, pk=driver_id)
    dailyreport = get_object_or_404(DriverDailyReport, pk=pk, driver=driver)
    if request.method == 'POST':
        report_form = DriverDailyReportForm(request.POST, instance=dailyreport)
        formset = ReportItemFormSet(request.POST, instance=dailyreport)
        if report_form.is_valid() and formset.is_valid():
            report_form.save()
            formset.save()
            messages.success(request, '日报修改成功')
            return redirect('staffbook:driver_detail', driver_id=driver.id)
    else:
        report_form = DriverDailyReportForm(instance=dailyreport)
        formset = ReportItemFormSet(instance=dailyreport)
        # 设置日期字段为只读和初值
        report_form.fields['date'].initial = dailyreport.date.strftime('%Y-%m-%d')
        report_form.fields['date'].widget = forms.HiddenInput()

    return render(request, 'staffbook/dailyreport_formset.html', {
        'form': report_form,
        'formset': formset,
        'driver': driver,
        'is_edit': True,
        #'selected_date': selected_date,   # ✅ 传入模板
    })

# 日报列表（管理员看全部，司机看自己）
@login_required
def dailyreport_list(request):
    if request.user.is_staff:
        reports = DriverDailyReport.objects.all().order_by('-date')
    else:
        reports = DriverDailyReport.objects.filter(driver=request.user).order_by('-date')
    return render(request, 'staffbook/dailyreport_list.html', {'reports': reports})

# 司机个人查看自己的日报（比如“我的资料”页可以引用此函数，或在 accounts/views.py 中实现）
@login_required
def my_dailyreports(request):
    reports = DriverDailyReport.objects.filter(driver=request.user).order_by('-date')
    return render(request, 'staffbook/my_dailyreports.html', {'reports': reports})

@staff_member_required
def bind_missing_users(request):
    drivers_without_user = Driver.objects.filter(user__isnull=True)

    if request.method == 'POST':
        for driver in drivers_without_user:
            # 使用 staff_code 作为用户名，避免重复
            username = f"driver{driver.staff_code}"
            if not User.objects.filter(username=username).exists():
                user = User.objects.create_user(username=username, password='12345678')
                driver.user = user
                driver.save()
        return redirect('staffbook:bind_missing_users')

    return render(request, 'staffbook/bind_missing_users.html', {
        'drivers': drivers_without_user,
    })