from django.contrib import admin
from django.utils.html import format_html
from django.utils.timezone import localdate
from django.contrib.admin import SimpleListFilter
from .models import Car
from carinfo.services.car_access import is_car_reservable
from carinfo.services.car_flags import is_under_repair, is_retired

# ✅ 筛选器：保险状态
class InsuranceStatusFilter(SimpleListFilter):
    title = '保险状态'
    parameter_name = 'insurance_status_filter'

    def lookups(self, request, model_admin):
        return [
            ('valid', '✅ 有效'),
            ('expired', '❌ 过期'),
            ('none', '未加入'),
        ]

    def queryset(self, request, queryset):
        today = localdate()
        if self.value() == 'valid':
            return queryset.filter(insurance_end_date__gte=today)
        elif self.value() == 'expired':
            return queryset.filter(insurance_end_date__lt=today)
        elif self.value() == 'none':
            return queryset.filter(insurance_end_date__isnull=True)
        return queryset

# ✅ 筛选器：车检状态
class InspectionStatusFilter(SimpleListFilter):
    title = '车检状态'
    parameter_name = 'inspection_status_filter'

    def lookups(self, request, model_admin):
        return [
            ('valid', '✅ 有效'),
            ('expired', '❌ 已过期'),
            ('none', '无记录'),
        ]

    def queryset(self, request, queryset):
        today = localdate()
        if self.value() == 'valid':
            return queryset.filter(inspection_date__gte=today)
        elif self.value() == 'expired':
            return queryset.filter(inspection_date__lt=today)
        elif self.value() == 'none':
            return queryset.filter(inspection_date__isnull=True)
        return queryset

# ✅ 筛选器：是否可预约
class ReservableStatusFilter(SimpleListFilter):
    title = '可预约'
    parameter_name = 'reservable_status'

    def lookups(self, request, model_admin):
        return [
            ('yes', '✅ 是'),
            ('no', '❌ 否'),
        ]

    def queryset(self, request, queryset):
        from carinfo.services.car_access import is_car_reservable
        if self.value() == 'yes':
            return [obj for obj in queryset if is_car_reservable(obj)]
        elif self.value() == 'no':
            return [obj for obj in queryset if not is_car_reservable(obj)]
        return queryset

# ✅ 主注册类
@admin.register(Car)
class CarAdmin(admin.ModelAdmin):
    list_display = (
        'license_plate', 'name', 'brand', 'model', 'year',
        'colored_status', 'is_active',
        'insurance_status_colored',    # 高亮显示保险状态
        'inspection_status_colored',   # 高亮显示车检状态
        'registration_number', 'first_registration_date', 'usage', 'body_shape',
        'model_code', 'engine_model', 'engine_displacement',
        'length', 'width', 'height', 'vehicle_weight', 'gross_weight',
        'capacity', 'max_load_weight',
        'department', 'manager_name',
        'inspection_date', 'insurance_end_date',
        'etc_device', 'fuel_card_number', 'pos_terminal_id', 'gps_device_id',
    )

    list_filter = (
        'status', 'is_active', 'brand', 'department', 'fuel_type',
        InsuranceStatusFilter,         # ✅ 保险状态筛选
        InspectionStatusFilter,        # ✅ 车检状态筛选
        ReservableStatusFilter,
    )

    search_fields = (
        'license_plate', 'name', 'brand', 'model',
        'notes', 'fuel_card_number', 'etc_device', 'manager_name',
        'registration_number', 'model_code'
    )

    ordering = ['license_plate']
    list_per_page = 15
    list_display_links = ('license_plate', 'name')

    actions = ['update_selected_insurance_status']  # ✅ 批量更新操作

    def update_selected_insurance_status(self, request, queryset):
        today = localdate()
        updated = 0

        for car in queryset:
            old_status = car.insurance_status

            if car.insurance_end_date:
                if car.insurance_end_date < today:
                    car.insurance_status = 'expired'
                else:
                    car.insurance_status = 'valid'
            else:
                car.insurance_status = 'none'

            if car.insurance_status != old_status:
                car.save(update_fields=['insurance_status'])
                updated += 1

        self.message_user(request, f"✅ 已更新 {updated} 条保险状态记录。")
    update_selected_insurance_status.short_description = "✅ 更新所选车辆的保险状态"

    def colored_status(self, obj):
        if is_car_reservable(obj):
            return format_html('<span style="color:green;">✅ 使用可</span>')
        elif is_under_repair(obj):
            return format_html('<span style="color:orange;">🛠️ 维修中</span>')
        elif is_retired(obj):
            return format_html('<span style="color:gray;">🗑️ 已报废</span>')
        else:
            return format_html('<span style="color:black;">❓ 未设定</span>')
        colored_status.short_description = '状态'

    def insurance_status_colored(self, obj):
        if obj.is_insurance_expired():
            return format_html('<span style="color: red;">❌ 保险过期</span>')
        elif obj.insurance_status == 'none':
            return format_html('<span style="color: gray;">未加入</span>')
        return format_html('<span style="color: green;">✅ 有效</span>')
    insurance_status_colored.short_description = "保险状态"

    def inspection_status_colored(self, obj):
        if obj.is_inspection_expired():
            return format_html('<span style="color: red;">❌ 已过期</span>')
        elif obj.inspection_date:
            return format_html('<span style="color: green;">✅ 有效</span>')
        return format_html('<span style="color: gray;">无记录</span>')
    inspection_status_colored.short_description = "车检状态"
