from decimal import Decimal, InvalidOperation

def normalize(value) -> Decimal:
    """
    将字符串或数字标准化为 Decimal，空值或非法输入返回 Decimal('0')
    """
    try:
        if value in [None, '', 'None']:
            return Decimal('0')
        return Decimal(str(value)).quantize(Decimal('1'))  # 保留整数
    except (InvalidOperation, TypeError, ValueError):
        return Decimal('0')
