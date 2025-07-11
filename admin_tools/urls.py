# admin_tools/urls.py
from django.urls import path
from . import views

app_name = 'admin_tools'

urlpatterns = [
    path('backup/', views.backup_database, name='backup'),
]
