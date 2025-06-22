# staffbook/constants.py

PAYMENT_METHOD_GROUPS = [
    ("平台类", [
        ("uber", "Uber"),
        ("didi", "Didi"),
        ("credit", "クレジ"),
    ]),
    ("扫码类", [
        ("barcode", "扫码"),
        ("cash", "現金(ながし)"),
    ]),
    ("补助类", [
        ("jingjiaoxin", "京交信"),
        ("omron", "オムロン"),
        ("kyoto", "京都市他"),
    ]),
]

# 从上面的 group 自动生成扁平的 choices 列表
PAYMENT_METHOD_CHOICES = [
    choice for _, group in PAYMENT_METHOD_GROUPS for choice in group
]
