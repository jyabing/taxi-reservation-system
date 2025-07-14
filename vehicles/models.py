from django.db import models
from django.utils.html import format_html
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from carinfo.models import Car
from datetime import datetime

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


class Reservation(models.Model):
    driver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="司机")
    
    vehicle = models.ForeignKey(Car, on_delete=models.CASCADE, verbose_name="车辆")

    date = models.DateField(verbose_name="预约日期")
    end_date = models.DateField(verbose_name="结束日期")
    start_time = models.TimeField(verbose_name="开始时间")
    end_time = models.TimeField(verbose_name="结束时间")
    purpose = models.CharField(max_length=200, blank=True, verbose_name="用途说明")
    status = models.CharField(
        max_length=10,
        choices=[
            ('pending', '申请中'),
            ('reserved', '已预约'),
            ('out', '已出库'),
            ('canceled', '已取消'),
            ('completed', '已完成'),
        ],
        default='pending',
        verbose_name="状态"
    )
    actual_departure = models.DateTimeField(null=True, blank=True, verbose_name="实际出库时间")
    actual_return = models.DateTimeField(null=True, blank=True, verbose_name="实际入库时间")

    # ✅ 新增字段
    start_datetime = models.DateTimeField(null=True, blank=True, verbose_name="开始时间（完整）")
    end_datetime = models.DateTimeField(null=True, blank=True, verbose_name="结束时间（完整）")

    def save(self, *args, **kwargs):
        # 自动拼接完整开始/结束时间
        self.start_datetime = timezone.make_aware(datetime.combine(self.date, self.start_time))
        self.end_datetime = timezone.make_aware(datetime.combine(self.end_date, self.end_time))
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