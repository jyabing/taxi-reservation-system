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
        # ⚠️ Django 不允许同时设置 fields="__all__" 和 exclude
        # 二选一；如果想排除 driver：
        exclude = ["driver"]          # ✅ 推荐只保留这个
        # fields = "__all__"

        widgets = {
            "etc_rider_payer": forms.Select(attrs={"class": "form-select form-select-sm js-etc-rider-payer"}),
            "etc_empty_card": forms.Select(attrs={"class": "form-select form-select-sm js-empty-etc-card"}),  # ✅ 新增
        }

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
        # 最不破坏的方式：全部字段
        fields = "__all__"
        widgets = {
            "is_pending": forms.CheckboxInput(attrs={"class": "pending-checkbox"}),
            "is_charter": forms.CheckboxInput(attrs={"class": "charter-checkbox"}),
            "is_flagged": forms.CheckboxInput(attrs={"class": "mark-checkbox"}),

            "etc_riding": forms.NumberInput(attrs={
                "class": "form-control form-control-sm etc-riding-input text-end",
                "min": 0, "step": 1, "inputmode": "numeric", "placeholder": "乗車ETC"
            }),
            "etc_empty": forms.NumberInput(attrs={
                "class": "form-control form-control-sm etc-empty-input text-end",
                "min": 0, "step": 1, "inputmode": "numeric", "placeholder": "空車ETC"
            }),

            "etc_riding_charge_type": forms.Select(attrs={
                "class": "form-select form-select-sm etc-riding-charge-select"
            }),
            "etc_empty_charge_type": forms.Select(attrs={
                "class": "form-select form-select-sm etc-empty-charge-select"
            }),

            # 旧字段（若模型仍在）继续隐藏，兼容历史
            "etc_charge_type": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 两个“负担”字段不是必填
        for key in ("etc_riding_charge_type", "etc_empty_charge_type"):
            if key in self.fields:
                self.fields[key].required = False

        # 金额默认 0
        self.fields["etc_riding"].initial = getattr(self.instance, "etc_riding", 0) or 0
        self.fields["etc_empty"].initial  = getattr(self.instance, "etc_empty", 0)  or 0

        # 负担默认：优先实例 → 旧字段 → company
        default_charge = "company"
        legacy = getattr(self.instance, "etc_charge_type", None) or default_charge

        if "etc_riding_charge_type" in self.fields:
            self.fields["etc_riding_charge_type"].initial = (
                getattr(self.instance, "etc_riding_charge_type", None) or legacy or default_charge
            )
        if "etc_empty_charge_type" in self.fields:
            self.fields["etc_empty_charge_type"].initial = (
                getattr(self.instance, "etc_empty_charge_type", None) or default_charge
            )

        # 旧字段隐藏域也给默认（如库里有非空约束）
        if "etc_charge_type" in self.fields:
            self.fields["etc_charge_type"].initial = legacy

    # —— 强化校验为非负整数 —— #
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

    # —— 两个负担字段：空值自动回落到 'company'，并做枚举校验 —— #
    def clean_etc_riding_charge_type(self):
        v = (self.cleaned_data.get("etc_riding_charge_type") or "").strip() or "company"
        choices = dict(DriverDailyReportItem.ETC_CHARGE_CHOICES)
        return v if v in choices else "company"

    def clean_etc_empty_charge_type(self):
        v = (self.cleaned_data.get("etc_empty_charge_type") or "").strip() or "company"
        choices = dict(DriverDailyReportItem.ETC_CHARGE_CHOICES)
        return v if v in choices else "company"

    def clean(self):
        cleaned = super().clean()

        # 非貸切 → charter 金额温和清零（不抛错）
        amt = cleaned.get("charter_amount_jpy", None)
        if cleaned.get("is_charter") is False and amt not in (None, "", 0):
            cleaned["charter_amount_jpy"] = 0

        # 兼容：如旧字段仍在，把它同步为“乘车负担”
        if "etc_charge_type" in self.fields:
            cleaned["etc_charge_type"] = cleaned.get("etc_riding_charge_type", "company") or "company"

        # （可选）金额为 0 时强制负担回 company，统一口径
        # if (cleaned.get("etc_riding") or 0) == 0:
        #     cleaned["etc_riding_charge_type"] = "company"
        # if (cleaned.get("etc_empty") or 0) == 0:
        #     cleaned["etc_empty_charge_type"] = "company"

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