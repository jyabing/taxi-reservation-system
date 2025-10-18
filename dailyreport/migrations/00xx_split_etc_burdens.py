# dailyreport/migrations/00xx_split_etc_burdens.py
from django.db import migrations

def copy_legacy_charge(apps, schema_editor):
    Item = apps.get_model('dailyreport', 'DriverDailyReportItem')
    for it in Item.objects.all().only(
        'id',
        'etc_riding', 'etc_empty',
        'etc_charge_type',
        'etc_riding_charge_type', 'etc_empty_charge_type'
    ):
        updated = False
        if it.etc_riding and not getattr(it, 'etc_riding_charge_type', None):
            it.etc_riding_charge_type = it.etc_charge_type
            updated = True
        if it.etc_empty and not getattr(it, 'etc_empty_charge_type', None):
            it.etc_empty_charge_type = it.etc_charge_type
            updated = True
        if updated:
            it.save(update_fields=['etc_riding_charge_type', 'etc_empty_charge_type'])

class Migration(migrations.Migration):

    dependencies = [
        ('dailyreport', '0007_driverdailyreport_etc_empty_card'),
    ]

    operations = [
        migrations.RunPython(copy_legacy_charge, migrations.RunPython.noop),
    ]
