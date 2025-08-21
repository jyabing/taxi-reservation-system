from datetime import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from carinfo.models import Car


class VehicleImage(models.Model):
    vehicle = models.ForeignKey(
        Car,
        on_delete=models.CASCADE,
        related_name='images',
        verbose_name=_("车辆")
    )
    image = models.ImageField(
        upload_to='vehicles/%Y/%m/%d/',
        verbose_name=_("图片文件")
    )

    def __str__(self):
        return f"{self.vehicle} - {self.image.url if self.image else '无图片'}"

    def preview(self):
        if self.image:
            return format_html('<img src="{}" style="height:50px;" />', self.image.url)
        return "-"
    preview.short_description = "预览图"
    preview.allow_tags = True


# ✅ 系统通知模型
class SystemNotice(models.Model):
    message = models.CharField("通知内容", max_length=255)
    is_active = models.BooleanField("是否启用", default=True)
    created_at = models.DateTimeField("创建时间", default=timezone.now)

    def __str__(self):
        return self.message

    class Meta:
        verbose_name = "系统通知"
        verbose_name_plural = "系统通知"


# ========= 兼容适配层（BEGIN） =========
def _rewrite_key(k: str) -> str:
    """
    支持：
    - 'car' / 'car__x' / 'car_id'
    - 带排序前缀的 '-car' / '-car__x' / '-car_id'
    其他保持不变
    """
    if not isinstance(k, str):
        return k

    # 处理 order_by 的前缀 '-'
    neg = ''
    if k.startswith('-'):
        neg, k = '-', k[1:]

    if k == 'car':
        k = 'vehicle'
    elif k.startswith('car__'):
        k = 'vehicle' + k[3:]  # 'car__' -> 'vehicle__'
    elif k == 'car_id':
        k = 'vehicle_id'

    return neg + k


def _rewrite_kwargs(kwargs: dict) -> dict:
    return {_rewrite_key(k): v for k, v in kwargs.items()}


def _rewrite_q(obj: Q) -> Q:
    """递归改写 Q(children=[('car__x', 1), Q(...), ...])"""
    new_children = []
    for child in obj.children:
        if isinstance(child, Q):
            new_children.append(_rewrite_q(child))
        elif isinstance(child, tuple) and len(child) == 2:
            k, v = child
            new_children.append((_rewrite_key(k), v))
        else:
            new_children.append(child)
    q = Q()
    q.connector = obj.connector
    q.negated = obj.negated
    q.children = new_children
    return q


def _rewrite_args(args):
    out = []
    for a in args:
        if isinstance(a, Q):
            out.append(_rewrite_q(a))
        else:
            out.append(a)
    return tuple(out)


def _rewrite_fieldnames(*names):
    # 用于 select_related / prefetch_related / order_by / values / only / defer
    return tuple(_rewrite_key(n) for n in names)


class CompatQuerySet(models.QuerySet):
    # 过滤类
    def filter(self, *args, **kwargs):
        return super().filter(*_rewrite_args(args), **_rewrite_kwargs(kwargs))

    def exclude(self, *args, **kwargs):
        return super().exclude(*_rewrite_args(args), **_rewrite_kwargs(kwargs))

    def get(self, *args, **kwargs):
        return super().get(*_rewrite_args(args), **_rewrite_kwargs(kwargs))

    # 写入类
    def update(self, **kwargs):
        return super().update(**_rewrite_kwargs(kwargs))

    def update_or_create(self, defaults=None, **kwargs):
        defaults = _rewrite_kwargs(defaults or {})
        kwargs = _rewrite_kwargs(kwargs)
        return super().update_or_create(defaults=defaults, **kwargs)

    def get_or_create(self, defaults=None, **kwargs):
        defaults = _rewrite_kwargs(defaults or {})
        kwargs = _rewrite_kwargs(kwargs)
        return super().get_or_create(defaults=defaults, **kwargs)

    # 名称参数类
    def order_by(self, *field_names):
        return super().order_by(*_rewrite_fieldnames(*field_names))

    def values(self, *field_names, **expressions):
        field_names = _rewrite_fieldnames(*field_names)
        expressions = {_rewrite_key(k): v for k, v in expressions.items()}
        return super().values(*field_names, **expressions)

    def values_list(self, *field_names, **kwargs):
        return super().values_list(*_rewrite_fieldnames(*field_names), **kwargs)

    def only(self, *fields):
        return super().only(*_rewrite_fieldnames(*fields))

    def defer(self, *fields):
        return super().defer(*_rewrite_fieldnames(*fields))

    def select_related(self, *fields):
        return super().select_related(*_rewrite_fieldnames(*fields))

    def prefetch_related(self, *lookups):
        return super().prefetch_related(*_rewrite_fieldnames(*lookups))


