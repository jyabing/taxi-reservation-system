from django import forms
from django.utils import timezone
from datetime import datetime, timedelta
from .models import Reservation

class ReservationForm(forms.ModelForm):
    class Meta:
        model = Reservation
        fields = ['date', 'start_time', 'end_date', 'end_time', 'purpose']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'text', 'class': 'flat-date'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'flat-date'}),
            'start_time': forms.TimeInput(attrs={'type': 'time', 'class': 'flat-time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'flat-time'}),
            'purpose': forms.TextInput(attrs={'placeholder': '用途说明'}),
        }

    def clean(self):
        cleaned = super().clean()
        date = cleaned.get('date')
        start = cleaned.get('start_time')
        end_date = cleaned.get('end_date')
        end = cleaned.get('end_time')

        if not all([date, start, end_date, end]):
            return cleaned

        start_dt = timezone.make_aware(datetime.combine(date, start))
        end_dt = timezone.make_aware(datetime.combine(end_date, end))
        now = timezone.localtime()

        if start_dt < now + timedelta(minutes=30):
            self.add_error('start_time', "开始时间必须晚于当前时间 30 分钟之后。")

        if end_dt <= start_dt:
            self.add_error('end_time', "结束时间必须晚于开始时间。")

        return cleaned
