from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from collections import defaultdict
from dateutil.relativedelta import relativedelta

# ✅ 正确导入 PAYMENT_RATES
from dailyreport.constants import PAYMENT_RATES, PAYMENT_KEYWORDS

def resolve_payment_method(raw_payment: str) -> str:
    """
    统一解析支付方式，返回系统内部 key。
    """
    if not raw_payment:
        return ""

    raw_payment = raw_payment.strip()

    # ✅ 如果本身就是 key（如 "cash" 或 "charter_cash"）
    if raw_payment in PAYMENT_RATES:
        return raw_payment

    if raw_payment in dropdown_map:
        return dropdown_map[raw_payment]
    
    if raw_payment in fallback_map:
        return fallback_map[raw_payment]

    # ✅ 清理括号、空格等
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

    # ✅ 根据关键词匹配 PAYMENT_KEYWORDS
    for key, keywords in PAYMENT_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in cleaned:
                return key

    return ""


def is_charter(payment_method: str) -> bool:
    """
    判断是否为貸切（包车）相关支付方式。
    """
    if not payment_method:
        return False
    cleaned = payment_method.strip().lower()
    return cleaned.startswith("charter")