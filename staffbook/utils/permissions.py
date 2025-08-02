from django.contrib.auth.decorators import user_passes_test

def is_dailyreport_admin(user):
    return user.is_authenticated and (user.is_superuser or user.groups.filter(name='日報管理').exists())

def get_active_drivers():
    return Driver.objects.filter(resigned_date__isnull=True)