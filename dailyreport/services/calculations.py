from collections import defaultdict

def calculate_totals_from_queryset(data_iter):
    """
    从 form.cleaned_data 或 report.items.all() 中统计所有支付方式合计。
    返回格式：
    {
        'cash': {'total': 12345, 'bonus': 0},
        'uber': {...},
        ...
        'charter_bank': {...},  # 貸切振込单独显示
    }
    """
    totals = defaultdict(lambda: {'total': 0, 'bonus': 0})

    # 所有允许的支付方式
    valid_methods = ['cash', 'uber', 'didi', 'ticket', 'credit', 'qr', 'charter_cash', 'charter_bank']

    for item in data_iter:
        if isinstance(item, dict):
            fee = item.get('meter_fee') or 0
            method = item.get('payment_method')
            note = item.get('note') or ''
        else:
            fee = item.meter_fee or 0
            method = item.payment_method
            note = item.note or ''

        # ✅ 跳过负数和取消项目
        if fee <= 0 or 'キャンセル' in note or method not in valid_methods:
            continue

        # ✅ 貸切現金计入 cash，同时单独记录
        if method == 'charter_cash':
            totals['cash']['total'] += fee
            totals['charter_cash']['total'] += fee
        # ✅ 貸切振込单独记录
        elif method == 'charter_bank':
            totals['charter_bank']['total'] += fee
        else:
            totals[method]['total'] += fee

    return totals


def calculate_deposit_difference(report, cash_total):
    """
    比较入金（deposit_amount）与现金收入（cash_total）之间的差额。
    - 返回 正值 表示多收；
    - 负值 表示少收；
    - 默认为 0。
    """
    deposit = report.deposit_amount or 0
    return deposit - cash_total