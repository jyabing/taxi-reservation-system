from django.urls import path
from . import views
from django.views.generic import TemplateView
#from .views import export_monthly_summary_excel

app_name = "dailyreport"

urlpatterns = [

    # 账号绑定页
    path('bind_missing_users/', views.bind_missing_users, name='bind_missing_users'),

    # -----------------------------------
    # 📋 日报功能（所有日报相关）
    # -----------------------------------

    # 日报总览 / 列表 / 导出
    path('dailyreports/', views.dailyreport_list, name='dailyreport_list'),  # （管理员或司机）所有日报功能入口
    path('dailyreports/overview/', views.dailyreport_overview, name='dailyreport_overview'),
    path('export/daily/<int:year>/<int:month>/', views.export_dailyreports_excel, name='export_dailyreports_excel'),#全员每日excel导出
    #path("dailyreport/export/monthly/<int:year>/<int:month>/", export_monthly_summary_excel, name="export_monthly_summary_excel"),#全员每月excel导出
    path('export/vehicle/<int:year>/<int:month>/', views.export_vehicle_csv, name='export_vehicle_csv'), # ✅ 車両運輸実績表 CSV 出力

    path('dailyreports/add/', views.dailyreport_create, name='dailyreport_add'),

    # 管理员：编辑/更新日报（旧方式）
    path('dailyreports/<int:pk>/edit/', views.dailyreport_edit, name='dailyreport_edit'),

    # ETC_填报对照表
    path("help/etc", TemplateView.as_view(template_name="dailyreport/etc_guide.html"), name="etc_help"),

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
    path(
        'external/import/',
        views.external_dailyreport_import,
        name='external_dailyreport_import',
    ),

    # 未分配司机账号的日报
    path('dailyreport/add/unassigned/', views.driver_dailyreport_add_unassigned, name='driver_dailyreport_add_unassigned'), #无账号员工日报

    path('items/<int:item_id>/delete/', views.dailyreport_item_delete, name='report_item_delete'),


    
]