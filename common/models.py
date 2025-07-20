# common/models.py
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class LinkClickLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    link_name = models.CharField(max_length=255)
    link_url = models.URLField(max_length=500)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} clicked {self.link_name} at {self.timestamp}"
