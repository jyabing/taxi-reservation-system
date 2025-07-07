import calendar
from django import forms
from django.utils import timezone
from datetime import datetime, timedelta
from .models import Reservation
from accounts.models import DriverUser

class ReservationForm(forms.ModelForm):
    class Meta:
        model = Reservation
        fields = ['start_time', 'end_time', 'purpose']
        widgets = {
            'start_time': forms.TextInput(attrs={'class': 'form-control flat-time'}),
            'end_time': forms.TextInput(attrs={'class': 'form-control flat-time'}),
            'purpose': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '用途说明'}),
        }

    def __init__(self, *args, **kwargs):
        # ⛳️ 把 driver 从视图传进来（可选）
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        # ✅ 如果 instance 没有 driver，而外部传进来的 request.user 存在，就先写入 initial
        if not self.instance.pk and self.request:
            self.initial['driver'] = getattr(self.request, 'user', None)

    def clean(self):
        cleaned = super().clean()

        # ✅ 优先用 instance 中的 driver，再回退到 initial 中的 driver
        driver = self.initial.get('driver')
        date = cleaned.get('date')
        end_date = cleaned.get('end_date')
        start_time = cleaned.get('start_time')
        end_time = cleaned.get('end_time')

        if not all([driver, date, end_date, start_time, end_time]):
            return cleaned

        start_dt = datetime.combine(date, start_time)
        end_dt = datetime.combine(end_date, end_time)

        qs = Reservation.objects.filter(
            driver=driver,
            date__lte=end_date,
            end_date__gte=date,
        ).exclude(pk=self.instance.pk)

        for r in qs:
            r_start = datetime.combine(r.date, r.start_time)
            r_end = datetime.combine(r.end_date, r.end_time)

            if start_dt < r_end and end_dt > r_start:
                raise forms.ValidationError("您在该时间段已有预约，不能重叠。")

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

class AdminStatsForm(forms.Form):
    driver = forms.ChoiceField(label="司机", required=False)
    month  = forms.DateField(
        label="统计月份",
        widget=forms.DateInput(attrs={'type': 'month'}),
        initial=timezone.localdate().replace(day=1)
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [('', '—— 全部司机 ——')] + [
            (u.id, u.username) for u in DriverUser.objects.filter(is_staff=False)
        ]
        self.fields['driver'].choices = choices