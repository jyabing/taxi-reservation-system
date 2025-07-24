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


# ✅ 核心逻辑，共通合计逻辑（传入 (fee, method) 数据对）
def calculate_totals_from_items(item_iterable):
    raw_totals   = defaultdict(lambda: Decimal('0'))
    split_totals = defaultdict(lambda: Decimal('0'))

    # 附加统计
    cash_total = Decimal('0')
    charter_total = Decimal('0')
    charter_cash_total = Decimal('0')
    charter_transfer_total = Decimal('0')
    meter_only_total = Decimal('0')
    meter_total = Decimal('0')

    for fee, method in item_iterable:
        fee = fee or Decimal('0')
        key = resolve_payment_method(method)

        # ✅ 所有都计入总売上
        meter_total += fee

        # ✅ 排除 charter_xxx 即为メータのみ
        if not (method or "").startswith("charter"):
            meter_only_total += fee

        # 现金合计
        if method in ['cash', 'uber_cash', 'didi_cash', 'go_cash']:
            cash_total += fee

        # 貸切合计
        if method in ['charter_cash', 'charter_transfer']:
            charter_total += fee
            if method == 'charter_cash':
                charter_cash_total += fee
            else:
                charter_transfer_total += fee

        # 原有分润统计逻辑
        raw_totals['meter']   += fee
        split_totals['meter'] += fee * PAYMENT_RATES['meter']

        if key in PAYMENT_RATES:
            raw_totals[key]   += fee
            split_totals[key] += fee * PAYMENT_RATES[key]

    totals = {}
    for k in PAYMENT_RATES:
        totals[f"{k}_raw"]   = raw_totals[k]
        totals[f"{k}_split"] = split_totals[k]

    # ⬇️ 加入新的聚合项
    totals.update({
        'cash_total': cash_total,
        'charter_total': charter_total,
        'charter_cash_total': charter_cash_total,
        'charter_transfer_total': charter_transfer_total,
        'meter_only_total': meter_only_total,
        'meter_total': meter_total,
    })

    return totals


# ✅ 前端页面编辑时，从 form.cleaned_data 或实例计算合计
def calculate_totals_from_formset(form_data_list):
    pairs = []
    for item in form_data_list:
        try:
            # 兼容 cleaned_data (dict) 和 instance (model)
            if isinstance(item, dict):
                if item.get('DELETE'):
                    continue
                fee = item.get('meter_fee')
                method = item.get('payment_method')
                note = item.get('note', '')
            else:
                if getattr(item, 'DELETE', False):
                    continue
                fee = getattr(item, 'meter_fee', None)
                method = getattr(item, 'payment_method', None)
                note = getattr(item, 'note', '')

            # 排除负数和“キャンセル”备注
            if fee is None or fee <= 0:
                continue
            if 'キャンセル' in str(note):
                continue

            pairs.append((fee, method))
        except Exception as e:
            print(f"⚠️ 合计计算中错误项: {e}")
            continue

    return calculate_totals_from_items(pairs)

# ✅ 直接从模型实例列表计算合计
# 后端构造新对象或 instance 时调用
def calculate_totals_from_instances(item_instances):
    pairs = []
    for item in item_instances:
        if getattr(item, 'DELETE', False):  # 一般模型中不会有 DELETE，但保留逻辑
            continue
        fee = getattr(item, 'meter_fee', None)
        method = getattr(item, 'payment_method', None)
        note = getattr(item, 'note', '')

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
