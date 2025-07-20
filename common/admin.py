# common/admin.py
from django.contrib import admin
from .models import LinkClickLog

@admin.register(LinkClickLog)
class LinkClickLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'link_name', 'link_url', 'timestamp')
    list_filter = ('user', 'link_name')
    search_fields = ('link_name', 'link_url', 'user__username')
