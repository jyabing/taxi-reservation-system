import subprocess, os, logging
from django.db import models
from django.utils.encoding import force_str
from django.contrib import admin, messages
import datetime as _dt
from rangefilter.filters import DateRangeFilter
from django.http import HttpResponse
from django.urls import path
from django.utils.html import format_html
from .models import DriverDailyReport, DriverDailyReportItem, DriverReportImage
from vehicles.models import Reservation
from django.utils import timezone
from datetime import time, datetime  # 新增

# ==== BEGIN INSERT: DailyReportAdminPermissionMixin ====
class DailyReportAdminPermissionMixin:
    """
    限制 Django Admin 中 DAILYREPORT 相关模型的可见范围：
    - 超级用户
    - 配车系统管理员 (UserProfile.is_dispatch_admin)
    - 日报管理系统管理员 (UserProfile.is_dailyreport_admin)
    """

    def _has_dailyreport_admin_flag(self, request):
        try:
            user = request.user
            if not getattr(user, "is_authenticated", False):
                return False
            if getattr(user, "is_superuser", False):
                return True
            profile = getattr(user, "userprofile", None)
            if profile is None:
                return False
            return (
                getattr(profile, "is_dispatch_admin", False) or
                getattr(profile, "is_dailyreport_admin", False)
            )
        except Exception:
            return False

    def has_module_permission(self, request):
        return self._has_dailyreport_admin_flag(request)

    def has_view_permission(self, request, obj=None):
        return self._has_dailyreport_admin_flag(request)

    def has_change_permission(self, request, obj=None):
        return self._has_dailyreport_admin_flag(request)

    def has_add_permission(self, request):
        return self._has_dailyreport_admin_flag(request)

    def has_delete_permission(self, request, obj=None):
        return self._has_dailyreport_admin_flag(request)
# ==== END INSERT: DailyReportAdminPermissionMixin ====


# >>> ADMIN SOFT PREFILL (no-FK) START
from django import forms

logger = logging.getLogger(__name__)


def _safe_as_time(val):
    """datetime/time/'HH:MM' -> time；失败返回 None"""
    try:
        if val is None:
            return None
        if hasattr(val, "time") and callable(getattr(val, "time")):
            return val.time()
        if hasattr(val, "hour") and hasattr(val, "minute") and not hasattr(val, "date"):
            return val
        s = str(val).strip()
        if ":" in s:
            h, m = s.split(":", 1)
            h = int(h); m = int(m)
            from datetime import time as _t
            if 0 <= h < 24 and 0 <= m < 60:
                return _t(h, m)
    except Exception:
        pass
    return None


def _guess_prefill_from_reservation(report):
    """
    仅根据 Reservation 计算建议值（不保存 DB）：
      vehicle：当天任一预约的 vehicle
      clock_in：当天预约最早 start_time
      clock_out：当天预约最晚 actual_return；如无，则最晚 end_time
    """
    try:
        user = getattr(getattr(report, "driver", None), "user", None)
        the_date = getattr(report, "date", None)
        if not user or not the_date:
            return None, None, None

        from vehicles.models import Reservation  # 本 app 已存在，无循环导入
        qs = (Reservation.objects
              .filter(driver=user, date=the_date)
              .select_related("vehicle")
              .order_by("start_time"))
        if not qs.exists():
            return None, None, None

        veh = None
        for r in qs:
            if getattr(r, "vehicle", None):
                veh = r.vehicle
                break

        ci = _safe_as_time(getattr(qs.first(), "start_time", None))

        actual_returns = []
        for r in qs:
            ar = _safe_as_time(getattr(r, "actual_return", None))
            if ar:
                actual_returns.append(ar)
        if actual_returns:
            co = sorted(actual_returns)[-1]
        else:
            last = qs.order_by("-end_time").first()
            co = _safe_as_time(getattr(last, "end_time", None))

        return ci, co, veh
    except Exception:
        return None, None, None


