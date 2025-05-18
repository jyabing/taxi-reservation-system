from django.contrib import admin
from django.forms.models import BaseInlineFormSet
from django.core.exceptions import ValidationError
from .models import Vehicle, Reservation, CarouselImage, VehicleImage
from django.utils.html import format_html
from django.urls import reverse
from .models import Tip

# ✅ 自定义内联表单验证器
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

# ✅ 照片内联
class VehicleImageInline(admin.TabularInline):
    model = VehicleImage
    formset = VehicleImageInlineFormSet  # ✅ 使用自定义验证
    extra = 1
    max_num = 5

@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ('vehicle', 'driver', 'date', 'start_time', 'end_time', 'status')
    list_filter = ('status', 'date')
    actions = ['approve_reservations']

    @admin.action(description="✅ 通过选中预约")
    def approve_reservations(self, request, queryset):
        updated = queryset.filter(status='pending').update(status='reserved')
        self.message_user(request, f"{updated} 条预约已成功通过。")

@admin.register(CarouselImage)
class CarouselImageAdmin(admin.ModelAdmin):
    list_display = ['title', 'order', 'is_active', 'preview']
    list_editable = ['order', 'is_active']

    def preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="100" />', obj.image.url)
        return "-"
    preview.short_description = "预览"

@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    inlines = [VehicleImageInline]
    list_display = ('license_plate', 'model', 'status', 'inspection_date', 'image_preview_column')
    list_display_links = ('license_plate',)

    def image_preview_column(self, obj):
        if obj.images.exists():
            # 只显示第一张缩略图，点击后触发 modal
            first = obj.images.first()
            return format_html(
                '<img src="{}" style="width:60px;height:45px;object-fit:cover;cursor:pointer;" onclick="showImageModal({})" />',
                first.image.url,
                obj.id
            )
        return "-"
    image_preview_column.short_description = "照片"

@admin.register(Tip)
class TipAdmin(admin.ModelAdmin):
    list_display = ('content', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('content',)