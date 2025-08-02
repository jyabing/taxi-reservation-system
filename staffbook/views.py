import csv, re, datetime

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse
from datetime import timedelta
from django.utils.timezone import make_aware, is_naive
from collections import defaultdict
from carinfo.models import Car
from vehicles.models import Reservation
from django.forms import inlineformset_factory

from .permissions import is_staffbook_admin
from django.contrib import messages
from .forms import (
    DriverForm, DriverPersonalInfoForm, DriverLicenseForm, 
    DriverBasicForm, RewardForm, DriverPayrollRecordForm, DriverCertificateForm
    )

from dailyreport.forms import (
    DriverDailyReportForm, DriverDailyReportItemForm, DriverReportImageForm,
)

from .models import (
    Driver, DrivingExperience, 
    DriverInsurance, FamilyMember, DriverLicense, LicenseType, Qualification, Aptitude,
    Reward, Accident, Education, Pension, DriverPayrollRecord 
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
from dailyreport.services.summary import (
    calculate_totals_from_queryset,
    calculate_totals_from_formset,  # 👈 加上这一行
)

def driver_card(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    return render(request, "staffbook/driver_basic_info.html", {"driver": driver})

@user_passes_test(is_staffbook_admin)
def staffbook_dashboard(request):
    return render(request, 'staffbook/dashboard.html')


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
    DriverInsuranceFormSet = inlineformset_factory(Driver, DriverInsurance, fields="__all__", extra=1, can_delete=True)
    FamilyFormSet = inlineformset_factory(Driver, FamilyMember, fields="__all__", extra=1, can_delete=True)

    if request.method == 'POST':
        form = DriverForm(request.POST, request.FILES, instance=driver)
        exp_formset = DrivingExpFormSet(request.POST, instance=driver)
        ins_formset = DriverInsuranceFormSet(request.POST, instance=driver)
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
        ins_formset = DriverInsuranceFormSet(instance=driver)
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
