import calendar
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
        driver = self.instance.driver or self.initial.get('driver')
        date = cleaned.get('date')
        end_date = cleaned.get('end_date')
        start_time = cleaned.get('start_time')
        end_time = cleaned.get('end_time')

        if not all([driver, date, end_date, start_time, end_time]):
            return cleaned

        # 1. 本次预约的开始/结束 datetime
        start_dt = datetime.combine(date, start_time)
        end_dt   = datetime.combine(end_date, end_time)

        # 2. 找出同司机当日所有「已预约」和「已出库」记录
        qs = Reservation.objects.filter(
            driver=driver,
            date__lte=end_date,
            end_date__gte=date,
        ).exclude(pk=self.instance.pk)

        # 3. 重叠判断
        for r in qs:
            r_start = datetime.combine(r.date, r.start_time)
            r_end   = datetime.combine(r.end_date, r.end_time)
            # 时间段重叠
            if start_dt < r_end and end_dt > r_start:
                raise forms.ValidationError("您在该时间段已有预约，不能重叠。")

            # 10 小时冷却判断
            # 如果 new_start 在旧 end 的后 10h 之前，报错
            gap = (start_dt - r_end).total_seconds() / 3600
            if 0 < gap < 10:
                raise forms.ValidationError("两次预约必须间隔至少 10 小时。")

        return cleaned

class MonthForm(forms.Form):
    month = forms.DateField(
        label="统计月份",
        widget=forms.DateInput(attrs={'type': 'month'}),
        input_formats=['%Y-%m'],    # ← 新增：告诉它识别 YYYY-MM 格式
    )