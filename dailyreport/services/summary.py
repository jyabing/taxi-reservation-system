from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from collections import defaultdict
from dailyreport.constants import PAYMENT_RATES, PAYMENT_KEYWORDS
from dateutil.relativedelta import relativedelta

def is_charter(method: str) -> bool:
    if not method:
        return False
    return resolve_payment_method(method).startswith("charter")


def is_cash_nagashi(payment_method: str, is_charter_flag: bool = False) -> bool:
    if is_charter_flag:
        return False
    keywords = ['現金', 'Didi（現金）', 'Uber（現金）', 'Go（現金）']
    return any(k in payment_method for k in keywords)

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

        # ✅ 精准判断是否属于メータのみ（排除貸切）
        if key != "charter":
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
        if not key:
            print(f"⚠️ 未识别的支付方式: {raw_payment}")
            continue
        if fee is None or fee <= 0:
            print(f"⚠️ 金额为 None: {raw_payment}")
            continue

        raw_totals[key] += fee
        split_totals[key] += fee * PAYMENT_RATES[key]

        # ✅ 替换前: if not raw_payment or "貸切" not in raw_payment:
        # ✅ 替换后:
        if not is_charter(raw_payment):
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

        # ✅ 替换前: if "貸切" not in key:
        # ✅ 替换后:
        if not is_charter(key):
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
def calculate_received_summary(
    data_iter,
    etc_expected=None,
    etc_collected=None,
    etc_payment_method=""
):
    received_meter_cash = Decimal("0")
    received_charter = Decimal("0")
    received_etc_cash = Decimal("0")
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

        if not is_charter(raw_payment):
            meter_only_total += fee
            if is_cash_nagashi(raw_payment, False):
                received_meter_cash += fee

        if is_charter(raw_payment):
            received_charter += fee

    # ETC 收入（如果是现金方式）
    try:
        etc_collected = Decimal(str(etc_collected or "0"))
        etc_expected = Decimal(str(etc_expected or "0"))
    except (InvalidOperation, TypeError):
        etc_collected = Decimal("0")
        etc_expected = Decimal("0")

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
