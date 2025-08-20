from django.contrib import admin
from django.forms.models import BaseInlineFormSet
from django.core.exceptions import ValidationError
from django.utils.html import format_html
from django import forms
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
        'vehicle', 'driver', 'date',
        'start_time', 'col_actual_out_time',   # ← 新增列（只看实际）
        'end_time',   'col_actual_in_time',    # ← 新增列（只看实际）
        'status', 'approved', 'approved_by_system', 'approval_time'
    )
    list_filter = (
        'status',
        'approved_by_system',
        'driver',
        'vehicle',
        ('date', DateRangeFilter),
    )
    search_fields = (
        'driver__username',
        'driver__first_name',
        'driver__last_name',
        'vehicle__license_plate',
    )
    actions = ['approve_reservations']
    list_per_page = 20

    @staticmethod
    def _fmt(v):
        return v.strftime('%H:%M') if hasattr(v, 'strftime') and v else '—'

    @admin.display(description='实际出库时间')
    def col_actual_out_time(self, obj):
        # 只取“实际出库”的字段；没有就显示 —；不回退计划时间
        # 按你实际字段名修改下面候选名即可
        v = (
            getattr(obj, 'actual_out_time', None) or
            getattr(obj, 'real_out_time', None) or
            getattr(obj, 'departed_at', None)      # 若你是 DateTimeField
        )
        return self._fmt(v)

    @admin.display(description='实际入库时间')
    def col_actual_in_time(self, obj):
        # 只取“实际入库”的字段；没有就 —；不回退计划时间
        v = (
            getattr(obj, 'actual_in_time', None) or
            getattr(obj, 'real_in_time', None) or
            getattr(obj, 'returned_at', None)      # 若你是 DateTimeField
        )
        return self._fmt(v)

    @admin.action(description="✅ 通过选中预约")
    def approve_reservations(self, request, queryset):
        updated = queryset.filter(status=ReservationStatus.APPLYING).update(status=ReservationStatus.BOOKED)
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
