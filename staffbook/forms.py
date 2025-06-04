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
    PAYMENT_METHOD_CHOICES = [
        ('', '--- 请选择 ---'),
        ('现金', '现金'),
        ('微信', '微信'),
        ('Uber', 'Uber'),
        ('Didi', 'Didi'),
        ('信用卡', '信用卡'),
        ('乘车券', '乘车券'),
        ('扫码', '扫码(PayPay/AuPay/支付宝/微信Pay等)'),
    ]
    payment_method = forms.ChoiceField(choices=PAYMENT_METHOD_CHOICES)

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
            'meter_fee': forms.NumberInput(attrs={'class': 'auto-width-input'}),
            # 'payment_method' 行删掉或注释掉，因为上面用了 ChoiceField
            'note': forms.TextInput(attrs={'class': 'auto-width-input'}),
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