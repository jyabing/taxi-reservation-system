from django.contrib import admin
from django.utils.html import format_html
from .models import Car

@admin.register(Car)
class CarAdmin(admin.ModelAdmin):
    list_display = (
        'license_plate', 'name', 'brand', 'model', 'year',
        'colored_status', 'is_active',  # ✅ 用带颜色的状态显示
        'registration_number', 'first_registration', 'usage', 'body_shape',
        'car_type_code', 'engine_model', 'engine_displacement',
        'length', 'width', 'height', 'vehicle_weight', 'gross_weight',
        'department', 'manager_name',
        'inspection_date', 'insurance_expiry',
        'etc_device', 'fuel_card_number', 'pos_terminal_id', 'gps_device_id',
    )

    list_filter = (
        'status', 'is_active', 'brand', 'department', 'fuel_type',
    )

    search_fields = (
        'license_plate', 'name', 'brand', 'model',
        'notes', 'fuel_card_number', 'etc_device', 'manager_name',
        'registration_number', 'model_code'
    )

    ordering = ['license_plate']
    list_per_page = 15

    def colored_status(self, obj):
        if obj.status == 'available':
            return format_html('<span style="color:green;">✅ 使用可</span>')
        elif obj.status == 'repair':
            return format_html('<span style="color:orange;">🛠️ 维修中</span>')
        elif obj.status == 'retired':
            return format_html('<span style="color:gray;">🗑️ 已报废</span>')
        else:
            return format_html('<span style="color:black;">❓ 未设定</span>')
    colored_status.short_description = '状态'
