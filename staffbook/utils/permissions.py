# staffbook/utils/permissions.py
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from django.db.models import Q
from staffbook.models import Driver

def get_active_drivers(target_month, keyword: str = ""):
    """
    返回 target_month 当月在职的司机：
    入职日 <= 当月末 且 (未退职 或 退职日 >= 当月初)
    target_month: date 或 "YYYY-MM"
    """
    # 允许传 "YYYY-MM"
    if isinstance(target_month, str):
        y, m = map(int, target_month.split("-"))
        month_start = date(y, m, 1)
    else:
        month_start = date(target_month.year, target_month.month, 1)

    month_end = (month_start + relativedelta(months=1)) - timedelta(days=1)

    qs = Driver.objects.filter(
        # 用户账号需可用（如不想限制可去掉这一行）
        user__is_active=True
    ).filter(
        Q(entry_date__lte=month_end) &                               # 入职不晚于当月末
        (Q(resigned_date__isnull=True) | Q(resigned_date__gte=month_start))  # 未退 或 退职不早于当月初
    )

    if keyword:
        qs = qs.filter(name__icontains=keyword)

    return qs.order_by('driver_code', 'name')
