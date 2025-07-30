from dailyreport.constants import PAYMENT_KEYWORDS

def resolve_payment_method(raw_payment: str) -> str:
    if not raw_payment:
        return ""

    # ✅ 统一清理括号、空格、换行符等
    cleaned = (
        raw_payment.replace("　", "")  # 去除全角空格
                .replace("（", "")    # 去掉括号内容（含全角）
                .replace("）", "")
                .replace("(", "")
                .replace(")", "")
                .replace("\n", "")
                .strip()
                .lower()
    )

    # ✅ fallback：处理明文输入（如“現金”）
    fallback_map = {
        "現金": "charter_cash",
        "クレジットカード": "charter_card",
        "振込": "charter_bank",
        "バーコード": "charter_barcode",
    }
    if raw_payment in fallback_map:
        return fallback_map[raw_payment]

    if cleaned == "credit_card":
        return "credit"

    for key, keywords in PAYMENT_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in cleaned:
                return key

    print(f"⚠️ 未识别支付方式: {raw_payment} -> cleaned: {cleaned}")
    return None