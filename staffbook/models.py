from django.db import models
from accounts.models import DriverUser
from django.conf import settings

class Driver(models.Model):
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
    # 可根据需要继续添加其他字段（如身份证号、入职日期、状态等）

    class Meta:
        verbose_name = "司机资料"
        verbose_name_plural = "司机资料"
    
    def __str__(self):
        return f"{self.staff_code} - {self.name}"

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

class DriverDailyReport(models.Model):
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name='daily_reports', verbose_name="司机")
    date = models.DateField('日期')
    time = models.CharField('乘车时间', max_length=20, blank=True, null=True)
    fare = models.DecimalField('运费金额', max_digits=8, decimal_places=2, blank=True, null=True)
    payment_method = models.CharField('支付方式', max_length=50, blank=True, null=True)
    note = models.TextField('备注', blank=True)

    class Meta:
        ordering = ['-date']
        verbose_name = '乘务日报'
        verbose_name_plural = '乘务日报'
        unique_together = ('driver', 'date')

    def __str__(self):
        return f"{self.driver} {self.date} {self.fare or ''}"

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