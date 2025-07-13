from django.core.management.base import BaseCommand
from django.utils.timezone import localdate
from carinfo.models import Car

class Command(BaseCommand):
    help = '批量更新所有车辆的保险状态（insurance_status）字段'

    def handle(self, *args, **options):
        today = localdate()
        total = 0
        updated = 0

        cars = Car.objects.all()
        for car in cars:
            old_status = car.insurance_status

            if car.insurance_end_date:
                if car.insurance_end_date < today:
                    car.insurance_status = 'expired'
                else:
                    car.insurance_status = 'valid'
            else:
                car.insurance_status = 'none'

            if car.insurance_status != old_status:
                car.save(update_fields=['insurance_status'])
                updated += 1
            total += 1

        self.stdout.write(self.style.SUCCESS(
            f'✅ 已检查 {total} 辆车，更新 {updated} 条记录。'
        ))
