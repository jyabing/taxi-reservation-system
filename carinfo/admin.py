from django.contrib import admin
from .models import Car

@admin.register(Car)
class CarAdmin(admin.ModelAdmin):
    list_display = (
        'license_plate', 'name', 'brand', 'model', 'year',
        'status', 'is_active',
        'registration_number', 'first_registration', 'usage', 'body_shape',
        'car_type_code', 'engine_model', 'engine_displacement',
        'length', 'width', 'height', 'vehicle_weight', 'gross_weight',
        'department', 'manager_name',
        'inspection_date', 'insurance_expiry',
        'etc_device', 'fuel_card_number', 'pos_terminal_id', 'gps_device_id',
    )
    list_filter = (
        'status', 'is_active', 'brand', 'department', 'fuel_type',  # ✅ fuel_type 也是新字段
    )
    search_fields = (
        'license_plate', 'name', 'brand', 'model',
        'notes', 'fuel_card_number', 'etc_device', 'manager_name',
        'registration_number', 'model_code'  # ✅ 添加
    )
    ordering = ['license_plate']

    list_per_page = 15  # ✅ 每页最多显示 20 条记录
