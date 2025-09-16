import calendar, requests, random, os, json
from calendar import monthrange
from datetime import date, datetime, timedelta, time as dtime
from .models import (
    Reservation,
    ReservationStatus,
    Tip,
    Car as Vehicle,
    SystemNotice,
)
from collections import defaultdict
from dailyreport.views import _totals_of

from django import forms
from decimal import Decimal, ROUND_HALF_UP
from accounts.utils import check_module_permission

from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponseRedirect, HttpResponseForbidden, HttpResponse
from django.utils import timezone
from django.urls import reverse
from django.utils.timezone import now, make_aware, localdate, is_naive
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models.functions import Cast
from django.db.models import TimeField, F, Q
from django.db import transaction
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.conf import settings
from django.core.paginator import Paginator
from django.core.mail import send_mail
from dateutil.relativedelta import relativedelta

from carinfo.services.car_access import (
    get_all_active_cars,
    is_car_reservable,
    get_car_by_id,
    is_under_repair,
    is_retired,
    is_admin_only,  # ✅ 没问题了
)

from django.db.models import F, ExpressionWrapper, DurationField, Sum
from django.views.decorators.csrf import csrf_exempt
from carinfo.models import Car

from .models import Reservation, Tip, Car
from .forms import MonthForm, AdminStatsForm, ReservationForm,  VehicleStatusForm, VehicleNoteForm
from accounts.models import DriverUser
from requests.exceptions import RequestException
from vehicles.utils import notify_driver_reservation_approved, send_notification

# 导入 Driver/DriverDailyReport（已确保在 staffbook 里定义！）
from dailyreport.models import Driver, DriverDailyReport, DriverDailyReportItem
from vehicles.models import Reservation, Tip
from vehicles.forms import VehicleNoteForm
from staffbook.models import Driver

# ✅ 邮件通知工具
from vehicles.utils import notify_admin_about_new_reservation

def is_vehicles_admin(user):
    return user.is_authenticated and (user.is_superuser or getattr(user.userprofile, 'is_vehicles_admin', False))

# 装饰器：限制仅 vehicles 管理员或超级管理员访问
require_vehicles_admin = user_passes_test(is_vehicles_admin)

# 所有 view 里的权限装饰器如下修改方式：
# 1. 超级管理员或 vehiclesvehicles_admin 才能访问的页面：@login_required + @require_vehicle_admin
# 2. 司机/所有用户都能访问的页面：@login_required

# ✅ 示例：
# @login_required
# @require_vehicle_admin
# def admin_stats_view(request):
#     return render(request, 'vehicles/admin_stats.html')

# 后续你只需要在已有函数前加上这个装饰器组合，并统一模板路径写为 'vehicles/xxx.html' 即可。

def _parse_dt_local(s: str):
    """把 datetime-local(YYYY-MM-DDTHH:MM) 解析成服务器时区的 aware datetime。"""
    if not s:
        return None
    dt = None
    try:
        # '2025-09-03T18:00'
        dt = datetime.fromisoformat(s)
    except Exception:
        dt = parse_datetime(s)
    if not dt:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


@login_required
def recent_reservations_view(request, car_id):
    car = get_object_or_404(Car, id=car_id)

    recent_reservations = (
        Reservation.objects
        .filter(vehicle=car)
        .order_by("-start_datetime")[:5]
    )

    return render(request, "vehicles/recent_reservations.html", {
        "car": car,
        "recent_reservations": recent_reservations,
    })

def get_status_text(vehicle, status_info):
    """
    返回车辆状态文本（带图标），优先使用车辆本身的数据库字段 status。
    """
    print(f"🚨 调试输出：{vehicle.license_plate} 的 vehicle.status = {vehicle.status}")

    # 车辆自身状态优先
    if vehicle.status == 'repair':
        return '🔧 维修中'
    elif vehicle.status == 'retired':
        return '🚫 已报废'
    elif vehicle.status not in ['usable', 'repair', 'retired']:
        return f'❓ 未知状态（值为 {vehicle.status}）'

    # 预约状态（status_info['status'] 用的是字符串）
    status = status_info.get('status', '')

    if status == 'available':
        return '🟥 可预约（点击预约）'
    elif status == 'booked':
        return '🟦 有预约（未出库）'
    elif status == 'out':
        return '🟩 出库中'
    elif status == 'overdue':
        return '⏰ 超时未归还'
    elif status == 'expired':
        return '📅 已过期'

    return '<span class="text-muted">—</span>'
    
@login_required
def vehicle_list(request):
    vehicles = get_all_active_cars()
    return render(request, 'vehicles/vehicle_list.html', {'vehicles': vehicles})

@login_required
def vehicle_detail(request, vehicle_id):
    vehicle = get_object_or_404(Car.objects.prefetch_related('images'), pk=vehicle_id)
    reservations = Reservation.objects.filter(vehicle=vehicle).order_by('-date')[:5]

    return render(request, 'vehicles/vehicle_detail.html', {
        'vehicle': vehicle,
        'reservations': reservations,
        'is_retired': is_retired(vehicle),
        'is_under_repair': is_under_repair(vehicle),
        'is_admin_only': is_admin_only(vehicle),
    })

    
@login_required
def vehicle_status_view(request):
    selected_date_str = request.GET.get('date')
    selected_date = datetime.strptime(selected_date_str, "%Y-%m-%d").date() if selected_date_str else localdate()
    now = timezone.localtime()
    now_dt = now

    current_driver = Driver.objects.filter(user=request.user).first()

    reservations = Reservation.objects.filter(
        date__lte=selected_date,
        end_date__gte=selected_date
    ).select_related('driver', 'vehicle')

    driver_today_vehicle_id = None
    if current_driver:
        today_reservation = reservations.filter(
            driver=request.user,
            date__lte=selected_date,
            end_date__gte=selected_date,
            actual_return__isnull=True,
            status__in=[ReservationStatus.BOOKED, ReservationStatus.OUT]
        ).order_by('start_datetime').first()
        if today_reservation:
            driver_today_vehicle_id = today_reservation.vehicle_id

    vehicles = get_all_active_cars()
    status_map = {}

    for vehicle in vehicles:
        res_list = reservations.filter(vehicle=vehicle).order_by('start_datetime')

        seen_reservation_ids = set()
        res_list_deduped = []
        for r in res_list:
            if not r.driver or r.id in seen_reservation_ids:
                continue
            if selected_date < r.date or selected_date > r.end_date:
                continue
            seen_reservation_ids.add(r.id)
            res_list_deduped.append(r)

        # 默认状态
        if selected_date < localdate():
            status = 'expired'
        else:
            status = 'available'

        # 有出库中的记录
        if res_list.filter(status=ReservationStatus.OUT, actual_departure__isnull=False, actual_return__isnull=True).exists():
            status = 'out'
        # 超时未归还
        elif res_list.filter(status=ReservationStatus.OUT, end_datetime__lt=now_dt, actual_return__isnull=True).exists():
            status = 'overdue'
        else:
            # 未出库但已预约
            future_booked = res_list.filter(status=ReservationStatus.BOOKED, actual_departure__isnull=True)
            for r in future_booked:
                start_dt = r.start_datetime
                expire_dt = start_dt + timedelta(hours=1)
                if now_dt > expire_dt:
                    r.status = 'cancel'
                    r.save()
                    if current_driver and r.driver_id == current_driver.id:
                        messages.warning(request, f"你对 {vehicle.license_plate} 的预约因超时未出库已被自动取消，请重新预约。")
                else:
                    status = 'booked'
                    break

        # 当前用户在该车的可操作预约（用于出入库按钮）
        user_reservation = None
        for r in res_list:
            if not current_driver or r.driver_id != current_driver.id:
                continue
            if r.status not in ['booked', 'out']:
                continue
            if r.actual_return:
                continue
            if r.end_datetime < now_dt:
                continue
            user_reservation = r
            break

        # 标签
        reserver_labels = []
        seen_res_ids = set()
        for r in res_list_deduped:
            if r.status not in ['booked', 'out'] or not r.driver:
                continue
            if r.id in seen_res_ids or r.date != selected_date:
                continue
            seen_res_ids.add(r.id)
            label = (
                f"{datetime.combine(r.date, r.start_time).strftime('%H:%M')}~"
                f"{datetime.combine(r.end_date, r.end_time).strftime('%H:%M')} "
                f"{getattr(r.driver, 'display_name', (r.driver.first_name or '') + ' ' + (r.driver.last_name or '')).strip()}"
            )
            reserver_labels.append(label)

        reserver_name = '<br>'.join(reserver_labels) if reserver_labels else ''
        is_repair = vehicle.status == 'repair'
        reservable = is_car_reservable(vehicle)

        # 今天的当前预约（优先 out，其次 booked）
        current_reservation = None
        for r in res_list_deduped:
            if r.date == selected_date and r.status == ReservationStatus.OUT:
                current_reservation = r
                break
        if not current_reservation:
            for r in res_list_deduped:
                if r.date == selected_date and r.status == ReservationStatus.BOOKED:
                    current_reservation = r
                    break

        status_info = {
            'status': status,                      # 'available'/'booked'/'out'/...
            'reservation': current_reservation,
            'user_reservation': user_reservation,
            'reserver_name': reserver_name,
            'reservable': reservable,
            'has_reservation': bool(reserver_labels),
            'click_reservation': False,
            'is_repair': is_repair,
        }

        status_info['status_text'] = get_status_text(vehicle, status_info)
        status_map[vehicle] = status_info

    if not any(info['status'] == 'available' for info in status_map.values()):
        messages.warning(request, "当前车辆状态不可预约，请选择其他车辆")

    vehicle_forms = {}
    note_forms = {}
    for vehicle in status_map.keys():
        vehicle.refresh_from_db()
        vehicle_forms[vehicle.id] = VehicleStatusForm(instance=vehicle, prefix=f"car_{vehicle.id}")
        note_forms[vehicle.id] = VehicleNoteForm(instance=vehicle)

    return render(request, 'vehicles/status_view.html', {
        'selected_date': selected_date,
        'status_map': status_map,
        'today': localdate(),
        'now': now,
        'vehicle_forms': vehicle_forms,
        'note_forms': note_forms,
        'request_driver_id': current_driver.id if current_driver else None,
        'driver_today_vehicle_id': driver_today_vehicle_id,
    })

