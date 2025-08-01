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
        'etc_expected',                 # 应收
        'etc_collected_cash',          # ✅ 新增：现金收取
        'etc_collected_app',           # ✅ 新增：App收取
        'get_etc_collected_total',     # ✅ 新增：实收合计（@property）
        'get_etc_diff',               
        'etc_shortage',                 # ✅ 新增：差额
        'etc_payment_method',
        'get_etc_uncollected',         # 原有未收字段
        'edited_by', 'edited_at',
        #'combined_group'
        'get_combined_groups',         # ✅ 新增：合算组
    ]

    readonly_fields = ['etc_shortage']
    list_filter = ['status', 'has_issue', 'driver']
    search_fields = ('driver__name', 'vehicle__license_plate', 'note')
    inlines = [DriverDailyReportItemInline]
    list_per_page = 20
    ordering = ['-date']
    

    @admin.display(description='ETC未收')
    def get_etc_uncollected(self, obj):
        amt = obj.etc_uncollected or 0
        if amt == 0:
            return format_html('<span style="color: green;">0</span>')
        return format_html('<span style="color: red;">{}</span>', amt)

    @admin.display(description='ETC实收合计')
    def get_etc_collected_total(self, obj):
        return obj.etc_collected_total

    @admin.display(description='ETC差額')
    def get_etc_diff(self, obj):
        expected = obj.etc_expected or 0
        collected = (obj.etc_collected_cash or 0) + (obj.etc_collected_app or 0)
        diff = expected - collected
        if diff == 0:
            color = 'green'
            label = '0（已收齐）'
        elif diff > 0:
            color = 'red'
            label = f'{diff}（未收）'
        else:
            color = 'orange'
            label = f'{diff}（多收？）'
        return format_html('<span style="color: {};">{}</span>', color, label)

    @admin.display(description='合算组')
    def get_combined_groups(self, obj):
        groups = sorted(set(i.combined_group for i in obj.items.all() if i.combined_group))
        if groups:
            return ", ".join(groups)
        return format_html('<span style="color:gray;font-style:italic;">无</span>')

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