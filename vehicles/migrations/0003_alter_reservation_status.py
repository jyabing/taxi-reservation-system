# Generated by Django 5.1.2 on 2025-04-14 03:51

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vehicles', '0002_reservation'),
    ]

    operations = [
        migrations.AlterField(
            model_name='reservation',
            name='status',
            field=models.CharField(choices=[('pending', '申请中'), ('reserved', '已预约'), ('out', '已出库')], default='pending', max_length=10, verbose_name='状态'),
        ),
    ]
