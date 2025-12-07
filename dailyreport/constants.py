# dailyreport/constants.py

from decimal import Decimal

# ⛳ 支付方式关键字与费率配置
PAYMENT_KEYWORDS = {
    'qr':        ['qr', 'コード', '扫码', 'barcode', 'wechat', 'paypay', '支付宝', 'aupay', 'line', 'スマホ'],
    'kyokushin': ['京交信タクチケ', '京交信', '京交信タクシーチケット', '京交信券', '京交信チケット'],
    'omron':     ['omron', 'オムロン', 'オムロン(愛のタクシーチケット)', 'オムロン券', '愛のタクシーチケット', 'omron_pay', 'omuron'],
    'kyotoshi':  ['京都市'],
    'credit':    ['クレジット', 'クレジットカード', 'クレカ', 'クレジ', 'credit', 'credit_card', 'visa', 'mastercard'],
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

# ===== 这里开始是新增的“计算口径”相关常量 =====
# 进公司的支付方式（公司侧入金）：用于判断“客人的钱到了公司”
COMPANY_SIDE_PAYMENT_KEYS = {
    # 统一认为这些都是“公司侧入金”
    'qr',
    'kyokushin',
    'omron',
    'kyotoshi',
    'credit',
    'uber',
    'didi',
}

# 司机手里的支付方式（不经过公司账户）
DRIVER_SIDE_PAYMENT_KEYS = {
    'cash',   # 现金
    'meter',  # メータ掛け（如果你以后有这种 key）
}

# 参与 ETC / 过不足 计算时，你可以用：
#
#   if payment_key in COMPANY_SIDE_PAYMENT_KEYS:
#       # 这单钱是进公司的：可以用来给司机报销 ETC
#   elif payment_key in DRIVER_SIDE_PAYMENT_KEYS:
#       # 钱在司机手里：不再额外给“実際ETC”报销（已经从客人那边收了）
#
# payment_key 一般来自你现有的 “标准化支付方式” 函数，
# 比如 normalize_payment_method(raw_string) 之类。
# ===== 新增常量到此结束 =====

# 貸切用：下拉选择（charter_payment_method）的候选值
CHARTER_PAYMENT_CHOICES = [
    # key           label（你可以按需要改文案）
    ('',              '---------'),
    ('jp_cash',       '現金（日本円）'),
    ('cash',          '現金（その他／外貨など）'),
    ('to_company',    '会社精算・社内売掛'),
    ('invoice',       '請求書発行（後日請求）'),
    ('uncollected',   '未収（回収予定なし）'),
]

# 参与「貸切現金」「貸切未収」汇总用的键名集合（来自 charter_payment_method）
CHARTER_CASH_KEYS = ['jp_cash', 'cash']
CHARTER_UNCOLLECTED_KEYS = ['to_company', 'invoice', 'uncollected', '未収', '請求']
