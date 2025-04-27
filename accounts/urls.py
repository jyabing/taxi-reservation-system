from django.urls import path
from django.contrib.auth import views as auth_views
from .views import (
    login_view, logout_view, login_success_view,
    driver_dashboard, profile_view, edit_profile,
    admin_dashboard, MyPasswordChangeView,
)

urlpatterns = [
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('login/success/', login_success_view, name='login_success'),   # ← 这一行必须有

    path('admin_dashboard/', admin_dashboard, name='admin_dashboard'),
    path('dashboard/', driver_dashboard, name='driver_dashboard'),
    
    path('profile/', profile_view, name='profile'),
    path('profile/edit/', edit_profile, name='edit_profile'),

    path('password/change/', MyPasswordChangeView.as_view(), name='change_password'),
]