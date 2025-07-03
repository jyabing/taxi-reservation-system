from django.core.management.base import BaseCommand
from carinfo.models import Car
from vehicles.models import Vehicle  # 仅在迁移时使用

class Command(BaseCommand):
    help = "将旧模型 Vehicle 的数据迁移到新模型 Car"

    def handle(self, *args, **kwargs):
        count_created = 0
        for vehicle in Vehicle.objects.all():
            car, created = Car.objects.get_or_create(
                license_plate=vehicle.license_plate.strip(),
                defaults={
                    "name": vehicle.model,
                    "model": vehicle.model,
                    "status": vehicle.status if vehicle.status in dict(Car.STATUS_CHOICES) else "available",
                    "notes": vehicle.notes or "",
                    "is_active": True,
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"✅ 已创建 Car: {car.license_plate}"))
                count_created += 1
            else:
                self.stdout.write(self.style.WARNING(f"⚠️ 已存在 Car: {car.license_plate}（跳过）"))
        self.stdout.write(self.style.SUCCESS(f"🎉 共迁移 {count_created} 辆车"))
