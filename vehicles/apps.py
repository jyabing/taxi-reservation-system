import os
from django.apps import AppConfig

class VehiclesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "vehicles"

    def ready(self):
        # 1) 注册 signals （保证 Reservation ↔ 日报同步）
        from . import signals  # noqa

        # 2) 启动 scheduler（只在主进程执行一次，避免 runserver 双启动）
        if os.environ.get("RUN_MAIN") == "true":
            from . import scheduler
            scheduler.start()
