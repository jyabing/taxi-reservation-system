from django.contrib import admin
from django.forms.models import BaseInlineFormSet
from django.core.exceptions import ValidationError
from django.utils.html import format_html
from django import forms
from django.utils import timezone
from django.utils.safestring import mark_safe
from .models import Reservation, ReservationStatus, VehicleImage, Tip, SystemNotice
from rangefilter.filters import DateRangeFilter
from . import admin_driver

# 🚗 自定义 Inline 表单（隐藏 image 输入框）
class VehicleImageForm(forms.ModelForm):
    class Meta:
        model = VehicleImage
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['image'].widget = forms.HiddenInput()

    class Media:
        js = (
            'https://code.jquery.com/jquery-3.6.0.min.js',
            '/static/js/image_upload.js',  # 你需将该 JS 文件放到 static/js 下
        )

# 🚗 限制车辆照片数量：至少 1 张，最多 5 张
class VehicleImageInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        total = 0
        for form in self.forms:
            if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                total += 1
        if total < 1:
            raise ValidationError("请至少上传 1 张车辆照片。")
        if total > 5:
            raise ValidationError("最多只能上传 5 张车辆照片。")

# 🚗 车辆图片内联表格（上传按钮 + 缩略图 + 隐藏字段）
class VehicleImageInline(admin.TabularInline):
    model = VehicleImage
    fields = ('preview', 'image')
    readonly_fields = ('preview',)

    def preview(self, obj):
        if obj.image and hasattr(obj.image, 'url'):
            return format_html('<img src="{}" style="height:50px;" />', obj.image.url)
        return ""

    def upload_button(self, obj):
        return mark_safe(
            '<input type="file" class="upload-btn" accept="image/*"><br><span class="upload-status"></span>'
        )


# ✅ 预约管理
@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = (
        "vehicle", "driver", "date",
        "start_time", "actual_departure_local",
        "end_time",   "actual_return_local",
        "status", "approved", "approved_by_system", "approval_time",
    )
    list_select_related = ("vehicle", "driver")
    list_per_page = 20

    list_filter = (
        "status",
        "approved_by_system",
        "driver",
        "vehicle",
        ("date", admin.DateFieldListFilter),  # 你若在用 DateRangeFilter 也可保留
    )
    search_fields = (
        "driver__username", "driver__first_name", "driver__last_name",
        "vehicle__license_plate",
    )

    # ✅ 实际出库
    @admin.display(description="实际出库时间", ordering="actual_departure", empty_value="—")
    def actual_departure_local(self, obj):
        if obj.actual_departure:
            return timezone.localtime(obj.actual_departure).strftime("%H:%M")
        return None

    # ✅ 实际入库
    @admin.display(description="实际入库时间", ordering="actual_return", empty_value="—")
    def actual_return_local(self, obj):
        if obj.actual_return:
            return timezone.localtime(obj.actual_return).strftime("%H:%M")
        return None

    # ✅ 批量通过（兼容两套状态值）
    @admin.action(description="✅ 通过选中预约")
    def approve_reservations(self, request, queryset):
        updated = queryset.filter(status__in=["pending", "applying"]).update(status="booked")
        self.message_user(request, f"{updated} 条预约已成功通过。")

# ✅ 注册 SystemNotice 模型
@admin.register(SystemNotice)
class SystemNoticeAdmin(admin.ModelAdmin):
    list_display = ('message', 'is_active', 'created_at')
    list_editable = ('is_active',)
    ordering = ('-created_at',)

    def save_model(self, request, obj, form, change):
        # ✅ 若当前保存的是启用状态，则将其他通知设为禁用
        if obj.is_active:
            SystemNotice.objects.exclude(id=obj.id).update(is_active=False)
        super().save_model(request, obj, form, change)

    # ✅ 新建对象时，默认启用
    def get_changeform_initial_data(self, request):
        return {'is_active': True}

# ✅ 使用提示管理
@admin.register(Tip)
class TipAdmin(admin.ModelAdmin):
    list_display = ('content', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('content',)
