# staffbook/forms.py

from django import forms
# ✅ 只从本 app 导入一次（不要再 from staffbook.models 导入自己）
from .models import (
    Driver, DriverLicense,
    Accident, Reward, DriverInsurance, DriverPayrollRecord
)

NATIONALITY_CHOICES = [
    ("日本", "日本"), ("中国", "中国"), ("韓国", "韓国"),
    ("ベトナム", "ベトナム"), ("その他", "その他"),
]
POSITION_CHOICES = [
    ("1", "常時選任運転者"),
    ("2", "運転者"),
    ("3", "職員"),
    ("4", "整備士"),
]
EMPLOY_TYPE_CHOICES = [
    ("1", "正式運転者"),
    ("2", "非常勤運転者"),
    ("3", "退職者"),
]
GENDER_CHOICES = [("男性", "男性"), ("女性", "女性"), ("未設定", "未設定")]
BLOOD_CHOICES  = [("A","A"),("B","B"),("AB","AB"),("O","O")]

# ---- 共通样式工具 ----
def apply_form_control_style(fields, exclude_types=(forms.Select, forms.RadioSelect, forms.CheckboxInput, forms.Textarea)):
    for name, field in fields.items():
        if not isinstance(field.widget, exclude_types):
            field.widget.attrs.update({'class': 'form-control'})

# ---- 基本データ編集（不含従業員番号）----
class DriverBasicEditForm(forms.ModelForm):
    class Meta:
        model = Driver
        fields = [
            'name', 'kana', 'alt_name', 'alt_kana',
            'nationality', 'gender', 'blood_type',
            'birth_date', 'hire_date',
            'company', 'workplace', 'department',
            'position', 'employ_type', 'remark',
        ]

# ---- 司机基础信息（含従業員番号）----
class DriverForm(forms.ModelForm):
    class Meta:
        model = Driver
        fields = [
            'driver_code', 'name', 'kana',
            'company', 'workplace', 'department',
            'position', 'employ_type',            # ✅ 加上 employ_type，配合 clean 使用
            'birth_date', 'gender', 'blood_type', 'resigned_date',
            'hire_date', 'appointment_date', 'create_date', 'remark'
        ]
        widgets = {
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'blood_type': forms.Select(attrs={'class': 'form-select'}),
            'birth_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'hire_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'resigned_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'appointment_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'create_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'remark': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_form_control_style(self.fields)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('employ_type') == '3' and not cleaned.get('resigned_date'):
            self.add_error('resigned_date', '退職者は退職日を入力してください。')
        return cleaned

# ---- 驾照信息 ----
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

# ---- 事故 ----
class AccidentForm(forms.ModelForm):
    class Meta:
        model = Accident
        fields = ['happened_at', 'description', 'penalty', 'note']
        widgets = {
            'happened_at': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 2}),
            'note': forms.Textarea(attrs={'rows': 2}),
        }

# ---- 简版基础信息（仍是 CharField，不做联动查询）----
class DriverBasicForm(forms.ModelForm):
    nationality = forms.ChoiceField(
        label="国籍", required=True,
        choices=[("", "--選択してください--")] + NATIONALITY_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    position = forms.ChoiceField(
        label="職種", required=True,
        choices=[("", "--選択してください--")] + POSITION_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    employ_type = forms.ChoiceField(
        label="在職類型", required=True,
        choices=[("", "--選択してください--")] + EMPLOY_TYPE_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    gender = forms.ChoiceField(
        label="性別", required=False,
        choices=[("", "--選択--")] + GENDER_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    blood_type = forms.ChoiceField(
        label="血液型", required=False,
        choices=[("", "--選択--")] + BLOOD_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = Driver
        fields = [
            "driver_code", "name", "kana",
            "alt_name", "alt_kana",
            "nationality",
            "company", "workplace",             # ✅ 仍为 CharField，保持文本输入
            "department", "position", "employ_type",
            "appointment_date", "hire_date", "create_date",
            "birth_date", "gender", "blood_type",
            "postal_code", "address", "phone_number",
            "photo", "photo_date", "remark",
        ]
        widgets = {
            "birth_date":       forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "hire_date":        forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "appointment_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "create_date":      forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "photo_date":       forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "remark":           forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
        }

# ---- 个人信息 ----
class DriverPersonalInfoForm(forms.ModelForm):
    class Meta:
        model = Driver
        fields = ['photo_date', 'postal_code', 'address', 'phone_number', 'photo']
        widgets = {
            'photo_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'postal_code': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.TextInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
        }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_form_control_style(self.fields, exclude_types=(forms.FileInput,))

# ---- 奖励 / 保险 / 薪资 / 在留 ----
class RewardForm(forms.ModelForm):
    class Meta:
        model = Reward
        fields = ['points', 'remark']
        widgets = {'remark': forms.Textarea(attrs={'rows': 3})}

class DriverInsuranceForm(forms.ModelForm):
    class Meta:
        model = DriverInsurance
        fields = ['kind', 'join_date', 'number']
        widgets = {'join_date': forms.DateInput(attrs={'type': 'date'})}

class DriverPayrollRecordForm(forms.ModelForm):
    class Meta:
        model = DriverPayrollRecord
        fields = []  # 由 view 里的 modelformset_factory 动态指定
        widgets = {'month': forms.DateInput(attrs={'type': 'month'})}

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
        apply_form_control_style(self.fields, exclude_types=(forms.CheckboxInput, forms.ClearableFileInput))
