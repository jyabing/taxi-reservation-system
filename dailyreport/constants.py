# dailyreport/constants.py

from decimal import Decimal

# ⛳ 支付方式关键字与费率配置
PAYMENT_KEYWORDS = {
    'qr':        ['qr', 'コード', '扫码', 'barcode', 'wechat', 'paypay', '支付宝', 'aupay', 'line', 'スマホ'],
    'kyokushin': ['京交信タクチケ', '京交信', '京交信タクシーチケット', '京交信券', '京交信チケット'],
    'omron':     ['omron', 'オムロン', 'オムロン(愛のタクシーチケット)', 'オムロン券', '愛のタクシーチケット', 'omron_pay', 'omuron'],
    'kyotoshi':  ['京都市'],
    'credit':    ['クレジット', 'クレジットカード', 'クレカ', 'クレジ', 'credit', 'credit_card', 'visa', 'mastercard'],  # ← 修正：加逗号
    'uber':      ['uber', 'uber現金', 'uber（現金）', 'ウーバー', 'ウーバー現金'],
    'didi':      ['didi', 'didi現金', 'didi（現金）', 'didi cash', 'ディディ', 'ディディ現金'],
    'cash':      ['cash', '現金', 'ながし', 'uber_cash'],
}

PAYMENT_RATES = {
    'meter':     Decimal('0.9091'),
    'cash':      Decimal('0'),
    'uber':      Decimal('0.05'),
    'didi':      Decimal('0.05'),
    'credit':    Decimal('0.05'),
    'kyokushin': Decimal('0.05'),
    'omron':     Decimal('0.05'),
    'kyotoshi':  Decimal('0.05'),
    'qr':        Decimal('0.05'),
}

CHARTER_PAYMENT_CHOICES = [

]

# 参与「貸切現金」「貸切未収」汇总用的键名集合（来自 charter_payment_method）
CHARTER_CASH_KEYS = ['jp_cash', 'cash']
CHARTER_UNCOLLECTED_KEYS = ['to_company', 'invoice', 'uncollected', '未収', '請求']