from django.db import models
from accounts.models import DriverUser
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator
from carinfo.models import Car
from datetime import datetime, timedelta

# 📌 插入在 import 之后，模型定义之前
RESIDENCE_STATUS_CHOICES = [
    ('日本人の配偶者等', '日本人の配偶者等'),
    ('永住者', '永住者'),
    ('定住者', '定住者'),
    ('家族滞在', '家族滞在'),
    ('技術・人文知識・国際業務', '技術・人文知識・国際業務'),
    ('技能', '技能'),
    ('技能実習', '技能実習'),
    ('特定技能46号', '特定技能46号'),
    ('留学', '留学'),
    ('研修', '研修'),
    ('短期滞在', '短期滞在'),
    ('その他', 'その他'),
]

PAYMENT_METHOD_CHOICES = [
    ('cash', '現金'),
    ('uber', 'Uber'),
    ('didi', 'Didi'),
    ('credit', 'クレジットカード'),
    ('kyokushin', '京交信'),
    ('omron', 'オムロン'),
    ('kyotoshi', '京都市他'),
    ('qr', '扫码(PayPay/AuPay/支付宝/微信Pay等)'),
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
    employ_type = models.CharField("在職類型", max_length=20, choices=[
        ('1', '正式運転者'),
        ('2', '非常勤運転者'),
        ('3', '退職者')  # ✅ 正确的方式是列表
    ])
    appointment_date = models.DateField(blank=True, null=True, verbose_name="選任年月日")
    hire_date = models.DateField(blank=True, null=True, verbose_name="入社年月日")
    resigned_date = models.DateField(blank=True, null=True, verbose_name="退職日")  # ✅ 新增
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

    # 🌐 外国籍・在留管理（用于签证在留tab页）
    is_foreign = models.BooleanField(default=False, verbose_name="外国籍")
    nationality = models.CharField(max_length=32, blank=True, null=True, verbose_name="国籍")
    residence_status = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        choices=RESIDENCE_STATUS_CHOICES,  # ✅ 选择项绑定
        verbose_name="在留資格"
    )
    residence_expiry = models.DateField(blank=True, null=True, verbose_name="在留期限")
    residence_card_image = models.ImageField(upload_to='residence_cards/', blank=True, null=True, verbose_name="在留カード画像")
    work_permission_confirmed = models.BooleanField(default=False, verbose_name="就労資格確認済")

    # 🧾 入社资料提出状况（可逐步扩展）
    has_health_check = models.BooleanField(default=False, verbose_name="健康診断書提出済")
    has_residence_certificate = models.BooleanField(default=False, verbose_name="住民票提出済")
    has_tax_form = models.BooleanField(default=False, verbose_name="扶養控除等申告書提出済")
    has_license_copy = models.BooleanField(default=False, verbose_name="免許証コピー提出済")



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

class Qualification(models.Model):
    driver = models.OneToOneField(Driver, on_delete=models.CASCADE, related_name='qualification')
    qualification_name = models.CharField("資格名", max_length=100, blank=True)
    qualification_number = models.CharField("資格番号", max_length=50, blank=True)
    issue_date = models.DateField("交付日", null=True, blank=True)
    expiry_date = models.DateField("有効期限", null=True, blank=True)
    note = models.TextField("備考", blank=True)

    class Meta:
        verbose_name = "資格"
        verbose_name_plural = "資格"

    def __str__(self):
        return f"{self.driver.name} - {self.qualification_name}"

class Aptitude(models.Model):
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name='aptitudes', verbose_name="司机")
    name = models.CharField("资质名称", max_length=100)
    issue_date = models.DateField("颁发日期", blank=True, null=True)
    expiry_date = models.DateField("到期日期", blank=True, null=True)
    note = models.TextField("备注", blank=True)

    class Meta:
        verbose_name = "资质"
        verbose_name_plural = "资质"

    def __str__(self):
        return f"{self.driver.name} - {self.name}"

class Reward(models.Model):
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name='rewards')
    points = models.IntegerField('积分', default=0)
    issued_at = models.DateTimeField('发放时间', default=timezone.now)
    remark = models.CharField('备注', max_length=200, blank=True)

    class Meta:
        verbose_name = '奖励记录'
        verbose_name_plural = '奖励记录'

    def __str__(self):
        return f"{self.driver.name}：{self.points} 点"

class Education(models.Model):
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name='educations')
    school_name = models.CharField('学校名称', max_length=100)
    degree = models.CharField('学位／学历', max_length=50, blank=True)
    start_date = models.DateField('起始日期', blank=True, null=True)
    end_date = models.DateField('结束日期', blank=True, null=True)
    note = models.TextField('备注', blank=True)

    class Meta:
        verbose_name = '教育经历'
        verbose_name_plural = '教育经历'

    def __str__(self):
        return f"{self.driver.name} – {self.school_name}"

