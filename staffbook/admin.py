from django.contrib import admin
from .models import DriverDailySales, DriverDailyReport, DriverPayrollRecord, DriverReportImage
from django.utils.html import format_html

@admin.register(DriverDailySales)
class DriverDailySalesAdmin(admin.ModelAdmin):
    list_display = ('driver', 'date', 'cash_amount', 'card_amount', 'ride_count', 'mileage')
    list_filter = ('date', 'driver')
    search_fields = ('driver__username',)

@admin.register(DriverDailyReport)
class DriverDailyReportAdmin(admin.ModelAdmin):
    list_display = ('driver', 'date', 'time', 'fare', 'payment_method', 'note')
    list_filter = ('date', 'driver', 'payment_method')
    search_fields = ('driver__username', 'note')

@admin.register(DriverPayrollRecord)
class DriverPayrollRecordAdmin(admin.ModelAdmin):
    list_display = ('driver', 'month_display', 'total_sales', 'salary_paid')
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
