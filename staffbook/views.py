import csv, re, datetime
import re
from itertools import zip_longest
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse
from datetime import datetime as DatetimeClass, timedelta, date as _date, datetime as _datetime, datetime as _dt, date 

from django.views.decorators.http import require_http_methods

from django.utils.timezone import make_aware, is_naive
from collections import defaultdict
from carinfo.models import Car
from vehicles.models import Reservation
from django.forms import inlineformset_factory
from dailyreport.models import DriverDailyReport, DriverDailyReportItem
from staffbook.models import Driver  # 你们的司机表

from .permissions import is_staffbook_admin
from django.contrib import messages
from .forms import (
    DriverForm, DriverPersonalInfoForm, DriverLicenseForm, 
    DriverBasicForm, RewardForm, DriverPayrollRecordForm, DriverCertificateForm,
    HistoryEntryForm
    )

from dailyreport.forms import (
    DriverDailyReportForm, DriverDailyReportItemForm, DriverReportImageForm,
)

from .models import (
    Driver, DrivingExperience, 
    DriverInsurance, FamilyMember, DriverLicense, LicenseType, Qualification, Aptitude,
    Reward, Accident, Education, Pension, DriverPayrollRecord,
    DriverSchedule,   # ←← 新增这一行注意：末尾那个逗号要保留，这样排版也一致
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

def is_admin_user(user):
    # "仅允许 is_staff 或 superuser 的用户访问：要么是超级管理员，要么是staff
    return user.is_superuser or user.is_staff

# ===== 売上に基づく分段控除（給与側の規則）BEGIN =====
def calc_progressive_fee_by_table(amount_jpy: int | Decimal) -> int:
    """
    基于你提供的分段表计算扣款。
    入参：不含税売上（円）
    返回：円（整数）

    表规则（单位换算）：
      - 黄色列为「万円」：22.5 → 225,000 円，…，77 → 770,000 円
      - 超过 125,000 円部分，每增加 10,000 円，加 7 万円（= 70,000 円）
    """
    # 阈值单位应为「万円」→ 换算为 円（×10,000）
    THRESHOLDS = [450_000, 550_000, 650_000, 750_000, 850_000, 950_000, 1_050_000, 1_150_000, 1_250_000]
    # 对应累计值（黄色列：万円）
    CUM_VALUES_MAN = [22.5, 28.5, 35, 42, 49, 56, 63, 70, 77]  # 万円
    # 超出 125,000 円后，每 10,000 円的增量：7 万円
    STEP_AFTER_LAST_MAN = 7.0  # 万円 / 1万
    # 单位换算
    MAN_TO_YEN = 10_000        # 万円 → 円
    STEP_SIZE = 10_000         # 每一段宽度（1万）

    amt = int(Decimal(amount_jpy))
    if amt <= 0:
        return 0

    # 阈值内：直接按段取累计值（本表以 1 万为步进，不做更细插值）
    for i, limit in enumerate(THRESHOLDS):
        if amt <= limit:
            return int(round(CUM_VALUES_MAN[i] * MAN_TO_YEN))

    # 超出部分：基数 + 追加段数 * 每段增量
    base_man = CUM_VALUES_MAN[-1]
    extra_steps = (amt - THRESHOLDS[-1]) // STEP_SIZE
    total_man = base_man + extra_steps * STEP_AFTER_LAST_MAN
    return int(round(total_man * MAN_TO_YEN))
# ===== 売上に基づく分段控除（黄色列：万円）END =====

def driver_card(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)
    return render(request, "staffbook/driver_basic_info.html", {"driver": driver})

@user_passes_test(is_staffbook_admin)
def staffbook_dashboard(request):
    return render(request, 'staffbook/dashboard.html')


# ==============================================================
# BEGIN: 司机本人填写“约日期”表单页（桌面=表格，手机=卡片）
# ==============================================================

from django.utils.safestring import mark_safe


@login_required
@require_http_methods(["GET", "POST"])
def schedule_form_view(request):
    """司机本人：提交自己的希望スケジュール"""
    today = date.today()

    # ① 找到这个登录用户对应的司机
    try:
        me = Driver.objects.get(user=request.user)
    except Driver.DoesNotExist:
        me = None

    # ② 当前要看的日期（?work_date=...），没有就看今天
    work_date_str = request.GET.get("work_date") or today.strftime("%Y-%m-%d")
    try:
        y, m, d = [int(x) for x in work_date_str.split("-")]
        work_date = date(y, m, d)
    except Exception:
        work_date = today

    # ③ 这一天，这个司机有没有已经填过
    existing = None
    if me:
        existing = DriverSchedule.objects.filter(driver=me, work_date=work_date).first()

    # ④ 车辆：这里“**不要过滤**”，全部给模板
    #    如果你以后要再限制，再往下挪
    
    raw_cars = (
        Car.objects
        .exclude(
            status__in=["scrapped", "retired", "disabled"],  # 完全不要显示的
            # 如果你模型里有这个字段就保留这行
            # is_scrapped=True,
        )
        .order_by("license_plate", "name", "id")
    )

    normal_cars = []
    maint_cars = []

    for c in raw_cars:
        plate = (
            getattr(c, "license_plate", None)
            or getattr(c, "registration_number", None)
            or ""
        )
        car_name = (
            getattr(c, "name", None)
            or getattr(c, "model", None)
            or ""
        )
        parts = []
        if plate:
            parts.append(str(plate))
        if car_name:
            parts.append(str(car_name))
        base_label = " / ".join(parts) if parts else f"ID:{c.id}"

        status = (getattr(c, "status", "") or "").strip()
        is_active = getattr(c, "is_active", True)
        is_maint  = bool(getattr(c, "is_maintaining", False))
        is_scrapped = bool(getattr(c, "is_scrapped", False))

        # 这里再保险一下：如果真的标了 scrapped，就不要
        if is_scrapped:
            continue

        # 是否属于“整備中”这一类
        is_maint_status = status in ("maintenance", "repair", "fixing") or is_maint

        label = base_label
        bad = False

        if is_maint_status:
            label = f"{base_label}（整備中）"
            bad = True
            c.label = label
            c.is_bad = bad
            maint_cars.append(c)
            continue

        # 走到这里就是“不是整備中”的车
        # 如果它 is_active=False，就不要显示
        if not is_active:
            continue

        # 正常车
        c.label = label
        c.is_bad = False
        normal_cars.append(c)

    # 顺序：正常车在上 + 整備中在下
    cars = normal_cars + maint_cars

    # ⑤ POST 保存
    if request.method == "POST" and me:
        # 同时兼容桌面端与手机端字段名
        mode     = request.POST.get("mode")      or request.POST.get("m-mode")
        shift    = request.POST.get("shift")     or request.POST.get("m-shift") or ""
        note     = request.POST.get("note")      or request.POST.get("m_note")  or ""
        any_car  = (request.POST.get("any_car")  or request.POST.get("m_any_car")) == "1"
        first_id = request.POST.get("first_car") or request.POST.get("m_first_car") or None
        second_id= request.POST.get("second_car")or request.POST.get("m_second_car") or None

        obj, _ = DriverSchedule.objects.get_or_create(
            driver=me,
            work_date=work_date,
        )

        obj.is_rest = (mode == "rest")
        obj.note = note

        if obj.is_rest:
            # 休み
            obj.shift = ""
            obj.any_car = False
            obj.first_choice_car = None
            obj.second_choice_car = None
        else:
            # 希望提出
            obj.shift = shift
            obj.any_car = any_car

            fc = Car.objects.filter(pk=first_id).first() if first_id else None
            sc = Car.objects.filter(pk=second_id).first() if second_id else None

            if fc and sc and fc.id == sc.id:
                sc = None

            obj.first_choice_car = fc
            obj.second_choice_car = sc

        obj.save()
        messages.success(request, "この日のスケジュールを保存しました。")

        # return redirect(f"{request.path}?work_date={work_date:%Y-%m-%d}")
        return redirect("staffbook:my_reservations")

    # ⑥ GET 渲染
    ctx = {
        "driver": me,
        "today": today,
        "work_date": work_date,
        "existing": existing,
        "cars": cars,
    }
    return render(request, "staffbook/schedule_form.html", ctx)
# ==============================================================
# END: 司机本人填写“约日期”表单页（支持保存）
# ==============================================================

# ==============================================================
# 司机本人：看自己最近30天内提交的希望/休み
# ==============================================================
@login_required
def schedule_my_list_view(request):
    """司机本人：看自己最近30天内提交的希望/休み"""
    # 1. 找到这个登录用户对应的司机
    try:
        driver = Driver.objects.get(user=request.user)
    except Driver.DoesNotExist:
        driver = None

    # ✅ 用我们在文件头里导入的名字 _date
    today = _date.today()
    to_date = today + timedelta(days=30)

    rows = []
    if driver:
        rows = (
            DriverSchedule.objects
            .filter(driver=driver, work_date__gte=today, work_date__lte=to_date)
            .order_by("work_date")
        )

    ctx = {
        "driver": driver,
        "rows": rows,
        "today": today,
        "to_date": to_date,
    }
    return redirect("staffbook:my_reservations")


# ==============================================================
# BEGIN: 司机本人查看「我的预约」页面
# ==============================================================

@login_required
def my_reservations_view(request):
    """
    当前登录司机查看自己提交的スケジュール
    """
    try:
        driver = Driver.objects.get(user=request.user)
    except Driver.DoesNotExist:
        driver = None

    today = _date.today()
    # 你模板里要显示 “今天 ~ to_date”
    to_date = today + timedelta(days=14)   # 想 7 天就写 7

    if driver:
        schedules = (
            DriverSchedule.objects
            .filter(driver=driver, work_date__gte=today, work_date__lte=to_date)
            .order_by("work_date", "-created_at")
        )
    else:
        schedules = []

    ctx = {
        "driver": driver,
        "today": today,
        "to_date": to_date,   # 👈 模板要的
        "schedules": schedules,
    }
    return render(request, "staffbook/my_reservations.html", ctx)

# ==============================================================
# END: 司机本人查看「我的预约」页面
# ==============================================================

# ==============================================================
# 管理员 / 事务员：查看所有司机提交的“日期+希望车両”
# URL: /staffbook/schedule-list/
# 模板: staffbook/schedule_list.html
# ==============================================================

@login_required
@user_passes_test(is_admin_user)   # 只允许 超管 or staff
def schedule_list_view(request):
    """
    管理者用：全ドライバーの提出スケジュールを見る＆更新する
    GET パラメータ:
      ?group=date|driver
      ?driver=123
      ?work_date=2025-11-03
    """
    today = _date.today()
    # 看今天到一周后（你想扩大就改这里）
    date_from = today
    date_to = today + timedelta(days=7)

    group = request.GET.get("group", "date")      # 按日期 / 按司机
    driver_id = request.GET.get("driver")         # 司机过滤
    work_date_str = request.GET.get("work_date")  # 指定日期过滤

    # ① 这一段时间内的全部司机提交
    qs = (
        DriverSchedule.objects
        .select_related("driver", "first_choice_car", "second_choice_car", "assigned_car")
        .filter(work_date__gte=date_from, work_date__lte=date_to)
    )

    # ② 如果指定了日，就再缩
    selected_work_date = None
    if work_date_str:
        try:
            selected_work_date = _date.fromisoformat(work_date_str)
            qs = qs.filter(work_date=selected_work_date)
        except ValueError:
            selected_work_date = None

    # ③ 如果指定了司机，也再缩
    if driver_id:
        qs = qs.filter(driver_id=driver_id)

    
    # 下拉用的车（正常在上，整備中在下；廃車/停用不出）
    raw_cars = (
        Car.objects
        .exclude(status__in=["scrapped", "retired", "disabled"])  # 廃車・退役・停用は出さない
        .order_by("license_plate", "name", "id")
    )

    normal_cars, maint_cars = [], []

    for c in raw_cars:
        plate = (
            getattr(c, "license_plate", None)
            or getattr(c, "registration_number", None)
            or ""
        )
        car_name = (
            getattr(c, "name", None)
            or getattr(c, "model", None)
            or ""
        )
        parts = []
        if plate:
            parts.append(str(plate))
        if car_name:
            parts.append(str(car_name))
        base_label = " / ".join(parts) if parts else f"ID:{c.id}"

        status = (getattr(c, "status", "") or "").strip()
        is_active = getattr(c, "is_active", True)
        is_maint  = bool(getattr(c, "is_maintaining", False))
        is_scrapped = bool(getattr(c, "is_scrapped", False))

        if is_scrapped:
            continue  # 保险再滤一次

        is_maint_status = status in ("maintenance", "repair", "fixing") or is_maint

        if is_maint_status:
            c.label = f"{base_label}（整備中）"
            c.is_bad = True
            maint_cars.append(c)
            continue

        if not is_active:
            continue

        c.label = base_label
        c.is_bad = False
        normal_cars.append(c)

    cars = normal_cars + maint_cars
    
    # 下拉司机 / 日期
    all_drivers = Driver.objects.order_by("driver_code", "name")
    date_choices = [date_from + timedelta(days=i) for i in range((date_to - date_from).days + 1)]

    # ④ 行内保存
    if request.method == "POST":
        sched_id = request.POST.get("sched_id")
        status = request.POST.get("status") or "pending"
        assigned_car_id = request.POST.get("assigned_car") or None
        admin_note = request.POST.get("admin_note", "").strip()

        # 把过滤条件也拿回来，保存后还回到同一筛选
        post_group = request.POST.get("group", group)
        post_driver = request.POST.get("driver") or driver_id
        post_work_date = request.POST.get("work_date") or work_date_str

        obj = DriverSchedule.objects.filter(pk=sched_id).first()
        if obj:
            obj.status = status
            obj.admin_note = admin_note
            if assigned_car_id:
                obj.assigned_car_id = assigned_car_id
            else:
                obj.assigned_car = None
            obj.save()
            messages.success(request, "スケジュールを更新しました。")

        # 回跳 URL
        redirect_url = f"{reverse('staffbook:schedule_list')}?group={post_group}"
        if post_driver:
            redirect_url += f"&driver={post_driver}"
        if post_work_date:
            redirect_url += f"&work_date={post_work_date}"
        return redirect(redirect_url)

    # ⑤ 分组显示（表格）
    grouped = {}
    if group == "driver":
        qs = qs.order_by("driver__driver_code", "work_date")
        for row in qs:
            key = f"{row.driver.driver_code} {row.driver.name}"
            grouped.setdefault(key, []).append(row)
    else:
        group = "date"
        qs = qs.order_by("work_date", "driver__driver_code")
        for row in qs:
            key = row.work_date
            grouped.setdefault(key, []).append(row)

    # ⑥ 只读配车表（就是你要的那个绿色牌子）
    dispatch_sections = []
    if selected_work_date:
        # 1) 这一天真正有记录的（注意这里要用 qs，不是 schedules）
        day_qs = qs.filter(work_date=selected_work_date)

        assigned_rows = []
        used_car_ids = set()

        for s in day_qs:
            car = s.assigned_car or None
            if car:
                used_car_ids.add(car.id)

            assigned_rows.append({
                "car": car,
                "driver": s.driver,
                "is_rest": s.is_rest,
                "shift": s.shift,
                "admin_note": s.admin_note,
                "driver_note": s.note,
            })

        if assigned_rows:
            dispatch_sections.append({
                "title": "本日の配車",
                "rows": assigned_rows,
            })

        # 2) 把“这一天没用到的车”塞进去，再分成 “整備中/修理中” 和 “空き車両”
        maint_rows = []
        free_rows = []
        for car in cars:
            status = getattr(car, "status", "")
            is_scrapped = getattr(car, "is_scrapped", False)
            is_active = getattr(car, "is_active", True)

            # 报废/不可用直接跳过
            if is_scrapped:
                continue
            if status in ("retired", "disabled", "scrapped"):
                continue
            if not is_active:
                continue

            # 今天已经分配过的，跳过
            if car.id in used_car_ids:
                continue

            # 是否维修中
            is_maint = False
            if status in ("maintenance", "repair", "fixing"):
                is_maint = True
            if getattr(car, "is_maintaining", False):
                is_maint = True

            row = {
                "car": car,
                "driver": None,
                "is_rest": False,
                "shift": None,
                "admin_note": "",
                "driver_note": "",
            }

            if is_maint:
                maint_rows.append(row)
            else:
                free_rows.append(row)

        if maint_rows:
            dispatch_sections.append({
                "title": "整備中 / 修理中",
                "rows": maint_rows,
            })

        if free_rows:
            dispatch_sections.append({
                "title": "空き車両",
                "rows": free_rows,
            })

    # ⑦ 渲染
    ctx = {
        "date_from": date_from,
        "date_to": date_to,
        "group": group,
        "grouped": grouped,
        "cars": cars,
        "all_drivers": all_drivers,
        "date_choices": date_choices,
        "selected_driver": int(driver_id) if driver_id else None,
        "selected_work_date": selected_work_date,
        "dispatch_sections": dispatch_sections,
    }
    return render(request, "staffbook/schedule_list.html", ctx)

# ======= staffbook/views.py 替换结束 =======

# ==============================================================
# END: 管理员 / 事务员：查看所有司机提交的“日期+希望车両”
# ==============================================================


@login_required
def schedule_delete_view(request, sched_id):
    """
    司机本人删除自己的提交（POST）
    """
    try:
        me = Driver.objects.get(user=request.user)
    except Driver.DoesNotExist:
        me = None

    sched = get_object_or_404(DriverSchedule, pk=sched_id)

    # 只能删自己的
    if not me or sched.driver_id != me.id:
        messages.error(request, "このスケジュールを削除する権限がありません。")
        return redirect("staffbook:my_reservations")  # 或你想回的页面

    if request.method == "POST":
        wd = sched.work_date
        sched.delete()
        messages.success(request, f"{wd:%Y-%m-%d} のスケジュールを削除しました。")

    return redirect("staffbook:my_reservations")  # 你的确认页 url 名称


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

    d = driver
    is_foreign = getattr(d, "is_foreign", False)  # 外国籍の人は在留カード/就労資格を判定

    missing_items = []
    edit_url = reverse('staffbook:driver_basic_edit', args=[driver.id])

    if driver.is_foreign:
        if not driver.residence_card_image:
            missing_items.append(("在留カード未上传", f"{edit_url}#residence-card"))
        if not driver.work_permission_confirmed:
            missing_items.append(("就労資格未確認", f"{edit_url}#work-permission"))

    if not driver.has_health_check:
        missing_items.append(("健康診断書未提出", f"{edit_url}#health-check"))
    if not driver.has_residence_certificate:
        missing_items.append(("住民票未提出", f"{edit_url}#juminhyo"))
    if not driver.has_license_copy:
        missing_items.append(("免許証コピー未提出", f"{edit_url}#license-copy"))

    # ====== 入社資料デフォルト清单（公司側）======
    # ⛳ 请确认右侧 getattr(...) 中的布尔字段与你的 Driver 模型一致
    company_docs = [
        {"name": "雇用契約書の作成・署名",      "submitted": getattr(d, "signed_employment_contract", False),         "anchor": "company-1"},
        {"name": "労働条件通知書の交付",        "submitted": getattr(d, "gave_labor_conditions", False),               "anchor": "company-2"},
        {"name": "就業規則・安全衛生の説明",    "submitted": getattr(d, "explained_rules_safety", False),              "anchor": "company-3"},
        {"name": "社会保険・厚生年金加入手続",  "submitted": getattr(d, "completed_social_insurance", False),          "anchor": "company-4"},
        {"name": "雇用保険加入手続",            "submitted": getattr(d, "completed_employment_insurance", False),      "anchor": "company-5"},
        {"name": "労災保険手続",                "submitted": getattr(d, "completed_worker_accident_insurance", False), "anchor": "company-6"},
        {"name": "厚生年金基金手続",            "submitted": getattr(d, "completed_pension_fund", False),              "anchor": "company-7"},
        {"name": "社内システムID発行",          "submitted": getattr(d, "created_system_account", False),              "anchor": "company-8"},
        {"name": "研修・マニュアルの周知",       "submitted": getattr(d, "notified_training_manual", False),            "anchor": "company-9"},
        {"name": "経費・交通費申請フロー説明",  "submitted": getattr(d, "explained_expense_flow", False),              "anchor": "company-10"},
    ]

    # ====== 入社資料デフォルト清单（社員側）======
    employee_docs = [
        {"name": "履歴書・職務経歴書",                          "submitted": getattr(d, "has_resume", False),               "anchor": "employee-1"},
        {"name": "運転免許証コピー",                            "submitted": getattr(d, "has_license_copy", False),         "anchor": "employee-2"},
        {"name": "住民票（本籍地記載・マイナンバーなし）",      "submitted": getattr(d, "has_residence_certificate", False), "anchor": "employee-3"},
        {"name": "健康診断書",                                  "submitted": getattr(d, "has_health_check", False),         "anchor": "employee-4"},
        {"name": "給与振込先口座情報",                          "submitted": getattr(d, "has_bank_info", False),            "anchor": "employee-5"},
        {"name": "マイナンバー（番号は保存しない・提出のみ）",  "submitted": getattr(d, "has_my_number_submitted", False),  "anchor": "employee-6"},
        {"name": "雇用保険被保険者証",                          "submitted": getattr(d, "has_koyo_hihokenshasho", False),   "anchor": "employee-7"},
        {"name": "年金手帳／基礎年金番号届出（番号保存なし）",  "submitted": getattr(d, "has_pension_proof", False),        "anchor": "employee-8"},
        # 外国籍のみ：対象外であれば “提出済み扱い” にして未提出に出さない
        {"name": "就労資格確認（外国籍のみ）",                   "submitted": (not is_foreign) or getattr(d, "work_permission_confirmed", False), "anchor": "employee-9"},
        {"name": "在留カード（外国籍のみ）",                     "submitted": (not is_foreign) or getattr(d, "has_zairyu_card", False),            "anchor": "employee-10"},
        {"name": "在留カード画像のアップロード（外国籍のみ）",   "submitted": (not is_foreign) or bool(getattr(d, "residence_card_image", None)),  "anchor": "employee-11"},
    ]

    # —— 生成编辑页链接（用于 ❌ 跳转）——
    edit_url = reverse('staffbook:driver_basic_edit', args=[driver.id])

    # —— 左右两列对齐行（模板遍历 paired_rows 渲染）——
    paired_rows = list(
        zip_longest(
            company_docs,
            employee_docs,
            fillvalue={"name": "", "submitted": None, "anchor": ""}
        )
    )

    # —— 未提出清单（用于详情页上方的黄色提示框）——
    missing_items = []
    for item in company_docs:
        if item["submitted"] is False:
            missing_items.append((item["name"], f"{edit_url}#{item['anchor']}"))
    for item in employee_docs:
        if item["submitted"] is False:
            missing_items.append((item["name"], f"{edit_url}#{item['anchor']}"))

    return render(request, 'staffbook/driver_basic_info.html', {
        'driver': driver,
        'paired_rows': paired_rows,
        'edit_url': edit_url,
        'main_tab': 'basic',
        'tab': 'basic',
        'missing_items': missing_items,
    })

@user_passes_test(is_staffbook_admin)
def driver_basic_edit(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)

    if request.method == 'POST':
        print('DEBUG POST employ_type =', request.POST.get('employ_type'))
        print('DEBUG POST resigned_date =', request.POST.get('resigned_date'))
        form = DriverBasicForm(request.POST, request.FILES, instance=driver)
        if form.is_valid():
            obj = form.save()
            print('DEBUG SAVED resigned_date =', obj.resigned_date)
            messages.success(request, "基本データを保存しました。")
            return redirect('staffbook:driver_basic_info', driver_id=driver.id)
        else:
            print("[DEBUG] DriverBasicForm errors:", form.errors)
            messages.error(request, "入力内容をご確認ください。")
    else:
        form = DriverBasicForm(instance=driver)

    # === 入社資料 清单（布尔字段快速版）========================
    # 用 getattr 避免字段尚未创建时报 AttributeError
    d = driver
    employee_docs = [
        {"name": "履歴書・職務経歴書", "submitted": getattr(d, "has_resume", False)},
        {"name": "運転免許証コピー", "submitted": getattr(d, "has_license_copy", False)},
        {"name": "住民票（本籍地記載・マイナンバーなし）", "submitted": getattr(d, "has_juminhyo", False)},
        {"name": "健康診断書", "submitted": getattr(d, "has_health_check", False)},
        {"name": "給与振込先口座情報", "submitted": getattr(d, "has_bank_info", False)},
        {"name": "マイナンバー（番号は保存しない・提出のみ）", "submitted": getattr(d, "has_my_number_submitted", False)},
        {"name": "雇用保険被保険者証", "submitted": getattr(d, "has_koyo_hihokenshasho", False)},
        {"name": "年金手帳/基礎年金番号の届出（番号保存なし）", "submitted": getattr(d, "has_pension_proof", False)},
        {"name": "在留カード（外国籍）", "submitted": getattr(d, "has_zairyu_card", False)},
    ]
    company_docs = [
        {"name": "入社資料一式交付", "submitted": getattr(d, "gave_joining_pack", False)},
        {"name": "社会保険・年金加入手続", "submitted": getattr(d, "completed_social_insurance", False)},
        {"name": "雇用契約書 締結", "submitted": getattr(d, "signed_employment_contract", False)},
        {"name": "就業規則・安全衛生 説明", "submitted": getattr(d, "explained_rules_safety", False)},
        {"name": "社内システムID 発行", "submitted": getattr(d, "created_system_account", False)},
        {"name": "研修/マニュアル 周知", "submitted": getattr(d, "notified_training_manual", False)},
        {"name": "経費/交通費 申請説明", "submitted": getattr(d, "explained_expense_flow", False)},
    ]
    # （可选）业務用
    ops_docs = [
        {"name": "Uber アカウント", "submitted": getattr(d, "has_uber_account", False)},
        {"name": "DiDi アカウント", "submitted": getattr(d, "has_didi_account", False)},
        {"name": "社名章/名札 交付", "submitted": getattr(d, "has_company_name_tag", False)},
        {"name": "配車システム アカウント", "submitted": getattr(d, "has_dispatch_account", False)},
    ]
    # ==========================================================

    return render(request, 'staffbook/driver_basic_edit.html', {
        'form': form,
        'driver': driver,
        'main_tab': 'basic',
        'tab': 'basic',
        'employee_docs': employee_docs,
        'company_docs': company_docs,
        'ops_docs': ops_docs,      # 模板用了再显示；没用就无视
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


@user_passes_test(is_staffbook_admin)
def driver_history_info(request, driver_id):
    """
    履歴查看页：从 Driver.history_data(JSONField) 读取并只读展示
    """
    driver = get_object_or_404(Driver, pk=driver_id)
    data = driver.history_data or {}
    education = data.get("education", [])
    jobs = data.get("jobs", [])
    return render(request, "staffbook/driver_history_info.html", {
        "driver": driver,
        "education": education,
        "jobs": jobs,
        "tab": "history",   # 二级tab高亮
    })

#履歴変更記録
@user_passes_test(is_staffbook_admin)
def driver_history_edit(request, driver_id):
    driver = get_object_or_404(Driver, pk=driver_id)

    def _load_lists():
        data = driver.history_data or {}
        return data.get("education", []), data.get("jobs", [])

    education, jobs = _load_lists()

    if request.method == "POST":
        errors = []

        def collect(prefix):
            """
            收集前端提交的某一类行（edu 或 job）
            - 兼容中间索引被删除的“空洞”（不再用 while 连续自增）
            - 后端强制补充 category，避免前端缺失导致表单校验失败
            """
            # 找到本类行里所有 index（根据 -place 键）
            indices = sorted({
                int(k.split("-")[1])
                for k in request.POST.keys()
                if k.startswith(f"{prefix}-") and k.endswith("-place")
            })

            rows = []
            for idx in indices:
                data = {
                    "category": "edu" if prefix == "edu" else "job",  # ✅ 关键：后端补上
                    "start_year":  request.POST.get(f"{prefix}-{idx}-start_year"),
                    "start_month": request.POST.get(f"{prefix}-{idx}-start_month"),
                    "end_year":    request.POST.get(f"{prefix}-{idx}-end_year"),
                    "end_month":   request.POST.get(f"{prefix}-{idx}-end_month"),
                    "place":       request.POST.get(f"{prefix}-{idx}-place") or "",
                    "note":        request.POST.get(f"{prefix}-{idx}-note") or "",
                }

                form = HistoryEntryForm(data)
                if form.is_valid():
                    c = form.cleaned_data

                    def ym(y, m):
                        if not y or not m:
                            return ""
                        return f"{int(y):04d}-{int(m):02d}"

                    rows.append({
                        "start": ym(c["start_year"], c["start_month"]),
                        "end":   ym(c.get("end_year"), c.get("end_month")),
                        "place": c["place"],
                        "note":  c.get("note", ""),
                    })
                else:
                    # 记录错误，最后统一提示
                    errors.append((prefix, idx, form.errors))
            return rows

        education = collect("edu")
        jobs      = collect("job")

        if errors:
            messages.error(request, "请检查输入项。")
            # 带回成功解析的行（有错的行因为无效，不再带回）
            return render(request, "staffbook/driver_history_edit.html", {
                "driver": driver,
                "education": education,
                "jobs": jobs,
                "post_errors": errors,
            })

        # ✅ 全部合法：写回 JSONField
        driver.history_data = {"education": education, "jobs": jobs}
        driver.save()
        messages.success(request, "履歴書已保存。")
        return redirect("staffbook:driver_history_info", driver_id=driver.id)

    # GET：渲染
    return render(request, "staffbook/driver_history_edit.html", {
        "driver": driver,
        "education": education,
        "jobs": jobs,
    })
# === 替换结束 ===


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






