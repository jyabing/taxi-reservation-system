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
        ids_yes = [obj.pk for obj in queryset if is_car_reservable(obj)]
        if self.value() == 'yes':
            return queryset.filter(pk__in=ids_yes)
        elif self.value() == 'no':
            return queryset.exclude(pk__in=ids_yes)
        return queryset

# ✅ 主注册类
@admin.register(Car)
class CarAdmin(admin.ModelAdmin):
    list_display = (
        'thumb',  # ✅ 缩略图
        'license_plate', 'name', 'brand', 'model', 'year',
        'colored_status', 'is_active',
        'insurance_status_colored',
        'inspection_status_colored',
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
        InsuranceStatusFilter, InspectionStatusFilter, ReservableStatusFilter,
    )

    search_fields = (
        'license_plate', 'name', 'brand', 'model',
        'notes', 'fuel_card_number', 'etc_device', 'manager_name',
        'registration_number', 'model_code'
    )

    ordering = ['license_plate']
    list_per_page = 15
    list_display_links = ('license_plate', 'name')

    actions = ['update_selected_insurance_status']

    # ✅ 只读预览字段（保留一处即可）
    readonly_fields = ('preview',)

    # ✅ 把 main_photo + preview 插到表单最前
    def get_fields(self, request, obj=None):
        fields = list(super().get_fields(request, obj))
        if 'main_photo' in fields:
            fields.remove('main_photo')
        return ['main_photo', 'preview'] + fields

    # ===== 图片工具 =====
    def _photo_url(self, obj):
        """
        统一走模型的 photo_url，不做 exists/HEAD 检查，
        与 Car.photo_url 的设计保持一致，适配 R2/S3 私有桶签名 URL。
        """
        return getattr(obj, "photo_url", None)

    @admin.display(description="照片", ordering="main_photo")
    def thumb(self, obj):
        url = self._photo_url(obj)
        if url:
            return format_html(
                '<img src="{}" style="width:72px;height:48px;object-fit:cover;'
                'border-radius:6px;box-shadow:0 0 2px rgba(0,0,0,.25);" />', url
            )
        return "—"

    @admin.display(description="预览")
    def preview(self, obj):
        url = self._photo_url(obj)
        if url:
            return format_html(
                '<img src="{}" style="max-width:280px;height:auto;border-radius:8px;'
                'box-shadow:0 0 3px rgba(0,0,0,.2);" />', url
            )
        return "（暂无图片）"

    # ===== 你的其他方法保持不变 =====
    def update_selected_insurance_status(self, request, queryset):
        today = localdate()
        updated = 0
        for car in queryset:
            old_status = car.insurance_status
            if car.insurance_end_date:
                car.insurance_status = 'expired' if car.insurance_end_date < today else 'valid'
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

    def save_model(self, request, obj, form, change):
        old_name = None
        if change:
            try:
                old = type(obj).objects.get(pk=obj.pk)
                old_name = getattr(old.main_photo, 'name', None)
            except type(obj).DoesNotExist:
                pass

        super().save_model(request, obj, form, change)

        # 如果这次确实上传了新图片，并且旧的是占位图，清理占位对象
        if form.cleaned_data.get('main_photo') and old_name and old_name.startswith('placeholder_'):
            try:
                obj.main_photo.storage.delete(old_name)
            except Exception:
                pass