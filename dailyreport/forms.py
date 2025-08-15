from datetime import timedelta
from django import forms
from django.forms import inlineformset_factory
from django.forms.models import BaseInlineFormSet
from .models import DriverDailyReport, DriverDailyReportItem, DriverReportImage
from vehicles.models import Reservation as VehicleReservation
from dailyreport.utils.debug import apply_form_control_style
from carinfo.models import Car  # 保持你项目里的实际路径


# ✅ 1. 自定义 FormSet（放在 ReportItemFormSet 之前！）
class RequiredReportItemFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()

        for form in self.forms:
            # 已经主动删除的行跳过
            if form.cleaned_data.get('DELETE'):
                continue

            meter_fee   = form.cleaned_data.get('meter_fee')
            pay_method  = form.cleaned_data.get('payment_method')

            # ★ 貸切相关字段
            is_charter  = form.cleaned_data.get('is_charter')
            charter_amt = form.cleaned_data.get('charter_amount_jpy')
            charter_pm  = form.cleaned_data.get('charter_payment_method')

            # ★ “这一行是否有内容”的判断，必须把貸切字段也算上
            has_data = any([
                meter_fee,
                pay_method,
                is_charter,
                charter_amt,
                charter_pm,
            ])

            if not has_data:
                # 整行都空：自动删除，避免抛错
                form.cleaned_data['DELETE'] = True
                continue

            # ★ 分支校验：貸切 vs 非貸切
            if is_charter or charter_amt or charter_pm:
                # 視為「貸切」行：只要求 charter_payment_method
                if not charter_pm:
                    form.add_error('charter_payment_method', '貸切の処理方法を選択してください。')
                # 注意：貸切行不强制普通 payment_method
            else:
                # 非貸切行：填写了料金就必须有普通支付方式
                if meter_fee and not pay_method:
                    form.add_error('payment_method', '支払方法は必須です。')

# ✅2. 主表 Form：编辑日报基本信息（出勤时间、备注、车辆等）
# --- forms.py 顶部：新增或替换为仅三项 ---
ETC_PAYMENT_CHOICES = [
    ("", "--------"),
    ("company_card", "会社カード"),
    ("personal_card", "個人カード（禁止）"),
]
# ---------------------------------------

