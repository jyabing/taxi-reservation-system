from decimal import Decimal, ROUND_HALF_UP
from datetime import date
from django.contrib.auth.models import User


def normalize(value):
    try:
        return Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0")

def is_admin_user(user):
    """
    判断当前用户是否为系统管理员或staff。
    供 @user_passes_test 装饰器使用。
    """
    try:
        return user.is_authenticated and (user.is_superuser or user.is_staff)
    except Exception:
        return False


def auto_assign_plan_for_date(work_date: date):
    """
    占位函数：返回空的自动配车计划。
    将来可替换为真实算法。
    """
    preview_rows = []
    assign_ops = []
    counts = {"first": 0, "second": 0, "any": 0}

    return {
        "preview_rows": preview_rows,
        "assign_ops": assign_ops,
        "counts": counts,
    }