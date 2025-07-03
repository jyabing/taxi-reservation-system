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

    # 🇯🇵 --- 日本法规扩展字段 ---
    registration_number = models.CharField("登録番号", max_length=20, blank=True)
    first_registration_date = models.DateField("初度登録年月", null=True, blank=True)
    engine_displacement = models.DecimalField("排气量（L）", max_digits=4, decimal_places=2, null=True, blank=True)
    model_code = models.CharField("型式", max_length=30, blank=True)
    vehicle_weight = models.DecimalField("车辆重量（kg）", max_digits=6, decimal_places=1, null=True, blank=True)

    # ✅ 新增字段：車両寸法
    length = models.IntegerField(null=True, blank=True, verbose_name="長さ（mm）")
    width = models.IntegerField(null=True, blank=True, verbose_name="幅（mm）")
    height = models.IntegerField(null=True, blank=True, verbose_name="高さ（mm）")

    # --- 使用与状态 ---
    status = models.CharField("车辆状态", max_length=20, choices=STATUS_CHOICES, default='available')
    is_active = models.BooleanField("是否启用", default=True)
    mileage = models.PositiveIntegerField("当前里程（km）", null=True, blank=True)
    fuel_type = models.CharField("燃料类型", max_length=20, blank=True)  # 例：汽油、电动、混动
    color = models.CharField("车身颜色", max_length=30, blank=True)

    # --- 🟡 车辆台账信息（日本式） ---
    registration_number = models.CharField("登録番号", max_length=50, blank=True)
    first_registration = models.DateField("初度登録年月", null=True, blank=True)
    usage = models.CharField("用途", max_length=50, blank=True)  # 自家用 / 业务用
    body_shape = models.CharField("车体形状", max_length=50, blank=True)

    car_type_code = models.CharField("型式", max_length=50, blank=True)
    engine_model = models.CharField("原动机型号", max_length=50, blank=True)
    engine_displacement = models.DecimalField("总排气量（L）", max_digits=4, decimal_places=2, null=True, blank=True)

    length = models.PositiveIntegerField("长度（mm）", null=True, blank=True)
    width = models.PositiveIntegerField("宽度（mm）", null=True, blank=True)
    height = models.PositiveIntegerField("高度（mm）", null=True, blank=True)
    vehicle_weight = models.PositiveIntegerField("车重（kg）", null=True, blank=True)
    gross_weight = models.PositiveIntegerField("总重（kg）", null=True, blank=True)

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