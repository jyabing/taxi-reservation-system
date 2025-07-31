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
        self.date = kwargs.pop('date', None)
        self.car = kwargs.pop('car', None)
        super().__init__(*args, **kwargs)

        if not self.instance.pk and self.request:
            self.initial['driver'] = getattr(self.request, 'user', None)

    def clean(self):
        cleaned = super().clean()

        driver = self.initial.get('driver')
        date = self.initial.get('date') or getattr(self.instance, 'date', None)
        start_time = cleaned.get('start_time')
        end_time = cleaned.get('end_time')
        car = self.car or getattr(self.instance, 'car', None)

        if not all([driver, date, start_time, end_time]):
            return cleaned

        # 跨日判断
        if end_time < start_time:
            end_date = date + timedelta(days=1)
        else:
            end_date = date

        cleaned['date'] = date
        cleaned['end_date'] = end_date

        start_dt = datetime.combine(date, start_time)
        end_dt = datetime.combine(end_date, end_time)

        # 当前司机是否有冲突
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
            if 0 < gap < 5:
                raise forms.ValidationError("两次预约必须间隔至少 5 小时。")

        # 车辆冲突校验
        if not car:
            raise forms.ValidationError("车辆信息缺失，无法校验是否已被他人预约。")

        car_conflicts = Reservation.objects.filter(
            car=car,
            date__lte=end_date,
            end_date__gte=date,
        ).exclude(pk=self.instance.pk)

        for r in car_conflicts:
            r_start = datetime.combine(r.date, r.start_time)
            r_end = datetime.combine(r.end_date, r.end_time)
            if start_dt < r_end and end_dt > r_start:
                raise forms.ValidationError(
                    f"该车辆在 {r.start_time.strftime('%H:%M')}～{r.end_time.strftime('%H:%M')} 已被 {r.driver} 预约，不能重叠。"
                )

        # 结束时间必须晚于开始时间
        if end_dt <= start_dt:
            raise forms.ValidationError("结束时间必须晚于开始时间。")

        # 时长限制
        duration = (end_dt - start_dt).total_seconds() / 3600
        if duration > 13:
            raise forms.ValidationError(f"预约时长为 {duration:.1f} 小时，超过系统上限（13小时）。")

        # 夜班跨日规则
        if end_date > date:
            if start_time < time(12, 0):
                raise forms.ValidationError("夜班预约的开始时间必须在中午12:00以后。")
            if end_time > time(12, 0):
                raise forms.ValidationError("夜班预约的结束时间必须在次日中午12:00以前。")

        return cleaned # ✅ 一定在 clean() 函数体的末尾缩进内


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


class VehicleStatusForm(forms.ModelForm):
    has_etc = forms.ChoiceField(choices=Car.YES_NO_SELF_CHOICES, label="ETC状态")
    has_oil_card = forms.ChoiceField(choices=Car.YES_NO_SELF_CHOICES, label="油卡状态")
    has_terminal = forms.ChoiceField(choices=Car.YES_NO_CHOICES, label="刷卡机状态")
    has_didi = forms.ChoiceField(choices=Car.YES_NO_SELF_CHOICES, label="Didi状态")
    has_uber = forms.ChoiceField(choices=Car.YES_NO_SELF_CHOICES, label="Uber状态")
    can_enter_hachioji = forms.BooleanField(required=False, label="可进入八条口")

    class Meta:
        model = Car
        fields = [
            'has_etc', 'has_oil_card', 'has_terminal',
            'has_didi', 'has_uber', 'can_enter_hachioji'
        ]


# ✅ 立即在下方添加：
class VehicleNoteForm(forms.ModelForm):
    class Meta:
        model = Car
        fields = ['notes']