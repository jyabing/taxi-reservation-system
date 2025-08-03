from decimal import Decimal
from collections import defaultdict
from django import forms
from dailyreport.services.summary import resolve_payment_method


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
        print(f"💰 処理中: {fee}円, 原始={method}, 解釈後={key}")

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

# ✅ 通用样式工具：为所有字段添加 Bootstrap class
def apply_form_control_style(fields):
    for name, field in fields.items():
        widget = field.widget
        if not isinstance(widget, (forms.CheckboxInput, forms.RadioSelect, forms.HiddenInput)):
            existing_class = widget.attrs.get('class', '')
            widget.attrs['class'] = f"{existing_class} form-control".strip()
