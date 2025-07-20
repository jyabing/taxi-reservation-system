# common/urls.py
from django.urls import path
from .views import log_link_click

urlpatterns = [
    path("log-link-click/", log_link_click, name="log_link_click"),
]
