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

# 放在 DriverDailyReportItemForm 前面
ETC_CHARGE_CHOICES = [
    ("company",  "会社（会社負担）"),
    ("driver",   "ドライバー（立替→後日返還）"),
    ("customer", "お客様（直接精算）"),
]

# --- 日报明细表单 ---
class DriverDailyReportItemForm(forms.ModelForm):
    """
    行级表单（唯一权威）：
    - ETC 负担字段兜底（company）
    - 旧字段 etc_charge_type 同步 ride
    - 非貸切自动清零
    - ★立替(advance) 服务端保护：强制清零売上 / ETC / 貸切
    """

    # 旧字段：隐藏，避免必填报错（兼容旧逻辑）
    etc_charge_type = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
    )

    # 新字段：ETC 负担者（后端提供选项，不靠 JS 造值）
    etc_riding_charge_type = forms.ChoiceField(
        required=False,
        choices=ETC_CHARGE_CHOICES,
        widget=forms.Select(attrs={"class": "form-select form-select-sm etc-riding-charge-select"}),
    )
    etc_empty_charge_type = forms.ChoiceField(
        required=False,
        choices=ETC_CHARGE_CHOICES,
        widget=forms.Select(attrs={"class": "form-select form-select-sm etc-empty-charge-select"}),
    )

    class Meta:
        model = DriverDailyReportItem
        fields = "__all__"

    # ---------- 单字段 clean：保证类型/范围 ----------

    def clean_etc_riding(self):
        try:
            return max(0, int(self.cleaned_data.get("etc_riding") or 0))
        except Exception:
            return 0

    def clean_etc_empty(self):
        try:
            return max(0, int(self.cleaned_data.get("etc_empty") or 0))
        except Exception:
            return 0

    def clean_advance_amount(self):
        # 你的模型如果还没加 advance_amount 字段，这里先保留也没事（字段不存在时 Django 不会调用这个 clean_XXX）
        try:
            return max(0, int(self.cleaned_data.get("advance_amount") or 0))
        except Exception:
            return 0

    def clean_etc_riding_charge_type(self):
        v = (self.cleaned_data.get("etc_riding_charge_type") or "").strip()
        return v if v in {"company", "driver", "customer"} else "company"

    def clean_etc_empty_charge_type(self):
        v = (self.cleaned_data.get("etc_empty_charge_type") or "").strip()
        return v if v in {"company", "driver", "customer"} else "company"

    def clean_etc_charge_type(self):
        # 旧字段也兜底，避免空值导致保存/旧逻辑崩
        v = (self.cleaned_data.get("etc_charge_type") or "").strip()
        return v if v in {"company", "driver", "customer"} else "company"

    # ---------- 核心 clean（唯一一个） ----------

    def save(self, commit=True):
        instance = super().save(commit=False)

        # ETC 写回实例（唯一写入点，保证字段一定有值）
        r_type = (self.cleaned_data.get("etc_riding_charge_type") or "company").strip() or "company"
        e_type = (self.cleaned_data.get("etc_empty_charge_type") or "company").strip() or "company"

        if r_type not in {"company", "driver", "customer"}:
            r_type = "company"
        if e_type not in {"company", "driver", "customer"}:
            e_type = "company"

        instance.etc_riding_charge_type = r_type
        instance.etc_empty_charge_type = e_type
        instance.etc_charge_type = r_type  # 旧字段永远跟 ride 同步

        # ★ 立替(advance) 最终双保险：即使绕过 clean，这里也强制纠正
        if (getattr(instance, "payment_method", "") or "").strip() == "advance":
            if hasattr(instance, "meter_fee"):
                instance.meter_fee = 0
            if hasattr(instance, "etc_riding"):
                instance.etc_riding = 0
            if hasattr(instance, "etc_empty"):
                instance.etc_empty = 0
            instance.etc_riding_charge_type = "company"
            instance.etc_empty_charge_type = "company"
            instance.etc_charge_type = "company"

            if hasattr(instance, "is_charter"):
                instance.is_charter = False
            if hasattr(instance, "charter_amount_jpy"):
                instance.charter_amount_jpy = 0
            if hasattr(instance, "charter_payment_method"):
                # 你的模型如果允许 blank/null，这里清空不会报错
                instance.charter_payment_method = ""

        if commit:
            instance.save()
        return instance


# --- 明细 FormSet（温和兜底：不写 instance，只回退 cleaned_data） ---
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

            # 写回 cleaned_data（温和兜底）
            cd["etc_riding_charge_type"] = ride_charge
            cd["etc_empty_charge_type"] = empty_charge
            cd["etc_charge_type"] = legacy


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