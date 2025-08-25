# dailyreport/forms.py
# 终版：完全移除“车辆分段/segment”相关代码；仅保留日报主表、明细、与可选图片表单。
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
    class Meta:
        model = DriverDailyReport
        exclude = ["driver"]
        fields = "__all__"
        # 如需定制部件请在此追加 widgets / labels
        # widgets = {...}
        # labels = {...}

    # 如需基础校验，可在此添加；保持空实现更稳妥
    def clean(self):
        cleaned = super().clean()
        return cleaned


# --- 日报明细表单 ---
class DriverDailyReportItemForm(forms.ModelForm):
    class Meta:
        model = DriverDailyReportItem
        fields = "__all__"
        # 你项目里已存在的字段（如 is_charter / charter_amount_jpy / charter_payment_method 等）
        # 将自动包含在内；需要自定义展示再在此添加 widgets/labels

    def clean(self):
        cleaned = super().clean()
        # 示例：若存在 charter 字段可做宽松校验（不会抛错）
        amount = cleaned.get("charter_amount_jpy", None)
        is_charter = cleaned.get("is_charter", None)
        if is_charter is False and amount not in (None, "", 0):
            # 不强制报错，仅可选清理；如你要强校验可改为 raise forms.ValidationError(...)
            try:
                cleaned["charter_amount_jpy"] = 0
            except Exception:
                pass
        return cleaned


# --- 明细 FormSet（不含任何分段逻辑） ---
class _BaseReportItemFormSet(BaseInlineFormSet):
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