class DriverDailyReportAdminForm(forms.ModelForm):
    """后台改页 GET 时，仅给空字段提供 initial（不落库，用户保存才入库）。"""
    class Meta:
        model = DriverDailyReport
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        inst = self.instance


        # 仅在 GET（未绑定）时做预填；POST 时尊重用户输入
        if not self.is_bound and self.instance:
            ci, co, veh = _guess_prefill_from_reservation(self.instance)
            if not getattr(self.instance, "clock_in", None) and ci:
                self.initial.setdefault("clock_in", ci)
            if not getattr(self.instance, "clock_out", None) and co:
                self.initial.setdefault("clock_out", co)
            # vehicle 用 id 作为 initial
            if not getattr(self.instance, "vehicle_id", None) and veh:
                self.initial.setdefault("vehicle", getattr(veh, "id", None))
# <<< ADMIN SOFT PREFILL (no-FK) END


# ✅ 日报主表 + 明细表注册（含内联）
class DriverDailyReportItemInline(admin.TabularInline):
    model = DriverDailyReportItem
    extra = 0
    fields = [
        'ride_time', 'ride_from', 'via', 'ride_to',
        'num_male', 'num_female',
        # ——— 计价与支付（通常一起录入）———
        'meter_fee', 'payment_method',
        # ——— 貸切相关 ———
        'is_charter', 'charter_amount_jpy', 'charter_payment_method',
        # ——— 备注与标记 ———
        'note', 'comment', 'is_flagged', 'has_issue',
    ]
    readonly_fields = ["meter_fee", 'has_issue']


