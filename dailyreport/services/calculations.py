from collections import defaultdict

def calculate_deposit_difference(report, cash_total):
    """
    比较入金（deposit_amount）与现金收入（cash_total）之间的差额。
    - 返回 正值 表示多收；
    - 负值 表示少收；
    - 默认为 0。
    """
    deposit = report.deposit_amount or 0
    return deposit - cash_total

def calculate_sales_totals(items):
    totals = {
        'cash_total': Decimal('0'),           # 现金ながし合计
        'charter_cash': Decimal('0'),         # 貸切現金
        'charter_unpaid': Decimal('0'),       # 貸切未収
        'didi_total': Decimal('0'),
        'uber_total': Decimal('0'),
        'credit_total': Decimal('0'),
        'kyokoshin_total': Decimal('0'),
        'omron_total': Decimal('0'),
        'kyoto_city_total': Decimal('0'),
        'scanpay_total': Decimal('0'),
        'sales_total': Decimal('0'),
        'meter_only_total': Decimal('0'),
    }

    for item in items:
        note = item.note or ''
        fee = item.meter_fee or 0
        method = item.payment_method or ''

        # ✅ 跳过取消/负数
        if fee <= 0 or 'キャンセル' in note:
            continue

        # ✅ 累加“メータのみ”：仅非包车项
        if not item.is_charter:
            totals['meter_only_total'] += fee

        # ✅ cash_total：现金ながし
        if method == 'cash':
            totals['cash_total'] += fee

        # ✅ 其他平台合计
        elif method == 'didi':
            totals['didi_total'] += fee
        elif method == 'uber':
            totals['uber_total'] += fee
        elif method == 'credit_card':
            totals['credit_total'] += fee
        elif method == 'kyokushin':
            totals['kyokoshin_total'] += fee
        elif method == 'omron':
            totals['omron_total'] += fee
        elif method == 'kyotoshi':
            totals['kyoto_city_total'] += fee
        elif method == 'qr':
            totals['scanpay_total'] += fee

        # ✅ 全部売上合计（不管是否包车）
        totals['sales_total'] += fee

    # ✅ 处理包车金额（独立字段，不依赖 payment_method）
    for item in items:
        if not item.is_charter or not item.charter_amount_jpy:
            continue

        if item.charter_payment_method in ['self_wechat', 'rmb_cash', 'jpy_cash']:
            totals['charter_cash'] += item.charter_amount_jpy
            totals['sales_total'] += item.charter_amount_jpy
            totals['cash_total'] += item.charter_amount_jpy  # ✅ 加入现金合计

        elif item.charter_payment_method in ['to_company', 'boss_wechat', 'bank_transfer']:
            totals['charter_unpaid'] += item.charter_amount_jpy
            totals['sales_total'] += item.charter_amount_jpy

    return totals