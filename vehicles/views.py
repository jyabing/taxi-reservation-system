import calendar, requests, random, os, json
from calendar import monthrange
from datetime import datetime, timedelta, time, date
from .models import Reservation, Tip, Car as Vehicle, SystemNotice
from collections import defaultdict

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
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.conf import settings
from django.core.paginator import Paginator
from django.core.mail import send_mail
from carinfo.models import Car

from django.db.models import F, ExpressionWrapper, DurationField, Sum
from django.views.decorators.csrf import csrf_exempt

from .models import Reservation, Tip, Car
from .forms import MonthForm, AdminStatsForm, ReservationForm
from accounts.models import DriverUser
from requests.exceptions import RequestException
from vehicles.utils import notify_driver_reservation_approved, send_notification

# 导入 Driver/DriverDailyReport（已确保在 staffbook 里定义！）
from dailyreport.models import Driver, DriverDailyReport, DriverDailyReportItem
from vehicles.models import Reservation, Tip

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

@login_required
def vehicle_list(request):
    vehicles = Car.objects.all()
    return render(request, 'vehicles/vehicle_list.html', {'vehicles': vehicles})

@login_required
def vehicle_detail(request, pk):
    vehicle = get_object_or_404(Car.objects.prefetch_related('images'), pk=pk)
    reservations = Reservation.objects.filter(vehicle=vehicle).order_by('-date')[:5]
    return render(request, 'vehicles/vehicle_detail.html', {
        'vehicle': vehicle,
        'reservations': reservations,
    })

