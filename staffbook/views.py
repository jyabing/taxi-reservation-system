# views.py 头部（替换你文件开头到第一个 def 之前的所有内容）

import csv, re, datetime
from decimal import Decimal, ROUND_HALF_UP
from collections import defaultdict
from calendar import monthrange

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import HttpResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.timezone import now, make_aware, is_naive
from django.db.models import Q, Sum, Case, When, F, DecimalField
from django.forms import inlineformset_factory, modelformset_factory

from carinfo.models import Car
from vehicles.models import Reservation
from dailyreport.models import DriverDailyReport, DriverDailyReportItem

from .permissions import is_staffbook_admin

# ---------- 只引入“工厂”而不是直接引入表单类 ----------
# 这一步是关键：避免 app 加载时循环依赖，解决
# “Cannot create form field for 'company' … related model 'staffbook.Company' has not been loaded yet”
from .forms import (
    DriverFormFactory,
    DriverPersonalInfoFormFactory,
    DriverLicenseFormFactory,
    DriverBasicEditFormFactory,
    RewardFormFactory,
    DriverPayrollRecordFormFactory,
    DriverCertificateFormFactory,
    AccidentFormFactory,
)

# ---------- 在 app 全部加载完成后，统一实例化一次 ----------
# 用原来的名字导出，后面的视图完全不用改
DriverForm              = DriverFormFactory()
DriverPersonalInfoForm  = DriverPersonalInfoFormFactory()
DriverLicenseForm       = DriverLicenseFormFactory()
DriverBasicEditForm     = DriverBasicEditFormFactory()
RewardForm              = RewardFormFactory()
DriverPayrollRecordForm = DriverPayrollRecordFormFactory()
DriverCertificateForm   = DriverCertificateFormFactory()
AccidentForm            = AccidentFormFactory()

# ---------- 模型 ----------
from .models import (
    Driver, DrivingExperience,
    DriverInsurance, FamilyMember, DriverLicense, LicenseType,
    Qualification, Aptitude, Reward, Accident, Education,
    Pension, DriverPayrollRecord
)

# ===== 売上に基づく分段控除（給与側の規則）BEGIN =====
def calc_progressive_fee_by_table(amount_jpy: int | Decimal) -> int:
    """
    基于分段表计算扣款。入参：不含税売上（円） -> 返回：円（整数）
    """
    THRESHOLDS = [450_000, 550_000, 650_000, 750_000, 850_000, 950_000, 1_050_000, 1_150_000, 1_250_000]
    CUM_VALUES_MAN = [22.5, 28.5, 35, 42, 49, 56, 63, 70, 77]  # 万円
    STEP_AFTER_LAST_MAN = 7.0  # 万円 / 1万
    MAN_TO_YEN = 10_000
    STEP_SIZE = 10_000

    amt = int(Decimal(amount_jpy))
    if amt <= 0:
        return 0
    for i, limit in enumerate(THRESHOLDS):
        if amt <= limit:
            return int(round(CUM_VALUES_MAN[i] * MAN_TO_YEN))
    base_man = CUM_VALUES_MAN[-1]
    extra_steps = (amt - THRESHOLDS[-1]) // STEP_SIZE
    total_man = base_man + extra_steps * STEP_AFTER_LAST_MAN
    return int(round(total_man * MAN_TO_YEN))
