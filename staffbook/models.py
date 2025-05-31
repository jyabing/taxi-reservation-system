from django.db import models
from accounts.models import DriverUser
from django.conf import settings

class DailySales(models.Model):
    driver = models.ForeignKey(DriverUser, on_delete=models.CASCADE)
    date = models.DateField()
    cash_amount = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    card_amount = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    ride_count = models.IntegerField(default=0)
    mileage = models.DecimalField(max_digits=6, decimal_places=1, default=0)

    class Meta:
        unique_together = ('driver', 'date')
        ordering = ['-date']

    def __str__(self):
        return f"{self.driver.username} - {self.date}"


class DailyReport(models.Model):
    driver = models.ForeignKey(DriverUser, on_delete=models.CASCADE)
    date = models.DateField()
    memo = models.TextField(blank=True)
    is_working_day = models.BooleanField(default=True)
    accident_occurred = models.BooleanField(default=False)

    class Meta:
        unique_together = ('driver', 'date')

    def __str__(self):
        return f"{self.driver.username} - {self.date} 日报"


class PayrollRecord(models.Model):
    driver = models.ForeignKey(DriverUser, on_delete=models.CASCADE)
    month = models.DateField()  # 使用每月第一天表示一个月
    total_sales = models.DecimalField(max_digits=10, decimal_places=2)
    salary_paid = models.DecimalField(max_digits=10, decimal_places=2)
    note = models.TextField(blank=True)

    class Meta:
        unique_together = ('driver', 'month')

    def __str__(self):
        return f"{self.driver.username} - {self.month.strftime('%Y-%m')} 工资"

class ReportImage(models.Model):
    driver = models.ForeignKey(DriverUser, on_delete=models.CASCADE)
    date = models.DateField()
    image = models.ImageField(upload_to='report_images/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('driver', 'date')

    def __str__(self):
        return f"{self.driver.username} - {self.date} 的图片"

class DriverDailyReport(models.Model):
    driver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='staffbook_daily_reports', verbose_name="司机")
    date = models.DateField(verbose_name="日期")
    time = models.CharField(max_length=20, verbose_name="乘车时间")
    fare = models.DecimalField(max_digits=8, decimal_places=2, verbose_name="运费金额")
    payment_method = models.CharField(max_length=50, verbose_name="支付方式")
    note = models.TextField(blank=True, verbose_name="备注")

    class Meta:
        ordering = ['-date']
        verbose_name = '乘务日报'
        verbose_name_plural = '乘务日报'

    def __str__(self):
        return f"{self.driver} {self.date} {self.fare}"