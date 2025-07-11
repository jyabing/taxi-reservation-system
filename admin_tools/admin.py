from django.contrib import admin
from django.db import models
from django.urls import path
from django.http import HttpResponse
import subprocess

class FakeModel(models.Model):
    class Meta:
        verbose_name = "数据库工具"
        verbose_name_plural = "数据库工具"
        app_label = 'admin_tools'
        managed = False

class DatabaseToolAdmin(admin.ModelAdmin):
    change_list_template = "admin_tools/database_tool_changelist.html"

    def get_queryset(self, request):
        return FakeModel.objects.none()

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

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

admin.site.register(FakeModel, DatabaseToolAdmin)
