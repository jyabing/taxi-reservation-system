import datetime
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test

from .permissions import is_staffbook_admin
from django.contrib import messages
from .forms import (
    DriverDailySalesForm, DriverDailyReportForm, DriverForm, 
    ReportItemFormSet, DriverPersonalInfoForm, DriverLicenseForm, 
    DriverBasicForm, RewardForm, DriverPayrollRecordForm
    )
from .models import (
    DriverDailySales, DriverDailyReport, DriverDailyReportItem, Driver, DrivingExperience, 
    Insurance, FamilyMember, DriverLicense, LicenseType, Qualification, Aptitude,
    Reward, Accident, Education, Insurance, Pension, DriverPayrollRecord 
    )
from django.db.models import Q, Sum, Case, When, F, DecimalField
from django.forms import inlineformset_factory, modelformset_factory
from django.utils import timezone
from django import forms
from datetime import timedelta
from calendar import monthrange
from django.utils.timezone import now
from django.core.paginator import Paginator
from django.urls import reverse
from decimal import Decimal, ROUND_HALF_UP

from vehicles.models import Reservation 

from accounts.utils import check_module_permission

def driver_card(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    return render(request, "staffbook/driver_basic_info.html", {"driver": driver})

@user_passes_test(is_staffbook_admin)
def staffbook_dashboard(request):
    return render(request, 'staffbook/dashboard.html')

# ✅ 新增日报
@user_passes_test(is_staffbook_admin)
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
@user_passes_test(is_staffbook_admin)
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
@user_passes_test(is_staffbook_admin)
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
@user_passes_test(is_staffbook_admin)
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

# ----- basic -----
# 个人主页+台账
@user_passes_test(is_staffbook_admin)
def driver_basic_info(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    return render(request, 'staffbook/driver_basic_info.html', {
        'driver': driver,
        'main_tab': 'basic',
        'tab': 'basic',
    })

@user_passes_test(is_staffbook_admin)
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
@user_passes_test(is_staffbook_admin)
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

@user_passes_test(is_staffbook_admin)
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
    })

