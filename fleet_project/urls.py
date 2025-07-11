from django.contrib import admin
from django.urls import path, include
from accounts.views import home_view

from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', home_view, name='home'),  # 主页视图
    path('admin/', admin.site.urls),
    path('admin/admin_tools/', include('admin_tools.urls', namespace='admin_tools')),  # ✅ 管理工具：数据库备份、日志查看等
    path('accounts/', include('accounts.urls')),
    path('vehicles/', include('vehicles.urls')),      # ✅ 自主配车系统（原 reservation）：预约、审批、出入库等
    path('staffbook/', include('staffbook.urls')),    # ✅ 员工系统：人事台账、保险、资格证等
    path('dailyreport/', include('dailyreport.urls')),  # ✅ 日报系统：乘务日报、统计、明细、出勤、分析
    path('carinfo/', include('carinfo.urls')),         # ✅ 车辆管理系统：台账、维修、照片等
    
]

# ✅ 始终启用静态资源路由，不依赖 DEBUG 设置
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# ✅ 启用媒体资源支持（可选，如果你有上传图片）
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)