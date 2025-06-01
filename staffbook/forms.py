from django import forms
from .models import DriverDailySales, DriverDailyReport, DriverPayrollRecord, DriverReportImage, Driver

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
        fields = ['date', 'time', 'fare', 'payment_method', 'note']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'time': forms.TextInput(attrs={'placeholder': '例：08:30-09:00'}),
            'payment_method': forms.TextInput(attrs={'placeholder': '现金/微信/Uber等'}),
            'note': forms.Textarea(attrs={'rows':2}),
        }

class DriverReportImageForm(forms.ModelForm):
    class Meta:
        model = DriverReportImage
        fields = ['image']