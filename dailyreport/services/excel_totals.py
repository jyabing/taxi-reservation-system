from decimal import Decimal

def calculate_excel_style_totals(items):
    totals = {
        "meter_total": Decimal("0"),
        "cash_total": Decimal("0"),
        "charter_cash": Decimal("0"),
        "etc": Decimal("0"),
    }

    for it in items:
        meter = Decimal(getattr(it, "meter_fee", 0) or 0)
        pm = str(getattr(it, "payment_method", "") or "").lower()
        is_charter = bool(getattr(it, "is_charter", False))

        # メーター
        totals["meter_total"] += meter

        # ながし現金
        if not is_charter and "cash" in pm:
            totals["cash_total"] += meter

    return totals
