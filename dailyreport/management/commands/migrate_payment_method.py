from django.core.management.base import BaseCommand
from dailyreport.models import DriverDailyReportItem

class Command(BaseCommand):
    help = '统一旧支付方式字段值，更新为新值'

    def handle(self, *args, **options):
        changes = {
            'credit': 'credit_card',
            'charter_bank': 'charter_transfer',
        }

        for old, new in changes.items():
            qs = DriverDailyReportItem.objects.filter(payment_method=old)
            count = qs.count()
            if count > 0:
                qs.update(payment_method=new)
                self.stdout.write(self.style.SUCCESS(f'✅ 更新 {old} → {new}：{count} 条记录'))
            else:
                self.stdout.write(f'➖ 无需更新 {old}')
