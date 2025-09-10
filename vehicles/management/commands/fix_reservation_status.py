# vehicles/management/commands/fix_reservation_status.py
from django.core.management.base import BaseCommand
from django.apps import apps
from django.contrib.auth import get_user_model
from django.db.models import Q
from datetime import date

class Command(BaseCommand):
    help = (
        "Batch fix reservations: change status from 'cancel' to 'reserved' and set approved flags.\n"
        "Default: only future dates (>= today), and only where status='cancel'.\n"
        "Use --dry-run to preview (default True)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", default=True,
                            help="Preview changes without saving (default: True)")
        parser.add_argument("--commit", action="store_true", default=False,
                            help="Actually write changes (overrides --dry-run).")
        parser.add_argument("--include-past", action="store_true", default=False,
                            help="Include past-dated reservations (date < today).")
        parser.add_argument("--ids", nargs="+", type=int, default=None,
                            help="Specific reservation IDs to include (space-separated).")
        parser.add_argument("--vehicle", type=str, default=None,
                            help="Filter by vehicle id/code/plate (best-effort; resolves to IDs first).")
        parser.add_argument("--driver", type=str, default=None,
                            help="Filter by driver (username/code/name; resolves to IDs first).")
        parser.add_argument("--status-from", type=str, default="cancel",
                            help="Only touch reservations with this status. Default: cancel")
        parser.add_argument("--status-to", type=str, default="reserved",
                            help="Set status to this value. Default: reserved")

    # ---------- helpers: resolve FK ids without joins ----------
    def resolve_vehicle_ids(self, needle: str):
        """
        Return a set of Vehicle IDs matching `needle`.
        Tries exact id, then common fields (code/number/plate...) INSIDE Vehicle table.
        """
        ids = set()
        try:
            Vehicle = apps.get_model("vehicles", "Vehicle")
        except Exception:
            return ids

        # 1) try as integer PK
        try:
            pk = int(needle)
            if Vehicle.objects.filter(id=pk).exists():
                ids.add(pk)
        except ValueError:
            pass

        # 2) try common columns inside Vehicle (no join)
        fields = {f.name for f in Vehicle._meta.get_fields()}
        candidates = []
        for col in ["code", "number", "vehicle_code", "car_no", "plate", "plate_no", "name"]:
            if col in fields:
                candidates.append(Q(**{f"{col}__iexact": needle}))
                candidates.append(Q(**{f"{col}__icontains": needle}))
        if candidates:
            q = Q()
            for c in candidates:
                q |= c
            for v in Vehicle.objects.filter(q).values_list("id", flat=True):
                ids.add(v)

        return ids

    def resolve_driver_ids(self, needle: str):
        """
        Return a set of driver/User IDs matching `needle`.
        Tries auth user first, then optional staffbook.Driver if present.
        """
        ids = set()

        # auth user model
        User = get_user_model()
        u_fields = {f.name for f in User._meta.get_fields()}
        user_q = Q()
        if "username" in u_fields:
            user_q |= Q(username__iexact=needle)
        for col in ["code", "employee_no", "name", "email"]:
            if col in u_fields:
                user_q |= Q(**{f"{col}__iexact": needle})
        for uid in User.objects.filter(user_q).values_list("id", flat=True):
            ids.add(uid)

        # optional staffbook.Driver (if Reservation.driver points there)
        try:
            Driver = apps.get_model("staffbook", "Driver")
            d_fields = {f.name for f in Driver._meta.get_fields()}
            d_q = Q()
            for col in ["username", "code", "employee_no", "name", "email"]:
                if col in d_fields:
                    d_q |= Q(**{f"{col}__iexact": needle})
            for did in Driver.objects.filter(d_q).values_list("id", flat=True):
                ids.add(did)
        except Exception:
            pass

        return ids

    def handle(self, *args, **opts):
        dry_run = opts["dry_run"] and not opts["commit"]
        include_past = opts["include_past"]
        ids = opts["ids"]
        v = opts["vehicle"]
        d = opts["driver"]
        status_from = opts["status_from"]
        status_to = opts["status_to"]

        Reservation = apps.get_model("vehicles", "Reservation")
        fields = {f.name for f in Reservation._meta.get_fields()}

        qs = Reservation.objects.all()

        # status 必须命中
        if status_from:
            qs = qs.filter(status=status_from)

        # 仅未来（默认）
        if not include_past and "date" in fields:
            qs = qs.filter(date__gte=date.today())

        # 指定 id
        if ids:
            qs = qs.filter(id__in=ids)

        # 车辆过滤：先解析成 vehicle_id 列表，再用 vehicle_id__in 过滤（避免 join）
        if v:
            veh_ids = self.resolve_vehicle_ids(v)
            if not veh_ids:
                self.stdout.write(self.style.WARNING(f"[vehicle={v}] resolved to 0 ids; nothing to do."))
                return
            qs = qs.filter(vehicle_id__in=list(veh_ids))

        # 司机过滤：同理，先解析 driver_id 列表
        if d:
            drv_ids = self.resolve_driver_ids(d)
            if not drv_ids:
                self.stdout.write(self.style.WARNING(f"[driver={d}] resolved to 0 ids; nothing to do."))
                return
            # 无法确定是 driver 还是 user 外键名？——优先用 driver_id，其次 user_id
            if "driver" in fields:
                qs = qs.filter(driver_id__in=list(drv_ids))
            elif "user" in fields:
                qs = qs.filter(user_id__in=list(drv_ids))
            else:
                self.stdout.write(self.style.ERROR("Reservation has no driver/user FK field to filter by."))
                return

        total = qs.count()
        self.stdout.write(self.style.WARNING(f"Matched {total} reservations."))

        # 预览前 50 条
        sample = list(qs.order_by("date", "start_time", "id").values(
            "id", "date", "start_time", "end_time", "status", "approved", "approved_by_system"
        )[:50])
        for row in sample:
            self.stdout.write(str(row))
        if total > 50:
            self.stdout.write(f"... and {total-50} more")

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry-run mode: no changes written. Use --commit to apply."))
            return

        # 真正写入
        updated = 0
        for r in qs.iterator():
            r.status = status_to
            r.approved = True
            r.approved_by_system = True
            r.save(update_fields=["status", "approved", "approved_by_system"])
            updated += 1

        self.stdout.write(self.style.SUCCESS(f"Updated {updated} reservations."))
