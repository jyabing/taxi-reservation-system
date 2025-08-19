from django.db import models
from accounts.models import DriverUser
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator
from carinfo.models import Car
from datetime import datetime, timedelta
from decimal import Decimal

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
    ('omron', 'オムロン(愛のタクシーチケット)'),
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
    #hire_date = models.DateField(blank=True, null=True, verbose_name="入社年月日")
    hire_date = models.DateField(verbose_name="入社年月日")
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
        verbose_name = "员工资料"
        verbose_name_plural = "员工资料"
    
    def __str__(self):
        return f"{self.driver_code} - {self.name}"

# 驾驶经验（可多条）
class DrivingExperience(models.Model):
    driver = models.ForeignKey(Driver, related_name="driving_exp", on_delete=models.CASCADE)
    vehicle_type = models.CharField("车种", max_length=30, blank=True)
    years = models.IntegerField("经验年数", blank=True, null=True)
    company = models.CharField("经验公司", max_length=50, blank=True)

# 保险信息（可多条）
class DriverInsurance(models.Model):
    driver = models.ForeignKey(Driver, related_name="driver_insurances", on_delete=models.CASCADE)
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
    
    # 売上分段控除（自動計算で保存）
    progressive_fee = models.DecimalField('売上分段控除', max_digits=10, decimal_places=2, default=0)
    
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

    def _as_dec(self, v):
        return v if isinstance(v, Decimal) else Decimal(str(v or 0))

    def recompute_totals(self):
        """総控除額・差引支給額を自動再計算"""
        # 総控除額 ＝ 法定控除合計 + その他控除 + 売上分段控除
        total_deds = (
            self._as_dec(self.health_insurance_deduction) +
            self._as_dec(self.health_care_insurance_deduction) +
            self._as_dec(self.pension_deduction) +
            self._as_dec(self.employment_insurance_deduction) +
            self._as_dec(self.workers_insurance_deduction) +
            self._as_dec(self.income_tax_deduction) +
            self._as_dec(self.resident_tax_deduction) +
            self._as_dec(self.other_deductions) +
            self._as_dec(self.progressive_fee)
        )
        self.total_deductions = total_deds

        # 差引支給額 ＝ 総支給額 − 総控除額
        self.net_pay = self._as_dec(self.total_pay) - self._as_dec(self.total_deductions)

    def save(self, *args, **kwargs):
        try:
            self.recompute_totals()
        except Exception:
            pass  # 防御：合計失敗でも保存は継続
        super().save(*args, **kwargs)
    # ===== INSERT-M: 自動合計ロジック END =====

    def __str__(self):
        return f"{self.driver} - {self.month.strftime('%Y-%m')} 工资"



# ✅【新增 Staff 模型】
class Staff(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='staff_profile',
        null=True, blank=True,
        verbose_name='绑定用户'
    )
    staff_code = models.CharField('職員番号', max_length=20, unique=True)
    name = models.CharField('氏名', max_length=32)
    department = models.CharField('部門', max_length=32, blank=True)
    position = models.CharField('職種', max_length=32, choices=[
        ('事務', '事務'),
        ('経理', '経理'),
        ('管理者', '管理者'),
        ('その他', 'その他'),
    ])
    hire_date = models.DateField(blank=True, null=True, verbose_name="入社年月日")
    resigned_date = models.DateField(blank=True, null=True, verbose_name="退職日")
    phone_number = models.CharField(max_length=32, blank=True, null=True, verbose_name="電話番号")
    note = models.TextField('備考', blank=True)

    class Meta:
        verbose_name = "事务员资料"
        verbose_name_plural = "事务员资料"

    def __str__(self):
        return f"{self.staff_code} - {self.name}"

class Vehicle(models.Model):
    name = models.CharField("车辆名", max_length=50)  # 如：シエンタ、白色皇冠等
    plate_number = models.CharField("车牌号", max_length=20)  # 如：5001、足立500 あ12-34

    def __str__(self):
        return f"{self.plate_number}（{self.name}）"
