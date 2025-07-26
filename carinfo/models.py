from django.db import models
from datetime import date
from django.core.exceptions import ValidationError
from django.utils.timezone import localdate

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

    # --- 登记信息 ---
    registration_number = models.CharField("登録番号", max_length=50, blank=True)
    first_registration_date = models.DateField("初度登録年月", null=True, blank=True)
    model_code = models.CharField("型式", max_length=50, blank=True)
    engine_model = models.CharField("原动机型号", max_length=50, blank=True)
    engine_displacement = models.DecimalField("总排气量（L）", max_digits=4, decimal_places=2, null=True, blank=True)
    chassis_number = models.CharField("车台番号", max_length=50, blank=True)
    length = models.PositiveIntegerField("长度（mm）", null=True, blank=True)
    width = models.PositiveIntegerField("宽度（mm）", null=True, blank=True)
    height = models.PositiveIntegerField("高度（mm）", null=True, blank=True)
    vehicle_weight = models.PositiveIntegerField("车重（kg）", null=True, blank=True)
    gross_weight = models.PositiveIntegerField("总重（kg）", null=True, blank=True)
    max_load_weight = models.PositiveIntegerField("最大積載量（kg）", null=True, blank=True)
    capacity = models.PositiveSmallIntegerField("乗車定員（人）", null=True, blank=True)
    usage = models.CharField("用途", max_length=50, blank=True)
    body_shape = models.CharField("车体形状", max_length=50, blank=True)
    user_company_name = models.CharField("使用者名称", max_length=100, blank=True)
    owner_company_name = models.CharField("所有者名称", max_length=100, blank=True)

    # --- 状态 ---
    status = models.CharField("车辆状态", max_length=20, choices=STATUS_CHOICES, default='available')
    is_active = models.BooleanField("是否启用", default=True)
    is_reserved_only_by_admin = models.BooleanField("是否为调配用车（禁止普通用户预约）", default=False)  # ✅ 新增
    mileage = models.PositiveIntegerField("当前里程（km）", null=True, blank=True)
    fuel_type = models.CharField("燃料类型", max_length=20, blank=True)
    color = models.CharField("车身颜色", max_length=30, blank=True)

    # --- 证件与保险 ---
    inspection_date = models.DateField("车检到期日", null=True, blank=True)
    insurance_certificate_number = models.CharField("保険証明書番号", max_length=50, blank=True)
    insurance_company = models.CharField("保険会社", max_length=100, blank=True)
    insurance_start_date = models.DateField("保険开始日", null=True, blank=True)
    insurance_end_date = models.DateField("保険结束日", null=True, blank=True)
    insurance_status = models.CharField("保険加入状況", max_length=20, choices=[
        ('valid', '加入中'), ('expired', '已过期'), ('none', '未加入')
    ], default='valid', blank=True)

    # --- 设备与责任人 ---
    etc_device = models.CharField("ETC设备编号", max_length=50, blank=True)
    fuel_card_number = models.CharField("油卡号", max_length=50, blank=True)
    pos_terminal_id = models.CharField("刷卡机编号", max_length=50, blank=True)
    gps_device_id = models.CharField("GPS设备编号", max_length=50, blank=True)
    department = models.CharField("所属部门", max_length=50, blank=True, default="未指定")
    manager_name = models.CharField("负责人姓名", max_length=50, blank=True)
    manager_phone = models.CharField("负责人电话", max_length=30, blank=True)

    # --- 备注与照片 ---
    notes = models.TextField("备注", blank=True)
    image = models.ImageField("车辆照片", upload_to="cars/", blank=True, null=True)

    def __str__(self):
        return self.license_plate

    # ✅ 新增结构化提醒方法
    def get_reminders(self, today=None):
        from datetime import timedelta
        from django.utils.timezone import localdate

        if today is None:
            today = localdate()

        reminders = []

        if self.inspection_date and self.inspection_date <= today + timedelta(days=30):
            reminders.append({
                'type': 'inspection',
                'date': self.inspection_date,
                'text': f"車検期限 {self.inspection_date.strftime('%-m月%-d日')}"
            })

        if self.insurance_end_date and self.insurance_end_date <= today + timedelta(days=30):
            reminders.append({
                'type': 'insurance',
                'date': self.insurance_end_date,
                'text': f"保険期限 {self.insurance_end_date.strftime('%-m月%-d日')}"
            })

        return reminders


    def is_insurance_expired(self):
        if self.insurance_end_date:
            return self.insurance_end_date < localdate()
        return False

    def is_inspection_expired(self):
        if self.inspection_date:
            return self.inspection_date < localdate()
        return False

    def update_insurance_status(self):
        today = localdate()
        if self.insurance_end_date:
            if self.insurance_end_date < today:
                self.insurance_status = 'expired'
            else:
                self.insurance_status = 'valid'
        else:
            self.insurance_status = 'none'

    def clean(self):
        if self.status == 'available' and self.is_insurance_expired():
            raise ValidationError("车辆为可用状态，但保险已过期。")
        if self.status == 'available' and self.is_inspection_expired():
            raise ValidationError("车辆为可用状态，但车检已过期。")

def get_inspection_reminder(self):
        """
        根据 inspection_date 返回车检提醒文案（5天内提示、过期天数、当天提醒）
        """
        if not self.inspection_date:
            print(f"[REMINDER] {self.license_plate}: 没有设置 inspection_date")
            return None

        today = today = localdate()
        delta = (self.inspection_date - today).days

        # ✅ 调试输出
        print(f"[REMINDER] {self.license_plate}: inspection_date={self.inspection_date}, today={today}, delta={delta}")

        if 0 < delta <= 5:
            return f"🚨 还有 {delta} 天请协助事务所对本车进行车检"
        elif delta == 0:
            return "✅ 不要忘记本日车检"
        elif -5 <= delta < 0:
            return f"⚠️ 车检日已推迟 {abs(delta)} 天"
        else:
            return None