from django import template

register = template.Library()

def calculate_totals(report):
    items = report.items.all()
    result = {
        "meter": 0, "cash": 0, "uber": 0, "didi": 0, "credit": 0,
        "kyokushin": 0, "omron": 0, "kyotoshi": 0, "qr": 0
    }
    for item in items:
        if item.payment_method and item.meter_fee:
            key = item.payment_method
            if key in result:
                result[key] += item.meter_fee

    bonus = {}
    for key, amount in result.items():
        if key == "meter":
            bonus[key] = round(amount * 0.5)
        elif key in ["cash", "uber", "didi"]:
            bonus[key] = round(amount * 0.9)
        else:
            bonus[key] = round(amount * 1.0)

    return {
        f"total_{k}": v for k, v in result.items()
    } | {
        f"{k}_split": v for k, v in bonus.items()
    }

@register.filter
def get_total(totals, key):
    return totals.get(f"total_{key}", 0)

@register.filter
def get_bonus(totals, key):
    return totals.get(f"{key}_split", 0)
