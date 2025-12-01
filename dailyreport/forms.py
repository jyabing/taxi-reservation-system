# dailyreport/forms.py
from __future__ import annotations
import openpyxl
from django.urls import reverse


from django.utils.encoding import force_str
import datetime as _dt

from django import forms
from django.forms import inlineformset_factory, BaseInlineFormSet
from carinfo.models import Car

from .models import DriverDailyReport, DriverDailyReportItem, DriverReportImage, DriverDailyReport


# --- 可选图片表单（若模型不存在也不报错） ---
try:
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
            "etc_rider_payer": forms.Select(
                attrs={"class": "form-select form-select-sm js-etc-rider-payer"}
            ),
            "etc_empty_card": forms.Select(
                attrs={"class": "form-select form-select-sm js-empty-etc-card"}
            ),  # ✅ 已有
            # ✅ 新增：司机負担ETC，作为 hidden 字段
            "etc_driver_cost": forms.HiddenInput(),

            # ===== [BEGIN PATCH] 回程費字段 widget =====
            "etc_return_fee_claimed": forms.NumberInput(
                attrs={
                    "class": "form-control form-control-sm text-end js-return-fee-claimed",
                    "min": 0,
                    "step": 1,
                    "inputmode": "numeric",
                    "pattern": "[0-9]*",
                }
            ),
            "etc_return_fee_method": forms.Select(
                attrs={
                    "class": "form-select form-select-sm js-return-fee-method",
                }
            ),
            # ===== [END PATCH] =====
        }

    def clean(self):
        cleaned = super().clean()
        co = cleaned.get("clock_out")
        if co:
            cleaned["unreturned_flag"] = False
        return cleaned


# ===== BEGIN IMPORT_EXTERNAL_DAILYREPORT_FORM M1 =====
class ExternalDailyReportImportForm(forms.Form):
    """
    外部日報データ(Excel) 取込用フォーム
    会社責任者がファイルをアップロードするだけ。
    """
    file = forms.FileField(
        label="外部日報データファイル（Excel）",
        help_text="拡張子 .xlsx のファイルを指定してください。"
    )

    def clean_file(self):
        f = self.cleaned_data["file"]
        name = f.name.lower()
        if not (name.endswith(".xlsx") or name.endswith(".xlsm")):
            raise forms.ValidationError(
                "Excel ファイル(.xlsx / .xlsm)を指定してください。"
            )
        return f
# ===== END IMPORT_EXTERNAL_DAILYREPORT_FORM M1 =====