@admin.register(DriverDailyReport)
class DriverDailyReportAdmin(DailyReportAdminPermissionMixin, admin.ModelAdmin):
    form = DriverDailyReportAdminForm
    inlines = [DriverDailyReportItemInline]

    # ===== [BEGIN PATCH] Admin Action: 批量重算当月給与 =====
    actions = ["action_recalc_payroll_current_month"]
    # ===== [END PATCH] Admin Action: 批量重算当月給与 =====

    # ✅ 通杀守门器：所有 POST 值入表单解析前强制变成 str（inline 也覆盖）
    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        if request.method == "POST":
            qd = request.POST  # QueryDict
            if hasattr(qd, "_mutable"):
                old_mutable = qd._mutable
                qd._mutable = True

            for key in list(qd.keys()):
                vals = qd.getlist(key)

                # 1) 扁平：只保留第一个值，避免 formset 字段进来是 list
                raw = vals[0] if vals else ""

                # 2) 规范化为字符串
                try:
                    if isinstance(raw, (_dt.datetime, _dt.date, _dt.time)):
                        norm = raw.isoformat(sep=" ")  # 更易被 Django 解析
                    elif isinstance(raw, (bytes, bytearray)):
                        norm = raw.decode("utf-8", errors="ignore")
                    elif isinstance(raw, str):
                        norm = raw
                    else:
                        # 例如 JS 对象 / Decimal / list 等
                        norm = force_str(raw)
                    if len(vals) > 1:
                        qd.setlist(key, [norm])
                    else:
                        qd[key] = norm
                except Exception as e:
                    logger.exception("POST normalize failed for key=%s, val=%r (%s)", key, raw, type(raw))
                    qd[key] = force_str(raw)

            if hasattr(qd, "_mutable"):
                qd._mutable = old_mutable

        return super().changeform_view(request, object_id, form_url, extra_context)

    

    # --- SOFT PREFILL on save (from Vehicles.Reservation) ---
    def save_model(self, request, obj, form, change):
        try:
            self._soft_prefill_from_reservations(obj)
        except Exception:
            # 预填失败不影响正常保存
            pass
        super().save_model(request, obj, form, change)

    # ===== [BEGIN PATCH] Admin Action: 批量重算当月給与 =====
    @admin.action(description="🧾 批量重算：当月 給与計算用（payroll_*）")
    def action_recalc_payroll_current_month(self, request, queryset):
        """
        选中任意几条日报 → 以“选中中最早日期”的月份作为目标月份
        对该月份内、选中涉及司机的所有日报，批量重算 payroll_* 并写回 DB。
        """
        if not queryset.exists():
            self.message_user(request, "未选中任何日报。", level=messages.WARNING)
            return

        # 以选中中最早日期的那条日报确定目标月份
        first = queryset.order_by("date").first()
        month_start = first.date.replace(day=1)
        if month_start.month == 12:
            next_month = month_start.replace(year=month_start.year + 1, month=1)
        else:
            next_month = month_start.replace(month=month_start.month + 1)

        # 仅对“这次选中涉及到的司机集合”做当月重算（避免误伤全员）
        driver_ids = list(queryset.values_list("driver_id", flat=True).distinct())

        qs = (
            queryset.model.objects
            .filter(driver_id__in=driver_ids, date__gte=month_start, date__lt=next_month)
            .prefetch_related("items")
        )

        updated = 0
        for rpt in qs.iterator():
            self._recalc_one_report_payroll(rpt)
            updated += 1

        self.message_user(
            request,
            f"完成：{month_start.strftime('%Y-%m')} 月 payroll_* 已重算并保存（{updated} 条）。"
        )

    def _recalc_one_report_payroll(self, report):
        """
        第一版：先保证月汇总不再全是 0
        - payroll_bd_sales：按 items 合计 meter_fee +（貸切なら charter_amount_jpy）
        - payroll_total：先用现有 bd 字段（若没填则 0）拼出一个可用合计
        后续 Step B3 我们再把编辑页 dailyreport.js 的口径逐条对齐进来。
        """
        def _i(v):
            try:
                return int(v or 0)
            except Exception:
                return 0

        sales = 0
        for it in report.items.all():
            sales += _i(getattr(it, "meter_fee", 0))
            if getattr(it, "is_charter", False):
                sales += _i(getattr(it, "charter_amount_jpy", 0))

        # 其他拆分先保留现状（避免破坏你现有已保存数据）
        bd_advance = _i(getattr(report, "payroll_bd_advance", 0))
        bd_etc_refund = _i(getattr(report, "payroll_bd_etc_refund", 0))
        bd_os_driver = _i(getattr(report, "payroll_bd_over_short_to_driver", 0))
        # 公司→司机分（你月汇总块里作为“精算补填”显示）
        bd_os_company = _i(getattr(report, "payroll_bd_over_short_to_company", 0))

        payroll_total = sales + bd_advance + bd_etc_refund + bd_os_company

        report.payroll_bd_sales = sales
        report.payroll_total = payroll_total
        report.save(update_fields=["payroll_bd_sales", "payroll_total"])
    # ===== [END PATCH] Admin Action: 批量重算当月給与 =====

    @staticmethod
    def _soft_prefill_from_reservations(obj):
        """
        仅当以下字段为空时，使用预约记录补齐：
        - obj.vehicle
        - obj.clock_in
        - obj.clock_out
        匹配条件：Reservation.driver == obj.driver.user 且 Reservation.date == obj.date
        时间优先：actual_* 优先于 计划 start/end
        """
        from vehicles.models import Reservation
        from django.utils import timezone

        driver_user = getattr(getattr(obj, "driver", None), "user", None)
        if not driver_user or not obj.date:
            return

        qs = Reservation.objects.filter(driver=driver_user, date=obj.date)

        # 车辆
        if not obj.vehicle_id:
            veh = (qs.exclude(vehicle__isnull=True)
                     .values_list("vehicle_id", flat=True)
                     .first())
            if veh:
                obj.vehicle_id = veh

        # 出勤时间（取最早）
        if not obj.clock_in:
            candidates = []
            for ad, st in qs.values_list("actual_departure", "start_time"):
                if ad:
                    t = timezone.localtime(ad).time() if timezone.is_aware(ad) else ad.time()
                    candidates.append(t)
                elif st:
                    candidates.append(st)
            if candidates:
                obj.clock_in = min(candidates)

        # 退勤时间（取最晚）
        if not obj.clock_out:
            candidates = []
            for ar, et in qs.values_list("actual_return", "end_time"):
                if ar:
                    t = timezone.localtime(ar).time() if timezone.is_aware(ar) else ar.time()
                    candidates.append(t)
                elif et:
                    candidates.append(et)
            if candidates:
                obj.clock_out = max(candidates)


    list_display = [
        'driver', 'date', 'vehicle',
        'status', 'has_issue',
        'etc_expected',                 # 应收
        'etc_collected_cash',          # ✅ 新增：现金收取
        'etc_collected_app',           # ✅ 新增：App收取
        'get_etc_collected_total',     # ✅ 新增：实收合计（@property）
        'get_etc_diff',               
        'etc_shortage',                 # ✅ 新增：差额
        'etc_payment_method',
        'get_etc_uncollected',         # 原有未收字段
        'edited_by', 'edited_at',
        #'combined_group'
        'get_combined_groups',         # ✅ 新增：合算组
    ]

    readonly_fields = ['etc_shortage']
    list_filter = ['status', 'has_issue', 'driver',  ('date', DateRangeFilter)]
    search_fields = ('driver__name', 'vehicle__license_plate', 'note')
    inlines = [DriverDailyReportItemInline]
    list_per_page = 20
    ordering = ['-date']
    

    @admin.display(description='ETC未收')
    def get_etc_uncollected(self, obj):
        amt = obj.etc_uncollected or 0
        if amt == 0:
            return format_html('<span style="color: green;">0</span>')
        return format_html('<span style="color: red;">{}</span>', amt)

    @admin.display(description='ETC实收合计')
    def get_etc_collected_total(self, obj):
        return obj.etc_collected_total

    @admin.display(description='ETC差額')
    def get_etc_diff(self, obj):
        expected = obj.etc_expected or 0
        collected = (obj.etc_collected_cash or 0) + (obj.etc_collected_app or 0)
        diff = expected - collected
        if diff == 0:
            color = 'green'
            label = '0（已收齐）'
        elif diff > 0:
            color = 'red'
            label = f'{diff}（未收）'
        else:
            color = 'orange'
            label = f'{diff}（多收？）'
        return format_html('<span style="color: {};">{}</span>', color, label)

    @admin.display(description='合算组')
    def get_combined_groups(self, obj):
        groups = sorted(set(i.combined_group for i in obj.items.all() if i.combined_group))
        if groups:
            return ", ".join(groups)
        return format_html('<span style="color:gray;font-style:italic;">无</span>')

