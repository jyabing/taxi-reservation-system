from django.db import models

class Car(models.Model):
    STATUS_CHOICES = [
        ('available', '可用'),
        ('repair', '维修中'),
        ('retired', '已报废'),
    ]

    # --- 基本信息 ---
    name = models.CharField("车辆名称", max_length=100)
    license_plate = models.CharField("车牌号", max_length=20, unique=True)
    brand = models.CharField("品牌", max_length=50, blank=True)
    model = models.CharField("型号", max_length=50, blank=True)
    year = models.PositiveIntegerField("出厂年份", null=True, blank=True)

    # --- 使用与状态 ---
    status = models.CharField("车辆状态", max_length=20, choices=STATUS_CHOICES, default='available')
    is_active = models.BooleanField("是否启用", default=True)
    mileage = models.PositiveIntegerField("当前里程（km）", null=True, blank=True)
    fuel_type = models.CharField("燃料类型", max_length=20, blank=True)  # 例：汽油、电动、混动
    color = models.CharField("车身颜色", max_length=30, blank=True)

    # --- 证件与设备 ---
    inspection_date = models.DateField("车检到期日", null=True, blank=True)
    insurance_expiry = models.DateField("保险到期日", null=True, blank=True)
    etc_device = models.CharField("ETC设备编号", max_length=50, blank=True)
    fuel_card_number = models.CharField("油卡号", max_length=50, blank=True)
    pos_terminal_id = models.CharField("刷卡机编号", max_length=50, blank=True)
    gps_device_id = models.CharField("GPS设备编号", max_length=50, blank=True)

    # --- 使用单位与责任人 ---
    department = models.CharField("所属部门", max_length=50, blank=True)
    manager_name = models.CharField("负责人姓名", max_length=50, blank=True)
    manager_phone = models.CharField("负责人电话", max_length=30, blank=True)

    # --- 备注与照片 ---
    notes = models.TextField("备注", blank=True)
    image = models.ImageField("车辆照片", upload_to="cars/", blank=True, null=True)

    def __str__(self):
        return self.license_plate