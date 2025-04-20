from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from accounts.views import home_view

urlpatterns = [
    path('', home_view),  # 首页欢迎页
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('vehicles/', include('vehicles.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)