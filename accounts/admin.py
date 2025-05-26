from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import DriverUser

class DriverUserAdmin(UserAdmin):
        (None, {
            'fields': ('is_formal', 'is_temporary', 'notification_email', 'wants_notification')
        }),
    )
    list_display = UserAdmin.list_display + ('is_formal', 'is_temporary', 'notification_email', 'wants_notification')

admin.site.register(DriverUser, DriverUserAdmin)
