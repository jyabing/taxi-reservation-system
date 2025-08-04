from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from collections import defaultdict
from dateutil.relativedelta import relativedelta
from .resolve import resolve_payment_method
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

def is_cash(payment_method: str) -> bool:
    return payment_method in ["cash", "uber_cash", "didi_cash", "go_cash"]

def calculate_totals_from_formset(data_iter):
    raw_totals = defaultdict(Decimal)
    meter_only_total = Decimal(0)
    nagashi_cash_total = Decimal(0)
    nagashi_cash_bonus = Decimal(0)

    for data in data_iter:
        note = data.get("note", "") or ""
        meter_fee = normalize(data.get("meter_fee", 0))
        payment_method = data.get("payment_method", "")
        method_key = resolve_payment_method(payment_method)

        if meter_fee > 0 and "キャンセル" not in note:
            meter_only_total += meter_fee
            if method_key:
                raw_totals[method_key] += meter_fee

            if is_cash(method_key):
                nagashi_cash_total += meter_fee
                nagashi_cash_bonus += meter_fee * PAYMENT_RATES.get(method_key, 0)

    # ✅ 修正：只遍历 PAYMENT_RATES，防止统计非法 key（例如 ""）
    result = {
        key: {
            "total": round(raw_totals.get(key, 0)),
            "bonus": round(raw_totals.get(key, 0) * PAYMENT_RATES[key])
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
    raw_totals = defaultdict(Decimal)
    meter_only_total = Decimal(0)
    nagashi_cash_total = Decimal(0)
    nagashi_cash_bonus = Decimal(0)

    for item in item_instances:
        note = getattr(item, "note", "") or ""
        meter_fee = normalize(getattr(item, "meter_fee", 0))
        payment_method = getattr(item, "payment_method", "")
        method_key = resolve_payment_method(payment_method)

        print(f"[🧾 ITEM] id={item.id}, pay=《{payment_method}》=> key=《{method_key}》, fee={meter_fee}")

        if meter_fee > 0 and "キャンセル" not in note:
            meter_only_total += meter_fee
            if method_key:
                raw_totals[method_key] += meter_fee

            if is_cash(method_key):
                nagashi_cash_total += meter_fee
                nagashi_cash_bonus += meter_fee * PAYMENT_RATES.get(method_key, 0)

    # ✅ 同样修正遍历 key 来源
    result = {
        key: {
            "total": round(raw_totals.get(key, 0)),
            "bonus": round(raw_totals.get(key, 0) * PAYMENT_RATES[key])
        }
        for key in PAYMENT_RATES
    }

    result["meter_only_total"] = round(meter_only_total)
    result["nagashi_cash"] = {
        "total": round(nagashi_cash_total),
        "bonus": round(nagashi_cash_bonus)
    }

    result["meter_total"] = round(meter_only_total)

    return result

def calculate_totals_from_queryset(queryset):
    return calculate_totals_from_instances(list(queryset))

def resolve_payment_method(method: str) -> str:
    if not method:
        return ""
    method = method.strip().lower()

    if "cash" in method or "現金" in method:
        return "cash"
    elif "uber" in method:
        return "uber"
    elif "didi" in method:
        return "didi"
    elif "credit" in method or "クレジット" in method:
        return "credit"
    elif "kyokushin" in method or "京交信" in method:
        return "kyokushin"
    elif "omron" in method or "オムロン" in method:
        return "omron"
    elif "kyotoshi" in method or "京都市" in method:
        return "kyotoshi"
    elif "qr" in method or "扫码" in method or "wechat" in method or "alipay" in method:
        return "qr"
    elif "etc" in method:
        return "etc"
    return ""