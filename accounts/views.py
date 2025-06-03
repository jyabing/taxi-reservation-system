from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import PasswordChangeView
from django.urls import reverse_lazy
from vehicles.models import CarouselImage, Tip
from django.utils.timezone import localdate
from staffbook.forms import DriverReportImageForm, DriverDailyReportForm
from staffbook.models import DriverDailyReport, DriverReportImage, DriverDailySales
from staffbook.utils import extract_text_from_image
from datetime import datetime
from calendar import monthrange
import re

OCR_API_KEY = 'K85459002688957'

User = get_user_model()

@login_required(login_url='/accounts/login/')
def home_view(request):
    user = request.user
    if user.is_superuser:
        return redirect('/admin/')
    elif user.is_staff:
        return redirect('admin_dashboard')  # 系统总览页
    else:
        return redirect('driver_dashboard')  # 配车首页（普通用户）或你配车首页的 name

def login_view(request):
    context = {}
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        context['username'] = username

        if not username or not password:
            messages.error(request, "请输入用户名和密码")
        else:
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                return redirect('home')  # 让 home_view 负责分流
            else:
                messages.error(request, "用户名或密码错误")
    return render(request, 'registration/login.html', context)
        
@login_required
def logout_view(request):
    logout(request)
    return redirect('login')

@login_required
def admin_dashboard(request):
    return render(request, 'accounts/admin_dashboard.html')

@login_required
def driver_dashboard(request):
    user = request.user
    staff_type = "正式员工" if user.is_formal else "临时工" if user.is_temporary else "未知身份"
    tips = list(Tip.objects.filter(is_active=True).values('content'))
    return render(request, 'accounts/dashboard.html', {
        'user': user,
        'staff_type': staff_type,
    })

@login_required
def edit_profile(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        if email:
            request.user.email = email
            request.user.save()
            messages.success(request, "邮箱地址已更新")
            return redirect('edit_profile')
        else:
            messages.error(request, "请输入有效的邮箱地址")
    return render(request, 'accounts/edit_profile.html')

class MyPasswordChangeView(PasswordChangeView):
    template_name = 'registration/password_change_form.html'
    success_url = reverse_lazy('profile')  # 修改成功后跳回个人资料页

@login_required
def login_success_view(request):
    user = request.user
    if user.is_superuser:
        return redirect('/admin/')
    elif user.is_staff:
        return redirect('admin_dashboard')
    else:
        return redirect('driver_dashboard')

@login_required
def profile_view(request):
    today = localdate()
    driver = getattr(request.user, "driver_profile", None)
    if not driver:
        return render(request, 'accounts/profile_error.html', {'message': '未绑定司机资料，请联系管理员'})

    # 获取或创建今日日报
    report, _ = DriverDailyReport.objects.get_or_create(
        driver=driver,
        date=today,
        defaults={
            'fare': 0,
            'time': '',
            'payment_method': '',
            'note': '',
        }
    )
    daily_form = DriverDailyReportForm(instance=report)

    # 获取今日是否上传图片
    image_uploaded = DriverReportImage.objects.filter(driver=driver, date=today).first()
    image_form = DriverReportImageForm()

    if request.method == 'POST':
        if 'upload_image' in request.POST:
            image_form = DriverReportImageForm(request.POST, request.FILES)
            if image_form.is_valid():
                img, created = DriverReportImage.objects.get_or_create(driver=driver, date=today)
                img.image = image_form.cleaned_data['image']
                img.save()
                messages.success(request, "图片上传成功" + ("（已更新原图）" if not created else ""))
                return redirect('profile')

        elif 'submit_daily' in request.POST:
            daily_form = DriverDailyReportForm(request.POST, instance=report)
            if daily_form.is_valid():
                daily_form.save()
                messages.success(request, "日報信息保存成功")
                return redirect('profile')

    return render(request, 'accounts/profile.html', {
        'daily_report_form': daily_form,
        'image_form': image_form,
        'image_uploaded': image_uploaded,
    })

@login_required
def monthly_reports_view(request):
    driver = request.user
    today = localdate()

    # 获取 URL 参数 ?month=2025-05
    month_str = request.GET.get('month', today.strftime('%Y-%m'))
    try:
        selected_month = datetime.strptime(month_str, '%Y-%m')
    except ValueError:
        selected_month = today

    # 获取该月起止日期
    first_day = selected_month.replace(day=1)
    last_day = selected_month.replace(day=monthrange(selected_month.year, selected_month.month)[1])

    # 查找日报 & 销售记录
    reports = DriverDailyReport.objects.filter(driver=driver, date__range=(first_day, last_day)).order_by('date')
    sales_map = {
        s.date: s for s in DriverDailySales.objects.filter(driver=driver, date__range=(first_day, last_day))
    }

    return render(request, 'accounts/monthly_reports.html', {
        'selected_month': selected_month,
        'reports': reports,
        'sales_map': sales_map,
    })