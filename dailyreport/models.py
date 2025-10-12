from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator

from dailyreport.constants import CHARTER_PAYMENT_CHOICES

from datetime import timedelta, datetime

from carinfo.models import Car
from staffbook.models import Driver

User = get_user_model()

# 支付方式选择项
PAYMENT_METHOD_CHOICES = [
    ('cash', '現金'),

    # ✅ 平台支付方式
    ('uber_cash', 'Uber（現金）'),
    ('uber', 'Uber'),

    # >>> 新增（只计入売上合計，不计入メーターのみ）
    ('uber_reservation', 'Uber予約'),
    ('uber_tip', 'Uberチップ'),
    ('uber_promotion', 'Uberプロモーション'),
    # <<< 新增结束

    ('didi_cash', 'Didi（現金）'),
    ('didi', 'Didi'),

    ('go_cash', 'GO（現金）'),
    ('go', 'GO'),

    # ✅ 其他
    ('credit_card', 'クレジットカード'),
    ('qr', 'バーコード(PayPay、auPay、wechat)'),
    ('kyokushin', '京交信'),
    ('omron', 'オムロン（愛のタクシーチケット）'),
    ('kyotoshi', '京都市他'),
]


# 核心：乘务日报（一天一条），不再保存单独的金额等，而是所有明细归属于这张日报
class DriverDailyReport(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELLED = 'cancelled'
    
    STATUS_CHOICES = [
        (STATUS_PENDING,   '待处理'),
        (STATUS_COMPLETED, '已完成'),
        (STATUS_CANCELLED, '已取消'),
    ]
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name='daily_reports', verbose_name="司机")
    vehicle = models.ForeignKey(Car, on_delete=models.SET_NULL, null=True, blank=True, related_name='daily_reports', verbose_name='本日使用车辆')
    date = models.DateField('日期')
    note = models.TextField('备注', blank=True)

    has_issue = models.BooleanField("包含异常记录", default=False)  # ✅ 新增

    status = models.CharField(
        "状态",
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )

    # —— 新增：出勤／退勤 时间字段 —— 
    clock_in  = models.TimeField("出勤时间",  null=True, blank=True)
    clock_out = models.TimeField("退勤时间",  null=True, blank=True)

    # —— 时间统计字段（自动计算） ——
    勤務時間 = models.DurationField("勤務時間", null=True, blank=True)
    休憩時間 = models.DurationField("休憩時間", null=True, blank=True, default=timedelta(minutes=20))
    実働時間 = models.DurationField("実働時間", null=True, blank=True)
    残業時間 = models.DurationField("残業時間", null=True, blank=True)

    deposit_amount = models.PositiveIntegerField("入金額", null=True, blank=True, help_text="手动输入的入金金额")
    deposit_difference = models.IntegerField("過不足額", null=True, blank=True, help_text="入金 − 現金")

    # ✅ etc_expected	IntegerField	应收ETC金额（从计程表）
    # ✅ etc_collected_cash	IntegerField	司机从乘客现金收取的ETC金额
    # ✅ etc_collected_app	IntegerField	司机通过app收取的ETC金额
    # ✅ etc_collected_total	@property	实收ETC合计 = cash + app
    # ✅ etc_uncollected	@property	应收 - 实收 = 未收部分
    # ✅ etc_collected	IntegerField	旧字段，暂时保留（可用于数据迁移）

    # ✅ 新字段（合并）
    etc_collected = models.PositiveIntegerField("ETC收取金额（円）", null=True, blank=True, help_text="日计账单中“空乘合计”")
    etc_payment_method = models.CharField(
        "ETC收取方式", max_length=20,
        choices=PAYMENT_METHOD_CHOICES,  # ✅ 正确引用全局变量，避免循环引用
        null=True, blank=True
    )
    
    # ✅ 请在这里插入新字段
    etc_collected_cash = models.PositiveIntegerField("ETC現金收取（円）", null=True, blank=True)
    etc_collected_app = models.PositiveIntegerField("ETCアプリ収取（円）", null=True, blank=True)
    
    etc_uncollected = models.PositiveIntegerField("ETC未收金额（円）", null=True, blank=True, help_text="日计账单中“空车合计”")
    
    # ✅ 新增字段：ETC不足部分（多跑未补收）
    etc_shortage = models.PositiveIntegerField(default=0, verbose_name="ETC不足额", help_text="ETC使用金额超过应收金额的部分，将从工资中扣除")

    etc_note = models.CharField(max_length=255, blank=True, verbose_name="ETC备注")

    @property
    def etc_collected_total(self):
        """实收ETC合计 = cash + app"""
        return (self.etc_collected_cash or 0) + (self.etc_collected_app or 0)
    
    @property
    def etc_expected(self):
        """ETC应收合计 = 收取 + 未收"""
        return (self.etc_collected or 0) + (self.etc_uncollected or 0)

    @property
    def is_etc_included_in_deposit(self):
        """
        判断是否已包含ETC（仅供参考，逻辑为：入金大于或等于实际现金总额+ETC收取金额）
        """
        if self.deposit_amount is None:
            return False
        meter_fee_total = self.total_meter_fee or 0
        etc_collected = self.etc_collected or 0
        # 如果入金额 >= 计程表金额 + ETC金额 → 认为已含ETC
        return self.deposit_amount >= (meter_fee_total + etc_collected)

    gas_volume = models.DecimalField("ガソリン量 (L)",max_digits=6, decimal_places=2,default=0,validators=[MinValueValidator(0)])
    mileage = models.DecimalField("里程 (KM)",max_digits=7, decimal_places=2,default=0,validators=[MinValueValidator(0)])

    # —— 编辑人/编辑时间 —— 
    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='edited_dailyreports',
        verbose_name="编辑人"
    )
    edited_at = models.DateTimeField("编辑时间", auto_now=True, null=True, blank=True, help_text="自动记录最后保存时间")

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

        # ✅ 新增：业务逻辑函数
    def calculate_work_times(self):
        """
        自动计算 勤務時間 / 休憩時間 / 実働時間 / 残業時間
        """
        #from datetime import datetime, timedelta
        """
        if not self.clock_in or not self.clock_out:
            # 任一为空就跳过计算
            self.勤務時間 = self.clock_out - self.clock_in
            self.休憩時間 = self.休憩時間 or timedelta(minutes=20)
            self.実働時間 = self.勤務時間 - self.休憩時間
            self.残業時間 = max(timedelta(), self.実働時間 - timedelta(hours=8))
            return
        """
        print("🧪 DEBUG: clock_in =", self.clock_in, "clock_out =", self.clock_out)

        # ✅ 任一时间为空，跳过计算，赋值为 None
        if not self.clock_in or not self.clock_out:
            self.勤務時間 = None
            self.休憩時間 = None
            self.実働時間 = None
            self.残業時間 = None
            return

        # 合成 datetime 对象用于跨日判断
        in_dt = datetime.combine(datetime.today(), self.clock_in)
        out_dt = datetime.combine(datetime.today(), self.clock_out)
        if out_dt <= in_dt:
            out_dt += timedelta(days=1)  # 跨午夜

        work_duration = out_dt - in_dt  # 勤務時間

        # 如果用户未填写休憩時間，则设为20分钟
        user_break = self.休憩時間 or timedelta()
        if user_break.total_seconds() <= 0:
            user_break = timedelta(minutes=0)

        # ✅ 在用户填写基础上 +20分钟
        break_duration = user_break + timedelta(minutes=20)  # 实际用于计算

        actual_duration = work_duration - break_duration  # 実働時間
        overtime = actual_duration - timedelta(hours=8)   # 残業時間，可为负数

        # 赋值保存
        self.勤務時間 = work_duration
        self.休憩時間 = break_duration
        self.実働時間 = actual_duration
        self.残業時間 = overtime

