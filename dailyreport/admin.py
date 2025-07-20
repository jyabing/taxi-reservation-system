import subprocess, os
from django.db import models
from django.contrib import admin
from django.http import HttpResponse
from django.urls import path
from django.utils.html import format_html
from .models import DriverDailyReport, DriverDailyReportItem, DriverReportImage


# ✅ 日报主表 + 明细表注册（含内联）
class DriverDailyReportItemInline(admin.TabularInline):
    model = DriverDailyReportItem
    extra = 0
    fields = [
        'ride_time', 'ride_from', 'via', 'ride_to', 'num_male', 'num_female',
        'meter_fee', 'payment_method', 'note', 'comment', 'is_flagged', 'has_issue'
    ]
    readonly_fields = ['has_issue']

@admin.register(DriverDailyReport)
class DriverDailyReportAdmin(admin.ModelAdmin):
    list_display = [
        'driver', 'date', 'vehicle',
        'status', 'has_issue',
        'etc_expected', 'etc_collected', 'etc_payment_method', 'get_etc_uncollected',
        'edited_by', 'edited_at'
    ]
    list_filter = ['status', 'has_issue', 'driver']
    search_fields = ('driver__name', 'vehicle__plate_number', 'note')
    inlines = [DriverDailyReportItemInline]
    list_per_page = 20
    ordering = ['-date']

    @admin.display(description='ETC未收')
    def get_etc_uncollected(self, obj):
        return obj.etc_uncollected

@admin.register(DriverDailyReportItem)
class DriverDailyReportItemAdmin(admin.ModelAdmin):
    list_display = ['report', 'ride_time', 'ride_from', 'ride_to', 'meter_fee', 'payment_method', 'has_issue']
    list_filter = ['payment_method', 'has_issue']
    search_fields = ('ride_from', 'ride_to', 'note', 'comment')

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