from django.contrib import admin
from django.urls import path, include
from accounts.views import home_view

from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', home_view),  # 主页视图
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('vehicles/', include('vehicles.urls')),
]

# ✅ 始终启用静态资源路由，不依赖 DEBUG 设置
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# ✅ 启用媒体资源支持（可选，如果你有上传图片）
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)