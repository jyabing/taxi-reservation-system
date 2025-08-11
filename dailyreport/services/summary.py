import logging
from decimal import Decimal, ROUND_HALF_UP
from collections import defaultdict
from dateutil.relativedelta import relativedelta
from django.db.models import Sum, Q
from dailyreport.models import DriverDailyReportItem

# 只使用外部实现，避免被本文件的重复定义覆盖
from .resolve import resolve_payment_method
from dailyreport.constants import PAYMENT_RATES  # 如果未使用 PAYMENT_KEYWORDS，这里不要再导入它
from dailyreport.utils import normalize

# 你项目里现金系的支付方式（保持与你数据库一致）
CASH_METHODS = ["cash", "uber_cash", "didi_cash", "go_cash"]

def is_cash(payment_method: str) -> bool:
    # 后端只认 'cash'；平台现金前端已并入 cash，这里不要再出现 *_cash 枚举
    return payment_method == "cash"

def calculate_totals_from_formset(data_iter):
    raw_totals = defaultdict(Decimal)
    meter_only_total = Decimal(0)
    nagashi_cash_total = Decimal(0)
    nagashi_cash_bonus = Decimal(0)

    # 与实例版保持一致的貸切统计
    charter_cash_total = Decimal(0)
    charter_uncollected_total = Decimal(0)

    CHARTER_CASH_METHODS = {"jpy_cash", "rmb_cash", "self_wechat", "boss_wechat"}
    CHARTER_UNCOLLECTED_METHODS = {"to_company", "bank_transfer", ""}

    for data in data_iter:
        note = (data.get("note") or "").strip()
        meter_fee = normalize(data.get("meter_fee", 0))
        payment_method = data.get("payment_method", "")
        method_key = resolve_payment_method(payment_method)

        is_charter = bool(data.get("is_charter", False))
        charter_amount = normalize(data.get("charter_amount_jpy", 0))
        charter_method = (data.get("charter_payment_method") or "").strip()

        # 只统计有效非取消单
        if meter_fee > 0 and "キャンセル" not in note:
            # メータのみ：只算“非貸切”行
            if not is_charter:
                meter_only_total += meter_fee
                if method_key:
                    raw_totals[method_key] += meter_fee
                if is_cash(method_key):
                    nagashi_cash_total += meter_fee
                    nagashi_cash_bonus += meter_fee * PAYMENT_RATES.get(method_key, 0)

        # 貸切金额：按枚举分别进 现金 / 未収
        if is_charter and charter_amount > 0:
            if charter_method in CHARTER_CASH_METHODS:
                charter_cash_total += charter_amount
            elif charter_method in CHARTER_UNCOLLECTED_METHODS:
                charter_uncollected_total += charter_amount

    # 输出结构
    result = {
        key: {
            "total": round(raw_totals.get(key, 0)),
            "bonus": round(raw_totals.get(key, 0) * PAYMENT_RATES[key]),
        }
        for key in PAYMENT_RATES
    }

    result["meter_only_total"] = round(meter_only_total)
    result["nagashi_cash"] = {
        "total": round(nagashi_cash_total),
        "bonus": round(nagashi_cash_bonus),
    }

    # 额外给出与实例版一致的几个汇总，供上层使用（不影响已有字段）
    result["charter_cash_total"] = round(charter_cash_total)
    result["charter_uncollected_total"] = round(charter_uncollected_total)
    result["deposit_total"] = round(nagashi_cash_total + charter_cash_total)
    result["sales_total"] = round(meter_only_total + charter_cash_total + charter_uncollected_total)

    return result