@admin.register(DriverDailyReportItem)
class DriverDailyReportItemAdmin(DailyReportAdminPermissionMixin, admin.ModelAdmin):
    # 列表页显示：加入貸切三字段
    list_display = [
        'report', 'ride_time', 'ride_from', 'ride_to',
        'is_charter', 'charter_amount_jpy', 'charter_payment_method',
        'meter_fee', 'payment_method', 'has_issue',
    ]

    # 过滤器：可按貸切与其支付方式筛选
    list_filter = ['is_charter', 'charter_payment_method', 'payment_method', 'has_issue']

    # 搜索保持不变
    search_fields = ('ride_from', 'ride_to', 'note', 'comment')

    # 详情页字段顺序：把貸切分组放在计价之后
    fields = (
        'report',
        'ride_time', 'ride_from', 'via', 'ride_to',
        'num_male', 'num_female',
        'meter_fee', 'payment_method',
        'is_charter', 'charter_amount_jpy', 'charter_payment_method',
        'note', 'comment', 'is_flagged', 'has_issue',
    )

    # 只读：保留你原来的 meter_fee，并把 has_issue 也设为只读（与 Inline 一致）
    readonly_fields = ['meter_fee', 'has_issue']

@admin.register(DriverReportImage)
class DriverReportImageAdmin(DailyReportAdminPermissionMixin, admin.ModelAdmin):
    list_display = ('driver', 'date', 'uploaded_at', 'image_tag')
    list_filter = ('date',)
    readonly_fields = ('image_tag',)

    def image_tag(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-height:80px;max-width:120px;" />', obj.image.url)
        return "-"
    image_tag.short_description = "图片预览"