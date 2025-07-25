# ✅ 文件路径: dailyreport/services/summary.py

from decimal import Decimal
from collections import defaultdict
from dailyreport.constants import PAYMENT_RATES, PAYMENT_KEYWORDS

# ✅ 清理并识别支付方式
def resolve_payment_method(raw_payment: str) -> str:
    print(f"🔍 [resolve] 原始值: {raw_payment!r}")
    if not raw_payment:
        return ""

    # 清洗输入值
    cleaned = (
        raw_payment.replace("　", "")   # 去除全角空格
                   .replace("（", "")   # 去除括号
                   .replace("）", "")
                   .replace("(", "")
                   .replace(")", "")
                   .replace("\n", "")   # 去除换行
                   .strip()             # 去除前后空格
                   .lower()             # 全部转小写
    )

    # ✅ 添加 credit_card 映射
    if cleaned == "credit_card":
        return "credit"

    # 2️⃣ 匹配关键字
    for key, keywords in PAYMENT_KEYWORDS.items():
        if any(keyword.lower() in cleaned for keyword in keywords):
            return key

    #3️⃣ 兜底匹配（严格匹配）
    if cleaned in PAYMENT_RATES:
        return cleaned

        print(f"➡️  解析结果: {cleaned!r} => {key!r}")

    return ""  # 未识别支付方式



def calculate_totals_from_formset(data_iter):
    """
    根据日报明细数据（通常来自 FormSet cleaned_data），统计每种支付方式的总额和分润金额。
    返回结构如：{"meter_raw": 10000, "meter_split": 5000, "cash_raw": ..., ...}
    """
    raw_totals = {key: Decimal("0") for key in PAYMENT_RATES}
    split_totals = {key: Decimal("0") for key in PAYMENT_RATES}
    meter_only_total = Decimal("0")

    for item in data_iter:
        # ✅ 修复关键：确保 fee 是 Decimal 类型
        try:
            fee = Decimal(str(item.get("meter_fee") or "0"))
        except:
            fee = Decimal("0")

        note = item.get("note", "")
        raw_payment = item.get("payment_method", "")
        key = resolve_payment_method(raw_payment)

        print("🧾 收到:", raw_payment, "=>", key, "金額:", fee)

        # 排除空值、负数、取消记录
        if not key or fee <= 0 or "キャンセル" in note:
            continue

        # 合计
        raw_totals[key] += fee
        split_totals[key] += fee * PAYMENT_RATES[key]

        # ✅ 只计入“メータのみ”金額
        meter_only_total += fee

    result = {}

    for key in PAYMENT_RATES:
        result[f"{key}_raw"] = round(raw_totals[key])
        result[f"{key}_split"] = round(split_totals[key])

    result["meter_only_total"] = round(meter_only_total)

    return result


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


def calculate_totals_from_items(pairs):
    """
    通用接口函数：给定 (fee, payment_method) 对，计算 totals 结构。
    """
    raw_totals = {key: Decimal("0") for key in PAYMENT_RATES}
    split_totals = {key: Decimal("0") for key in PAYMENT_RATES}
    meter_only_total = Decimal("0")

    for fee, raw_payment in pairs:
        key = resolve_payment_method(raw_payment)
        if not key or fee <= 0:
            continue

        raw_totals[key] += fee
        split_totals[key] += fee * PAYMENT_RATES[key]
        # ✅ 如果不是貸切，则视为「メータのみ」
        if not raw_payment or "貸切" not in raw_payment:
            meter_only_total += fee

    result = {}
    for key in PAYMENT_RATES:
        result[f"{key}_raw"] = round(raw_totals[key])
        result[f"{key}_split"] = round(split_totals[key])
    result["meter_only_total"] = round(meter_only_total)
    return result