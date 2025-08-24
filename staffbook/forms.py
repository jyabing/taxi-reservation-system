from .models import (
    Driver, DriverLicense,
)
from django import forms
from staffbook.models import Accident, Reward, DriverInsurance, DriverPayrollRecord # ✅ 保险、事故、奖励等模型

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
            'driver_code', 'name', 'kana', 'department',
            'position', 'birth_date', 'gender', 'blood_type', 'resigned_date',
            'hire_date', 'appointment_date', 'create_date', 'remark'
        ]
        widgets = {
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'blood_type': forms.Select(attrs={'class': 'form-select'}),
            'birth_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'hire_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'resigned_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),  # ✅ 新增
            'appointment_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'create_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'remark': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_form_control_style(self.fields)

    def clean(self):
        cleaned_data = super().clean()
        employ_type = cleaned_data.get('employ_type')
        resigned_date = cleaned_data.get('resigned_date')

        if employ_type == '3' and not resigned_date:
            self.add_error('resigned_date', '退職者は退職日を入力してください。')

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
            'driver_code', 'name', 'kana', 'department',
            'position', 'employ_type',
            'appointment_date', 'hire_date', 'create_date',
            'birth_date', 'gender', 'blood_type', 'postal_code', 'address',
            'phone_number', 'photo', 'photo_date', 'remark'
        ]

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
class DriverInsuranceForm(forms.ModelForm):
    class Meta:
        model = DriverInsurance
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

# ✅ 签证在留信息表单
class DriverCertificateForm(forms.ModelForm):
    class Meta:
        model = Driver
        fields = [
            'is_foreign', 'nationality', 'residence_status', 'residence_expiry',
            'residence_card_image', 'work_permission_confirmed',
            'has_health_check', 'has_residence_certificate',
            'has_tax_form', 'has_license_copy'
        ]
        widgets = {
            'residence_expiry': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'nationality': forms.TextInput(attrs={'class': 'form-control'}),
            'residence_status': forms.Select(attrs={'class': 'form-select'}),
            'residence_card_image': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_form_control_style(
            self.fields,
            exclude_types=(forms.CheckboxInput, forms.ClearableFileInput)
        )