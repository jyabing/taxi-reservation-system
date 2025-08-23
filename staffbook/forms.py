from django import forms
from .models import (
    Driver, DriverLicense, Accident, Reward, DriverInsurance, DriverPayrollRecord,
    Qualification, Aptitude, Education, Pension,  # 这些视图里会用到
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

def apply_form_control_style(fields, exclude_types=(forms.Select, forms.RadioSelect, forms.CheckboxInput, forms.Textarea)):
    for name in fields:
        if not isinstance(fields[name].widget, exclude_types):
            fields[name].widget.attrs.update({'class': 'form-control'})

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
        widgets = {
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'blood_type': forms.Select(attrs={'class': 'form-select'}),
            'birth_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'hire_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'remark': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }
    nationality = forms.ChoiceField(label="国籍", required=False, choices=[("", "--選択してください--")] + NATIONALITY_CHOICES, widget=forms.Select(attrs={"class": "form-select"}))
    position    = forms.ChoiceField(label="職種", required=False, choices=[("", "--選択してください--")] + POSITION_CHOICES, widget=forms.Select(attrs={"class": "form-select"}))
    employ_type = forms.ChoiceField(label="在職類型", required=False, choices=[("", "--選択してください--")] + EMPLOY_TYPE_CHOICES, widget=forms.Select(attrs={"class": "form-select"}))
    gender      = forms.ChoiceField(label="性別", required=False, choices=[("", "--選択--")] + GENDER_CHOICES, widget=forms.Select(attrs={"class": "form-select"}))
    blood_type  = forms.ChoiceField(label="血液型", required=False, choices=[("", "--選択--")] + BLOOD_CHOICES, widget=forms.Select(attrs={"class": "form-select"}))

class DriverForm(forms.ModelForm):
    class Meta:
        model = Driver
        fields = [
            'driver_code', 'name', 'kana', 'company', 'workplace', 'department',
            'position', 'birth_date', 'gender', 'blood_type', 'resigned_date',
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
            'note': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'license_types': forms.CheckboxSelectMultiple(),
        }
    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('issue_date'):
            self.add_error('issue_date', '交付年月日为必填项')
        return cleaned

class AccidentForm(forms.ModelForm):
    class Meta:
        model = Accident
        fields = ['happened_at', 'description', 'penalty', 'note']
        widgets = {
            'happened_at': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'note': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
        }

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

class RewardForm(forms.ModelForm):
    class Meta:
        model = Reward
        fields = ['points', 'remark']
        widgets = {'remark': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'})}

class DriverInsuranceForm(forms.ModelForm):
    class Meta:
        model = DriverInsurance
        fields = ['kind', 'join_date', 'number']
        widgets = {'join_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})}

class DriverPayrollRecordForm(forms.ModelForm):
    class Meta:
        model = DriverPayrollRecord
        fields = []
        widgets = {'month': forms.DateInput(attrs={'type': 'month', 'class': 'form-control'})}

# 下面这些是视图里会用到的简单表单（保持最小化）
class QualificationForm(forms.ModelForm):
    class Meta:
        model = Qualification
        fields = '__all__'

class AptitudeForm(forms.ModelForm):
    class Meta:
        model = Aptitude
        fields = '__all__'

class EducationForm(forms.ModelForm):
    class Meta:
        model = Education
        fields = '__all__'

class PensionForm(forms.ModelForm):
    class Meta:
        model = Pension
        fields = '__all__'