@login_required
def vehicle_status_view(request):
    # ✅ 调试打印所有预约记录
    # from vehicles.models import Reservation
    # print("🚨 所有预约记录:")
    # for r in Reservation.objects.all():
    #     print(f"🚗 {r.vehicle} | {r.start_datetime} ~ {r.end_datetime} | 状态: {r.status}")

    # ✅ 清空旧 messages
    list(messages.get_messages(request))  # 消耗掉所有旧消息

    date_str = request.GET.get('date')
    selected_date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else timezone.localdate()

    # ✅ 跨日支持
    start_of_day = make_aware(datetime.combine(selected_date, time.min))
    end_of_day = make_aware(datetime.combine(selected_date + timedelta(days=1), time.min))

    reservations = Reservation.objects.filter(
        Q(date__lte=selected_date) & Q(end_date__gte=selected_date),
        status__in=['reserved', 'out']
    )

    vehicles = Car.objects.all()
    status_map = {}
    now = timezone.localtime()
    now_dt = now

    for vehicle in vehicles:
        res_list = reservations.filter(vehicle=vehicle).order_by('start_datetime')
        #print(f"🔍 DEBUG: {vehicle.license_plate} 预约数: {res_list.count()}")

        # ✅ 去重处理：相同司机、时间段、日期只显示一次
        seen_keys = set()
        res_list_deduped = []
        for r in res_list:
            key = (
                r.driver.id if r.driver else None,
                r.start_time,
                r.end_time,
                r.date,
                r.end_date,
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            res_list_deduped.append(r)

        # 默认状态
        if selected_date < timezone.localdate():
            status = 'expired'
        else:
            status = 'available'

        # 出库中优先
        if res_list.filter(status='out', actual_departure__isnull=False, actual_return__isnull=True).exists():
            status = 'out'

        # ✅ 已过结束时间但尚未入库
        elif res_list.filter(status='out', end_datetime__lt=now_dt, actual_return__isnull=True).exists():
            status = 'overdue'

        # ✅ 当前预约未出库
        else:
            future_reserved = res_list.filter(status='reserved', actual_departure__isnull=True)
            for r in future_reserved:
                start_dt = r.start_datetime
                expire_dt = start_dt + timedelta(hours=1)
                if now_dt > expire_dt:
                    r.status = 'canceled'
                    r.save()
                    if r.driver == request.user:
                        messages.warning(request, f"你对 {vehicle.license_plate} 的预约因超时未出库已被自动取消，请重新预约。")
                else:
                    status = 'reserved'
                    break

        # 当前用户的预约（当天）
        user_reservation = res_list.filter(
            driver=request.user,
            status__in=['reserved', 'out'],
            date__lte=selected_date,
            end_date__gte=selected_date
        ).first()

        # ✅ 所有人预约者显示（使用去重后的 res_list_deduped）
        reserver_labels = [
            (
                f"{datetime.combine(r.date, r.start_time).strftime('%H:%M')}~"
                f"{datetime.combine(r.end_date, r.end_time).strftime('%H:%M')} "
                f"{getattr(r.driver, 'display_name', (r.driver.first_name or '') + ' ' + (r.driver.last_name or '')).strip()}"
            )
            for r in res_list_deduped
            if r.status in ['reserved', 'out'] and r.driver
        ]

        # 如果有多个预约者，显示所有人
        reserver_name = '<br>'.join(reserver_labels) if reserver_labels else ''

        status_map[vehicle] = {
            'status': status,
            'user_reservation': user_reservation,
            'reserver_name': reserver_name,
        }

    # 所有车辆都不可预约时提示
    if not any(info['status'] == 'available' for info in status_map.values()):
        messages.warning(request, "当前车辆状态不可预约，请选择其他车辆")

    return render(request, 'vehicles/status_view.html', {
        'selected_date': selected_date,
        'status_map': status_map,
        'today': localdate(),
        'now': now,  # ✅ 加这一行
    })

@login_required
def reserve_vehicle_view(request, car_id):
    car = get_object_or_404(Car, id=car_id)
    min_time = (timezone.now() + timedelta(minutes=30)).strftime('%Y-%m-%dT%H:%M')

    if request.method == 'POST':
        form = ReservationForm(request.POST)
        form.instance.driver = request.user
        selected_dates_raw = request.POST.get('selected_dates', '')
        selected_dates = json.loads(selected_dates_raw) if selected_dates_raw else []

        # ✅ 修正 Flatpickr 日期偏移（强制向后 +1 天）
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
                    # ✅ 用户在前端选择的日期，即预约开始日
                    start_date = datetime.strptime(date_str, '%Y-%m-%d').date()

                    # ✅ 构造 start_dt 在前
                    start_dt = datetime.combine(start_date, start_time)

                    # ✅ 判断是否跨日
                    if end_time <= start_time:
                        end_date = start_date + timedelta(days=1)
                    else:
                        end_date = start_date

                    end_dt = datetime.combine(end_date, end_time)

                    # ✅ 限制跨两天
                    if (end_dt.date() - start_dt.date()).days >= 2:
                        messages.error(request, f"⚠️ 预约 {start_date} ~ {end_date} 跨了两天，系统不允许，请分开预约。")
                        continue

                    # ✅ 限制最长 13 小时
                    duration_hours = (end_dt - start_dt).total_seconds() / 3600
                    if duration_hours > 13:
                        messages.error(request, f"⚠️ {start_date} 的预约时间为 {duration_hours:.1f} 小时，超过限制。")
                        continue

                    # ✅ 夜班限制（可选）
                    if end_date > start_date:
                        if start_time < time(12, 0) or end_time > time(12, 0):
                            messages.error(request, f"⚠️ {start_date} 的跨日预约时间段非法。夜班必须 12:00 后开始，次日 12:00 前结束。")
                            continue

                    # ✅ 检查是否重复预约（当前用户）
                    duplicate_by_same_user = Reservation.objects.filter(
                        vehicle=car,
                        driver=request.user,
                        date__lte=end_dt.date(),
                        end_date__gte=start_dt.date(),
                    ).filter(
                        Q(start_time__lt=end_time) & Q(end_time__gt=start_time)
                    ).exists()
                    if duplicate_by_same_user:
                        messages.warning(request, f"{start_date} 你已预约该车，已跳过。")
                        continue

                    # ✅ 检查是否违反10小时间隔（当前用户）
                    recent_same_vehicle_reservations = Reservation.objects.filter(
                        vehicle=car,
                        driver=request.user,
                    ).only('date', 'start_time').order_by('-date', '-start_time')# 优化性能

                    too_close = False
                    for prev in recent_same_vehicle_reservations:
                        prev_start_dt = datetime.combine(prev.date, prev.start_time)
                        delta_sec = abs((start_dt - prev_start_dt).total_seconds())
                        if delta_sec < 36000:  # 10小时 = 36000秒
                            too_close = True
                            break

                    if too_close:
                        messages.warning(request, f"⚠️ {start_date} 的预约时间与之前预约相隔不足10小时，已跳过。")
                        continue

                    # ✅ 检查是否与其他人预约冲突
                    conflict_exists = Reservation.objects.filter(
                        vehicle=car,
                        date__lte=end_dt.date(),
                        end_date__gte=start_dt.date(),
                        status__in=['reserved', 'out'],
                    ).filter(
                        Q(start_time__lt=end_time) & Q(end_time__gt=start_time)
                    ).exclude(driver=request.user).exists()


                    if conflict_exists:
                        messages.warning(request, f"{start_date} 存在预约冲突，已跳过。")
                        continue

                    # ✅ 创建预约记录
                    new_res = Reservation.objects.create(
                        driver=request.user,
                        vehicle=car,
                        date=start_date,
                        end_date=end_date,
                        start_time=start_time,
                        end_time=end_time,
                        purpose=purpose,
                        status='pending',
                    )

                    created_count += 1

                    # ✅ 邮件通知（可选）
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

            return redirect('vehicle_status')

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
    is_past = is_today and timezone.localtime().time() > time(0, 30)
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

    # 获取目标日期与周偏移
    date_str = request.GET.get('date')
    offset = int(request.GET.get('offset', 0))

    if date_str:
        try:
            base_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            base_date = today
    else:
        base_date = today

    # ✅ 当前周的7天
    start_date = base_date + timedelta(days=offset * 7)
    week_dates = [start_date + timedelta(days=i) for i in range(7)]

    vehicles = Car.objects.all()

    reminders = []
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
                    reminders.append((car, reminder_text))

    # ✅ 只抓取当前周内的相关预约
    reservations = Reservation.objects.filter(
        Q(date__in=week_dates)
    ).select_related('vehicle', 'driver')

    # ✅ 自动取消超时未出库预约
    canceled = []
    for r in reservations.filter(status='reserved', actual_departure__isnull=True):
        start_dt = make_aware(datetime.combine(r.date, r.start_time))
        if timezone.now() > start_dt + timedelta(hours=1):
            r.status = 'canceled'
            r.save()
            if r.driver == request.user:
                canceled.append(r)

    if canceled:
        messages.warning(request, f"你有 {len(canceled)} 条预约因超过1小时未出库已被自动取消，请重新预约。")

    # ✅ 冷却期逻辑
    user_res_today = reservations.filter(
        driver=request.user,
        date=today,
        status__in=['reserved', 'out']
    )
    cooldown_end = None
    if user_res_today.exists():
        last = user_res_today.order_by('-end_date', '-end_time').first()
        end_dt = datetime.combine(last.end_date, last.end_time)
        cooldown_end = end_dt + timedelta(hours=10)

    # ✅ 按车 + 日期分类（仅按 start_date 显示，避免跨日重复）
    vehicle_date_map = defaultdict(lambda: defaultdict(list))
    for res in reservations:
        if res.date in week_dates:
            vehicle_date_map[res.vehicle][res.date].append(res)

    # ✅ 构建每辆车每一天的数据行
    data = []
    for vehicle in vehicles:

        # ✅ 构建该车的每日提醒字典（供模板中按日期查找）
        vehicle.daily_reminders = {}

        for d in week_dates:
            reminders = []
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
                        reminders.append({
                            'type': rtype,
                            'message': msg,
                            'is_today': (delta == 0)
                        })
            if reminders:
                vehicle.daily_reminders[d] = reminders

        # ✅ 原有每周预约构造逻辑
        row = {'vehicle': vehicle, 'days': []}
        for d in week_dates:
            day_reservations = sorted(vehicle_date_map[vehicle][d], key=lambda r: r.start_time)

            if request.user.is_staff:
                is_past = False
            else:
                if d < today:
                    is_past = True
                elif d == today and now_time < time(hour=0, minute=30):
                    is_past = True
                else:
                    is_past = False

            row['days'].append({
                'date': d,
                'reservations': day_reservations,
                'is_past': is_past,
            })

        # ✅ 添加提醒结构到每个 row
        reminders = []
        if vehicle.inspection_date:
            delta = (vehicle.inspection_date - today).days
            if -5 <= delta <= 5:
                reminders.append({
                    'type': 'inspection',
                    'message': f"车检日 {vehicle.inspection_date} 距今 {delta} 天",
                    'is_today': delta == 0
                })

        if vehicle.insurance_end_date:
            delta = (vehicle.insurance_end_date - today).days
            if -5 <= delta <= 5:
                reminders.append({
                    'type': 'insurance',
                    'message': f"保险到期日 {vehicle.insurance_end_date} 距今 {delta} 天",
                    'is_today': delta == 0
                })

        row['reminders'] = reminders
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
        'reminders': reminders,  # ✅ 新增
    })
    
