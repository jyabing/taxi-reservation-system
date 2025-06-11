from django.db import models

class Car(models.Model):
    STATUS_CHOICES = [
        ('available', '可用'),
        ('repair', '维修中'),
        ('retired', '已报废'),
    ]

    name = models.CharField("车辆名称", max_length=100)
    status = models.CharField("车辆状态", max_length=20, choices=STATUS_CHOICES, default='available')
    license_plate = models.CharField("车牌号", max_length=20, unique=True)
    brand = models.CharField("品牌", max_length=50, blank=True)
    model = models.CharField("型号", max_length=50, blank=True)
    year = models.PositiveIntegerField("出厂年份", null=True, blank=True)
    is_active = models.BooleanField("是否启用", default=True)
    notes = models.TextField("备注", blank=True)

    def __str__(self):
        return self.license_plate