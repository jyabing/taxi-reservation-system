# ===== dailyreport/order_analysis.py  BEGIN =====
from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from django.utils.timezone import localdate
from django.utils.dateparse import parse_date

from .models import DriverDailyReportItem, DriverDailyReport, Driver


# --------------------------------------------------
# 小工具：把各种类型统一成 date（修复 fromisoformat 报错）
# --------------------------------------------------
def _coerce_to_date(value, default: Optional[date] = None) -> Optional[date]:
    """
    支持:
        - None            -> default
        - date            -> 原样返回
        - datetime        -> .date()
        - 'YYYY-MM-DD'    -> 解析为 date
        其它类型           -> default
    """
    if value is None:
        return default
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return default
        d = parse_date(s)
        return d or default
    return default


# --------------------------------------------------
# 支付方式归一化（与 _totals_of / export Excel 统一）
# --------------------------------------------------
def _canon_payment_method(v: str) -> str:
    if not v:
        return ""
    s = str(v).strip().lower()
    mapping = {
        "現金": "cash",
        "现金": "cash",
        "cash(現金)": "cash",

        "uber現金": "uber_cash",
        "didi現金": "didi_cash",
        "go現金": "go_cash",

        "バーコード": "qr",
        "barcode": "qr",
        "bar_code": "qr",
        "qr_code": "qr",

        "company card": "credit",
        "company_card": "credit",
        "credit card": "credit",
        "会社カード": "credit",

        "jp_cash": "jpy_cash",
        "jpy cash": "jpy_cash",
        "jpy-cash": "jpy_cash",

        # 貸切支付方式（与 _normalize 一致）
        "日元現金": "jpy_cash",
        "日元现金": "jpy_cash",
        "人民幣現金": "rmb_cash",
        "人民币现金": "rmb_cash",
        "自有微信": "self_wechat",
        "老板微信": "boss_wechat",
        "公司回收": "to_company",
        "会社回収": "to_company",
        "公司结算": "to_company",
        "銀行振込": "bank_transfer",
        "bank": "bank_transfer",
        "--------": "",
        "------": "",
    }
    return mapping.get(s, s)


# —— 这三类 Uber 特殊别名，只看“精确匹配” —— #
UBER_RESV_ALIASES = {"uber_reservation", "uber_resv", "uber予約"}
UBER_TIP_ALIASES = {"uber_tip", "uber tip", "ubertip"}
UBER_PROMO_ALIASES = {"uber_promo", "uber_promotion", "uberプロモーション"}

# 貸切“现金”/“未收”/“其它”分类口径
CHARTER_CASH_KEYS = {"jpy_cash", "rmb_cash", "self_wechat", "boss_wechat", "cash", "jp_cash"}
CHARTER_UNCOL_KEYS = {"to_company", "bank_transfer", ""}


@dataclass
class MonthlyOrderStats:
    """
    每月订单结构统计结果（全员或单一司机）
    所有金额单位：日元 int
    """
    meter_water_total: int = 0          # メーター(水揚)合計 = メーターのみ + 貸切(現金/未収/不明)
    meter_only_total: int = 0           # 非貸切・有支付方式的メーター合計

    cash_total: int = 0                 # 现金(メーター侧：含 uber_cash/didi_cash/go_cash)
    uber_total: int = 0                 # Uber売上（不含预约/チップ/プロモ）
    didi_total: int = 0
    go_total: int = 0
    credit_total: int = 0
    kyokushin_total: int = 0
    omron_total: int = 0
    kyotoshi_total: int = 0
    qr_total: int = 0                   # PayPay / 条码支付

    charter_cash_total: int = 0         # 貸切現金
    charter_uncollected_total: int = 0  # 貸切未収 (to_company/bank_transfer/空白)
    charter_unknown_total: int = 0      # 其它不认识的貸切支付方式合计

    uber_reservation_total: int = 0     # Uber予約
    uber_tip_total: int = 0             # Uberチップ
    uber_promotion_total: int = 0       # Uberプロモーション

    def as_dict(self) -> dict:
        """方便丢进模板 / 前端图表"""
        return {f.name: getattr(self, f.name) for f in fields(self)}


