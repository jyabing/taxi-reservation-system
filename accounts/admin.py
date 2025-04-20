from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import DriverUser


class DriverUserAdmin(UserAdmin):
    model = DriverUser
    fieldsets = UserAdmin.fieldsets + (
        (None, {'fields': ('is_formal', 'is_temporary')}),
    )

admin.site.register(DriverUser, DriverUserAdmin)
