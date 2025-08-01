# Generated by Django 5.1.2 on 2025-07-16 18:24

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('carinfo', '0006_car_capacity_car_chassis_number_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='car',
            name='car_type_code',
        ),
        migrations.RemoveField(
            model_name='car',
            name='first_registration',
        ),
        migrations.RemoveField(
            model_name='car',
            name='insurance_expiry',
        ),
        migrations.AlterField(
            model_name='car',
            name='chassis_number',
            field=models.CharField(blank=True, max_length=50, verbose_name='车台番号'),
        ),
        migrations.AlterField(
            model_name='car',
            name='department',
            field=models.CharField(blank=True, default='未指定', max_length=50, verbose_name='所属部门'),
        ),
        migrations.AlterField(
            model_name='car',
            name='insurance_end_date',
            field=models.DateField(blank=True, null=True, verbose_name='保険结束日'),
        ),
        migrations.AlterField(
            model_name='car',
            name='insurance_start_date',
            field=models.DateField(blank=True, null=True, verbose_name='保険开始日'),
        ),
        migrations.AlterField(
            model_name='car',
            name='model_code',
            field=models.CharField(blank=True, max_length=50, verbose_name='型式'),
        ),
    ]
