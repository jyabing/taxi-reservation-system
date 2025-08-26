import subprocess, os
from django.db import models
from django.contrib import admin
from rangefilter.filters import DateRangeFilter
from django.http import HttpResponse
from django.urls import path
from django.utils.html import format_html
from .models import DriverDailyReport, DriverDailyReportItem, DriverReportImage
from vehicles.models import Reservation
from django.utils import timezone
from datetime import time, datetime  # 新增

# >>> ADMIN SOFT PREFILL (no-FK) START
from django import forms

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
    readonly_fields = ['has_issue']

@admin.register(DriverDailyReport)
class DriverDailyReportAdmin(admin.ModelAdmin):
    form = DriverDailyReportAdminForm  # ✅ 使用上面的预填表单
    # --- SOFT PREFILL on save (from Vehicles.Reservation) ---
    def save_model(self, request, obj, form, change):
        try:
            self._soft_prefill_from_reservations(obj)
        except Exception:
            # 预填失败不影响正常保存
            pass
        super().save_model(request, obj, form, change)

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
class DriverDailyReportItemAdmin(admin.ModelAdmin):
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
class DriverReportImageAdmin(admin.ModelAdmin):
    list_display = ('driver', 'date', 'uploaded_at', 'image_tag')
    list_filter = ('date',)
    readonly_fields = ('image_tag',)

    def image_tag(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-height:80px;max-width:120px;" />', obj.image.url)
        return "-"
    image_tag.short_description = "图片预览"