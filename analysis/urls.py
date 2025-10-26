from django.urls import path
from .views import (
    vehicle_idle_view, vehicle_idle_export_csv,
    driver_sales_view, driver_sales_export_csv,
    efficiency_view, efficiency_export_csv,
)

app_name = "analysis"

urlpatterns = [
    path("vehicle/", vehicle_idle_view, name="vehicle_idle"),
    path("vehicle/export.csv", vehicle_idle_export_csv, name="vehicle_idle_export_csv"),

    # 新增：司机売上分析
    path("driver/", driver_sales_view, name="driver_sales"),
    path("driver/export.csv", driver_sales_export_csv, name="driver_sales_export_csv"),

    # 新增：高效利用率分析
    path("efficiency/", efficiency_view, name="efficiency"),
    path("efficiency/export.csv", efficiency_export_csv, name="efficiency_export_csv"),
]
