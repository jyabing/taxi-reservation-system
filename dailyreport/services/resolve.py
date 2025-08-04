from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from collections import defaultdict
from dateutil.relativedelta import relativedelta

# ✅ 正确导入 PAYMENT_RATES
from dailyreport.constants import PAYMENT_KEYWORDS

def resolve_payment_method(raw_payment: str) -> str:
    """
    统一解析支付方式关键词，返回 key（如 cash、uber、didi 等）
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
    """
    判断是否属于“現金（ながし）”系列
    """
    return payment_method in ["cash", "uber_cash", "didi_cash", "go_cash"]