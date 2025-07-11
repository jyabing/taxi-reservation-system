import subprocess
from django.db import models
from django.contrib import admin
from django.http import HttpResponse
from django.urls import path

# ✅ 正确方式定义伪模型（脱离 dailyreport）
class FakeModel(models.Model):
    class Meta:
        verbose_name = "数据库工具"
        verbose_name_plural = "数据库工具"
        app_label = 'staffbook'  # ✅ 用一个合法、不会冲突的名字
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