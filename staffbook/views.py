import csv, re, datetime
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse
from datetime import timedelta
from collections import defaultdict
from carinfo.models import Car
from vehicles.models import Reservation

from .permissions import is_staffbook_admin
from django.contrib import messages
from .forms import (
    DriverDailyReportForm, DriverForm, 
    ReportItemFormSet, DriverPersonalInfoForm, DriverLicenseForm, 
    DriverBasicForm, RewardForm, DriverPayrollRecordForm, DriverCertificateForm
    )
from .models import (
    DriverDailyReport, DriverDailyReportItem, Driver, DrivingExperience, 
    Insurance, FamilyMember, DriverLicense, LicenseType, Qualification, Aptitude,
    Reward, Accident, Education, Insurance, Pension, DriverPayrollRecord 
    )
from django.db.models import Q, Sum, Case, When, F, DecimalField
from django.forms import inlineformset_factory, modelformset_factory
from django.utils import timezone
from django import forms

from calendar import monthrange
from django.utils.timezone import now
from django.core.paginator import Paginator
from django.urls import reverse
from decimal import Decimal, ROUND_HALF_UP

from accounts.utils import check_module_permission
from staffbook.utils import (
    calculate_totals_from_queryset,
    calculate_totals_from_formset,  # 👈 加上这一行
)

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
    return render(request, 'staffbook/driver_dailyreport_edit.html', {'form': form})

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
    return render(request, 'staffbook/driver_dailyreport_edit.html', {'form': form})

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

    # ✅ 新增：检查缺失项
    missing_items = []

    if driver.is_foreign:
        if not driver.residence_card_image:
            missing_items.append(("在留カード未上传", f"/staffbook/drivers/{driver.id}/certificate/"))
        if not driver.work_permission_confirmed:
            missing_items.append(("就労資格未確認", f"/staffbook/drivers/{driver.id}/certificate/"))

    if not driver.has_health_check:
        missing_items.append(("健康診断書未提出", f"/staffbook/drivers/{driver.id}/certificate/"))
    if not driver.has_residence_certificate:
        missing_items.append(("住民票未提出", f"/staffbook/drivers/{driver.id}/certificate/"))
    if not driver.has_license_copy:
        missing_items.append(("免許証コピー未提出", f"/staffbook/drivers/{driver.id}/certificate/"))

    return render(request, 'staffbook/driver_basic_info.html', {
        'driver': driver,
        'main_tab': 'basic',
        'tab': 'basic',
        'missing_items': missing_items,  # ✅ 新增 context
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

@user_passes_test(is_staffbook_admin)
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

        return redirect("staffbook:driver_dailyreport_edit", driver_id=driver.id, report_id=report.id)

    # ✅ 渲染模板
    return render(request, "staffbook/driver_dailyreport_add.html", {
        "driver": driver,
        "current_month": display_date.strftime("%Y年%m月"),
        "year": display_date.year,
        "month": display_date.month,
        "calendar_dates": calendar_dates,
    })

@user_passes_test(is_staffbook_admin)
def dailyreport_add_by_month(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)

    month_str = request.GET.get("month")  # 格式："2025-03"
    if not month_str:
        return redirect("staffbook:driver_dailyreport_add_selector", driver_id=driver_id)

    try:
        year, month = map(int, month_str.split("-"))
        # 校验是否是合法月份
        assert 1 <= month <= 12
    except (ValueError, AssertionError):
        return redirect("staffbook:driver_dailyreport_add_selector", driver_id=driver_id)

    current_month = f"{year}年{month}月"

    return render(request, "staffbook/dailyreport_add_month.html", {
        "driver": driver,
        "year": year,
        "month": month,
        "current_month": current_month,
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
            return redirect('staffbook:driver_basic_info', driver_id=driver.id)
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
        ('omron', 'オムロン'),
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

    return render(request, 'staffbook/driver_dailyreport_edit.html', {
        'form': report_form,
        'formset': formset,
        'driver': driver,
        'is_edit': False,
        'summary_keys': summary_keys,
        'totals': totals,
    })

# ✅ 编辑日报（管理员）
@user_passes_test(is_staffbook_admin)
def dailyreport_edit_for_driver(request, driver_id, report_id):
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
            return redirect('staffbook:driver_dailyreport_month', driver_id=driver_id)
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

    return render(request, 'staffbook/driver_dailyreport_edit.html', {
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

@user_passes_test(is_staffbook_admin)
def driver_dailyreport_add_unassigned(request):
    driver_id = request.GET.get("driver_id")
    if not driver_id:
        messages.warning(request, "未选择员工，无法添加日报。")
        return redirect("staffbook:dailyreport_overview")

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

    return redirect("staffbook:driver_dailyreport_edit", driver_id=driver.id, report_id=report.id)


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
    driver_qs = Driver.objects.all()
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
    return render(request, 'staffbook/dailyreport_overview.html', {
        'page_obj':  page_obj,
        'month':     month,
        'month_str': month_str,
        'keyword':   keyword,
        'totals_all':    totals_all,
        'summary_keys':  summary_keys,
    })
    
@user_passes_test(is_staffbook_admin)
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
        '従業員（コード）', '空車', 'ETC', '楽券', '子機料',
        'Uber売上', 'クレジット売上', 'DIDI売上', 'PayPay売上',
        'オムロン売上', '京交信市他売上', '水揚合計',
        'ガソリン', '里程KM', '煙草', '返金不足'
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
