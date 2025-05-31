from django import forms
from .models import DailySales, ReportImage, DailyReport

class DailySalesForm(forms.ModelForm):
    class Meta:
        model = DailySales
        fields = ['date', 'cash_amount', 'card_amount', 'ride_count', 'mileage']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
        }

class DailyReportForm(forms.ModelForm):
    class Meta:
        model = DailyReport
        fields = ['is_working_day', 'accident_occurred', 'memo']

class ReportImageForm(forms.ModelForm):
    class Meta:
        model = ReportImage
        fields = ['image']