@login_required
def reserve_vehicle_view(request, car_id):
    car = get_car_by_id(car_id)
    min_time = (timezone.now() + timedelta(minutes=30)).strftime('%Y-%m-%dT%H:%M')

    # 禁止不可预约车辆
    if not is_car_reservable(car):
        messages.error(request, "该车辆当前状态不可预约。")
        return redirect('vehicles:vehicle_status')

    if car.is_reserved_only_by_admin and not request.user.is_staff:
        messages.error(request, "该车辆为调配用车，仅限管理员预约。")
        return redirect('vehicles:vehicle_status')

    if request.method == 'POST':
        form = ReservationForm(request.POST)
        form.instance.driver = request.user
        selected_dates_raw = request.POST.get('selected_dates', '')
        selected_dates = json.loads(selected_dates_raw) if selected_dates_raw else []

        # Flatpickr 日期偏移修正
        selected_dates = [
            (datetime.strptime(d, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
            for d in selected_dates
        ]

        if form.is_valid() and selected_dates:
            cleaned = form.cleaned_data
            start_time = cleaned['start_time']
            end_time = cleaned['end_time']
            purpose = cleaned['purpose']

            created_count = 0

            for date_str in selected_dates:
                try:
                    start_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    start_dt = datetime.combine(start_date, start_time)

                    # 跨日判断
                    if end_time <= start_time:
                        end_date = start_date + timedelta(days=1)
                    else:
                        end_date = start_date
                    end_dt = datetime.combine(end_date, end_time)

                    # 限制：最长 13 小时
                    duration_hours = (end_dt - start_dt).total_seconds() / 3600
                    if duration_hours > 13:
                        messages.error(request, f"⚠️ {start_date} 的预约时间为 {duration_hours:.1f} 小时，超过限制。")
                        continue

                    # 夜班限制（可选）
                    if end_date > start_date:
                        if start_time < dtime(12, 0) or end_time > dtime(12, 0):
                            messages.error(request, f"⚠️ {start_date} 的跨日预约时间段非法。夜班必须 12:00 后开始，次日 12:00 前结束。")
                            continue

                    # 重复预约（当前用户，同车，同时间段，检查有效状态）
                    duplicate_by_same_user = Reservation.objects.filter(
                        vehicle=car,
                        driver=request.user,
                        date__lte=end_dt.date(),
                        end_date__gte=start_dt.date(),
                        status__in=[ReservationStatus.PENDING, ReservationStatus.BOOKED, ReservationStatus.OUT],
                    ).filter(
                        Q(start_time__lt=end_time) & Q(end_time__gt=start_time)
                    ).exists()
                    if duplicate_by_same_user:
                        messages.warning(request, f"{start_date} 你已预约该车，已跳过。")
                        continue

                    # 10 小时间隔（同车、同用户）
                    recent_same_vehicle_reservations = Reservation.objects.filter(
                        vehicle=car,
                        driver=request.user,
                    ).only('date', 'start_time').order_by('-date', '-start_time')

                    too_close = False
                    for prev in recent_same_vehicle_reservations:
                        prev_start_dt = datetime.combine(prev.date, prev.start_time)
                        if abs((start_dt - prev_start_dt).total_seconds()) < 36000:
                            too_close = True
                            break
                    if too_close:
                        messages.warning(request, f"⚠️ {start_date} 的预约时间与之前预约相隔不足10小时，已跳过。")
                        continue

                    # 与其他人冲突
                    conflict_exists = Reservation.objects.filter(
                        vehicle=car,
                        date__lte=end_dt.date(),
                        end_date__gte=start_dt.date(),
                        status__in=[ReservationStatus.BOOKED, ReservationStatus.OUT],
                    ).filter(
                        Q(start_time__lt=end_time) & Q(end_time__gt=start_time)
                    ).exclude(driver=request.user).exists()
                    if conflict_exists:
                        messages.warning(request, f"{start_date} 存在预约冲突，已跳过。")
                        continue

                    # 创建预约（默认 PENDING）
                    new_res = Reservation.objects.create(
                        driver=request.user,
                        vehicle=car,
                        date=start_date,
                        end_date=end_date,
                        start_time=start_time,
                        end_time=end_time,
                        purpose=purpose,
                        status=ReservationStatus.PENDING,
                    )

                    created_count += 1

                    # 通知（略）
                    subject = "【新预约通知】车辆预约提交"
                    plain_message = (
                        f"预约人：{request.user.get_full_name() or request.user.username}\n"
                        f"车辆：{car.license_plate}（{getattr(car, 'model', '未登记型号')}）\n"
                        f"日期：{start_date} ~ {end_date}  {start_time} - {end_time}\n"
                        f"用途：{purpose}"
                    )
                    html_message = f"""
                    <p>有新的车辆预约提交：</p>
                    <ul>
                        <li><strong>预约人：</strong> {request.user.get_full_name() or request.user.username}</li>
                        <li><strong>车辆：</strong> {car.license_plate}（{getattr(car, 'model', '未登记型号')}）</li>
                        <li><strong>日期：</strong> {start_date} ~ {end_date}</li>
                        <li><strong>时间：</strong> {start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}</li>
                        <li><strong>用途：</strong> {purpose}</li>
                    </ul>
                    """
                    send_notification(subject, plain_message, ['jiabing.msn@gmail.com'], html_message)

                    print(f"✅ 创建成功: {car.license_plate} @ {start_dt} ~ {end_dt}")

                except ValueError as e:
                    print(f"❌ 日期转换错误: {e}")
                    continue

            if created_count > 0:
                messages.success(request, f"✅ 已成功预约 {created_count} 天！")
            else:
                messages.warning(request, "⚠️ 没有成功预约任何日期，请检查冲突或重复预约情况。")

            return redirect('vehicles:vehicle_status')

        else:
            messages.error(request, "请填写所有字段，并选择预约日期（最多7天）")

    else:
        initial = {
            'start_time': request.GET.get('start', ''),
            'end_time': request.GET.get('end', ''),
            'purpose': request.GET.get('purpose', ''),
        }
        form = ReservationForm(initial={**initial, 'driver': request.user})

    return render(request, 'vehicles/reserve_vehicle.html', {
        'vehicle': car,
        'form': form,
        'min_time': min_time,
    })


@login_required
def vehicle_timeline_view(request, vehicle_id):
    date_str = request.GET.get('date')
    if date_str:
        selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    else:
        selected_date = timezone.localdate()
    # 1. 获取当前时间
    now = timezone.localtime()
    is_today = selected_date == timezone.localdate()
    is_past = is_today and timezone.localtime().time() > dtime(0, 30)
    # 0:30之后不允许新预约

    vehicle = get_object_or_404(Car, id=vehicle_id)
    reservations = Reservation.objects.filter(vehicle=vehicle, date=selected_date).order_by('start_time')
    
    return render(request, 'vehicles/timeline_view.html', {
        'vehicle': vehicle,
        'selected_date': selected_date,
        'reservations': reservations,
        'is_past': is_past,  # ✅ 传入模板
        'hours': range(24),  # ✅ 加上这行
    })

@login_required
def weekly_overview_view(request):
    today = timezone.localdate()
    now_dt = timezone.localtime()
    now_time = now_dt.time()

    date_str = request.GET.get('date')
    offset = int(request.GET.get('offset', 0))

    if date_str:
        try:
            base_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            base_date = today
    else:
        base_date = today

    start_date = base_date + timedelta(days=offset * 7)
    week_dates = [start_date + timedelta(days=i) for i in range(7)]

    vehicles = get_all_active_cars()
    for v in vehicles:
        status_val = getattr(v, "status", None)
        v.is_maintenance = (status_val in ("repair", "maintenance", "under_maintenance")) or is_under_repair(v)

    global_reminders = []
    for car in vehicles:
        fields = [
            ('inspection_date', '车辆检査'),
            ('insurance_expiry', '保险'),
            ('mandatory_insurance_expiry', '强制保险'),
            ('lease_expiry', '租赁合约'),
        ]
        for field, label in fields:
            due_date = getattr(car, field, None)
            if due_date:
                reminder_text = get_due_reminder(due_date, label)
                if reminder_text:
                    global_reminders.append((car, reminder_text))

    reservations = Reservation.objects.filter(
        Q(date__in=week_dates)
    ).select_related('vehicle', 'driver')

    # 自动取消超时未出库（BOOKED→过期 1h → CANCEL）
    canceled = []
    for r in reservations.filter(status=ReservationStatus.BOOKED, actual_departure__isnull=True):
        start_dt = make_aware(datetime.combine(r.date, r.start_time))
        if timezone.now() > start_dt + timedelta(hours=1):
            r.status = 'cancel'
            r.save()
            if r.driver == request.user:
                canceled.append(r)

    if canceled:
        messages.warning(request, f"你有 {len(canceled)} 条预约因超过1小时未出库已被自动取消，请重新预约。")

    user_res_today = reservations.filter(
        driver=request.user,
        date=today,
        status__in=[ReservationStatus.BOOKED, ReservationStatus.OUT]
    )
    cooldown_end = None
    if user_res_today.exists():
        last = user_res_today.order_by('-end_date', '-end_time').first()
        end_dt = datetime.combine(last.end_date, last.end_time)
        cooldown_end = end_dt + timedelta(hours=10)

    vehicle_date_map = defaultdict(lambda: defaultdict(list))
    for res in reservations:
        if res.date in week_dates:
            vehicle_date_map[res.vehicle][res.date].append(res)

    data = []
    for vehicle in vehicles:
        vehicle.daily_reminders = {}

        for d in week_dates:
            daily_reminders = []
            fields = [
                ('inspection_date', 'inspection', '车辆检査'),
                ('insurance_expiry', 'insurance', '保险'),
                ('mandatory_insurance_expiry', 'mandatory_insurance', '强制保险'),
                ('lease_expiry', 'lease', '租赁合约'),
            ]
            for field, rtype, label in fields:
                due_date = getattr(vehicle, field, None)
                if isinstance(due_date, date):
                    delta = (d - due_date).days
                    if -5 <= delta <= 5:
                        if delta < 0:
                            msg = f"{-delta}天后{label}到期，请协助事务完成{label}更新"
                        elif delta == 0:
                            msg = f"今天{label}到期，请协助事务完成{label}更新"
                        else:
                            msg = f"{label}到期延迟{delta}天，请协助事务完成{label}更新"
                        daily_reminders.append({'type': rtype, 'message': msg, 'is_today': (delta == 0)})
            if daily_reminders:
                vehicle.daily_reminders[d] = daily_reminders

        row = {'vehicle': vehicle, 'days': []}
        for d in week_dates:
            day_reservations = sorted(vehicle_date_map[vehicle][d], key=lambda r: r.start_time)

            if request.user.is_staff:
                is_past = False
            else:
                if d < today:
                    is_past = True
                elif d == today and now_time < dtime(hour=0, minute=30):
                    is_past = True
                else:
                    is_past = False

            row['days'].append({
                'date': d,
                'reservations': day_reservations,
                'is_past': is_past,
                'is_maintenance': vehicle.is_maintenance,
            })

        vehicle_reminders = []
        if vehicle.inspection_date:
            delta = (vehicle.inspection_date - today).days
            if -5 <= delta <= 5:
                vehicle_reminders.append({'type': 'inspection', 'message': f"车检日 {vehicle.inspection_date} 距今 {delta} 天", 'is_today': delta == 0})
        if getattr(vehicle, 'insurance_end_date', None):
            delta = (vehicle.insurance_end_date - today).days
            if -5 <= delta <= 5:
                vehicle_reminders.append({'type': 'insurance', 'message': f"保险到期日 {vehicle.insurance_end_date} 距今 {delta} 天", 'is_today': delta == 0})

        row['reminders'] = vehicle_reminders
        data.append(row)

    return render(request, 'vehicles/weekly_view.html', {
        'week_dates': week_dates,
        'vehicle_data': data,
        'offset': offset,
        'now_dt': now_dt,
        'now_time': now_time,
        'cooldown_end': cooldown_end,
        'today': base_date,
        'selected_date': date_str if date_str else today.strftime("%Y-%m-%d"),
        'reminders': global_reminders,
    })
    
@login_required
def timeline_selector_view(request):
    vehicles = get_all_active_cars()

    if request.method == 'POST':
        vehicle_id = request.POST.get('vehicle_id')
        date = request.POST.get('date')
        return HttpResponseRedirect(f"/vehicles/timeline/{vehicle_id}/?date={date}")

    return render(request, 'vehicles/timeline_selector.html', {
        'vehicles': vehicles,
    })

@login_required
def weekly_selector_view(request):
    vehicles = get_all_active_cars()  # ✅ 排除报废、维修中等不可预约车辆

    if request.method == 'POST':
        date = request.POST.get('date')
        return redirect(f"/vehicles/weekly/?start={date}")

    return render(request, 'vehicles/weekly_selector.html', {
        'vehicles': vehicles
    })

@login_required
def vehicle_monthly_gantt_view(request, vehicle_id):
    vehicle = get_object_or_404(Car, id=vehicle_id)

    # 1. 读取当前月份参数或默认今天
    month_str = request.GET.get('date')  # 例：2025-05
    if month_str:
        try:
            year, month = map(int, month_str.split('-'))
        except ValueError:
            today = timezone.localdate()
            year, month = today.year, today.month
    else:
        today = timezone.localdate()
        year, month = today.year, today.month

    # 2. 获取当月第一天、上下月跳转
    current_month = date(year, month, 1)
    prev_month = (current_month - timedelta(days=1)).replace(day=1)
    next_month = (current_month + timedelta(days=32)).replace(day=1)
    days_in_month = monthrange(year, month)[1]

    matrix = []
    now = timezone.localtime()

    for day in range(1, days_in_month + 1):
        d = date(year, month, day)
        is_past = make_aware(datetime.combine(d, time.max)) < now

        # 获取本日涉及的预约（包含跨日的）
        reservations = Reservation.objects.filter(
            vehicle=vehicle,
            date__lte=d,
            end_date__gte=d,
            status__in=[ReservationStatus.PENDING, ReservationStatus.BOOKED, ReservationStatus.OUT]
        ).order_by('start_time')

        segments = []
        for r in reservations:
            start_dt = max(datetime.combine(r.date, r.start_time), datetime.combine(d, time.min))
            end_dt = min(datetime.combine(r.end_date, r.end_time), datetime.combine(d, time.max))

            start_offset = max((start_dt - datetime.combine(d, time.min)).total_seconds() / 3600, 0)
            end_offset = min((end_dt - datetime.combine(d, time.min)).total_seconds() / 3600, 24)
            length = max(end_offset - start_offset, 0.1)  # 避免 0 长度

            if length > 0:
                segments.append({
                    'start': start_offset,
                    'length': length,
                    'status': r.status,
                    'label': f"{r.driver.username} {r.start_time.strftime('%H:%M')}-{r.end_time.strftime('%H:%M')}"
                })

        # 非管理员不可预约过去
        if request.user.is_staff:
            is_past = False
        elif d < today:
            is_past = True
        elif d == today and now.time() >= dtime(23, 30):
            is_past = True
        else:
            is_past = False

        matrix.append({
            'date': d,
            'segments': segments,
            'is_past': is_past
        })

    return render(request, 'vehicles/monthly_gantt.html', {
        'vehicle': vehicle,
        'matrix': matrix,
        'hours': list(range(24)),
        'current_month': current_month,
        'prev_month': prev_month,
        'next_month': next_month,
        'now': now,
        'is_admin': request.user.is_staff,
    })

from django.utils import timezone
from django.db.models import Q
from django.shortcuts import render

def vehicle_weekly_gantt_view(request):
    """
    周甘特图（所有车辆一览）
    URL: /vehicles/weekly/gantt/?start=YYYY-MM-DD
    模板: vehicles/weekly_gantt.html
    依赖字段：
      Reservation: date(Date), end_date(Date|NULL), start_time(Time|NULL), end_time(Time|NULL),
                   vehicle(FK), driver(FK|NULL), status(可选)
      Vehicle: 显示名用 display_name/plate/name 任一；兜底用 id
    """
    tz = timezone.get_current_timezone()
    today_local = timezone.localdate()

    # 解析 ?start=YYYY-MM-DD，归一到周一
    raw = request.GET.get("start")
    try:
        base = datetime.strptime(raw, "%Y-%m-%d").date() if raw else today_local
    except (TypeError, ValueError):
        base = today_local
    week_start = base - timedelta(days=base.weekday())     # 周一
    week_end   = week_start + timedelta(days=7)            # [start, end)
    week_start_dt = datetime.combine(week_start, dtime(0, 0, 0), tzinfo=tz)
    week_end_dt   = datetime.combine(week_end,   dtime(0, 0, 0), tzinfo=tz)
    HOURS = 7 * 24
    week_dates = [week_start + timedelta(days=i) for i in range(7)]

    # 取覆盖该周的预约：开始 < 周末 且 结束 >= 周初
    from vehicles.models import Reservation  # 维持你项目里的导入风格
    qs = (
        Reservation.objects
        .select_related("vehicle", "driver")
        .filter(
            Q(date__lt=week_end) &
            (Q(end_date__gte=week_start) | Q(end_date__isnull=True, date__gte=week_start))
        )
        .order_by("vehicle__id", "date", "start_time")
    )

    vehicle_rows = []

    def label_of_vehicle(v):
        """
        行头展示优先用车号/车牌号（和 weekly_view.html 一致），
        其次用内部编号；最后才用名称兜底。
        """
        code = (
            getattr(v, "license_plate", "")   # ✅ 你周视图使用的字段
            or getattr(v, "car_number", "")
            or getattr(v, "vehicle_code", "")
            or ""
        )
        name = (
            getattr(v, "display_name", "")
            or getattr(v, "name", "")
            or getattr(v, "model_name", "")
            or ""
        )
        if code and name:
            return f"{code}（{name}）"
        return code or name or f"Vehicle #{getattr(v, 'id', 'N/A')}"

    # 内嵌：按单个车辆聚合并推入 vehicle_rows
    def flush_bucket(vobj, items):
        segs = []
        cursor = 0
        for r in items:
            # 组合 datetime（允许空的 start/end_time）
            s_d = r.date
            e_d = r.end_date or r.date
            s_t = getattr(r, "start_time", None) or dtime(0, 0, 0)
            e_t = getattr(r, "end_time",   None) or dtime(23, 59, 59)

            s_dt = datetime.combine(s_d, s_t, tzinfo=tz)
            e_dt = datetime.combine(e_d, e_t, tzinfo=tz)

            # 与本周窗口取交集
            start_clamped = max(s_dt, week_start_dt)
            end_clamped   = min(e_dt, week_end_dt - timedelta(seconds=1))
            if start_clamped >= end_clamped:
                continue

            # 转小时索引（向上取整结束）
            start_hours = int((start_clamped - week_start_dt).total_seconds() // 3600)
            end_hours   = int(((end_clamped - week_start_dt).total_seconds() + 3599) // 3600)
            start_hours = max(0, min(HOURS, start_hours))
            end_hours   = max(0, min(HOURS, end_hours))
            length = max(1, end_hours - start_hours)

            # 前置空白
            gap = start_hours - cursor
            if gap < 0:
                gap = 0
            cursor = start_hours + length

            status = getattr(r, "status", None) or "reserved"
            dname = ""
            if getattr(r, "driver", None):
                dname = getattr(r.driver, "username", "") or getattr(r.driver, "name", "") or ""
            title = (
                f"{label_of_vehicle(vobj)}  "
                f"{dname}  "
                f"{start_clamped.strftime('%m/%d %H:%M')}–{end_clamped.strftime('%m/%d %H:%M')}"
            ).strip()

            segs.append({
                "start": start_hours,
                "length": length,
                "title": title,
                "status": status,
                "gap": gap,
            })

        segs.sort(key=lambda x: x["start"])
        if not segs:
            return

        tail_gap = HOURS - cursor
        if tail_gap < 0:
            tail_gap = 0

        vehicle_rows.append({
            "vehicle_label": label_of_vehicle(vobj),
            "segs": segs,
            "tail_gap": tail_gap,
        })

    # 按 vehicle 分桶
    current_vid = None
    bucket = []
    current_vehicle = None
    for r in qs:
        vid = getattr(r.vehicle, "id", None)
        if current_vid is None:
            current_vid = vid
            current_vehicle = r.vehicle
            bucket = [r]
        elif vid == current_vid:
            bucket.append(r)
        else:
            flush_bucket(current_vehicle, bucket)
            current_vid = vid
            current_vehicle = r.vehicle
            bucket = [r]
    if bucket:
        flush_bucket(current_vehicle, bucket)

    ctx = {
        "week_start": week_start,
        "week_end": week_end - timedelta(days=1),   # 显示到周日
        "prev_week": week_start - timedelta(days=7),
        "this_week": (today_local - timedelta(days=today_local.weekday())),
        "next_week": week_start + timedelta(days=7),
        "HOURS": HOURS,               # 168
        "week_dates": week_dates,     # 模板表头
        "vehicle_rows": vehicle_rows, # 行数据
    }
    return render(request, "vehicles/weekly_gantt.html", ctx)


@login_required
def daily_selector_view(request):
    if request.method == 'POST':
        date = request.POST.get('date')
        return redirect(f"/vehicles/daily/?date={date}")
    return render(request, 'vehicles/daily_selector.html')

@login_required
def daily_overview_view(request):
    date_str = request.GET.get('date')
    if date_str:
        try:
            selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            selected_date = timezone.localdate()
    else:
        selected_date = timezone.localdate()

    now_dt = timezone.localtime()  # ✅ 改名避免与函数 now 冲突
    vehicles = get_all_active_cars()
    reservations = Reservation.objects.filter(date=selected_date)

    data = []
    for vehicle in vehicles:
        r = reservations.filter(vehicle=vehicle).first()

        if r:
            item = {'vehicle': vehicle, 'reservation': r}
        else:
            is_today = selected_date == now_dt.date()
            is_past = is_today and now_dt.time() > dtime(0, 30)

            if request.user.is_staff:
                is_past = False

            item = {'vehicle': vehicle, 'reservation': None, 'is_past': is_past}

        data.append(item)

    return render(request, 'vehicles/daily_view.html', {
        'selected_date': selected_date,
        'data': data,
    })

@login_required
def reservation_dashboard(request):
    return render(request, 'vehicles/reservation_dashboard.html')

@login_required
def my_reservations_view(request):
    # ✅ 获取当前用户预约记录，按时间倒序
    all_reservations = Reservation.objects.filter(
        driver=request.user
    ).order_by('-date', '-start_time')

    # ✅ 分页（每页最多显示10条）
    paginator = Paginator(all_reservations, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # ✅ 自动取消超时未出库的预约（仅处理当前页）
    canceled_any = False
    for r in page_obj.object_list:
        if r.status == ReservationStatus.BOOKED and not r.actual_departure:
            try:
                start_dt = make_aware(datetime.combine(r.date, r.start_time))
                expire_dt = start_dt + timedelta(hours=1)
                if timezone.now() > expire_dt:
                    r.status = 'canceled'
                    r.save()
                    canceled_any = True
            except Exception as e:
                if settings.DEBUG:
                    print(f"[取消预约异常] ID={r.id} → {e}")
                continue

    # ✅ 优化上次入库查询逻辑：批量查找后分组缓存
    driver_ids = [r.driver_id for r in page_obj.object_list]
    all_returns = Reservation.objects.filter(
        driver_id__in=driver_ids,
        actual_return__isnull=False
    ).order_by('driver_id', '-actual_return')

    returns_by_driver = defaultdict(list)
    for res in all_returns:
        returns_by_driver[res.driver_id].append(res)

    # ✅ 计算预约间隔信息（当前页）
    reservation_infos = {}
    for r in page_obj.object_list:
        info = {}

        try:
            start_dt = datetime.combine(r.date, r.start_time)
            if is_naive(start_dt):
                start_dt = make_aware(start_dt)
        except Exception as e:
            if settings.DEBUG:
                print(f"[⛔ start_dt 构建失败] ID={r.id} → {e}")
            continue

        # ✅ 内存中找上一条入库记录
        driver_returns = returns_by_driver.get(r.driver_id, [])
        last_return = next((ret for ret in driver_returns if ret.actual_return < start_dt), None)

        if last_return:
            last_return_dt = last_return.actual_return
            if is_naive(last_return_dt):
                last_return_dt = make_aware(last_return_dt)
            diff = start_dt - last_return_dt
            info['last_return'] = last_return_dt
            info['diff_from_last_return'] = round(diff.total_seconds() / 3600, 1)

        # ✅ 暂时保留原始“下次预约”逻辑（下一步优化）
        next_res = Reservation.objects.filter(
            driver=r.driver,
            status__in=[ReservationStatus.PENDING, ReservationStatus.BOOKED],
            date__gt=r.end_date
        ).order_by('date', 'start_time').first()

        if next_res:
            try:
                current_end_dt = datetime.combine(r.end_date, r.end_time)
                next_start_dt = datetime.combine(next_res.date, next_res.start_time)
                if is_naive(current_end_dt):
                    current_end_dt = make_aware(current_end_dt)
                if is_naive(next_start_dt):
                    next_start_dt = make_aware(next_start_dt)
                diff_next = next_start_dt - current_end_dt
                info['next_reservation'] = next_start_dt
                info['diff_to_next'] = round(diff_next.total_seconds() / 3600, 1)
            except Exception as e:
                if settings.DEBUG:
                    print(f"[⛔ next_start_dt 构建失败] ID={r.id} → {e}")
                continue

        reservation_infos[r.id] = info

    # ✅ 额外信息（公告等）
    tips = Tip.objects.filter(is_active=True).order_by('created_at')
    notice_message = SystemNotice.objects.filter(is_active=True).first()
    print("当前用户：", request.user)

    # === 新增: 计算今天所在页和今天第一条的ID ===
    today = localdate()

    # 是否有“今天”的记录
    has_today = all_reservations.filter(date=today).exists()

    # 比“今天更晚”的记录条数（注意你的排序是 -date, -start_time）
    newer_count = all_reservations.filter(date__gt=today).count()

    # 用 paginator.per_page 计算今天在第几页（若今天无记录则为 None）
    today_page = (newer_count // paginator.per_page + 1) if has_today else None

    # “今天”的第一条 id（按与列表一致的排序）
    today_first_id = (
        all_reservations.filter(date=today)
        .order_by('-date', '-start_time', '-id')
        .values_list('pk', flat=True)
        .first()
    )

    # 传入模板
    ctx = {
        'page_obj': page_obj,
        'reservation_infos': reservation_infos,
        'canceled_any': canceled_any,
        'tips': tips,
        'notice_message': notice_message,
        'today_page': today_page,
        'today_first_id': today_first_id,
    }
    return render(request, 'vehicles/my_reservations.html', ctx)

@staff_member_required
def reservation_approval_list(request):
    pending_reservations = Reservation.objects.filter(status=ReservationStatus.PENDING).order_by('date', 'start_time')
    return render(request, 'vehicles/reservation_approval_list.html', {
        'pending_reservations': pending_reservations
    })

@staff_member_required
def approve_reservation(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk)
    reservation.status = 'booked'   # ← 不要再用 'reserved'
    if hasattr(reservation, 'approved_by'):
        reservation.approved_by = request.user
    if hasattr(reservation, 'approved_at'):
        reservation.approved_at = timezone.now()
    reservation.save()
    notify_driver_reservation_approved(reservation)
    messages.success(request, f"✅ 预约 ID {pk} 已成功审批，并已通知司机。")
    return redirect('vehicles:reservation_approval_list')

@login_required
def reservation_detail_view(request, reservation_id):
    reservation = get_object_or_404(Reservation, id=reservation_id)
    return render(request, 'vehicles/reservation_detail.html', {
        'reservation': reservation
    })

@login_required
def check_out(request, reservation_id):
    reservation = get_object_or_404(Reservation, id=reservation_id)
    if request.user != reservation.driver:
        return HttpResponseForbidden("你不能操作别人的预约")

    with transaction.atomic():
        # 锁定当前预约行，避免并发修改（有些数据库会忽略，但不影响兼容性）
        Reservation.objects.select_for_update().filter(pk=reservation.pk)

        # 已经出库就不重复操作
        if reservation.actual_departure:
            messages.warning(request, "你已经出库了！")
            return redirect('vehicles:vehicle_status')

        # 🚫 同一用户是否还有其它“出库未入库”的记录
        unfinished_qs = (
            Reservation.objects
            .select_for_update()
            .filter(
                driver=request.user,
                status=ReservationStatus.DEPARTED,
                actual_return__isnull=True,
            )
            .exclude(id=reservation.id)
        )
        if unfinished_qs.exists():
            messages.error(request, "因有未完成入库操作的记录，请完成上一次入库操作后再进行本次出库。")
            return redirect('vehicles:vehicle_status')

        # ✅ 正常登记出库（和检查同一事务内，避免竞态）
        reservation.actual_departure = timezone.now()
        reservation.status = 'out'
        reservation.save()

    messages.success(request, "出库登记成功")
    return redirect('vehicles:vehicle_status')

@login_required
def check_in(request, reservation_id):
    reservation = get_object_or_404(Reservation, id=reservation_id)
    if request.user != reservation.driver:
        return HttpResponseForbidden("你不能操作别人的预约")
    if not reservation.actual_departure:
        messages.warning(request, "请先出库登记")
    elif reservation.actual_return:
        messages.warning(request, "你已经入库了！")
    else:
        reservation.actual_return = timezone.now()
        reservation.save()
        messages.success(request, "入库登记成功")
    return redirect('vehicles:vehicle_status')

@login_required
def edit_reservation_view(request, reservation_id):
    reservation = get_object_or_404(Reservation, id=reservation_id)

    # ✅ 权限判断：仅本人或管理员可访问
    if reservation.status not in ['pending', 'booked']:
        return HttpResponseForbidden("⛔️ 当前状态不可修改。")

    if request.method == 'POST':
        form = ReservationForm(
            request.POST,
            request=request,
            car=reservation.vehicle,
            instance=reservation,
            initial={'date': reservation.date, 'driver': reservation.driver}
        )

        if form.is_valid():
            updated_res = form.save(commit=False)
            updated_res.driver = updated_res.driver or request.user
            updated_res.date = form.cleaned_data['date']
            updated_res.end_date = form.cleaned_data['end_date']
            updated_res.save()

            messages.success(request, "✅ 预约已修改")
            return redirect('vehicles:my_reservations')
    else:
        form = ReservationForm(
            instance=reservation,
            request=request,
            car=reservation.vehicle,
            initial={'date': reservation.date, 'driver': reservation.driver}
        )

    return render(request, 'vehicles/edit_reservation.html', {
        'form': form,
        'reservation': reservation,
    })

@login_required
def delete_reservation_view(request, reservation_id):
    reservation = Reservation.objects.filter(id=reservation_id, driver=request.user).first()
    if not reservation:
        messages.error(request, "この予約は存在しないか、既に削除されました。")
        return redirect('vehicles:my_reservations')

    if reservation.status not in ['pending', 'booked']:
        return HttpResponseForbidden("已确认预约不能删除。")

    if request.method == 'POST':
        reservation.delete()
        messages.success(request, "予約を削除しました。")
        return redirect('vehicles:my_reservations')

    return render(request, 'vehicles/reservation_confirm_delete.html', {
        'reservation': reservation
    })

@login_required
def vehicle_detail_view(request, vehicle_id):
    vehicle = get_object_or_404(Car, id=vehicle_id)
    reservations = Reservation.objects.filter(vehicle=vehicle).order_by('-date')[:5]
    return render(request, 'vehicles/vehicle_detail.html', {
        'vehicle': vehicle,
        'reservations': reservations
    })

@require_POST
@login_required
def complete_return(request, pk):
    """
    一键入库：仅允许本人（或按需放宽），把 actual_return 设为现在，并将状态置为 DONE。
    适用于“未完成出入库手续(incomplete)”或“已出库(out)”且尚未入库的预约。
    """
    # 仅本人（如需管理员可操作，按需放宽为：if request.user.is_staff: 不限制 driver）
    res = get_object_or_404(Reservation, pk=pk, driver=request.user)

    # 已经入库过就不重复
    if res.actual_return:
        messages.info(request, "该预约已完成入库。")
        return redirect("vehicles:my_reservations")

    # 仅允许在 out / incomplete 时一键入库
    if res.status not in (ReservationStatus.OUT, ReservationStatus.INCOMPLETE):
        messages.error(request, "当前状态不可执行入库操作。")
        return redirect("vehicles:my_reservations")

    # 执行入库 → 置为完成
    res.actual_return = timezone.now()
    res.status = ReservationStatus.DONE
    res.save(update_fields=["actual_return", "status"])

    messages.success(request, "入库手续已完成。")
    return redirect("vehicles:my_reservations")

@require_POST
@login_required
def confirm_check_io(request):
    # ① 取预约ID：POST 优先，URL ?rid= 兜底
    reservation_id = (request.POST.get("reservation_id", "").strip()
                      or request.GET.get("rid", "").strip())
    action_type = (request.POST.get("action_type") or "").strip().lower()
    actual_time_str = (request.POST.get("actual_time") or "").strip()

    if not reservation_id.isdigit():
        messages.error(request, "无效的预约编号，请刷新页面后重试。")
        return redirect("vehicles:my_reservations")

    # ② 解析为 aware datetime（表单是 datetime-local，无时区）；空值时兜底为“现在”
    try:
        if actual_time_str:
            actual_time = datetime.strptime(actual_time_str, "%Y-%m-%dT%H:%M")
            if timezone.is_naive(actual_time):
                actual_time = timezone.make_aware(actual_time)
        else:
            actual_time = timezone.now()
    except Exception:
        messages.error(request, "时间格式不正确。")
        return redirect("vehicles:my_reservations")

    # 仅允许本人操作；如需管理员越权，这里可放宽
    reservation = get_object_or_404(Reservation, id=int(reservation_id), driver=request.user)

    if action_type == "departure":
        with transaction.atomic():
            # A. 拦截：是否还有“出库未入库/未完成”的其他记录（out 或 incomplete，且 actual_return 为空）
            unfinished_exists = (
                Reservation.objects
                .select_for_update()
                .filter(driver=request.user,
                        actual_return__isnull=True,
                        status__in=[ReservationStatus.OUT, ReservationStatus.INCOMPLETE])
                .exclude(id=reservation.id)
                .exists()
            )
            if unfinished_exists:
                messages.error(request, "因有未完成入库操作的记录，请先完成上一次入库。")
                return redirect("vehicles:my_reservations")

            # B. 10 小时冷却（距上次入库不足 10 小时不允许再次出库）
            last_return = (
                Reservation.objects
                .filter(driver=request.user, actual_return__isnull=False, actual_return__lt=actual_time)
                .order_by("-actual_return")
                .first()
            )
            if last_return and (actual_time - last_return.actual_return) < timedelta(hours=10):
                next_allowed = last_return.actual_return + timedelta(hours=10)
                messages.error(
                    request,
                    f"距上次入库未满 10 小时，请于 {timezone.localtime(next_allowed).strftime('%Y-%m-%d %H:%M')} 后再试。"
                )
                return redirect("vehicles:my_reservations")

            # C. 更新为“已出库”
            reservation.actual_departure = actual_time
            reservation.status = ReservationStatus.OUT
            reservation.save(update_fields=["actual_departure", "status"])

        messages.success(request, "✅ 出库记录已保存。")
        return redirect("vehicles:my_reservations")

    elif action_type == "return":
        # A. 入库 -> 直接视为完成（无论当前是 out 还是 incomplete）
        reservation.actual_return = actual_time
        reservation.status = ReservationStatus.DONE
        reservation.save(update_fields=["actual_return", "status"])

        # B. 如有后续预约且不足 10 小时，则自动顺延
        next_res = (
            Reservation.objects
            .filter(driver=request.user,
                    date__gte=reservation.date,
                    status__in=[ReservationStatus.PENDING, ReservationStatus.BOOKED])
            .exclude(id=reservation.id)
            .order_by("date", "start_time")
            .first()
        )
        if next_res:
            next_start = timezone.make_aware(datetime.combine(next_res.date, next_res.start_time)) \
                         if timezone.is_naive(datetime.combine(next_res.date, next_res.start_time)) \
                         else datetime.combine(next_res.date, next_res.start_time)
            if (next_start - actual_time) < timedelta(hours=10):
                new_start = actual_time + timedelta(hours=10)
                next_res.date = new_start.date()
                next_res.start_time = new_start.time()
                next_res.save(update_fields=["date", "start_time"])
                messages.warning(
                    request,
                    f"⚠️ 下次预约已顺延至 {timezone.localtime(new_start).strftime('%Y-%m-%d %H:%M')}"
                )

        messages.success(request, "✅ 入库记录已保存。")
        return redirect("vehicles:my_reservations")

    else:
        messages.error(request, "❌ 无效的操作类型。")
        return redirect("vehicles:my_reservations")

@login_required
def confirm_check_io_view(request, reservation_id):
    reservation = get_object_or_404(Reservation, id=reservation_id, driver=request.user)
    action = request.GET.get("action")

    if action not in ['departure', 'return']:
        return HttpResponseForbidden("非法操作类型")

    default_time = timezone.localtime().strftime("%Y-%m-%dT%H:%M")  # 用于 datetime-local 输入默认值

    return render(request, "vehicles/confirm_check_io.html", {
        "reservation": reservation,
        "action": action,
        "default_time": default_time,
    })


@login_required
def vehicle_status_with_photo(request):
    date_str = request.GET.get('date')
    if date_str:
        selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    else:
        selected_date = timezone.localdate()

    reservations = Reservation.objects.filter(date=selected_date)
    vehicles = get_all_active_cars()
    status_map = {}

    today = localdate()

    for vehicle in vehicles:
        r = reservations.filter(vehicle=vehicle).first()
        if r:
            status = r.status
            user_reservation = r if r.driver == request.user else None
        else:
            status = 'available'
            user_reservation = None

        # ✅ 新增提醒逻辑
        show_inspection_warning = (
            vehicle.inspection_date and vehicle.inspection_date <= today + timedelta(days=30)
        )
        show_insurance_warning = (
            vehicle.insurance_expiry and vehicle.insurance_expiry <= today + timedelta(days=30)
        )

        status_map[vehicle] = {
            'status': status,
            'user_reservation': user_reservation,
            'reserver_name': reserver_name,
            'reservable': is_car_reservable(vehicle),
            'is_repair': is_under_repair(vehicle),              # ✅ 新增
            'is_admin_only': is_admin_only(vehicle),            # ✅ 新增
            'is_retired': is_retired(vehicle),                  # ✅ 预留
            'is_reserved_by_admin': is_reserved_by_admin(vehicle),  # ✅ 可选
        }

    return render(request, 'vehicles/status_view_with_photo.html', {
        'selected_date': selected_date,
        'status_map': status_map
    })

def vehicle_image_list_view(request, vehicle_id):
    vehicle = get_object_or_404(Car, id=vehicle_id)
    images = vehicle.images.all()
    data = [{'url': img.image.url} for img in images]
    return JsonResponse({'images': data})

def vehicle_image_delete_view(request, vehicle_id, index):
    vehicle = get_object_or_404(Car, id=vehicle_id)
    images = list(vehicle.images.all())

    if 0 <= index < len(images):
        images[index].delete()
        return JsonResponse({'status': 'deleted'})
    return JsonResponse({'status': 'invalid_index'}, status=400)

@login_required
def my_stats_view(request):
    from dailyreport.models import DriverDailyReportItem  # <--- 新增或提前导入

    today = timezone.localdate()
    default_month = today.replace(day=1)

    if request.method == 'POST':
        form = MonthForm(request.POST)
        if form.is_valid():
            month_date = form.cleaned_data['month']
        else:
            month_date = default_month
    else:
        month_date = default_month
        form = MonthForm(initial={'month': default_month})

    year, month = month_date.year, month_date.month
    first_day = month_date.replace(day=1)
    last_day = first_day.replace(day=calendar.monthrange(year, month)[1])

    qs = Reservation.objects.filter(
        driver=request.user,
        actual_departure__date__gte=first_day,
        actual_departure__date__lte=last_day,
        status__in=[ReservationStatus.DEPARTED, ReservationStatus.DONE],
    )

    total_checkouts = qs.count()

    duration_expr = ExpressionWrapper(
        F('actual_return') - F('actual_departure'),
        output_field=DurationField()
    )
    agg = qs.annotate(interval=duration_expr).aggregate(total_duration=Sum('interval'))
    total_duration = agg['total_duration'] or timedelta()

    # 只改这里👇
    sales_data = DriverDailyReportItem.objects.filter(
        report__driver__user=request.user,
        report__date__gte=first_day,
        report__date__lte=last_day,
    ).aggregate(total=Sum('meter_fee'))['total'] or 0

    take_home = sales_data * Decimal('0.7')

    return render(request, 'vehicles/my_stats.html', {
        'form': form,
        'month_display': first_day.strftime('%Y年%m月'),
        'month_value': f"{year}-{month:02d}",
        'total_checkouts': total_checkouts,
        'total_duration': total_duration,
        'sales_data': sales_data,
        'take_home': take_home,
    })

# 売上API数据（伪代码）
def fetch_sales(user, start_date, end_date):
    # 本地查询/外部API，简写示例
    return 0  # 替换为真实売上金额

def is_admin(user):
    return user.is_staff

@login_required
@user_passes_test(is_admin)
def admin_stats_view(request):
    # 获取月份（默认本月）
    month_str = request.GET.get('month')
    try:
        query_month = datetime.strptime(month_str, "%Y-%m") if month_str else datetime.now()
    except:
        query_month = datetime.now()
    month_start = query_month.replace(day=1)
    next_month = (month_start + timedelta(days=32)).replace(day=1)
    month_end = next_month - timedelta(days=1)

    # 司机筛选
    driver_id = request.GET.get('driver')
    drivers = DriverUser.objects.filter(is_active=True).order_by('username')
    if driver_id and driver_id != "all":
        drivers = drivers.filter(id=driver_id)

    # 分页设置
    page_num = int(request.GET.get("page", 1))
    paginator = Paginator(drivers, 20)  # 每页20人
    page_obj = paginator.get_page(page_num)

    stats_list = []
    for driver in page_obj.object_list:
        # 该司机本月所有预约
        reservations = Reservation.objects.filter(
            driver=driver,
            date__gte=month_start.date(),
            end_date__lte=month_end.date(),
            status__in=[ReservationStatus.BOOKED, ReservationStatus.OUT, ReservationStatus.DONE]
        )

        # 出入库总次数
        count = reservations.count()

        # 出入库总时长
        total_seconds = 0
        for r in reservations:
            start_dt = datetime.combine(r.date, r.start_time)
            end_dt = datetime.combine(r.end_date, r.end_time)
            total_seconds += (end_dt - start_dt).total_seconds()
        total_hours = total_seconds // 3600
        total_days = total_seconds // 86400
        total_time_str = f"{int(total_days)}天, {int(total_hours % 24)}:{int((total_seconds % 3600) // 60):02d}"

        # 売上与工资（示例：本地API或外部API获取）
        sales = fetch_sales(driver, month_start.date(), month_end.date())
        salary = round(sales * 0.7, 2)

        stats_list.append({
            "driver": driver,
            "count": count,
            "total_time": total_time_str,
            "sales": sales,
            "salary": salary,
        })

    context = {
        "page_obj": page_obj,
        "stats_list": stats_list,
        "month": month_start.strftime("%Y-%m"),
        "driver_id": driver_id or "all",
        "drivers": DriverUser.objects.all(),
    }
    return render(request, "vehicles/admin_stats.html", context)

@csrf_exempt
def upload_vehicle_image(request):
    if request.method == 'POST' and request.FILES.get('file'):
        try:
            file_obj = request.FILES['file']
            filename = default_storage.save(f'vehicle_photos/{file_obj.name}', ContentFile(file_obj.read()))
            file_url = default_storage.url(filename)
            return JsonResponse({'url': file_url})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
def api_daily_sales_mock(request):  #一个假的销售数据接口以便调试
    target_date = request.GET.get('date')
    if not target_date:
        return JsonResponse({'error': '缺少日期参数'}, status=400)

    # 模拟当前用户是司机 hikari9706，返回随机数据
    return JsonResponse({
        'date': target_date,
        'ながし現金': 13450,
        '貸切現金': 4600,
        'ETC 空車': 720,
        'ETC 乗車': 1600,
        'uberプロモーション': 980,
        '备注': '已完成夜班'
    })

@login_required
def calendar_view(request):
    today = timezone.localdate()
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))
    current_month = date(year, month, 1)

    import calendar
    cal = calendar.Calendar(firstweekday=6)  # 周日开始
    month_days = cal.itermonthdates(year, month)
    calendar_matrix = []
    week = []
    for d in month_days:
        if d.month != month:
            week.append(None)
        else:
            week.append(d)
        if len(week) == 7:
            calendar_matrix.append(week)
            week = []

    # 计算上下月
    prev_month = (current_month.replace(day=1) - timedelta(days=1)).replace(day=1)
    next_month = (current_month.replace(day=28) + timedelta(days=4)).replace(day=1)

    return render(request, 'vehicles/calendar_view.html', {
        'current_month': current_month,
        'calendar_matrix': calendar_matrix,
        'today': today,
        'prev_year': prev_month.year,
        'prev_month': prev_month.month,
        'next_year': next_month.year,
        'next_month': next_month.month,
    })

def home_view(request):
    return render(request, 'home.html')


@login_required
def test_email_view(request):
    try:
        send_mail(
            subject='测试邮件：车辆预约系统',
            message='这是一封来自 Django 的测试邮件，用于验证邮件发送功能。',
            from_email='jiabing.msn@gmail.com',  # 发件人
            recipient_list=['jiabing.msn@gmail.com'],  # 收件人换成你自己的
            fail_silently=False,  # 设置为 False 以便报错时看到异常信息
        )
        return HttpResponse("✅ 邮件发送成功，请检查收件箱。")
    except Exception as e:
        return HttpResponse(f"❌ 邮件发送失败：{str(e)}")

@staff_member_required
def admin_reset_departure(request, reservation_id):
    reservation = get_object_or_404(Reservation, id=reservation_id)
    if reservation.actual_departure:
        reservation.actual_departure = None
        reservation.status = 'booked'
        reservation.vehicle.status = 'available'
        reservation.vehicle.save()
        reservation.save()
        messages.success(request, f"已撤销出库登记：{reservation}")
    else:
        messages.warning(request, "该预约没有出库记录。")
    return redirect('vehicles:vehicle_status')


@staff_member_required
def admin_reset_return(request, reservation_id):
    reservation = get_object_or_404(Reservation, id=reservation_id)
    if reservation.actual_return:
        reservation.actual_return = None
        reservation.status = 'out'
        reservation.vehicle.status = 'out'
        reservation.vehicle.save()
        reservation.save()
        messages.success(request, f"已撤销入库登记：{reservation}")
    else:
        messages.warning(request, "该预约没有入库记录。")
    return redirect('vehicles:vehicle_status')

def reservation_home(request):
    return render(request, 'vehicles/reservation_home.html')
    
def reservation_status(request):
    return render(request, 'vehicles/reservation_status.html')

@login_required
def create_reservation(request, vehicle_id):
    vehicle = get_object_or_404(Vehicle, id=vehicle_id)

    if request.method == "POST":
        try:
            # 获取 POST 字段
            date_list_raw = request.POST.get("selected_dates")  # 字符串："2025-07-07,2025-07-08"
            start_time_str = request.POST.get("start_time")  # "09:00"
            end_time_str = request.POST.get("end_time")      # "21:00"
            purpose = request.POST.get("purpose")

            if not date_list_raw or not start_time_str or not end_time_str:
                messages.error(request, "请输入完整预约信息。")
                return redirect(request.path)

            date_list = [d.strip() for d in date_list_raw.split(",")]
            start_time = datetime.strptime(start_time_str, "%H:%M").time()
            end_time = datetime.strptime(end_time_str, "%H:%M").time()

            # 校验时间段不超过13小时
            duration = (
                datetime.combine(datetime.today(), end_time) -
                datetime.combine(datetime.today(), start_time)
            ).total_seconds() / 3600

            if duration > 13:
                messages.error(request, "预约时段不能超过13小时。")
                return redirect(request.path)

            # 循环创建多条预约记录
            for date_str in date_list:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()

                start_dt = make_aware(datetime.combine(date_obj, start_time))
                end_dt = make_aware(datetime.combine(date_obj, end_time))

                Reservation.objects.create(
                    user=request.user,
                    vehicle=vehicle,
                    start_datetime=start_dt,
                    end_datetime=end_dt,
                    purpose=purpose,
                )

            messages.success(request, f"成功创建 {len(date_list)} 条预约记录！")
            return redirect('vehicles:vehicle_status')

        except Exception as e:
            messages.error(request, f"发生错误：{str(e)}")
            return redirect(request.path)

    return render(request, 'vehicles/create_reservation.html', {
        'vehicle': vehicle,
    })

def reservation_approval(request):
    return render(request, 'vehicles/reservation_approval.html')

def admin_index(request):
    return render(request, 'staffbook/admin_index.html')

def admin_list(request):
    return render(request, 'vehicles/admin_list.html')



@login_required
def my_dailyreports(request):
    # 1) 当前司机
    driver = get_object_or_404(Driver, user=request.user)

    # 2) 年月
    today = timezone.localdate()
    try:
        year = int(request.GET.get('year', today.year))
        month = int(request.GET.get('month', today.month))
    except ValueError:
        year, month = today.year, today.month

    # 3) 本月该司机的日报
    qs = (
        DriverDailyReport.objects
        .filter(driver=driver, date__year=year, date__month=month)
        .order_by('-date')
        .prefetch_related('items')
    )

    # ========== 口径 ==========
    SPECIAL_UBER = {'uber_reservation', 'uber_tip', 'uber_promotion'}

    reports_data = []
    total_raw = Decimal('0')            # 本月メータ料金合計（未分成，所有明细 meter_fee 总和）
    monthly_sales_total = 0             # 本月売上合計（列表口径）
    monthly_meter_only_total = 0        # 本月メータのみ合計

    for rpt in qs:
        # 原始合计（底部“本月メータ料金合計”用）
        raw = sum(Decimal(getattr(it, 'meter_fee', 0) or 0) for it in rpt.items.all())
        total_raw += raw

        # 与详情页一致的売上合計
        totals = _totals_of(rpt.items.all())
        sales_total = int(totals.get('sales_total', 0) or 0)
        monthly_sales_total += sales_total   # ✅ 只加一次

        # 列表用「メータのみ」
        meter_only_total = sum(
            int(getattr(it, 'meter_fee', 0) or 0)
            for it in rpt.items.all()
            if (not getattr(it, 'is_charter', False))
            and getattr(it, 'payment_method', None)
            and getattr(it, 'payment_method') not in SPECIAL_UBER
        )
        monthly_meter_only_total += meter_only_total

        reports_data.append({
            'id':               rpt.id,
            'date':             rpt.date,
            'note':             rpt.note,
            'sales_total':      sales_total,        # 売上合計
            'meter_only_total': meter_only_total,   # メータのみ
        })

    # 分成后的显示
    coef = Decimal('0.9091')
    total_split = (total_raw * coef).quantize(Decimal('1'), rounding=ROUND_HALF_UP)

    return render(request, 'vehicles/my_dailyreports.html', {
        'reports': reports_data,
        'selected_year': year,
        'selected_month': month,

        'monthly_sales_total': monthly_sales_total,               # ✅ 修正后不再翻倍
        'monthly_meter_only_total': monthly_meter_only_total,     # ✅

        'total_raw': total_raw,                                   # 原始 meter_fee 月总
        'total_split': total_split,                               # 分成后
        'attendance_days': (
            qs.filter(items__isnull=False).values('date').distinct().count()
        ),
        'debug_text': f'qs_count={qs.count()} | reports_len={len(reports_data)}',
    })



@login_required
def my_daily_report_detail(request, report_id):
    report = get_object_or_404(DriverDailyReport, id=report_id, driver__user=request.user)

    # ✅ 定义“日报工作窗口”：前一日 12:00 ~ 次日 12:00
    window_start = make_aware(datetime.combine(report.date - timedelta(days=1), dtime(12, 0)))
    window_end   = make_aware(datetime.combine(report.date + timedelta(days=1), dtime(12, 0)))

    # ✅ 只有【日报选了车辆】才去找预约；否则显示 --:--
    reservation = None
    if getattr(report, 'vehicle_id', None):
        reservation = (
            Reservation.objects.filter(
                driver=request.user,
                vehicle_id=report.vehicle_id,
                actual_departure__isnull=False,
                actual_departure__gte=window_start,
                actual_departure__lt=window_end,
            )
            .order_by('actual_departure')
            .first()
        )

    start_time = reservation.actual_departure if reservation else None
    end_time   = reservation.actual_return if reservation else None
    duration   = (end_time - start_time) if (start_time and end_time) else None

    # ✅ 排序函数（无 start_time 时，不做跨日+1）
    def parse_ride_datetime(item):
        try:
            ride_time = datetime.strptime(item.ride_time, "%H:%M").time()
            base_date = report.date
            if start_time and ride_time < start_time.time():
                base_date += timedelta(days=1)
            return datetime.combine(base_date, ride_time)
        except Exception:
            return datetime.max

    # 原始所有项
    items_all = report.items.all().order_by('combined_group', 'id')

    # ✅ 合算组去重：同组仅保留第一条
    items_raw, seen_groups = [], set()
    for item in items_all:
        g = item.combined_group
        if not g or g not in seen_groups:
            items_raw.append(item)
            if g:
                seen_groups.add(g)

    # ✅ 排序
    items = sorted(items_raw, key=parse_ride_datetime)

    # ✅ 金额统计 —— 先用统一口径拿合计
    totals = _totals_of(items)  # items 是我们已排序/去重后的列表
    total_sales = totals.get('sales_total', 0)

    # === 追加：在本页也按月视图口径计算「メータのみ」 ===
    SPECIAL_UBER = {'uber_reservation', 'uber_tip', 'uber_promotion'}

    # ① 基础“メータのみ”= 非貸切 且 有支付方式 的メータ合计
    base_meter_only = sum(
        int(getattr(it, 'meter_fee', 0) or 0)
        for it in items
        if not getattr(it, 'is_charter', False) and getattr(it, 'payment_method', None)
    )

    # ② 三类 Uber（予約/チップ/プロモ）总额（也只看非貸切）
    special_uber_sum = sum(
        int(getattr(it, 'meter_fee', 0) or 0)
        for it in items
        if not getattr(it, 'is_charter', False)
        and getattr(it, 'payment_method', '') in SPECIAL_UBER
    )

    # ③ 详情页用的「メータのみ」
    meter_only_total = max(0, base_meter_only - special_uber_sum)
    # === 追加结束 ===

    # （保留原本的现金统计兜底逻辑）
    total_cash = totals.get('cash_total', None)
    if total_cash is None:
        total_cash = sum(
            Decimal(it.meter_fee or 0)
            for it in items
            if getattr(it, 'payment_method', '') and 'cash' in it.payment_method.lower()
        )

    deposit = report.deposit_amount or Decimal("0")
    deposit_diff = deposit - total_cash
    is_deposit_exact = (deposit_diff == 0)

    # ✅ 本月出勤日数
    month_start = report.date.replace(day=1)
    month_end   = month_start + relativedelta(months=1)
    attendance_days = (
        DriverDailyReport.objects
        .filter(driver=report.driver, date__gte=month_start, date__lt=month_end, items__isnull=False)
        .values('date').distinct().count()
    )

    # ✅ 新增：调用 _totals_of，得到正确的 sales_total 和 meter_only_total
    totals = _totals_of(report.items.all())
    report.meter_only_total = totals.get("meter_only_total", 0)

    return render(request, 'vehicles/my_daily_report_detail.html', {
        'report': report,
        'items': items,
        'start_time': start_time,
        'end_time': end_time,
        'duration': duration,

        # ✅ 传给模板
        'total_cash': total_cash,
        'total_sales': total_sales,
        'meter_only_total': meter_only_total,

        'deposit': deposit,
        'deposit_diff': deposit_diff,
        'is_deposit_exact': is_deposit_exact,
        'attendance_days': attendance_days,
    })


# 函数：生成到期提醒文案（提前5天～当天～延后5天）
def get_due_reminder(due_date, label="保险"):
    """
    输入:
        due_date: 到期日期 (datetime.date)
        label: 字段标签文字 (如 "保险", "检査")
    返回:
        None 或 提醒文字 (str)
    """
    if not due_date:
        return None

    today = date.today()
    delta = (due_date - today).days

    if -5 <= delta <= 5:
        if delta > 0:
            return f"{delta}天后{label}到期，请协助事务完成{label}更新"
        elif delta == 0:
            return f"今天{label}到期，请协助事务完成{label}更新"
        else:
            return f"{label}到期延迟{-delta}天，请协助事务完成{label}更新"

    return None


@login_required
def edit_vehicle_notes(request, car_id):
    car = get_object_or_404(Car, id=car_id)

    selected_date_str = request.GET.get('date')
    selected_date = date.today()

    if selected_date_str:
        try:
            selected_date = date.fromisoformat(selected_date_str)
        except ValueError:
            try:
                import re
                match = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日", selected_date_str)
                if match:
                    y, m, d = map(int, match.groups())
                    selected_date = date(y, m, d)
            except Exception:
                pass

    # ✅ 统一 selected_date_str 为标准格式
    selected_date_str = selected_date.isoformat()

    # ✅ 检查当前用户是否为预约者
    user_reservation = Reservation.objects.filter(
        vehicle=car,
        driver=request.user,
        date__lte=selected_date,
        end_date__gte=selected_date,
        status__in=[ReservationStatus.BOOKED, ReservationStatus.DEPARTED]
    ).first()

    if not user_reservation:
        return HttpResponseForbidden("你没有权限编辑该车辆备注。")

    # ✅ 表单处理逻辑
    if request.method == 'POST':
        form = VehicleNoteForm(request.POST, instance=car)
        if form.is_valid():
            form.save()
            return redirect(f"{reverse('vehicles:vehicle_status')}?date={selected_date_str}")
    else:
        form = VehicleNoteForm(instance=car)

    return render(request, 'vehicles/edit_vehicle_notes.html', {
        'form': form,
        'car': car,
        'selected_date': selected_date_str,
    })

@login_required
@require_POST
def save_vehicle_note(request, car_id):
    car = get_object_or_404(Car, pk=car_id)

    vehicle_form = VehicleStatusForm(request.POST, instance=car, prefix=f"car_{car_id}")
    note_form = VehicleNoteForm(request.POST, instance=car)

    if vehicle_form.is_valid() and note_form.is_valid():
        vehicle_form.save()
        car.notes = note_form.cleaned_data.get('notes', '')
        car.save()  # ✅ 强制写入备注字段
        messages.success(request, f"✅ {car.license_plate} 的车辆状态已保存")
    else:
        print("❌ 表单验证失败")
        print("vehicle_form.errors:", vehicle_form.errors)
        print("note_form.errors:", note_form.errors)
        messages.error(request, "❌ 保存失败，请检查输入内容")

    return redirect('vehicles:vehicle_status')


# ✅ 加入到 vehicles/views.py 顶部位置
from django.views.decorators.http import require_GET
from django.utils.dateparse import parse_datetime

# ✅ 新增冲突检测 API（支持立即调用）
@require_GET
@login_required
def check_reservation_conflict(request):
    car_id = request.GET.get("car_id")
    start_str = request.GET.get("start_datetime")
    end_str = request.GET.get("end_datetime")

    if not car_id or not start_str or not end_str:
        return JsonResponse({'status': 'error', 'message': '缺少参数'}, status=400)

    try:
        start_dt = parse_datetime(start_str)
        end_dt = parse_datetime(end_str)
        if not start_dt or not end_dt:
            raise ValueError("时间格式不正确")
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'时间解析失败: {e}'}, status=400)

    # ✅ 查询是否有冲突预约（非当前用户）
    conflict_exists = Reservation.objects.filter(
        vehicle_id=car_id,
        start_datetime__lt=end_dt,
        end_datetime__gt=start_dt,
        status__in=[ReservationStatus.BOOKED, ReservationStatus.DEPARTED]
    ).exclude(driver=request.user).exists()

    if conflict_exists:
        return JsonResponse({'status': 'conflict'})
    else:
        return JsonResponse({'status': 'ok'})
