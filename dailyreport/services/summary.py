from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from collections import defaultdict
from dailyreport.constants import PAYMENT_RATES, PAYMENT_KEYWORDS

# ✅ 支付方式识别与标准化
def resolve_payment_method(raw_payment: str) -> str:
    if not raw_payment:
        return ""

    cleaned = (
        raw_payment.replace("　", "")   # 全角空格
                   .replace("（", "").replace("）", "")
                   .replace("(", "").replace(")", "")
                   .replace("\n", "").strip().lower()
    )

    if cleaned == "credit_card":
        return "credit"

    for key, keywords in PAYMENT_KEYWORDS.items():
        if any(keyword.lower() in cleaned for keyword in keywords):
            return key

    if cleaned in PAYMENT_RATES:
        return cleaned

    return ""


# ✅ 主逻辑：表单数据统计（用于编辑页）
def calculate_totals_from_formset(data_iter):
    raw_totals = {key: Decimal("0") for key in PAYMENT_RATES}
    split_totals = {key: Decimal("0") for key in PAYMENT_RATES}
    meter_only_total = Decimal("0")

    for item in data_iter:
        try:
            fee = Decimal(str(item.get("meter_fee") or "0"))
        except:
            fee = Decimal("0")

        note = item.get("note", "")
        raw_payment = item.get("payment_method", "")
        key = resolve_payment_method(raw_payment)

        if not key or fee <= 0 or "キャンセル" in note:
            continue

        raw_totals[key] += fee
        split_totals[key] += fee * PAYMENT_RATES[key]

        # ✅ 正确判断：只有非貸切项目才记入 meter_only
        if "貸切" not in raw_payment and "charter" not in raw_payment:
            meter_only_total += fee

    result = {}

    for key in PAYMENT_RATES:
        result[f"{key}_raw"] = round(raw_totals[key])
        result[f"{key}_split"] = round(split_totals[key])

    result["meter_only_total"] = round(meter_only_total)
    print("🧮 meter_only_total:", meter_only_total)
    return result


# ✅ 通用 ORM 明细对象统计函数
def calculate_totals_from_queryset(queryset):
    pairs = []

    for item in queryset:
        fee = getattr(item, 'meter_fee', None)
        method = getattr(item, 'payment_method', None)
        note = getattr(item, 'note', '')

        if fee is None or fee <= 0:
            continue
        if 'キャンセル' in str(note):
            continue

        pairs.append((fee, method))

    return calculate_totals_from_items(pairs)


# ✅ 给定 (fee, method) 结构计算 totals
def calculate_totals_from_items(pairs):
    raw_totals = {key: Decimal("0") for key in PAYMENT_RATES}
    split_totals = {key: Decimal("0") for key in PAYMENT_RATES}
    meter_only_total = Decimal("0")

    for fee, raw_payment in pairs:
        key = resolve_payment_method(raw_payment)
        if not key or fee <= 0:
            continue

        raw_totals[key] += fee
        split_totals[key] += fee * PAYMENT_RATES[key]

        if not raw_payment or "貸切" not in raw_payment:
            meter_only_total += fee

    result = {}
    for key in PAYMENT_RATES:
        result[f"{key}_raw"] = round(raw_totals[key])
        result[f"{key}_split"] = round(split_totals[key])
    result["meter_only_total"] = round(meter_only_total)
    return result


# ✅ 报表等场合使用的 bonus/合计结构
def build_totals_from_items(items):
    totals = defaultdict(Decimal)
    meter_only_total = Decimal('0')

    rates = PAYMENT_RATES
    valid_keys = PAYMENT_RATES.keys()

    for item in items:
        if not item.meter_fee or item.meter_fee <= 0:
            continue
        if item.note and 'キャンセル' in item.note:
            continue

        key = item.payment_method or 'unknown'
        amount = item.meter_fee
        totals[f"total_{key}"] += amount
        totals["total_meter"] += amount

        if "貸切" not in key:
            meter_only_total += amount

    totals_all = {}
    for key in valid_keys:
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


# ✅ ETC 实收、入金额、差额 等统计
def calculate_received_and_etc_deficit(
    data_iter,
    etc_expected=None,
    etc_collected=None,
    etc_payment_method=""
):
    received_amount = Decimal("0")
    meter_only_total = Decimal("0")

    for item in data_iter:
        try:
            fee = Decimal(str(item.get("meter_fee") or "0"))
        except (InvalidOperation, TypeError):
            fee = Decimal("0")

        note = item.get("note", "")
        raw_payment = item.get("payment_method", "")
        key = resolve_payment_method(raw_payment)

        if not key or fee <= 0 or "キャンセル" in note:
            continue

        if "貸切" not in raw_payment and "charter" not in raw_payment:
            meter_only_total += fee

        if key == "cash":
            received_amount += fee

    try:
        etc_collected = Decimal(str(etc_collected or "0"))
        etc_expected = Decimal(str(etc_expected or "0"))
    except (InvalidOperation, TypeError):
        etc_collected = Decimal("0")
        etc_expected = Decimal("0")

    if resolve_payment_method(etc_payment_method) == "cash":
        received_amount += etc_collected

    etc_deficit = Decimal("0")
    if etc_collected > etc_expected:
        etc_deficit = etc_collected - etc_expected

    return {
        "received_amount": round(received_amount),
        "etc_deficit": round(etc_deficit),
    }
