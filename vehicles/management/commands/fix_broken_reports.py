from django.core.management.base import BaseCommand
from vehicles.models import DriverDailyReport
from staffbook.models import Driver
from accounts.models import DriverUser
from django.db import transaction

class Command(BaseCommand):
    help = '修复 DriverDailyReport 中错误的 driver 字段（应为 Driver 实例，实际却是 DriverUser）'

    @transaction.atomic
    def handle(self, *args, **kwargs):
        count_fixed = 0
        broken = DriverDailyReport.objects.filter(driver__isnull=False)
        for report in broken:
            if isinstance(report.driver, DriverUser):
                try:
                    correct_driver = Driver.objects.get(user=report.driver)
                    report.driver = correct_driver
                    report.save()
                    count_fixed += 1
                    self.stdout.write(self.style.SUCCESS(
                        f"已修复报告 ID {report.id}：driver 改为 Driver 实例 {correct_driver}"
                    ))
                except Driver.DoesNotExist:
                    self.stderr.write(self.style.ERROR(
                        f"❌ 报告 ID {report.id} 的 DriverUser {report.driver} 无匹配的 Driver 实例"
                    ))

        self.stdout.write(self.style.SUCCESS(f"✅ 修复完成，共修复 {count_fixed} 条日报记录。"))
