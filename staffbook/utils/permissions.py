from django.contrib.auth.decorators import user_passes_test

def is_dailyreport_admin(user):
    return user.is_authenticated and (user.is_superuser or user.groups.filter(name='日報管理').exists())

def get_active_drivers(year=None, month=None):
    from staffbook.models import Driver
    from datetime import date

    qs = Driver.objects.filter(user__is_active=True)

    if year and month:
        month_start = date(year, month, 1)
        qs = qs.filter(
            entry_date__lte=month_start,
        ).filter(
            Q(resigned_date__isnull=True) | Q(resigned_date__gte=month_start)
        )

    return qs