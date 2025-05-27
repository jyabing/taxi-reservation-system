from django.contrib import admin
from django.forms.models import BaseInlineFormSet
from django.core.exceptions import ValidationError
from django.utils.html import format_html
from django import forms
from django.utils.safestring import mark_safe
from .models import Vehicle, Reservation, CarouselImage, VehicleImage, Tip
from rangefilter.filters import DateRangeFilter

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

# ✅ 车辆管理页（包含缩略图预览 + 图片上传）
@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    inlines = [VehicleImageInline]
    list_display = ('id', 'license_plate', 'first_preview', 'notes')

    def first_preview(self, obj):
        first = obj.images.first()
        if first and first.image and hasattr(first.image, 'url'):
            return format_html('<img src="{}" style="height:40px;" />', first.image.url)
        return ""
    first_preview.short_description = "封面缩略"

# ✅ 预约管理
@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ('vehicle', 'driver', 'date', 'start_time', 'end_time', 'status')
    list_filter = ('status', 'date', DateRangeFilter)
    actions = ['approve_reservations']
    list_per_page = 20   # ✅ 新增：每页显示20条数据（你可以改成30、50都可以）

    @admin.action(description="✅ 通过选中预约")
    def approve_reservations(self, request, queryset):
        updated = queryset.filter(status='pending').update(status='reserved')
        self.message_user(request, f"{updated} 条预约已成功通过。")

# ✅ 轮播图管理
@admin.register(CarouselImage)
class CarouselImageAdmin(admin.ModelAdmin):
    list_display = ['title', 'order', 'is_active', 'preview']
    list_editable = ['order', 'is_active']

    def preview(self, obj):
        if obj.image_url:
            return format_html('<a href="{0}" target="_blank"><img src="{0}" width="100" /></a>', obj.image_url)
        return "-"
    preview.short_description = "预览"

# ✅ 使用提示管理
@admin.register(Tip)
class TipAdmin(admin.ModelAdmin):
    list_display = ('content', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('content',)
