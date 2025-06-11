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
    staff_code = models.CharField('员工コード', max_length=20, unique=True)
    name = models.CharField('姓名', max_length=30)
    phone = models.CharField('手机号', max_length=20, blank=True, null=True)
    tax_id = models.CharField('税号', max_length=30, blank=True, null=True)
    # —— 台账扩展字段 ——
    gender = models.CharField("性别", max_length=5, choices=[('男', '男'), ('女', '女')], blank=True)
    birthday = models.DateField("出生年月日", blank=True, null=True)
    address = models.CharField("住址", max_length=128, blank=True)
    hire_date = models.DateField("聘用日期", blank=True, null=True)
    employ_type = models.CharField("在职类型", max_length=20, blank=True)  # 常时、兼职等
    company = models.CharField("公司名", max_length=40, blank=True)
    workplace = models.CharField("所属营业所", max_length=40, blank=True)
    education = models.CharField("最终学历", max_length=40, blank=True)
    previous_employer = models.CharField("前任勤务先", max_length=40, blank=True)
    qualification = models.CharField("资格证", max_length=40, blank=True)
    qualification_date = models.DateField("资格取得年月", blank=True, null=True)
    health_insurance = models.CharField("健康保险", max_length=40, blank=True)
    health_check = models.CharField("健康诊断结果", max_length=100, blank=True)
    health_check_date = models.DateField("健康诊断日期", blank=True, null=True)
    family_info = models.TextField("家族状况", blank=True)
    note = models.TextField("备注", blank=True)
    photo = models.ImageField("照片", upload_to="staff_photos/", blank=True, null=True)  # 如需支持照片上传
    # 可根据需要继续添加其他字段（如身份证号、入职日期、状态等）

    class Meta:
        verbose_name = "司机资料"
        verbose_name_plural = "司机资料"
    
    def __str__(self):
        return f"{self.staff_code} - {self.name}"

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

# 核心：乘务日报（一天一条），不再保存单独的金额等，而是所有明细归属于这张日报
class DriverDailyReport(models.Model):
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name='daily_reports', verbose_name="司机")
    date = models.DateField('日期')
    note = models.TextField('备注', blank=True)

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
