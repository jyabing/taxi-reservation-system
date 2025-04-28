import calendar
from calendar import monthrange
from django.utils import timezone
from django.db.models import Q
from datetime import datetime, timedelta, time, date  # ✅ 一起导入

from django.shortcuts import render, get_object_or_404, redirect  # ✅ 一起导入
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponseRedirect
from django.core.mail import send_mail

from .models import Vehicle, Reservation
from .forms import ReservationForm
from django.views.decorators.http import require_POST
#把 import 语句分类整理在一起，是一个非常好的编码习惯，不仅让代码更清晰，也能减少重复导入或顺序错误的情况。

def vehicle_list(request):
    vehicles = Vehicle.objects.all()
    return render(request, 'vehicles/vehicle_list.html', {'vehicles': vehicles})

def vehicle_status_view(request):
    date_str = request.GET.get('date')
    if date_str:
        selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    else:
        selected_date = timezone.localdate()

    reservations = Reservation.objects.filter(date=selected_date)
    vehicles = Vehicle.objects.all()

    status_map = {}

    for vehicle in vehicles:
        # 该车的所有预约记录
        r = reservations.filter(vehicle=vehicle).first()
        status = r.status if r else 'available'

        # 当前用户自己的预约（如果有）
        user_res = reservations.filter(vehicle=vehicle, driver=request.user).first()

        # 保存状态和用户预约记录
        status_map[vehicle] = {
            'status': status,
            'user_reservation': user_res,
        }

    return render(request, 'vehicles/status_view.html', {
        'selected_date': selected_date,
        'status_map': status_map,
    })

@login_required
def vehicle_timeline_view(request, vehicle_id):
    date_str = request.GET.get('date')
    if date_str:
        selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    else:
        selected_date = timezone.localdate()

    vehicle = get_object_or_404(Vehicle, id=vehicle_id)
    reservations = Reservation.objects.filter(vehicle=vehicle, date=selected_date).order_by('start_time')

    return render(request, 'vehicles/timeline_view.html', {
        'vehicle': vehicle,
        'selected_date': selected_date,
        'reservations': reservations,
    })

@login_required
def make_reservation_view(request, vehicle_id):
    vehicle = get_object_or_404(Vehicle, id=vehicle_id)

    if request.method == 'POST':
        form = ReservationForm(request.POST)
        if form.is_valid():
            cleaned = form.cleaned_data
            start_dt = datetime.combine(cleaned['date'], cleaned['start_time'])
            end_dt = datetime.combine(cleaned['end_date'], cleaned['end_time'])

            if end_dt <= start_dt:
                messages.error(request, "结束时间必须晚于开始时间（请检查跨日设置）")
                return render(request, 'vehicles/reservation_form.html', {'vehicle': vehicle, 'form': form})
            else:
                # === 前后缓冲时间段 ===
                buffer_start = start_dt - timedelta(minutes=30)
                buffer_end = end_dt + timedelta(minutes=30)

                # === 1. 检查：车辆在该时间段是否已有预约 ===
                conflict = Reservation.objects.filter(
                    vehicle=vehicle,
                    date__lte=cleaned['end_date'],
                    end_date__gte=cleaned['date'],
                    start_time__lt=cleaned['end_time'],
                    end_time__gt=cleaned['start_time'],
                    status__in=['pending', 'reserved', 'out']
                ).exists()

                if conflict:
                    messages.error(request, "该时间段内该车辆已有预约，不能重复申请")
                else:
                    # === 2. 检查：同一人预约不同车辆是否间隔 ≥10小时 ===
                    other_reservations = Reservation.objects.filter(
                        driver=request.user,
                        date__lte=cleaned['end_date'],
                        end_date__gte=cleaned['date'],
                    ).exclude(vehicle=vehicle)

                    for r in other_reservations:
                        r_start = datetime.combine(r.date, r.start_time)
                        r_end = datetime.combine(r.end_date, r.end_time)

                        # 1. 判断时间段是否重叠
                        if (start_dt < r_end and end_dt > r_start):
                            messages.error(request, "您在此时间段已预约了其他车辆，不能重叠预约。")
                            break

                        # 2. 判断是否间隔不足10小时
                        gap_start = abs((start_dt - r_end).total_seconds())
                        gap_end = abs((end_dt - r_start).total_seconds())
                        if gap_start < 10 * 3600 or gap_end < 10 * 3600:
                            messages.error(request, "您预约了多辆车，间隔必须至少 10 小时。")
                            break
                    else:
                        # === 保存预约 ===
                        new_reservation = form.save(commit=False)
                        new_reservation.vehicle = vehicle
                        new_reservation.driver = request.user
                        new_reservation.status = 'pending'
                        new_reservation.save()
                        messages.success(request, "已提交申请，等待审批")
                        return redirect('vehicle_status')
    else:
        # === 预填表单参数 ===
        initial = {
            'date': request.GET.get('date', ''),
            'start_time': request.GET.get('start', ''),
            'end_date': request.GET.get('end_date', ''),
            'end_time': request.GET.get('end', ''),
        }
        form = ReservationForm(initial=initial)

    return render(request, 'vehicles/reservation_form.html', {
        'vehicle': vehicle,
        'form': form
    })