class DriverDailyReportForm(forms.ModelForm):

    # 覆盖 etc_payment_method 字段为受控的三选项、class Meta: 之前（或之后都行，但一定在类内部，且不要再有同名字段的其它定义）
    etc_payment_method = forms.ChoiceField(
        choices=ETC_PAYMENT_CHOICES,          # 你在顶部已定义三项
        required=False,
        label="空車ETC カード",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = DriverDailyReport
        fields = [
            'vehicle', 'date', 'note', 'has_issue', 'status',
            'clock_in', 'clock_out', 'gas_volume', 'mileage',
            'deposit_amount', 'deposit_difference',
            'etc_collected', 'etc_payment_method', 'etc_uncollected',
            'etc_shortage',
        ]
        widgets = {
            'vehicle':      forms.HiddenInput(),
            'status':       forms.HiddenInput(),
            'date':         forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'note':         forms.Textarea(attrs={'class': 'form-control auto-width-input', 'rows': 2}),
            'has_issue':    forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'clock_in':     forms.TimeInput(attrs={'type': 'time', 'class': 'form-control auto-width-input'}),
            'clock_out':    forms.TimeInput(attrs={'type': 'time', 'class': 'form-control auto-width-input'}),
            'gas_volume':   forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control auto-width-input', 'placeholder': '0.00 L'}),
            'mileage':      forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control auto-width-input', 'placeholder': '0.00 KM'}),
            # ✅ ETC 字段
            'etc_collected': forms.NumberInput(attrs={'step': '1', 'class': 'form-control auto-width-input'}),
            'etc_payment_method': forms.Select(attrs={'class': 'form-select'}),
            'etc_uncollected': forms.NumberInput(attrs={'step': '1', 'class': 'form-control auto-width-input'}),
            'etc_shortage': forms.NumberInput(attrs={'step': '1', 'readonly': 'readonly', 'class': 'form-control auto-width-input text-danger', 'placeholder': 'ETC不足额,自动计算'}),
        }

    def __init__(self, *args, **kwargs):
        instance = kwargs.get('instance', None)
        super().__init__(*args, **kwargs)

        # ✅ 样式初始化（通用）
        apply_form_control_style(self.fields)
        self.fields['has_issue'].widget.attrs.update({'class': 'form-check-input'})
        self.fields['vehicle'].disabled = True

        # ✅ 设置数值字段为非必填 + 默认值，防止 None 导致报错
        numeric_defaults = {
            'deposit_amount': 0,
            'etc_collected': 0,
            'etc_uncollected': 0,
            'etc_shortage': 0,
            'gas_volume': 0.0,
            'mileage': 0.0,
        }

        for field_name, default_value in numeric_defaults.items():
            if field_name in self.fields:
                self.fields[field_name].required = False
                self.fields[field_name].initial = default_value

        # ✅ 自动注入 clock_in / clock_out / vehicle（仅在 GET 且有 instance 时生效）
        if instance and not self.data:
            driver_user = getattr(instance.driver, "user", None)
            if driver_user:
                res = (
                    VehicleReservation.objects           # ← 这里用 VehicleReservation
                    .filter(
                        driver=driver_user,
                        actual_departure__date=instance.date,
                        actual_departure__isnull=False
                    )
                    .order_by('-actual_departure')
                    .first()
                )
                if res:
                    self.fields['clock_in'].initial = res.actual_departure.time()
                    if res.actual_return:
                        self.fields['clock_out'].initial = res.actual_return.time()
                    if res.vehicle:
                        self.fields['vehicle'].initial = res.vehicle


    # ✅ 插入位置开始：ETC 字段清洗
    def clean_etc_collected(self):
        value = self.cleaned_data.get('etc_collected')
        if value in [None, '', '例：2110']:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            self.add_error('etc_collected', '数値を入力してください')
            return None

    def clean_etc_uncollected(self):
        value = self.cleaned_data.get('etc_uncollected')
        if value in [None, '', '例：470']:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            self.add_error('etc_uncollected', '数値を入力してください')
            return None
    # ✅ 插入位置结束

    
    # 改动 2：兜底校验
    def clean_etc_payment_method(self):
        v = (self.cleaned_data.get("etc_payment_method") or "").strip().lower()
        if v in {"customer_card", "guest_card", "customer", "guest", "お客様", "お客様カード"}:
            return ""
        if v not in {"", "company_card", "personal_card"}:
            return ""
        return v
    
    
    def clean(self):
        cleaned_data = super().clean()

        # 获取前端输入的 "hh:mm" 格式字符串
        break_time_str = self.data.get('break_time_input', '')
        if break_time_str:
            try:
                h, m = map(int, break_time_str.strip().split(':'))
                total_minutes = h * 60 + m

                # 保存原始输入（不额外加 20 分钟）
                cleaned_data['休憩時間'] = timedelta(minutes=total_minutes)
            except ValueError:
                self.add_error('break_time_input', '休憩時間の形式は「HH:MM」で入力してください')

        return cleaned_data

        
# ✅ 3. 明细 Form：包含多条乘车记录的 InlineFormSet
class DriverDailyReportItemForm(forms.ModelForm):
    class Meta:
        model = DriverDailyReportItem
        fields = '__all__'
        widgets = {
            'ride_time': forms.TextInput(attrs={'class': 'ride-time-input auto-width-input'}),
            'ride_from': forms.TextInput(attrs={'class': 'auto-width-input'}),
            'via': forms.TextInput(attrs={'class': 'auto-width-input'}),
            'ride_to': forms.TextInput(attrs={'class': 'auto-width-input'}),
            'num_male': forms.NumberInput(attrs={'class': 'auto-width-input'}),
            'num_female': forms.NumberInput(attrs={'class': 'auto-width-input'}),
            'meter_fee': forms.NumberInput(attrs={
                'step': '1',
                'class': 'form-control form-control-sm text-end auto-width-input meter-fee-input',
                'type': 'number',
                'inputmode': 'numeric',
                'pattern': '[0-9]*',
            }),
            'payment_method': forms.Select(attrs={'class': 'payment-method-select'}),
            'note': forms.TextInput(attrs={'class': 'note-input auto-width-input'}),
            'is_flagged': forms.CheckboxInput(attrs={'class': 'mark-checkbox'}),
            'charter_amount_jpy': forms.NumberInput(attrs={
                'step': '1',
                'class': 'form-control form-control-sm text-end charter-amount-input',
                'inputmode': 'numeric',
                'pattern': '[0-9]*',
            }),
            'charter_payment_method': forms.Select(attrs={
                'class': 'form-select form-select-sm charter-payment-method-select',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ✅ 这些你原来就有
        self.fields['num_male'].required = False
        self.fields['num_female'].required = False
        self.fields['charter_amount_jpy'].required = False
        self.fields['charter_payment_method'].required = False

        # ✅ 关键：给「貸切」复选框一个确定的类名，便于 JS 选择器命中
        if 'is_charter' in self.fields:
            cls = self.fields['is_charter'].widget.attrs.get('class', '')
            self.fields['is_charter'].widget.attrs['class'] = (cls + ' charter-checkbox').strip()

# 4. 明细 FormSet（必须最后）
ReportItemFormSet = inlineformset_factory(
    DriverDailyReport,
    DriverDailyReportItem,
    form=DriverDailyReportItemForm,
    formset=RequiredReportItemFormSet,
    extra=1,
    can_delete=True,
    max_num=40
)

# ✅ 日报上传图片
class DriverReportImageForm(forms.ModelForm):
    class Meta:
        model = DriverReportImage
        fields = ['image']
