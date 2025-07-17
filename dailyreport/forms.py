from datetime import timedelta
from django import forms
from django.forms import inlineformset_factory
from django.forms.models import BaseInlineFormSet  # ✅ ← 需要这行
from .models import DriverDailyReport, DriverDailyReportItem, DriverReportImage
from vehicles.models import Reservation
from dailyreport.utils import apply_form_control_style


# ✅ 1. 自定义 FormSet（放在 ReportItemFormSet 之前！）
class RequiredReportItemFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()

        for form in self.forms:
            # 忽略已标记为删除的行
            if form.cleaned_data.get('DELETE'):
                continue

            # 只要金额或支付方式有填写，就视为有效行
            has_data = any([
                form.cleaned_data.get('meter_fee'),
                form.cleaned_data.get('payment_method'),
            ])

            if has_data:
                # 只强制支付方式为必填
                if not form.cleaned_data.get('payment_method'):
                    form.add_error('payment_method', '支払方法は必須です。')
            else:
                # 如果整行都为空白，自动标记为删除（避免报错）
                form.cleaned_data['DELETE'] = True

# ✅2. 主表 Form：编辑日报基本信息（出勤时间、备注、车辆等）
class DriverDailyReportForm(forms.ModelForm):
    class Meta:
        model = DriverDailyReport
        fields = [
            'vehicle', 'date', 'note', 'has_issue', 'status',
            'clock_in', 'clock_out', 'gas_volume', 'mileage',
            'deposit_amount', 'deposit_difference',
            # ✅ 新增字段
            'etc_expected', 'etc_collected'
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
            # ✅ 新增 ETC 字段样式
            'etc_expected': forms.NumberInput(attrs={'step': '1', 'class': 'form-control auto-width-input', 'placeholder': '例：4050'}),
            'etc_collected': forms.NumberInput(attrs={'step': '1', 'class': 'form-control auto-width-input', 'placeholder': '例：2270'}),
        }

    def __init__(self, *args, **kwargs):
        instance = kwargs.get('instance', None)
        super().__init__(*args, **kwargs)

        # 样式初始化
        apply_form_control_style(self.fields)
        self.fields['has_issue'].widget.attrs.update({'class': 'form-check-input'})
        self.fields['vehicle'].disabled = True

        # ✅ 自动注入 clock_in / clock_out / vehicle，仅限 GET 且 instance 存在时
        if instance and not self.data:
            driver_user = instance.driver.user
            if driver_user:
                res = (
                    Reservation.objects
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
                'class': 'form-control form-control-sm text-end auto-width-input meter-fee-input',  # ← 就是这段
                'type': 'number',
                'step': '1',
                'inputmode': 'numeric',
                'pattern': '[0-9]*',
            }),
            'payment_method': forms.Select(attrs={'class': 'payment-method-select'}),
            'note': forms.TextInput(attrs={'class': 'note-input auto-width-input'}),
            'is_flagged': forms.CheckboxInput(attrs={'class': 'mark-checkbox'}),  # ✅ 已添加
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ✅ 显式取消必填，避免“这个字段是必填项”错误
        self.fields['num_male'].required = False
        self.fields['num_female'].required = False

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
