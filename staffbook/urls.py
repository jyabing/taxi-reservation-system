# taxi_project/staffbook/urls.py
from django.urls import path
from . import views

app_name = 'staffbook'

urlpatterns = [
    # -----------------------------------
    # 📘 员工基本信息与履历
    # -----------------------------------
    path('dashboard/', views.staffbook_dashboard, name='dashboard'),
    path('drivers/', views.driver_list, name='driver_list'),
    # 🔻✅ 新增这一行：资料未提交一览
    path('driver_documents/', views.driver_documents_status, name='driver_documents_status'),

    path('drivers/create/', views.driver_create, name='driver_create'),
    path('drivers/<int:driver_id>/edit/', views.driver_edit, name='driver_edit'),
    
    # 👉 基本资料页分组（主页、证件、紧急联系人等）
    path('drivers/<int:driver_id>/basic/', views.driver_basic_info, name='driver_basic_info'),
    path('drivers/<int:driver_id>/basic/edit/', views.driver_basic_edit, name='driver_basic_edit'),
    path('drivers/<int:driver_id>/personal/', views.driver_personal_info, name='driver_personal_info'),
    path('drivers/<int:driver_id>/personal/edit/', views.driver_personal_edit, name='driver_personal_edit'),
    path('drivers/<int:driver_id>/certificate/', views.driver_certificate_info, name='driver_certificate_info'),
    path('drivers/<int:driver_id>/certificate/edit/', views.driver_certificate_edit, name='driver_certificate_edit'),
    path('drivers/<int:driver_id>/emergency/', views.driver_emergency_info, name='driver_emergency_info'),
    path('drivers/<int:driver_id>/emergency/edit/', views.driver_emergency_edit, name='driver_emergency_edit'),
    path('drivers/<int:driver_id>/history/', views.driver_history_info, name='driver_history_info'),
    path('drivers/<int:driver_id>/history/edit/', views.driver_history_edit, name='driver_history_edit'),

    # 👉 驾驶信息（经验、驾照、资格等）
    path('drivers/<int:driver_id>/experience/', views.driver_experience_info, name='driver_experience_info'),
    path('drivers/<int:driver_id>/experience/edit/', views.driver_experience_edit, name='driver_experience_edit'),
    path('drivers/<int:driver_id>/license/', views.driver_license_info, name='driver_license_info'),
    path('drivers/<int:driver_id>/license/edit/', views.driver_license_edit, name='driver_license_edit'),
    path('drivers/<int:driver_id>/qualification/', views.driver_qualification_info, name='driver_qualification_info'),
    path('drivers/<int:driver_id>/qualification/edit/', views.driver_qualification_edit, name='driver_qualification_edit'),
    path('drivers/<int:driver_id>/aptitude/', views.driver_aptitude_info, name='driver_aptitude_info'),
    path('drivers/<int:driver_id>/aptitude/edit/', views.driver_aptitude_edit, name='driver_aptitude_edit'),
    path('drivers/<int:driver_id>/rewards/', views.driver_rewards_info, name='driver_rewards_info'),
    path('drivers/<int:driver_id>/rewards/edit/', views.driver_rewards_edit, name='driver_rewards_edit'),
    path('drivers/<int:driver_id>/accident/', views.driver_accident_info, name='driver_accident_info'),
    path('drivers/<int:driver_id>/accident/edit/', views.driver_accident_edit, name='driver_accident_edit'),
    path('drivers/<int:driver_id>/education/', views.driver_education_info, name='driver_education_info'),
    path('drivers/<int:driver_id>/education/edit/', views.driver_education_edit, name='driver_education_edit'),

    # 👉 健康・保险・工资等
    path('drivers/<int:driver_id>/health/', views.driver_health_info, name='driver_health_info'),
    path('drivers/<int:driver_id>/health/edit/', views.driver_health_edit, name='driver_health_edit'),
    path('drivers/<int:driver_id>/pension/', views.driver_pension_info, name='driver_pension_info'),
    path('drivers/<int:driver_id>/health_insurance/', views.driver_health_insurance_info, name='driver_health_insurance_info'),
    path('drivers/<int:driver_id>/employment_insurance/', views.driver_employment_insurance_info, name='driver_employment_insurance_info'),
    path('drivers/<int:driver_id>/tax/', views.driver_tax_info, name='driver_tax_info'),
    path('drivers/<int:driver_id>/salary/', views.driver_salary, name='driver_salary'),

    # ===================================
    # 🚗 这里开始是我们这次加的“约日期系统”入口
    # ===================================
    # 🚗 司机本人填写“出勤日・希望車両”
    path('schedule/', views.schedule_form_view, name='schedule_form'),

    # 🚗 司机本人查看自己的预约（旧名字保留，别删，页面可能有引用）
    path('my_reservations/', views.my_reservations_view, name='my_reservations'),

    # ✅ 管理员查看所有司机的预约/希望
    path("schedule-admin/", views.schedule_list_view, name="schedule_list"),
]
