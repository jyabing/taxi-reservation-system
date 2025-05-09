from django import forms
from .models import Reservation
from django.utils import timezone
from datetime import datetime, timedelta

class ReservationForm(forms.ModelForm):
    class Meta:
        model = Reservation
        fields = ['vehicle', 'date', 'start_time', 'end_date', 'end_time', 'purpose']

    def clean(self):
        cleaned = super().clean()
        date = cleaned.get('date')
        start = cleaned.get('start_time')
        end_date = cleaned.get('end_date')
        end = cleaned.get('end_time')

        if not all([date, start, end_date, end]):
            return cleaned  # 有缺失字段时先跳过校验

        start_dt = timezone.make_aware(datetime.combine(date, start))
        end_dt = timezone.make_aware(datetime.combine(end_date, end))
        now = timezone.localtime()

        # ✅ 校验：开始时间必须比当前时间晚 30 分钟
        if start_dt < now + timedelta(minutes=30):
            self.add_error('start_time', "开始时间必须晚于当前时间 30 分钟之后。")

        # ✅ 校验：结束时间必须在开始时间之后
        if end_dt <= start_dt:
            self.add_error('end_time', "结束时间必须晚于开始时间。")

        return cleaned