# ===== 売上に基づく分段控除 END =====


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
    from .forms import DriverForm
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
    from .forms import DriverBasicEditForm
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
    from .forms import DriverBasicEditForm
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
    from .forms import DriverBasicEditForm
    driver = get_object_or_404(Driver, pk=driver_id)

    # 用不含 driver_code 的表单
    form = DriverBasicEditForm(request.POST or None, request.FILES or None, instance=driver)

    companies   = Company.objects.order_by("name")
    workplaces  = Workplace.objects.order_by("company", "name")

    # 选中值（POST 优先 → 实例值兜底），字符串化便于模板比较
    selected_company_id   = str(request.POST.get("company")   or driver.company or "")
    selected_workplace_id = str(request.POST.get("workplace") or driver.workplace or "")
    selected_employ_type  = str(request.POST.get("employ_type") or driver.employ_type or "")

    # 固定下拉（你之前页面在用）
    NATIONALITY_CHOICES = ["日本", "中国", "韓国", "ベトナム", "その他"]
    GENDER_CHOICES      = [("男性","男性"), ("女性","女性"), ("未設定","未設定")]
    BLOOD_CHOICES       = [("A","A"), ("B","B"), ("AB","AB"), ("O","O")]

    # 这些从模型 choices 读取，防止写死
    employ_type_choices   = list(form.fields['employ_type'].choices)   # 在職類型
    driver_position_choices = list(form.fields['position'].choices)    # 職種

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "基本データを保存しました。")
        return redirect('staffbook:driver_basic_info', driver_id=driver.id)

    return render(request, 'staffbook/driver_basic_edit.html', {
        'form': form,
        'driver': driver,

        'companies': companies,
        'workplaces': workplaces,
        'selected_company_id': selected_company_id,
        'selected_workplace_id': selected_workplace_id,

        'nationality_choices': NATIONALITY_CHOICES,
        'gender_choices': GENDER_CHOICES,
        'blood_choices': BLOOD_CHOICES,

        'employ_type_choices': employ_type_choices,
        'driver_position_choices': driver_position_choices,
        'selected_employ_type': selected_employ_type,

        'main_tab': 'basic',
        'tab': 'basic',
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
    from .forms import DriverBasicEditForm
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
    from .forms import DriverBasicEditForm
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
    from .forms import DriverBasicEditForm
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
    from .forms import DriverLicenseForm
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
    from .forms import QualificationForm
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
    from .forms import AptitudeForm
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
    from .forms import RewardForm
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
    from .forms import AccidentForm
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
    #import datetime as _dt  # ← 加这一行，确保本函数总能拿到“模块”
    """
    給与情報：勤怠 / 支給 / 控除
    - 上部情報：売上対象月(前月)・当月売上(不含税)・分段控除
    - 控除タブ：progressive_fee を只読表示。保存時は当月レコードへ強制反映（Model.save() 側の合計再計算を起動）
    - edit モード：sub パラメータに応じて該当フィールドのみレンダリング
    """
    driver = get_object_or_404(Driver, pk=driver_id)

    # -------- URL パラメータ --------
    sub_tab   = request.GET.get('sub', 'attendance')   # attendance / payment / deduction
    mode      = request.GET.get('mode', 'view')        # view / edit
    month_str = request.GET.get('month')               # YYYY-MM

    # 勤怠タブは常に只読（URLで mode=edit を指定されても無効化）
    if sub_tab == 'attendance':
        mode = 'view'

    # -------- 給与月の期間 --------
    if not month_str:
        today = datetime.date.today()
        month_str = today.strftime('%Y-%m')
    year, mon = map(int, month_str.split('-'))

    start = datetime.date(year, mon, 1)
    end   = datetime.date(year + (1 if mon == 12 else 0), 1 if mon == 12 else mon + 1, 1)

    # -------- 売上対象月（前月） --------
    if mon == 1:
        sales_year, sales_mon = year - 1, 12
    else:
        sales_year, sales_mon = year, mon - 1
    sales_start = datetime.date(sales_year, sales_mon, 1)
    sales_end   = datetime.date(sales_year + (1 if sales_mon == 12 else 0),
                                1 if sales_mon == 12 else sales_mon + 1, 1)
    sales_month_str = f"{sales_year:04d}-{sales_mon:02d}"

    # -------- 集計：不含税売上 & 分段控除 --------
    monthly_sales_excl_tax = Decimal('0')
    progressive_fee_value  = 0
    try:
        items_qs = DriverDailyReportItem.objects.filter(
            report__driver=driver,
            report__date__gte=sales_start,
            report__date__lt=sales_end,
        )
        meter_sum   = items_qs.aggregate(s=Sum('meter_fee'))['s'] or 0
        charter_sum = items_qs.filter(is_charter=True).aggregate(s=Sum('charter_amount_jpy'))['s'] or 0
        gross_incl_tax = Decimal(meter_sum) + Decimal(charter_sum)

        TAX_DIVISOR = Decimal("1.10")  # 如果原始就是不含税，可改为 1.0
        monthly_sales_excl_tax = (gross_incl_tax / TAX_DIVISOR).quantize(Decimal('1'), rounding=ROUND_HALF_UP)

        # 你的分段控除函数
        progressive_fee_value  = calc_progressive_fee_by_table(monthly_sales_excl_tax)
    except Exception as e:
        print(f"[WARN] 売上集計に失敗: {e}")

    # -------- 当月の給与レコード --------
    qs = DriverPayrollRecord.objects.filter(
        driver=driver,
        month__gte=start,
        month__lt=end
    ).order_by('-month')

    # edit で当月レコードがない場合は 1 行作って編集可能にする
    if mode == 'edit' and not qs.exists():
        DriverPayrollRecord.objects.get_or_create(driver=driver, month=start)
        qs = DriverPayrollRecord.objects.filter(driver=driver, month__gte=start, month__lt=end)

    # -------- タブごとのフィールド --------
    fields_by_tab = {
        'attendance': [
            'attendance_days', 'absence_days',
            'holiday_work_days', 'paid_leave_days',
            'overtime_hours', 'night_hours', 'holiday_hours',
            'total_working_hours'
        ],
        'payment': [
            'basic_pay', 'overtime_allowance', 'night_allowance',
            'holiday_allowance', 'commute_allowance', 'bonus',
            'other_allowances', 'special_allowance',
            'transportation_allowance', 'total_pay'
        ],
        'deduction': [
            'health_insurance_deduction', 'health_care_insurance_deduction',
            'pension_deduction', 'employment_insurance_deduction',
            'workers_insurance_deduction', 'income_tax_deduction',
            'resident_tax_deduction', 'tax_total',
            'progressive_fee', 'other_deductions',
            'total_deductions', 'net_pay'
        ],
    }
    fields = fields_by_tab.get(sub_tab, [])

    # ======== 編集モード ========
    if mode == 'edit':
        FormSet = modelformset_factory(
            DriverPayrollRecord,
            form=DriverPayrollRecordForm,
            fields=fields,
            extra=0
        )
        formset = FormSet(request.POST or None, queryset=qs)

        # 控除タブ：progressive_fee 页面上禁改（保存时由后端覆盖）
        if sub_tab == 'deduction':
            for f in formset.forms:
                if 'progressive_fee' in f.fields:
                    f.fields['progressive_fee'].disabled = True

        if request.method == 'POST':
            if formset.is_valid():
                formset.save()

                # 保存后把分段控除 + 出勤日数 强制写回当月记录（触发模型合计）
                try:
                    # —— 出勤日数：当月“有至少一条日报明细”的日期数 —— 
                    attendance_days_count = (
                        DriverDailyReportItem.objects
                        .filter(
                            report__driver=driver,
                            report__date__gte=start,   # 当月起
                            report__date__lt=end       # 次月起（半开区间）
                        )
                        .values('report__date').distinct().count()
                    )

                    # —— 固定天数（默认=当月工作日 Mon–Fri；若你有公司“固定天数”字段，替换这里即可）——
                    from datetime import timedelta
                    base_days = sum(
                        1 for i in range((end - start).days)
                        if (start + timedelta(days=i)).weekday() < 5
                    )

                    for rec in DriverPayrollRecord.objects.filter(driver=driver, month__gte=start, month__lt=end):
                        rec.progressive_fee  = Decimal(str(progressive_fee_value))
                        rec.attendance_days  = attendance_days_count

                        # 缺勤日 = 固定天数 − 出勤 − 有給（不足取 0）
                        paid = rec.paid_leave_days or 0
                        rec.absence_days = max(base_days - attendance_days_count - paid, 0)

                        rec.save()
                except Exception as e:
                    print(f"[WARN] progressive_fee auto-save failed: {e}")

                messages.success(request, "保存しました。")
                return redirect(
                    f"{reverse('staffbook:driver_salary', args=[driver.id])}"
                    f"?sub={sub_tab}&month={month_str}&mode=view"
                )

        context = {'formset': formset}

    # ======== 只読モード（ここに“勤怠集計”が入っています） ========
    else:
        def _yen(x) -> int:
            return int(Decimal(x).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

        # ---- 時間外割増 1~4 の合計（残業手当の元）----
        c = Decimal(monthly_sales_excl_tax)  # 当月売上（不含税）
        o1 = _yen(min(Decimal("225000"), c / Decimal("2")))
        o2 = _yen(Decimal("60000") if c > Decimal("550000")
                  else max(Decimal("0"), (c - Decimal("450000")) * Decimal("0.6")))
        o3 = _yen(Decimal("65000") if c > Decimal("650000")
                  else max(Decimal("0"), (c - Decimal("550000")) * Decimal("0.65")))
        o4 = _yen((c - Decimal("650000")) * Decimal("0.7")) if c > Decimal("650000") else 0
        overtime_calc_sum = o1 + o2 + o3 + o4

        # ========= 这里是你要的“前后都保留”的勤怠统计块（开始） =========

        records = list(qs)

        # 头表（日报 Header）与明细（Item）
        header_qs = DriverDailyReport.objects.filter(
            driver=driver, date__gte=start, date__lt=end
        )
        items_qs = DriverDailyReportItem.objects.filter(
            report__driver=driver, report__date__gte=start, report__date__lt=end
        )

        # 出勤日数（来自日报明细）
        attendance_days = items_qs.values('report__date').distinct().count()
        attendance_days_from_reports = attendance_days

        # —— 固定天数（默认=当月工作日 Mon–Fri；如有公司固定天数字段，可替换这里）——
        from datetime import timedelta
        base_days = sum(
            1 for i in range((end - start).days)
            if (start + timedelta(days=i)).weekday() < 5
        )

        # —— 工具函数：把各种“时间/时长表示”转成十进制小时（不依赖 datetime 类型判断，避免再次报错）——
        def hours_value(v: object) -> Decimal:
            """任意输入 → 十进制小时。支持 timedelta-like、数字、'HH:MM(:SS)' 字符串。"""
            if v is None:
                return Decimal('0')
            # timedelta-like（有 total_seconds 方法）
            if hasattr(v, 'total_seconds') and callable(getattr(v, 'total_seconds', None)):
                return (Decimal(v.total_seconds()) / Decimal('3600')).quantize(Decimal('0.00'))
            # 纯数字
            if isinstance(v, (int, float, Decimal)):
                return Decimal(str(v))
            # "HH:MM(:SS)" 字符串
            s = str(v).strip()
            if ':' in s:
                try:
                    hh, mm, *ss = s.split(':')
                    sec = ss[0] if ss else '0'
                    return (Decimal(hh or '0')
                            + Decimal(mm or '0')/Decimal('60')
                            + Decimal(sec or '0')/Decimal('3600')).quantize(Decimal('0.00'))
                except Exception:
                    return Decimal('0')
            # 兜底：按数字字符串解析
            try:
                return Decimal(s)
            except Exception:
                return Decimal('0')

        def to_sec(t: object) -> int:
            """把 time/datetime/'HH:MM(:SS)'/十进制小时 转成 秒；不使用 isinstance(datetime.*)。"""
            # datetime-like：有 .time() 方法
            try:
                if hasattr(t, 'time') and callable(getattr(t, 'time', None)):
                    tt = t.time()
                else:
                    tt = t
                # time-like：有 hour/minute 属性
                if hasattr(tt, 'hour') and hasattr(tt, 'minute'):
                    sec = getattr(tt, 'second', 0) or 0
                    return int(tt.hour) * 3600 + int(tt.minute) * 60 + int(sec)
            except Exception:
                pass
            # "HH:MM(:SS)"
            s = str(t).strip()
            if ':' in s:
                parts = s.split(':')
                try:
                    h = int(parts[0] or 0)
                    m = int(parts[1] or 0)
                    sec = int(parts[2] or 0) if len(parts) > 2 else 0
                    return h*3600 + m*60 + sec
                except Exception:
                    return 0
            # 兜底：若是“十进制小时”数字，转成秒
            try:
                hours = Decimal(str(t))
                return int(hours * Decimal('3600'))
            except Exception:
                return 0

        def first_attr(obj, names):
            for nm in names:
                if hasattr(obj, nm):
                    v = getattr(obj, nm)
                    if v not in (None, ''):
                        return v
            return None

        def hours_from_times(h) -> Decimal:
            """若头表有上/下班时刻 + 休憩，推导実働小时。"""
            st = first_attr(h, ('start_time','duty_start','clock_in','on_duty_time','work_start'))
            et = first_attr(h, ('end_time','duty_end','clock_out','off_duty_time','work_end'))
            if not st or not et:
                return Decimal('0')

            ssec, esec = to_sec(st), to_sec(et)
            if esec < ssec:  # 跨零点
                esec += 24*3600
            hours = Decimal(esec - ssec) / Decimal('3600')

            # 扣休憩（分钟或小时）
            br_min = first_attr(h, ('break_minutes','rest_minutes','break_time_minutes'))
            br_hr  = first_attr(h, ('break_hours','rest_hours','break_time_hours'))
            if br_min is not None:
                hours -= Decimal(str(br_min))/Decimal('60')
            elif br_hr is not None:
                hours -= Decimal(str(br_hr))
            return hours if hours > 0 else Decimal('0')

        # —— 先从“头表字段”取実働/残業；缺失再退回“明细行字段”；还不行就用时刻推导 —— #
        sum_actual = Decimal('0')  # 実働时间（小时）
        sum_ot     = Decimal('0')  # 残業时间（小时）

        if header_qs.exists():
            for h in header_qs:
                # 実働
                v_act = first_attr(h, (
                    'actual_working_hours','total_working_hours','working_hours',
                    'actual_hours','actual_work_time','work_hours','real_working_hours',
                ))
                sum_actual += hours_value(v_act) if v_act is not None else hours_from_times(h)
                # 残業
                v_ot = first_attr(h, ('overtime_hours','total_overtime_hours','ot_hours','overtime'))
                if v_ot is not None:
                    sum_ot += hours_value(v_ot)
                else:
                    v_ot_min = first_attr(h, ('overtime_minutes','ot_minutes','overtime_time_minutes'))
                    if v_ot_min is not None:
                        sum_ot += Decimal(str(v_ot_min))/Decimal('60')
        else:
            # 退回明细行累加
            def sum_rows(qs, hour_fields, minute_fields=()):
                total = Decimal('0')
                for it in qs:
                    picked = False
                    for f in hour_fields:
                        if hasattr(it, f):
                            total += hours_value(getattr(it, f))
                            picked = True
                            break
                    if not picked:
                        for f in minute_fields:
                            if hasattr(it, f):
                                total += Decimal(str(getattr(it, f)))/Decimal('60')
                                break
                return total

            sum_actual = sum_rows(
                items_qs,
                ('actual_working_hours','working_hours','work_hours','actual_hours','actual_work_time'),
                ('actual_minutes','working_minutes','work_minutes','actual_work_minutes')
            )
            sum_ot = sum_rows(
                items_qs,
                ('overtime_hours','overtime_time','overtime','ot_hours','total_overtime_hours'),
                ('overtime_minutes','ot_minutes','overtime_time_minutes')
            )

        # 保留两位小数（模板显示 0.00）
        sum_actual = sum_actual.quantize(Decimal('0.00'))
        sum_ot     = sum_ot.quantize(Decimal('0.00'))
        # === 勤怠集計（替换块结束） ===

        # 把结果写入每条记录（同时覆盖 view_* 与同名原字段）
        for r in records:
            r.view_attendance_days     = attendance_days
            r.view_total_working_hours = sum_actual
            r.view_overtime_hours      = sum_ot
            r.attendance_days          = attendance_days
            r.total_working_hours      = sum_actual
            r.overtime_hours           = sum_ot

            # —— 缺勤日（显示/存储口径一致）——
            paid = getattr(r, 'paid_leave_days', 0) or 0
            r.view_absence_days = max(base_days - attendance_days - paid, 0)
            r.absence_days      = r.view_absence_days

            # 残業手当（显示用）
            r.view_overtime_allowance = overtime_calc_sum

            # 総支給額（显示用）
            pieces = [
                r.basic_pay or 0,
                overtime_calc_sum,
                r.night_allowance or 0,
                r.holiday_allowance or 0,
                r.commute_allowance or 0,
                r.bonus or 0,
                r.other_allowances or 0,
                r.special_allowance or 0,
                r.transportation_allowance or 0,
            ]
            r.view_total_pay = _yen(sum(Decimal(p) for p in pieces))

            # 控除页“合計”条
            def _to_dec(x): return Decimal(x or 0)
            social_ins_total = (
                _to_dec(r.health_insurance_deduction)
                + _to_dec(r.health_care_insurance_deduction)
                + _to_dec(r.pension_deduction)
                + _to_dec(r.employment_insurance_deduction)
                + _to_dec(r.workers_insurance_deduction)
            )
            total_pay_for_tax = _to_dec(getattr(r, 'view_total_pay', None) or r.total_pay)
            non_taxable = _to_dec(r.commute_allowance) + _to_dec(r.transportation_allowance)
            taxable_amount = total_pay_for_tax - non_taxable - social_ins_total
            if taxable_amount < 0:
                taxable_amount = Decimal('0')
            cash_payment = Decimal('0')  # 现现金额暂定 0
            net_pay = _to_dec(r.net_pay)
            bank_transfer = net_pay - cash_payment
            r.view_summary = {
                "social_ins_total": int(social_ins_total),
                "taxable_amount":   int(taxable_amount),
                "bank_transfer":    int(bank_transfer),
                "cash_payment":     int(cash_payment),
                "net_pay":          int(net_pay),
            }
        # ========= 这里是你要的“前后都保留”的勤怠统计块（结束） =========

        context = {'records': records}

    # -------- レンダリング --------
    return render(request, 'staffbook/driver_salary.html', {
        'driver': driver,
        'main_tab': 'salary',
        'tab': 'salary',
        'sub_tab': sub_tab,
        'mode': mode,
        'month': month_str,

        # 上部情報バー
        'sales_month_str': sales_month_str,
        'monthly_sales_excl_tax': int(monthly_sales_excl_tax),
        'progressive_fee': int(progressive_fee_value),

        **context,
    })