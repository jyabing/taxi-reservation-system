# staffbook/forms.py  —— 直接整文件替换
from django import forms
from django.apps import apps

def _M(name: str):
    """懒加载模型，避免导入顺序问题。"""
    return apps.get_model("staffbook", name)

# 通用：给非选择型控件加 form-control
def apply_form_control_style(fields, exclude_types=(forms.Select, forms.RadioSelect, forms.CheckboxInput, forms.Textarea, forms.FileInput)):
    for key, field in fields.items():
        if not isinstance(field.widget, exclude_types):
            css = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (css + " form-control").strip()

# --------------------------
# 下面都是“工厂函数”，调用时再创建 ModelForm 类
# --------------------------

def DriverFormFactory():
    Driver = _M("Driver")
    class DriverForm(forms.ModelForm):
        class Meta:
            model = Driver
            fields = [
                "driver_code", "name", "kana",
                "company", "workplace", "department",
                "position", "birth_date", "gender", "blood_type", "resigned_date",
                "hire_date", "appointment_date", "create_date", "remark",
            ]
            widgets = {
                "gender": forms.Select(attrs={"class": "form-select"}),
                "blood_type": forms.Select(attrs={"class": "form-select"}),
                "birth_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
                "hire_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
                "resigned_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
                "appointment_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
                "create_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
                "remark": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            }

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            apply_form_control_style(self.fields)

        def clean(self):
            cleaned = super().clean()
            employ_type = cleaned.get("employ_type")
            resigned_date = cleaned.get("resigned_date")
            if employ_type == "3" and not resigned_date:
                self.add_error("resigned_date", "退職者は退職日を入力してください。")
            return cleaned

    return DriverForm


def DriverBasicEditFormFactory():
    Driver = _M("Driver")
    class DriverBasicEditForm(forms.ModelForm):
        class Meta:
            model = Driver
            fields = [
                "name", "kana", "alt_name", "alt_kana",
                "nationality", "gender", "blood_type",
                "birth_date", "hire_date",
                "company", "workplace", "department",
                "position", "employ_type", "remark",
            ]
            widgets = {
                "gender": forms.Select(attrs={"class": "form-select"}),
                "blood_type": forms.Select(attrs={"class": "form-select"}),
                "birth_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
                "hire_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
                "remark": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            }

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            apply_form_control_style(self.fields)

    return DriverBasicEditForm


def DriverPersonalInfoFormFactory():
    Driver = _M("Driver")
    class DriverPersonalInfoForm(forms.ModelForm):
        class Meta:
            model = Driver
            fields = ["photo_date", "postal_code", "address", "phone_number", "photo"]
            widgets = {
                "photo_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
                "postal_code": forms.TextInput(attrs={"class": "form-control"}),
                "address": forms.TextInput(attrs={"class": "form-control"}),
                "phone_number": forms.TextInput(attrs={"class": "form-control"}),
            }

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            apply_form_control_style(self.fields)

    return DriverPersonalInfoForm


def DriverCertificateFormFactory():
    Driver = _M("Driver")
    class DriverCertificateForm(forms.ModelForm):
        class Meta:
            model = Driver
            fields = [
                "is_foreign", "nationality", "residence_status", "residence_expiry",
                "residence_card_image", "work_permission_confirmed",
                "has_health_check", "has_residence_certificate",
                "has_tax_form", "has_license_copy",
            ]
            widgets = {
                "residence_expiry": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
                "nationality": forms.TextInput(attrs={"class": "form-control"}),
                "residence_status": forms.Select(attrs={"class": "form-select"}),
                "residence_card_image": forms.ClearableFileInput(attrs={"class": "form-control"}),
            }

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            apply_form_control_style(self.fields)

    return DriverCertificateForm


def DriverLicenseFormFactory():
    DriverLicense = _M("DriverLicense")
    class DriverLicenseForm(forms.ModelForm):
        class Meta:
            model = DriverLicense
            fields = [
                "photo", "license_number", "issue_date", "expiry_date",
                "date_acquired_a", "date_acquired_b", "date_acquired_c",
                "license_types", "license_conditions", "note",
            ]
            widgets = {
                "license_number": forms.TextInput(attrs={"class": "form-control"}),
                "license_conditions": forms.TextInput(attrs={"class": "form-control"}),
                "note": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
                "issue_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
                "expiry_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
                "date_acquired_a": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
                "date_acquired_b": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
                "date_acquired_c": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
                "license_types": forms.CheckboxSelectMultiple(),
            }

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            apply_form_control_style(self.fields)

        def clean(self):
            cleaned = super().clean()
            if not cleaned.get("issue_date"):
                self.add_error("issue_date", "交付年月日为必填项")
            return cleaned

    return DriverLicenseForm


def AccidentFormFactory():
    Accident = _M("Accident")
    class AccidentForm(forms.ModelForm):
        class Meta:
            model = Accident
            fields = ["happened_at", "description", "penalty", "note"]
            widgets = {
                "happened_at": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
                "description": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
                "note": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            }
    return AccidentForm


def RewardFormFactory():
    Reward = _M("Reward")
    class RewardForm(forms.ModelForm):
        class Meta:
            model = Reward
            fields = ["points", "remark"]
            widgets = {
                "remark": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
            }
    return RewardForm


def DriverInsuranceFormFactory():
    DriverInsurance = _M("DriverInsurance")
    class DriverInsuranceForm(forms.ModelForm):
        class Meta:
            model = DriverInsurance
            fields = ["kind", "join_date", "number"]
            widgets = {"join_date": forms.DateInput(attrs={"type": "date", "class": "form-control"})}
    return DriverInsuranceForm


def DriverPayrollRecordFormFactory():
    DriverPayrollRecord = _M("DriverPayrollRecord")
    class DriverPayrollRecordForm(forms.ModelForm):
        class Meta:
            model = DriverPayrollRecord
            fields = []  # 具体字段由 view 里的 modelformset_factory(fields=...) 指定
            widgets = {"month": forms.DateInput(attrs={"type": "month", "class": "form-control"})}
    return DriverPayrollRecordForm