class ReservationManager(models.Manager.from_queryset(CompatQuerySet)):
    def create(self, **kwargs):
        kwargs = _rewrite_kwargs(kwargs)
        return super().create(**kwargs)
# ========= 兼容适配层（END） =========


class ReservationStatus(models.TextChoices):
    # —— 按你原始定义恢复 —— #
    PENDING    = "pending",    "申请中"
    BOOKED     = "booked",     "已预约"
    OUT        = "out",        "已出库"
    DONE       = "done",       "已完成"
    CANCEL     = "cancel",     "已取消"
    INCOMPLETE = "incomplete", "未完成出入库手续"


class Reservation(models.Model):
    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name="司机"
    )

    vehicle = models.ForeignKey(
        Car,
        on_delete=models.CASCADE,
        verbose_name="车辆"
    )

    date = models.DateField(verbose_name="预约日期")
    end_date = models.DateField(verbose_name="结束日期")
    start_time = models.TimeField(verbose_name="开始时间")
    end_time = models.TimeField(verbose_name="结束时间")

    purpose = models.CharField(max_length=200, blank=True, verbose_name="用途说明")

    status = models.CharField(
        max_length=20,
        choices=ReservationStatus.choices,
        default=ReservationStatus.PENDING,   # 恢复默认 PENDING
        verbose_name="状态",
        db_index=True,
    )

    actual_departure = models.DateTimeField(null=True, blank=True, verbose_name="实际出库时间")
    actual_return = models.DateTimeField(null=True, blank=True, verbose_name="实际入库时间")

    start_datetime = models.DateTimeField(null=True, blank=True, verbose_name="开始时间（完整）")
    end_datetime = models.DateTimeField(null=True, blank=True, verbose_name="结束时间（完整）")

    # 绑定兼容 Manager
    objects = ReservationManager()

    # —— car / car_id 别名属性（兼容历史代码）——
    @property
    def car(self):
        return self.vehicle

    @car.setter
    def car(self, value):
        self.vehicle = value

    @property
    def car_id(self):
        return self.vehicle_id

    @car_id.setter
    def car_id(self, value):
        self.vehicle_id = value

    # —— __init__ 参数兼容 —— #
    def __init__(self, *args, **kwargs):
        if 'car' in kwargs and 'vehicle' not in kwargs:
            kwargs['vehicle'] = kwargs.pop('car')
        if 'car_id' in kwargs and 'vehicle_id' not in kwargs:
            kwargs['vehicle_id'] = kwargs.pop('car_id')
        super().__init__(*args, **kwargs)

    def save(self, *args, **kwargs):
        # 自动拼接完整开始/结束时间（兼容 USE_TZ 开/关）
        dt_start = datetime.combine(self.date, self.start_time)
        dt_end = datetime.combine(self.end_date, self.end_time)

        if getattr(settings, "USE_TZ", False):
            if timezone.is_naive(dt_start):
                dt_start = timezone.make_aware(dt_start)
            if timezone.is_naive(dt_end):
                dt_end = timezone.make_aware(dt_end)

        self.start_datetime = dt_start
        self.end_datetime = dt_end

        super().save(*args, **kwargs)

    # 自动审批相关字段
    approved = models.BooleanField(default=False, verbose_name="是否已审批")
    approval_time = models.DateTimeField(null=True, blank=True, verbose_name="审批时间")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    approved_by_system = models.BooleanField(default=False, verbose_name="是否系统自动审批")

    def __str__(self):
        return f"{self.vehicle} {self.date} ~ {self.end_date} {self.start_time}-{self.end_time}"

    class Meta:
        verbose_name = "预约记录"
        verbose_name_plural = "预约记录"


class Tip(models.Model):
    content = models.TextField("提示内容")
    is_active = models.BooleanField("是否启用", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.content[:30]

    class Meta:
        verbose_name = "提示信息"
        verbose_name_plural = "提示信息"
