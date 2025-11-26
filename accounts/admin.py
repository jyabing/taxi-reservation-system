from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import DriverUser, UserProfile

# ✅ 1. 表单定义（控制通知字段隐藏）
class DriverUserAdminForm(forms.ModelForm):
    class Meta:
        model = DriverUser
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not (self.instance and (self.instance.is_staff or self.instance.is_superuser)):
            self.fields['wants_notification'].widget = forms.HiddenInput()
            self.fields['notification_email'].widget = forms.HiddenInput()

# ✅ 2. 用户后台配置
class DriverUserAdmin(UserAdmin):
    form = DriverUserAdminForm

    fieldsets = UserAdmin.fieldsets + (
        (None, {'fields': ('is_formal', 'is_temporary', 'notification_email', 'wants_notification')}), )

    def full_name(self, obj):
        return f"{obj.first_name}{obj.last_name}"
    full_name.short_description = "姓名"

    list_display = (
        'username', 'full_name', 'email',
        'notification_email', 'is_formal', 'is_temporary', 'wants_notification',
    )

# ✅ 4. 注册权限扩展模型
@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = [
        'user',
        'is_vehicles_admin',       # 配车系统管理员（你原来就有的）
        'is_staffbook_admin',      # 员工台账系统管理员
        'is_dailyreport_admin',    # 日报管理系统管理员（新加的）
        'is_carinfo_admin',        # 车辆资料管理系统管理员
    ]

    list_editable = [
        'is_vehicles_admin',
        'is_staffbook_admin',
        'is_dailyreport_admin',
        'is_carinfo_admin',
    ]

    search_fields = ['user__username']
# ==== END REPLACE: UserProfileAdmin ====
