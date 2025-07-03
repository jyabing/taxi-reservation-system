# ✅ 引入必要模块
from django.core.management.base import BaseCommand
from django.db import connection
from carinfo.models import Car  # 🚗 新模型

# ✅ 命令类定义
class Command(BaseCommand):
    help = "使用 SQL 从旧表 vehicles_vehicle 中导入数据到新模型 Car"

    def handle(self, *args, **kwargs):
        # ✅ 从旧表中提取字段：license_plate, model, status, notes
        with connection.cursor() as cursor:
            cursor.execute("SELECT license_plate, model, status, notes FROM vehicles_vehicle")
            rows = cursor.fetchall()

        count_created = 0  # 用于统计新建数量

        # ✅ 遍历旧数据并写入 Car 模型
        for row in rows:
            license_plate, model, status, notes = row
            if not license_plate:
                continue

            car, created = Car.objects.get_or_create(
                license_plate=license_plate.strip(),
                defaults={
                    "name": model or "",
                    "model": model or "",
                    "status": status if status in dict(Car.STATUS_CHOICES) else "available",
                    "notes": notes or "",
                    "is_active": True,
                }
            )

            # ✅ 输出迁移日志
            if created:
                self.stdout.write(self.style.SUCCESS(f"✅ 创建 Car: {car.license_plate}"))
                count_created += 1
            else:
                self.stdout.write(self.style.WARNING(f"⚠️ 已存在 Car: {car.license_plate}（跳过）"))

        # ✅ 最终统计
        self.stdout.write(self.style.SUCCESS(f"🎉 共迁移 {count_created} 辆车"))
