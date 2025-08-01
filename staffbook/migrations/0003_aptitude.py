# Generated by Django 5.1.2 on 2025-06-16 03:37

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('staffbook', '0002_qualification'),
    ]

    operations = [
        migrations.CreateModel(
            name='Aptitude',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, verbose_name='资质名称')),
                ('issue_date', models.DateField(blank=True, null=True, verbose_name='颁发日期')),
                ('expiry_date', models.DateField(blank=True, null=True, verbose_name='到期日期')),
                ('note', models.TextField(blank=True, verbose_name='备注')),
                ('driver', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='aptitudes', to='staffbook.driver', verbose_name='司机')),
            ],
            options={
                'verbose_name': '资质',
                'verbose_name_plural': '资质',
            },
        ),
    ]
