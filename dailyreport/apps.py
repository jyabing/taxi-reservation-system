from django.apps import AppConfig

class DailyreportConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "dailyreport"   # 路径
    # 不要自定义 label；默认等于 'dailyreport'
    def ready(self):
        from . import signals  # noqa