# 乘务日报明细，一天可有多条，归属于DriverDailyReport
class DriverDailyReportItem(models.Model):
    report = models.ForeignKey(
        DriverDailyReport, on_delete=models.CASCADE, related_name='items', verbose_name="所属日报"
    )
    ride_time = models.CharField("乘车时间", max_length=30, blank=True)
    ride_from = models.CharField("乘车地", max_length=100, blank=True)
    via = models.CharField("経由", max_length=100, blank=True)
    ride_to = models.CharField("降车地", max_length=100, blank=True)
    num_male = models.IntegerField("男性", blank=True, null=True)
    num_female = models.IntegerField("女性", blank=True, null=True)
    meter_fee = models.DecimalField("メータ料金", max_digits=7, decimal_places=2, blank=True, null=True)
    is_charter = models.BooleanField(default=False)  # ✅ 添加 default
    
    #charter_amount_jpy = models.DecimalField(max_digits=8, decimal_places=0, default=0)
    #charter_payment_method = models.CharField(max_length=20, blank=True, default="")
    payment_method = models.CharField("支付方式", max_length=16, choices=PAYMENT_METHOD_CHOICES, blank=True)
     # --- 新增开始：待入（未到账不计入売上；到账后手动取消勾选） ---
    is_pending = models.BooleanField(default=False, verbose_name="待入")
    # --- 新增结束 ---

     # === ↓↓↓ 包车收款明细字段：用于计算貸切現金/未収合計 ↓↓↓ ===

    charter_payment_method = models.CharField(
        max_length=20,
        choices=[
            ('self_wechat', '司机微信/支付宝'),
            ('rmb_cash', '人民币现金'),
            ('jpy_cash', '日元现金'),
            ('to_company', '转付公司'),
            ('boss_wechat', '老板微信'),
            ('bank_transfer', '银行转账'),
        ],
        default="jpy_cash",             # ← 如需默认选项，加上
        blank=True,
        null=True,
        verbose_name='貸切收款方式'
    )

    charter_amount_original = models.DecimalField(
        max_digits=10, decimal_places=2,
        blank=True,
        null=True,
        verbose_name='貸切原始金额（元/円）'
    )

    charter_exchange_rate = models.DecimalField(
        max_digits=6, decimal_places=2,
        blank=True,
        null=True,
        verbose_name='換算汇率'
    )

    charter_amount_jpy = models.DecimalField(
        max_digits=10, decimal_places=0,
        blank=True,
        null=True,
        verbose_name='貸切日元金额'
    )

    # === ↑↑↑ 包车字段结束 ↑↑↑ ===

    # ======= BEGIN NEW (ETC 明细化：行级字段) =======
    etc_riding = models.PositiveIntegerField("乗車ETC（円）", default=0)
    etc_empty  = models.PositiveIntegerField("空車ETC（円）", default=0)

    ETC_CHARGE_CHOICES = (
        ("company",  "会社負担"),
        ("driver",   "ドライバー立替"),
        ("customer", "お客様支払"),
    )
    etc_charge_type = models.CharField(
        "ETC負担",
        max_length=20,
        choices=ETC_CHARGE_CHOICES,
        default="company",
    )
    # ======= END NEW (ETC 明细化：行级字段) =======

    note = models.CharField("备注", max_length=255, blank=True)
    comment = models.TextField("录入员注释", blank=True)
    is_flagged = models.BooleanField(default=False, verbose_name="标记为重点")
    has_issue = models.BooleanField("是否异常", default=False)

    combined_group = models.CharField("合算グループ", max_length=100, blank=True, null=True)

    def save(self, *args, **kwargs):
        # ✅ 已有逻辑：如果 comment 不为空就设为有异常
        self.has_issue = bool(self.comment.strip())
        
        super().save(*args, **kwargs)

        # ✅ 保存后更新日报状态
        if self.report:
            self.report.has_issue = self.report.items.filter(has_issue=True).exists()
            self.report.save(update_fields=['has_issue'])

    def __str__(self):
        return f"{self.ride_time} - {self.ride_from}→{self.ride_to} - {self.meter_fee}"



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