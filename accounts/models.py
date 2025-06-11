from django.contrib.auth.models import AbstractUser, User
from django.db import models
from django.conf import settings

# ✅ 你已使用的自定义用户模型
class DriverUser(AbstractUser):
    is_formal = models.BooleanField('正社員', default=False)
    is_temporary = models.BooleanField('アルバイト', default=False)
    notification_email = models.EmailField('通知用メールアドレス', blank=True, null=True)
    wants_notification = models.BooleanField('接收系统通知', default=False)

    def __str__(self):
        return self.username

# ✅ 权限扩展模型，正确绑定 DriverUser
class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    is_vehicles_admin = models.BooleanField(default=False, verbose_name="配车系统管理员")
    is_staffbook_admin = models.BooleanField(default=False, verbose_name="员工台账系统管理员")
    is_carinfo_admin = models.BooleanField(default=False, verbose_name="车辆管理系统管理员")

    def __str__(self):
        return self.user.username