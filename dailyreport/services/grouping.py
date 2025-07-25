from collections import defaultdict
from decimal import Decimal
from .rates import rates  # ✅ 用外部 rates.py 中定义的比例

def group_report_items(items):
    """
    将 DriverDailyReportItem 列表按 combined_group 分组，合并为“一单”的结构。
    返回结构为：
    {
        'A': {'items': [...], 'total': ..., 'group_id': 'A'},
        '__single_123': {...}
    }
    """
    grouped = defaultdict(list)
    result = {}

    for item in items:
        group_id = item.combined_group or f"__single_{item.pk or id(item)}"
        grouped[group_id].append(item)

    for group_id, item_list in grouped.items():
        total = sum((i.meter_fee or Decimal("0")) for i in item_list)
        result[group_id] = {
            "items": item_list,
            "total": total,
            "group_id": group_id,
        }

    return result


def calculate_totals_from_grouped_items(grouped_items, report=None):
    totals = defaultdict(Decimal)
    counts = defaultdict(int)

    for group_id, group in grouped_items.items():
        for item in group['items']:
            if not item.payment_method:
                continue
            if not item.meter_fee or item.meter_fee <= 0:
                continue
            if item.note and 'キャンセル' in item.note:
                continue

            key = item.payment_method
            fee = item.meter_fee
            rate = rates.get(key, Decimal("0"))
            bonus = (fee * rate).quantize(Decimal("1"))

            totals[key] += fee
            totals[f"{key}_raw"] += fee
            totals[f"{key}_split"] += bonus
            totals["meter_raw"] += fee

            counts[f"{key}_count"] += 1

            print(f"🧾 ID:{item.pk} 支付方式:{key} 金额:{fee} 分成:{bonus} 备注:{item.note or ''}")

    # 🔧 ETC 处理：额外添加 report.etc_collected
    if report:
        if report.etc_collected and report.etc_payment_method:
            key = report.etc_payment_method
            fee = report.etc_collected
            rate = rates.get(key, Decimal("0"))
            bonus = (fee * rate).quantize(Decimal("1"))
            totals[key] += fee
            totals[f"{key}_raw"] += fee
            totals[f"{key}_split"] += bonus
            print(f"🚗 ETC收款 金額:{fee} 支付方式:{key} 分成:{bonus}")
            print("🚩 grouped totals:", result)

    result = {}
    result.update(totals)
    result.update(counts)
    return result
