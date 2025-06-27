from decimal import Decimal
from collections import defaultdict

# ⛳ 共通关键词映射（用于模糊匹配支付方式）
PAYMENT_KEYWORDS = {
    'qr':        ['qr', 'コード', '扫码', 'barcode', 'wechat', 'paypay', '支付宝', 'aupay', 'line', 'スマホ'],
    'kyokushin': ['京交信'],
    'omron':     ['オムロン'],
    'kyotoshi':  ['京都市'],
}

# ✅ 用于表单页：FormSet 汇总
def calculate_totals_from_formset(formset):
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

    for row in formset:
        # row 是 DriverDailyReportItem 实例，不是 form

        amt = getattr(row, 'meter_fee', Decimal('0')) or Decimal('0')
        pay = getattr(row, 'payment_method', '') or ''

        pay_clean = (
            str(pay).replace("　", "")
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

        matched = False
        for key, keywords in PAYMENT_KEYWORDS.items():
            if any(keyword.lower() in pay_clean for keyword in keywords):
                raw[key] += amt
                split[key] += amt * rates[key]
                matched = True
                break

        if not matched and pay_clean in rates:
            raw[pay_clean] += amt
            split[pay_clean] += amt * rates[pay_clean]

    totals = {}
    for k in rates:
        totals[f"{k}_raw"] = raw[k]
        totals[f"{k}_split"] = split[k]
    return totals


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
