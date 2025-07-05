from django.urls import path
from . import views

app_name = 'staffbook'

urlpatterns = [

    # -----------------------------------
    # 📋 日报功能（所有日报相关）
    # -----------------------------------

    # 日报总览 / 列表 / 导出
    path('dailyreports/', views.dailyreport_list, name='dailyreport_list'),  # 所有日报（管理员或司机）
    path('dailyreports/overview/', views.dailyreport_overview, name='dailyreport_overview'),
    path('dailyreports/export/', views.export_dailyreports_csv, name='export_dailyreports_csv'),

    # ✅ ✅ ✅ 这行必须存在
    path('monthly_summary/export/', views.export_monthly_summary_csv, name='export_monthly_summary_csv'),

    path('my_dailyreports/', views.my_dailyreports, name='my_dailyreports'),  # 当前用户

    # 管理员：直接新增日报（旧方式）→ 建议改路径避免冲突
    path('dailyreports/add/', views.dailyreport_create, name='dailyreport_add'),

    # 管理员：编辑/更新日报（旧方式）
    path('dailyreports/<int:pk>/edit/', views.dailyreport_edit, name='dailyreport_edit'),

    # ---------------------------------------
    # 👨‍✈️ 针对某员工（driver_id）日报管理
    # ---------------------------------------

    # 月视图
    path('drivers/<int:driver_id>/dailyreport/', views.driver_dailyreport_month, name='driver_dailyreport_month'),

    # ✅ 使用“选择日期”的新方式新增日报（推荐）
    path('drivers/<int:driver_id>/dailyreport/add/', views.dailyreport_add_selector, name='driver_dailyreport_add_selector'),

    # ✅ ⬇️ 新增：通过 URL 参数指定月份的日报添加视图
    path('drivers/<int:driver_id>/dailyreport/add/month/', views.dailyreport_add_by_month, name='driver_dailyreport_add_month'),

    # 直接新建日报（可改名 direct_add/ 保留旧功能）
    path('drivers/<int:driver_id>/dailyreport/direct_add/', views.dailyreport_create_for_driver, name='driver_dailyreport_direct_add'),

    # 编辑 & 删除
    path('drivers/<int:driver_id>/dailyreport/<int:report_id>/edit/', views.dailyreport_edit_for_driver, name='driver_dailyreport_edit'),
    path('drivers/<int:driver_id>/dailyreport/<int:pk>/delete/', views.dailyreport_delete_for_driver, name='driver_dailyreport_delete'),

    # 未分配司机账号的日报
    path('dailyreport/add/unassigned/', views.driver_dailyreport_add_unassigned, name='driver_dailyreport_add_unassigned'),

    # -----------------------------------
    # 📘 员工基本信息与履历
    # -----------------------------------
    path('dashboard/', views.staffbook_dashboard, name='dashboard'),
    path('drivers/', views.driver_list, name='driver_list'),
    # 🔻✅ 新增这一行：资料未提交一览
    path('driver_documents/', views.driver_documents_status, name='driver_documents_status'),

    path('drivers/create/', views.driver_create, name='driver_create'),
    path('drivers/<int:driver_id>/edit/', views.driver_edit, name='driver_edit'),
    path('bind_missing_users/', views.bind_missing_users, name='bind_missing_users'),

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
]