@staff_member_required  # 限制管理员访问
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
def check_out(request, reservation_id):
    reservation = get_object_or_404(Reservation, id=reservation_id)

    if request.user != reservation.driver:
        return HttpResponseForbidden("你不能操作别人的预约")

    if reservation.actual_departure:
        messages.warning(request, "你已经出车过了！")
    else:
        reservation.actual_departure = timezone.now()
        reservation.save()
        messages.success(request, "出车登记成功")

    return redirect('vehicle_status')

@login_required
def check_in(request, reservation_id):
    reservation = get_object_or_404(Reservation, id=reservation_id)

    if request.user != reservation.driver:
        return HttpResponseForbidden("你不能操作别人的预约")

    if not reservation.actual_departure:
        messages.warning(request, "请先出车登记")
    elif reservation.actual_return:
        messages.warning(request, "你已经还车过了！")
    else:
        reservation.actual_return = timezone.now()
        reservation.save()
        messages.success(request, "还车登记成功")

    return redirect('vehicle_status')

@login_required
def weekly_overview_view(request):
    today = timezone.localdate()

    # 获取当前周的开始日期（周一）
    weekday = today.weekday()  # 0: Monday
    monday = today - timedelta(days=weekday)

    # 支持切换周
    offset = int(request.GET.get('offset', 0))
    monday += timedelta(weeks=offset)

    week_dates = [monday + timedelta(days=i) for i in range(7)]
    vehicles = Vehicle.objects.all()
    reservations = Reservation.objects.filter(date__in=week_dates)

    data = []
    for vehicle in vehicles:
        row = {'vehicle': vehicle, 'days': []}
        for date in week_dates:
            r = reservations.filter(vehicle=vehicle, date=date).first()
            row['days'].append(r)
        data.append(row)

    return render(request, 'vehicles/weekly_view.html', {
        'week_dates': week_dates,
        'vehicle_data': data,
        'offset': offset,
    })

