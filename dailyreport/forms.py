# dailyreport/forms.py
# 终版：完全移除“车辆分段/segment”相关代码；仅保留日报主表、明细、与可选图片表单。
from __future__ import annotations

from django.utils.encoding import force_str
import datetime as _dt

from django import forms
from django.forms import inlineformset_factory, BaseInlineFormSet
from carinfo.models import Car

from .models import DriverDailyReport, DriverDailyReportItem

# --- 可选图片表单（若模型不存在也不报错） ---
try:
    from .models import DriverReportImage  # 若你的项目没有该模型，会进入 except 分支

    class DriverReportImageForm(forms.ModelForm):
        class Meta:
            model = DriverReportImage
            fields = "__all__"
except Exception:
    class DriverReportImageForm(forms.Form):
        image = forms.ImageField(required=False)
        note = forms.CharField(required=False, max_length=255)


# --- 日报主表单 ---
class DriverDailyReportForm(forms.ModelForm):
    vehicle = forms.ModelChoiceField(
        queryset=Car.objects.all().order_by('name'),
        required=False
    )
    # 新增：未完成入库手续（非模型字段）
    unreturned_flag = forms.BooleanField(
        required=False,
        label="未完成入库手续"
    )

    class Meta:
        model = DriverDailyReport
        exclude = ["driver"]
        fields = "__all__"   # 保持你的原样

    def clean(self):
        cleaned = super().clean()
        # 若用户输入了退勤时间，则把“未完成入库手续”强制视为未勾选
        co = cleaned.get("clock_out")
        if co:
            cleaned["unreturned_flag"] = False
        return cleaned


# --- 日报明细表单 ---
class DriverDailyReportItemForm(forms.ModelForm):
    class Meta:
        model = DriverDailyReportItem
        fields = "__all__"
        widgets = {
            # 你原有的三个复选框样式
            "is_pending": forms.CheckboxInput(attrs={"class": "pending-checkbox"}),
            "is_charter": forms.CheckboxInput(attrs={"class": "charter-checkbox"}),
            "is_flagged": forms.CheckboxInput(attrs={"class": "mark-checkbox"}),

            # === 行级ETC：现在改成可见控件（整数 + 下拉） ===
            "etc_riding": forms.NumberInput(attrs={
                "class": "form-control form-control-sm etc-riding-input text-end",
                "min": 0, "step": 1, "inputmode": "numeric", "placeholder": "乗車ETC"
            }),
            "etc_empty": forms.NumberInput(attrs={
                "class": "form-control form-control-sm etc-empty-input text-end",
                "min": 0, "step": 1, "inputmode": "numeric", "placeholder": "空車ETC"
            }),
            "etc_charge_type": forms.Select(attrs={
                "class": "form-select form-select-sm etc-charge-type-select"
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 兜底默认，防止 NULL 触发 NOT NULL 约束
        self.fields["etc_riding"].initial = self.instance.etc_riding or 0
        self.fields["etc_empty"].initial = self.instance.etc_empty or 0
        self.fields["etc_charge_type"].initial = self.instance.etc_charge_type or "company"

    # —— 强化校验为非负整数/合法枚举 —— #
    def clean_etc_riding(self):
        v = self.cleaned_data.get("etc_riding")
        try:
            v = int(v or 0)
        except Exception:
            v = 0
        return max(0, v)

    def clean_etc_empty(self):
        v = self.cleaned_data.get("etc_empty")
        try:
            v = int(v or 0)
        except Exception:
            v = 0
        return max(0, v)

    def clean_etc_charge_type(self):
        v = (self.cleaned_data.get("etc_charge_type") or "company").strip()
        if v not in dict(DriverDailyReportItem.ETC_CHARGE_CHOICES):
            v = "company"
        return v

    def clean(self):
        cleaned = super().clean()
        # 温和一致性处理：若非貸切，清零 charter_amount_jpy（不抛错）
        amt = cleaned.get("charter_amount_jpy", None)
        is_charter = cleaned.get("is_charter", None)
        if is_charter is False and amt not in (None, "", 0):
            try:
                cleaned["charter_amount_jpy"] = 0
            except Exception:
                pass
        return cleaned


# --- 明细 FormSet（不含任何分段逻辑） ---
class _BaseReportItemFormSet(BaseInlineFormSet):
    def _should_delete_form(self, form):
        # ★ 勾了 DELETE 就判定为删除
        return bool(getattr(form, "cleaned_data", {}) and form.cleaned_data.get("DELETE"))

    
    def clean(self):
        super().clean()
        # 如需“至少 1 条明细”强校验，取消注释：
        # count = sum(
        #     1 for f in self.forms
        #     if getattr(f, "cleaned_data", None)
        #     and not f.cleaned_data.get("DELETE", False)
        # )
        # if count == 0:
        #     raise forms.ValidationError("请至少填写一条日报明细。")


ReportItemFormSet = inlineformset_factory(
    parent_model=DriverDailyReport,
    model=DriverDailyReportItem,
    form=DriverDailyReportItemForm,
    formset=_BaseReportItemFormSet,
    extra=0,
    can_delete=True,
)

# 兼容旧代码里对 RequiredReportItemFormSet 的引用
RequiredReportItemFormSet = ReportItemFormSet




class _NormalizePostMixin:
    """把 self.data 里所有值强制规范为字符串，避免 fromisoformat 类型错误。"""
    def _normalize_querydict(self):
        if not hasattr(self, "data") or self.data is None:
            return
        qd = self.data
        try:
            qd = qd.copy()  # QueryDict -> 可写
        except Exception:
            return
        for key in list(qd.keys()):
            vals = qd.getlist(key)
            raw = vals[0] if vals else ""
            # 统一为字符串
            if isinstance(raw, (_dt.datetime, _dt.date, _dt.time)):
                norm = raw.isoformat(sep=" ")
            elif isinstance(raw, (bytes, bytearray)):
                norm = raw.decode("utf-8", errors="ignore")
            elif isinstance(raw, str):
                norm = raw
            else:
                norm = force_str(raw)
            qd.setlist(key, [norm])
        self.data = qd

class DriverDailyReportAdminForm(_NormalizePostMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 🚧 在字段解析前就把 data 里的值全转成 str
        self._normalize_querydict()

    class Meta:
        from .models import DriverDailyReport
        model = DriverDailyReport
        fields = "__all__"



class NormalizeInlineFormSet(_NormalizePostMixin, BaseInlineFormSet):
    def __init__(self, *args, **kwargs):
        # 先规范化，再交给父类去解析
        if args and hasattr(args[0], "copy"):
            data = args[0].copy()
            # 对整个 formset 的 POST 做一次通杀
            self.data = data  # 暂存给 mixin 用
        else:
            self.data = None
        self._normalize_querydict()
        if self.data is not None:
            args = (self.data, *args[1:])
        super().__init__(*args, **kwargs)