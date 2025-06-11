from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import DriverUser, UserProfile

# 1️⃣ 先定义表单
class DriverUserAdminForm(forms.ModelForm):
    class Meta:
        model = DriverUser
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not (self.instance and (self.instance.is_staff or self.instance.is_superuser)):
            self.fields['wants_notification'].widget = forms.HiddenInput()
            self.fields['notification_email'].widget = forms.HiddenInput()

# 2️⃣ 再定义 admin
class DriverUserAdmin(UserAdmin):
    form = DriverUserAdminForm

    fieldsets = UserAdmin.fieldsets + (
        (None, {'fields': ('is_formal', 'is_temporary', 'notification_email', 'wants_notification')}),
    )

    # 合并姓名方法
    def full_name(self, obj):
        # 可自定义顺序（姓+名 or 名+姓），如下为【姓+名】
        return f"{obj.first_name}{obj.last_name}"
    full_name.short_description = "姓名"

    list_display = (
        'username',                # 用户名
        'full_name',               # 合并后的姓名
        'email',                   # 系统邮箱
        'notification_email',      # 通知用邮箱（如需）
        'is_formal',
        'is_temporary',
        'wants_notification',
    )

# 3️⃣ 注册
admin.site.register(DriverUser, DriverUserAdmin)

# 4️⃣ 注册 UserProfile 模型（权限扩展）
@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'is_vehicles_admin', 'is_staffbook_admin', 'is_carinfo_admin']
    list_editable = ['is_vehicles_admin', 'is_staffbook_admin', 'is_carinfo_admin']
    search_fields = ['user__username']