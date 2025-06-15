from django.urls import path
from . import views

app_name = 'staffbook'

urlpatterns = [
    
    # 日报相关（全部/自己/新建/编辑）
    path('submit_sales/', views.submit_sales, name='submit_sales'),  # 日报录入（通常司机用）
    path('sales_thanks/', views.sales_thanks, name='sales_thanks'),  # 录入成功页
    path('dailyreports/', views.dailyreport_list, name='dailyreport_list'),  # 所有日报（或按权限过滤）
    path('dailyreports/add/', views.dailyreport_create, name='dailyreport_add'),  # 管理员新建日报
    path('dailyreports/<int:pk>/edit/', views.dailyreport_edit, name='dailyreport_edit'), # 管理员编辑日报
    path('my_dailyreports/', views.my_dailyreports, name='my_dailyreports'), # 当前登录用户的日报列表
    path('dailyreports/overview/', views.dailyreport_overview, name='dailyreport_overview'),  # 日报概览（管理员用）

    # 员工（司机）信息管理
    path('dashboard/', views.staffbook_dashboard, name='dashboard'),
    path('drivers/', views.driver_list, name='driver_list'),  # 员工主目录
    path('drivers/create/', views.driver_create, name='driver_create'),  # 新增员工
    
    path('drivers/<int:driver_id>/basic/', views.driver_basic_info, name='driver_basic_info'),  # 个人主页+台账
    path('drivers/<int:driver_id>/basic/edit/', views.driver_basic_edit, name='driver_basic_edit'),  # 编辑个人主页+台账
    
    path('drivers/<int:driver_id>/personal/', views.driver_personal_info, name='driver_personal_info'),#個人情報
    path('drivers/<int:driver_id>/personal/edit/', views.driver_personal_edit, name='driver_personal_edit'), # 编辑个人信息

    path('drivers/<int:driver_id>/certificate/', views.driver_certificate_info, name='driver_certificate_info'),#签证在留
    path('drivers/<int:driver_id>/certificate/edit/', views.driver_certificate_edit, name='driver_certificate_edit'), # 编辑签证在留

    path('drivers/<int:driver_id>/history/', views.driver_history_info, name='driver_history_info'),#履歴変更記録
    path('drivers/<int:driver_id>/history/edit/', views.driver_history_edit, name='driver_history_edit'), # 编辑履歴変更記録    

    path('drivers/<int:driver_id>/emergency/', views.driver_emergency_info, name='driver_emergency_info'), # 緊急連絡先
    path('drivers/<int:driver_id>/emergency/edit/', views.driver_emergency_edit, name='driver_emergency_edit'), # 编辑紧急联系人信息
    
    path('drivers/<int:driver_id>/experience/', views.driver_experience_info, name='driver_experience_info'),#運転経験
    path('drivers/<int:driver_id>/experience/edit/', views.driver_experience_edit, name='driver_experience_edit'), # 编辑運転経験    
    
    path('drivers/<int:driver_id>/license/', views.driver_license_info, name='driver_license_info'), # 员工驾驶证信息
    path('drivers/<int:driver_id>/license/edit/', views.driver_license_edit, name='driver_license_edit'), # 编辑员工驾驶证信息
    
    path('drivers/<int:driver_id>/qualification/', views.driver_qualification_info, name='driver_qualification_info'),#資格
    path('drivers/<int:driver_id>/qualification/edit/', views.driver_qualification_edit, name='driver_qualification_edit'), # 编辑資格
    
    path('drivers/<int:driver_id>/aptitude/', views.driver_aptitude_info, name='driver_aptitude_info'),#適性診断
    path('drivers/<int:driver_id>/aptitude/edit/', views.driver_aptitude_edit, name='driver_aptitude_edit'), # 编辑適性診断
    
    path('drivers/<int:driver_id>/rewards/', views.driver_rewards_info, name='driver_rewards_info'),#賞罰
    path('drivers/<int:driver_id>/rewards/edit/', views.driver_rewards_edit, name='driver_rewards_edit'), # 编辑賞罰
    
    path('drivers/<int:driver_id>/accident/', views.driver_accident_info, name='driver_accident_info'),#事故・違反
    path('drivers/<int:driver_id>/accident/edit/', views.driver_accident_edit, name='driver_accident_edit'), # 编辑事故・違反
    
    path('drivers/<int:driver_id>/education/', views.driver_education_info, name='driver_education_info'),#指導教育
    path('drivers/<int:driver_id>/education/edit/', views.driver_education_edit, name='driver_education_edit'), # 编辑指導教育
    
    # 健康診断
    path('drivers/<int:driver_id>/health/', views.driver_health_info, name='driver_health_info'),   # 健康診断只读
    path('drivers/<int:driver_id>/health/edit/', views.driver_health_edit, name='driver_health_edit'), # 编辑

    # 既往歴
    path('drivers/<int:driver_id>/history/', views.driver_history_info, name='driver_history_info'),   # 既往歴只读
    path('drivers/<int:driver_id>/history/edit/', views.driver_history_edit, name='driver_history_edit'), # 编辑
    path('drivers/<int:driver_id>/daily/', views.driver_dailyreport_month, name='driver_dailyreport_month'),  # 员工日报卡片（个人主页）
    
    path('drivers/<int:driver_id>/edit/', views.driver_edit, name='driver_edit'),  # 编辑员工信息
    path('bind_missing_users/', views.bind_missing_users, name='bind_missing_users'),
    
    # 某员工的日报管理（以员工ID为主键，管理员用）
    #path('drivers/<int:driver_id>/dailyreport/<int:pk>/', views.dailyreport_detail, name='driver_dailyreport_detail'),
    path('drivers/<int:driver_id>/dailyreport/add/', views.dailyreport_create_for_driver, name='driver_dailyreport_add'),

    path('drivers/<int:driver_id>/dailyreport/<int:report_id>/edit/', views.dailyreport_edit_for_driver, name='driver_dailyreport_edit'),
    path('drivers/<int:driver_id>/dailyreport/<int:pk>/delete/', views.dailyreport_delete_for_driver, name='driver_dailyreport_delete'),
]