# staffbook/migrations/0018_company_workplace_fk.py
from django.db import migrations, models
import django.db.models.deletion

def forwards(apps, schema_editor):
    Driver    = apps.get_model('staffbook', 'Driver')
    Company   = apps.get_model('staffbook', 'Company')
    Workplace = apps.get_model('staffbook', 'Workplace')

    # 逐条把旧文本值映射到新表，并写回外键
    for d in Driver.objects.all().only('id', 'company', 'workplace'):
        comp_name = (d.company or '').strip() or '未設定'
        comp, _ = Company.objects.get_or_create(name=comp_name)

        wp_name = (d.workplace or '').strip() or '未設定'
        wp, _ = Workplace.objects.get_or_create(company=comp, name=wp_name)

        # 临时字段先写入
        setattr(d, 'company_fk_id', comp.id)
        setattr(d, 'workplace_fk_id', wp.id)
        d.save(update_fields=['company_fk', 'workplace_fk'])

class Migration(migrations.Migration):

    dependencies = [
        ('staffbook', '0017_driverpayrollrecord_progressive_fee'),
    ]

    operations = [
        # 1) 若项目默认 BigAutoField，则这两个 CreateModel 与你的 0001 保持一致
        migrations.CreateModel(
            name='Company',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name='Workplace',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='workplaces', to='staffbook.company')),
            ],
            options={'unique_together': {('company', 'name')}},
        ),

        # 2) 给 Driver 加两个“临时外键”字段
        migrations.AddField(
            model_name='driver',
            name='company_fk',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='drivers_tmp', to='staffbook.company', verbose_name='事業者名'),
        ),
        migrations.AddField(
            model_name='driver',
            name='workplace_fk',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='drivers_tmp2', to='staffbook.workplace', verbose_name='営業所名'),
        ),

        # 3) 把旧文本列数据搬到外键
        migrations.RunPython(forwards, migrations.RunPython.noop),

        # 4) 删除旧文本列
        migrations.RemoveField(model_name='driver', name='company'),
        migrations.RemoveField(model_name='driver', name='workplace'),

        # 5) 把临时外键重命名为正式字段名
        migrations.RenameField(model_name='driver', old_name='company_fk',   new_name='company'),
        migrations.RenameField(model_name='driver', old_name='workplace_fk', new_name='workplace'),
    ]
