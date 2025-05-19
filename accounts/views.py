from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import PasswordChangeView
from django.urls import reverse_lazy
from vehicles.models import CarouselImage, Tip

User = get_user_model()

def home_view(request):
    # 查询所有“启用”的轮播图，并按照 order 排序
    carousel_images = CarouselImage.objects.filter(is_active=True).order_by('order')
    return render(request, 'home.html', {
        'carousel_images': carousel_images,  # 传给模板的上下文名
    })

def login_view(request):
    context = {}
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        context['username'] = username  # 保持输入的用户名回传给前端

        if not username or not password:
            messages.error(request, "请输入用户名和密码")
        else:
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                messages.error(request, "用户名不存在")
            else:
                user = authenticate(request, username=username, password=password)
                if user is not None:
                    login(request, user)
                    if user.is_superuser:
                        return redirect('/admin/')
                    elif user.is_staff:
                        return redirect('admin_dashboard')
                    else:
                        return redirect('driver_dashboard')
                else:
                    messages.error(request, "密码错误")

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
def profile_view(request):
    return render(request, 'accounts/profile.html')

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
