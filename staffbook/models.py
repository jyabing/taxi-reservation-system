from django.db import models
from accounts.models import DriverUser
from django.conf import settings
from django.utils import timezone

PAYMENT_METHOD_CHOICES = [
    ('cash', '现金'),
    ('uber', 'Uber'),
    ('didi', 'Didi'),
    ('credit', '信用卡'),
    ('ticket', '乘车券'),
    ('barcode', '扫码(PayPay/AuPay/支付宝/微信Pay等)'),
]

# 司机基本信息 + 台账扩展字段
class Driver(models.Model):
    # user 字段一定指向 AUTH_USER_MODEL
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,    # 通常是 accounts.DriverUser
        on_delete=models.CASCADE,
        related_name='driver_profile',
        null=True, blank=True,       # 允许先不绑定
        verbose_name='绑定用户'
    )
    # 新建司机
    driver_code = models.CharField('従業員番号', max_length=20, unique=True)
    name = models.CharField('氏名', max_length=32)
    kana = models.CharField('フリガナ', max_length=32)
    company = models.CharField('事業者名', max_length=64)
    workplace = models.CharField('営業所名', max_length=64)
    department = models.CharField('部門', max_length=32, blank=True)
    position = models.CharField('職種', max_length=32, choices=[
        ('1', '常時選任運転者'),
        ('2', '運転者'),
        ('3', '職員'),
        ('4', '整備士')
    ])
    employ_type = models.CharField("在职类型", max_length=20, choices=[  # 常时、兼职等
        ('1', '正式運転者'),
        ('2', '非常勤運転者')
    ])
    appointment_date = models.DateField(blank=True, null=True, verbose_name="選任年月日")
    hire_date = models.DateField(blank=True, null=True, verbose_name="入社年月日")
    create_date = models.DateField(blank=True, null=True, verbose_name="作成年月日")
    birth_date = models.DateField(blank=True, null=True, verbose_name="生年月日")
    gender = models.CharField(max_length=8, choices=[
        ('男性', '男性'), ('女性', '女性'), ('未設定', '未設定')], default='未設定', verbose_name="性別")
    blood_type = models.CharField(max_length=4, choices=[
        ('A', 'A'), ('B', 'B'), ('AB', 'AB'), ('O', 'O')], verbose_name="血液型", blank=True, null=True)
    postal_code = models.CharField(max_length=16, blank=True, null=True, verbose_name="郵便番号")
    address = models.CharField(max_length=128, blank=True, null=True, verbose_name="住所")
    phone_number = models.CharField(max_length=32, blank=True, null=True, verbose_name="電話番号")
    photo = models.ImageField(upload_to='driver_photos/', blank=True, null=True, verbose_name="写真")
    photo_date = models.DateField(blank=True, null=True, verbose_name="撮影年月日")
    # 保险相关
    health_insurance_no = models.CharField(max_length=32, blank=True, null=True, verbose_name="健康保険番号")
    health_insurance_join_date = models.DateField(blank=True, null=True, verbose_name="健康保険加入日")
    pension_no = models.CharField(max_length=32, blank=True, null=True, verbose_name="厚生年金保険番号")
    pension_join_date = models.DateField(blank=True, null=True, verbose_name="厚生年金保険加入日")
    employment_insurance_no = models.CharField(max_length=32, blank=True, null=True, verbose_name="雇用保険番号")
    employment_insurance_join_date = models.DateField(blank=True, null=True, verbose_name="雇用保険加入日")
    workers_insurance_no = models.CharField(max_length=32, blank=True, null=True, verbose_name="労災保険番号")
    workers_insurance_join_date = models.DateField(blank=True, null=True, verbose_name="労災保険加入日")
    pension_fund_no = models.CharField(max_length=32, blank=True, null=True, verbose_name="厚生年金基金番号")
    pension_fund_join_date = models.DateField(blank=True, null=True, verbose_name="厚生年金基金加入日")
    # 其它
    remark = models.CharField(max_length=256, blank=True, null=True, verbose_name="特記事項")
    # 可根据需要继续添加其他字段（如身份证号、入职日期、状态等）

    class Meta:
        verbose_name = "司机资料"
        verbose_name_plural = "司机资料"
    
    def __str__(self):
        return f"{self.driver_code} - {self.name}"

