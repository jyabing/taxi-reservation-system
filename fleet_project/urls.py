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