import calendar, requests, random, os
from calendar import monthrange
from datetime import datetime, timedelta, time, date

from django import forms
from decimal import Decimal, ROUND_HALF_UP
from accounts.utils import check_module_permission

from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponseRedirect, HttpResponseForbidden, HttpResponse
from django.utils import timezone
from django.urls import reverse
from django.utils.timezone import now, make_aware, localdate
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.conf import settings
from django.core.paginator import Paginator
from carinfo.models import Car

from django.db.models import F, ExpressionWrapper, DurationField, Sum
from django.views.decorators.csrf import csrf_exempt

from .models import Reservation, Tip
from .forms import ReservationForm, MonthForm, AdminStatsForm
from accounts.models import DriverUser
from requests.exceptions import RequestException

# 导入 Driver/DriverDailyReport（已确保在 staffbook 里定义！）
from staffbook.models import Driver, DriverDailyReport, DriverDailyReportItem
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
    date_str = request.GET.get('date')
    selected_date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else timezone.localdate()
    reservations = Reservation.objects.filter(date=selected_date)
    vehicles = Car.objects.all()
    status_map = {}
    now_dt = timezone.localtime()

    for vehicle in vehicles:
        res_list = reservations.filter(vehicle=vehicle).order_by('start_time')

        # ✅ 如果是过去的日期，则不能预约
        if selected_date < timezone.localdate():
            status = 'expired'
        else:
            status = 'available'

        # 是否有出库中
        active = res_list.filter(
            status='out', actual_departure__isnull=False, actual_return__isnull=True
        )
        if active.exists():
            status = 'out'
        else:
            # 是否有未出库的预约
            future_reserved = res_list.filter(status='reserved', actual_departure__isnull=True)
            for r in future_reserved:
                start_dt = timezone.make_aware(datetime.combine(r.date, r.start_time))
                expire_dt = start_dt + timedelta(hours=1)
                if now_dt > expire_dt:
                    r.status = 'canceled'
                    r.save()
                    if r.driver == request.user:
                        messages.warning(request, f"你对 {vehicle.license_plate} 的预约因超时未出库已被自动取消，请重新预约。")
                else:
                    status = 'reserved'
                    break

        # 当前登录用户的预约记录（用于按钮）
        user_reservation = res_list.filter(driver=request.user).first()

        # 新增：查找当日该车的预约者姓名（取第一条预约）
        #r = res_list.first()
        #reserver_name = r.driver.get_full_name() if r else ''
        names = res_list.values_list('driver__first_name', 'driver__last_name')
        #reserver_names = []
        reserver_labels = []
        for r in res_list:
            name = (r.driver.first_name or '') + (r.driver.last_name or '')
            label = f"{r.start_time.strftime('%H:%M')}~{r.end_time.strftime('%H:%M')} {name}"
            reserver_labels.append(label)
        reserver_name = '<br>'.join(reserver_labels) if reserver_labels else ''        

        status_map[vehicle] = {
            'status': status,
            'user_reservation': user_reservation,
            'reserver_name': reserver_name,
        }

    return render(request, 'vehicles/status_view.html', {
        'selected_date': selected_date,
        'status_map': status_map,
        'today': localdate(),  # ✅ 加上 today 给模板组件比较
    })

