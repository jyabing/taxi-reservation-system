from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from collections import defaultdict
from dateutil.relativedelta import relativedelta
from .resolve import resolve_payment_method
from dailyreport.constants import PAYMENT_RATES, PAYMENT_KEYWORDS


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


def resolve_payment_method(method: str) -> str:
    if not method:
        return ''

    cleaned = (
        method.replace('　', '')  # 全角空格
              .replace('（', '(')
              .replace('）', ')')
              .replace('\n', '')
              .strip()
    )

    if cleaned == '現金(ながし)':
        return 'cash'
    elif cleaned.lower() == 'uber':
        return 'uber'
    elif cleaned.lower() == 'didi':
        return 'didi'
    elif cleaned == 'クレジットカード':
        return 'credit'
    elif '京交信' in cleaned:
        return 'kyokushin'
    elif 'オムロン' in cleaned:
        return 'omron'
    elif '京都市' in cleaned or '京田辺' in cleaned or '京丹後' in cleaned:
        return 'kyotoshi'
    elif '扫码' in cleaned or 'バーコード' in cleaned:
        return 'qr'

    elif '貸切' in cleaned:
        if '現金' in cleaned:
            return 'charter_cash'
        elif '振込' in cleaned:
            return 'charter_bank'
        elif 'クレジ' in cleaned or 'クレジット' in cleaned:
            return 'charter_card'

    print(f"⚠️ 未识别支付方式: {method} -> cleaned: {cleaned}")
    return ''

def calculate_totals_from_formset(data_iter):
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
            if not is_charter(raw_payment):
                meter_only_total += fee
                meter_only_per_key[key] += fee

        charter_fee = normalize(item.get("charter_fee"))
        charter_method = item.get("charter_payment_method", "")
        charter_key = resolve_payment_method(charter_method)

        if charter_key and charter_fee > 0:
            raw_totals[charter_key] += charter_fee
            split_totals[charter_key] += charter_fee * PAYMENT_RATES[charter_key]

    result = {f"{key}_raw": round(raw_totals[key]) for key in PAYMENT_RATES}
    result.update({f"{key}_split": round(split_totals[key]) for key in PAYMENT_RATES})
    result["meter_only_total"] = round(meter_only_total)
    return result


def calculate_totals_from_queryset(queryset):
    pairs = []
    for item in queryset:
        fee = getattr(item, 'meter_fee', None)
        method = getattr(item, 'payment_method', None)
        note = getattr(item, 'note', '')
        if fee is None or fee <= 0 or 'キャンセル' in str(note):
            continue
        pairs.append((fee, method))
    return calculate_totals_from_items(pairs)


def calculate_totals_from_items(pairs):
    raw_totals = {key: Decimal("0") for key in PAYMENT_RATES}
    split_totals = {key: Decimal("0") for key in PAYMENT_RATES}
    meter_only_total = Decimal("0")
    meter_only_per_key = {key: Decimal("0") for key in PAYMENT_RATES}

    for fee, raw_payment in pairs:
        fee = normalize(fee)
        key = resolve_payment_method(raw_payment)
        if not key or fee <= 0:
            continue
        raw_totals[key] += fee
        split_totals[key] += fee * PAYMENT_RATES[key]
        if not is_charter(raw_payment):
            meter_only_total += fee
            meter_only_per_key[key] += fee

    result = {f"{key}_raw": round(raw_totals[key]) for key in PAYMENT_RATES}
    result.update({f"{key}_split": round(split_totals[key]) for key in PAYMENT_RATES})
    result.update({f"{key}_meter_only_total": round(meter_only_per_key[key]) for key in PAYMENT_RATES})
    result["meter_only_total"] = round(meter_only_total)
    return result


def build_totals_from_items(items):
    totals = defaultdict(Decimal)
    meter_only_total = Decimal('0')
    rates = PAYMENT_RATES
    for item in items:
        fee = normalize(getattr(item, 'meter_fee', None))
        note = getattr(item, 'note', '')
        if fee <= 0 or 'キャンセル' in str(note):
            continue
        key = item.payment_method or 'unknown'
        totals[f"total_{key}"] += fee
        totals["total_meter"] += fee
        if not is_charter(key):
            meter_only_total += fee

    totals_all = {}
    for key in PAYMENT_RATES:
        total = totals.get(f"total_{key}", Decimal('0'))
        bonus = (total * rates.get(key, Decimal('0'))).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        totals_all[key] = {"total": total, "bonus": bonus}

    meter_total = totals.get("total_meter", Decimal("0"))
    totals_all["meter"] = {
        "total": meter_total,
        "bonus": (meter_total * rates['meter']).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    }
    totals_all["meter_only_total"] = meter_only_total
    return totals_all


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
    meter_total = Decimal("0")
    charter_total = Decimal("0")

    for item in item_instances:
        note = getattr(item, 'note', '') or ''
        meter_fee = normalize(getattr(item, 'meter_fee', 0))
        payment_method = getattr(item, 'payment_method', '')
        method_key = resolve_payment_method(payment_method)

        # ✅ 核心修正：如果支付方式是 charter 系，meter_fee 当作 charter_total
        if meter_fee > 0 and 'キャンセル' not in note and method_key:
            raw_totals[method_key] += meter_fee
            meter_total += meter_fee

            # ✅ 如果是 charter 类型，也计入 charter_total
            if method_key.startswith('charter_'):
                charter_total += meter_fee

        # charter_fee 字段暂时忽略（你没用上）
        # charter_fee = normalize(getattr(item, 'charter_fee', 0))
        # charter_method = getattr(item, 'charter_payment_method', '')
        # charter_key = resolve_payment_method(charter_method)
        # if charter_fee > 0 and 'キャンセル' not in note and charter_key:
        #     raw_totals[charter_key] += charter_fee
        #     charter_total += charter_fee

    result = {f"{key}_raw": round(raw_totals[key]) for key in raw_totals}
    result["total"] = sum(result.values())
    result["meter_total"] = round(meter_total)
    result["charter_total"] = round(charter_total)
    return result