# --------------------------------------------------
# 主函数：构建月度订单结构统计
# --------------------------------------------------
def build_monthly_order_stats(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    driver: Optional[Driver] = None,
) -> MonthlyOrderStats:
    """
    根据 DriverDailyReportItem 统计某一时间段内的订单结构。
    - date_from / date_to:
        * 可以是 date/datetime/字符串("YYYY-MM-DD")
        * 不传则默认为“本月 1 日 ～ 本月末”
    - driver:
        * 传入 Driver 实例时，只统计该司机
        * 不传则统计全员
    """
    today = localdate()

    # 归一化起止日期（修复 fromisoformat: argument must be str）
    month_first = today.replace(day=1)
    if date_from is None and date_to is None:
        # 默认：本月
        date_from = month_first
        # 下个月 1 日 - 1 天
        next_month = (month_first.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
        date_to = next_month - datetime.timedelta(days=1)
    else:
        date_from = _coerce_to_date(date_from, default=month_first)
        date_to = _coerce_to_date(date_to, default=today)

    # 保护：如果 date_from > date_to，交换
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from

    # 取对应日期范围的明细行
    qs = (
        DriverDailyReportItem.objects
        .select_related("report", "report__driver")
        .filter(
            report__date__gte=date_from,
            report__date__lte=date_to,
        )
    )
    if driver is not None:
        qs = qs.filter(report__driver=driver)

    stats = MonthlyOrderStats()

    for it in qs:
        is_charter = bool(getattr(it, "is_charter", False))
        meter_fee = int(getattr(it, "meter_fee", 0) or 0)
        charter_jpy = int(getattr(it, "charter_amount_jpy", 0) or 0)

        pm_raw = getattr(it, "payment_method", "")
        cpm_raw = getattr(it, "charter_payment_method", "")

        pm = _canon_payment_method(pm_raw)
        cpm = _canon_payment_method(cpm_raw)

        # ------------ 先处理三类 Uber 特殊单 ------------
        if not is_charter:
            # 非貸切 → 看 payment_method
            if pm in UBER_RESV_ALIASES:
                stats.uber_reservation_total += meter_fee
                # 这三类不再计入普通 Uber / 现金等
                continue
            if pm in UBER_TIP_ALIASES:
                stats.uber_tip_total += meter_fee
                continue
            if pm in UBER_PROMO_ALIASES:
                stats.uber_promotion_total += meter_fee
                continue
        else:
            # 貸切 → 看 charter_payment_method
            if cpm in UBER_RESV_ALIASES:
                stats.uber_reservation_total += charter_jpy
                continue
            if cpm in UBER_TIP_ALIASES:
                stats.uber_tip_total += charter_jpy
                continue
            if cpm in UBER_PROMO_ALIASES:
                stats.uber_promotion_total += charter_jpy
                continue

        # ------------ 常规票据合计 ------------
        if not is_charter:
            # 非貸切：只要有支付方式，就计入 meter_only_total
            if pm:
                stats.meter_only_total += meter_fee

            # 现金（含各平台现金别名）
            if pm in {"cash", "uber_cash", "didi_cash", "go_cash", "jpy_cash"}:
                stats.cash_total += meter_fee

            # 平台/信売
            if pm == "uber":
                stats.uber_total += meter_fee
            elif pm == "didi":
                stats.didi_total += meter_fee
            elif pm == "go":
                stats.go_total += meter_fee
            elif pm in {"credit", "credit_card"}:
                stats.credit_total += meter_fee
            elif pm == "kyokushin":
                stats.kyokushin_total += meter_fee
            elif pm == "omron":
                stats.omron_total += meter_fee
            elif pm == "kyotoshi":
                stats.kyotoshi_total += meter_fee
            elif pm in {"qr", "scanpay"}:
                stats.qr_total += meter_fee

        else:
            # 貸切：金额来源是 charter_jpy
            amt = charter_jpy
            if amt <= 0:
                continue

            # 现金/未收/未知 分类
            if cpm in CHARTER_CASH_KEYS:
                stats.charter_cash_total += amt
            elif cpm in CHARTER_UNCOL_KEYS:
                stats.charter_uncollected_total += amt
            else:
                stats.charter_unknown_total += amt

            # 同时计入信売/平台明细（口径与 Excel 导出一致）
            if cpm == "kyokushin":
                stats.kyokushin_total += amt
            elif cpm == "omron":
                stats.omron_total += amt
            elif cpm == "kyotoshi":
                stats.kyotoshi_total += amt
            elif cpm == "uber":
                stats.uber_total += amt
            elif cpm == "didi":
                stats.didi_total += amt
            elif cpm == "go":
                stats.go_total += amt
            elif cpm in {"credit", "credit_card"}:
                stats.credit_total += amt
            elif cpm in {"qr", "scanpay"}:
                stats.qr_total += amt

    # 最后统一计算メーター(水揚)合計
    stats.meter_water_total = (
        stats.meter_only_total
        + stats.charter_cash_total
        + stats.charter_uncollected_total
        + stats.charter_unknown_total
    )
    return stats


# ===== dailyreport/order_analysis.py  END =====