@user_passes_test(is_staffbook_admin)
def driver_certificate_edit(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    return render(request, 'staffbook/driver_certificate_info.html', {
        'driver': driver,
        'main_tab': 'basic',
        'tab': 'certificate',
    })


#履歴変更記録
@user_passes_test(is_staffbook_admin)
def driver_history_info(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    return render(request, 'staffbook/driver_history_info.html', {
        'driver': driver,
        'main_tab': 'basic',
        'tab': 'history',
    })

@user_passes_test(is_staffbook_admin)
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
    driver = get_object_or_404(Driver, pk=driver_id)

    sub_tab = request.GET.get('sub', 'attendance')
    mode    = request.GET.get('mode', 'view')

    # —— 修正版：无论如何都有默认 month_str —— 
    month_str = request.GET.get('month')
    if not month_str:
        today = datetime.date.today()
        month_str = today.strftime('%Y-%m')
    # 现在 month_str 一定是 "YYYY-MM"
    year, mon = map(int, month_str.split('-'))
    start = datetime.date(year, mon, 1)
    if mon == 12:
        end = datetime.date(year + 1, 1, 1)
    else:
        end = datetime.date(year, mon + 1, 1)

    qs = DriverPayrollRecord.objects.filter(
        driver=driver,
        month__gte=start,
        month__lt=end
    ).order_by('-month')

    if mode == 'edit':
        FormSet = modelformset_factory(DriverPayrollRecord, form=DriverPayrollRecordForm, extra=0)
        formset = FormSet(request.POST or None, queryset=qs)
        if request.method == 'POST' and formset.is_valid():
            formset.save()
            return redirect(
                f"{reverse('staffbook:driver_salary', args=[driver.id])}"
                f"?sub={sub_tab}&month={month_str}"
            )
        context = {'formset': formset}
    else:
        context = {'records': qs}

    return render(request, 'staffbook/driver_salary.html', {
        'driver': driver,
        'main_tab': 'salary',
        'tab': 'salary',
        'sub_tab': sub_tab,
        'mode': mode,
        'month': month_str,
        **context,
    })

# ✅ 司机日报
@user_passes_test(is_staffbook_admin)
def driver_dailyreport_month(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
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

    return render(request, 'staffbook/driver_dailyreport_month.html', {
        'driver': driver,
        'reports': reports,
        'selected_month': selected_month,
        'selected_date': selected_date,
    })

# ✅ 管理员新增日报给某员工
@user_passes_test(is_staffbook_admin)
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
@user_passes_test(is_staffbook_admin)
def dailyreport_edit_for_driver(request, driver_id, report_id):
    report = get_object_or_404(DriverDailyReport, pk=report_id, driver_id=driver_id)

    if request.method == 'POST':
        form = DriverDailyReportForm(request.POST, instance=report)
        formset = ReportItemFormSet(request.POST, instance=report)

        if form.is_valid() and formset.is_valid():
            inst = form.save(commit=False)

            print("📝 保存日报：", inst.date)
            print("🕒 clock_in:", inst.clock_in)
            print("🕒 clock_out:", inst.clock_out)
            print("📦 当前状态:", inst.status)

            # ✅ 状态为取消或申请中 + 填写了出退勤 → 自动设为 completed
            if inst.status in ['cancelled', 'pending'] and inst.clock_in and inst.clock_out:
                inst.status = 'completed'
                print("🚦 状态自动变更为 completed")

            # ✅ 如果填写了出退勤 → 去除异常标记
            if inst.clock_in and inst.clock_out:
                inst.has_issue = False

            inst.save()
            formset.instance = inst
            formset.save()

            # ✅ Reservation 同步写入实际出/入库时间
            driver_user = inst.driver.user
            if driver_user and inst.clock_in:
                res = (Reservation.objects
                       .filter(driver=driver_user, date=inst.date)
                       .order_by('start_time')
                       .first())
                print("🔍 查找到 Reservation:", res)

                if res:
                    tz = timezone.get_current_timezone()
                    res.actual_departure = timezone.make_aware(
                        datetime.datetime.combine(inst.date, inst.clock_in), tz
                    )

                    if inst.clock_out:
                        ret_date = inst.date
                        if inst.clock_out < inst.clock_in:
                            ret_date += datetime.timedelta(days=1)
                        res.actual_return = timezone.make_aware(
                            datetime.datetime.combine(ret_date, inst.clock_out), tz
                        )
                        print("✅ 写入 actual_return:", res.actual_return)

                    res.save()

            return redirect('staffbook:dailyreport_overview')

    else:
        initial = {'status': report.status}
        duration = None
        driver_user = report.driver.user

        clock_in = None
        clock_out = None


        if driver_user:
            res = (Reservation.objects
                   .filter(driver=driver_user, date=report.date)
                   .order_by('start_time')
                   .first())
            if res:
                if res.actual_departure:
                    clock_in = timezone.localtime(res.actual_departure).time()
                    initial['clock_in'] = clock_in
                if res.actual_return:
                    clock_out = timezone.localtime(res.actual_return).time()
                    initial['clock_out'] = clock_out

                    # ✅ 自动设置车辆
                if res.vehicle:
                    initial['vehicle'] = res.vehicle

                # ✅ 如果日报本身没有写入 vehicle，强制写入一次
                if not report.vehicle:
                    report.vehicle = res.vehicle
                    report.save()

                    # ✅ 计算总时长（支持跨日）
                if clock_in and clock_out:
                    dt_in = datetime.datetime.combine(report.date, clock_in)
                    dt_out = datetime.datetime.combine(report.date, clock_out)
                    if dt_out <= dt_in:
                        dt_out += datetime.timedelta(days=1)
                    duration = dt_out - dt_in
                    print("🕒 duration =", duration)

        form = DriverDailyReportForm(instance=report, initial=initial)
        formset = ReportItemFormSet(instance=report)


    # 计算各支付方式的原始和分成金额
    rates = {
        'meter':   Decimal('0.9091'),
        'cash':    Decimal('0'),
        'uber':    Decimal('0.05'),
        'didi':    Decimal('0.05'),
        'credit':  Decimal('0.05'),
        'ticket':  Decimal('0.05'),
        'barcode': Decimal('0.05'),
        'wechat':  Decimal('0.05'),
    }
    raw   = {k: Decimal('0') for k in rates}
    split = {k: Decimal('0') for k in rates}

    # 根据请求方法选择数据来源
    data_iter = (
        formset.cleaned_data
        if request.method == 'POST' and formset.is_valid()
        else [f.initial for f in formset.forms]
    )

    for row in data_iter:
        if row.get('DELETE'):
            continue
        amt = row.get('meter_fee') or Decimal('0')
        pay = row.get('payment_method') or ''

        # 累计里程费
        raw['meter']   += amt
        split['meter'] += amt * rates['meter']

        # 累计支付方式
        if pay in ('barcode', 'wechat'):
            raw['barcode']   += amt
            split['barcode'] += amt * rates['barcode']
        elif pay in rates:
            raw[pay]   += amt
            split[pay] += amt * rates[pay]

    # 组合 totals 并添加别名 qr
    totals = {}
    for k in rates:
        totals[f"{k}_raw"]   = raw[k]
        totals[f"{k}_split"] = split[k]
    totals['qr_raw']   = raw['barcode']
    totals['qr_split'] = split['barcode']

    return render(request, 'staffbook/dailyreport_formset.html', {
        'form':      form,
        'formset':   formset,
        'totals':    totals,
        'driver_id': driver_id,
        'report':    report,
        'duration': duration,
    })


# ✅ 司机查看自己日报
@login_required
def my_dailyreports(request):
    reports = DriverDailyReport.objects.filter(driver=request.user).order_by('-date')
    return render(request, 'staffbook/my_dailyreports.html', {'reports': reports})

# ✅ 批量生成账号绑定员工
@user_passes_test(is_staffbook_admin)
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

@user_passes_test(is_staffbook_admin)
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

    # 3. 构建 reports，只按 month 和 keyword 过滤
    reports = DriverDailyReport.objects.filter(
        date__year=month.year,
        date__month=month.month
    )
    if keyword:
        reports = reports.filter(driver__name__icontains=keyword)

    # 4. 全员明细聚合
    items = DriverDailyReportItem.objects.filter(report__in=reports)
    totals = items.aggregate(
        total_meter  = Sum('meter_fee'),
        total_cash   = Sum(Case(When(payment_method='cash',    then=F('meter_fee')), default=0, output_field=DecimalField())),
        total_uber   = Sum(Case(When(payment_method='uber',    then=F('meter_fee')), default=0, output_field=DecimalField())),
        total_didi   = Sum(Case(When(payment_method='didi',    then=F('meter_fee')), default=0, output_field=DecimalField())),
        total_credit = Sum(Case(When(payment_method='credit',  then=F('meter_fee')), default=0, output_field=DecimalField())),
        total_ticket = Sum(Case(When(payment_method='ticket',  then=F('meter_fee')), default=0, output_field=DecimalField())),
        total_qr     = Sum(Case(When(payment_method__in=['barcode','wechat'], then=F('meter_fee')), default=0, output_field=DecimalField())),
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
        'ticket': Decimal('0.05'),
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
        'ticket_split': split('ticket'),
        'qr_split':     split('qr'),
    })

    # 7. 按司机小计 & 分页
    driver_ids = reports.values_list('driver', flat=True).distinct()
    driver_data = []
    for d in Driver.objects.filter(id__in=driver_ids):
        dr_reps = reports.filter(driver=d)
        driver_data.append({
            'driver':    d,
            'total_fee': sum(r.total_meter_fee for r in dr_reps),
            'note':      "⚠️ 異常あり" if dr_reps.filter(has_issue=True).exists() else "",
        })
    page_obj = Paginator(driver_data, 10).get_page(request.GET.get('page'))

    # 8. 渲染
    return render(request, 'staffbook/dailyreport_overview.html', {
        'page_obj':  page_obj,
        'month':     month,
        'month_str': month_str,
        'keyword':   keyword,
        'totals':    totals,
    })