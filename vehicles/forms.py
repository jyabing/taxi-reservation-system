import calendar
from django import forms
from django.utils import timezone
from datetime import datetime, timedelta
from .models import Reservation
from accounts.models import DriverUser
from carinfo.models import Car

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
        self.request = kwargs.pop('request', None)
        self.date = kwargs.pop('date', None)  # ✅ 从视图传入 date
        super().__init__(*args, **kwargs)

        if not self.instance.pk and self.request:
            self.initial['driver'] = getattr(self.request, 'user', None)

    def clean(self):
        cleaned = super().clean()

        driver = self.initial.get('driver')
        date = self.initial.get('date') or getattr(self.instance, 'date', None)
        start_time = cleaned.get('start_time')
        end_time = cleaned.get('end_time')

        if not all([driver, date, start_time, end_time]):
            return cleaned  # 不足信息则不做校验

        # ✅ 判断是否跨日
        if end_time < start_time:
            end_date = date + timedelta(days=1)
        else:
            end_date = date

        # ✅ 存入 cleaned_data 中，供后续保存使用
        cleaned['date'] = date
        cleaned['end_date'] = end_date

        start_dt = datetime.combine(date, start_time)
        end_dt = datetime.combine(end_date, end_time)

        # ✅ 查找重叠时间的预约
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

            # ✅ 间隔小于 10 小时
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


class VehicleNoteForm(forms.ModelForm):
    class Meta:
        model = Car
        fields = ['notes']
        widgets = {
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 6}),
        }
        labels = {
            'notes': '备注信息（如：ETC有无、油卡状态、刷卡机型号等）',
        }