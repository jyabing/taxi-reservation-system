from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import DriverDailySalesForm, DriverDailyReportForm, DriverForm, ReportItemFormSet, DriverPersonalInfoForm, DriverLicenseForm, DriverBasicForm
from .models import DriverDailySales, DriverDailyReport, Driver, DrivingExperience, Insurance, FamilyMember, DriverLicense, LicenseType
from django.db.models import Q, Sum
from django.forms import inlineformset_factory
from django.utils import timezone
from django import forms
from datetime import date
from calendar import monthrange

from accounts.utils import check_module_permission

def driver_card(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    return render(request, "staffbook/driver_basic_info.html", {"driver": driver})

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
        return redirect('staffbook:driver_basic_info', driver_id=driver.id)
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
            Q(name__icontains=keyword) | Q(driver_code__icontains=keyword)
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
            return redirect('staffbook:driver_basic_info', driver_id=driver.id)
    else:
        form = DriverForm()
    return render(request, 'staffbook/driver_create.html', {'form': form, 'is_create': True})

# ✅ 编辑员工
def driver_edit(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    DrivingExpFormSet = inlineformset_factory(Driver, DrivingExperience, fields="__all__", extra=1, can_delete=True)
    InsuranceFormSet = inlineformset_factory(Driver, Insurance, fields="__all__", extra=1, can_delete=True)
    FamilyFormSet = inlineformset_factory(Driver, FamilyMember, fields="__all__", extra=1, can_delete=True)

    if request.method == 'POST':
        form = DriverForm(request.POST, request.FILES, instance=driver)
        exp_formset = DrivingExpFormSet(request.POST, instance=driver)
        ins_formset = InsuranceFormSet(request.POST, instance=driver)
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
        ins_formset = InsuranceFormSet(instance=driver)
        fam_formset = FamilyFormSet(instance=driver)

    return render(request, 'staffbook/driver_edit.html', {
        'form': form,
        'exp_formset': exp_formset,
        'ins_formset': ins_formset,
        'fam_formset': fam_formset,
        'driver': driver,
    })

# 个人主页+台账
@login_required
def driver_basic_info(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    return render(request, 'staffbook/driver_basic_info.html', {
        'driver': driver,
        'main_tab': 'basic',
        'tab': 'basic',
    })

@login_required
def driver_basic_edit(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    if request.method == 'POST':
        form = DriverBasicForm(request.POST, request.FILES, instance=driver)
        if form.is_valid():
            form.save()
            return redirect('staffbook:driver_basic_info', driver_id=driver.id)
    else:
        form = DriverBasicForm(instance=driver)
    return render(request, 'staffbook/driver_basic_edit.html', {
        'form': form,
        'driver': driver,
        'main_tab': 'basic',
        'tab': 'basic'
    })

#運転経験
@login_required
def driver_experience_info(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    # 查询经验对象，可以多条
    experiences = DrivingExperience.objects.filter(driver=driver)
    return render(request, 'staffbook/driver_experience_info.html', {
        'driver': driver,
        'experiences': experiences,
        'main_tab': 'driving',
        'tab': 'experience',
    })

@login_required
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

#個人情報
@login_required
def driver_personal_info(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    if request.method == 'POST':
        form = DriverPersonalInfoForm(request.POST, request.FILES, instance=driver)
        if form.is_valid():
            form.save()
            messages.success(request, "个人情报已保存！")
            return redirect('staffbook:driver_personal_info', driver_id=driver.id)
    else:
        form = DriverPersonalInfoForm(instance=driver)
    return render(request, 'staffbook/driver_personal_info.html', {
        'driver': driver,
        'form': form,
        'active_tab': 'personal',  # tab高亮
    })

@login_required
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

# 緊急連絡先
@login_required
def driver_emergency_info(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    # 你可以先不传实际数据，先做一个空模板
    return render(request, 'staffbook/driver_emergency_info.html', {
        'driver': driver,
        'main_tab': 'basic',
        'tab': 'emergency'
    })

@login_required
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
@login_required
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

@login_required
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
@login_required
def driver_experience_info(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    experiences = DrivingExperience.objects.filter(driver=driver)
    return render(request, 'staffbook/driver_experience_info.html', {
        'driver': driver,
        'experiences': experiences,
        'main_tab': 'driving',
        'tab': 'experience',
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
@login_required
def driver_qualification_info(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    qualification, _ = Qualification.objects.get_or_create(driver=driver)
    return render(request, 'staffbook/driver_qualification_info.html', {
        'driver': driver,
        'qualification': qualification,
        'main_tab': 'driving',
        'tab': 'qualification',
    })

@login_required
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
@login_required
def driver_aptitude_info(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    qualification, created = Qualification.objects.get_or_create(driver=driver)
    return render(request, 'staffbook/driver_qualification_info.html', {
        'driver': driver,
        'qualification': qualification,
        'main_tab': 'driving',
        'tab': 'qualification',
    })

@login_required
def driver_aptitude_edit(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    aptitude, created = aptitude.objects.get_or_create(driver=driver)
    if request.method == 'POST':
        form = aptitudeForm(request.POST, instance=aptitude)
        if form.is_valid():
            form.save()
            return redirect('staffbook:driver_aptitude_info', driver_id=driver.id)
    else:
        form = aptitudeForm(instance=aptitude)
    return render(request, 'staffbook/driver_aptitude_edit.html', {
        'form': form,
        'driver': driver,
        'main_tab': 'driving',
        'tab': 'aptitude',
    })


#賞罰
@login_required
def driver_rewards_info(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    rewards, created = Rewards.objects.get_or_create(driver=driver)
    return render(request, 'staffbook/driver_rewards_info.html', {
        'driver': driver,
        'rewards': rewards,
        'main_tab': 'driving',
        'tab': 'rewards',
    })

@login_required
def driver_rewards_edit(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    rewards, created = Rewards.objects.get_or_create(driver=driver)
    if request.method == 'POST':
        form = rewardsForm(request.POST, instance=rewards)
        if form.is_valid():
            form.save()
            return redirect('staffbook:driver_rewards_info', driver_id=driver.id)
    else:
        form = rewardsForm(instance=health)
    return render(request, 'staffbook/driver_rewards_edit.html', {
        'form': form,
        'driver': driver,
        'main_tab': 'driving',
        'tab': 'rewards',
    })


#事故・違反
@login_required
def driver_accident_info(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    accident, created = Accident.objects.get_or_create(driver=driver)
    return render(request, 'staffbook/driver_accident_info.html', {
        'driver': driver,
        'accident': accident,
        'main_tab': 'driving',
        'tab': 'education',
    })

@login_required
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
@login_required
def driver_education_info(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    education, created = Education.objects.get_or_create(driver=driver)
    return render(request, 'staffbook/driver_education_info.html', {
        'driver': driver,
        'education': education,
        'main_tab': 'driving',
        'tab': 'education',
    })

@login_required
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
@login_required
def driver_health_info(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    health, created = Health.objects.get_or_create(driver=driver)
    return render(request, 'staffbook/driver_health_info.html', {
        'driver': driver,
        'health': health,
        'main_tab': 'driving',
        'tab': 'health',
    })

@login_required
def driver_health_edit(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    health, created = Health.objects.get_or_create(driver=driver)
    if request.method == 'POST':
        form = HealthForm(request.POST, instance=health)
        if form.is_valid():
            form.save()
            return redirect('staffbook:driver_health_info', driver_id=driver.id)
    else:
        form = HealthForm(instance=health)
    return render(request, 'staffbook/driver_health_edit.html', {
        'form': form,
        'driver': driver,
        'main_tab': 'driving',
        'tab': 'health',
    })


#既往歴
@login_required
def driver_history_info(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    history, created = History.objects.get_or_create(driver=driver)
    return render(request, 'staffbook/driver_history_info.html', {
        'driver': driver,
        'history': history,
        'main_tab': 'driving',
        'tab': 'history',
    })

@login_required
def driver_history_edit(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    history, created = History.objects.get_or_create(driver=driver)
    if request.method == 'POST':
        form = historyForm(request.POST, instance=health)
        if form.is_valid():
            form.save()
            return redirect('staffbook:driver_history_info', driver_id=driver.id)
    else:
        form = HistoryForm(instance=history)
    return render(request, 'staffbook/driver_history_edit.html', {
        'form': form,
        'driver': driver,
        'main_tab': 'driving',
        'tab': 'history',
    })


# ✅ 司机日报（管理员看全部，司机看自己）
@login_required
def driver_card_daily(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    # 默认查询本月日报
    today = date.today()
    selected_month = request.GET.get('month', today.strftime('%Y-%m'))
    year, month = map(int, selected_month.split('-'))
    reports = DriverDailyReport.objects.filter(driver=driver, date__year=year, date__month=month).order_by('-date')
    return render(request, 'staffbook/driver_card_daily.html', {
        'driver': driver,
        'reports': reports,
        'selected_month': selected_month,
        'active_tab': 'daily',
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
            return redirect('staffbook:driver_basic_info', driver_id=driver.id)
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
            return redirect('staffbook:driver_basic_info', driver_id=driver.id)

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
            username = f"driver{driver.driver_code}"
            if not User.objects.filter(username=username).exists():
                user = User.objects.create_user(username=username, password='12345678')
                driver.user = user
                driver.save()
        return redirect('staffbook:bind_missing_users')

    return render(request, 'staffbook/bind_missing_users.html', {
        'drivers': drivers_without_user,
    })
