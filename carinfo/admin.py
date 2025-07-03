from django.contrib import admin
from .models import Car

@admin.register(Car)
class CarAdmin(admin.ModelAdmin):
    list_display = (
        'license_plate', 'name', 'brand', 'model', 'year',
        'status', 'is_active',
        'department', 'manager_name',
        'inspection_date', 'insurance_expiry',
        'etc_device', 'fuel_card_number', 'pos_terminal_id', 'gps_device_id',
    )
    list_filter = (
        'status', 'is_active', 'brand', 'department',
    )
    search_fields = (
        'license_plate', 'name', 'brand', 'model',
        'notes', 'fuel_card_number', 'etc_device', 'manager_name'
    )
    ordering = ['license_plate']
