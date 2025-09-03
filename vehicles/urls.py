from django.urls import path
from . import views
from .views import save_vehicle_note, reserve_vehicle_view

app_name = 'vehicles'  # 👈 这句决定是否需要用 'vehicles:' 前缀
#如果上面有 app_name {% url 'vehicles:vehicle_status' %}-->
#如果上面没有 app_name {% url 'vehicle_status' %}-->


urlpatterns = [
    path('list/', views.vehicle_list, name='vehicle_list'),
    path('status/', views.vehicle_status_view, name='vehicle_status'),

    # 预约相关
    path('reserve/<int:car_id>/', views.reserve_vehicle_view, name='make_reservation'),  # ← 保留这一条
    path('approval/', views.reservation_approval_list, name='reservation_approval_list'),
    path('approve/<int:pk>/', views.approve_reservation, name='approve_reservation'),
    path('checkout/<int:reservation_id>/', views.check_out, name='check_out'),
    path('checkin/<int:reservation_id>/', views.check_in, name='check_in'),

    # ✅ 一键入库完成（未完成→完成）
    path(
        'reservations/<int:pk>/complete_return/',
        views.complete_return,
        name='reservations_complete_return',
    ),

    # 其余保持不动……
    path('timeline/<int:vehicle_id>/', views.vehicle_timeline_view, name='vehicle_timeline'),
    path('weekly/', views.weekly_overview_view, name='weekly_overview'),
    path('select_timeline/', views.timeline_selector_view, name='timeline_selector'),
    path('select_weekly/', views.weekly_selector_view, name='weekly_selector'),
    path('select_daily/', views.daily_selector_view, name='daily_selector'),
    path('dashboard/', views.reservation_dashboard, name='reservation_dashboard'),
    path('daily/', views.daily_overview_view, name='daily_overview'),
    path('my_reservations/', views.my_reservations_view, name='my_reservations'),
    path('recent/<int:car_id>/', views.recent_reservations_view, name='recent_reservations'),
    path('reservation/<int:reservation_id>/', views.reservation_detail_view, name='reservation_detail'),
    path('vehicle/<int:vehicle_id>/', views.vehicle_detail, name='vehicle_detail'),
    path('reservation/<int:reservation_id>/edit/', views.edit_reservation_view, name='edit_reservation'),
    path('reservation/<int:reservation_id>/delete/', views.delete_reservation_view, name='delete_reservation'),
    path('confirm_check_io/', views.confirm_check_io, name='confirm_check_io'),
    path('status/photo/', views.vehicle_status_with_photo, name='vehicle_status_with_photo'),
    path('monthly/<int:vehicle_id>/', views.vehicle_monthly_gantt_view, name='vehicle_monthly_gantt'),
    path('weekly/gantt/', views.vehicle_weekly_gantt_view, name='vehicle_weekly_gantt'),
    path('admin/vehicle/<int:vehicle_id>/images/', views.vehicle_image_list_view, name='vehicle_image_list'),
    path('admin/vehicle/<int:vehicle_id>/delete_image/<int:index>/', views.vehicle_image_delete_view, name='vehicle_image_delete'),
    path('edit_notes/<int:car_id>/', views.edit_vehicle_notes, name='edit_vehicle_notes'),
    path('save_note/<int:car_id>/', save_vehicle_note, name='save_vehicle_note'),
    path('calendar/', views.calendar_view, name='calendar_view'),
    path('api/daily-sales/', views.api_daily_sales_mock, name='api_daily_sales'),
    path('my_stats/', views.my_stats_view, name='my_stats'),
    path('admin_stats/', views.admin_stats_view, name='admin_stats'),
    path('admin/vehicle/upload_image/', views.upload_vehicle_image, name='upload_vehicle_image'),
    path('test-email/', views.test_email_view, name='test_email'),
    path('admin/reset_departure/<int:reservation_id>/', views.admin_reset_departure, name='admin_reset_departure'),
    path('admin/reset_return/<int:reservation_id>/', views.admin_reset_return, name='admin_reset_return'),
    path('home/', views.reservation_home, name='reservation_home'),
    path('reservation/status/', views.reservation_status, name='reservation_status'),
    path('reservation/create/', views.create_reservation, name='create_reservation'),
    path('reservation/approval/', views.reservation_approval, name='reservation_approval'),
    path('admin/', views.admin_index, name='staffbook_admin_index'),
    path('admin/list/', views.admin_list, name='vehicle_admin_list'),
    path('my_dailyreports/', views.my_dailyreports, name='my_dailyreports'),
    path('my_dailyreport/<int:report_id>/', views.my_daily_report_detail, name='my_daily_report_detail'),
    
]
