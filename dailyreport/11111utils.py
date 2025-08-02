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
                note = str(item.get('note', '') or '')
            else:
                if getattr(item, 'DELETE', False):
                    continue
                fee = getattr(item, 'meter_fee', None)
                method = getattr(item, 'payment_method', None)
                note = str(getattr(item, 'note', '') or '')

            # ✅ 排除负数或空金额
            if not fee or fee <= 0:
                continue

            # ✅ 排除キャンセル项目（支持中英文大小写）
            if 'キャンセル' in note or 'cancel' in note.lower():
                continue

            print("🧾 传入项目：", fee, method)  # ✅ 添加这行调试打印
            pairs.append((fee, method))

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

# ✅ 通用样式工具：为所有字段添加 Bootstrap class
def apply_form_control_style(fields):
    for name, field in fields.items():
        widget = field.widget
        if not isinstance(widget, (forms.CheckboxInput, forms.RadioSelect, forms.HiddenInput)):
            existing_class = widget.attrs.get('class', '')
            widget.attrs['class'] = f"{existing_class} form-control".strip()
