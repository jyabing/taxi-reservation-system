from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import DriverUser

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
    list_display = UserAdmin.list_display + ('is_formal', 'is_temporary', 'notification_email', 'wants_notification')

# 3️⃣ 注册
admin.site.register(DriverUser, DriverUserAdmin)
