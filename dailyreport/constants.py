# dailyreport/constants.py

from decimal import Decimal

# ⛳ 支付方式关键字与费率配置
PAYMENT_KEYWORDS = {
    'qr':        ['qr', 'コード', '扫码', 'barcode', 'wechat', 'paypay', '支付宝', 'aupay', 'line', 'スマホ'],
    'kyokushin': ['京交信タクチケ'],
    'omron':     ['オムロン(愛のタクシーチケット)'],
    'kyotoshi':  ['京都市'],
    'credit':    ['クレジット', 'クレジットカード', 'クレカ', 'credit', 'visa', 'mastercard'],
    
    'uber':      ['uber', 'uber現金', 'uber（現金）', 'ウーバー', 'ウーバー現金'],
    'didi':      ['didi', 'didi現金', 'didi（現金）', 'didi cash', 'ディディ', 'ディディ現金'],
    
    "charter_cash": ["貸切（現金）", "charter cash", "チャーター現金"],
    "charter_card": ["貸切（クレジ）", "charter card", "チャータークレジ"],
    "charter_bank": ["貸切（振込）", "charter bank", "チャーター振込"],  # ✅ 新增
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
    "charter_cash":  Decimal('0'),
    "charter_card":  Decimal('0.05'),
    "charter_bank": Decimal('0'),  # ✅ 按照振込设定为 0
}

CHARTER_PAYMENT_CHOICES = [
    ("charter_cash", "現金"),
    ("charter_card", "クレジットカード"),
    ("charter_bank", "振込"),
    ("charter_barcode", "バーコード"),
]