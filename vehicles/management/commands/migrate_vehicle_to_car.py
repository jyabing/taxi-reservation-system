from django.core.management.base import BaseCommand
from vehicles.models import Vehicle
from carinfo.models import Car

class Command(BaseCommand):
    help = "将 vehicles.Vehicle 数据迁移到 carinfo.Car 模型"

    def handle(self, *args, **kwargs):
        count_created = 0
        for vehicle in Vehicle.objects.all():
            car, created = Car.objects.get_or_create(
                license_plate=vehicle.license_plate.strip(),
                defaults={
                    "name": f"{vehicle.model}",              # 车辆名称暂取 model
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