@login_required
def timeline_selector_view(request):
    vehicles = Car.objects.all()

    if request.method == 'POST':
        vehicle_id = request.POST.get('vehicle_id')
        date = request.POST.get('date')
        return HttpResponseRedirect(f"/vehicles/timeline/{vehicle_id}/?date={date}")

    return render(request, 'vehicles/timeline_selector.html', {
        'vehicles': vehicles,
    })

@login_required
def weekly_selector_view(request):
    if request.method == 'POST':
        date = request.POST.get('date')
        return redirect(f"/vehicles/weekly/?start={date}")
    return render(request, 'vehicles/weekly_selector.html')

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
            status__in=['pending', 'reserved', 'out']
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
        elif d == today and now.time() >= time(23, 30):
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
    vehicles = Car.objects.all()
    reservations = Reservation.objects.filter(date=selected_date)

    data = []
    for vehicle in vehicles:
        r = reservations.filter(vehicle=vehicle).first()

        if r:
            item = {'vehicle': vehicle, 'reservation': r}
        else:
            is_today = selected_date == now_dt.date()
            is_past = is_today and now_dt.time() > time(0, 30)

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
    all_reservations = Reservation.objects.filter(
        driver=request.user
    ).order_by('-date', '-start_time')

    # ✅ 自动取消超时未出库的预约
    canceled_any = False
    for r in all_reservations:
        if r.status == 'reserved' and not r.actual_departure:
            start_dt = timezone.make_aware(datetime.combine(r.date, r.start_time))
            expire_dt = start_dt + timedelta(hours=1)
            if timezone.now() > expire_dt:
                r.status = 'canceled'
                r.save()
                canceled_any = True

    # ✅ 计算预约相关时间间隔
    reservation_infos = {}
    for r in all_reservations:
        info = {}

        # 上次入库
        start_dt = datetime.combine(r.date, r.start_time)
        if is_naive(start_dt):
            start_dt = make_aware(start_dt)

        last_return = Reservation.objects.filter(
            driver=r.driver,
            actual_return__isnull=False,
            actual_return__lt=start_dt
        ).order_by('-actual_return').first()

        if last_return:
            last_return_dt = last_return.actual_return
            if is_naive(last_return_dt):
                last_return_dt = make_aware(last_return_dt)

            diff = start_dt - last_return_dt
            info['last_return'] = last_return_dt
            info['diff_from_last_return'] = round(diff.total_seconds() / 3600, 1)

        # 下次预约
        next_res = Reservation.objects.filter(
            driver=r.driver,
            status__in=['pending', 'reserved'],
            date__gt=r.end_date
        ).order_by('date', 'start_time').first()

        if next_res:
            current_end_dt = datetime.combine(r.end_date, r.end_time)
            next_start_dt = datetime.combine(next_res.date, next_res.start_time)

            if is_naive(current_end_dt):
                current_end_dt = make_aware(current_end_dt)
            if is_naive(next_start_dt):
                next_start_dt = make_aware(next_start_dt)

            diff_next = next_start_dt - current_end_dt
            info['next_reservation'] = next_start_dt
            info['diff_to_next'] = round(diff_next.total_seconds() / 3600, 1)

        reservation_infos[r.id] = info

    # 分页
    paginator = Paginator(all_reservations, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    tips = Tip.objects.filter(is_active=True).order_by('-created_at')

    # 仅用于走马灯通知
    notice_message = None
    notice = SystemNotice.objects.filter(is_active=True).order_by('-created_at').first()
    if notice:
        notice_message = notice.message

    # 用于页面内部的 tips（如果你之后还要用）
    tips = Tip.objects.filter(is_active=True).order_by('-created_at')

    return render(request, 'vehicles/my_reservations.html', {
        'page_obj': page_obj,
        'reservations': page_obj,
        'today': timezone.localdate(),
        'now': timezone.localtime(),
        'tips': tips,
        'canceled_any': canceled_any,
        'reservation_infos': reservation_infos,
        'notice_message': notice.message if notice else None,  # ✅ 传入模板
    })

@staff_member_required
def reservation_approval_list(request):
    pending_reservations = Reservation.objects.filter(status='pending').order_by('date', 'start_time')
    return render(request, 'vehicles/reservation_approval_list.html', {
        'pending_reservations': pending_reservations
    })

@staff_member_required
def approve_reservation(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk)

    # ✅ 设置状态为“已预约”
    reservation.status = 'reserved'

    # ✅ 可选：记录审批人和时间（前提是模型中有这些字段）
    if hasattr(reservation, 'approved_by'):
        reservation.approved_by = request.user
    if hasattr(reservation, 'approved_at'):
        reservation.approved_at = timezone.now()

    reservation.save()

    # ✅ 新增：通知司机预约已通过
    notify_driver_reservation_approved(reservation)

    messages.success(request, f"✅ 预约 ID {pk} 已成功审批，并已通知司机。")
    return redirect('reservation_approval_list')

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
    if reservation.actual_departure:
        messages.warning(request, "你已经出库了！")
    else:
        reservation.actual_departure = timezone.now()
        reservation.save()
        messages.success(request, "出库登记成功")
    return redirect('vehicle_status')

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
    return redirect('vehicle_status')

@login_required
def edit_reservation_view(request, reservation_id):
    reservation = get_object_or_404(Reservation, id=reservation_id)

    # ✅ 权限判断：仅本人或管理员可访问
    if reservation.driver != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("⛔️ 无权修改他人预约。")

    # ✅ 状态限制：仅允许修改 pending 或 reserved
    if reservation.status not in ['pending', 'reserved']:
        return HttpResponseForbidden("⛔️ 当前状态不可修改。")

    if request.method == 'POST':
        form = ReservationForm(
            request.POST,
            instance=reservation,
            initial={'date': reservation.date, 'driver': reservation.driver}
        )

        if form.is_valid():
            cleaned = form.cleaned_data
            start_time = cleaned['start_time']
            end_time = cleaned['end_time']
            date = cleaned['date']
            end_date = cleaned['end_date']

            # ✅ 构造起止时间点
            start_dt = datetime.combine(date, start_time)
            end_dt = datetime.combine(end_date, end_time)

            # ✅ 结束时间必须晚于开始时间
            if end_dt <= start_dt:
                messages.error(request, "⚠️ 结束时间必须晚于开始时间")
                return redirect(request.path)

            # ✅ 时长限制（最多13小时）
            duration = (end_dt - start_dt).total_seconds() / 3600
            if duration > 13:
                messages.error(request, "⚠️ 预约时间不得超过13小时。")
                return redirect(request.path)

            # ✅ 若为跨日（夜班），检查是否符合夜班要求
            if end_date > date:
                if start_time < time(12, 0):
                    messages.error(request, "⚠️ 夜班预约的开始时间必须为中午12:00以后。")
                    return redirect(request.path)
                if end_time > time(12, 0):
                    messages.error(request, "⚠️ 夜班预约的结束时间必须为次日中午12:00以前。")
                    return redirect(request.path)

            # ✅ 保存更新
            updated_res = form.save(commit=False)
            if not updated_res.driver:
                updated_res.driver = request.user
            updated_res.date = date
            updated_res.end_date = end_date
            updated_res.save()

            messages.success(request, "✅ 预约已修改")
            return redirect('my_reservations')
    else:
        form = ReservationForm(
            instance=reservation,
            request=request,
            initial={'date': reservation.date, 'driver': reservation.driver}
        )

    return render(request, 'vehicles/edit_reservation.html', {
        'form': form,
        'reservation': reservation,
    })

@login_required
def delete_reservation_view(request, reservation_id):
    reservation = get_object_or_404(Reservation, id=reservation_id, driver=request.user)
    if reservation.status not in ['pending', 'reserved']:
        return HttpResponseForbidden("已确认预约不能删除。")

    if request.method == 'POST':
        reservation.delete()
        return redirect('my_reservations')

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
def confirm_check_io(request):
    reservation_id = request.POST.get("reservation_id")
    action_type = request.POST.get("action_type")
    actual_time_str = request.POST.get("actual_time")

    # ✅ 显式转换为 aware datetime（带时区）
    actual_time = datetime.strptime(actual_time_str, "%Y-%m-%dT%H:%M")
    if timezone.is_naive(actual_time):
        actual_time = timezone.make_aware(actual_time)

    reservation = get_object_or_404(Reservation, id=reservation_id, driver=request.user)

    if action_type == "departure":
        # ✅ 查找上次入库
        last_return = Reservation.objects.filter(
            driver=request.user,
            actual_return__isnull=False,
            actual_return__lt=actual_time
        ).order_by("-actual_return").first()

        if last_return:
            diff = actual_time - last_return.actual_return
            if diff < timedelta(hours=10):
                next_allowed = last_return.actual_return + timedelta(hours=10)
                messages.error(request, f"距上次入库还未满10小时，请于 {next_allowed.strftime('%H:%M')} 后再试出库。")
                return redirect("my_reservations")

        # ✅ 更新状态
        reservation.actual_departure = actual_time
        reservation.status = "out"
        reservation.save()
        messages.success(request, "✅ 出库记录已保存。")
        return redirect("my_reservations")

    elif action_type == "return":
        reservation.actual_return = actual_time

        # ✅ 检查后续预约是否不足 10 小时，自动延后
        next_res = Reservation.objects.filter(
            driver=request.user,
            date__gte=reservation.date,
            status__in=['pending', 'reserved']
        ).exclude(id=reservation.id).order_by("date", "start_time").first()

        if next_res:
            next_start = timezone.make_aware(datetime.combine(next_res.date, next_res.start_time))
            if timezone.is_naive(next_start):
                next_start = timezone.make_aware(next_start)

            if next_start - actual_time < timedelta(hours=10):
                new_start = actual_time + timedelta(hours=10)
                next_res.date = new_start.date()
                next_res.start_time = new_start.time()
                next_res.save()
                messages.warning(request, f"⚠️ 下次预约时间已自动顺延至 {new_start.strftime('%Y-%m-%d %H:%M')}")

        reservation.status = "completed"
        reservation.save()
        messages.success(request, "✅ 入库记录已保存。")
        return redirect("my_reservations")

    else:
        messages.error(request, "❌ 无效的操作类型。")
        return redirect("my_reservations")

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
    vehicles = Car.objects.all()
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
            'show_inspection_warning': show_inspection_warning,
            'show_insurance_warning': show_insurance_warning,
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
        status__in=['out', 'completed'],
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
            status__in=['reserved', 'out', 'completed']
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
        reservation.status = 'reserved'
        reservation.vehicle.status = 'available'
        reservation.vehicle.save()
        reservation.save()
        messages.success(request, f"已撤销出库登记：{reservation}")
    else:
        messages.warning(request, "该预约没有出库记录。")
    return redirect('vehicle_status')


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
    return redirect('vehicle_status')

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
            return redirect('vehicle_status')

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
    # 1. 拿到当前登录用户对应的 Driver
    driver = get_object_or_404(Driver, user=request.user)

    # 2. 如果有 ?date=YYYY-MM-DD，就只看那一天，否则就全部
    selected_date = request.GET.get('date', '').strip()
    today = timezone.localdate()

    # 默认使用当前年月
    try:
        year = int(request.GET.get('year', today.year))
        month = int(request.GET.get('month', today.month))
    except ValueError:
        year = today.year
        month = today.month

    # 只筛选该年月
    qs = DriverDailyReport.objects.filter(
        driver=driver,
        date__year=year,
        date__month=month
    ).order_by('-date')

    # 3. 汇总聚合原始里程费
    agg = (
        DriverDailyReportItem.objects
        .filter(report__in=qs)
        .values('report')
        .annotate(meter_raw=Sum('meter_fee'))
    )
    raw_map = {o['report']: o['meter_raw'] or Decimal('0') for o in agg}

    # 4. 计算每行和总计
    coef = Decimal('0.9091')
    reports_data = []
    total_raw = Decimal('0')

    for rpt in qs:
        raw = raw_map.get(rpt.id, Decimal('0'))
        split = (raw * coef).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        total_raw += raw
        reports_data.append({
            'id':           rpt.id,
            'date':         rpt.date,
            'note':         rpt.note,
            'meter_raw':    raw,
            'meter_split':  split,
        })

    total_split = (total_raw * coef).quantize(Decimal('1'), rounding=ROUND_HALF_UP)

    return render(request, 'vehicles/my_dailyreports.html', {
        'reports_data':      reports_data,
        'total_raw':         total_raw,
        'total_split':       total_split,
        'selected_date':     selected_date,
        'selected_year':     year,     # ✅ 添加
        'selected_month':    month,    # ✅ 添加
        'current_month':     today.strftime("%Y年%-m月"),
    })

@login_required
def my_daily_report_detail(request, report_id):
    report = get_object_or_404(DriverDailyReport, id=report_id, driver__user=request.user)

    # ✅ 找到当天实际出库记录（可能为前一天下午）
    reservation = Reservation.objects.filter(
        driver=request.user,
        actual_departure__lte=make_aware(datetime.combine(report.date, time(12, 0)))
    ).order_by('-actual_departure').first()

    start_time = reservation.actual_departure if reservation else None
    end_time = reservation.actual_return if reservation else None

    duration = None
    if start_time and end_time:
        duration = end_time - start_time

    # ✅ 跨日排序逻辑：根据 ride_time 和出库时间判断是否跨日
    items_raw = report.items.all()

    def parse_ride_datetime(item):
        try:
            ride_time = datetime.strptime(item.ride_time, "%H:%M").time()
            base_date = report.date
            if start_time and ride_time < start_time.time():
                base_date += timedelta(days=1)
            return datetime.combine(base_date, ride_time)
        except Exception:
            return datetime.max  # 排在最后

    items = sorted(items_raw, key=parse_ride_datetime)

    # ✅ 打印付款方式
    print("=== 所有乘车记录付款方式 ===")
    for item in items:
        print(f"- {item.ride_time} | 金額: {item.meter_fee} | 支付: {item.payment_method}")
    print("=== END ===")

    # ✅ 现金总额（基于排序后的 items，保持一致）
    total_cash = sum(
        Decimal(item.meter_fee or 0)
        for item in items
        if item.payment_method and "cash" in item.payment_method.lower()
    )

    deposit = report.deposit_amount or Decimal("0")
    deposit_diff = deposit - total_cash
    is_deposit_exact = (deposit_diff == 0)

    print("所有明细付款方式：")
    for item in items:
        print("-", item.payment_method, ":", item.meter_fee)

    return render(request, 'vehicles/my_daily_report_detail.html', {
        'report': report,
        'items': items,
        'start_time': start_time,
        'end_time': end_time,
        'duration': duration,
        'total_cash': total_cash,
        'deposit': deposit,
        'deposit_diff': deposit_diff,
        'is_deposit_exact': is_deposit_exact,
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