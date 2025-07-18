# Generated by Django 5.1.2 on 2025-07-03 12:38

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('carinfo', '0003_car_color_car_department_car_etc_device_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='car',
            name='engine_displacement',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=4, null=True, verbose_name='排气量（L）'),
        ),
        migrations.AddField(
            model_name='car',
            name='first_registration_date',
            field=models.DateField(blank=True, null=True, verbose_name='初度登録年月'),
        ),
        migrations.AddField(
            model_name='car',
            name='model_code',
            field=models.CharField(blank=True, max_length=30, verbose_name='型式'),
        ),
        migrations.AddField(
            model_name='car',
            name='registration_number',
            field=models.CharField(blank=True, max_length=20, verbose_name='登録番号'),
        ),
        migrations.AddField(
            model_name='car',
            name='vehicle_weight',
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=6, null=True, verbose_name='车辆重量（kg）'),
        ),
    ]