# 驾驶经验（可多条）
class DrivingExperience(models.Model):
    driver = models.ForeignKey(Driver, related_name="driving_exp", on_delete=models.CASCADE)
    vehicle_type = models.CharField("车种", max_length=30, blank=True)
    years = models.IntegerField("经验年数", blank=True, null=True)
    company = models.CharField("经验公司", max_length=50, blank=True)

# 保险信息（可多条）
class Insurance(models.Model):
    driver = models.ForeignKey(Driver, related_name="insurances", on_delete=models.CASCADE)
    kind = models.CharField("保险种类", max_length=20)  # 健康/厚生年金/雇用/劳灾
    join_date = models.DateField("加入年月日", blank=True, null=True)
    number = models.CharField("保险号", max_length=40, blank=True)

# 家庭成员（可多条）
class FamilyMember(models.Model):
    driver = models.ForeignKey(Driver, related_name="family_members", on_delete=models.CASCADE)
    name = models.CharField("家族姓名", max_length=20)
    relation = models.CharField("关系", max_length=10)
    birthday = models.DateField("出生年月", blank=True, null=True)

    def __str__(self):
        return f"{self.driver.name} - {self.name}({self.relation})"

# 日销售（不变）
class DriverDailySales(models.Model):
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name='daily_sales')
    date = models.DateField('日期')
    cash_amount = models.DecimalField('现金', max_digits=8, decimal_places=2, default=0)
    card_amount = models.DecimalField('刷卡', max_digits=8, decimal_places=2, default=0)
    ride_count = models.IntegerField('乘车次数', default=0)
    mileage = models.DecimalField('里程', max_digits=6, decimal_places=1, default=0)

    class Meta:
        unique_together = ('driver', 'date')
        ordering = ['-date']
        verbose_name = "司机日销售"
        verbose_name_plural = "司机日销售"

    def __str__(self):
        return f"{self.driver} - {self.date}"

class LicenseType(models.Model):
    """驾驶证种类，如：大型、中型、准中型、普通等"""
    name = models.CharField('种类', max_length=30, unique=True)
    label = models.CharField('显示名', max_length=32, blank=True)

    def __str__(self):
        return self.label or self.name

class DriverLicense(models.Model):
    driver = models.OneToOneField('Driver', on_delete=models.CASCADE, related_name='license')
    photo = models.ImageField("免许写真", upload_to='license_photos/', null=True, blank=True)
    license_number = models.CharField("免許証番号", max_length=32, blank=True)
    issue_date = models.DateField("交付年月日", null=True, blank=True)
    expiry_date = models.DateField("有効期限", null=True, blank=True)
    date_acquired_a = models.DateField("二・小・原取得年月日", null=True, blank=True)
    date_acquired_b = models.DateField("其他取得年月日", null=True, blank=True)
    date_acquired_c = models.DateField("二種取得年月日", null=True, blank=True)
    license_types = models.ManyToManyField(LicenseType, verbose_name="種　類", blank=True)
    license_conditions = models.CharField("条件", max_length=128, blank=True)
    note = models.TextField("備考", blank=True)

    def __str__(self):
        return f"{self.driver.name}的免許证"

class Accident(models.Model):
    driver = models.ForeignKey('Driver', on_delete=models.CASCADE, related_name='accidents', verbose_name="司机")
    happened_at = models.DateField("发生日期")
    description = models.CharField("简要说明", max_length=100)
    penalty = models.CharField("处理/处分", max_length=100, blank=True)
    note = models.CharField("备注", max_length=200, blank=True)

    class Meta:
        verbose_name = "事故・違反"
        verbose_name_plural = "事故・違反"

    def __str__(self):
        return f"{self.driver.name} - {self.happened_at} - {self.description}"



