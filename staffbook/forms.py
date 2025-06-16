from django import forms
from .models import (
    Driver, DriverLicense, Accident,
    DriverDailySales, DriverDailyReport, DriverDailyReportItem,
    DriverPayrollRecord, DriverReportImage, Reward, Insurance
)
from django.forms import inlineformset_factory

# ✅ 通用样式自动添加工具函数
def apply_form_control_style(fields, exclude_types=(forms.Select, forms.RadioSelect, forms.CheckboxInput, forms.Textarea)):
    for field in fields:
        if not isinstance(fields[field].widget, exclude_types):
            fields[field].widget.attrs.update({'class': 'form-control'})

# ✅ 司机基础信息表单
class DriverForm(forms.ModelForm):
    class Meta:
        model = Driver
        fields = [
            'driver_code', 'name', 'kana', 'company', 'workplace', 'department',
            'position', 'birth_date', 'gender', 'blood_type',
            'hire_date', 'appointment_date', 'create_date', 'remark'
        ]
        widgets = {
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'blood_type': forms.Select(attrs={'class': 'form-select'}),
            'birth_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'hire_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'appointment_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'create_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'remark': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_form_control_style(self.fields)

# ✅ 驾照信息表单
class DriverLicenseForm(forms.ModelForm):
    class Meta:
        model = DriverLicense
        fields = [
            'photo', 'license_number', 'issue_date', 'expiry_date',
            'date_acquired_a', 'date_acquired_b', 'date_acquired_c',
            'license_types', 'license_conditions', 'note'
        ]
        widgets = {
            'issue_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'date_acquired_a': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'date_acquired_b': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'date_acquired_c': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'license_number': forms.TextInput(attrs={'class': 'form-control'}),
            'license_conditions': forms.TextInput(attrs={'class': 'form-control'}),
            'note': forms.Textarea(attrs={'class': 'form-control', 'rows':2}),
            'license_types': forms.CheckboxSelectMultiple(),
        }

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('issue_date'):
            self.add_error('issue_date', '交付年月日为必填项')
        return cleaned

# ✅ 事故表单
class AccidentForm(forms.ModelForm):
    class Meta:
        model = Accident
        fields = ['happened_at', 'description', 'penalty', 'note']
        widgets = {
            'happened_at': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 2}),
            'note': forms.Textarea(attrs={'rows': 2}),
        }

# ✅ 简版基础信息表单
class DriverBasicForm(forms.ModelForm):
    class Meta:
        model = Driver
        fields = [
            'driver_code', 'name', 'kana', 'company', 'workplace', 'department',
            'position', 'employ_type',
            'appointment_date', 'hire_date', 'create_date',
            'birth_date', 'gender', 'blood_type', 'postal_code', 'address',
            'phone_number', 'photo', 'photo_date', 'remark'
        ]

# ✅ 日销售数据表单
class DriverDailySalesForm(forms.ModelForm):
    class Meta:
        model = DriverDailySales
        fields = ['date', 'cash_amount', 'card_amount', 'ride_count', 'mileage']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }

# ✅ 日报主表表单
class DriverDailyReportForm(forms.ModelForm):
    class Meta:
        model = DriverDailyReport
        fields = ['date', 'note']
        widgets = {
            'note': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }

# ✅ 日报明细表单
class DriverDailyReportItemForm(forms.ModelForm):
    class Meta:
        model = DriverDailyReportItem
        fields = [
            'ride_time', 'ride_from', 'via', 'ride_to',
            'num_male', 'num_female', 'meter_fee',
            'payment_method', 'note'
        ]
        widgets = {
            'ride_time': forms.TextInput(attrs={'class': 'ride-time-input auto-width-input'}),
            'ride_from': forms.TextInput(attrs={'class': 'auto-width-input'}),
            'via': forms.TextInput(attrs={'class': 'auto-width-input'}),
            'ride_to': forms.TextInput(attrs={'class': 'auto-width-input'}),
            'num_male': forms.NumberInput(attrs={'class': 'auto-width-input'}),
            'num_female': forms.NumberInput(attrs={'class': 'auto-width-input'}),
            'meter_fee': forms.NumberInput(attrs={'class': 'meter-fee-input auto-width-input'}),
            'payment_method': forms.Select(attrs={'class': 'payment-method-select'}),
            'note': forms.TextInput(attrs={'class': 'note-input auto-width-input'}),
        }

# ✅ 明细表单集合
ReportItemFormSet = inlineformset_factory(
    DriverDailyReport,
    DriverDailyReportItem,
    form=DriverDailyReportItemForm,
    extra=1,
    can_delete=True,
    max_num=40
)

# ✅ 日报上传图片
class DriverReportImageForm(forms.ModelForm):
    class Meta:
        model = DriverReportImage
        fields = ['image']

# ✅ 司机个人信息编辑
class DriverPersonalInfoForm(forms.ModelForm):
    class Meta:
        model = Driver
        fields = ['photo_date', 'postal_code', 'address', 'phone_number', 'photo']
        widgets = {
            'photo_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'postal_code': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.TextInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            # 图片字段不需要 form-control
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_form_control_style(self.fields, exclude_types=(forms.FileInput,))

# ✅ 奖励表单
class RewardForm(forms.ModelForm):
    class Meta:
        model = Reward
        # 根据需要列出所有要在表单中出现的字段
        fields = ['points', 'remark']
        labels = {
            'points': '积分',
            'remark': '备注',
        }
        widgets = {
            'remark': forms.Textarea(attrs={'rows': 3}),
        }

# ✅ 保险表单
class InsuranceForm(forms.ModelForm):
    class Meta:
        model = Insurance
        fields = ['kind', 'join_date', 'number']
        widgets = {
            'join_date': forms.DateInput(attrs={'type': 'date'}),
        }

class DriverPayrollRecordForm(forms.ModelForm):
    class Meta:
        model = DriverPayrollRecord
        # 不在这里写具体字段，由 view 里 modelformset_factory(fields=…) 动态指定
        fields = []
        widgets = {
            'month': forms.DateInput(attrs={'type': 'month'}),
        }