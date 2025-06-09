from django import forms
from .models import DriverDailySales, DriverDailyReport, DriverPayrollRecord, DriverReportImage, Driver, DriverDailyReportItem
from django.forms import inlineformset_factory

class DriverForm(forms.ModelForm):
    class Meta:
        model = Driver
        fields = ['staff_code', 'name', 'phone', 'tax_id']
        widgets = {
            'staff_code': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'tax_id': forms.TextInput(attrs={'class': 'form-control'}),
        }

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