@login_required
def make_reservation_view(request, vehicle_id):
    vehicle = get_object_or_404(Car, id=vehicle_id)
    min_time = (timezone.now() + timedelta(minutes=30)).strftime('%Y-%m-%dT%H:%M')
    if vehicle.status == 'maintenance':
        messages.error(request, "维修中车辆不可预约")
        return redirect('vehicle_status')

    allow_submit = vehicle.status == 'available'
    if request.method == 'POST':
        if not allow_submit:
            messages.error(request, "当前车辆状态不可预约，请选择其他车辆")
            return redirect('vehicle_status')

        form = ReservationForm(request.POST)
        form.instance.driver = request.user
        if form.is_valid():
            cleaned = form.cleaned_data
            start_dt = datetime.combine(cleaned['date'], cleaned['start_time'])
            end_dt = datetime.combine(cleaned['end_date'], cleaned['end_time'])
            if end_dt <= start_dt:
                messages.error(request, "结束时间必须晚于开始时间（请检查跨日设置）")
            else:
                new_res = form.save(commit=False)
                new_res.vehicle = vehicle
                new_res.status = 'pending'
                new_res.save()
                notify_admin_about_new_reservation(new_res)  # 邮件通知
                messages.success(request, "已提交申请，等待审批")
                return redirect('vehicle_status')
    else:
        initial = {
            'date': request.GET.get('date', ''),
            'start_time': request.GET.get('start', ''),
            'end_date': request.GET.get('end_date', ''),
            'end_time': request.GET.get('end', ''),
        }
        form = ReservationForm(initial=initial)
    return render(request, 'vehicles/reservation_form.html', {
        'vehicle': vehicle,
        'form': form,
        'min_time': min_time,
        'allow_submit': allow_submit,
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

    # ✅ 新规则：以 base_date 为“第1天”，向后生成7天
    start_date = base_date + timedelta(days=offset * 7)
    week_dates = [start_date + timedelta(days=i) for i in range(7)]

    vehicles = Car.objects.all()
    reservations = Reservation.objects.filter(date__in=week_dates)

    # 自动取消超时未出库预约
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

    # 冷却期
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

    # 构建每辆车的每一天数据
    data = []
    for vehicle in vehicles:
        row = {'vehicle': vehicle, 'days': []}
        for d in week_dates:
            day_reservations = reservations.filter(vehicle=vehicle, date=d).order_by('start_time')
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
        data.append(row)

    return render(request, 'vehicles/weekly_view.html', {
        'week_dates': week_dates,
        'vehicle_data': data,
        'offset': offset,
        'now_dt': now_dt,
        'now_time': now_time,
        'cooldown_end': cooldown_end,
        'today': base_date,  # ✅ 注意：这里要传 base_date 给模板用
        'selected_date': date_str if date_str else today.strftime("%Y-%m-%d"),
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

    # ✅ 处理“超时未出库”的预约
    canceled_any = False
    for r in all_reservations:
        if r.status == 'reserved' and not r.actual_departure:
            start_dt = timezone.make_aware(datetime.combine(r.date, r.start_time))
            expire_dt = start_dt + timedelta(hours=1)
            if timezone.now() > expire_dt:
                r.status = 'canceled'
                r.save()
                canceled_any = True

    # 分页
    paginator = Paginator(all_reservations, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    all_tips = Tip.objects.filter(is_active=True).order_by('-created_at')
    tips = [tip for tip in all_tips if tip.is_visible(request.user)]

    return render(request, 'vehicles/my_reservations.html', {
        'page_obj': page_obj,
        'reservations': page_obj,
        'today': timezone.localdate(),
        'now': timezone.localtime(),
        'tips': tips,
        'canceled_any': canceled_any,  # ✅ 传给模板
    })

@staff_member_required
def reservation_approval_list(request):
    pending_reservations = Reservation.objects.filter(status='pending').order_by('date', 'start_time')
    return render(request, 'vehicles/reservation_approval_list.html', {
        'pending_reservations': pending_reservations
    })

@staff_member_required
def approve_reservation(request, reservation_id):
    reservation = get_object_or_404(Reservation, id=reservation_id)
    reservation.status = 'reserved'
    reservation.save()
    messages.success(request, f"预约 {reservation} 审批通过")
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
def my_reservations_view(request):
    all_reservations = Reservation.objects.filter(driver=request.user).order_by('-date', '-start_time')
    paginator = Paginator(all_reservations, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    tips = list(Tip.objects.filter(is_active=True).values('content'))
    return render(request, 'vehicles/my_reservations.html', {
        'page_obj': page_obj,
        'reservations': page_obj,
        'today': timezone.localdate(),
        'now': timezone.localtime(),
        'tips': tips,
    })

@login_required
def edit_reservation_view(request, reservation_id):
    reservation = get_object_or_404(Reservation, id=reservation_id, driver=request.user)
    if reservation.status not in ['pending', 'reserved']:
        return HttpResponseForbidden("已确认预约无法修改。")

    if request.method == 'POST':
        form = ReservationForm(request.POST, instance=reservation)
        if form.is_valid():
            cleaned = form.cleaned_data
            start_dt = datetime.combine(cleaned['date'], cleaned['start_time'])
            end_dt = datetime.combine(cleaned['end_date'], cleaned['end_time'])
            if end_dt <= start_dt:
                messages.error(request, "结束时间必须晚于开始时间")
            else:
                form.save()
                messages.success(request, "预约已修改")
                return redirect('my_reservations')
    else:
        form = ReservationForm(instance=reservation)

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
    reservation_id = request.POST.get('reservation_id')
    action = request.POST.get('action_type')       # 'departure' 或 'return'
    actual_time = request.POST.get('actual_time')  # ISO格式 '2025-06-17T12:30'

    reservation = get_object_or_404(Reservation, id=reservation_id, driver=request.user)

    try:
        dt = timezone.datetime.fromisoformat(actual_time)
        dt = timezone.make_aware(dt) if timezone.is_naive(dt) else dt
    except Exception:
        messages.error(request, "时间格式错误")
        return redirect('my_reservations')

    if action == 'departure':
        if reservation.status != 'reserved':
            return HttpResponseForbidden("当前预约不允许出库登记")
        reservation.actual_departure = dt
        reservation.status = 'out'
        reservation.vehicle.status = 'out'
        messages.success(request, "🚗 实际出库时间已登记，状态更新为“出库中”")
    elif action == 'return':
        if reservation.status != 'out':
            return HttpResponseForbidden("当前预约不允许入库登记")
        reservation.actual_return = dt
        reservation.status = 'completed'
        reservation.vehicle.status = 'available'
        messages.success(request, "🅿️ 实际入库时间已登记，预约完成，车辆空闲中")
    else:
        return HttpResponseForbidden("未知操作类型")

    reservation.vehicle.save()
    reservation.save()
    return redirect('my_reservations')

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

    for vehicle in vehicles:
        r = reservations.filter(vehicle=vehicle).first()
        if r:
            status = r.status
            user_reservation = r if r.driver == request.user else None
        else:
            status = 'available'
            user_reservation = None

        status_map[vehicle] = {
            'status': status,
            'user_reservation': user_reservation
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
    from staffbook.models import DriverDailyReportItem  # <--- 新增或提前导入

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

def create_reservation(request):
    return render(request, 'vehicles/create_reservation.html')

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

    reservation = Reservation.objects.filter(
        driver=request.user,
        actual_departure__date=report.date
    ).order_by('actual_departure').first()

    start_time = reservation.actual_departure if reservation else None
    end_time = reservation.actual_return if reservation else None
    duration = None
    if start_time and end_time:
        duration = end_time - start_time

    return render(request, 'vehicles/my_daily_report_detail.html', {
        'report': report,
        'start_time': start_time,
        'end_time': end_time,
        'duration': duration,
    })