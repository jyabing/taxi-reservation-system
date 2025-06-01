from django.urls import path
from . import views

app_name = 'staffbook'

urlpatterns = [
    path('submit_sales/', views.submit_sales, name='submit_sales'),  # 新日报录入
    path('sales_thanks/', views.sales_thanks, name='sales_thanks'),
    path('dailyreports/', views.dailyreport_list, name='dailyreport_list'),  # 日报列表
    path('dailyreports/add/', views.dailyreport_create, name='dailyreport_add'),         # 新建日报
    path('dailyreports/<int:pk>/edit/', views.dailyreport_edit, name='dailyreport_edit'), # 编辑日报
    path('my_dailyreports/', views.my_dailyreports, name='my_dailyreports'), # 个人日报（可选）

    path('drivers/', views.driver_list, name='driver_list'),  # 员工列表
    path('drivers/create/', views.driver_create, name='driver_create'),
    path('drivers/<int:driver_id>/', views.driver_detail, name='driver_detail'),
    path('drivers/<int:driver_id>/edit/', views.driver_edit, name='driver_edit'),
    
    path('drivers/<int:driver_id>/dailyreport/add/', views.dailyreport_create_for_driver, name='driver_dailyreport_add'),
    path('drivers/<int:driver_id>/dailyreport/<int:pk>/edit/', views.dailyreport_edit_for_driver, name='driver_dailyreport_edit'),
    path('drivers/<int:driver_id>/dailyreport/<int:pk>/delete/', views.dailyreport_delete_for_driver, name='driver_dailyreport_delete'),
]
