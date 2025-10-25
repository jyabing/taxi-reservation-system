from django.db import migrations


def forward_update_own_to_driver(apps, schema_editor):
    Report = apps.get_model('dailyreport', 'DriverDailyReport')
    updated1 = Report.objects.filter(etc_rider_payer='own').update(etc_rider_payer='driver')
    updated2 = Report.objects.filter(etc_empty_card='own').update(etc_empty_card='driver')
    print(f"✅ Updated {updated1} rows in etc_rider_payer, {updated2} rows in etc_empty_card.")


class Migration(migrations.Migration):

    dependencies = [
        ('dailyreport', '0003_alter_driverdailyreport_etc_empty_card_and_more'),  # ← 改成你上一个迁移的文件名
    ]

    operations = [
        migrations.RunPython(forward_update_own_to_driver, migrations.RunPython.noop),
    ]
