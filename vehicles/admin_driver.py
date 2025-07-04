from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from accounts.models import DriverUser
from accounts.admin import DriverUserAdminForm

# ✅ 原样复用你的 DriverUserAdmin，只是换了注册位置
class DriverUserAdmin(UserAdmin):
    form = DriverUserAdminForm

    fieldsets = UserAdmin.fieldsets + (
        (None, {'fields': ('is_formal', 'is_temporary', 'notification_email', 'wants_notification')}),
    )

    def full_name(self, obj):
        return f"{obj.first_name}{obj.last_name}"
    full_name.short_description = "姓名"

    list_display = (
        'username', 'full_name', 'email',
        'notification_email', 'is_formal', 'is_temporary', 'wants_notification',
    )

admin.site.register(DriverUser, DriverUserAdmin)