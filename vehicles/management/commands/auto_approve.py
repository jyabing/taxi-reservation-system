from django.core.management.base import BaseCommand
from vehicles.models import Reservation
from django.utils.timezone import now, timedelta

class Command(BaseCommand):
    help = '自动通过超过1小时未审批的预约'

    def handle(self, *args, **kwargs):
        threshold = now() - timedelta(hours=1)
        pending = Reservation.objects.filter(
            status='pending',
            approved=False,
            created_at__lt=threshold
        )

        count = 0
        for reservation in pending:
            reservation.status = 'reserved'
            reservation.approved = True
            reservation.approved_by_system = True  # ✅ 系统通过标记为 True
            reservation.approval_time = now()
            reservation.save()
            count += 1
            self.stdout.write(f"✅ 自动审批通过预约：{reservation.id}（{reservation.driver}）")

        if count == 0:
            self.stdout.write("ℹ️ 暂无需要自动审批的预约。")
        else:
            self.stdout.write(f"🎉 共自动审批了 {count} 条预约记录。")
