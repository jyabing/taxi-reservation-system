from django.contrib.auth.models import AbstractUser
from django.db import models

class DriverUser(AbstractUser):
    is_formal = models.BooleanField(default=False)
    is_temporary = models.BooleanField(default=False)

    def __str__(self):
        return self.username
