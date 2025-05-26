from django.contrib.auth.models import AbstractUser
from django.db import models

class DriverUser(AbstractUser):
    is_formal = models.BooleanField('正社員',default=False)
    is_temporary = models.BooleanField('アルバイト',default=False)
    notification_email = models.EmailField('通知用メールアドレス', blank=True, null=True)
    wants_notification = models.BooleanField('接收系统通知', default=False)

    def __str__(self):
        return self.username
