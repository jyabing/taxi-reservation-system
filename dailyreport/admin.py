import subprocess, os
from django.db import models
from django.contrib import admin
from django.http import HttpResponse
from django.urls import path
from django.utils.html import format_html
from .models import DriverDailyReport, DriverDailyReportItem, DriverReportImage

# ✅ 正确方式定义伪模型（脱离 dailyreport）
class FakeModel(models.Model):
    class Meta:
        verbose_name = "数据库工具"
        verbose_name_plural = "数据库工具"
        app_label = 'accounts'  # ✅ 用一个合法、不会冲突的名字
        managed = False  # ✅ 不生成数据表

class DatabaseToolAdmin(admin.ModelAdmin):
    change_list_template = "admin/database_tool_changelist.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('backup/', self.admin_site.admin_view(self.backup_view), name="backup_database"),
        ]
        return custom_urls + urls

    def backup_view(self, request):
        try:
            result = subprocess.run(
                ['/mnt/e/Django-project/taxi_project/backup_postgres.sh'],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            return HttpResponse(f"<pre>✅ 备份成功：\n{result.stdout}</pre>")
        except subprocess.CalledProcessError as e:
            return HttpResponse(f"<pre>❌ 备份失败：\n{e.stderr}</pre>", status=500)

# ✅ 注册伪模型用于后台按钮展示
admin.site.register(FakeModel, DatabaseToolAdmin)

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
    list_display = ['driver', 'date', 'vehicle', 'status', 'has_issue', 'edited_by', 'edited_at']
    list_filter = ['status', 'has_issue', 'driver']
    search_fields = ('driver__name', 'vehicle__plate_number', 'note')
    inlines = [DriverDailyReportItemInline]
    list_per_page = 20
    ordering = ['-date']

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