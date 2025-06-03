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

    # 员工（司机）信息管理
    path('drivers/', views.driver_list, name='driver_list'),  # 员工主目录
    path('drivers/create/', views.driver_create, name='driver_create'),  # 新增员工
    path('drivers/<int:driver_id>/', views.driver_detail, name='driver_detail'),  # 个人主页+台账
    path('drivers/<int:driver_id>/edit/', views.driver_edit, name='driver_edit'),  # 编辑员工信息
    
    # 某员工的日报管理（以员工ID为主键，管理员用）
    path('drivers/<int:driver_id>/dailyreport/add/', views.dailyreport_create_for_driver, name='driver_dailyreport_add'),
    path('drivers/<int:driver_id>/dailyreport/<int:pk>/edit/', views.dailyreport_edit_for_driver, name='driver_dailyreport_edit'),
    path('drivers/<int:driver_id>/dailyreport/<int:pk>/delete/', views.dailyreport_delete_for_driver, name='driver_dailyreport_delete'),
]