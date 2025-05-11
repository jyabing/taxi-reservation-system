from django.core.management.base import BaseCommand
from vehicles.tasks import auto_update_reservations

class Command(BaseCommand):
    help = '自动更新预约状态'

    def handle(self, *args, **options):
        auto_update_reservations()
        self.stdout.write(self.style.SUCCESS('✅ 已执行自动更新预约状态'))