# --- 日报明细表单 ---
class DriverDailyReportItemForm(forms.ModelForm):
    """
    目的：
    - 先保证『能保存』，不再因为 etc_xxx_charge_type 报错；
    - 乘车/空车 ETC 负担类型确实写入模型字段；
    - 旧字段 etc_charge_type 始终跟乘车负担同步，方便旧逻辑继续工作。
    """

    # 旧字段：显式覆盖成 CharField(required=False) + HiddenInput
    etc_charge_type = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
    )

    # 新字段：Select
    etc_riding_charge_type = forms.CharField(
        required=False,
        widget=forms.Select(
            attrs={"class": "form-select form-select-sm etc-riding-charge-select"}
        ),
    )
    etc_empty_charge_type = forms.CharField(
        required=False,
        widget=forms.Select(
            attrs={"class": "form-select form-select-sm etc-empty-charge-select"}
        ),
    )

    class Meta:
        model = DriverDailyReportItem
        fields = "__all__"
        widgets = {
            # "etc_charge_type": forms.HiddenInput(),  # 上面字段定义已覆盖
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 金额默认 0（防止 None）
        if "etc_riding" in self.fields:
            self.fields["etc_riding"].initial = getattr(self.instance, "etc_riding", 0) or 0
        if "etc_empty" in self.fields:
            self.fields["etc_empty"].initial = getattr(self.instance, "etc_empty", 0) or 0

        # 旧字段 -> 默认立替者
        default_charge = "company"
        legacy = getattr(self.instance, "etc_charge_type", None) or default_charge

        # 乘车负担：实例值 > 旧字段 > 默认 company
        if "etc_riding_charge_type" in self.fields:
            initial_val = (
                getattr(self.instance, "etc_riding_charge_type", None)
                or legacy
                or default_charge
            )
            field = self.fields["etc_riding_charge_type"]
            field.initial = initial_val
            # ⭐ 把服务器端的初始值写到 data-initial，给前端 JS 使用
            field.widget.attrs["data-initial"] = initial_val or ""

        # 空车负担：实例值 > 默认 company
        if "etc_empty_charge_type" in self.fields:
            initial_val = (
                getattr(self.instance, "etc_empty_charge_type", None)
                or default_charge
            )
            field = self.fields["etc_empty_charge_type"]
            field.initial = initial_val
            field.widget.attrs["data-initial"] = initial_val or ""

        # 旧字段初始
        if "etc_charge_type" in self.fields:
            self.fields["etc_charge_type"].initial = legacy

    # —— 金额：非负整数 —— #
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

    # —— 负担类型：空/乱值一律回退到 'company' —— #
    def clean_etc_riding_charge_type(self):
        v = (self.cleaned_data.get("etc_riding_charge_type") or "").strip()
        if not v:
            return "company"
        allow = {"company", "driver", "customer"}
        return v if v in allow else "company"

    def clean_etc_empty_charge_type(self):
        v = (self.cleaned_data.get("etc_empty_charge_type") or "").strip()
        if not v:
            return "company"
        allow = {"company", "driver", "customer"}
        return v if v in allow else "company"

    # —— 旧字段：保证永远有值，不再报“必填” —— #
    def clean_etc_charge_type(self):
        """
        兼容老字段：如果没填，就用乘车负担或 'company'
        """
        v = (self.cleaned_data.get("etc_charge_type") or "").strip()
        if not v:
            v = (self.cleaned_data.get("etc_riding_charge_type") or "").strip()
        if not v:
            v = "company"
        return v

    def clean(self):
        cleaned = super().clean()

        # 非貸切 → charter 金额清零（保持你原来的逻辑）
        if cleaned.get("is_charter") is False and cleaned.get("charter_amount_jpy") not in (
            None,
            "",
            0,
        ):
            cleaned["charter_amount_jpy"] = 0

        # 旧字段始终同步为“乘车负担”（再兜底 company）
        cleaned["etc_charge_type"] = (
            cleaned.get("etc_riding_charge_type")
            or cleaned.get("etc_charge_type")
            or "company"
        )

        return cleaned

    # === 关键补丁：强制把表单里的值写回模型字段，再同步旧字段 ===
    def save(self, commit=True):
        """
        保证：
        - etc_riding_charge_type / etc_empty_charge_type 一定写入实例
        - etc_charge_type 跟乘车负担保持一致（旧逻辑仍可用）
        """
        instance = super().save(commit=False)

        r_type = self.cleaned_data.get("etc_riding_charge_type") or "company"
        e_type = self.cleaned_data.get("etc_empty_charge_type") or "company"

        instance.etc_riding_charge_type = r_type
        instance.etc_empty_charge_type = e_type
        instance.etc_charge_type = r_type or e_type or "company"

        if commit:
            instance.save()
        return instance



# --- 明细 FormSet（不含任何分段逻辑） ---
class _BaseReportItemFormSet(BaseInlineFormSet):
    def _should_delete_form(self, form):
        # ★ 勾了 DELETE 就判定为删除
        return bool(getattr(form, "cleaned_data", {}) and form.cleaned_data.get("DELETE"))

    def clean(self):
        """
        温和版校验：
          - 不再因为 ETC 负担字段空/乱值而整套表单报错；
          - 自动把无效值回退为 'company'；
          - 同时把旧字段 etc_charge_type 跟 ride 的负担同步。
        """
        super().clean()

        allow = {"company", "driver", "customer"}

        for form in self.forms:
            cd = getattr(form, "cleaned_data", None)
            if not cd:
                continue
            # 被标记删除的行不处理
            if self.can_delete and cd.get("DELETE"):
                continue

            ride_charge = (cd.get("etc_riding_charge_type") or "").strip()
            empty_charge = (cd.get("etc_empty_charge_type") or "").strip()
            legacy = (cd.get("etc_charge_type") or "").strip()

            if ride_charge not in allow:
                ride_charge = "company"
            if empty_charge not in allow:
                empty_charge = "company"
            if legacy not in allow:
                legacy = ride_charge or "company"

            # 写回 cleaned_data
            cd["etc_riding_charge_type"] = ride_charge
            cd["etc_empty_charge_type"] = empty_charge
            cd["etc_charge_type"] = legacy

            # 再同步到 instance，避免保存时报错
            inst = form.instance
            if inst is not None:
                inst.etc_riding_charge_type = ride_charge
                inst.etc_empty_charge_type = empty_charge
                if hasattr(inst, "etc_charge_type"):
                    inst.etc_charge_type = legacy

        # ⚠️ 这里不要再 raise ValidationError("空車ETC負担の無効値") 之类的东西
        # 如需“至少 1 条明细”，在这里单独加判断即可



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