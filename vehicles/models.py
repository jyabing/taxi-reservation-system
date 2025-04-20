from django.db import models
from django.conf import settings

class Vehicle(models.Model):
    STATUS_CHOICES = [
        ('available', '可预约'),
        ('reserved', '已预约'),
        ('out', '已出库'),
        ('maintenance', '维修中'),
    ]

    license_plate = models.CharField(max_length=20, unique=True, verbose_name="车牌号")
    model = models.CharField(max_length=50, verbose_name="车型")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available', verbose_name="状态")

    # ✅ 新增字段
    photo = models.ImageField(upload_to='vehicle_photos/', blank=True, null=True, verbose_name="车辆照片")
    inspection_date = models.DateField(blank=True, null=True, verbose_name="车检日期")
    notes = models.TextField(blank=True, verbose_name="备注")

    def __str__(self):
        return f"{self.license_plate}({self.model})"
    class Meta:
        verbose_name = "车辆"
        verbose_name_plural = "车辆"


class Reservation(models.Model):
    driver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="司机")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, verbose_name="车辆")
    date = models.DateField(verbose_name="预约日期")             # ✅ 开始日期
    end_date = models.DateField(verbose_name="结束日期")         # ✅ 结束日期（支持跨日）
    start_time = models.TimeField(verbose_name="开始时间")
    end_time = models.TimeField(verbose_name="结束时间")
    status = models.CharField(
        max_length=10,
        choices=[
            ('pending', '申请中'),
            ('reserved', '已预约'),
            ('out', '已出库'),
            ('canceled', '已取消'),
        ],
        default='pending',
        verbose_name="状态"
    )
    actual_departure = models.DateTimeField(null=True, blank=True, verbose_name="实际出库时间")
    actual_return = models.DateTimeField(null=True, blank=True, verbose_name="实际还车时间")

    def __str__(self):
        return f"{self.vehicle} {self.date} ~ {self.end_date} {self.start_time}-{self.end_time}"

class CarouselImage(models.Model):
    title = models.CharField(max_length=100, verbose_name="标题", blank=True)
    description = models.TextField(verbose_name="说明", blank=True)
    image = models.ImageField(upload_to='carousel/', verbose_name="轮播图片")
    order = models.PositiveIntegerField(default=0, verbose_name="排序顺序")
    is_active = models.BooleanField(default=True, verbose_name="是否启用")

    def __str__(self):
        return self.title or f"图片 {self.id}"

    class Meta:
        verbose_name = "轮播图"
        verbose_name_plural = "轮播图管理"
        ordering = ['order']