class Pension(models.Model):
    driver = models.ForeignKey(
        Driver,
        on_delete=models.CASCADE,
        related_name='pensions',
        verbose_name='司机'
    )
    pension_number = models.CharField('年金番号', max_length=32, blank=True)
    join_date = models.DateField('厚生年金加入日', null=True, blank=True)
    note = models.TextField('备注', blank=True)

    class Meta:
        verbose_name = '厚生年金记录'
        verbose_name_plural = '厚生年金记录'

    def __str__(self):
        return f"{self.driver.name} – {self.join_date or '未加入'}"


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

# ★ 新增！乘务日报明细，一天可有多条，归属于DriverDailyReport
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
    payment_method = models.CharField("支付方式", max_length=16, choices=PAYMENT_METHOD_CHOICES, blank=True)
    note = models.CharField("备注", max_length=255, blank=True)
    comment = models.TextField("录入员注释", blank=True)  # 新增字段
    is_flagged = models.BooleanField(default=False, verbose_name="标记为重点")
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
    month = models.DateField('月份')  # 用每月1号代表当月

    # --- 勤怠字段 ---
    working_days = models.IntegerField('就業日数', default=0)
    attendance_days = models.IntegerField('出勤日数', default=0)
    absence_days = models.IntegerField('欠勤日数', default=0)
    holiday_work_days = models.IntegerField('休日出勤日数', default=0)
    paid_leave_days = models.IntegerField('有給日数', default=0)
    overtime_hours = models.DecimalField('残業時間', max_digits=5, decimal_places=2, default=0)
    night_hours = models.DecimalField('深夜時間', max_digits=5, decimal_places=2, default=0)
    holiday_hours = models.DecimalField('休日時間', max_digits=5, decimal_places=2, default=0)
    total_working_hours = models.DecimalField('総労働時間', max_digits=5, decimal_places=2, default=0)
    late_minutes = models.IntegerField('遅刻分', default=0)  # 分钟数
    early_minutes = models.IntegerField('早退分', default=0)  # 分钟数

    # --- 支給字段 ---
    basic_pay = models.DecimalField('基本給', max_digits=10, decimal_places=2, default=0)
    overtime_allowance = models.DecimalField('残業手当', max_digits=10, decimal_places=2, default=0)
    night_allowance = models.DecimalField('深夜手当', max_digits=10, decimal_places=2, default=0)
    holiday_allowance = models.DecimalField('休日手当', max_digits=10, decimal_places=2, default=0)
    commute_allowance = models.DecimalField('通勤手当', max_digits=10, decimal_places=2, default=0)
    bonus = models.DecimalField('資格手当', max_digits=10, decimal_places=2, default=0)
    other_allowances = models.DecimalField('役職手当', max_digits=10, decimal_places=2, default=0)
    special_allowance = models.DecimalField('住宅手当', max_digits=10, decimal_places=2, default=0)
    transportation_allowance = models.DecimalField('家族手当', max_digits=10, decimal_places=2, default=0)
    total_pay = models.DecimalField('総支給額', max_digits=10, decimal_places=2, default=0)

    # --- 控除字段 ---
    health_insurance_deduction = models.DecimalField('健康保険扣除', max_digits=10, decimal_places=2, default=0)
    health_care_insurance_deduction = models.DecimalField('介護保険', max_digits=10, decimal_places=2, default=0)
    pension_deduction = models.DecimalField('厚生年金扣除', max_digits=10, decimal_places=2, default=0)
    employment_insurance_deduction = models.DecimalField('雇用保険扣除', max_digits=10, decimal_places=2, default=0)
    workers_insurance_deduction = models.DecimalField('労災保険扣除', max_digits=10, decimal_places=2, default=0)
    income_tax_deduction = models.DecimalField('所得税扣除', max_digits=10, decimal_places=2, default=0)
    resident_tax_deduction = models.DecimalField('住民税扣除', max_digits=10, decimal_places=2, default=0)
    tax_total = models.DecimalField('税金合計', max_digits=10, decimal_places=2, default=0)
    other_deductions = models.DecimalField('其他扣除', max_digits=10, decimal_places=2, default=0)
    total_deductions = models.DecimalField('総控除額', max_digits=10, decimal_places=2, default=0)
    # --- 最终金额 ---
    # 差引支給額 = 总支给额 - 总控除额
    # 这里默认总支给额和总控除额都已计算好
    net_pay = models.DecimalField('差引支給額', max_digits=10, decimal_places=2, default=0)

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

class Vehicle(models.Model):
    name = models.CharField("车辆名", max_length=50)  # 如：シエンタ、白色皇冠等
    plate_number = models.CharField("车牌号", max_length=20)  # 如：5001、足立500 あ12-34

    def __str__(self):
        return f"{self.plate_number}（{self.name}）"
