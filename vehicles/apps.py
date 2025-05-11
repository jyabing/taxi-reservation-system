import os
from django.apps import AppConfig
import threading
import time

class VehiclesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'vehicles'

    def ready(self):
        if os.environ.get('RUN_MAIN') == 'true':  # 避免重复执行
            from . import scheduler
            scheduler.start()