# 核心：乘务日报（一天一条），不再保存单独的金额等，而是所有明细归属于这张日报
class DriverDailyReport(models.Model):
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name='daily_reports', verbose_name="司机")
    date = models.DateField('日期')
    note = models.TextField('备注', blank=True)

    has_issue = models.BooleanField("包含异常记录", default=False)  # ✅ 新增

    # ✅ 新增两个字段
    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='edited_dailyreports',
        verbose_name="编辑人"
    )
    edited_at = models.DateTimeField("编辑时间", null=True, blank=True)

    @property
    def total_meter_fee(self):
        """返回该日报下所有明细的メータ料金合计"""
        # items 为 related_name，指向所有明细表
        return sum(item.meter_fee or 0 for item in self.items.all())

    class Meta:
        ordering = ['-date']
        verbose_name = '乘务日报'
        verbose_name_plural = '乘务日报'
        unique_together = ('driver', 'date')

    def __str__(self):
        return f"{self.driver} {self.date}"

# ★ 新增！乘务日报明细，一天可有多条，归属于DriverDailyReport
class DriverDailyReportItem(models.Model):
    report = models.ForeignKey(
        DriverDailyReport, on_delete=models.CASCADE, related_name='items', verbose_name="所属日报"
    )
    ride_time = models.CharField("乘车时间", max_length=30, blank=True)
    ride_from = models.CharField("乘车地", max_length=100, blank=True)
    via = models.CharField("経由", max_length=100, blank=True)
    ride_to = models.CharField("降车地", max_length=100, blank=True)
    num_male = models.IntegerField("男", default=0)
    num_female = models.IntegerField("女", default=0)
    meter_fee = models.DecimalField("メータ料金", max_digits=7, decimal_places=2, blank=True, null=True)
    payment_method = models.CharField("支付方式", max_length=16, choices=PAYMENT_METHOD_CHOICES, blank=True)
    note = models.CharField("备注", max_length=255, blank=True)
    comment = models.TextField("录入员注释", blank=True)  # 新增字段
    has_issue = models.BooleanField("是否异常", default=False)  # 新增字段

    def save(self, *args, **kwargs):
    # 如果 comment 不为空就设为有异常
        self.has_issue = bool(self.comment.strip())
        super().save(*args, **kwargs)

    # 更新日报本体状态（是否包含异常记录）
        if self.report:
            self.report.has_issue = self.report.items.filter(has_issue=True).exists()
            self.report.save(update_fields=['has_issue'])

    def __str__(self):
        return f"{self.ride_time} - {self.ride_from}→{self.ride_to} - {self.meter_fee}"

# 工资记录（不变）
class DriverPayrollRecord(models.Model):
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name='payroll_records')
    month = models.DateField('月份')  # 通常用每月1号代表该月
    total_sales = models.DecimalField('总业绩', max_digits=10, decimal_places=2)
    salary_paid = models.DecimalField('实发工资', max_digits=10, decimal_places=2)
    note = models.TextField('备注', blank=True)

    class Meta:
        unique_together = ('driver', 'month')
        ordering = ['-month']
        verbose_name = "工资记录"
        verbose_name_plural = "工资记录"

    def __str__(self):
        return f"{self.driver} - {self.month.strftime('%Y-%m')} 工资"

# 日报图片（不变）
class DriverReportImage(models.Model):
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name='report_images')
    date = models.DateField('日期')
    image = models.ImageField('日报图片', upload_to='report_images/')
    uploaded_at = models.DateTimeField('上传时间', auto_now_add=True)

    class Meta:
        unique_together = ('driver', 'date')
        ordering = ['-date']
        verbose_name = "日报图片"
        verbose_name_plural = "日报图片"

    def __str__(self):
        return f"{self.driver} - {self.date} 的图片"
