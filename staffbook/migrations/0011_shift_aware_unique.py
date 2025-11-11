# staffbook/migrations/0011_shift_aware_unique.py
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ("staffbook", "0010_driverschedule_uniq_car_per_day"),  # 你的上一版约束迁移名
    ]

    operations = [
        # 1) 删掉旧的 (work_date, assigned_car) 唯一约束
        migrations.RunSQL(
            sql="ALTER TABLE staffbook_driverschedule DROP CONSTRAINT IF EXISTS uniq_car_per_day;",
            reverse_sql="",
        ),
        # 2) 添加新的 (work_date, assigned_car, shift) 唯一约束（Meta 中也写了，双保险）
        migrations.AddConstraint(
            model_name="driverschedule",
            constraint=models.UniqueConstraint(
                fields=("work_date", "assigned_car", "shift"),
                name="uniq_car_per_day_and_shift",
            ),
        ),
    ]