def calculate_totals_from_instances(item_instances):
    raw_totals = defaultdict(Decimal)
    meter_only_total = Decimal(0)
    nagashi_cash_total = Decimal(0)
    nagashi_cash_bonus = Decimal(0)

    # 🔽 貸切合计
    charter_cash_total = Decimal(0)
    charter_uncollected_total = Decimal(0)

    # 与前端一致的貸切枚举（如你已有统一函数，可改成调用）
    CHARTER_CASH_METHODS = {"jpy_cash", "rmb_cash", "self_wechat", "boss_wechat"}
    CHARTER_UNCOLLECTED_METHODS = {"to_company", "bank_transfer", ""}

    for item in item_instances:
        note = getattr(item, "note", "") or ""
        meter_fee = normalize(getattr(item, "meter_fee", 0))
        payment_method = getattr(item, "payment_method", "")
        method_key = resolve_payment_method(payment_method)

        is_charter = bool(getattr(item, "is_charter", False))
        charter_amount = normalize(getattr(item, "charter_amount_jpy", 0))
        charter_method_raw = getattr(item, "charter_payment_method", "") or ""
        charter_method = charter_method_raw.strip()

        # 💡 只统计“有效非取消单”
        if meter_fee > 0 and "キャンセル" not in note:
            # ✅ メータのみ：只算“非貸切”行
            if not is_charter:
                meter_only_total += meter_fee
                if method_key:
                    raw_totals[method_key] += meter_fee
                if is_cash(method_key):
                    nagashi_cash_total += meter_fee
                    nagashi_cash_bonus += meter_fee * PAYMENT_RATES.get(method_key, 0)

        # 🔽 貸切金额按支付方式分别进入“現金/未収”
        if is_charter and charter_amount > 0:
            if charter_method in CHARTER_CASH_METHODS:
                charter_cash_total += charter_amount
            elif charter_method in CHARTER_UNCOLLECTED_METHODS:
                charter_uncollected_total += charter_amount
            # 其它未知枚举不计入，避免误差

    # ✅ 输出结构：各支付方式 total/bonus（bonus 按你既有费率）
    result = {
        key: {
            "total": round(raw_totals.get(key, 0)),
            "bonus": round(raw_totals.get(key, 0) * PAYMENT_RATES[key]),
        }
        for key in PAYMENT_RATES
    }

    # ✅ メータのみ
    result["meter_only_total"] = round(meter_only_total)
    # 如需保留“ながし現金”单独显示：
    result["nagashi_cash"] = {
        "total": round(nagashi_cash_total),
        "bonus": round(nagashi_cash_bonus),
    }
    # 若模板还读这个字段，让它等于メータのみ（兼容）
    result["meter_total"] = round(meter_only_total)

    # ✅ 貸切合计
    result["charter_cash_total"] = round(charter_cash_total)
    result["charter_uncollected_total"] = round(charter_uncollected_total)

    # ✅ 入金合计（現金(ながし) + 貸切現金）
    result["deposit_total"] = round(nagashi_cash_total + charter_cash_total)

    # ✅ 売上合計 = メータのみ + 貸切現金 + 貸切未収
    # 这里不要再把 nagashi_cash 或 sum(raw_totals) 叠加一次（它们已包含在 meter_only_total 内）
    result["sales_total"] = round(meter_only_total + charter_cash_total + charter_uncollected_total)

    return result

def calculate_totals_from_queryset(queryset):
    return calculate_totals_from_instances(list(queryset))

def build_month_aggregates(items_qs):
    """
    月报聚合：
    - 現金合計（只统计非貸切的现金系 meter_fee）
    - 貸切現金 合計（统计 is_charter=True 且 charter_payment_method='jpy_cash' 的 charter_amount_jpy）
    - 貸切未収 合計（统计 is_charter=True 且 charter_payment_method='to_company' 的 charter_amount_jpy）
    """
    if not isinstance(items_qs, (DriverDailyReportItem._default_manager.__class__().all().__class__,)):
        # 容错：传进来不是 QuerySet 的情况
        items_qs = DriverDailyReportItem.objects.none()

    # ✅ 普通現金合計（明确排除貸切）
    cash_total = (
        items_qs.filter(
            is_charter=False,
            payment_method__in=CASH_METHODS
        ).aggregate(total=Sum("meter_fee"))["total"]
        or Decimal("0")
    )

    # ✅ 貸切現金 合計
    charter_cash_total = (
        items_qs.filter(
            is_charter=True,
            charter_payment_method="jpy_cash"
        ).aggregate(total=Sum("charter_amount_jpy"))["total"]
        or Decimal("0")
    )

    # ✅ 貸切未収 合計
    charter_uncollected_total = (
        items_qs.filter(
            is_charter=True,
            charter_payment_method="to_company"
        ).aggregate(total=Sum("charter_amount_jpy"))["total"]
        or Decimal("0")
    )

    return {
        "cash_total": cash_total,
        "charter_cash_total": charter_cash_total,
        "charter_uncollected_total": charter_uncollected_total,
    }