@login_required
def timeline_selector_view(request):
    vehicles = Vehicle.objects.all()

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
    vehicle = get_object_or_404(Vehicle, id=vehicle_id)

    # 1. 读 ?date=YYYY-MM，否则用今天
    month_str = request.GET.get('date')  # e.g. "2025-04"
    if month_str:
        try:
            year, month = map(int, month_str.split('-'))
        except ValueError:
            today = date.today()
            year, month = today.year, today.month
    else:
        today = date.today()
        year, month = today.year, today.month

    # 2. 计算本月第一天 和 上／下个月的第一天
    current_month = date(year, month, 1)
    if month == 1:
        prev_month = date(year - 1, 12, 1)
    else:
        prev_month = date(year, month - 1, 1)
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)

    # 3. 本月天数
    days_in_month = monthrange(year, month)[1]

    # 4. 构造甘特图矩阵
    matrix = []
    for day in range(1, days_in_month + 1):
        d = date(year, month, day)
        qs = Reservation.objects.filter(
            vehicle=vehicle,
            date__lte=d,
            end_date__gte=d,
            status__in=['pending', 'reserved', 'out']
        ).order_by('start_time')

        segments = []
        for r in qs:
            start_dt = max(datetime.combine(r.date, r.start_time),
                           datetime.combine(d, time.min))
            end_dt   = min(datetime.combine(r.end_date, r.end_time),
                           datetime.combine(d, time.max))
            start_offset = (start_dt - datetime.combine(d, time.min)).total_seconds() / 3600
            length = (end_dt - start_dt).total_seconds() / 3600
            segments.append({
                'start': start_offset,
                'length': length,
                'status': r.status,
                'label': f"{r.driver.username} {r.start_time}-{r.end_time}"
            })

        matrix.append({'date': d, 'segments': segments})

    hours = list(range(24))

    return render(request, 'vehicles/monthly_gantt.html', {
        'vehicle': vehicle,
        'matrix': matrix,
        'hours': hours,
        'current_month': current_month,
        'prev_month': prev_month,
        'next_month': next_month,
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

    vehicles = Vehicle.objects.all()
    reservations = Reservation.objects.filter(date=selected_date)

    data = []
    for vehicle in vehicles:
        r = reservations.filter(vehicle=vehicle).first()
        data.append({'vehicle': vehicle, 'reservation': r})

    return render(request, 'vehicles/daily_view.html', {
        'selected_date': selected_date,
        'data': data,
    })

@login_required
def reservation_dashboard(request):
    return render(request, 'vehicles/reservation_dashboard.html')

@login_required
def my_reservations_view(request):
    reservations = Reservation.objects.filter(driver=request.user).order_by('-date')
    today = timezone.localdate()
    now = timezone.localtime()  # ✅ 当前时间（包含小时分钟）
    return render(request, 'vehicles/my_reservations.html', {
        'reservations': reservations,
        'today': today,
        'now': now
    })

@login_required 
def test_email_view(request): 
    send_mail( 
        subject='📮 测试邮件 - 车辆预约系统', 
        message='这是一个测试邮件，说明邮件设置成功！', 
        from_email=None, recipient_list=[request.user.email], # 发送给当前登录用户   
        fail_silently=False, 
    ) 
    return HttpResponse("✅ 邮件已发送至：" + request.user.email)

@login_required
def reservation_detail_view(request, reservation_id):
    reservation = get_object_or_404(Reservation, id=reservation_id)
    return render(request, 'vehicles/reservation_detail.html', {
        'reservation': reservation
    })

@login_required
def vehicle_detail_view(request, vehicle_id):
    vehicle = get_object_or_404(Vehicle, id=vehicle_id)
    reservations = Reservation.objects.filter(vehicle=vehicle).order_by('-date')[:5]
    return render(request, 'vehicles/vehicle_detail.html', {
        'vehicle': vehicle,
        'reservations': reservations
    })

@login_required
def edit_reservation_view(request, reservation_id):
    reservation = get_object_or_404(Reservation, id=reservation_id, driver=request.user)
    if reservation.status != 'pending':
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
    if reservation.status != 'pending':
        return HttpResponseForbidden("已确认预约不能删除。")

    if request.method == 'POST':
        reservation.delete()
        return redirect('my_reservations')

    return render(request, 'vehicles/reservation_confirm_delete.html', {
        'reservation': reservation
    })

@require_POST
@login_required
def confirm_check_io(request):
    reservation_id = request.POST.get('reservation_id')
    action_type = request.POST.get('action_type')  # 'departure' or 'return'
    actual_time = request.POST.get('actual_time')

    reservation = get_object_or_404(Reservation, id=reservation_id, driver=request.user)

    # 必须是状态为已预约才能登记出入库
    if reservation.status != 'reserved':
        return HttpResponseForbidden("当前预约不允许操作出入库")

    try:
        dt = timezone.datetime.fromisoformat(actual_time)
        dt = timezone.make_aware(dt) if timezone.is_naive(dt) else dt
    except Exception as e:
        messages.error(request, "时间格式错误")
        return redirect('my_reservations')

    if action_type == 'departure' and not reservation.actual_departure:
        reservation.actual_departure = dt
        messages.success(request, "🚗 实际出库时间已登记")
    elif action_type == 'return' and not reservation.actual_return:
        reservation.actual_return = dt
        messages.success(request, "🅿️ 实际还车时间已登记")
    else:
        messages.warning(request, "无法处理该操作")

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
    vehicles = Vehicle.objects.all()
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

def home_view(request):
    return render(request, 'home.html')