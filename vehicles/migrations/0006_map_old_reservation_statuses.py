from django.db import migrations

def map_old_statuses(apps, schema_editor):
    Reservation = apps.get_model("vehicles", "Reservation")
    mapping = {
        "pending":  "applying",
        "reserved": "booked",
        "out":      "departed",
        "completed":"completed",
        "canceled": "canceled",   # 只是显示名改成“决定不出库”
    }
    for old, new in mapping.items():
        Reservation.objects.filter(status=old).update(status=new)

class Migration(migrations.Migration):

    dependencies = [
        ("vehicles", "0005_alter_reservation_status"),
    ]

    operations = [
        migrations.RunPython(map_old_statuses, migrations.RunPython.noop),
    ]
