from decimal import Decimal, ROUND_HALF_UP

def normalize(value):
    try:
        return Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0")