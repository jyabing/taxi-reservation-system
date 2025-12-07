# dailyreport/utils.py
from decimal import Decimal
from collections import defaultdict
from django import forms
from dailyreport.services.summary import resolve_payment_method
from dailyreport.constants import PAYMENT_RATES, CHARTER_CASH_KEYS, CHARTER_UNCOLLECTED_KEYS


# ✅ 核心逻辑，共通合计逻辑（传入 (fee, method) 数据对）
def calculate_totals_from_items(item_iterable):
    """
    用于「入金・売上」的共通合计：
      - 按支付方式统计 raw / split（分润）
      - 统计 total_meter / meter_only / cash_total

    约定：
      - item_iterable 里可以是：
          1) (fee, method) 的二元组
          2) 或者真正的明细对象，具有 .meter_fee / .payment_method 属性
    """
    raw_totals = defaultdict(lambda: Decimal('0'))
    split_totals = defaultdict(lambda: Decimal('0'))

    cash_total = Decimal('0')
    meter_only_total = Decimal('0')
    meter_total = Decimal('0')

    for row in item_iterable:
        # ① 兼容两种输入：tuple 或 对象
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            fee, method = row[0], row[1]
        else:
            # 认为是明细对象
            fee = getattr(row, "meter_fee", None)
            method = getattr(row, "payment_method", "")

        fee = fee or Decimal('0')

        key = resolve_payment_method(method)
        print(f"💰 処理中: {fee}円, 原始={method}, 解釈後={key}")

        # 所有都计入总売上
        meter_total += fee

        # メータのみ = 非 charter 支付方式
        #   ※ charter_xxx 这种是貸切专用，不算入一般メーター売上
        if not (method or "").startswith("charter"):
            meter_only_total += fee

        # 现金合计（含各种现金方式）
        if method in ['cash', 'uber_cash', 'didi_cash', 'go_cash']:
            cash_total += fee

        # 原有分润统计逻辑
        raw_totals['meter'] += fee
        split_totals['meter'] += fee * PAYMENT_RATES['meter']

        if key in PAYMENT_RATES:
            raw_totals[key] += fee
            split_totals[key] += fee * PAYMENT_RATES[key]

    totals = {}
    for k in PAYMENT_RATES:
        totals[f"{k}_raw"] = raw_totals[k]
        totals[f"{k}_split"] = split_totals[k]

    totals.update({
        'cash_total': cash_total,
        'meter_only_total': meter_only_total,
        'meter_total': meter_total,
    })

    return totals


# ✅ 新版：计算「実際ETC 会社→運転手」
def calculate_actual_etc_company_to_driver(items):
    """
    実際ETC（会社 → 運転手）

    口径（和填报指南一致）：
    - 使用司机自己的 ETC 卡（etc_riding_charge_type / etc_empty_charge_type = 'driver'）
    - 不属于“司机自费”的场景
    - 且该 ETC 行通过【公司侧】结算：
        QR / クレジ / Uber / DiDi / 京交信 / オムロン / 京都市 等
    - 乘车 + 空车 ETC 的「实际使用额」全部计入

    例：
        乘车ETC  = 4410（司机卡，支付=QR）
        空车ETC实际使用 = 2150（司机卡，回程费通过 QR 收到 4410）
      → 実際ETC 会社→運転手 = 4410 + 2150 = 6560
    """

    total = Decimal('0')

    # ✅ 公司侧结算的支付方式 key（resolve_payment_method 后的结果）
    COMPANY_SIDE_KEYS = {
        'qr',
        'credit',
        'uber',
        'didi',
        'kyokushin',
        'omron',
        'kyotoshi',
    }

    for item in items:
        # ========= 1️⃣ 乘车 ETC =========
        riding_etc = getattr(item, 'etc_riding', None) or Decimal('0')
        riding_charge = getattr(item, 'etc_riding_charge_type', '')

        # 条件：司机 ETC 垫付 + 公司侧结算
        if riding_etc > 0 and riding_charge == 'driver':
            payment_method_raw = getattr(item, 'payment_method', '') or ''
            payment_key = resolve_payment_method(payment_method_raw)

            if payment_key in COMPANY_SIDE_KEYS:
                total += riding_etc

        # ========= 2️⃣ 空车 ETC（回程） =========
        # ✅ 优先使用「实际使用额」
        empty_etc = (
            getattr(item, 'etc_empty_used_amount', None)
            or getattr(item, 'etc_empty', None)
            or Decimal('0')
        )
        empty_charge = getattr(item, 'etc_empty_charge_type', '')

        if empty_etc > 0 and empty_charge == 'driver':
            # 回程费可能有单独的支付方式，没有就退回主 payment_method
            empty_payment_raw = (
                getattr(item, 'etc_empty_pay_method', None)
                or getattr(item, 'payment_method', '')
                or ''
            )
            empty_payment_key = resolve_payment_method(empty_payment_raw)

            if empty_payment_key in COMPANY_SIDE_KEYS:
                total += empty_etc

    return total


# ✅ 通用样式工具：为所有字段添加 Bootstrap class
def apply_form_control_style(fields):
    for name, field in fields.items():
        widget = field.widget
        if not isinstance(widget, (forms.CheckboxInput, forms.RadioSelect, forms.HiddenInput)):
            existing_class = widget.attrs.get('class', '')
            widget.attrs['class'] = f"{existing_class} form-control".strip()
