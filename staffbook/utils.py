from datetime import date
from decimal import Decimal
from django.db.models import Q
from collections import defaultdict
from django.contrib.auth.decorators import user_passes_test
from calendar import monthrange
from .models import Driver
import builtins
builtins.print = lambda *args, **kwargs: None

# ⛳ 共通关键词映射（用于模糊匹配支付方式）
PAYMENT_KEYWORDS = {
    'qr':        ['qr', 'コード', '扫码', 'barcode', 'wechat', 'paypay', '支付宝', 'aupay', 'line', 'スマホ'],
    'kyokushin': ['京交信タクチケ'],
    'omron':     ['オムロン(愛のタクシーチケット)'],
    'kyotoshi':  ['京都市'],
}

# ✅ 用于表单页：FormSet 汇总
def calculate_totals_from_formset(data_iter):
    result = {}
    rates = {
        'meter':  Decimal('0.9091'),
        'cash':   Decimal('0'),
        'uber':   Decimal('0.05'),
        'didi':   Decimal('0.05'),
        'credit': Decimal('0.05'),
        'kyokushin': Decimal('0.05'),
        'omron':     Decimal('0.05'),
        'kyotoshi':  Decimal('0.05'),
        'qr':        Decimal('0.05'),
    }

    for key in rates:
        result[f"{key}_raw"] = Decimal('0')
        result[f"{key}_split"] = Decimal('0')

    for item in data_iter:
        if item.get('DELETE'):
            continue

        fee = item.get('meter_fee') or Decimal('0')
        method = item.get('payment_method')

        # ✅ 无论支付方式如何，都加总至 meter_raw 和 meter_split
        result["meter_raw"] += fee
        result["meter_split"] += fee * rates['meter']

        if method in rates:
            result[f"{method}_raw"] += fee
            result[f"{method}_split"] += (fee * rates[method])

    return result


# ✅ 用于 overview 页：QuerySet 汇总
def calculate_totals_from_queryset(queryset):
    rates = {
        'meter':     Decimal('0.9091'),
        'cash':      Decimal('0'),
        'uber':      Decimal('0.05'),
        'didi':      Decimal('0.05'),
        'credit':    Decimal('0.05'),
        'kyokushin': Decimal('0.05'),
        'omron':     Decimal('0.05'),
        'kyotoshi':  Decimal('0.05'),
        'qr':        Decimal('0.05'),
    }

    raw   = defaultdict(lambda: Decimal('0'))
    split = defaultdict(lambda: Decimal('0'))

    print("🚨 当前获取记录数：", len(queryset))
    for item in queryset:
        print("🔎 支払方式：", item.payment_method, "金額：", item.meter_fee)
        amt = item.meter_fee or Decimal('0')
        pay = item.payment_method or ''

        pay_clean = (
            pay.replace("　", "")
               .replace("（", "")
               .replace("）", "")
               .replace("(", "")
               .replace(")", "")
               .replace("\n", "")
               .strip()
               .lower()
        )

        raw['meter'] += amt
        split['meter'] += amt * rates['meter']

        print(f"🔍 原始: '{pay}' -> clean: '{pay_clean}'")

        matched = False
        for key, keywords in PAYMENT_KEYWORDS.items():
            if any(keyword.lower() in pay_clean for keyword in keywords):
                print(f"✅ 匹配成功: {key} <- {pay_clean}")
                raw[key] += amt
                split[key] += amt * rates[key]
                matched = True
                break

        if not matched and pay_clean in rates:
            print(f"📌 直接命中 key: {pay_clean}")
            raw[pay_clean] += amt
            split[pay_clean] += amt * rates[pay_clean]

    totals = {}
    for k in rates:
        totals[f"{k}_raw"] = raw[k]
        totals[f"{k}_split"] = split[k]
    return totals

def apply_form_control_style(fields):
    """
    给所有表单字段添加 Bootstrap 的 'form-control' 样式（跳过 checkbox 和 radio）
    """
    for field in fields.values():
        if not getattr(field.widget, 'input_type', '') in ['checkbox', 'radio']:
            existing_class = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = (existing_class + ' form-control').strip()

def is_dailyreport_admin(user):
    return user.is_superuser or getattr(user, 'is_dailyreport_admin', False)

# 可选：用于视图装饰器
dailyreport_admin_required = user_passes_test(is_dailyreport_admin)


def get_active_drivers(month_obj, keyword=None):
    """
    参数:
        month_obj: datetime.date 或 datetime.datetime 对象，代表查询的月份
        keyword: 可选关键字（姓名模糊匹配）
    返回:
        在该月内在职的 Driver queryset
    """
    year = month_obj.year
    month = month_obj.month
    first_day = date(year, month, 1)
    last_day = date(year, month, monthrange(year, month)[1])

    qs = Driver.objects.filter(
        hire_date__lte=last_day
    ).filter(
        Q(resigned_date__isnull=True) | Q(resigned_date__gte=first_day)
    )

    if keyword:
        qs = qs.filter(name__icontains=keyword)

    return qs