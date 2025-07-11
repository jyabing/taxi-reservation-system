# admin_tools/views.py
from django.http import HttpResponse
from django.contrib.admin.views.decorators import staff_member_required
import subprocess

@staff_member_required
def backup_database(request):
    # 示例备份逻辑（替换为你实际用的 pg_dump 命令）
    subprocess.run(['pg_dump', '-U', 'youruser', '-h', 'localhost', '-f', 'backup.sql'])
    return HttpResponse("数据库已备份")
