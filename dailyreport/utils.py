from decimal import Decimal
from collections import defaultdict
from django import forms

# ⛳ 支付方式关键字与费率配置
PAYMENT_KEYWORDS = {
    'qr':        ['qr', 'コード', '扫码', 'barcode', 'wechat', 'paypay', '支付宝', 'aupay', 'line', 'スマホ'],
    'kyokushin': ['京交信タクチケ'],
    'omron':     ['オムロン(愛のタクシーチケット)'],
    'kyotoshi':  ['京都市'],
}

PAYMENT_RATES = {
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


# ✅ 清理并识别支付方式
def resolve_payment_method(raw_payment: str) -> str:
    if not raw_payment:
        return ""

    cleaned = (
        raw_payment.replace("　", "")
                   .replace("（", "")
                   .replace("）", "")
                   .replace("(", "")
                   .replace(")", "")
                   .replace("\n", "")
                   .strip()
                   .lower()
    )

    for key, keywords in PAYMENT_KEYWORDS.items():
        if any(keyword.lower() in cleaned for keyword in keywords):
            return key

    if cleaned in PAYMENT_RATES:
        return cleaned

    return ""  # 未识别支付方式


# ✅ 共通合计逻辑（传入 (fee, method) 数据对）
def calculate_totals_from_items(item_iterable):
    raw_totals   = defaultdict(lambda: Decimal('0'))
    split_totals = defaultdict(lambda: Decimal('0'))

    for fee, method in item_iterable:
        fee = fee or Decimal('0')
        key = resolve_payment_method(method)

        # 总是加入 meter 的统计
        raw_totals['meter']   += fee
        split_totals['meter'] += fee * PAYMENT_RATES['meter']

        if key in PAYMENT_RATES:
            raw_totals[key]   += fee
            split_totals[key] += fee * PAYMENT_RATES[key]

    # 返回标准化键名：xxx_raw / xxx_split
    totals = {}
    for k in PAYMENT_RATES:
        totals[f"{k}_raw"]   = raw_totals[k]
        totals[f"{k}_split"] = split_totals[k]
    return totals


# ✅ 表单页用：从 FormSet cleaned_data 计算
def calculate_totals_from_formset(form_data_list):
    pairs = []
    for item in form_data_list:
        if item.get('DELETE'):
            continue
        fee = item.get('meter_fee')
        method = item.get('payment_method')
        note = item.get('note', '')

        # ✅ 排除负数和“キャンセル”备注
        if fee is None or fee <= 0:
            continue
        if 'キャンセル' in str(note):
            continue

        pairs.append((fee, method))
    return calculate_totals_from_items(pairs)


# ✅ 数据库页用：从 QuerySet 计算
def calculate_totals_from_queryset(queryset):
    pairs = []
    for item in queryset:
        fee = getattr(item, 'meter_fee', Decimal('0'))
        method = getattr(item, 'payment_method', '')
        pairs.append((fee, method))
    return calculate_totals_from_items(pairs)

# ✅ 通用样式工具：为所有字段添加 Bootstrap class
def apply_form_control_style(fields):
    for name, field in fields.items():
        widget = field.widget
        if not isinstance(widget, (forms.CheckboxInput, forms.RadioSelect, forms.HiddenInput)):
            existing_class = widget.attrs.get('class', '')
            widget.attrs['class'] = f"{existing_class} form-control".strip()
