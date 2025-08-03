from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from collections import defaultdict
from dateutil.relativedelta import relativedelta
from .resolve import resolve_payment_method, is_charter
from dailyreport.constants import PAYMENT_RATES, PAYMENT_KEYWORDS
from dailyreport.utils import normalize

def normalize(val):
    try:
        return Decimal(str(val)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0")

def resolve_payment_method(raw_payment: str) -> str:
    """
    统一解析支付方式关键词，返回 key（如 cash、card、uber、didi 等）
    """
    if not raw_payment:
        return ""

    raw_payment = raw_payment.strip()
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

def is_charter(method_key: str) -> bool:
    return method_key in ["charter_cash", "charter_card", "charter_bank", "charter_barcode"]
#def is_cash_nagashi(method: str) -> bool:
#    key = resolve_payment_method(method)
#    return key in ["cash", "didi_cash", "uber_cash", "go_cash"]

def is_cash(payment_method: str) -> bool:
    return payment_method in ["cash", "charter_cash", "uber_cash", "didi_cash", "go_cash"]

def calculate_totals_from_formset(data_iter):
    from collections import defaultdict
    from dailyreport.constants import PAYMENT_RATES
    from .resolve import resolve_payment_method
    from dailyreport.utils import normalize

    raw_totals = defaultdict(Decimal)
    meter_only_total = Decimal(0)
    nagashi_cash_total = Decimal(0)
    nagashi_cash_bonus = Decimal(0)

    for data in data_iter:
        note = data.get("note", "") or ""
        meter_fee = normalize(data.get("meter_fee", 0))

        payment_method = data.get("payment_method", "")
        method_key = resolve_payment_method(payment_method)

        if meter_fee > 0 and "キャンセル" not in note and method_key:
            # ✅ 将原 meter_fee 统计入各分类
            raw_totals[method_key] += meter_fee
            meter_only_total += meter_fee  # charter 已无，全部计入

            if is_cash(method_key):
                nagashi_cash_total += meter_fee
                nagashi_cash_bonus += meter_fee * PAYMENT_RATES.get(method_key, 0)

        # ✅ charter_fee 统一加到 cash（忽略 charter_payment_method）
        charter_fee = normalize(data.get("charter_fee", 0))
        if charter_fee > 0 and "キャンセル" not in note:
            raw_totals["cash"] += charter_fee
            nagashi_cash_total += charter_fee
            nagashi_cash_bonus += charter_fee * PAYMENT_RATES.get("cash", 0)

    result = {
        key: {
            "total": round(raw_totals[key]),
            "bonus": round(raw_totals[key] * PAYMENT_RATES[key])
        }
        for key in PAYMENT_RATES
    }

    result["meter_only_total"] = round(meter_only_total)
    result["nagashi_cash"] = {
        "total": round(nagashi_cash_total),
        "bonus": round(nagashi_cash_bonus)
    }

    return result


def calculate_totals_from_instances(item_instances):
    from dailyreport.constants import PAYMENT_RATES
    from dailyreport.utils import normalize

    raw_totals = defaultdict(Decimal)
    meter_only_total = Decimal(0)
    nagashi_cash_total = Decimal(0)
    nagashi_cash_bonus = Decimal(0)

    for item in item_instances:
        note = getattr(item, "note", "") or ""
        meter_fee = normalize(getattr(item, "meter_fee", 0))

        payment_method = getattr(item, "payment_method", "")
        method_key = resolve_payment_method(payment_method)

        if meter_fee > 0 and "キャンセル" not in note and method_key:
            raw_totals[method_key] += meter_fee
            meter_only_total += meter_fee

            if is_cash(method_key):
                nagashi_cash_total += meter_fee
                nagashi_cash_bonus += meter_fee * PAYMENT_RATES.get(method_key, 0)

        charter_fee = normalize(getattr(item, "charter_fee", 0))
        if charter_fee > 0 and "キャンセル" not in note:
            raw_totals["cash"] += charter_fee
            nagashi_cash_total += charter_fee
            nagashi_cash_bonus += charter_fee * PAYMENT_RATES.get("cash", 0)

    result = {
        key: {
            "total": round(raw_totals[key]),
            "bonus": round(raw_totals[key] * PAYMENT_RATES[key])
        }
        for key in PAYMENT_RATES
    }

    result["meter_only_total"] = round(meter_only_total)
    result["nagashi_cash"] = {
        "total": round(nagashi_cash_total),
        "bonus": round(nagashi_cash_bonus)
    }

    return result

def calculate_totals_from_queryset(queryset):
    """
    从 QuerySet 生成统计汇总（封装实例处理）
    """
    item_list = list(queryset)
    return calculate_totals_from_instances(item_list)