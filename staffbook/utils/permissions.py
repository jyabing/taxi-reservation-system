import calendar
from datetime import datetime, date, timedelta   # ← 增加 datetime
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from django.db.models import Q
from django.core.exceptions import FieldError
from staffbook.models import Driver


def get_active_drivers(target_month, keyword: str = ""):
    """
    支持的 target_month 格式：
      - 'YYYY-MM' / 'YYYY年MM月' / int(月份1..12) / datetime / date / None
    """

    def _normalize_year_month(m):
        today = timezone.localdate()
        y, mth = today.year, today.month

        if isinstance(m, (datetime, date)):
            return m.year, m.month
        if isinstance(m, int):
            return (y, m) if 1 <= m <= 12 else (y, mth)
        if isinstance(m, str):
            s = m.strip()
            for fmt in ("%Y-%m", "%Y年%m月"):
                try:
                    dt = datetime.strptime(s, fmt)
                    return dt.year, dt.month
                except ValueError:
                    pass
            if s.isdigit():
                im = int(s)
                if 1 <= im <= 12:
                    return y, im
            return y, mth
        return y, mth

    year, month = _normalize_year_month(target_month)
    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])

    # 在职：入社 ≤ 当月末 且 （未退职 或 退职日 ≥ 当月初）
    qs = Driver.objects.filter(
        hire_date__lte=last_day
    ).filter(
        Q(resigned_date__isnull=True) | Q(resigned_date__gte=first_day)
    )

    # 关键字：匹配 姓名 / 假名 / 工号
    kw = (keyword or "").strip()
    if kw:
        qs = qs.filter(
            Q(name__icontains=kw) |
            Q(kana__icontains=kw) |
            Q(driver_code__icontains=kw)
        )

    return qs.order_by("driver_code", "name")