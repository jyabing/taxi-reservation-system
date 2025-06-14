from django import forms
from .models import DriverDailySales, DriverDailyReport, DriverPayrollRecord, DriverReportImage, Driver, DriverDailyReportItem, DriverLicense, LicenseType, Accident
from django.forms import inlineformset_factory

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
        for field in self.fields:
            # 统一样式
            if not isinstance(self.fields[field].widget, (forms.Select, forms.RadioSelect, forms.CheckboxInput, forms.Textarea)):
                self.fields[field].widget.attrs.update({'class': 'form-control'})

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

class AccidentForm(forms.ModelForm):
    class Meta:
        model = Accident
        fields = ['happened_at', 'description', 'penalty', 'note']

class DriverBasicForm(forms.ModelForm):
    class Meta:
        model = Driver
        fields = [
            'driver_code', 'name', 'kana', 'company', 'workplace', 'department',
            'position', 'employ_type',  # ←必须有employ_type
            'appointment_date', 'hire_date', 'create_date',
            'birth_date', 'gender', 'blood_type', 'postal_code', 'address',
            'phone_number', 'photo', 'photo_date', 'remark'
        ]














class DriverDailySalesForm(forms.ModelForm):
    class Meta:
        model = DriverDailySales
        fields = ['date', 'cash_amount', 'card_amount', 'ride_count', 'mileage']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
        }

class DriverDailyReportForm(forms.ModelForm):
    class Meta:
        model = DriverDailyReport
        fields = ['date', 'note']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'note': forms.Textarea(attrs={'rows':2}),
        }

class DriverDailyReportItemForm(forms.ModelForm):
    class Meta:
        model = DriverDailyReportItem
        fields = [
            'ride_time', 'ride_from', 'via', 'ride_to',
            'num_male', 'num_female', 'meter_fee',
            'payment_method', 'note'
        ]
        widgets = {
            'ride_time': forms.TextInput(attrs={'class': 'ride-time-input auto-width-input', 'placeholder': '例：08:30-09:00'}),
            'ride_from': forms.TextInput(attrs={'class': 'auto-width-input'}),
            'via': forms.TextInput(attrs={'class': 'auto-width-input'}),
            'ride_to': forms.TextInput(attrs={'class': 'auto-width-input'}),
            'num_male': forms.NumberInput(attrs={'class': 'auto-width-input'}),
            'num_female': forms.NumberInput(attrs={'class': 'auto-width-input'}),
            # 关键：这里要多加一个 class
            'meter_fee': forms.NumberInput(attrs={'class': 'meter-fee-input auto-width-input'}),
            'note': forms.TextInput(attrs={'class': 'auto-width-input'}),
            'payment_method': forms.Select(attrs={'class': 'payment-method-select'}),
        }

ReportItemFormSet = inlineformset_factory(
    DriverDailyReport,
    DriverDailyReportItem,
    form=DriverDailyReportItemForm,
    extra=1,
    can_delete=True,
    max_num=40,
)

class DriverReportImageForm(forms.ModelForm):
    class Meta:
        model = DriverReportImage
        fields = ['image']


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