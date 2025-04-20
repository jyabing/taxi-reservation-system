from django.core.management.base import BaseCommand
from django.utils import timezone
from vehicles.models import Reservation
from datetime import datetime

class Command(BaseCommand):
    help = '自动取消已过期但未出库的预约'

    def handle(self, *args, **kwargs):
        now = timezone.now()
        count = 0
        for r in Reservation.objects.filter(status='reserved', actual_departure__isnull=True):
            end_time = datetime.combine(r.date, r.end_time)
            end_time = timezone.make_aware(end_time)
            if end_time < now:
                r.status = 'canceled'
                r.save()
                count += 1
                self.stdout.write(self.style.WARNING(f"已取消预约：{r}"))

        self.stdout.write(self.style.SUCCESS(f"完成处理：共取消 {count} 条过期预约"))
