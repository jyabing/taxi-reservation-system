from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from collections import defaultdict
from dateutil.relativedelta import relativedelta
from .resolve import resolve_payment_method, is_charter
from dailyreport.constants import PAYMENT_RATES, PAYMENT_KEYWORDS
from dailyreport.utils import normalize

def normalize(value, as_decimal=True):
    if value in [None, '']:
        return Decimal('0') if as_decimal else 0
    try:
        return Decimal(str(value)) if as_decimal else int(value)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal('0') if as_decimal else 0


def is_charter(method: str) -> bool:
    if not method:
        return False
    return resolve_payment_method(method).startswith("charter")


def is_cash_nagashi(payment_method: str, is_charter_flag: bool = False) -> bool:
    if is_charter_flag:
        return False
    keywords = ['現金', 'Didi（現金）', 'Uber（現金）', 'Go（現金）']
    return any(k in payment_method for k in keywords)


def resolve_payment_method(raw_payment: str) -> str:
    """
    统一解析支付方式字段，返回用于统计的标准 key。
    """
    if not raw_payment:
        return ""

    raw_payment = raw_payment.strip()

    charter_map = {
        "貸切（現金）": "cash",  # ✅ 修改后
        "貸切（クレジ）": "card",
        "貸切（クレジット）": "card",
        "貸切（振込）": "bank",
    }
    if raw_payment in charter_map:
        return charter_map[raw_payment]

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
        for keyword in keywords:
            if keyword.lower() in cleaned:
                return key

    return ""

def normalize(val):
    try:
        return Decimal(str(val)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0")


def is_charter_cash(key: str) -> bool:
    """是否是貸切（現金）支付方式"""
    return key in ["charter_cash", "貸切（現金）", "charter現金", "貸切現金"]


def calculate_totals_from_formset(data_iter):
    from decimal import Decimal
    from dailyreport.constants import PAYMENT_RATES
    from .resolve import resolve_payment_method, is_charter

    raw_totals = {key: Decimal("0") for key in PAYMENT_RATES}
    split_totals = {key: Decimal("0") for key in PAYMENT_RATES}
    meter_only_total = Decimal("0")
    meter_only_per_key = {key: Decimal("0") for key in PAYMENT_RATES}

    for item in data_iter:
        fee = normalize(item.get("meter_fee"))
        note = item.get("note", "")
        raw_payment = item.get("payment_method", "")
        key = resolve_payment_method(raw_payment)

        if key and fee > 0 and "キャンセル" not in note:
            raw_totals[key] += fee
            split_totals[key] += fee * PAYMENT_RATES[key]

            if not is_charter(key):
                meter_only_total += fee
                meter_only_per_key[key] += fee

        # 🔽 charter（貸切）处理
        charter_fee = normalize(item.get("charter_fee"))
        charter_method = item.get("charter_payment_method", "")
        charter_key = resolve_payment_method(charter_method)

        if charter_key and charter_fee > 0:
            raw_totals[charter_key] += charter_fee
            split_totals[charter_key] += charter_fee * PAYMENT_RATES[charter_key]

        # ✅ 补丁：兼容 “貸切誤填在 meter_fee” 的情况
        if key and is_charter(key) and fee > 0 and "キャンセル" not in note:
            raw_totals[key] += fee
            split_totals[key] += fee * PAYMENT_RATES[key]

    # ✅ 返回结构化格式 totals[key] = {total: ..., bonus: ...}
    result = {
        key: {
            "total": round(raw_totals[key]),
            "bonus": round(split_totals[key])
        }
        for key in PAYMENT_RATES
    }

    result["meter_only_total"] = round(meter_only_total)
    return result

def calculate_received_summary(data_iter, etc_expected=None, etc_collected=None, etc_payment_method=""):
    received_meter_cash = Decimal("0")
    received_charter = Decimal("0")
    received_etc_cash = Decimal("0")
    meter_only_total = Decimal("0")

    for item in data_iter:
        fee = normalize(item.get("meter_fee"))
        note = item.get("note", "")
        raw_payment = item.get("payment_method", "")
        key = resolve_payment_method(raw_payment)

        if not key or fee <= 0 or "キャンセル" in note:
            continue

        if not is_charter(raw_payment):
            meter_only_total += fee
            if is_cash_nagashi(raw_payment):
                received_meter_cash += fee
        else:
            if is_cash_nagashi(raw_payment) or resolve_payment_method(raw_payment) == "charter_cash":
                received_meter_cash += fee
            else:
                received_charter += fee

    etc_collected = normalize(etc_collected)
    etc_expected = normalize(etc_expected)

    if resolve_payment_method(etc_payment_method) == "cash":
        received_etc_cash = etc_collected

    deposit_total = received_meter_cash + received_charter + received_etc_cash
    etc_deficit = max(Decimal("0"), etc_expected - etc_collected)

    return {
        "received_meter_cash": round(received_meter_cash),
        "received_charter": round(received_charter),
        "received_etc_cash": round(received_etc_cash),
        "deposit_total": round(deposit_total),
        "etc_deficit": round(etc_deficit),
        "meter_only_total": round(meter_only_total),
    }


def calculate_totals_from_instances(item_instances):
    print("[DEBUG] using calculate_totals_from_instances()")

    raw_totals = {key: Decimal("0") for key in PAYMENT_RATES}
    meter_only_total = Decimal("0")

    for item in item_instances:
        note = getattr(item, 'note', '') or ''
        meter_fee = normalize(getattr(item, 'meter_fee', 0))
        payment_method = getattr(item, 'payment_method', '')
        method_key = resolve_payment_method(payment_method)

        if meter_fee > 0 and 'キャンセル' not in note and method_key:
            raw_totals[method_key] += meter_fee
            if not is_charter(method_key):
                meter_only_total += meter_fee

    result = {}
    for key in PAYMENT_RATES:
        result[key] = {
            "total": round(raw_totals[key]),
            "bonus": round(raw_totals[key] * PAYMENT_RATES[key])
        }
    result["meter_only_total"] = round(meter_only_total)
    return result
    

def calculate_totals_from_queryset(queryset):
    """
    从 QuerySet 生成统计汇总（封装实例处理）
    """
    item_list = list(queryset)
    return calculate_totals_from_instances(item_list)