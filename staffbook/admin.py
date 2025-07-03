from django.contrib import admin
from django.utils.html import format_html
from django.contrib.auth import get_user_model
from .models import (
    Driver, DriverDailySales, DriverDailyReport, DriverPayrollRecord,
    DriverReportImage, DrivingExperience, Insurance, FamilyMember
)

User = get_user_model()

# 台账明细 Inline
class DrivingExperienceInline(admin.TabularInline):
    model = DrivingExperience
    extra = 1

class InsuranceInline(admin.TabularInline):
    model = Insurance
    extra = 1

class FamilyMemberInline(admin.TabularInline):
    model = FamilyMember
    extra = 1


@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ('driver_code', 'name', 'kana', 'user', 'phone_number')
    search_fields = ('driver_code', 'name')
    list_filter = ('user',)

    def save_model(self, request, obj, form, change):
        # 新增/编辑时如果没绑定用户则自动创建并绑定
        if not obj.user:
            username = obj.driver_code  # 用员工号做用户名，保证唯一
            user, created = User.objects.get_or_create(
                username=username,
                defaults={'is_active': True, 'first_name': obj.name}
            )
            obj.user = user
        super().save_model(request, obj, form, change)

@admin.register(DriverDailySales)
class DriverDailySalesAdmin(admin.ModelAdmin):
    list_display = ('driver', 'date', 'cash_amount', 'card_amount', 'ride_count', 'mileage')
    list_filter = ('date', 'driver')
    search_fields = ('driver__username',)

@admin.register(DriverDailyReport)
class DriverDailyReportAdmin(admin.ModelAdmin):
    list_display = ['driver', 'date', 'note']
    list_filter = ['driver', 'date']
    search_fields = ('driver__username', 'note')
    list_per_page = 20  # ✅ 每页最多显示 20 条

@admin.register(DriverPayrollRecord)
class DriverPayrollRecordAdmin(admin.ModelAdmin):
    list_display = [
        'driver',
        'month',
        'basic_pay',        # 替换原 total_sales
        'total_pay',        # 替换原 salary_paid
        'note',
    ]
    list_filter = ('month', 'driver')
    search_fields = ('driver__username',)

    def month_display(self, obj):
        return obj.month.strftime('%Y-%m')
    month_display.short_description = '月份'

@admin.register(DriverReportImage)
class DriverReportImageAdmin(admin.ModelAdmin):
    list_display = ('driver', 'date', 'uploaded_at', 'image_tag')
    list_filter = ('date',)
    readonly_fields = ('image_tag',)

    def image_tag(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-height:80px;max-width:120px;" />', obj.image.url)
        return "-"
    image_tag.short_description = "图片预览"
